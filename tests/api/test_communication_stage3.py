"""Tests for Stage 3 (Geo Fencing/Temporary Permissions/MSG91 request): the generalized
`send_now()`, individual "Send Message" on Lead/Customer records (with IDOR/authorization),
CRM entity_type/entity_id message linkage, Bulk Messaging (idempotent enqueue, resumable
worker processing, partial failure, cancel/retry-failed), and a Secure Application Link
regression check (the one pre-existing `send_now` caller, now entity-linked).
"""

import json

from app.features.communication import adapters as communication_adapters
from app.features.communication.constants import Channel, QueueStatus, TemplateCategory
from app.features.communication.models import CommunicationQueueItem, CommunicationTemplate
from app.features.communication.service import CommunicationService
from app.features.communication.template_engine import extract_variable_names
from app.features.customer.models import Application, Customer
from app.features.integrations.models import IntegrationConfig
from app.features.leads.models import Lead
from app.security.encryption import encrypt
from app.utils.helpers import to_object_id


async def _grant_permission(client, owner_headers, employee_id, *, module, resource, actions):
    r = await client.post("/api/v1/permissions", json={"module": module, "resource": resource, "actions": actions}, headers=owner_headers)
    assert r.status_code == 200, r.text
    permission = r.json()["data"]
    r = await client.post("/api/v1/roles", json={"name": f"Role for {module}:{resource}:{employee_id}"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    role = r.json()["data"]
    r = await client.put(
        f"/api/v1/roles/{role['id']}/permissions", json={"grants": [{"permission_id": permission["id"], "granted_actions": actions}]}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/roles/{role['id']}/assign", json={"employee_id": employee_id}, headers=owner_headers)
    assert r.status_code == 200, r.text


async def _login(client, mobile, password):
    r = await client.post("/api/v1/auth/login", json={"mobile": mobile, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def _create_employee(client, owner_headers, master_data, mobile, email):
    payload = {
        "mobile": mobile, "initial_password": "InitialPass1!", "first_name": "Staff", "last_name": "Member", "email": email,
        "department_id": master_data["department_id"], "designation_id": master_data["designation_id"], "branch_id": master_data["branch_id"],
        "joining_date": "2026-01-15", "employment_type": "full_time",
    }
    r = await client.post("/api/v1/employees", json=payload, headers=owner_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _employee_headers_with_send_permission(client, owner_headers, master_data, *, mobile, email):
    employee = await _create_employee(client, owner_headers, master_data, mobile=mobile, email=email)
    await _grant_permission(client, owner_headers, employee["id"], module="communication", resource="send", actions=["view", "create"])
    await _grant_permission(client, owner_headers, employee["id"], module="leads", resource="leads", actions=["view", "create", "edit"])
    headers = await _login(client, mobile, "InitialPass1!")
    return employee, headers


async def _seed_lead(mock_db, *, mobile, full_name="Test Lead", email="lead@example.com", assigned_to=None) -> str:
    lead = Lead(
        lead_code=f"AFS-LEAD-{mobile}", full_name=full_name, mobile=mobile, email=email,
        source_id="000000000000000000000000", product_category="loan", product_id="000000000000000000000000", assigned_to=assigned_to,
    )
    result = await mock_db["leads"].insert_one(lead.model_dump(by_alias=True, exclude={"id"}))
    return str(result.inserted_id)


async def _seed_customer(mock_db, *, mobile, full_name="Test Customer", email="customer@example.com", assigned_employee_id=None) -> str:
    customer = Customer(customer_code=f"AFS-CUS-{mobile}", user_id=str(to_object_id("000000000000000000000000")), full_name=full_name, mobile=mobile, email=email)
    result = await mock_db["customers"].insert_one(customer.model_dump(by_alias=True, exclude={"id"}))
    customer_id = str(result.inserted_id)
    if assigned_employee_id is not None:
        application = Application(
            application_code=f"AFS-APP-{mobile}", user_id=customer.user_id, customer_id=customer_id,
            product_category="loan", product_id="000000000000000000000000", form_definition_id="000000000000000000000000",
            assigned_to=assigned_employee_id,
        )
        await mock_db["applications"].insert_one(application.model_dump(by_alias=True, exclude={"id"}))
    return customer_id


async def _seed_template(mock_db, *, channel: str, category: str = TemplateCategory.WELCOME, body: str = "Hi {{customer_name}}, ref {{lead_code}}", subject: str | None = None) -> str:
    template = CommunicationTemplate(name=f"{category}-{channel}", channel=channel, category=category, subject=subject, body=body, variables=extract_variable_names(body))
    result = await mock_db["communication_templates"].insert_one(template.model_dump(by_alias=True, exclude={"id"}))
    return str(result.inserted_id)


async def _seed_active_config(mock_db, *, channel: str, provider: str = "generic") -> None:
    config = IntegrationConfig(
        integration_code=f"AFS-INTG-{channel.upper()}", integration_type=channel, provider=provider, name=f"{channel} test",
        config_encrypted=encrypt(json.dumps({"api_url": "https://example.test/send", "api_key": "key123", "access_token": "tok123"})),
        is_enabled=True, is_active=True,
    )
    await mock_db["integration_configs"].insert_one(config.model_dump(by_alias=True, exclude={"id"}))


def _install_fake_adapter(monkeypatch, *, success=True, is_transient=False, error=None):
    async def _fake(*, recipient, subject, body, config, **_kwargs):
        return communication_adapters.DeliveryOutcome(success, "MSGID-STAGE3" if success else None, error, is_transient=is_transient)

    monkeypatch.setitem(communication_adapters.ADAPTERS, Channel.WHATSAPP, _fake)
    monkeypatch.setitem(communication_adapters.ADAPTERS, Channel.SMS, _fake)
    monkeypatch.setitem(communication_adapters.ADAPTERS, Channel.EMAIL, _fake)


# ---------------------------------------------------------------------- individual "Send Message"


async def test_send_message_to_lead_success_and_linkage(client, mock_db, owner_headers, master_data, monkeypatch):
    _install_fake_adapter(monkeypatch, success=True)
    await _seed_active_config(mock_db, channel=Channel.WHATSAPP)
    lead_id = await _seed_lead(mock_db, mobile="9611110001")
    template_id = await _seed_template(mock_db, channel=Channel.WHATSAPP, body="Hi {{customer_name}}")

    r = await client.post(
        "/api/v1/communication/messages",
        json={"entity_type": "lead", "entity_id": lead_id, "channel": "whatsapp", "template_id": template_id},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["success"] is True
    assert data["queue_item_id"]

    r = await client.get(f"/api/v1/communication/messages?entity_type=lead&entity_id={lead_id}", headers=owner_headers)
    assert r.status_code == 200, r.text
    messages = r.json()["data"]
    assert len(messages) == 1
    assert messages[0]["entity_type"] == "lead"
    assert messages[0]["entity_id"] == lead_id
    assert messages[0]["status"] == "sent"


async def test_send_message_to_customer_success(client, mock_db, owner_headers, master_data, monkeypatch):
    _install_fake_adapter(monkeypatch, success=True)
    await _seed_active_config(mock_db, channel=Channel.SMS)
    customer_id = await _seed_customer(mock_db, mobile="9611110002")
    template_id = await _seed_template(mock_db, channel=Channel.SMS)

    r = await client.post(
        "/api/v1/communication/messages",
        json={"entity_type": "customer", "entity_id": customer_id, "channel": "sms", "template_id": template_id},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["success"] is True


async def test_send_message_email_channel(client, mock_db, owner_headers, master_data, monkeypatch):
    _install_fake_adapter(monkeypatch, success=True)
    await _seed_active_config(mock_db, channel=Channel.EMAIL)
    lead_id = await _seed_lead(mock_db, mobile="9611110003", email="reachable@example.com")
    template_id = await _seed_template(mock_db, channel=Channel.EMAIL, subject="Update")

    r = await client.post(
        "/api/v1/communication/messages",
        json={"entity_type": "lead", "entity_id": lead_id, "channel": "email", "template_id": template_id},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["success"] is True


async def test_send_message_invalid_recipient_no_email(client, mock_db, owner_headers, master_data, monkeypatch):
    _install_fake_adapter(monkeypatch, success=True)
    await _seed_active_config(mock_db, channel=Channel.EMAIL)
    lead = Lead(
        lead_code="AFS-LEAD-NOEMAIL", full_name="No Email", mobile="9611110004", email=None,
        source_id="000000000000000000000000", product_category="loan", product_id="000000000000000000000000",
    )
    result = await mock_db["leads"].insert_one(lead.model_dump(by_alias=True, exclude={"id"}))
    lead_id = str(result.inserted_id)
    template_id = await _seed_template(mock_db, channel=Channel.EMAIL, subject="Update")

    r = await client.post(
        "/api/v1/communication/messages",
        json={"entity_type": "lead", "entity_id": lead_id, "channel": "email", "template_id": template_id},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["success"] is False
    assert data["error"] == "Invalid recipient."


async def test_send_message_missing_template_is_clear_error(client, mock_db, owner_headers, master_data):
    lead_id = await _seed_lead(mock_db, mobile="9611110005")
    r = await client.post(
        "/api/v1/communication/messages",
        json={"entity_type": "lead", "entity_id": lead_id, "channel": "whatsapp", "template_id": "000000000000000000000000"},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["success"] is False
    assert data["error"] == "Message template is invalid or not approved."


async def test_send_message_wrong_channel_template_rejected(client, mock_db, owner_headers, master_data):
    lead_id = await _seed_lead(mock_db, mobile="9611110006")
    sms_template_id = await _seed_template(mock_db, channel=Channel.SMS)
    r = await client.post(
        "/api/v1/communication/messages",
        json={"entity_type": "lead", "entity_id": lead_id, "channel": "whatsapp", "template_id": sms_template_id},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["error"] == "Message template is invalid or not approved."


async def test_send_message_missing_provider_config_surfaces_real_error(client, mock_db, owner_headers, master_data):
    lead_id = await _seed_lead(mock_db, mobile="9611110007")
    template_id = await _seed_template(mock_db, channel=Channel.WHATSAPP)
    r = await client.post(
        "/api/v1/communication/messages",
        json={"entity_type": "lead", "entity_id": lead_id, "channel": "whatsapp", "template_id": template_id},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["success"] is False
    assert "No active whatsapp integration is configured" in data["error"]


async def test_send_message_forged_lead_id_returns_not_found(client, mock_db, owner_headers, master_data):
    template_id = await _seed_template(mock_db, channel=Channel.WHATSAPP)
    r = await client.post(
        "/api/v1/communication/messages",
        json={"entity_type": "lead", "entity_id": "000000000000000000000000", "channel": "whatsapp", "template_id": template_id},
        headers=owner_headers,
    )
    assert r.status_code == 404, r.text


async def test_send_message_unsupported_entity_type_rejected(client, mock_db, owner_headers, master_data):
    template_id = await _seed_template(mock_db, channel=Channel.WHATSAPP)
    r = await client.post(
        "/api/v1/communication/messages",
        json={"entity_type": "employee", "entity_id": "000000000000000000000000", "channel": "whatsapp", "template_id": template_id},
        headers=owner_headers,
    )
    assert r.status_code == 422, r.text  # pattern-validated at the schema layer


# ---------------------------------------------------------------------- authorization / IDOR


async def test_employee_without_communication_permission_is_denied(client, mock_db, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data, mobile="9622220001", email="nosend@example.com")
    headers = await _login(client, "9622220001", "InitialPass1!")
    lead_id = await _seed_lead(mock_db, mobile="9611110008")
    template_id = await _seed_template(mock_db, channel=Channel.WHATSAPP)

    r = await client.post(
        "/api/v1/communication/messages",
        json={"entity_type": "lead", "entity_id": lead_id, "channel": "whatsapp", "template_id": template_id},
        headers=headers,
    )
    assert r.status_code == 403, r.text
    assert employee["id"]  # keep flake8/ruff happy about unused var while documenting intent


async def test_employee_cannot_send_message_for_unassigned_lead(client, mock_db, owner_headers, master_data, monkeypatch):
    _install_fake_adapter(monkeypatch, success=True)
    await _seed_active_config(mock_db, channel=Channel.WHATSAPP)
    other_employee = await _create_employee(client, owner_headers, master_data, mobile="9622220010", email="other@example.com")
    _, headers = await _employee_headers_with_send_permission(client, owner_headers, master_data, mobile="9622220002", email="assignee@example.com")

    lead_id = await _seed_lead(mock_db, mobile="9611110009", assigned_to=other_employee["id"])
    template_id = await _seed_template(mock_db, channel=Channel.WHATSAPP)

    r = await client.post(
        "/api/v1/communication/messages",
        json={"entity_type": "lead", "entity_id": lead_id, "channel": "whatsapp", "template_id": template_id},
        headers=headers,
    )
    assert r.status_code == 403, r.text


async def test_employee_can_send_message_for_own_assigned_lead(client, mock_db, owner_headers, master_data, monkeypatch):
    _install_fake_adapter(monkeypatch, success=True)
    await _seed_active_config(mock_db, channel=Channel.WHATSAPP)
    employee, headers = await _employee_headers_with_send_permission(client, owner_headers, master_data, mobile="9622220003", email="assignee2@example.com")
    lead_id = await _seed_lead(mock_db, mobile="9611110010", assigned_to=employee["id"])
    template_id = await _seed_template(mock_db, channel=Channel.WHATSAPP)

    r = await client.post(
        "/api/v1/communication/messages",
        json={"entity_type": "lead", "entity_id": lead_id, "channel": "whatsapp", "template_id": template_id},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["success"] is True


async def test_employee_cannot_send_message_for_unassigned_customer(client, mock_db, owner_headers, master_data):
    _, headers = await _employee_headers_with_send_permission(client, owner_headers, master_data, mobile="9622220004", email="custnoaccess@example.com")
    customer_id = await _seed_customer(mock_db, mobile="9611110011")  # no application assignment
    template_id = await _seed_template(mock_db, channel=Channel.SMS)

    r = await client.post(
        "/api/v1/communication/messages",
        json={"entity_type": "customer", "entity_id": customer_id, "channel": "sms", "template_id": template_id},
        headers=headers,
    )
    assert r.status_code == 403, r.text


async def test_employee_cannot_view_messages_for_unassigned_lead(client, mock_db, owner_headers, master_data):
    other_employee = await _create_employee(client, owner_headers, master_data, mobile="9622220011", email="other2@example.com")
    _, headers = await _employee_headers_with_send_permission(client, owner_headers, master_data, mobile="9622220005", email="viewnoaccess@example.com")
    lead_id = await _seed_lead(mock_db, mobile="9611110012", assigned_to=other_employee["id"])

    r = await client.get(f"/api/v1/communication/messages?entity_type=lead&entity_id={lead_id}", headers=headers)
    assert r.status_code == 403, r.text


async def test_unauthenticated_cannot_send_message(client, mock_db):
    lead_id = await _seed_lead(mock_db, mobile="9611110013")
    r = await client.post("/api/v1/communication/messages", json={"entity_type": "lead", "entity_id": lead_id, "channel": "whatsapp", "template_id": "000000000000000000000000"})
    assert r.status_code in (401, 403), r.text


# ---------------------------------------------------------------------- Secure Application Link regression + linkage


async def test_secure_link_notify_still_works_and_now_links_to_lead(client, mock_db, owner_headers, master_data, monkeypatch):
    _install_fake_adapter(monkeypatch, success=True)
    await _seed_active_config(mock_db, channel=Channel.WHATSAPP)
    await _seed_template(mock_db, channel=Channel.WHATSAPP, category=TemplateCategory.SECURE_LINK, body="Hi {{customer_name}}, {{secure_link}}")

    lead = Lead(
        lead_code="AFS-LEAD-SECURELINK", full_name="Secure Link Lead", mobile="9611119999",
        source_id="000000000000000000000000", product_category="loan", product_id="000000000000000000000000",
    )
    result = await mock_db["leads"].insert_one(lead.model_dump(by_alias=True, exclude={"id"}))
    lead_id = str(result.inserted_id)

    r = await client.post(f"/api/v1/leads/{lead_id}/secure-links", json={}, headers=owner_headers)
    assert r.status_code == 200, r.text
    link = r.json()["data"]

    r = await client.post(f"/api/v1/secure-links/{link['id']}/notify", json={"channels": ["whatsapp"]}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["notification_status"]["whatsapp"] == "sent"

    r = await client.get(f"/api/v1/communication/messages?entity_type=lead&entity_id={lead_id}", headers=owner_headers)
    assert r.status_code == 200, r.text
    messages = r.json()["data"]
    assert len(messages) == 1
    assert messages[0]["entity_type"] == "lead"
    assert messages[0]["entity_id"] == lead_id


# ---------------------------------------------------------------------- bulk messaging


async def test_create_bulk_job_dedupes_and_reports_recipient_count(client, mock_db, owner_headers, master_data):
    lead_a = await _seed_lead(mock_db, mobile="9633330001")
    lead_b = await _seed_lead(mock_db, mobile="9633330002")
    template_id = await _seed_template(mock_db, channel=Channel.WHATSAPP)

    r = await client.post(
        "/api/v1/communication/bulk-messages",
        json={"channel": "whatsapp", "template_id": template_id, "recipient_type": "lead", "recipient_ids": [lead_a, lead_b, lead_a]},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["recipient_count"] == 2  # deduped
    assert data["status"] == "queued"


async def test_create_bulk_job_rejects_missing_template(client, mock_db, owner_headers, master_data):
    lead_id = await _seed_lead(mock_db, mobile="9633330003")
    r = await client.post(
        "/api/v1/communication/bulk-messages",
        json={"channel": "whatsapp", "template_id": "000000000000000000000000", "recipient_type": "lead", "recipient_ids": [lead_id]},
        headers=owner_headers,
    )
    assert r.status_code == 422, r.text


async def test_create_bulk_job_rejects_empty_recipients(client, mock_db, owner_headers, master_data):
    template_id = await _seed_template(mock_db, channel=Channel.WHATSAPP)
    r = await client.post(
        "/api/v1/communication/bulk-messages",
        json={"channel": "whatsapp", "template_id": template_id, "recipient_type": "lead", "recipient_ids": []},
        headers=owner_headers,
    )
    assert r.status_code == 422, r.text  # min_length=1 on the schema


async def test_bulk_job_requires_bulk_permission(client, mock_db, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data, mobile="9622220006", email="nobulk@example.com")
    headers = await _login(client, "9622220006", "InitialPass1!")
    template_id = await _seed_template(mock_db, channel=Channel.WHATSAPP)
    lead_id = await _seed_lead(mock_db, mobile="9633330004")

    r = await client.post(
        "/api/v1/communication/bulk-messages",
        json={"channel": "whatsapp", "template_id": template_id, "recipient_type": "lead", "recipient_ids": [lead_id]},
        headers=headers,
    )
    assert r.status_code == 403, r.text
    assert employee["id"]


async def test_process_bulk_message_jobs_enqueues_and_skips_no_contact(client, mock_db, owner_headers, master_data):
    good_lead = await _seed_lead(mock_db, mobile="9633330005")
    no_email_lead = Lead(
        lead_code="AFS-LEAD-NOEMAIL2", full_name="No Email Bulk", mobile="9633330006", email=None,
        source_id="000000000000000000000000", product_category="loan", product_id="000000000000000000000000",
    )
    result = await mock_db["leads"].insert_one(no_email_lead.model_dump(by_alias=True, exclude={"id"}))
    no_email_lead_id = str(result.inserted_id)

    template_id = await _seed_template(mock_db, channel=Channel.EMAIL, subject="Update")
    r = await client.post(
        "/api/v1/communication/bulk-messages",
        json={"channel": "email", "template_id": template_id, "recipient_type": "lead", "recipient_ids": [good_lead, no_email_lead_id]},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    job_id = r.json()["data"]["id"]

    service = CommunicationService(mock_db)
    await service.process_bulk_message_jobs()

    job = await service.get_bulk_message_job(job_id)
    assert job.status == "completed"
    assert job.queued_count == 1
    assert job.skipped_count == 1

    queued_items = await mock_db["communication_queue"].find({"business_event": f"bulk:{job_id}"}).to_list(length=10)
    assert len(queued_items) == 1
    assert queued_items[0]["entity_id"] == good_lead


async def test_process_bulk_message_jobs_is_idempotent_on_reprocessing(client, mock_db, owner_headers, master_data):
    """Simulates a worker restart re-processing an already-(partially-)handled job —
    must never create a second CommunicationQueueItem for the same recipient/channel."""
    lead_id = await _seed_lead(mock_db, mobile="9633330007")
    template_id = await _seed_template(mock_db, channel=Channel.WHATSAPP)
    r = await client.post(
        "/api/v1/communication/bulk-messages",
        json={"channel": "whatsapp", "template_id": template_id, "recipient_type": "lead", "recipient_ids": [lead_id]},
        headers=owner_headers,
    )
    job_id = r.json()["data"]["id"]

    service = CommunicationService(mock_db)
    await service.process_bulk_message_jobs()
    first_count = await mock_db["communication_queue"].count_documents({"business_event": f"bulk:{job_id}"})
    assert first_count == 1

    # Force the job back into a re-processable state (worker-restart simulation) — real
    # idempotency guarantee is the (business_event, entity_type, entity_id, channel)
    # dedup check inside _enqueue_bulk_recipient, not next_index alone.
    await mock_db["bulk_message_jobs"].update_one({"_id": to_object_id(job_id)}, {"$set": {"status": "processing", "next_index": 0, "queued_count": 0}})
    await service.process_bulk_message_jobs()

    second_count = await mock_db["communication_queue"].count_documents({"business_event": f"bulk:{job_id}"})
    assert second_count == 1  # never duplicated


async def test_process_bulk_message_jobs_resumes_across_multiple_batches(client, mock_db, owner_headers, master_data, monkeypatch):
    """Small BULK_ENQUEUE_BATCH_SIZE forces multiple ticks — proves next_index actually
    advances incrementally (queue recovery / worker restart resilience) rather than the
    whole job being processed in one shot regardless of batch size."""
    monkeypatch.setattr("app.features.communication.service.BULK_ENQUEUE_BATCH_SIZE", 1)
    lead_ids = [await _seed_lead(mock_db, mobile=f"96333400{i:02d}") for i in range(3)]
    template_id = await _seed_template(mock_db, channel=Channel.WHATSAPP)
    r = await client.post(
        "/api/v1/communication/bulk-messages",
        json={"channel": "whatsapp", "template_id": template_id, "recipient_type": "lead", "recipient_ids": lead_ids},
        headers=owner_headers,
    )
    job_id = r.json()["data"]["id"]

    service = CommunicationService(mock_db)
    await service.process_bulk_message_jobs()
    job = await service.get_bulk_message_job(job_id)
    assert job.next_index == 1
    assert job.status == "processing"

    await service.process_bulk_message_jobs()
    await service.process_bulk_message_jobs()
    job = await service.get_bulk_message_job(job_id)
    assert job.next_index == 3
    assert job.status == "completed"
    assert job.queued_count == 3


async def test_bulk_job_progress_reflects_actual_send_outcomes(client, mock_db, owner_headers, master_data, monkeypatch):
    _install_fake_adapter(monkeypatch, success=True)
    await _seed_active_config(mock_db, channel=Channel.WHATSAPP)
    lead_id = await _seed_lead(mock_db, mobile="9633350001")
    template_id = await _seed_template(mock_db, channel=Channel.WHATSAPP)

    r = await client.post(
        "/api/v1/communication/bulk-messages",
        json={"channel": "whatsapp", "template_id": template_id, "recipient_type": "lead", "recipient_ids": [lead_id]},
        headers=owner_headers,
    )
    job_id = r.json()["data"]["id"]

    service = CommunicationService(mock_db)
    await service.process_bulk_message_jobs()  # enqueues (PENDING)
    await service.process_pending_queue()  # actually sends (via the existing, unmodified pipeline)

    r = await client.get(f"/api/v1/communication/bulk-messages/{job_id}", headers=owner_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["sent"] == 1
    assert data["failed"] == 0


async def test_bulk_job_failed_messages_and_retry(client, mock_db, owner_headers, master_data, monkeypatch):
    _install_fake_adapter(monkeypatch, success=False, is_transient=False, error="Invalid recipient.")
    await _seed_active_config(mock_db, channel=Channel.WHATSAPP)
    lead_id = await _seed_lead(mock_db, mobile="9633350002")
    template_id = await _seed_template(mock_db, channel=Channel.WHATSAPP)

    r = await client.post(
        "/api/v1/communication/bulk-messages",
        json={"channel": "whatsapp", "template_id": template_id, "recipient_type": "lead", "recipient_ids": [lead_id]},
        headers=owner_headers,
    )
    job_id = r.json()["data"]["id"]

    service = CommunicationService(mock_db)
    await service.process_bulk_message_jobs()
    await service.process_pending_queue()  # permanent failure -> status "failed"

    r = await client.get(f"/api/v1/communication/bulk-messages/{job_id}/failed", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 1

    # Flip the adapter to succeed, then retry.
    _install_fake_adapter(monkeypatch, success=True)
    r = await client.post(f"/api/v1/communication/bulk-messages/{job_id}/retry-failed", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["retried_count"] == 1

    r = await client.get(f"/api/v1/communication/bulk-messages/{job_id}", headers=owner_headers)
    assert r.json()["data"]["failed"] == 0
    assert r.json()["data"]["sent"] == 1


async def test_bulk_job_cancel_stops_further_processing(client, mock_db, owner_headers, master_data, monkeypatch):
    monkeypatch.setattr("app.features.communication.service.BULK_ENQUEUE_BATCH_SIZE", 1)
    lead_ids = [await _seed_lead(mock_db, mobile=f"96333600{i:02d}") for i in range(2)]
    template_id = await _seed_template(mock_db, channel=Channel.WHATSAPP)
    r = await client.post(
        "/api/v1/communication/bulk-messages",
        json={"channel": "whatsapp", "template_id": template_id, "recipient_type": "lead", "recipient_ids": lead_ids},
        headers=owner_headers,
    )
    job_id = r.json()["data"]["id"]

    r = await client.post(f"/api/v1/communication/bulk-messages/{job_id}/cancel", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "cancelled"

    service = CommunicationService(mock_db)
    await service.process_bulk_message_jobs()  # a cancelled job must not be picked up
    queued_items = await mock_db["communication_queue"].count_documents({"business_event": f"bulk:{job_id}"})
    assert queued_items == 0


async def test_cannot_cancel_completed_bulk_job(client, mock_db, owner_headers, master_data):
    lead_id = await _seed_lead(mock_db, mobile="9633370001")
    template_id = await _seed_template(mock_db, channel=Channel.WHATSAPP)
    r = await client.post(
        "/api/v1/communication/bulk-messages",
        json={"channel": "whatsapp", "template_id": template_id, "recipient_type": "lead", "recipient_ids": [lead_id]},
        headers=owner_headers,
    )
    job_id = r.json()["data"]["id"]

    service = CommunicationService(mock_db)
    await service.process_bulk_message_jobs()  # completes immediately (1 recipient, default batch size)

    r = await client.post(f"/api/v1/communication/bulk-messages/{job_id}/cancel", headers=owner_headers)
    assert r.status_code == 422, r.text


async def test_bulk_messaging_to_customers(client, mock_db, owner_headers, master_data, monkeypatch):
    _install_fake_adapter(monkeypatch, success=True)
    await _seed_active_config(mock_db, channel=Channel.SMS)
    customer_id = await _seed_customer(mock_db, mobile="9633380001")
    template_id = await _seed_template(mock_db, channel=Channel.SMS)

    r = await client.post(
        "/api/v1/communication/bulk-messages",
        json={"channel": "sms", "template_id": template_id, "recipient_type": "customer", "recipient_ids": [customer_id]},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    job_id = r.json()["data"]["id"]

    service = CommunicationService(mock_db)
    await service.process_bulk_message_jobs()
    await service.process_pending_queue()

    r = await client.get(f"/api/v1/communication/bulk-messages/{job_id}", headers=owner_headers)
    assert r.json()["data"]["sent"] == 1

    # And it's linked to the Customer's own message history too.
    r = await client.get(f"/api/v1/communication/messages?entity_type=customer&entity_id={customer_id}", headers=owner_headers)
    assert len(r.json()["data"]) == 1


async def test_bulk_job_not_found_returns_404(client, owner_headers):
    r = await client.get("/api/v1/communication/bulk-messages/000000000000000000000000", headers=owner_headers)
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------- generalized send_now() direct unit coverage


async def test_send_now_requires_exactly_one_of_category_or_template_id(mock_db):
    service = CommunicationService(mock_db)
    from app.core.exceptions import ValidationError

    try:
        await service.send_now(channel=Channel.WHATSAPP, recipient="9876543210", variables={}, entity_type="lead", entity_id="x")
    except ValidationError:
        pass
    else:
        raise AssertionError("expected ValidationError when neither category nor template_id is given")

    template_id = await _seed_template(mock_db, channel=Channel.WHATSAPP)
    try:
        await service.send_now(
            channel=Channel.WHATSAPP, recipient="9876543210", variables={}, entity_type="lead", entity_id="x",
            category=TemplateCategory.WELCOME, template_id=template_id,
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("expected ValidationError when both category and template_id are given")


async def test_send_now_entity_linkage_persisted_on_queue_item(mock_db, monkeypatch):
    _install_fake_adapter(monkeypatch, success=True)
    await _seed_active_config(mock_db, channel=Channel.WHATSAPP)
    template_id = await _seed_template(mock_db, channel=Channel.WHATSAPP)
    service = CommunicationService(mock_db)

    success, queue_item_id, error = await service.send_now(
        channel=Channel.WHATSAPP, recipient="9876543210", variables={"customer_name": "Test"},
        entity_type="lead", entity_id="lead-abc-123", template_id=template_id,
    )
    assert success is True
    assert error is None
    item = await mock_db["communication_queue"].find_one({"_id": to_object_id(queue_item_id)})
    assert item["entity_type"] == "lead"
    assert item["entity_id"] == "lead-abc-123"


async def test_send_now_transient_failure_still_enters_retry_pipeline(mock_db, monkeypatch):
    """Send Message going through the exact same retry/backoff machinery as every other
    queued message — a transient provider failure schedules a retry, it isn't lost."""
    _install_fake_adapter(monkeypatch, success=False, is_transient=True, error="timeout")
    await _seed_active_config(mock_db, channel=Channel.WHATSAPP)
    template_id = await _seed_template(mock_db, channel=Channel.WHATSAPP)
    service = CommunicationService(mock_db)

    success, queue_item_id, _error = await service.send_now(
        channel=Channel.WHATSAPP, recipient="9876543210", variables={}, entity_type="lead", entity_id="lead-xyz", template_id=template_id,
    )
    assert success is False
    item = await mock_db["communication_queue"].find_one({"_id": to_object_id(queue_item_id)})
    assert item["status"] == QueueStatus.RETRYING
    assert item["retry_count"] == 1
    assert isinstance(CommunicationQueueItem.model_validate(item), CommunicationQueueItem)  # sanity: still a well-formed document
