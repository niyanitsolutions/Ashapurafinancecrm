"""Tests for the MSG91 Communication Providers configuration UI hardening: the new
sectioned Owner-facing field set (Credentials / Channel Configuration / Delivery &
Webhook Configuration), the `dlt_entity_id` -> `dlt_template_id` rename, the config-level
WhatsApp template default/fallback used by `_send_one`, and a confirmed pre-existing bug
fix (the draft Test Connection call never told the tester which provider it was testing,
so MSG91 credentials always fell through to the generic api_url-required check and failed
Test Connection even when valid). All of this still runs on Module 9A's existing encrypted
IntegrationConfig storage/API — no new credential store, no schema change.
"""

import json

from app.features.communication import adapters as communication_adapters
from app.features.communication.constants import Channel, TemplateCategory
from app.features.communication.models import CommunicationQueueItem, CommunicationTemplate
from app.features.communication.service import CommunicationService
from app.features.communication.template_engine import extract_variable_names
from app.features.integrations import testers as integrations_testers
from app.features.integrations.models import IntegrationConfig, IntegrationProvider
from app.features.integrations.testers import ConnectionCheckResult
from app.security.encryption import decrypt, encrypt
from app.utils.helpers import to_object_id


async def _seed_msg91_providers(mock_db):
    rows = [
        IntegrationProvider(integration_type="sms", provider="msg91", label="MSG91 SMS"),
        IntegrationProvider(integration_type="whatsapp", provider="msg91", label="MSG91 WhatsApp"),
        IntegrationProvider(integration_type="email", provider="msg91", label="MSG91 Email (SMTP)"),
    ]
    for row in rows:
        await mock_db["integration_providers"].insert_one(row.model_dump(by_alias=True, exclude={"id"}))


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


# ---------------------------------------------------------------------- field set / masking


async def test_create_msg91_sms_config_masks_secrets_only(client, mock_db, owner_headers):
    await _seed_msg91_providers(mock_db)
    r = await client.post(
        "/api/v1/integration-configs",
        json={
            "integration_type": "sms", "provider": "msg91", "name": "MSG91 SMS",
            "config": {
                "auth_key": "authkey1234567", "sender_id": "AFSFIN", "flow_id": "flow-abc-123",
                "dlt_template_id": "1234567890123456789", "webhook_secret": "whsecret123456",
            },
        },
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    config = r.json()["data"]["config"]
    # Secrets masked to "****last4" only.
    assert config["auth_key"] != "authkey1234567"
    assert config["auth_key"].endswith("4567")
    assert "*" in config["auth_key"]
    assert config["webhook_secret"] != "whsecret123456"
    assert config["webhook_secret"].endswith("3456")
    # Non-secret channel-configuration fields shown in full — nothing sensitive here.
    assert config["sender_id"] == "AFSFIN"
    assert config["flow_id"] == "flow-abc-123"
    assert config["dlt_template_id"] == "1234567890123456789"


async def test_create_msg91_whatsapp_config_new_template_fields_not_masked(client, mock_db, owner_headers):
    await _seed_msg91_providers(mock_db)
    r = await client.post(
        "/api/v1/integration-configs",
        json={
            "integration_type": "whatsapp", "provider": "msg91", "name": "MSG91 WhatsApp",
            "config": {
                "auth_key": "authkey1234567", "integrated_number": "919876543210",
                "whatsapp_template_name": "order_update", "whatsapp_template_language": "en",
                "whatsapp_template_namespace": "ns-123", "webhook_secret": "whsecret123456",
            },
        },
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    config = r.json()["data"]["config"]
    assert config["auth_key"].endswith("4567") and "*" in config["auth_key"]
    assert config["integrated_number"] == "919876543210"
    assert config["whatsapp_template_name"] == "order_update"
    assert config["whatsapp_template_language"] == "en"
    assert config["whatsapp_template_namespace"] == "ns-123"


# ---------------------------------------------------------------------- edit: preserve vs. replace secret


async def test_edit_msg91_config_without_changing_secret_preserves_it(client, mock_db, owner_headers):
    await _seed_msg91_providers(mock_db)
    r = await client.post(
        "/api/v1/integration-configs",
        json={
            "integration_type": "sms", "provider": "msg91", "name": "MSG91 SMS",
            "config": {"auth_key": "originalauthkey", "sender_id": "AFSFIN", "flow_id": "flow-1"},
        },
        headers=owner_headers,
    )
    config_id = r.json()["data"]["id"]
    masked_auth_key = r.json()["data"]["config"]["auth_key"]

    # Simulates the Msg91ConfigForm edit flow: unrelated field changed, secret field
    # resubmitted exactly as loaded (still its masked value) because the Owner didn't touch it.
    r = await client.patch(
        f"/api/v1/integration-configs/{config_id}",
        json={"config": {"sender_id": "AFSNEW", "auth_key": masked_auth_key}},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["config"]["sender_id"] == "AFSNEW"

    raw = await mock_db["integration_configs"].find_one({"_id": to_object_id(config_id)})
    stored = json.loads(decrypt(raw["config_encrypted"]))
    assert stored["auth_key"] == "originalauthkey"  # untouched, not overwritten with the mask string


async def test_edit_msg91_config_with_new_secret_value_replaces_it(client, mock_db, owner_headers):
    await _seed_msg91_providers(mock_db)
    r = await client.post(
        "/api/v1/integration-configs",
        json={"integration_type": "sms", "provider": "msg91", "name": "MSG91 SMS", "config": {"auth_key": "originalauthkey", "sender_id": "AFSFIN", "flow_id": "flow-1"}},
        headers=owner_headers,
    )
    config_id = r.json()["data"]["id"]

    r = await client.patch(f"/api/v1/integration-configs/{config_id}", json={"config": {"auth_key": "brandnewauthkey"}}, headers=owner_headers)
    assert r.status_code == 200, r.text

    raw = await mock_db["integration_configs"].find_one({"_id": to_object_id(config_id)})
    stored = json.loads(decrypt(raw["config_encrypted"]))
    assert stored["auth_key"] == "brandnewauthkey"
    # A genuine credential change must force re-verification (existing Module 9A rule).
    assert raw["is_active"] is False
    assert raw["last_success_at"] is None


# ---------------------------------------------------------------------- authorization / IDOR


async def test_employee_without_permission_cannot_create_or_edit_msg91_config(client, mock_db, owner_headers, master_data):
    await _seed_msg91_providers(mock_db)
    employee = await _create_employee(client, owner_headers, master_data, mobile="9900000401", email="no.perm@example.com")
    headers = await _login(client, "9900000401", "InitialPass1!")

    r = await client.post(
        "/api/v1/integration-configs",
        json={"integration_type": "sms", "provider": "msg91", "name": "MSG91 SMS", "config": {"auth_key": "k", "sender_id": "S", "flow_id": "f"}},
        headers=headers,
    )
    assert r.status_code == 403, r.text

    r = await client.post(
        "/api/v1/integration-configs",
        json={"integration_type": "sms", "provider": "msg91", "name": "MSG91 SMS", "config": {"auth_key": "k", "sender_id": "S", "flow_id": "f"}},
        headers=owner_headers,
    )
    config_id = r.json()["data"]["id"]

    r = await client.patch(f"/api/v1/integration-configs/{config_id}", json={"config": {"sender_id": "X"}}, headers=headers)
    assert r.status_code == 403, r.text


async def test_edit_forged_config_id_returns_not_found(client, mock_db, owner_headers):
    await _seed_msg91_providers(mock_db)
    r = await client.patch("/api/v1/integration-configs/000000000000000000000000", json={"config": {"sender_id": "X"}}, headers=owner_headers)
    assert r.status_code == 404, r.text


async def test_msg91_secret_never_returned_in_full_anywhere(client, mock_db, owner_headers):
    await _seed_msg91_providers(mock_db)
    r = await client.post(
        "/api/v1/integration-configs",
        json={
            "integration_type": "whatsapp", "provider": "msg91", "name": "MSG91 WhatsApp",
            "config": {"auth_key": "verysecretauthkeyvalue", "integrated_number": "919876543210", "webhook_secret": "verysecretwebhookvalue"},
        },
        headers=owner_headers,
    )
    config_id = r.json()["data"]["id"]

    r_get = await client.get(f"/api/v1/integration-configs/{config_id}", headers=owner_headers)
    r_list = await client.get("/api/v1/integration-configs?integration_type=whatsapp", headers=owner_headers)
    for body in (r.json(), r_get.json(), r_list.json()):
        payload_text = json.dumps(body)
        assert "verysecretauthkeyvalue" not in payload_text
        assert "verysecretwebhookvalue" not in payload_text


# ---------------------------------------------------------------------- test-draft provider dispatch (bug fix)


async def test_draft_test_without_provider_falls_back_to_generic_and_fails_for_msg91_shaped_config(client, mock_db, owner_headers):
    """Reproduces the confirmed pre-existing bug: the old generic wizard's draft Test
    Connection never sent `provider`, so a valid MSG91 SMS config (auth_key + flow_id,
    no api_url) always failed with 'Missing required field: api_url' — even though the
    credentials were correct. This is the exact "screen is NOT production-ready" defect."""
    r = await client.post(
        "/api/v1/integration-configs/test-draft",
        json={"integration_type": "sms", "config": {"auth_key": "authkey123", "flow_id": "flow-1", "sender_id": "AFSFIN"}},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    result = r.json()["data"]
    assert result["success"] is False
    assert "api_url" in (result["error_message"] or "")


async def test_draft_test_with_msg91_provider_dispatches_to_msg91_tester(client, mock_db, owner_headers, monkeypatch):
    """The fix: Msg91ConfigForm now sends `provider: "msg91"` on every draft Test
    Connection call, so the real MSG91-specific auth-key check runs instead of the
    generic api_url check."""
    called_with = {}

    async def _fake_authkey_check(auth_key):
        called_with["auth_key"] = auth_key
        return ConnectionCheckResult(success=True, response_time_ms=7, error_message=None)

    monkeypatch.setattr(integrations_testers, "_test_msg91_authkey", _fake_authkey_check)

    r = await client.post(
        "/api/v1/integration-configs/test-draft",
        json={"integration_type": "sms", "provider": "msg91", "config": {"auth_key": "authkey123", "flow_id": "flow-1", "sender_id": "AFSFIN"}},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["success"] is True
    assert called_with["auth_key"] == "authkey123"


async def test_draft_test_msg91_whatsapp_requires_integrated_number(client, mock_db, owner_headers, monkeypatch):
    async def _fake_authkey_check(auth_key):
        return ConnectionCheckResult(success=True, response_time_ms=1, error_message=None)

    monkeypatch.setattr(integrations_testers, "_test_msg91_authkey", _fake_authkey_check)

    r = await client.post(
        "/api/v1/integration-configs/test-draft",
        json={"integration_type": "whatsapp", "provider": "msg91", "config": {"auth_key": "authkey123"}},  # no integrated_number
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    result = r.json()["data"]
    assert result["success"] is False
    assert "integrated_number" in (result["error_message"] or "")


# ---------------------------------------------------------------------- WhatsApp config-level template fallback


async def _seed_active_msg91_config(mock_db, *, channel: str, extra: dict) -> None:
    config = IntegrationConfig(
        integration_code=f"AFS-INTG-{channel.upper()}-MSG91", integration_type=channel, provider="msg91", name=f"MSG91 {channel}",
        config_encrypted=encrypt(json.dumps({"auth_key": "k", **extra})), is_enabled=True, is_active=True,
    )
    await mock_db["integration_configs"].insert_one(config.model_dump(by_alias=True, exclude={"id"}))


async def _seed_template(mock_db, *, channel: str, category: str, body: str = "Hello {{name}}", **template_kwargs) -> dict:
    template = CommunicationTemplate(
        name=f"{category}-{channel}", channel=channel, category=category, body=body, variables=extract_variable_names(body), **template_kwargs
    )
    result = await mock_db["communication_templates"].insert_one(template.model_dump(by_alias=True, exclude={"id"}))
    return await mock_db["communication_templates"].find_one({"_id": result.inserted_id})


async def test_send_falls_back_to_config_level_whatsapp_template_when_template_has_none(mock_db, monkeypatch):
    await _seed_template(mock_db, channel=Channel.WHATSAPP, category=TemplateCategory.WELCOME, body="Hi {{name}}")
    await _seed_active_msg91_config(
        mock_db, channel=Channel.WHATSAPP,
        extra={"integrated_number": "919876543210", "whatsapp_template_name": "default_welcome", "whatsapp_template_namespace": "ns-1", "whatsapp_template_language": "en"},
    )

    captured = {}

    async def _fake_send(*, recipient, subject, body, config, provider_template_meta, **_kwargs):
        captured["meta"] = provider_template_meta
        return communication_adapters.DeliveryOutcome(True, "MSGID1", None, is_transient=False)

    monkeypatch.setitem(communication_adapters.ADAPTERS, Channel.WHATSAPP, _fake_send)

    service = CommunicationService(mock_db)
    template_doc = await mock_db["communication_templates"].find_one({})
    queue_id = await service._queue.insert(
        CommunicationQueueItem(
            channel=Channel.WHATSAPP, recipient="9876540001", template_id=str(template_doc["_id"]),
            rendered_body="Hi Jane", rendered_subject=None, variables={"name": "Jane"}, business_event="manual", entity_type=None, entity_id=None,
        )
    )
    await service._send_one(queue_id)

    assert captured["meta"] == {"name": "default_welcome", "namespace": "ns-1", "language": "en"}


async def test_send_prefers_template_own_provider_template_over_config_default(mock_db, monkeypatch):
    template_doc = await _seed_template(
        mock_db, channel=Channel.WHATSAPP, category=TemplateCategory.WELCOME, body="Hi {{name}}",
        provider_template_name="specific_template", provider_template_namespace="ns-specific", provider_template_language="hi",
    )
    await _seed_active_msg91_config(
        mock_db, channel=Channel.WHATSAPP,
        extra={"integrated_number": "919876543210", "whatsapp_template_name": "default_welcome", "whatsapp_template_namespace": "ns-1", "whatsapp_template_language": "en"},
    )

    captured = {}

    async def _fake_send(*, recipient, subject, body, config, provider_template_meta, **_kwargs):
        captured["meta"] = provider_template_meta
        return communication_adapters.DeliveryOutcome(True, "MSGID1", None, is_transient=False)

    monkeypatch.setitem(communication_adapters.ADAPTERS, Channel.WHATSAPP, _fake_send)

    service = CommunicationService(mock_db)
    from app.features.communication.models import CommunicationQueueItem

    queue_id = await service._queue.insert(
        CommunicationQueueItem(
            channel=Channel.WHATSAPP, recipient="9876540001", template_id=str(template_doc["_id"]),
            rendered_body="Hi Jane", rendered_subject=None, variables={"name": "Jane"}, business_event="manual", entity_type=None, entity_id=None,
        )
    )
    await service._send_one(queue_id)

    assert captured["meta"] == {"name": "specific_template", "namespace": "ns-specific", "language": "hi"}
