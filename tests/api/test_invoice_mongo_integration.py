"""Opt-in REAL MongoDB invoice checks; only a loopback server and random test DB.

Set AFS_INVOICE_TEST_MONGO_URI to a local test MongoDB URI to run. No configured
application database is used. Every test owns and removes its random test namespace.
"""

import asyncio
import os
from uuid import uuid4

import pytest
from app.features.auth.models import User
from app.features.invoices.repository import ensure_invoice_indexes
from app.features.invoices.schemas import InvoiceInput, StatusInput
from app.features.invoices.service import InvoiceService
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from test_invoices import sample


@pytest.fixture
async def real_invoice_db():
    uri = os.environ.get("AFS_INVOICE_TEST_MONGO_URI")
    if not uri:
        pytest.skip(
            "AFS_INVOICE_TEST_MONGO_URI not supplied; real MongoDB checks are opt-in"
        )
    from pymongo.uri_parser import parse_uri

    parsed = parse_uri(uri)
    if any(
        host not in {"localhost", "127.0.0.1", "::1"}
        for host, _port in parsed["nodelist"]
    ):
        pytest.fail("Invoice integration tests only accept a loopback MongoDB server")
    connection = AsyncIOMotorClient(uri, tz_aware=True, serverSelectionTimeoutMS=2000)
    await connection.admin.command("ping")
    name = "afs_invoice_test_" + uuid4().hex
    database = connection[name]
    try:
        yield database
    finally:
        assert (
            database.name.startswith("afs_invoice_test_") and len(database.name) == 49
        )
        await connection.drop_database(database.name)
        connection.close()


async def test_real_mongo_tail_reuse_concurrent_allocations_and_restart(
    real_invoice_db, mock_redis
):
    db = real_invoice_db
    await ensure_invoice_indexes(db)
    actor = User(id=str(ObjectId()), mobile="9000000001", role="owner")
    service = InvoiceService(db, mock_redis)
    payload = InvoiceInput.model_validate(sample())
    first = await service.create(payload, actor)
    tail = await service.create(payload, actor)
    assert (await service.delete_draft(tail["id"], 1, actor, "Test deletion"))[
        "number_reusable"
    ]
    # New service instance against persisted Mongo state, without in-process numbering state.
    service = InvoiceService(db, mock_redis)
    created = await asyncio.gather(*(service.create(payload, actor) for _ in range(20)))
    assert len({row["invoice_number"] for row in created}) == 20
    assert sum(row["invoice_number"] == tail["invoice_number"] for row in created) == 1
    assert not (await service.delete_draft(first["id"], 1, actor))["number_reusable"]
    latest = max(created, key=lambda row: row["invoice_number"])
    await asyncio.gather(
        service.delete_draft(latest["id"], 1, actor),
        *(service.create(payload, actor) for _ in range(10)),
    )
    reserved = await db.invoices.find({"is_deleted": False}).to_list(None)
    assert len(reserved) == len({row["invoice_number"] for row in reserved})
    assert all(row["invoice_number"] != first["invoice_number"] for row in reserved)
    assert (await db.invoices.find_one({"_id": ObjectId(tail["id"])}))["is_deleted"]


async def test_real_mongo_concurrent_correction_and_stale_saves(
    real_invoice_db, mock_redis
):
    db = real_invoice_db
    await ensure_invoice_indexes(db)
    actor = User(id=str(ObjectId()), mobile="9000000001", role="owner")
    service = InvoiceService(db, mock_redis)
    company = await service.company.get_or_create()
    await service.company.update(
        company.require_id(),
        {
            "company_name": "Synthetic Invoice Test",
            "address": {
                "line1": "Test street",
                "city": "Pune",
                "state": "Maharashtra",
                "pincode": "411030",
            },
            "invoice_config": {
                "gstin": "29DFPPP1103E1ZI",
                "bank_name": "Test bank",
                "account_number": "1234",
                "ifsc": "UBIN0813982",
            },
        },
    )
    original = await service.create(InvoiceInput.model_validate(sample()), actor)
    original = await service.status(
        original["id"], StatusInput(status="issued", version=1), actor
    )
    results = await asyncio.gather(
        *(
            service.duplicate(
                original["id"],
                actor,
                replacement=True,
                reason="Correct amount",
                request_key=f"real-correction-request-{i:03}",
            )
            for i in range(15)
        )
    )
    assert len({row["id"] for row in results}) == 1
    draft = results[0]
    changed = sample()
    changed["customer"]["name"] = "Corrected Customer"
    changed["items"][0].update(quantity="2", rate="100")
    edits = await asyncio.gather(
        *(
            service.update(draft["id"], InvoiceInput.model_validate(changed), actor)
            for _ in range(5)
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(result, dict) for result in edits) == 1
    assert all(
        isinstance(result, dict) or getattr(result, "http_status", None) == 409
        for result in edits
    )
    resumed = await InvoiceService(db, mock_redis).correction_draft(
        original["id"], actor
    )
    assert resumed["id"] == draft["id"] and resumed["grand_total"] == "236.00"
    assert await service.get(original["id"], actor) == original
    assert await db.invoices.count_documents({"replacement_for": original["id"]}) == 1


async def test_real_mongo_reviewed_index_migration_and_legacy_guard(
    real_invoice_db, mock_redis
):
    import importlib.util
    from pathlib import Path

    from app.features.invoices.numbering import reuse_ready

    spec = importlib.util.spec_from_file_location(
        "real_invoice_migration",
        Path(__file__).parents[2] / "scripts" / "migrate_invoice_number_reuse.py",
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    db = real_invoice_db
    await db.invoices.create_index("invoice_number", unique=True)
    await ensure_invoice_indexes(db)
    assert not await reuse_ready(db)
    await migration.migrate(db)
    assert not await reuse_ready(db)
    await migration.migrate(db, apply=True)
    assert await reuse_ready(db)
    actor = User(id=str(ObjectId()), mobile="9000000001", role="owner")
    service = InvoiceService(db, mock_redis)
    doc = await service.create(InvoiceInput.model_validate(sample()), actor)
    await service.delete_draft(doc["id"], 1, actor)
    new = await service.create(InvoiceInput.model_validate(sample()), actor)
    assert new["invoice_number"] == doc["invoice_number"]
    with pytest.raises(RuntimeError, match="Duplicate invoice numbers"):
        await migration.migrate(db, apply=True, rollback=True)


@pytest.mark.parametrize("restore_cancelled", [False, True])
async def test_real_mongo_same_number_revision_cas_and_immutable_original(
    real_invoice_db, mock_redis, restore_cancelled
):
    from app.features.invoices.revisions import InvoiceRevisionService
    from app.features.invoices.schemas import ReissueInput, RevisionInput
    from app.utils.datetime import utc_now

    db = real_invoice_db
    await ensure_invoice_indexes(db)
    actor = User(id=str(ObjectId()), mobile="9000000001", role="owner")
    service = InvoiceService(db, mock_redis)
    company = await service.company.get_or_create()
    await service.company.update(
        company.require_id(),
        {
            "company_name": "Synthetic Invoice Revision Test",
            "address": {
                "line1": "Test street",
                "city": "Pune",
                "state": "Maharashtra",
                "pincode": "411030",
            },
            "invoice_config": {
                "gstin": "29DFPPP1103E1ZI",
                "bank_name": "Test bank",
                "account_number": "1234",
                "ifsc": "UBIN0813982",
                "same_number_reissue_enabled": True,
                "same_number_policy_reason": "Approved synthetic test policy",
                "same_number_policy_approved_by": actor.require_id(),
                "same_number_policy_approved_at": utc_now(),
            },
        },
    )
    original = await service.create(InvoiceInput.model_validate(sample()), actor)
    original = await service.status(
        original["id"], StatusInput(status="issued", version=1), actor
    )
    if restore_cancelled:
        original = await service.status(
            original["id"],
            StatusInput(
                status="cancelled",
                version=original["version"],
                reason="Accidental cancellation",
            ),
            actor,
        )
    revisions = InvoiceRevisionService(service)
    original_snapshot = await revisions.historical(original["id"], 1, actor)
    counter = await db.counters.find_one({"_id": "INV"})
    indexes = await db.invoices.index_information()
    changed = sample()
    changed["items"][0].update(rate="100", quantity="2")
    payload = RevisionInput(
        invoice=InvoiceInput.model_validate(changed),
        version=original["version"],
        reason="Correct amount",
    )
    requests = await asyncio.gather(
        *(revisions.request(original["id"], payload, actor) for _ in range(10)),
        return_exceptions=True,
    )
    assert sum(isinstance(row, dict) for row in requests) == 1
    pending = next(row for row in requests if isinstance(row, dict))
    approvals = await asyncio.gather(
        *(
            revisions.reissue(
                original["id"],
                ReissueInput(
                    version=pending["version"],
                    proposal_id=pending["revision_proposal"]["id"],
                    approval_reason="Owner approved",
                ),
                actor,
            )
            for _ in range(8)
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(row, dict) for row in approvals) == 1
    effective = await service.get(original["id"], actor)
    assert (
        effective["id"] == original["id"]
        and effective["invoice_number"] == original["invoice_number"]
    )
    assert effective["effective_revision"] == 2 and effective["grand_total"] == "236.00"
    assert effective["status"] == "issued" and effective["reissued_at"]
    if restore_cancelled:
        assert effective["cancellation_reason"] == "Accidental cancellation"
    assert await revisions.historical(original["id"], 1, actor) == original_snapshot
    assert await db.invoices.count_documents({}) == 1
    assert (await db.counters.find_one({"_id": "INV"}))["seq"] == counter["seq"]
    assert await db.invoices.index_information() == indexes


async def test_real_mongo_retirement_wins_against_already_started_legacy_issue(
    real_invoice_db, mock_redis, monkeypatch
):
    from app.features.invoices.revisions import InvoiceRevisionService
    from app.features.invoices.schemas import ReissueInput, RevisionInput
    from app.utils.datetime import utc_now

    db = real_invoice_db
    await ensure_invoice_indexes(db)
    actor = User(id=str(ObjectId()), mobile="9000000001", role="owner")
    service = InvoiceService(db, mock_redis)
    company = await service.company.get_or_create()
    await service.company.update(
        company.require_id(),
        {
            "company_name": "Synthetic Legacy Recovery",
            "address": {
                "line1": "Test street",
                "city": "Pune",
                "state": "Maharashtra",
                "pincode": "411030",
            },
            "invoice_config": {
                "gstin": "29DFPPP1103E1ZI",
                "bank_name": "Test bank",
                "account_number": "1234",
                "ifsc": "UBIN0813982",
                "same_number_reissue_enabled": True,
                "same_number_policy_reason": "Owner approved test",
                "same_number_policy_approved_by": actor.require_id(),
                "same_number_policy_approved_at": utc_now(),
            },
        },
    )
    original = await service.create(InvoiceInput.model_validate(sample()), actor)
    original = await service.status(
        original["id"], StatusInput(status="issued", version=1), actor
    )
    original = await service.status(
        original["id"],
        StatusInput(
            status="cancelled",
            version=original["version"],
            reason="Accidental cancellation",
        ),
        actor,
    )
    legacy = await service.duplicate(
        original["id"], actor, replacement=True, reason="Old workflow"
    )
    before_counter = await db.counters.find_one({"_id": "INV"})
    ready, release = asyncio.Event(), asyncio.Event()
    real_replace = service.replace

    async def paused_replace(invoice_id, current, version, updates, user, action):
        if invoice_id == legacy["id"] and updates.get("status") == "issued":
            ready.set()
            await release.wait()
        return await real_replace(invoice_id, current, version, updates, user, action)

    monkeypatch.setattr(service, "replace", paused_replace)
    issuing = asyncio.create_task(
        service.status(legacy["id"], StatusInput(status="issued", version=1), actor)
    )
    try:
        await asyncio.wait_for(ready.wait(), 5)
        revisions = InvoiceRevisionService(service)
        pending = await revisions.request(
            original["id"],
            RevisionInput(
                invoice=InvoiceInput.model_validate(sample()),
                version=original["version"],
                reason="Correct original number",
            ),
            actor,
        )
        restored = await revisions.reissue(
            original["id"],
            ReissueInput(
                version=pending["version"],
                proposal_id=pending["revision_proposal"]["id"],
                approval_reason="Owner approved retiring old copy",
                retire_legacy_drafts=True,
                legacy_draft_versions={legacy["id"]: legacy["version"]},
            ),
            actor,
        )
        assert (
            restored["invoice_number"] == original["invoice_number"]
            and restored["status"] == "issued"
        )
    finally:
        release.set()
        outcome = await asyncio.gather(issuing, return_exceptions=True)
    assert getattr(outcome[0], "http_status", None) == 409
    retired = await service.get(legacy["id"], actor)
    assert (
        retired["status"] == "cancelled"
        and retired["is_archived"]
        and not retired["issued_at"]
    )
    assert retired["invoice_number"] == legacy["invoice_number"]
    assert (await db.counters.find_one({"_id": "INV"}))["seq"] == before_counter["seq"]
    assert (
        await db.invoices.count_documents({"status": "issued", "is_deleted": False})
        == 1
    )


async def test_real_mongo_direct_save_concurrency_with_issued_replacement(
    real_invoice_db, mock_redis
):
    from app.features.invoices.revisions import InvoiceRevisionService
    from app.features.invoices.schemas import DirectRevisionInput
    from app.utils.datetime import utc_now

    db = real_invoice_db
    await ensure_invoice_indexes(db)
    actor = User(id=str(ObjectId()), mobile="9000000001", role="owner")
    service = InvoiceService(db, mock_redis)
    company = await service.company.get_or_create()
    await service.company.update(
        company.require_id(),
        {
            "company_name": "Synthetic Legacy Recovery",
            "address": {
                "line1": "Test street",
                "city": "Pune",
                "state": "Maharashtra",
                "pincode": "411030",
            },
            "invoice_config": {
                "gstin": "29DFPPP1103E1ZI",
                "bank_name": "Test bank",
                "account_number": "1234",
                "ifsc": "UBIN0813982",
                "same_number_reissue_enabled": True,
                "same_number_policy_reason": "Owner approved test",
                "same_number_policy_approved_by": actor.require_id(),
                "same_number_policy_approved_at": utc_now(),
            },
        },
    )

    original = await service.create(InvoiceInput.model_validate(sample()), actor)
    original = await service.status(
        original["id"], StatusInput(status="issued", version=1), actor
    )
    original = await service.status(
        original["id"],
        StatusInput(status="cancelled", version=2, reason="Accidental cancellation"),
        actor,
    )
    # Seed the historical separately numbered copy through its existing legacy API.
    legacy = await service.duplicate(
        original["id"], actor, replacement=True, reason="Legacy correction"
    )
    legacy = await service.status(
        legacy["id"], StatusInput(status="issued", version=legacy["version"]), actor
    )
    revisions = InvoiceRevisionService(service)
    frozen = await revisions.historical(original["id"], 1, actor)
    child_frozen = await revisions.historical(legacy["id"], 1, actor)
    counter = await db.counters.find_one({"_id": "INV"})
    changed = sample()
    changed["customer"]["name"] = "Directly saved company"
    payload = DirectRevisionInput(
        invoice=InvoiceInput.model_validate(changed),
        version=original["version"],
        reason="Direct correction",
        legacy_replacement_versions={legacy["id"]: legacy["version"]},
    )
    outcomes = await asyncio.gather(
        *(revisions.save(original["id"], payload, actor) for _ in range(12)),
        return_exceptions=True,
    )
    assert sum(isinstance(row, dict) for row in outcomes) == 1
    saved = await service.get(original["id"], actor)
    assert (
        saved["invoice_number"] == original["invoice_number"]
        and saved["status"] == "issued"
    )
    assert saved["effective_revision"] == 2 and saved["revision_proposal"] is None
    assert saved["customer"]["name"] == "Directly saved company"
    assert await revisions.historical(original["id"], 1, actor) == frozen
    assert await revisions.historical(legacy["id"], 1, actor) == child_frozen
    child = await service.get(legacy["id"], actor)
    assert child["status"] == "cancelled" and child["is_archived"]
    assert await db.invoices.count_documents({"status": "issued"}) == 1
    assert await db.invoices.count_documents({}) == 2
    assert (await db.counters.find_one({"_id": "INV"}))["seq"] == counter["seq"]
    raw = await db.invoices.find_one({"_id": ObjectId(original["id"])})
    assert "revision_save_lock" not in raw
