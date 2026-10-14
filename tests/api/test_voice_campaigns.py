from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from bson import ObjectId

from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.features.auth.models import User
from app.features.customer.models import Customer
from app.features.voice_assistant.campaign_router import parse_audience_csv
from app.features.voice_assistant.campaign_schemas import AudienceInput, CampaignAction, CampaignInput, ContactConsentInput, RecipientInput, SuppressionInput
from app.features.voice_assistant.campaign_service import CampaignService
from app.features.voice_assistant.catalog import initialize_voice_module
from app.features.voice_assistant.scheduling import local_to_utc
from app.utils.datetime import utc_now


@pytest.fixture
async def campaign_context(mock_db, mock_redis, owner_headers):
    await initialize_voice_module(mock_db)
    actor = User.model_validate(await mock_db.users.find_one({"role": "owner"}))
    customer = Customer(customer_code="AFS-CUS-TEST", user_id=str(ObjectId()), full_name="Campaign fixture", mobile="9000000100")
    customer_id = str((await mock_db.customers.insert_one(customer.model_dump(by_alias=True, exclude={"id"}))).inserted_id)
    return CampaignService(mock_db, mock_redis), actor, customer_id


async def prepare(context):
    svc, actor, customer_id = context
    campaign = await svc.save(CampaignInput(name="Eligibility test", purpose="service_callback", objective="Verify eligibility without dialing", calling_start="00:00", calling_end="23:59"), actor)
    payload = AudienceInput(version=campaign["version"], idempotency_key=uuid4().hex, recipients=[RecipientInput(customer_id=customer_id), RecipientInput(customer_id=customer_id)])
    receipt = await svc.audience(campaign["id"], payload, actor)
    return campaign, payload, receipt


async def test_audience_idempotency_and_no_contact_side_effects(campaign_context, mock_db):
    svc, actor, customer_id = campaign_context
    campaign, payload, receipt = await prepare(campaign_context)
    assert receipt["duplicates_in_file"] == 1
    assert await svc.audience(campaign["id"], payload, actor) == receipt
    assert await mock_db.voice_campaign_recipients.count_documents({}) == 1
    with pytest.raises(ConflictError):
        await svc.audience(campaign["id"], payload.model_copy(update={"recipients": [RecipientInput(customer_id=customer_id)]}), actor)
    preview = await svc.preview(campaign["id"], actor)
    assert preview["items"][0]["reason"] == "missing_or_expired_consent"
    assert preview["calls_placed"] == 0
    assert await mock_db.voice_calls.count_documents({}) == 0


async def test_consent_suppression_withdrawal_and_atomic_history(campaign_context):
    svc, actor, customer_id = campaign_context
    campaign, _, _ = await prepare(campaign_context)
    grant = ContactConsentInput(customer_id=customer_id, purpose="service_callback", action="grant", evidence_reference="test-only-attestation", expires_at=utc_now() + timedelta(days=1))
    policy = await svc.save_contact_policy(grant, actor)
    assert len(policy["history"]) == 1
    assert (await svc.preview(campaign["id"], actor))["items"][0]["reason"] == "dry_run_eligible"
    await svc.save_contact_policy(SuppressionInput(customer_id=customer_id, reason="test opt-out"), actor)
    assert (await svc.preview(campaign["id"], actor))["items"][0]["reason"] == "suppressed"
    withdrawn = await svc.save_contact_policy(grant.model_copy(update={"version": policy["version"], "action": "withdraw"}), actor)
    assert [event["action"] for event in withdrawn["history"]] == ["grant", "withdraw"]


async def test_worker_recovery_and_emergency_stop(campaign_context, mock_db):
    svc, actor, _ = campaign_context
    campaign, _, _ = await prepare(campaign_context)
    doc = await svc.get(campaign["id"], actor)
    ready = await svc.action(campaign["id"], CampaignAction(version=doc["version"], action="validate"), actor)
    await svc.action(campaign["id"], CampaignAction(version=ready["version"], action="start"), actor)
    await mock_db.voice_campaign_recipients.update_one({}, {"$set": {"status": "leased", "lease_until": utc_now() - timedelta(seconds=1), "lease_token": "expired"}})
    assert (await svc.sweep())["processed"] == 1
    assert (await svc.get(campaign["id"], actor))["status"] == "completed"
    assert await mock_db.voice_calls.count_documents({}) == 0
    await svc.emergency(True, "test emergency stop", actor)
    assert await svc.sweep() == {"processed": 0, "failed": 0}


async def test_live_modes_and_cross_owner_scope_blocked(campaign_context):
    svc, actor, _ = campaign_context
    for mode in ("test", "production"):
        with pytest.raises(ForbiddenError):
            await svc.save(CampaignInput(name="Blocked live", purpose="service_callback", objective="Must never place a call", mode=mode), actor)
    campaign, _, _ = await prepare(campaign_context)
    other = actor.model_copy(update={"id": ObjectId(), "role": "employee"})
    with pytest.raises(ForbiddenError):
        await svc.get(campaign["id"], other)
    with pytest.raises(ForbiddenError):
        await svc.emergency(True, "Unauthorized stop", other)


async def test_capacity_boundary_and_rejected_import_recovery(campaign_context, mock_db):
    svc, actor, customer_id = campaign_context
    campaign, _, _ = await prepare(campaign_context)
    # Boundary fixture construction is not a Mongo throughput benchmark. Mongomock
    # implements unique-index insertion quadratically; real Mongo indexes are tested
    # by the idempotency/concurrent-reservation cases separately.
    await mock_db.voice_campaign_recipients.drop_indexes()
    await mock_db.voice_campaign_recipients.insert_many([
        {"campaign_id": campaign["id"], "customer_id": str(ObjectId()), "status": "pending"}
        for _ in range(9999)
    ])
    assert await mock_db.voice_campaign_recipients.count_documents({"campaign_id": campaign["id"]}) == 10_000
    extra = Customer(customer_code="AFS-CUS-EXTRA", user_id=str(ObjectId()), full_name="Extra fixture", mobile="9000000101")
    extra_id = str((await mock_db.customers.insert_one(extra.model_dump(by_alias=True, exclude={"id"}))).inserted_id)
    doc = await svc.get(campaign["id"], actor)
    payload = AudienceInput(version=doc["version"], idempotency_key=uuid4().hex, recipients=[RecipientInput(customer_id=extra_id)])
    with pytest.raises(ValidationError):
        await svc.audience(campaign["id"], payload, actor)
    assert await mock_db.voice_campaign_imports.count_documents({"status": "pending"}) == 0
    assert await mock_db.voice_campaign_recipients.count_documents({"campaign_id": campaign["id"]}) == 10_000
    assert not (await svc.get(campaign["id"], actor)).get("import_lease_until")


async def test_concurrent_workers_fence_duplicate_reservations(campaign_context, mock_db, monkeypatch):
    import asyncio

    svc, actor, _ = campaign_context
    campaign, _, _ = await prepare(campaign_context)
    doc = await svc.get(campaign["id"], actor)
    ready = await svc.action(campaign["id"], CampaignAction(version=doc["version"], action="validate"), actor)
    await svc.action(campaign["id"], CampaignAction(version=ready["version"], action="start"), actor)
    entered, release = asyncio.Event(), asyncio.Event()
    original = svc.eligibility

    async def held_eligibility(*args):
        entered.set()
        await release.wait()
        return await original(*args)

    monkeypatch.setattr(svc, "eligibility", held_eligibility)
    first = asyncio.create_task(svc.sweep())
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        outcomes = await asyncio.gather(*(svc.sweep() for _ in range(9)))
        assert sum(result["processed"] for result in outcomes) == 0
    finally:
        release.set()
        first_result = await first
    assert first_result["processed"] == 1
    assert (await mock_db.voice_campaign_recipients.find_one({}))["attempts"] == 1
    assert await mock_db.voice_calls.count_documents({}) == 0


async def test_import_lease_loss_is_recoverable_without_false_completion(campaign_context, mock_db, monkeypatch):
    svc, actor, customer_id = campaign_context
    campaign = await svc.save(CampaignInput(name="Lease recovery", purpose="service_callback", objective="Test interrupted audience import"), actor)
    extra = Customer(customer_code="AFS-CUS-RECOVERY", user_id=str(ObjectId()), full_name="Recovery fixture", mobile="9000000102")
    extra_id = str((await mock_db.customers.insert_one(extra.model_dump(by_alias=True, exclude={"id"}))).inserted_id)
    payload = AudienceInput(version=1, idempotency_key=uuid4().hex, recipients=[RecipientInput(customer_id=customer_id), RecipientInput(customer_id=extra_id)])
    original = svc.check_import_lease
    checks = 0

    async def expire(doc):
        nonlocal checks
        checks += 1
        if checks == 2:
            await mock_db.voice_campaigns.update_one({"_id": doc["_id"]}, {"$set": {"import_lease_until": utc_now() - timedelta(seconds=1)}})
        await original(doc)

    monkeypatch.setattr(svc, "check_import_lease", expire)
    with pytest.raises(ConflictError):
        await svc.audience(campaign["id"], payload, actor)
    assert await mock_db.voice_campaign_recipients.count_documents({}) == 1
    assert (await mock_db.voice_campaign_imports.find_one({}))["status"] == "pending"
    monkeypatch.setattr(svc, "check_import_lease", original)
    assert (await svc.audience(campaign["id"], payload, actor))["total_recipients"] == 2


async def test_future_campaign_preview_is_not_currently_eligible(campaign_context):
    svc, actor, customer_id = campaign_context
    campaign = await svc.save(CampaignInput(name="Future review", purpose="service_callback", objective="Test future campaign scheduling", scheduled_at=utc_now() + timedelta(days=1)), actor)
    await svc.audience(campaign["id"], AudienceInput(version=1, idempotency_key=uuid4().hex, recipients=[RecipientInput(customer_id=customer_id)]), actor)
    preview = await svc.preview(campaign["id"], actor)
    assert preview["items"][0]["reason"] == "campaign_not_due"
    assert preview["items"][0]["eligible"] is False


async def test_noncanonical_campaign_id_cannot_split_recipient_scope(campaign_context, mock_db):
    svc, actor, _ = campaign_context
    campaign, _, _ = await prepare(campaign_context)
    doc = await svc.get(campaign["id"], actor)
    doc["_id"] = ObjectId("a" * 24)
    await mock_db.voice_campaigns.insert_one(doc)
    with pytest.raises(ValidationError):
        await svc.preview("A" * 24, actor)


@pytest.mark.parametrize("record_id", ["A" * 24, "not-an-id"])
async def test_import_envelope_limit_cannot_be_bypassed_by_id_shape(client, owner_headers, record_id):
    response = await client.post(f"/api/v1/voice-assistant/campaigns/{record_id}/recipients/import", headers={**owner_headers, "Content-Length": str(30 * 1024 * 1024)}, content=b"x")
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "voice_upload_rejected"


def test_dst_gaps_and_ambiguity():
    with pytest.raises(ValidationError):
        local_to_utc(datetime(2026, 3, 8, 2, 30), "America/New_York")
    with pytest.raises(ValidationError):
        local_to_utc(datetime(2026, 11, 1, 1, 30), "America/New_York")
    assert local_to_utc(datetime(2026, 11, 1, 1, 30), "America/New_York", 1) - local_to_utc(datetime(2026, 11, 1, 1, 30), "America/New_York", 0) == timedelta(hours=1)
    assert local_to_utc(datetime(2026, 1, 1, 10), "Asia/Kolkata") == datetime(2026, 1, 1, 4, 30, tzinfo=UTC)


def test_csv_rejects_contact_data_and_oversized_audience():
    with pytest.raises(ValidationError):
        parse_audience_csv(b"phone\n9000000000\n")
    with pytest.raises(ValidationError):
        parse_audience_csv(("customer_id\n" + ("a" * 24 + "\n") * 501).encode())
    assert len(parse_audience_csv(("customer_id,timezone\n" + "a" * 24 + ",Asia/Kolkata\n").encode())) == 1


async def test_registered_campaign_api_enforces_permissions(client, owner_headers, employee_headers, campaign_context):
    path = "/api/v1/voice-assistant/campaigns"
    assert (await client.get(path)).status_code in (401, 403)
    assert (await client.get(path, headers=employee_headers)).status_code == 403
    payload = {"name": "API campaign", "purpose": "service_callback", "objective": "Verify registered endpoint", "mode": "production"}
    assert (await client.post(path, headers=owner_headers, json=payload)).status_code == 403
    payload["mode"] = "dry_run"
    result = await client.post(path, headers=owner_headers, json=payload)
    assert result.status_code == 200, result.text
    assert result.json()["data"]["status"] == "draft"


async def test_contact_policy_api_denies_employee_and_records_owner_attestation(client, owner_headers, employee_headers, campaign_context):
    _, _, customer_id = campaign_context
    path = "/api/v1/voice-assistant/contact-policies/consent"
    payload = {"customer_id": customer_id, "purpose": "service_callback", "action": "grant", "evidence_reference": "fixture-attestation", "expires_at": (utc_now() + timedelta(days=1)).isoformat()}
    assert (await client.put(path, headers=employee_headers, json=payload)).status_code == 403
    result = await client.put(path, headers=owner_headers, json=payload)
    assert result.status_code == 200, result.text
    assert result.json()["data"]["verification"] == "operator_attested_not_independently_verified"
