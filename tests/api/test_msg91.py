"""Tests for MSG91 as a real, specific Communication Provider (Stage 2 of the Geo
Fencing/Temporary Permissions/MSG91 request): the SMS/WhatsApp adapter branches inside
`communication/adapters.py`, MSG91's Test Connection logic in `integrations/testers.py`,
the SMS delivery-report webhook, and `CommunicationTemplate`'s new provider-template
fields. MSG91 Email is deliberately untested here beyond config/masking — it sends via
the exact same, already-tested generic SMTP path (`send_email`), unchanged.

No real MSG91 account/credentials exist in this environment — every network call is
monkeypatched at `_send_msg91_request` (adapters) or `_test_msg91_authkey` (testers),
matching this codebase's own established pattern (see testers.py's own module docstring).
"""

import json

import pytest

from app.features.communication import adapters as communication_adapters
from app.features.communication.adapters import _normalize_indian_mobile
from app.features.communication.constants import Channel, QueueStatus, TemplateCategory
from app.features.communication.models import CommunicationQueueItem, CommunicationTemplate
from app.features.communication.service import CommunicationService
from app.features.integrations import testers as integrations_testers
from app.features.integrations.models import IntegrationConfig, IntegrationProvider
from app.features.integrations.testers import ConnectionCheckResult
from app.security.encryption import encrypt
from app.utils.datetime import utc_now
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


async def _seed_msg91_provider_catalog(mock_db) -> None:
    rows = [
        IntegrationProvider(integration_type="sms", provider="msg91", label="MSG91 SMS"),
        IntegrationProvider(integration_type="whatsapp", provider="msg91", label="MSG91 WhatsApp"),
        IntegrationProvider(integration_type="email", provider="msg91", label="MSG91 Email (SMTP)"),
    ]
    for row in rows:
        await mock_db["integration_providers"].insert_one(row.model_dump(by_alias=True, exclude={"id"}))


async def _seed_msg91_config(
    mock_db, *, channel: str, is_active: bool = True, extra_config: dict[str, str] | None = None
) -> str:
    config_values = {"auth_key": "test-auth-key", "sender_id": "AFSCRM", "flow_id": "flow123", "integrated_number": "919000000000"}
    config_values.update(extra_config or {})
    config = IntegrationConfig(
        integration_code=f"AFS-INTG-{channel.upper()}", integration_type=channel, provider="msg91", name=f"MSG91 {channel}",
        config_encrypted=encrypt(json.dumps(config_values)), is_enabled=True, is_active=is_active,
    )
    result = await mock_db["integration_configs"].insert_one(config.model_dump(by_alias=True, exclude={"id"}))
    return str(result.inserted_id)


# ---------------------------------------------------------------------- _normalize_indian_mobile


def test_normalize_indian_mobile_adds_country_code():
    assert _normalize_indian_mobile("9876543210") == "919876543210"


def test_normalize_indian_mobile_leaves_already_prefixed_unchanged():
    assert _normalize_indian_mobile("919876543210") == "919876543210"


def test_normalize_indian_mobile_strips_non_digits():
    assert _normalize_indian_mobile("+91 98765-43210") == "919876543210"


# ---------------------------------------------------------------------- send_sms (MSG91 branch)


async def test_send_sms_msg91_missing_credentials_is_permanent_failure():
    outcome = await communication_adapters.send_sms(
        recipient="9876543210", subject=None, body="Hi", config={"_provider": "msg91"}, variables={}, variable_order=[],
    )
    assert outcome.success is False
    assert outcome.is_transient is False
    assert outcome.error == "MSG91 is not configured for this channel."


async def test_send_sms_msg91_success_maps_variables_positionally(monkeypatch):
    captured = {}

    async def _fake_request(url, *, auth_key, json_body):
        captured["url"] = url
        captured["auth_key"] = auth_key
        captured["json_body"] = json_body
        return True, {"type": "success", "message": "req-abc-123"}, 200, 42

    monkeypatch.setattr(communication_adapters, "_send_msg91_request", _fake_request)

    outcome = await communication_adapters.send_sms(
        recipient="9876543210", subject=None, body="ignored for msg91",
        config={"_provider": "msg91", "auth_key": "key1", "flow_id": "flow1", "sender_id": "AFSCRM"},
        variables={"customer_name": "Ravi", "lead_code": "LEAD1"}, variable_order=["customer_name", "lead_code"],
    )
    assert outcome.success is True
    assert outcome.provider_message_id == "req-abc-123"
    assert outcome.is_transient is False
    assert captured["url"] == communication_adapters.MSG91_SMS_FLOW_URL
    assert captured["json_body"]["flow_id"] == "flow1"
    assert captured["json_body"]["sender"] == "AFSCRM"
    recipient_entry = captured["json_body"]["recipients"][0]
    assert recipient_entry["mobiles"] == "919876543210"
    assert recipient_entry["VAR1"] == "Ravi"
    assert recipient_entry["VAR2"] == "LEAD1"


@pytest.mark.parametrize(
    ("status_code", "message", "expected_error", "expected_transient"),
    [
        (401, "invalid authkey", "Unable to authenticate with the communication provider.", False),
        (429, "rate limit exceeded", "Provider rate limit reached. Message will be retried.", True),
        (500, "internal error", "MSG91 is temporarily unavailable. Message will be retried.", True),
        (400, "invalid mobile number", "Invalid recipient.", False),
        (400, "flow id missing", "Message template is invalid or not approved.", False),
    ],
)
async def test_send_sms_msg91_error_classification(monkeypatch, status_code, message, expected_error, expected_transient):
    async def _fake_request(url, *, auth_key, json_body):
        return status_code < 400, {"type": "error", "message": message}, status_code, 10

    monkeypatch.setattr(communication_adapters, "_send_msg91_request", _fake_request)

    outcome = await communication_adapters.send_sms(
        recipient="9876543210", subject=None, body="x", config={"_provider": "msg91", "auth_key": "key1", "flow_id": "flow1"},
        variables={}, variable_order=[],
    )
    assert outcome.success is False
    assert outcome.error == expected_error
    assert outcome.is_transient is expected_transient


async def test_send_sms_non_msg91_provider_uses_generic_path_unchanged(monkeypatch):
    """Regression guard — a config with no `_provider` (or a non-msg91 one) must never
    hit the MSG91 branch; the pre-existing generic HTTP POST adapter stays the fallback."""
    called = {}

    async def _fake_timed_post(url, **kwargs):
        called["url"] = url
        return True, None, 5

    monkeypatch.setattr(communication_adapters, "_timed_post", _fake_timed_post)
    outcome = await communication_adapters.send_sms(
        recipient="9876543210", subject=None, body="hello", config={"api_url": "https://example.test/sms", "api_key": "k"},
    )
    assert outcome.success is True
    assert called["url"] == "https://example.test/sms"


# ---------------------------------------------------------------------- send_whatsapp (MSG91 branch)


async def test_send_whatsapp_msg91_missing_provider_template_fails_cleanly():
    outcome = await communication_adapters.send_whatsapp(
        recipient="9876543210", subject=None, body="hi", config={"_provider": "msg91", "auth_key": "k", "integrated_number": "919000000000"},
        variables={}, variable_order=[], provider_template_meta=None,
    )
    assert outcome.success is False
    assert outcome.is_transient is False
    assert outcome.error == "Message template is invalid or not approved."


async def test_send_whatsapp_msg91_success_builds_template_payload(monkeypatch):
    captured = {}

    async def _fake_request(url, *, auth_key, json_body):
        captured["url"] = url
        captured["json_body"] = json_body
        return True, {"type": "success", "message": "wa-req-1"}, 200, 30

    monkeypatch.setattr(communication_adapters, "_send_msg91_request", _fake_request)

    outcome = await communication_adapters.send_whatsapp(
        recipient="9876543210", subject=None, body="ignored",
        config={"_provider": "msg91", "auth_key": "key1", "integrated_number": "919000000000"},
        variables={"customer_name": "Ravi"}, variable_order=["customer_name"],
        provider_template_meta={"name": "loan_update", "namespace": "ns123", "language": "en"},
    )
    assert outcome.success is True
    assert outcome.provider_message_id == "wa-req-1"
    assert captured["url"] == communication_adapters.MSG91_WHATSAPP_URL
    payload = captured["json_body"]["payload"]
    assert payload["template"]["name"] == "loan_update"
    assert payload["template"]["namespace"] == "ns123"
    assert payload["template"]["to_and_components"][0]["to"] == ["919876543210"]
    assert payload["template"]["to_and_components"][0]["components"]["body_1"] == {"type": "text", "value": "Ravi"}


# ---------------------------------------------------------------------- integrations/testers.py — MSG91 Test Connection


async def test_msg91_sms_tester_missing_auth_key():
    result = await integrations_testers.test_sms({"provider": "msg91", "flow_id": "flow1"})
    assert result.success is False
    assert "auth_key" in (result.error_message or "")


async def test_msg91_sms_tester_missing_flow_id():
    result = await integrations_testers.test_sms({"provider": "msg91", "auth_key": "key1"})
    assert result.success is False
    assert "flow_id" in (result.error_message or "")


async def test_msg91_sms_tester_success(monkeypatch):
    async def _fake_authkey_check(auth_key: str) -> ConnectionCheckResult:
        assert auth_key == "key1"
        return ConnectionCheckResult(True, 15, None)

    monkeypatch.setattr(integrations_testers, "_test_msg91_authkey", _fake_authkey_check)
    result = await integrations_testers.test_sms({"provider": "msg91", "auth_key": "key1", "flow_id": "flow1"})
    assert result.success is True


async def test_msg91_whatsapp_tester_missing_integrated_number():
    result = await integrations_testers.test_whatsapp({"provider": "msg91", "auth_key": "key1"})
    assert result.success is False
    assert "integrated_number" in (result.error_message or "")


async def test_non_msg91_sms_provider_unaffected_by_msg91_branch(monkeypatch):
    """Regression guard — a config with provider != msg91 must still use the pre-existing
    generic reachability check."""
    called = {}

    async def _fake_timed_get(url, **kwargs):
        called["url"] = url
        return ConnectionCheckResult(True, 5, None)

    monkeypatch.setattr(integrations_testers, "_timed_get", _fake_timed_get)
    result = await integrations_testers.test_sms({"provider": "generic_sms", "api_url": "https://example.test/sms"})
    assert result.success is True
    assert called["url"] == "https://example.test/sms"


# ---------------------------------------------------------------------- MSG91 SMS delivery webhook


async def _seed_queue_item(mock_db, *, status: str, provider_message_id: str | None, channel: str = Channel.SMS) -> str:
    template = CommunicationTemplate(name="t", channel=channel, category=TemplateCategory.LEAD_ASSIGNED, body="Hi {{name}}", variables=["name"])
    template_result = await mock_db["communication_templates"].insert_one(template.model_dump(by_alias=True, exclude={"id"}))
    item = CommunicationQueueItem(
        channel=channel, recipient="9876543210", template_id=str(template_result.inserted_id), variables={"name": "Ravi"},
        rendered_body="Hi Ravi", status=status, provider_message_id=provider_message_id, sent_at=utc_now() if status != "pending" else None,
    )
    result = await mock_db["communication_queue"].insert_one(item.model_dump(by_alias=True, exclude={"id"}))
    return str(result.inserted_id)


async def test_msg91_webhook_rejects_missing_secret(client):
    r = await client.post("/api/v1/communication/webhooks/msg91", json={"requestId": "abc", "status": 1})
    assert r.status_code == 403


async def test_msg91_webhook_rejects_wrong_secret(client, mock_db):
    await _seed_msg91_config(mock_db, channel=Channel.SMS, extra_config={"webhook_secret": "correct-secret"})
    r = await client.post("/api/v1/communication/webhooks/msg91?secret=wrong-secret", json={"requestId": "abc", "status": 1})
    assert r.status_code == 403


async def test_msg91_webhook_rejects_malformed_body(client, mock_db):
    await _seed_msg91_config(mock_db, channel=Channel.SMS, extra_config={"webhook_secret": "s3cr3t"})
    r = await client.post("/api/v1/communication/webhooks/msg91?secret=s3cr3t", content=b"not json")
    assert r.status_code == 400


async def test_msg91_webhook_rejects_missing_required_fields(client, mock_db):
    await _seed_msg91_config(mock_db, channel=Channel.SMS, extra_config={"webhook_secret": "s3cr3t"})
    r = await client.post("/api/v1/communication/webhooks/msg91?secret=s3cr3t", json={"telNum": "9876543210"})
    assert r.status_code == 400


async def test_msg91_webhook_unknown_message_id_is_safely_ignored(client, mock_db):
    await _seed_msg91_config(mock_db, channel=Channel.SMS, extra_config={"webhook_secret": "s3cr3t"})
    r = await client.post("/api/v1/communication/webhooks/msg91?secret=s3cr3t", json={"requestId": "does-not-exist", "status": 1})
    assert r.status_code == 200


async def test_msg91_webhook_marks_delivered(client, mock_db):
    await _seed_msg91_config(mock_db, channel=Channel.SMS, extra_config={"webhook_secret": "s3cr3t"})
    queue_item_id = await _seed_queue_item(mock_db, status=QueueStatus.SENT, provider_message_id="req-xyz")

    r = await client.post("/api/v1/communication/webhooks/msg91?secret=s3cr3t", json={"requestId": "req-xyz", "status": 1, "telNum": "9876543210"})
    assert r.status_code == 200

    updated = await mock_db["communication_queue"].find_one({"_id": to_object_id(queue_item_id)})
    assert updated["status"] == QueueStatus.DELIVERED
    assert updated["delivered_at"] is not None

    history = await mock_db["communication_history"].find_one({"queue_item_id": queue_item_id})
    assert history is not None
    assert history["status"] == QueueStatus.DELIVERED
    assert history["delivered_at"] is not None


async def test_msg91_webhook_marks_failed(client, mock_db):
    await _seed_msg91_config(mock_db, channel=Channel.SMS, extra_config={"webhook_secret": "s3cr3t"})
    queue_item_id = await _seed_queue_item(mock_db, status=QueueStatus.SENT, provider_message_id="req-fail-1")

    r = await client.post("/api/v1/communication/webhooks/msg91?secret=s3cr3t", json={"requestId": "req-fail-1", "status": 2})
    assert r.status_code == 200

    updated = await mock_db["communication_queue"].find_one({"_id": to_object_id(queue_item_id)})
    assert updated["status"] == QueueStatus.FAILED
    assert updated["error_detail"]


async def test_msg91_webhook_duplicate_callback_is_idempotent(client, mock_db):
    await _seed_msg91_config(mock_db, channel=Channel.SMS, extra_config={"webhook_secret": "s3cr3t"})
    queue_item_id = await _seed_queue_item(mock_db, status=QueueStatus.SENT, provider_message_id="req-dup-1")

    r1 = await client.post("/api/v1/communication/webhooks/msg91?secret=s3cr3t", json={"requestId": "req-dup-1", "status": 1})
    assert r1.status_code == 200
    r2 = await client.post("/api/v1/communication/webhooks/msg91?secret=s3cr3t", json={"requestId": "req-dup-1", "status": 1})
    assert r2.status_code == 200

    updated = await mock_db["communication_queue"].find_one({"_id": to_object_id(queue_item_id)})
    assert updated["status"] == QueueStatus.DELIVERED
    # Never regressed/duplicated — exactly one history row for this queue item.
    history_count = await mock_db["communication_history"].count_documents({"queue_item_id": queue_item_id})
    assert history_count == 1


async def test_msg91_webhook_unrecognized_status_is_no_op(client, mock_db):
    await _seed_msg91_config(mock_db, channel=Channel.SMS, extra_config={"webhook_secret": "s3cr3t"})
    queue_item_id = await _seed_queue_item(mock_db, status=QueueStatus.SENT, provider_message_id="req-unknown-status")

    r = await client.post("/api/v1/communication/webhooks/msg91?secret=s3cr3t", json={"requestId": "req-unknown-status", "status": 999})
    assert r.status_code == 200

    updated = await mock_db["communication_queue"].find_one({"_id": to_object_id(queue_item_id)})
    assert updated["status"] == QueueStatus.SENT  # unchanged — 999 isn't a recognized delivered/failed code


async def test_process_delivery_webhook_service_method_directly(mock_db):
    """Direct service-level test (no HTTP/secret layer) for the state-machine rules:
    never regress from a terminal state, never advance a non-`sent` item."""
    service = CommunicationService(mock_db)
    await _seed_queue_item(mock_db, status=QueueStatus.PENDING, provider_message_id="req-pending-1")

    outcome = await service.process_delivery_webhook(provider="msg91", provider_message_id="req-pending-1", delivered=True, failed=False, error=None)
    assert outcome == "unexpected_state"

    outcome_unknown = await service.process_delivery_webhook(provider="msg91", provider_message_id="does-not-exist", delivered=True, failed=False, error=None)
    assert outcome_unknown == "unknown_message_id"


# ---------------------------------------------------------------------- CommunicationTemplate provider fields


async def test_create_whatsapp_template_with_provider_fields(client, owner_headers, mock_db, master_data):
    employee = await _create_employee(client, owner_headers, master_data, mobile="9900000501", email="msg91.staff@example.com")
    await _grant_permission(client, owner_headers, employee["id"], module="communication", resource="templates", actions=["view", "create", "edit"])
    headers = await _login(client, "9900000501", "InitialPass1!")

    r = await client.post(
        "/api/v1/communication/templates",
        json={
            "name": "MSG91 WA Template", "channel": "whatsapp", "category": "welcome", "body": "Hi {{customer_name}}",
            "provider_template_name": "welcome_msg", "provider_template_namespace": "ns_abc", "provider_template_language": "en",
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["provider_template_name"] == "welcome_msg"
    assert data["provider_template_namespace"] == "ns_abc"
    assert data["provider_template_language"] == "en"

    r = await client.patch(f"/api/v1/communication/templates/{data['id']}", json={"provider_template_name": "welcome_msg_v2"}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["provider_template_name"] == "welcome_msg_v2"


# ---------------------------------------------------------------------- Communication Providers config CRUD (reuses Module 9A)


async def test_create_msg91_config_via_integrations_api_masks_secrets(client, owner_headers, mock_db):
    await _seed_msg91_provider_catalog(mock_db)
    r = await client.post(
        "/api/v1/integration-configs",
        json={
            "integration_type": "sms", "provider": "msg91", "name": "MSG91 SMS Production",
            "config": {"auth_key": "super-secret-key", "sender_id": "AFSCRM", "flow_id": "flow123", "webhook_secret": "whsecret1"},
        },
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["config"]["auth_key"] != "super-secret-key"  # masked — never returned in full
    assert data["config"]["sender_id"] == "AFSCRM"  # non-secret field returned as-is
    assert "super-secret-key" not in r.text  # not leaked anywhere in the raw response body