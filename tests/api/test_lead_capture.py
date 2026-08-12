"""End-to-end tests for Module 9B (Lead Capture): Website form capture (success +
missing/invalid-data failures), Manual API capture (permission-gated), the Meta webhook
(verification handshake, HMAC signature enforcement, live Graph API retrieval
monkeypatched, idempotency via CaptureReceipt), the retry queue (resolves a transient
failure, exhausts after repeated failure), and Source Mapping admin endpoints.
"""

import hashlib
import hmac
import json
from datetime import timedelta

from app.features.integrations import oauth as integrations_oauth
from app.features.integrations.models import IntegrationConfig
from app.features.lead_capture import meta_client
from app.features.lead_capture.constants import FailureStatus
from app.features.lead_capture.models import CaptureFailure, CaptureSource
from app.features.lead_capture.service import LeadCaptureService
from app.features.system_settings.models import LeadSource
from app.security.encryption import encrypt
from app.utils.datetime import utc_now


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


async def _seed_lead_sources_and_capture_sources(mock_db, *, product_id: str) -> None:
    for name in ("Website", "Meta", "Manual"):
        await mock_db["lead_sources"].insert_one(LeadSource(name=name).model_dump(by_alias=True, exclude={"id"}))
    website_source = await mock_db["lead_sources"].find_one({"name": "Website"})
    meta_source = await mock_db["lead_sources"].find_one({"name": "Meta"})
    manual_source = await mock_db["lead_sources"].find_one({"name": "Manual"})

    rows = [
        CaptureSource(key="website_form", label="Website Form", lead_source_id=str(website_source["_id"])),
        CaptureSource(key="meta_lead_ads", label="Meta Lead Ads", lead_source_id=str(meta_source["_id"]), default_product_category="loan", default_product_id=product_id),
        CaptureSource(key="manual_api", label="Manual API", lead_source_id=str(manual_source["_id"])),
    ]
    for row in rows:
        await mock_db["capture_sources"].insert_one(row.model_dump(by_alias=True, exclude={"id"}))


async def _seed_loan_product(mock_db) -> str:
    from app.features.system_settings.models import LoanProduct

    result = await mock_db["loan_products"].insert_one(LoanProduct(name="Personal Loan").model_dump(by_alias=True, exclude={"id"}))
    return str(result.inserted_id)


async def _seed_active_meta_config(mock_db, *, access_token="tok123", verify_token="verify123", app_secret="whsecret456", selected_forms="") -> None:
    # `app_secret` is what Meta actually signs webhook payloads with (App Dashboard ->
    # App Settings -> Basic) — see LeadCaptureService.handle_meta_webhook's own comment.
    # `webhook_secret` is still generated/stored (shown once at config creation) but is
    # no longer read for POST signature verification; kept here only because it's part
    # of the same encrypted blob shape a real config would have.
    config = IntegrationConfig(
        integration_code="AFS-INTG-META1", integration_type="meta", provider="meta", name="Meta Production",
        config_encrypted=encrypt(
            json.dumps(
                {"access_token": access_token, "webhook_verify_token": verify_token, "app_secret": app_secret, "webhook_secret": "unused-legacy-value", "selected_forms": selected_forms}
            )
        ),
        is_enabled=True, is_active=True,
    )
    await mock_db["integration_configs"].insert_one(config.model_dump(by_alias=True, exclude={"id"}))


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def test_website_capture_success_and_lead_source_mapping(client, mock_db, owner_headers):
    product_id = await _seed_loan_product(mock_db)
    await _seed_lead_sources_and_capture_sources(mock_db, product_id=product_id)

    r = await client.post(
        "/api/v1/lead-capture/website",
        json={
            "full_name": "Jane Prospect", "mobile": "9876543210", "email": "jane@example.com", "product_category": "loan", "product_id": product_id,
            "form_version": "v2", "utm_source": "google", "utm_campaign": "spring-promo",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "created"
    lead_code = r.json()["data"]["lead_code"]

    lead_doc = await mock_db["leads"].find_one({"lead_code": lead_code})
    assert lead_doc is not None
    assert lead_doc["created_by"] is None  # system-actor attribution nulled out, per decision precedent

    website_source = await mock_db["lead_sources"].find_one({"name": "Website"})
    assert lead_doc["source_id"] == str(website_source["_id"])

    activity = await mock_db["lead_activities"].find_one({"lead_id": str(lead_doc["_id"]), "event_type": "captured"})
    assert activity is not None
    assert activity["metadata"]["capture_source"] == "website_form"
    # Reserved Lead Source Metadata / Form Version — captured only when supplied, never fabricated.
    assert activity["metadata"]["source_metadata"] == {"form_version": "v2", "utm_source": "google", "utm_campaign": "spring-promo"}


async def test_website_capture_missing_and_invalid_data_logged_as_failures(client, mock_db):
    product_id = await _seed_loan_product(mock_db)
    await _seed_lead_sources_and_capture_sources(mock_db, product_id=product_id)

    r = await client.post("/api/v1/lead-capture/website", json={"full_name": "No Mobile"})
    assert r.status_code == 422, r.text
    failures = await mock_db["capture_failures"].find({"failure_reason": "missing_required_fields"}).to_list(length=10)
    assert len(failures) == 1

    r = await client.post(
        "/api/v1/lead-capture/website", json={"full_name": "Bad Mobile", "mobile": "12345", "product_category": "loan", "product_id": product_id}
    )
    assert r.status_code == 422, r.text
    failures = await mock_db["capture_failures"].find({"failure_reason": "invalid_data"}).to_list(length=10)
    assert len(failures) == 1


async def test_manual_capture_is_permission_gated(client, mock_db, owner_headers, employee_headers, master_data):
    product_id = await _seed_loan_product(mock_db)
    await _seed_lead_sources_and_capture_sources(mock_db, product_id=product_id)

    r = await client.post(
        "/api/v1/lead-capture/manual", json={"full_name": "Manual Lead", "mobile": "9876500001", "product_category": "loan", "product_id": product_id},
        headers=employee_headers,
    )
    assert r.status_code == 403, r.text

    employee = await _create_employee(client, owner_headers, master_data, mobile="9900000201", email="capture.staff@example.com")
    await _grant_permission(client, owner_headers, employee["id"], module="lead_capture", resource="captures", actions=["create"])
    granted_headers = await _login(client, "9900000201", "InitialPass1")

    r = await client.post(
        "/api/v1/lead-capture/manual", json={"full_name": "Manual Lead", "mobile": "9876500001", "product_category": "loan", "product_id": product_id},
        headers=granted_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["lead_code"].startswith("AFS-LEAD-")


async def test_meta_webhook_verification_handshake(client, mock_db):
    await _seed_active_meta_config(mock_db, verify_token="correct-token")

    config_before = await mock_db["integration_configs"].find_one({"integration_type": "meta"})
    assert config_before.get("webhook_verified_at") is None

    r = await client.get("/api/v1/lead-capture/webhooks/meta", params={"hub.mode": "subscribe", "hub.verify_token": "correct-token", "hub.challenge": "12345"})
    assert r.status_code == 200, r.text
    assert r.text == "12345"

    # A successful handshake records the one genuine signal for the Connection Health
    # panel's "Webhook Verified" status (see integrations/models.py IntegrationConfig).
    config_after = await mock_db["integration_configs"].find_one({"integration_type": "meta"})
    assert config_after["webhook_verified_at"] is not None

    r = await client.get("/api/v1/lead-capture/webhooks/meta", params={"hub.mode": "subscribe", "hub.verify_token": "wrong-token", "hub.challenge": "12345"})
    assert r.status_code == 403, r.text


async def test_meta_webhook_verify_rejects_unsupported_hub_mode(client, mock_db):
    await _seed_active_meta_config(mock_db, verify_token="correct-token")
    r = await client.get("/api/v1/lead-capture/webhooks/meta", params={"hub.mode": "unsubscribe", "hub.verify_token": "correct-token", "hub.challenge": "1"})
    assert r.status_code == 400, r.text
    r = await client.get("/api/v1/lead-capture/webhooks/meta")  # no params at all — not a verification request
    assert r.status_code == 400, r.text


async def test_meta_webhook_verify_trims_whitespace_around_token(client, mock_db):
    await _seed_active_meta_config(mock_db, verify_token="correct-token")
    r = await client.get(
        "/api/v1/lead-capture/webhooks/meta", params={"hub.mode": "subscribe", "hub.verify_token": "  correct-token  ", "hub.challenge": "1"}
    )
    assert r.status_code == 200, r.text
    assert r.text == "1"


async def test_meta_webhook_verify_succeeds_before_config_is_active(client, mock_db, owner_headers):
    """Regression test for the reported production bug: 'GET /lead-capture/webhooks/meta
    -> 403 Forbidden' even with the correct hub.verify_token. Root cause: verification
    used to look up only the *active* Meta config, but a config is never active until
    after a full OAuth Connect — while Meta's dashboard 'Verify and Save' click (which
    triggers this exact GET request) is normally the very first setup step, done before
    OAuth Connect ever runs. Verification must succeed against ANY configured Meta
    credential set, active or not — this test creates a config exactly the way the
    Integrations UI does (POST /integration-configs, is_active defaults to False) and
    confirms the handshake now succeeds without ever enabling or activating it.
    """
    from app.features.integrations.models import IntegrationProvider

    await mock_db["integration_providers"].insert_one(
        IntegrationProvider(integration_type="meta", provider="meta", label="Meta").model_dump(by_alias=True, exclude={"id"})
    )
    r = await client.post(
        "/api/v1/integration-configs",
        json={"integration_type": "meta", "provider": "meta", "name": "Meta Not Yet Connected", "config": {"app_id": "1", "app_secret": "s"}},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    config = r.json()["data"]
    assert config["is_active"] is False  # exactly the real-world state at the moment Meta calls this endpoint
    verify_token = config["config"]["webhook_verify_token"]

    r = await client.get(
        "/api/v1/lead-capture/webhooks/meta", params={"hub.mode": "subscribe", "hub.verify_token": verify_token, "hub.challenge": "999"}
    )
    assert r.status_code == 200, r.text
    assert r.text == "999"

    updated = await mock_db["integration_configs"].find_one({"integration_code": config["integration_code"]})
    assert updated["webhook_verified_at"] is not None


async def test_meta_webhook_rejects_invalid_signature(client, mock_db):
    await _seed_active_meta_config(mock_db, app_secret="realsecret")
    body = json.dumps({"entry": []}).encode()
    r = await client.post("/api/v1/lead-capture/webhooks/meta", content=body, headers={"X-Hub-Signature-256": "sha256=deadbeef"})
    assert r.status_code == 403, r.text


async def test_meta_webhook_creates_lead_and_is_idempotent(client, mock_db, owner_headers, monkeypatch):
    product_id = await _seed_loan_product(mock_db)
    await _seed_lead_sources_and_capture_sources(mock_db, product_id=product_id)
    await _seed_active_meta_config(mock_db, access_token="tok123", app_secret="realsecret")

    async def _fake_fetch(leadgen_id, *, access_token):
        assert access_token == "tok123"
        return {"field_data": [{"name": "full_name", "values": ["Meta Prospect"]}, {"name": "phone_number", "values": ["+919876511111"]}]}

    monkeypatch.setattr(meta_client, "fetch_lead_fields", _fake_fetch)

    body = json.dumps({"entry": [{"id": "PAGE1", "changes": [{"field": "leadgen", "value": {"leadgen_id": "LEADGEN1", "form_id": "FORM1"}}]}]}).encode()
    signature = _sign(body, "realsecret")

    r = await client.post("/api/v1/lead-capture/webhooks/meta", content=body, headers={"X-Hub-Signature-256": signature})
    assert r.status_code == 200, r.text

    leads = await mock_db["leads"].find({"mobile": "9876511111"}).to_list(length=10)
    assert len(leads) == 1

    receipts = await mock_db["capture_receipts"].find({"external_id": "LEADGEN1"}).to_list(length=10)
    assert len(receipts) == 1

    # Retried webhook delivery (same leadgen_id) — idempotent, no second Lead created.
    r = await client.post("/api/v1/lead-capture/webhooks/meta", content=body, headers={"X-Hub-Signature-256": signature})
    assert r.status_code == 200, r.text
    leads = await mock_db["leads"].find({"mobile": "9876511111"}).to_list(length=10)
    assert len(leads) == 1


async def test_meta_webhook_captures_campaign_details_and_custom_questions(client, mock_db, owner_headers, monkeypatch):
    product_id = await _seed_loan_product(mock_db)
    await _seed_lead_sources_and_capture_sources(mock_db, product_id=product_id)
    await _seed_active_meta_config(mock_db, access_token="tok123", app_secret="realsecret")

    async def _fake_fetch(leadgen_id, *, access_token):
        return {
            "field_data": [
                {"name": "full_name", "values": ["Campaign Prospect"]},
                {"name": "phone_number", "values": ["9876555555"]},
                {"name": "Preferred City", "values": ["Ahmedabad"]},
            ]
        }

    async def _fake_campaign_details(*, access_token, ad_id):
        assert access_token == "tok123"
        assert ad_id == "AD1"
        return {"ad_name": "Personal Loan Ad", "adset_name": "Ahmedabad Adset", "campaign_name": "Q3 Loan Campaign"}

    monkeypatch.setattr(meta_client, "fetch_lead_fields", _fake_fetch)
    monkeypatch.setattr(integrations_oauth, "fetch_ad_campaign_details", _fake_campaign_details)

    body = json.dumps({"entry": [{"changes": [{"value": {"leadgen_id": "LEADGEN_CAMPAIGN", "ad_id": "AD1"}}]}]}).encode()
    signature = _sign(body, "realsecret")
    r = await client.post("/api/v1/lead-capture/webhooks/meta", content=body, headers={"X-Hub-Signature-256": signature})
    assert r.status_code == 200, r.text

    lead = await mock_db["leads"].find_one({"mobile": "9876555555"})
    assert lead is not None
    activity = await mock_db["lead_activities"].find_one({"lead_id": str(lead["_id"]), "event_type": "captured"})
    assert activity is not None
    metadata = activity["metadata"]["source_metadata"]
    assert metadata["campaign_name"] == "Q3 Loan Campaign"
    assert metadata["adset_name"] == "Ahmedabad Adset"
    assert metadata["ad_name"] == "Personal Loan Ad"
    assert metadata["ad_id"] == "AD1"
    assert json.loads(metadata["custom_questions"]) == {"Preferred City": "Ahmedabad"}


async def test_meta_webhook_skips_leads_from_unselected_forms(client, mock_db, owner_headers, monkeypatch):
    product_id = await _seed_loan_product(mock_db)
    await _seed_lead_sources_and_capture_sources(mock_db, product_id=product_id)
    # OAuth Connect (Module 9A) narrowed intake to one Lead Form on the Page.
    await _seed_active_meta_config(mock_db, access_token="tok123", app_secret="realsecret", selected_forms="FORM_A")

    async def _fake_fetch(leadgen_id, *, access_token):
        return {"field_data": [{"name": "full_name", "values": ["Should Not Import"]}, {"name": "phone_number", "values": ["9876544444"]}]}

    monkeypatch.setattr(meta_client, "fetch_lead_fields", _fake_fetch)

    body = json.dumps({"entry": [{"changes": [{"value": {"leadgen_id": "LEADGEN_SKIP", "form_id": "FORM_B"}}]}]}).encode()
    signature = _sign(body, "realsecret")
    r = await client.post("/api/v1/lead-capture/webhooks/meta", content=body, headers={"X-Hub-Signature-256": signature})
    assert r.status_code == 200, r.text

    assert await mock_db["leads"].count_documents({"mobile": "9876544444"}) == 0
    assert await mock_db["capture_failures"].count_documents({}) == 0  # an intentional skip, not a failure

    body = json.dumps({"entry": [{"changes": [{"value": {"leadgen_id": "LEADGEN_ALLOW", "form_id": "FORM_A"}}]}]}).encode()
    signature = _sign(body, "realsecret")
    r = await client.post("/api/v1/lead-capture/webhooks/meta", content=body, headers={"X-Hub-Signature-256": signature})
    assert r.status_code == 200, r.text
    assert await mock_db["leads"].count_documents({"mobile": "9876544444"}) == 1


async def test_meta_webhook_test_tool_synthetic_id_is_not_retried_forever(client, mock_db, monkeypatch):
    """Meta's Lead Ads Testing Tool sends a synthetic, permanently non-retrievable id
    (all-one-digit, e.g. "444444444444") — the resulting Graph 404/400 can never
    succeed no matter how many times it's retried. Must be classified `invalid_data`
    (status `ignored`, never retried) with a message that says so plainly, distinct
    from a genuine transient Graph failure on a real-looking id (proven unaffected by
    test_meta_webhook_transient_failure_is_queued_for_retry, just above/below)."""
    import httpx

    product_id = await _seed_loan_product(mock_db)
    await _seed_lead_sources_and_capture_sources(mock_db, product_id=product_id)
    await _seed_active_meta_config(mock_db, app_secret="realsecret")

    async def _fake_fetch_synthetic_id_failure(leadgen_id, *, access_token):
        assert leadgen_id == "444444444444"
        raise httpx.HTTPError(
            "Unsupported get request. Object with ID '444444444444' does not exist, cannot be loaded due to "
            "missing permissions, or does not support this operation."
        )

    monkeypatch.setattr(meta_client, "fetch_lead_fields", _fake_fetch_synthetic_id_failure)

    body = json.dumps({"entry": [{"changes": [{"value": {"leadgen_id": "444444444444", "form_id": "444444444444"}}]}]}).encode()
    signature = _sign(body, "realsecret")
    r = await client.post("/api/v1/lead-capture/webhooks/meta", content=body, headers={"X-Hub-Signature-256": signature})
    assert r.status_code == 200, r.text

    failure = await mock_db["capture_failures"].find_one({"capture_source": "meta_lead_ads", "raw_payload.leadgen_id": "444444444444"})
    assert failure is not None
    assert failure["failure_reason"] == "invalid_data"
    assert failure["status"] == "ignored"
    assert failure["next_retry_at"] is None


async def test_meta_client_annotates_test_tool_graph_failures_with_a_clear_message(monkeypatch):
    """Unit-level proof that meta_client.fetch_lead_fields itself (not just the service
    layer's classification) rewrites a synthetic-id Graph failure into an explicit,
    non-production-error message, while leaving a real-looking id's failure untouched."""
    import httpx

    from app.features.integrations import oauth as integrations_oauth_module

    async def _fake_graph_get(leadgen_id, *, access_token, fields, debug_label=None):
        raise httpx.HTTPError("Unsupported get request. Object with ID '444444444444' does not exist.")

    monkeypatch.setattr(integrations_oauth_module, "graph_get", _fake_graph_get)

    try:
        await meta_client.fetch_lead_fields("444444444444", access_token="tok")
        raise AssertionError("expected httpx.HTTPError")
    except httpx.HTTPError as exc:
        assert "Testing Tool" in str(exc)
        assert "not a production error" in str(exc)

    async def _fake_graph_get_real(leadgen_id, *, access_token, fields, debug_label=None):
        raise httpx.HTTPError("temporary Graph API outage")

    monkeypatch.setattr(integrations_oauth_module, "graph_get", _fake_graph_get_real)
    try:
        await meta_client.fetch_lead_fields("120209000123456789", access_token="tok")
        raise AssertionError("expected httpx.HTTPError")
    except httpx.HTTPError as exc:
        assert str(exc) == "temporary Graph API outage"  # untouched — not flagged as a Testing Tool id


def test_parse_meta_fields_missing_product_mapping_has_actionable_message():
    from app.features.lead_capture.parsers import CaptureValidationError, parse_meta_fields

    try:
        parse_meta_fields({"full_name": "Jane", "mobile": "9876543210"}, default_product_category=None, default_product_id=None)
        raise AssertionError("expected CaptureValidationError")
    except CaptureValidationError as exc:
        assert exc.detail == "Meta Lead Ads source requires a default Product Category and Product before leads can be created."


async def test_meta_webhook_transient_failure_is_queued_for_retry(client, mock_db, monkeypatch):
    product_id = await _seed_loan_product(mock_db)
    await _seed_lead_sources_and_capture_sources(mock_db, product_id=product_id)
    await _seed_active_meta_config(mock_db, app_secret="realsecret")

    import httpx

    async def _fake_fetch_failure(leadgen_id, *, access_token):
        raise httpx.ConnectError("connection failed")

    monkeypatch.setattr(meta_client, "fetch_lead_fields", _fake_fetch_failure)

    body = json.dumps({"entry": [{"changes": [{"value": {"leadgen_id": "LEADGEN2"}}]}]}).encode()
    signature = _sign(body, "realsecret")
    r = await client.post("/api/v1/lead-capture/webhooks/meta", content=body, headers={"X-Hub-Signature-256": signature})
    assert r.status_code == 200, r.text  # always ack once signature-verified

    failure = await mock_db["capture_failures"].find_one({"failure_reason": "api_error", "capture_source": "meta_lead_ads"})
    assert failure is not None
    assert failure["status"] == "pending"
    assert failure["next_retry_at"] is not None


async def test_retry_queue_resolves_then_exhausts(mock_db, owner_headers, monkeypatch):
    product_id = await _seed_loan_product(mock_db)
    await _seed_lead_sources_and_capture_sources(mock_db, product_id=product_id)
    await _seed_active_meta_config(mock_db, access_token="tok999", app_secret="whsecret")

    service = LeadCaptureService(mock_db)
    failure = CaptureFailure(
        capture_source="meta_lead_ads", failure_reason="api_error", raw_payload={"leadgen_id": "LEADGEN3"}, status=FailureStatus.PENDING,
        next_retry_at=utc_now() - timedelta(minutes=1),
    )
    failure_id = await service._failures.insert(failure)

    async def _fake_fetch_success(leadgen_id, *, access_token):
        return {"field_data": [{"name": "full_name", "values": ["Retried Prospect"]}, {"name": "phone_number", "values": ["9876522222"]}]}

    monkeypatch.setattr(meta_client, "fetch_lead_fields", _fake_fetch_success)
    await service.retry_due_failures()

    resolved = await service._failures.find_by_id(failure_id)
    assert resolved.status == FailureStatus.RESOLVED
    assert resolved.resolved_lead_id is not None

    # A fresh failure that keeps failing should exhaust after MAX_RETRY_ATTEMPTS.
    failure2 = CaptureFailure(
        capture_source="meta_lead_ads", failure_reason="api_error", raw_payload={"leadgen_id": "LEADGEN4"}, status=FailureStatus.PENDING,
        next_retry_at=utc_now() - timedelta(minutes=1), retry_count=4,
    )
    failure2_id = await service._failures.insert(failure2)

    import httpx

    async def _fake_fetch_failure(leadgen_id, *, access_token):
        raise httpx.ConnectError("still failing")

    monkeypatch.setattr(meta_client, "fetch_lead_fields", _fake_fetch_failure)
    await service.retry_due_failures()

    exhausted = await service._failures.find_by_id(failure2_id)
    assert exhausted.status == FailureStatus.EXHAUSTED


async def test_source_mapping_admin_endpoints(client, mock_db, owner_headers, employee_headers):
    product_id = await _seed_loan_product(mock_db)
    await _seed_lead_sources_and_capture_sources(mock_db, product_id=product_id)

    r = await client.get("/api/v1/lead-capture/sources", headers=employee_headers)
    assert r.status_code == 403, r.text

    r = await client.get("/api/v1/lead-capture/sources", headers=owner_headers)
    assert r.status_code == 200, r.text
    keys = {s["key"] for s in r.json()["data"]}
    assert keys == {"website_form", "meta_lead_ads", "manual_api"}

    r = await client.patch("/api/v1/lead-capture/sources/website_form", json={"default_product_category": "insurance"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["default_product_category"] == "insurance"


async def test_capture_failures_list_and_manual_retry(client, mock_db, owner_headers, monkeypatch):
    product_id = await _seed_loan_product(mock_db)
    await _seed_lead_sources_and_capture_sources(mock_db, product_id=product_id)
    await _seed_active_meta_config(mock_db)

    failure = CaptureFailure(capture_source="meta_lead_ads", failure_reason="api_error", raw_payload={"leadgen_id": "LEADGEN5"}, status=FailureStatus.PENDING)
    result = await mock_db["capture_failures"].insert_one(failure.model_dump(by_alias=True, exclude={"id"}))

    r = await client.get("/api/v1/lead-capture/failures", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 1

    async def _fake_fetch_success(leadgen_id, *, access_token):
        return {"field_data": [{"name": "full_name", "values": ["Manually Retried"]}, {"name": "phone_number", "values": ["9876533333"]}]}

    monkeypatch.setattr(meta_client, "fetch_lead_fields", _fake_fetch_success)
    r = await client.post(f"/api/v1/lead-capture/failures/{result.inserted_id}/retry", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "resolved"


