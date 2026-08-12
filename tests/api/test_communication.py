"""End-to-end tests for Module 9C (Communication Engine): Template Management CRUD
(permission-gated), the business-event poller (`lead_assigned` audit log -> enqueue ->
send, idempotent on re-poll), transient-failure retry/backoff + exhaustion,
permanent-failure (no retry), and the manual Retry Action.
"""

import json

from app.features.communication import adapters as communication_adapters
from app.features.communication.constants import Channel, QueueStatus, TemplateCategory
from app.features.communication.models import CommunicationQueueItem, CommunicationTemplate
from app.features.communication.service import CommunicationService
from app.features.communication.template_engine import extract_variable_names, render
from app.features.integrations.models import IntegrationConfig
from app.security.encryption import encrypt
from app.shared.audit_log import write_audit_log


async def _grant_permission(client, owner_headers, employee_id, *, module, resource, actions):
    r = await client.post("/api/v1/permissions", json={"module": module, "resource": resource, "actions": actions}, headers=owner_headers)
    if r.status_code == 409:
        existing = await client.get("/api/v1/permissions", headers=owner_headers)
        permission = next(p for p in existing.json()["data"] if p["module"] == module and p["resource"] == resource)
    else:
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


async def _seed_active_config(mock_db, *, channel: str, provider: str = "generic") -> None:
    config = IntegrationConfig(
        integration_code=f"AFS-INTG-{channel.upper()}", integration_type=channel, provider=provider, name=f"{channel} test",
        config_encrypted=encrypt(json.dumps({"api_url": "https://example.test/send", "api_key": "key123", "access_token": "tok123"})),
        is_enabled=True, is_active=True,
    )
    await mock_db["integration_configs"].insert_one(config.model_dump(by_alias=True, exclude={"id"}))


async def _seed_template(mock_db, *, channel: str, category: str, body: str = "Hello {{name}}", subject: str | None = None) -> dict:
    template = CommunicationTemplate(name=f"{category}-{channel}", channel=channel, category=category, subject=subject, body=body, variables=extract_variable_names(body))
    result = await mock_db["communication_templates"].insert_one(template.model_dump(by_alias=True, exclude={"id"}))
    return await mock_db["communication_templates"].find_one({"_id": result.inserted_id})


def test_template_engine_render_and_extract():
    assert render("Hi {{name}}, code {{lead_code}}.", {"name": "Jane"}) == "Hi Jane, code {{lead_code}}."
    assert extract_variable_names("Hi {{name}}, {{name}} and {{lead_code}}") == ["lead_code", "name"]


async def test_template_management_crud_and_permissions(client, mock_db, owner_headers, employee_headers, master_data):
    r = await client.post(
        "/api/v1/communication/templates", json={"name": "Welcome WA", "channel": "whatsapp", "category": "welcome", "body": "Hi {{name}}"}, headers=employee_headers
    )
    assert r.status_code == 403, r.text

    employee = await _create_employee(client, owner_headers, master_data, mobile="9900000301", email="comm.staff@example.com")
    await _grant_permission(client, owner_headers, employee["id"], module="communication", resource="templates", actions=["view", "create", "edit"])
    granted_headers = await _login(client, "9900000301", "InitialPass1!")

    r = await client.post(
        "/api/v1/communication/templates",
        json={"name": "Welcome WA", "channel": "whatsapp", "category": "welcome", "body": "Hi {{name}}, welcome!"},
        headers=granted_headers,
    )
    assert r.status_code == 200, r.text
    template = r.json()["data"]
    assert template["variables"] == ["name"]
    assert template["status"] == "active"

    r = await client.get("/api/v1/communication/templates", headers=granted_headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 1

    r = await client.get(f"/api/v1/communication/templates/{template['id']}", headers=granted_headers)
    assert r.status_code == 200, r.text

    r = await client.patch(f"/api/v1/communication/templates/{template['id']}", json={"body": "Hi {{name}} re: {{lead_code}}!"}, headers=granted_headers)
    assert r.status_code == 200, r.text
    assert set(r.json()["data"]["variables"]) == {"name", "lead_code"}


async def test_lead_assigned_business_event_enqueues_sends_and_is_idempotent(client, mock_db, owner_headers, master_data, monkeypatch):
    employee = await _create_employee(client, owner_headers, master_data, mobile="9876540001", email="assignee@example.com")
    await _seed_template(mock_db, channel=Channel.WHATSAPP, category=TemplateCategory.LEAD_ASSIGNED, body="New lead {{lead_id}} assigned to you.")
    await _seed_active_config(mock_db, channel=Channel.WHATSAPP)

    await write_audit_log(mock_db, event_type="lead_assigned", user_id=None, metadata={"employee_id": employee["id"], "lead_id": "LEAD100"})

    async def _fake_send(*, recipient, subject, body, config):
        assert recipient == "9876540001"
        assert "LEAD100" in body
        return communication_adapters.DeliveryOutcome(True, "MSGID1", None, is_transient=False)

    monkeypatch.setitem(communication_adapters.ADAPTERS, Channel.WHATSAPP, _fake_send)

    service = CommunicationService(mock_db)
    await service.poll_business_events()

    queued = await mock_db["communication_queue"].find_one({"business_event": "lead_assigned"})
    assert queued is not None
    assert queued["status"] == QueueStatus.PENDING
    assert queued["recipient"] == "9876540001"
    assert "LEAD100" in queued["rendered_body"]

    await service.process_pending_queue()

    sent = await mock_db["communication_queue"].find_one({"_id": queued["_id"]})
    assert sent["status"] == QueueStatus.SENT
    assert sent["provider_message_id"] == "MSGID1"
    assert sent["sent_at"] is not None

    history = await mock_db["communication_history"].find_one({"queue_item_id": str(queued["_id"])})
    assert history is not None
    assert history["status"] == QueueStatus.SENT

    # Idempotent — a second poll never enqueues a duplicate for the same (event, entity, channel).
    await service.poll_business_events()
    count = await mock_db["communication_queue"].count_documents({"business_event": "lead_assigned"})
    assert count == 1


async def test_transient_failure_schedules_backoff_retry(mock_db, monkeypatch):
    template = await _seed_template(mock_db, channel=Channel.SMS, category=TemplateCategory.WELCOME, body="Hi {{name}}")
    await _seed_active_config(mock_db, channel=Channel.SMS)
    service = CommunicationService(mock_db)

    item = CommunicationQueueItem(channel=Channel.SMS, recipient="9999999998", template_id=str(template["_id"]), variables={}, rendered_body="Hi there")
    result = await mock_db["communication_queue"].insert_one(item.model_dump(by_alias=True, exclude={"id"}))
    queue_item_id = str(result.inserted_id)

    async def _fake_fail_transient(*, recipient, subject, body, config):
        return communication_adapters.DeliveryOutcome(False, None, "temporary provider error", is_transient=True)

    monkeypatch.setitem(communication_adapters.ADAPTERS, Channel.SMS, _fake_fail_transient)
    await service._send_one(queue_item_id)

    updated = await mock_db["communication_queue"].find_one({"_id": result.inserted_id})
    assert updated["status"] == QueueStatus.RETRYING
    assert updated["retry_count"] == 1
    assert updated["next_retry_at"] is not None


async def test_transient_failure_exhausts_after_max_attempts(mock_db, monkeypatch):
    template = await _seed_template(mock_db, channel=Channel.SMS, category=TemplateCategory.WELCOME, body="Hi {{name}}")
    await _seed_active_config(mock_db, channel=Channel.SMS)
    service = CommunicationService(mock_db)

    item = CommunicationQueueItem(
        channel=Channel.SMS, recipient="9999999999", template_id=str(template["_id"]), variables={}, rendered_body="Hi there",
        status=QueueStatus.RETRYING, retry_count=4,
    )
    result = await mock_db["communication_queue"].insert_one(item.model_dump(by_alias=True, exclude={"id"}))
    queue_item_id = str(result.inserted_id)

    async def _fake_fail_transient(*, recipient, subject, body, config):
        return communication_adapters.DeliveryOutcome(False, None, "still failing", is_transient=True)

    monkeypatch.setitem(communication_adapters.ADAPTERS, Channel.SMS, _fake_fail_transient)
    await service._send_one(queue_item_id)

    updated = await mock_db["communication_queue"].find_one({"_id": result.inserted_id})
    assert updated["status"] == QueueStatus.EXHAUSTED
    assert updated["retry_count"] == 5

    history = await mock_db["communication_history"].find_one({"queue_item_id": queue_item_id})
    assert history is not None
    assert history["status"] == QueueStatus.EXHAUSTED


async def test_permanent_failure_does_not_retry(mock_db, monkeypatch):
    template = await _seed_template(mock_db, channel=Channel.EMAIL, category=TemplateCategory.WELCOME, body="Hi {{name}}", subject="Welcome")
    await _seed_active_config(mock_db, channel=Channel.EMAIL)
    service = CommunicationService(mock_db)

    item = CommunicationQueueItem(
        channel=Channel.EMAIL, recipient="bad-address", template_id=str(template["_id"]), variables={}, rendered_subject="Welcome", rendered_body="Hi there",
    )
    result = await mock_db["communication_queue"].insert_one(item.model_dump(by_alias=True, exclude={"id"}))
    queue_item_id = str(result.inserted_id)

    async def _fake_fail_permanent(*, recipient, subject, body, config):
        return communication_adapters.DeliveryOutcome(False, None, "invalid recipient address", is_transient=False)

    monkeypatch.setitem(communication_adapters.ADAPTERS, Channel.EMAIL, _fake_fail_permanent)
    await service._send_one(queue_item_id)

    updated = await mock_db["communication_queue"].find_one({"_id": result.inserted_id})
    assert updated["status"] == QueueStatus.FAILED
    assert updated["retry_count"] == 0  # permanent failure is not a retry attempt


async def test_manual_retry_action_and_queue_history_views(client, mock_db, owner_headers, employee_headers, master_data, monkeypatch):
    template = await _seed_template(mock_db, channel=Channel.WHATSAPP, category=TemplateCategory.WELCOME, body="Hi {{name}}")
    await _seed_active_config(mock_db, channel=Channel.WHATSAPP)
    item = CommunicationQueueItem(
        channel=Channel.WHATSAPP, recipient="9111111111", template_id=str(template["_id"]), variables={}, rendered_body="Hi there",
        status=QueueStatus.FAILED, error_detail="boom",
    )
    result = await mock_db["communication_queue"].insert_one(item.model_dump(by_alias=True, exclude={"id"}))
    queue_item_id = str(result.inserted_id)

    r = await client.post(f"/api/v1/communication/queue/{queue_item_id}/retry", headers=employee_headers)
    assert r.status_code == 403, r.text

    employee = await _create_employee(client, owner_headers, master_data, mobile="9900000401", email="retry.staff@example.com")
    await _grant_permission(client, owner_headers, employee["id"], module="communication", resource="queue", actions=["view", "edit"])
    granted_headers = await _login(client, "9900000401", "InitialPass1!")

    async def _fake_send_success(*, recipient, subject, body, config):
        return communication_adapters.DeliveryOutcome(True, "MSGID2", None, is_transient=False)

    monkeypatch.setitem(communication_adapters.ADAPTERS, Channel.WHATSAPP, _fake_send_success)

    r = await client.post(f"/api/v1/communication/queue/{queue_item_id}/retry", headers=granted_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == QueueStatus.SENT

    r = await client.get("/api/v1/communication/queue", headers=granted_headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 1

    await _grant_permission(client, owner_headers, employee["id"], module="communication", resource="history", actions=["view"])
    granted_headers = await _login(client, "9900000401", "InitialPass1!")
    r = await client.get("/api/v1/communication/history", headers=granted_headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 1
    assert r.json()["data"][0]["status"] == QueueStatus.SENT
