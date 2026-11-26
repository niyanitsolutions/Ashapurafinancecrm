# ruff: noqa: F811
"""Identity matching, activity idempotency and reversible Owner-only reconciliation."""

import asyncio
from types import SimpleNamespace

import pytest
from app.core.exceptions import ConflictError, ForbiddenError
from app.features.auth.models import User
from app.features.daily_operations.identity import (
    apply_link,
    candidates,
    name_key,
    preview,
    resolve_rows,
    rollback_link,
)
from app.features.daily_operations.router import IdentityDecision, IdentityRollback
from app.features.daily_operations.schemas import FollowUpInput
from app.features.daily_operations.service import (
    DailyOperationsService,
    ensure_daily_operations_indexes,
)
from app.shared.customer_identity import normalize_mobile
from bson import ObjectId
from test_pin_mongo_integration import pin_mongo  # noqa: F401


@pytest.mark.parametrize(
    "value", ["+91 98765-43210", "0091 (98765) 43210", "919876543210", "9876543210"]
)
def test_exact_normalization(value):
    assert normalize_mobile(value) == "9876543210"
    assert name_key("  RAVI   Kumar  ") == "ravi kumar"
    assert name_key("O?Neil") != name_key("O Neil")
    assert name_key("A-B") != name_key("A B")


async def seed(db):
    uid, cid, aid = ObjectId(), ObjectId(), ObjectId()
    await db.users.insert_one(
        {"_id": uid, "mobile": "9876543210", "role": "customer", "is_deleted": False}
    )
    await db.customers.insert_one(
        {
            "_id": cid,
            "full_name": "Ravi Kumar",
            "mobile": "+91 98765-43210",
            "user_id": str(uid),
            "is_deleted": False,
        }
    )
    await db.applications.insert_one(
        {"_id": aid, "customer_id": str(cid), "user_id": str(uid), "is_deleted": False}
    )
    return str(cid), str(aid)


async def test_exact_vs_partial_and_snapshots(mock_db):
    cid, aid = await seed(mock_db)
    assert (await candidates(mock_db, " RAVI   KUMAR ", "9876543210"))["exact"] == [cid]
    assert (await candidates(mock_db, "Suresh", "9876543210"))["partial"] == [cid]
    assert (await candidates(mock_db, "Ravi Kumar", "9876543211"))["partial"] == [cid]
    row = {
        "_id": ObjectId(),
        "application_id": aid,
        "customer_name": "",
        "customer_number": "old",
    }
    await resolve_rows(mock_db, [row])
    assert row["customer_name"] == "Ravi Kumar"
    assert row["identity_snapshot"]["customer_name"] == ""
    assert row["identity_state"] == "linked_current"
    row = {
        "application_id": aid,
        "customer_id": str(ObjectId()),
        "customer_name": "Historical",
    }
    await resolve_rows(mock_db, [row])
    assert (
        row["customer_name"] == "Historical"
        and row["identity_state"] == "manual_review"
    )


def payload(**changes):
    return FollowUpInput.model_validate(
        {
            "date": "2026-11-25",
            "remarks_date": "2026-11-25",
            "customer_name": "Ravi Kumar",
            "customer_number": "9876543210",
            "bank": "Test Bank",
            "status": "DISBURSE",
            "remarks": "Keep history",
            **changes,
        }
    )


def owner():
    return User(id=str(ObjectId()), mobile="9876543200", role="owner", status="active")


async def test_activity_retry_distinct_days_and_manual_review(mock_db):
    await ensure_daily_operations_indexes(mock_db)
    await seed(mock_db)
    service = DailyOperationsService(mock_db)
    actor = owner()
    body = payload(
        customer_name="Independent Prospect",
        customer_number="9876543299",
        idempotency_key="stable-submission-0001",
    )
    first = await service.save("follow-ups", body, actor)
    retry = await service.save("follow-ups", body, actor)
    assert first["id"] == retry["id"] and not first.get("customer_id")
    assert "request_fingerprint" not in first and "activity_key" not in first
    with pytest.raises(ConflictError):
        await service.save(
            "follow-ups",
            payload(
                customer_name="Independent Prospect",
                customer_number="9876543299",
                idempotency_key="stable-submission-0002",
            ),
            actor,
        )
    separate = await service.save(
        "follow-ups",
        payload(
            customer_name="Independent Prospect",
            customer_number="9876543299",
            idempotency_key="stable-submission-0002",
            separate_activity_reason="Second bank discussion",
        ),
        actor,
    )
    tomorrow = await service.save(
        "follow-ups",
        payload(
            customer_name="Independent Prospect",
            customer_number="9876543299",
            date="2026-11-26",
            remarks_date="2026-11-26",
        ),
        actor,
    )
    assert len({first["id"], separate["id"], tomorrow["id"]}) == 3
    with pytest.raises(ConflictError):
        await service.save("follow-ups", payload(), actor)
    with pytest.raises(ConflictError):
        await service.save("follow-ups", payload(customer_name="Suresh"), actor)
    reviewed = await service.save(
        "follow-ups",
        payload(
            customer_name="Suresh",
            identity_review_reason="Verified separate person with supplied evidence",
        ),
        actor,
    )
    assert reviewed["identity_state"] == "reviewed_distinct" and not reviewed.get(
        "customer_id"
    )
    assert await mock_db.customers.count_documents({}) == 1
    assert await mock_db.applications.count_documents({}) == 1
    assert (await mock_db.daily_follow_ups.find_one({"_id": ObjectId(first["id"])}))[
        "history"
    ][0]["after"]["remarks"] == "Keep history"


async def test_preview_is_bounded_read_only_and_owner_only(mock_db):
    await seed(mock_db)
    await mock_db.daily_follow_ups.insert_many(
        [
            {
                "_id": ObjectId(),
                "version": 1,
                "is_deleted": False,
                "customer_name": "RAVI KUMAR",
                "customer_number": "9876543210",
            }
            for _ in range(3)
        ]
    )
    before = await mock_db.daily_follow_ups.find({}).to_list(10)
    report = await preview(mock_db, owner(), limit=2)
    assert (
        report["mode"] == "read_only"
        and report["has_more"]
        and len(report["items"]) == 2
    )
    assert report["counts"]["safe_candidates"] == 2
    assert before == await mock_db.daily_follow_ups.find({}).to_list(10)
    with pytest.raises(ForbiddenError):
        await preview(mock_db, SimpleNamespace(role="employee"))


async def test_real_concurrency_and_reconciliation_rollback(pin_mongo):
    db = pin_mongo
    await ensure_daily_operations_indexes(db)
    cid, aid = await seed(db)
    actor = owner()
    service = DailyOperationsService(db)
    body = payload(
        customer_name="Independent Prospect",
        customer_number="9876543299",
        idempotency_key="concurrent-submission-0001",
    )
    results = await asyncio.gather(
        *(service.save("follow-ups", body, actor) for _ in range(6))
    )
    assert len({r["id"] for r in results}) == 1
    assert await db.daily_follow_ups.count_documents({}) == 1
    historical = {
        "_id": ObjectId(),
        "import_key": "historical",
        "is_deleted": False,
        "version": 1,
        "customer_name": "Ravi Kumar",
        "customer_number": "9876543210",
        "history": [],
        "remarks": "Original",
    }
    await db.daily_follow_ups.insert_one(historical)
    report = await preview(db, actor)
    item = next(r for r in report["items"] if r["id"] == str(historical["_id"]))
    body = IdentityDecision(
        version=1,
        customer_id=cid,
        application_id=aid,
        preview_fingerprint=item["preview_fingerprint"],
        reason="Owner verified identity using original application",
        confirmed=True,
    )
    linked = await apply_link(db, actor, item["id"], body)
    with pytest.raises(ConflictError):
        await apply_link(db, actor, item["id"], body)
    undone = await rollback_link(
        db,
        actor,
        item["id"],
        IdentityRollback(
            version=linked["version"],
            event_id=linked["event_id"],
            reason="Owner approved rollback of test link",
            confirmed=True,
        ),
    )
    saved = await db.daily_follow_ups.find_one({"_id": historical["_id"]})
    assert "customer_id" not in saved and saved["remarks"] == "Original"
    assert saved["version"] == undone["version"] and len(saved["history"]) == 2
    assert await db.audit_logs.count_documents({}) == 2
    assert await db.applications.count_documents({}) == 1


async def test_identity_preview_route_is_not_captured_by_generic_kind(
    client, owner_headers, mock_db
):
    response = await client.get(
        "/api/v1/daily-operations/identity-review/preview?limit=2",
        headers=owner_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["mode"] == "read_only"
    assert await mock_db.daily_follow_ups.count_documents({}) == 0


async def test_null_names_and_inconsistent_reference_users_are_reviewed(mock_db):
    _cid, aid = await seed(mock_db)
    row = {"application_id": aid, "customer_name": None, "customer_number": None}
    await resolve_rows(mock_db, [row])
    assert (
        row["customer_name"] == "Ravi Kumar"
        and row["identity_snapshot"]["customer_name"] is None
    )
    empty = {"customer_name": None, "customer_number": None}
    await resolve_rows(mock_db, [empty])
    assert empty["identity_state"] == "manual_review"
    lead = ObjectId()
    await mock_db.leads.insert_one(
        {
            "_id": lead,
            "user_id": str(ObjectId()),
            "is_deleted": False,
            "full_name": "Different person",
        }
    )
    conflict = {
        "application_id": aid,
        "lead_id": str(lead),
        "customer_name": "Original snapshot",
    }
    await resolve_rows(mock_db, [conflict])
    assert (
        conflict["identity_state"] == "manual_review"
        and conflict["customer_name"] == "Original snapshot"
    )
