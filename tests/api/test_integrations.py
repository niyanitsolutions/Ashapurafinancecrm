"""End-to-end tests for Module 9A (API Management): the integration config platform
only — encryption, masking, Enable/Disable, Activate (one active per integration_type),
Test Connection (network calls monkeypatched, never hitting a real provider), and
Access Control permission gating. No business action (send/fetch) exists in this module
to test, by design.
"""

import json
from urllib.parse import parse_qs, urlparse

from app.features.integrations import meta_status as meta_status_client
from app.features.integrations import oauth as oauth_client
from app.features.integrations import service as integrations_service
from app.features.integrations import testers as integrations_testers
from app.features.integrations.models import IntegrationProvider
from app.features.integrations.testers import ConnectionCheckResult
from app.security.encryption import decrypt
from app.utils.datetime import utc_now
from app.utils.helpers import to_object_id


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
        "mobile": mobile, "initial_password": "InitialPass1", "first_name": "Staff", "last_name": "Member", "email": email,
        "department_id": master_data["department_id"], "designation_id": master_data["designation_id"], "branch_id": master_data["branch_id"],
        "joining_date": "2026-01-15", "employment_type": "full_time",
    }
    r = await client.post("/api/v1/employees", json=payload, headers=owner_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _seed_providers(mock_db):
    rows = [
        IntegrationProvider(integration_type="meta", provider="meta", label="Meta (Facebook/Instagram)"),
        IntegrationProvider(integration_type="whatsapp", provider="whatsapp_business_api", label="WhatsApp Business API"),
        IntegrationProvider(integration_type="sms", provider="generic_sms", label="Generic SMS Provider"),
        IntegrationProvider(integration_type="email", provider="smtp", label="SMTP"),
        IntegrationProvider(integration_type="maps", provider="google_maps", label="Google Maps"),
    ]
    for row in rows:
        await mock_db["integration_providers"].insert_one(row.model_dump(by_alias=True, exclude={"id"}))


async def test_permission_gating_and_provider_catalog(client, mock_db, owner_headers, employee_headers, master_data):
    await _seed_providers(mock_db)

    r = await client.get("/api/v1/integration-providers", headers=employee_headers)
    assert r.status_code == 403, r.text

    employee = await _create_employee(client, owner_headers, master_data, mobile="9900000101", email="integrations.viewer@example.com")
    await _grant_permission(client, owner_headers, employee["id"], module="integrations", resource="configs", actions=["view", "create", "edit"])
    granted_headers = await _login(client, "9900000101", "InitialPass1")

    r = await client.get("/api/v1/integration-providers", headers=granted_headers)
    assert r.status_code == 200, r.text
    providers = {p["provider"] for p in r.json()["data"]}
    assert {"meta", "whatsapp_business_api", "generic_sms", "smtp", "google_maps"} <= providers


async def test_create_config_encrypts_and_masks_secrets(client, mock_db, owner_headers):
    await _seed_providers(mock_db)

    r = await client.post(
        "/api/v1/integration-configs",
        json={
            "integration_type": "meta", "provider": "meta", "name": "Meta Production",
            "config": {"app_id": "1234567890", "app_secret": "supersecretvalue", "access_token": "EAABtoken12345"},
        },
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    config = r.json()["data"]
    assert config["integration_code"].startswith("AFS-INTG-")
    assert config["config"]["app_id"] == "1234567890"  # not secret-looking — shown in full
    assert config["config"]["app_secret"] != "supersecretvalue"
    assert config["config"]["app_secret"].endswith("alue")  # last 4 chars visible
    assert config["config"]["access_token"].endswith("2345")
    assert "*" in config["config"]["app_secret"]
    assert config["is_enabled"] is False
    assert config["is_active"] is False

    raw = await mock_db["integration_configs"].find_one({"integration_code": config["integration_code"]})
    stored_config = json.loads(decrypt(raw["config_encrypted"]))
    assert stored_config["app_secret"] == "supersecretvalue"  # stored plaintext never equals the ciphertext blob
    assert raw["config_encrypted"] != json.dumps(stored_config)  # genuinely encrypted, not stored as plain JSON


async def test_create_config_rejects_unknown_provider(client, mock_db, owner_headers):
    await _seed_providers(mock_db)
    r = await client.post(
        "/api/v1/integration-configs", json={"integration_type": "sms", "provider": "not_a_real_provider", "name": "X", "config": {}}, headers=owner_headers
    )
    assert r.status_code == 422, r.text


async def test_update_merges_config_without_exposing_old_secrets(client, mock_db, owner_headers):
    await _seed_providers(mock_db)
    r = await client.post(
        "/api/v1/integration-configs",
        json={"integration_type": "sms", "provider": "generic_sms", "name": "SMS Prod", "config": {"api_url": "https://sms.example.com", "api_key": "originalkey1"}},
        headers=owner_headers,
    )
    config_id = r.json()["data"]["id"]

    r = await client.patch(f"/api/v1/integration-configs/{config_id}", json={"config": {"sender_id": "AFSCRM"}}, headers=owner_headers)
    assert r.status_code == 200, r.text
    updated = r.json()["data"]
    assert updated["config"]["sender_id"] == "AFSCRM"
    assert updated["config"]["api_key"].endswith("key1")  # untouched original secret still present, still masked


async def test_enable_disable_and_activate_lifecycle(client, mock_db, owner_headers, monkeypatch):
    await _seed_providers(mock_db)

    async def _fake_success(_config):
        return ConnectionCheckResult(success=True, response_time_ms=1, error_message=None)

    monkeypatch.setitem(integrations_service.TESTERS, "whatsapp", _fake_success)

    async def _create(name):
        r = await client.post(
            "/api/v1/integration-configs",
            json={"integration_type": "whatsapp", "provider": "whatsapp_business_api", "name": name, "config": {"api_url": "https://wa.example.com", "access_token": "tok1"}},
            headers=owner_headers,
        )
        assert r.status_code == 200, r.text
        return r.json()["data"]["id"]

    config_a = await _create("WhatsApp Production")
    config_b = await _create("WhatsApp Test")

    r = await client.post(f"/api/v1/integration-configs/{config_a}/activate", json={}, headers=owner_headers)
    assert r.status_code == 422, r.text  # not enabled yet

    r = await client.patch(f"/api/v1/integration-configs/{config_a}/enable", json={}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["is_enabled"] is True

    r = await client.post(f"/api/v1/integration-configs/{config_a}/activate", json={}, headers=owner_headers)
    assert r.status_code == 422, r.text  # enabled, but never successfully tested yet

    r = await client.post(f"/api/v1/integration-configs/{config_a}/test", json={}, headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.post(f"/api/v1/integration-configs/{config_a}/activate", json={}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["is_active"] is True

    await client.patch(f"/api/v1/integration-configs/{config_b}/enable", json={}, headers=owner_headers)
    await client.post(f"/api/v1/integration-configs/{config_b}/test", json={}, headers=owner_headers)
    r = await client.post(f"/api/v1/integration-configs/{config_b}/activate", json={}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["is_active"] is True

    r = await client.get(f"/api/v1/integration-configs/{config_a}", headers=owner_headers)
    assert r.json()["data"]["is_active"] is False  # deactivated when config_b became active

    r = await client.patch(f"/api/v1/integration-configs/{config_b}/disable", json={}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["is_enabled"] is False
    assert r.json()["data"]["is_active"] is False  # disabling clears active too


async def test_connection_success_and_failure_recorded(client, mock_db, owner_headers, monkeypatch):
    await _seed_providers(mock_db)
    r = await client.post(
        "/api/v1/integration-configs",
        json={"integration_type": "meta", "provider": "meta", "name": "Meta Test", "config": {"app_id": "1", "app_secret": "s", "access_token": "t"}},
        headers=owner_headers,
    )
    config_id = r.json()["data"]["id"]

    async def _fake_success(_config):
        return ConnectionCheckResult(success=True, response_time_ms=42, error_message=None)

    monkeypatch.setitem(integrations_service.TESTERS, "meta", _fake_success)
    r = await client.post(f"/api/v1/integration-configs/{config_id}/test", json={}, headers=owner_headers)
    assert r.status_code == 200, r.text
    result = r.json()["data"]
    assert result["success"] is True
    assert result["response_time_ms"] == 42

    r = await client.get(f"/api/v1/integration-configs/{config_id}", headers=owner_headers)
    detail = r.json()["data"]
    assert detail["last_success_at"] is not None
    assert detail["last_failure_at"] is None
    assert detail["last_error_message"] is None

    async def _fake_failure(_config):
        return ConnectionCheckResult(success=False, response_time_ms=15, error_message="HTTP 401: invalid token")

    monkeypatch.setitem(integrations_service.TESTERS, "meta", _fake_failure)
    r = await client.post(f"/api/v1/integration-configs/{config_id}/test", json={}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["success"] is False

    r = await client.get(f"/api/v1/integration-configs/{config_id}", headers=owner_headers)
    detail = r.json()["data"]
    assert detail["last_failure_at"] is not None
    assert detail["last_error_message"] == "HTTP 401: invalid token"

    r = await client.get(f"/api/v1/integration-configs/{config_id}/test-logs", headers=owner_headers)
    assert r.status_code == 200, r.text
    logs = r.json()["data"]
    assert len(logs) == 2
    assert logs[0]["success"] is False  # newest first


async def test_list_configs_filtered_by_integration_type(client, mock_db, owner_headers):
    await _seed_providers(mock_db)
    await client.post(
        "/api/v1/integration-configs", json={"integration_type": "meta", "provider": "meta", "name": "M1", "config": {}}, headers=owner_headers
    )
    await client.post(
        "/api/v1/integration-configs", json={"integration_type": "maps", "provider": "google_maps", "name": "Maps1", "config": {}}, headers=owner_headers
    )
    r = await client.get("/api/v1/integration-configs?integration_type=meta", headers=owner_headers)
    assert r.status_code == 200, r.text
    items = r.json()["data"]
    assert len(items) == 1
    assert items[0]["integration_type"] == "meta"


# ---------------------------------------------------------------------- Meta multi-check test_meta()


async def _create_meta_config(client, owner_headers, name="Meta Config"):
    # `user_access_token` alongside `access_token` (the Page token) — matches a real
    # OAuth-connected config; /me/accounts and /me/adaccounts (meta_status.py) only ever
    # get called using the User token, so a config lacking one can't exercise those paths.
    r = await client.post(
        "/api/v1/integration-configs",
        json={
            "integration_type": "meta", "provider": "meta", "name": name,
            "config": {"app_id": "111", "app_secret": "s", "access_token": "t", "user_access_token": "user-tok"},
        },
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


async def test_meta_test_connection_all_checks_pass(client, mock_db, owner_headers, monkeypatch):
    await _seed_providers(mock_db)
    config_id = await _create_meta_config(client, owner_headers)

    async def _fake_debug_token(access_token, app_id, app_secret):
        return {"app_id": "111", "is_valid": True, "scopes": ["leads_retrieval", "pages_show_list", "pages_manage_metadata"]}, None

    monkeypatch.setattr(integrations_testers, "fetch_debug_token", _fake_debug_token)
    r = await client.post(f"/api/v1/integration-configs/{config_id}/test", json={}, headers=owner_headers)
    assert r.status_code == 200, r.text
    result = r.json()["data"]
    assert result["success"] is True
    checks = {c["key"]: c for c in result["checks"]}
    assert checks["app_id"]["passed"] is True
    assert checks["app_secret"]["passed"] is True
    assert checks["token"]["passed"] is True
    assert checks["permissions"]["passed"] is True


async def test_meta_test_connection_wrong_app_id_and_missing_permission(client, mock_db, owner_headers, monkeypatch):
    await _seed_providers(mock_db)
    config_id = await _create_meta_config(client, owner_headers)

    async def _fake_debug_token(access_token, app_id, app_secret):
        return {"app_id": "999", "is_valid": True, "scopes": ["pages_show_list"]}, None  # wrong app_id, missing leads_retrieval

    monkeypatch.setattr(integrations_testers, "fetch_debug_token", _fake_debug_token)
    r = await client.post(f"/api/v1/integration-configs/{config_id}/test", json={}, headers=owner_headers)
    assert r.status_code == 200, r.text
    result = r.json()["data"]
    assert result["success"] is False
    checks = {c["key"]: c for c in result["checks"]}
    assert checks["app_id"]["passed"] is False
    assert checks["permissions"]["passed"] is False
    assert "leads_retrieval" in checks["permissions"]["detail"]


async def test_meta_test_connection_invalid_token_reports_specific_error(client, mock_db, owner_headers, monkeypatch):
    await _seed_providers(mock_db)
    config_id = await _create_meta_config(client, owner_headers)

    async def _fake_debug_token_error(access_token, app_id, app_secret):
        return None, "Access Token is invalid or has expired."

    monkeypatch.setattr(integrations_testers, "fetch_debug_token", _fake_debug_token_error)
    r = await client.post(f"/api/v1/integration-configs/{config_id}/test", json={}, headers=owner_headers)
    assert r.status_code == 200, r.text
    result = r.json()["data"]
    assert result["success"] is False
    assert result["error_message"] == "Access Token is invalid or has expired."
    assert all(not c["passed"] for c in result["checks"])


async def test_meta_test_connection_reports_missing_field(client, mock_db, owner_headers):
    await _seed_providers(mock_db)
    r = await client.post(
        "/api/v1/integration-configs",
        json={"integration_type": "meta", "provider": "meta", "name": "Meta Incomplete", "config": {"app_id": "111"}},  # no secret/token
        headers=owner_headers,
    )
    config_id = r.json()["data"]["id"]
    r = await client.post(f"/api/v1/integration-configs/{config_id}/test", json={}, headers=owner_headers)
    assert r.status_code == 200, r.text
    result = r.json()["data"]
    assert result["success"] is False
    assert "app_secret" in result["error_message"]


# ---------------------------------------------------------------------- test-draft (stateless, no persistence)


async def test_draft_connection_does_not_persist_anything(client, mock_db, owner_headers, monkeypatch):
    async def _fake_success(_config):
        return ConnectionCheckResult(success=True, response_time_ms=5, error_message=None)

    monkeypatch.setitem(integrations_service.TESTERS, "whatsapp", _fake_success)
    r = await client.post(
        "/api/v1/integration-configs/test-draft",
        json={"integration_type": "whatsapp", "config": {"api_url": "https://wa.example.com"}},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["success"] is True

    assert await mock_db["integration_configs"].count_documents({}) == 0
    assert await mock_db["integration_test_logs"].count_documents({}) == 0


# ---------------------------------------------------------------------- Save/Activate staleness + gating


async def test_update_config_clears_success_and_active_only_on_credential_change(client, mock_db, owner_headers, monkeypatch):
    await _seed_providers(mock_db)
    r = await client.post(
        "/api/v1/integration-configs",
        json={"integration_type": "whatsapp", "provider": "whatsapp_business_api", "name": "WA", "config": {"api_url": "https://wa.example.com"}},
        headers=owner_headers,
    )
    config_id = r.json()["data"]["id"]

    async def _fake_success(_config):
        return ConnectionCheckResult(success=True, response_time_ms=1, error_message=None)

    monkeypatch.setitem(integrations_service.TESTERS, "whatsapp", _fake_success)
    await client.post(f"/api/v1/integration-configs/{config_id}/test", json={}, headers=owner_headers)
    await client.patch(f"/api/v1/integration-configs/{config_id}/enable", json={}, headers=owner_headers)
    await client.post(f"/api/v1/integration-configs/{config_id}/activate", json={}, headers=owner_headers)

    r = await client.get(f"/api/v1/integration-configs/{config_id}", headers=owner_headers)
    assert r.json()["data"]["is_active"] is True

    # Editing the name only must NOT reset test/active state.
    r = await client.patch(f"/api/v1/integration-configs/{config_id}", json={"name": "WA Renamed"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["is_active"] is True
    assert r.json()["data"]["last_success_at"] is not None

    # Editing actual credentials must reset test/active state.
    r = await client.patch(
        f"/api/v1/integration-configs/{config_id}", json={"config": {"api_url": "https://wa2.example.com"}}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    detail = r.json()["data"]
    assert detail["is_active"] is False
    assert detail["last_success_at"] is None
    assert detail["health_status"] is None

    r = await client.post(f"/api/v1/integration-configs/{config_id}/activate", json={}, headers=owner_headers)
    assert r.status_code == 422, r.text  # must retest before activating again


async def test_activate_requires_prior_successful_test(client, mock_db, owner_headers, monkeypatch):
    await _seed_providers(mock_db)
    r = await client.post(
        "/api/v1/integration-configs",
        json={"integration_type": "whatsapp", "provider": "whatsapp_business_api", "name": "WA", "config": {"api_url": "https://wa.example.com"}},
        headers=owner_headers,
    )
    config_id = r.json()["data"]["id"]
    await client.patch(f"/api/v1/integration-configs/{config_id}/enable", json={}, headers=owner_headers)

    r = await client.post(f"/api/v1/integration-configs/{config_id}/activate", json={}, headers=owner_headers)
    assert r.status_code == 422, r.text
    assert "Test the connection" in r.json()["error"]["message"]

    async def _fake_success(_config):
        return ConnectionCheckResult(success=True, response_time_ms=1, error_message=None)

    monkeypatch.setitem(integrations_service.TESTERS, "whatsapp", _fake_success)
    await client.post(f"/api/v1/integration-configs/{config_id}/test", json={}, headers=owner_headers)

    r = await client.post(f"/api/v1/integration-configs/{config_id}/activate", json={}, headers=owner_headers)
    assert r.status_code == 200, r.text


async def test_activated_at_set_once_and_not_overwritten(client, mock_db, owner_headers, monkeypatch):
    await _seed_providers(mock_db)
    r = await client.post(
        "/api/v1/integration-configs",
        json={"integration_type": "whatsapp", "provider": "whatsapp_business_api", "name": "WA", "config": {"api_url": "https://wa.example.com"}},
        headers=owner_headers,
    )
    config_id = r.json()["data"]["id"]

    async def _fake_success(_config):
        return ConnectionCheckResult(success=True, response_time_ms=1, error_message=None)

    monkeypatch.setitem(integrations_service.TESTERS, "whatsapp", _fake_success)
    await client.post(f"/api/v1/integration-configs/{config_id}/test", json={}, headers=owner_headers)
    await client.patch(f"/api/v1/integration-configs/{config_id}/enable", json={}, headers=owner_headers)
    await client.post(f"/api/v1/integration-configs/{config_id}/activate", json={}, headers=owner_headers)

    r = await client.get(f"/api/v1/integration-configs/{config_id}", headers=owner_headers)
    first_activated_at = r.json()["data"]["activated_at"]
    assert first_activated_at is not None

    await client.patch(f"/api/v1/integration-configs/{config_id}/disable", json={}, headers=owner_headers)
    await client.patch(f"/api/v1/integration-configs/{config_id}/enable", json={}, headers=owner_headers)
    await client.post(f"/api/v1/integration-configs/{config_id}/test", json={}, headers=owner_headers)
    await client.post(f"/api/v1/integration-configs/{config_id}/activate", json={}, headers=owner_headers)

    r = await client.get(f"/api/v1/integration-configs/{config_id}", headers=owner_headers)
    assert r.json()["data"]["activated_at"] == first_activated_at


async def test_test_log_records_graph_api_version_and_tested_ip(client, mock_db, owner_headers, monkeypatch):
    await _seed_providers(mock_db)
    config_id = await _create_meta_config(client, owner_headers)

    async def _fake_debug_token(access_token, app_id, app_secret):
        return {"app_id": "111", "is_valid": True, "scopes": ["leads_retrieval", "pages_show_list", "pages_manage_metadata"]}, None

    monkeypatch.setattr(integrations_testers, "fetch_debug_token", _fake_debug_token)
    await client.post(f"/api/v1/integration-configs/{config_id}/test", json={}, headers=owner_headers)

    r = await client.get(f"/api/v1/integration-configs/{config_id}/test-logs", headers=owner_headers)
    log = r.json()["data"][0]
    assert log["graph_api_version"] == "v19.0"
    assert "tested_ip" in log  # populated whenever the ASGI test transport exposes a client host


# ---------------------------------------------------------------------- Meta connection health / setup progress


async def test_meta_status_uses_user_token_for_me_accounts_and_page_token_for_page_scoped_calls(client, mock_db, owner_headers, monkeypatch):
    """Regression test for the confirmed bug: /me/accounts and /me/adaccounts require a
    User Access Token (they list what a *user* manages) — get_meta_status used to pass
    the Page Access Token (`access_token`) into both, which Meta rejects. Proves the
    fix by capturing exactly which token value reaches each Graph function."""
    await _seed_providers(mock_db)
    r = await client.post(
        "/api/v1/integration-configs",
        json={
            "integration_type": "meta", "provider": "meta", "name": "Meta OAuth Connected",
            "config": {"app_id": "111", "app_secret": "s", "access_token": "page-tok-XYZ", "user_access_token": "user-tok-ABC"},
        },
        headers=owner_headers,
    )
    config_id = r.json()["data"]["id"]

    calls: dict[str, str] = {}

    async def _fake_ad_accounts(token):
        calls["fetch_ad_accounts_count"] = token
        return 3

    async def _fake_pages(token):
        calls["fetch_pages"] = token
        return [{"id": "p1", "name": "Page One"}]

    async def _fake_lead_forms(token, page_ids):
        calls["fetch_lead_forms_count"] = token
        return 5

    async def _fake_debug_token(access_token, app_id, app_secret):
        calls["fetch_debug_token"] = access_token
        return {"app_id": "111", "is_valid": True, "scopes": []}, None

    monkeypatch.setattr(meta_status_client, "fetch_ad_accounts_count", _fake_ad_accounts)
    monkeypatch.setattr(meta_status_client, "fetch_pages", _fake_pages)
    monkeypatch.setattr(meta_status_client, "fetch_lead_forms_count", _fake_lead_forms)
    monkeypatch.setattr(integrations_testers, "fetch_debug_token", _fake_debug_token)

    r = await client.get(f"/api/v1/integration-configs/{config_id}/meta-status", headers=owner_headers)
    assert r.status_code == 200, r.text
    status = r.json()["data"]

    # The two previously-broken calls now receive the User token.
    assert calls["fetch_ad_accounts_count"] == "user-tok-ABC"
    assert calls["fetch_pages"] == "user-tok-ABC"
    # Page-scoped calls are untouched — still the Page token, exactly as before.
    assert calls["fetch_lead_forms_count"] == "page-tok-XYZ"
    assert calls["fetch_debug_token"] == "page-tok-XYZ"
    assert status["ad_accounts_count"] == 3
    assert status["pages_count"] == 1
    assert status["lead_forms_count"] == 5


async def test_meta_status_without_user_token_skips_me_accounts_calls_gracefully(client, mock_db, owner_headers, monkeypatch):
    """A config that was never connected via OAuth (no `user_access_token` at all —
    e.g. a legacy manually-pasted-token config) can't call /me/accounts or
    /me/adaccounts at all now; this must degrade to the same 'could not be determined'
    None values the code already used for a missing token, not raise or misuse the
    Page token as a fallback."""
    await _seed_providers(mock_db)
    config_id = await _create_meta_config(client, owner_headers)
    # Strip the helper's default user_access_token to simulate a legacy config.
    from app.security.encryption import decrypt, encrypt

    doc = await mock_db["integration_configs"].find_one({"_id": to_object_id(config_id)})
    current = json.loads(decrypt(doc["config_encrypted"]))
    current.pop("user_access_token", None)
    await mock_db["integration_configs"].update_one({"_id": doc["_id"]}, {"$set": {"config_encrypted": encrypt(json.dumps(current))}})

    called = {"me_endpoints": False}

    async def _fail_if_called(*_args, **_kwargs):
        called["me_endpoints"] = True
        raise AssertionError("fetch_ad_accounts_count/fetch_pages must not be called without a user_access_token")

    monkeypatch.setattr(meta_status_client, "fetch_ad_accounts_count", _fail_if_called)
    monkeypatch.setattr(meta_status_client, "fetch_pages", _fail_if_called)

    r = await client.get(f"/api/v1/integration-configs/{config_id}/meta-status", headers=owner_headers)
    assert r.status_code == 200, r.text
    status = r.json()["data"]
    assert called["me_endpoints"] is False
    assert status["ad_accounts_count"] is None
    assert status["pages_count"] is None
    assert status["lead_forms_count"] is None


async def test_meta_status_health_and_setup_progress_progression(client, mock_db, owner_headers, monkeypatch):
    await _seed_providers(mock_db)
    config_id = await _create_meta_config(client, owner_headers)

    r = await client.get(f"/api/v1/integration-configs/{config_id}/meta-status", headers=owner_headers)
    assert r.status_code == 200, r.text
    status = r.json()["data"]
    assert status["health_status"] is None
    assert status["setup_progress"]["saved"] is True
    assert status["setup_progress"]["test_connection_passed"] is False

    async def _fake_debug_token(access_token, app_id, app_secret):
        return {
            "app_id": "111", "is_valid": True, "scopes": ["leads_retrieval", "pages_show_list", "pages_manage_metadata"],
            "expires_at": 0, "application": "AFS Test App",
        }, None

    monkeypatch.setattr(integrations_testers, "fetch_debug_token", _fake_debug_token)
    await client.post(f"/api/v1/integration-configs/{config_id}/test", json={}, headers=owner_headers)

    async def _fake_ad_accounts(_token):
        return 2

    async def _fake_pages(_token):
        return [{"id": "p1", "name": "Page One"}, {"id": "p2", "name": "Page Two"}]

    async def _fake_lead_forms(_token, page_ids):
        return 8

    monkeypatch.setattr(meta_status_client, "fetch_ad_accounts_count", _fake_ad_accounts)
    monkeypatch.setattr(meta_status_client, "fetch_pages", _fake_pages)
    monkeypatch.setattr(meta_status_client, "fetch_lead_forms_count", _fake_lead_forms)

    r = await client.get(f"/api/v1/integration-configs/{config_id}/meta-status", headers=owner_headers)
    status = r.json()["data"]
    assert status["health_status"] == "warning"  # tested good, but webhook not verified / no lead yet
    assert status["ad_accounts_count"] == 2
    assert status["pages_count"] == 2
    assert status["lead_forms_count"] == 8
    assert status["belongs_to_app_name"] == "AFS Test App"
    assert status["missing_permissions"] == []
    assert status["setup_progress"]["test_connection_passed"] is True
    assert status["setup_progress"]["webhook_verified"] is False
    assert status["setup_progress"]["first_lead_received"] is False

    # Simulate a verified webhook + a received lead — health should progress to "healthy".
    await mock_db["integration_configs"].update_one({"_id": to_object_id(config_id)}, {"$set": {"webhook_verified_at": utc_now()}})
    await mock_db["capture_receipts"].insert_one({
        "capture_source": "meta_lead_ads", "external_id": "leadgen-1", "lead_id": "lead-1",
        "is_deleted": False, "created_at": utc_now(), "updated_at": utc_now(),
    })
    await client.patch(f"/api/v1/integration-configs/{config_id}/enable", json={}, headers=owner_headers)
    await client.post(f"/api/v1/integration-configs/{config_id}/activate", json={}, headers=owner_headers)

    r = await client.get(f"/api/v1/integration-configs/{config_id}/meta-status", headers=owner_headers)
    status = r.json()["data"]
    assert status["health_status"] == "healthy"
    assert status["setup_progress"]["webhook_verified"] is True
    assert status["setup_progress"]["first_lead_received"] is True
    assert status["setup_progress"]["activated"] is True
    assert status["total_leads_imported"] == 1
    assert status["last_lead_received_at"] is not None
    assert status["completed_steps"] == 6


async def test_meta_status_missing_permissions_reported_with_reason(client, mock_db, owner_headers, monkeypatch):
    await _seed_providers(mock_db)
    config_id = await _create_meta_config(client, owner_headers)

    async def _fake_debug_token(access_token, app_id, app_secret):
        return {"app_id": "111", "is_valid": True, "scopes": []}, None

    monkeypatch.setattr(integrations_testers, "fetch_debug_token", _fake_debug_token)
    r = await client.get(f"/api/v1/integration-configs/{config_id}/meta-status", headers=owner_headers)
    assert r.status_code == 200, r.text
    missing = {m["permission"]: m["why_needed"] for m in r.json()["data"]["missing_permissions"]}
    assert "leads_retrieval" in missing
    assert "pages_show_list" in missing
    assert missing["leads_retrieval"]  # non-empty explanation


async def test_meta_status_for_non_meta_config_is_gracefully_empty(client, mock_db, owner_headers):
    await _seed_providers(mock_db)
    r = await client.post(
        "/api/v1/integration-configs",
        json={"integration_type": "whatsapp", "provider": "whatsapp_business_api", "name": "WA", "config": {"api_url": "https://wa.example.com"}},
        headers=owner_headers,
    )
    config_id = r.json()["data"]["id"]
    r = await client.get(f"/api/v1/integration-configs/{config_id}/meta-status", headers=owner_headers)
    assert r.status_code == 200, r.text
    status = r.json()["data"]
    assert status["ad_accounts_count"] is None
    assert status["pages_count"] is None
    assert status["lead_forms_count"] is None
    assert status["missing_permissions"] == []


# ---------------------------------------------------------------------- Meta OAuth Connect flow


async def test_create_meta_config_auto_generates_and_reveals_webhook_credentials(client, mock_db, owner_headers):
    await _seed_providers(mock_db)
    r = await client.post(
        "/api/v1/integration-configs",
        json={"integration_type": "meta", "provider": "meta", "name": "Meta OAuth", "config": {"app_id": "111", "app_secret": "s"}},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["webhook_callback_path"] == "/lead-capture/webhooks/meta"
    verify_token, secret = data["config"]["webhook_verify_token"], data["config"]["webhook_secret"]
    assert "*" not in verify_token and len(verify_token) > 20
    assert "*" not in secret and len(secret) > 20

    # Never revealed again on a subsequent read — masked like any other secret from here on.
    r2 = await client.get(f"/api/v1/integration-configs/{data['id']}", headers=owner_headers)
    reread = r2.json()["data"]
    assert reread["webhook_callback_path"] is None
    assert "*" in reread["config"]["webhook_verify_token"]
    assert reread["config"]["webhook_verify_token"] != verify_token


async def test_meta_oauth_connect_and_disconnect_flow(client, mock_db, owner_headers, monkeypatch):
    await _seed_providers(mock_db)
    r = await client.post(
        "/api/v1/integration-configs",
        json={"integration_type": "meta", "provider": "meta", "name": "Meta OAuth", "config": {"app_id": "111", "app_secret": "s"}},
        headers=owner_headers,
    )
    config_id = r.json()["data"]["id"]

    r = await client.get(f"/api/v1/integration-configs/{config_id}/oauth/login", headers=owner_headers)
    assert r.status_code == 200, r.text
    state = parse_qs(urlparse(r.json()["data"]["authorize_url"]).query)["state"][0]

    async def _fake_exchange_code(*, app_id, app_secret, redirect_uri, code):
        return "short-lived-token", 3600

    async def _fake_exchange_long_lived(*, app_id, app_secret, short_lived_token):
        return "long-lived-user-token", 5_184_000

    async def _fake_pages(user_access_token):
        return [{"id": "PAGE1", "name": "Ashapura Page", "access_token": "page-token-1"}]

    async def _fake_ad_accounts(user_access_token):
        return [{"id": "act_1", "name": "Ashapura Ads"}]

    async def _fake_forms(*, page_access_token, page_id):
        return [{"id": "FORM1", "name": "Loan Interest Form"}]

    async def _fake_subscribe(*, page_access_token, page_id):
        return True

    async def _fake_business_id(*, page_access_token, page_id):
        return None

    monkeypatch.setattr(oauth_client, "exchange_code_for_token", _fake_exchange_code)
    monkeypatch.setattr(oauth_client, "exchange_for_long_lived_token", _fake_exchange_long_lived)
    monkeypatch.setattr(oauth_client, "fetch_pages_with_tokens", _fake_pages)
    monkeypatch.setattr(oauth_client, "fetch_ad_accounts", _fake_ad_accounts)
    monkeypatch.setattr(oauth_client, "fetch_lead_forms", _fake_forms)
    monkeypatch.setattr(oauth_client, "subscribe_page_to_leadgen", _fake_subscribe)
    monkeypatch.setattr(oauth_client, "fetch_page_business_id", _fake_business_id)

    r = await client.get("/api/v1/integration-configs/oauth/callback", params={"code": "authcode", "state": state})
    assert r.status_code == 307, r.text
    location = r.headers["location"]
    assert f"/integrations/{config_id}" in location
    session_id = parse_qs(urlparse(location).query)["oauth_session"][0]

    r = await client.get(f"/api/v1/integration-configs/{config_id}/oauth/session/{session_id}", headers=owner_headers)
    assert r.status_code == 200, r.text
    session_data = r.json()["data"]
    assert session_data["pages"] == [{"id": "PAGE1", "name": "Ashapura Page", "instagram_username": ""}]
    assert session_data["ad_accounts"] == [{"id": "act_1", "name": "Ashapura Ads"}]

    r = await client.get(f"/api/v1/integration-configs/{config_id}/oauth/session/{session_id}/forms", params={"page_id": "PAGE1"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == [{"id": "FORM1", "name": "Loan Interest Form"}]

    async def _fake_debug_token(access_token, app_id, app_secret):
        return {"app_id": "111", "is_valid": True, "scopes": ["leads_retrieval", "pages_show_list", "pages_manage_metadata"]}, None

    monkeypatch.setattr(integrations_testers, "fetch_debug_token", _fake_debug_token)

    r = await client.post(
        f"/api/v1/integration-configs/{config_id}/oauth/session/{session_id}/connect",
        json={"page_id": "PAGE1", "ad_account_id": "act_1", "selected_forms": ["FORM1"]},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    connected = r.json()["data"]
    assert connected["config"]["page_id"] == "PAGE1"
    assert connected["config"]["page_name"] == "Ashapura Page"
    assert connected["is_enabled"] is True
    assert connected["is_active"] is True  # OAuth proving the token works auto-tests + auto-activates
    assert connected["last_success_at"] is not None

    raw = await mock_db["integration_configs"].find_one({"_id": to_object_id(config_id)})
    stored = json.loads(decrypt(raw["config_encrypted"]))
    assert stored["access_token"] == "page-token-1"  # same key testers.py/meta_status.py/meta_client.py already read
    assert stored["selected_forms"] == "FORM1"

    # The OAuth session is single-use — reusing it after Connect must fail.
    r = await client.get(f"/api/v1/integration-configs/{config_id}/oauth/session/{session_id}", headers=owner_headers)
    assert r.status_code == 404, r.text

    r = await client.post(f"/api/v1/integration-configs/{config_id}/oauth/disconnect", headers=owner_headers)
    assert r.status_code == 200, r.text
    disconnected = r.json()["data"]
    assert disconnected["is_enabled"] is False
    assert disconnected["is_active"] is False

    raw_after_disconnect = await mock_db["integration_configs"].find_one({"_id": to_object_id(config_id)})
    stored_after_disconnect = json.loads(decrypt(raw_after_disconnect["config_encrypted"]))
    assert "page_id" not in stored_after_disconnect
    assert "access_token" not in stored_after_disconnect
    assert "user_access_token" not in stored_after_disconnect
    # App ID/App Secret are the Meta App Dashboard's own credentials, not OAuth output —
    # Disconnect must never touch them, so reconnecting doesn't require re-entering them.
    assert stored_after_disconnect["app_id"] == "111"
    assert stored_after_disconnect["app_secret"] == "s"


async def test_meta_oauth_login_rejects_non_meta_config(client, mock_db, owner_headers):
    await _seed_providers(mock_db)
    r = await client.post(
        "/api/v1/integration-configs",
        json={"integration_type": "whatsapp", "provider": "whatsapp_business_api", "name": "WA", "config": {"api_url": "https://wa.example.com"}},
        headers=owner_headers,
    )
    config_id = r.json()["data"]["id"]
    r = await client.get(f"/api/v1/integration-configs/{config_id}/oauth/login", headers=owner_headers)
    assert r.status_code == 422, r.text


async def test_meta_token_refresh_worker_replaces_expiring_token_safely(client, mock_db, mock_redis, owner_headers, monkeypatch):
    """Simulates the daily `refresh_meta_tokens` cron end-to-end: a config whose
    long-lived User Token is about to expire gets a fresh User + Page Token; a config
    that isn't due yet is left completely untouched; a config whose refresh call fails
    keeps its still-valid token (never overwritten with nothing) and only records the
    failure — exactly the three behaviors item 7 of the audit asks to verify."""
    await _seed_providers(mock_db)
    from datetime import timedelta

    from app.features.integrations.service import IntegrationsService
    from app.utils.datetime import utc_now

    service = IntegrationsService(mock_db, mock_redis)

    async def _make_connected_config(name: str, *, expires_in_days: float) -> str:
        r = await client.post(
            "/api/v1/integration-configs",
            json={"integration_type": "meta", "provider": "meta", "name": name, "config": {"app_id": "111", "app_secret": "s"}},
            headers=owner_headers,
        )
        config_id = r.json()["data"]["id"]
        config = await service.get_config(config_id)
        current = json.loads(decrypt(config.config_encrypted))
        current.update(
            {
                "access_token": "old-page-token", "user_access_token": "old-user-token", "page_id": "PAGE1",
                "user_token_expires_at": (utc_now() + timedelta(days=expires_in_days)).isoformat(),
            }
        )
        from app.security.encryption import encrypt

        await mock_db["integration_configs"].update_one(
            {"_id": to_object_id(config_id)}, {"$set": {"config_encrypted": encrypt(json.dumps(current)), "is_enabled": True}}
        )
        return config_id

    not_due_id = await _make_connected_config("Meta Not Due", expires_in_days=30)  # well outside the 7-day refresh window
    due_id = await _make_connected_config("Meta Due", expires_in_days=2)  # inside the window — should refresh
    failing_id = await _make_connected_config("Meta Failing", expires_in_days=1)  # inside the window — Graph call fails

    exchange_call_count = {"count": 0}

    async def _fake_exchange(*, app_id, app_secret, short_lived_token):
        exchange_call_count["count"] += 1
        return "new-user-token", 5_184_000

    async def _fake_refresh_page_token(*, user_access_token, page_id):
        # Processed in Mongo's natural insertion order: "due" first (succeeds), then
        # "failing" second (models Meta rejecting the refresh — e.g. a revoked grant).
        return "new-page-token" if exchange_call_count["count"] == 1 else None

    monkeypatch.setattr(oauth_client, "exchange_for_long_lived_token", _fake_exchange)
    monkeypatch.setattr(oauth_client, "refresh_page_token", _fake_refresh_page_token)

    await service.refresh_expiring_meta_tokens()

    # Not due — completely untouched, and never even attempted a Graph call for itself.
    not_due = json.loads(decrypt((await service.get_config(not_due_id)).config_encrypted))
    assert not_due["access_token"] == "old-page-token"
    assert not_due["user_access_token"] == "old-user-token"
    assert exchange_call_count["count"] == 2  # exactly the "due" + "failing" configs, not "not due"

    # Due and succeeded — new tokens in place, old ones gone.
    refreshed = json.loads(decrypt((await service.get_config(due_id)).config_encrypted))
    assert refreshed["access_token"] == "new-page-token"
    assert refreshed["user_access_token"] == "new-user-token"
    assert refreshed["user_token_expires_at"] != ""

    # Due but the Graph call failed — the still-valid old token must survive untouched,
    # and the failure must be visible (same fields a failed Test Connection would set).
    failed_config = await service.get_config(failing_id)
    failed_decrypted = json.loads(decrypt(failed_config.config_encrypted))
    assert failed_decrypted["access_token"] == "old-page-token"
    assert failed_decrypted["user_access_token"] == "old-user-token"
    assert failed_config.last_failure_at is not None
    assert "Token refresh failed" in (failed_config.last_error_message or "")

    audit_events = await mock_db["audit_logs"].find({"event_type": {"$in": ["integration_token_refreshed", "integration_token_refresh_failed"]}}).to_list(length=10)
    assert {e["event_type"] for e in audit_events} == {"integration_token_refreshed", "integration_token_refresh_failed"}


async def test_meta_oauth_connect_actually_calls_page_subscription(client, mock_db, owner_headers, monkeypatch):
    """Item 3's "automatic page subscription" claim, verified by actually asserting the
    Graph call happens during Connect — not just that a mocked version returns success."""
    await _seed_providers(mock_db)
    r = await client.post(
        "/api/v1/integration-configs",
        json={"integration_type": "meta", "provider": "meta", "name": "Meta OAuth", "config": {"app_id": "111", "app_secret": "s"}},
        headers=owner_headers,
    )
    config_id = r.json()["data"]["id"]
    r = await client.get(f"/api/v1/integration-configs/{config_id}/oauth/login", headers=owner_headers)
    state = parse_qs(urlparse(r.json()["data"]["authorize_url"]).query)["state"][0]

    subscribed_calls: list[tuple[str, str]] = []

    async def _fake_exchange_code(*, app_id, app_secret, redirect_uri, code):
        return "short-lived-token", 3600

    async def _fake_exchange_long_lived(*, app_id, app_secret, short_lived_token):
        return "long-lived-user-token", 5_184_000

    async def _fake_pages(user_access_token):
        return [{"id": "PAGE1", "name": "Ashapura Page", "access_token": "page-token-1"}]

    async def _fake_ad_accounts(user_access_token):
        return []

    async def _fake_subscribe(*, page_access_token, page_id):
        subscribed_calls.append((page_access_token, page_id))
        return True

    monkeypatch.setattr(oauth_client, "exchange_code_for_token", _fake_exchange_code)
    monkeypatch.setattr(oauth_client, "exchange_for_long_lived_token", _fake_exchange_long_lived)
    monkeypatch.setattr(oauth_client, "fetch_pages_with_tokens", _fake_pages)
    monkeypatch.setattr(oauth_client, "fetch_ad_accounts", _fake_ad_accounts)
    async def _fake_business_id(*, page_access_token, page_id):
        return None

    monkeypatch.setattr(oauth_client, "subscribe_page_to_leadgen", _fake_subscribe)
    monkeypatch.setattr(oauth_client, "fetch_page_business_id", _fake_business_id)

    r = await client.get("/api/v1/integration-configs/oauth/callback", params={"code": "authcode", "state": state})
    session_id = parse_qs(urlparse(r.headers["location"]).query)["oauth_session"][0]

    async def _fake_debug_token(access_token, app_id, app_secret):
        return {"app_id": "111", "is_valid": True, "scopes": ["leads_retrieval", "pages_show_list", "pages_manage_metadata"]}, None

    monkeypatch.setattr(integrations_testers, "fetch_debug_token", _fake_debug_token)

    r = await client.post(
        f"/api/v1/integration-configs/{config_id}/oauth/session/{session_id}/connect",
        json={"page_id": "PAGE1", "ad_account_id": None, "selected_forms": []},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    assert subscribed_calls == [("page-token-1", "PAGE1")]


async def test_meta_status_panel_surfaces_token_refresh_and_connection_summary(client, mock_db, mock_redis, owner_headers, monkeypatch):
    """The Owner-facing Status panel's new fields: connected Page/Ad Account/Form count,
    the long-lived User Token's own expiry, and when it was last refreshed."""
    await _seed_providers(mock_db)
    from datetime import timedelta

    from app.features.integrations.service import IntegrationsService
    from app.security.encryption import encrypt
    from app.utils.datetime import utc_now

    service = IntegrationsService(mock_db, mock_redis)
    r = await client.post(
        "/api/v1/integration-configs",
        json={"integration_type": "meta", "provider": "meta", "name": "Meta Status", "config": {"app_id": "111", "app_secret": "s"}},
        headers=owner_headers,
    )
    config_id = r.json()["data"]["id"]
    expires_at = utc_now() + timedelta(days=45)
    await mock_db["integration_configs"].update_one(
        {"_id": to_object_id(config_id)},
        {
            "$set": {
                "is_enabled": True,
                "config_encrypted": encrypt(
                    json.dumps(
                        {
                            "app_id": "111", "app_secret": "s", "access_token": "page-tok", "page_id": "PAGE1", "page_name": "Ashapura Page",
                            "ad_account_id": "act_1", "selected_forms": "FORM1,FORM2", "user_access_token": "user-tok",
                            "user_token_expires_at": expires_at.isoformat(),
                        }
                    )
                ),
            }
        },
    )
    await service.refresh_expiring_meta_tokens()  # not due (45 days out) — must not touch anything or write a refresh log

    r = await client.get(f"/api/v1/integration-configs/{config_id}/meta-status", headers=owner_headers)
    assert r.status_code == 200, r.text
    status = r.json()["data"]
    assert status["connected_page_name"] == "Ashapura Page"
    assert status["connected_ad_account_id"] == "act_1"
    assert status["connected_form_count"] == 2
    assert status["user_token_expires_at"] is not None
    assert status["last_token_refresh_at"] is None  # never refreshed yet

    await write_audit_log_helper(mock_db, config_id)
    r = await client.get(f"/api/v1/integration-configs/{config_id}/meta-status", headers=owner_headers)
    assert r.json()["data"]["last_token_refresh_at"] is not None


async def write_audit_log_helper(mock_db, config_id: str) -> None:
    from app.features.integrations.constants import AuditEvent
    from app.shared.audit_log import write_audit_log

    await write_audit_log(mock_db, event_type=AuditEvent.TOKEN_REFRESHED, user_id=None, metadata={"config_id": config_id})


async def test_meta_sync_forms_refetches_from_the_connected_page(client, mock_db, owner_headers, monkeypatch):
    await _seed_providers(mock_db)
    r = await client.post(
        "/api/v1/integration-configs",
        json={"integration_type": "meta", "provider": "meta", "name": "Meta Sync", "config": {"app_id": "111", "app_secret": "s"}},
        headers=owner_headers,
    )
    config_id = r.json()["data"]["id"]

    # Not yet connected — no Page/token stored — must reject with a clear error, not a 500.
    r = await client.get(f"/api/v1/integration-configs/{config_id}/oauth/forms", headers=owner_headers)
    assert r.status_code == 422, r.text

    from app.security.encryption import encrypt

    await mock_db["integration_configs"].update_one(
        {"_id": to_object_id(config_id)},
        {"$set": {"config_encrypted": encrypt(json.dumps({"app_id": "111", "app_secret": "s", "access_token": "page-tok", "page_id": "PAGE1"}))}},
    )

    async def _fake_forms(*, page_access_token, page_id):
        assert page_access_token == "page-tok"
        assert page_id == "PAGE1"
        return [{"id": "FORM1", "name": "Loan Form"}, {"id": "FORM2", "name": "Insurance Form"}]

    monkeypatch.setattr(oauth_client, "fetch_lead_forms", _fake_forms)
    r = await client.get(f"/api/v1/integration-configs/{config_id}/oauth/forms", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == [{"id": "FORM1", "name": "Loan Form"}, {"id": "FORM2", "name": "Insurance Form"}]


async def test_meta_oauth_callback_rejects_forged_state(client, mock_db, owner_headers):
    await _seed_providers(mock_db)
    r = await client.post(
        "/api/v1/integration-configs",
        json={"integration_type": "meta", "provider": "meta", "name": "Meta OAuth", "config": {"app_id": "111", "app_secret": "s"}},
        headers=owner_headers,
    )
    config_id = r.json()["data"]["id"]

    from app.security.encryption import encrypt

    forged_state = encrypt(json.dumps({"config_id": config_id, "nonce": "never-issued"}))
    r = await client.get("/api/v1/integration-configs/oauth/callback", params={"code": "authcode", "state": forged_state})
    assert r.status_code == 307, r.text
    assert "oauth_error" in r.headers["location"]
