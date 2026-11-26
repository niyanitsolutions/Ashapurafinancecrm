# ruff: noqa: F811
"""One exact Application workspace, explicit identity choices, reversible review."""

import asyncio

import pytest
from app.core.exceptions import ConflictError, ForbiddenError
from app.features.daily_operations.identity import apply_link, preview, rollback_link
from app.features.daily_operations.linked import OpenLinkedRequest, open_linked
from app.features.daily_operations.resolution import search
from app.features.daily_operations.router import IdentityDecision, IdentityRollback
from app.features.daily_operations.schemas import FollowUpInput
from app.features.daily_operations.service import (
    DailyOperationsService,
    ensure_daily_operations_indexes,
)
from bson import ObjectId
from test_pin_mongo_integration import pin_mongo  # noqa: F401
from test_unified_operations import seed_identity, seed_team


@pytest.fixture
async def workspace(pin_mongo):
    db = pin_mongo
    await ensure_daily_operations_indexes(db)
    owner, employees = await seed_team(db)
    customer, application = await seed_identity(db, "Synthetic Prospect")
    await db.applications.update_one(
        {"_id": ObjectId(application.id)}, {"$set": {"assigned_to": employees[0][0].id}}
    )
    return db, owner, employees, customer, application


async def test_application_workspace_atomic_idempotent_and_two_applications_separate(
    workspace,
):
    db, owner, _, customer, app = workspace
    service = DailyOperationsService(db)
    body = OpenLinkedRequest(entity="application", record_id=app.id)
    attempts = await asyncio.gather(
        *(open_linked(service, body, owner) for _ in range(5)), return_exceptions=True
    )
    assert all(isinstance(result, (dict, ConflictError)) for result in attempts)
    rows = [result for result in attempts if isinstance(result, dict)]
    assert (
        rows
    )  # At least one transaction commits; a losing writer may require explicit refresh.
    assert len({r["id"] for r in rows}) == 1
    assert (await open_linked(service, body, owner))["id"] == rows[0]["id"]
    assert await db.daily_follow_ups.count_documents({}) == 1
    assert (
        await db.audit_logs.count_documents({"event_type": "daily_follow_up_linked"})
        == 1
    )
    raw = await db.applications.find_one({"_id": ObjectId(app.id)})
    raw["_id"] = ObjectId()
    raw["application_code"] = "SYNTHETIC-APP-SECOND"
    await db.applications.insert_one(raw)
    second = await open_linked(
        service,
        OpenLinkedRequest(entity="application", record_id=str(raw["_id"])),
        owner,
    )
    assert second["id"] != rows[0]["id"]
    result = await search(service, owner, customer.customer_code)
    assert {r["id"] for r in result["items"] if r["entity"] == "application"} == {
        app.id,
        str(raw["_id"]),
    }
    assert all(r["workspace_status"] == "Existing workspace" for r in result["items"])
    exact_code = await search(service, owner, "SYNTHETIC-APP-SECOND")
    assert len(exact_code["items"]) == 1
    assert exact_code["items"][0]["workspace_status"] == "Existing workspace"
    assert exact_code["items"][0]["mobile"] == customer.mobile


async def test_manual_entry_cannot_bypass_matching_identity_even_on_another_day(
    workspace,
):
    db, owner, _, customer, _ = workspace
    body = FollowUpInput(
        date="2026-11-26",
        remarks_date="2026-11-26",
        customer_name=customer.full_name,
        customer_number=customer.mobile,
        bank="Synthetic Bank",
        next_action="Call",
        due_date="2026-11-26",
        separate_activity_reason="Second activity should use the workspace",
        idempotency_key="synthetic-submission-key",
    )
    with pytest.raises(ConflictError):
        await DailyOperationsService(db).save("follow-ups", body, owner)
    assert await db.daily_follow_ups.count_documents({}) == 0
    prospect = body.model_copy(
        update={
            "customer_name": "New Unverified Prospect",
            "customer_number": "9000070099",
            "separate_activity_reason": "",
        }
    )
    row = await DailyOperationsService(db).save("follow-ups", prospect, owner)
    assert row["relationship_label"] == "Standalone - Unlinked"
    assert not row.get("customer_id") and not row.get("application_id")


async def test_owner_application_link_keeps_record_history_and_can_undo(workspace):
    db, owner, employees, customer, app = workspace
    record = {
        "_id": ObjectId(),
        "version": 1,
        "is_deleted": False,
        "import_key": "synthetic-history",
        "customer_name": customer.full_name,
        "customer_number": customer.mobile,
        "assigned_to": employees[0][0].id,
        "remarks": "Historical note",
        "history": [{"source": "manual", "after": {"remarks": "Historical note"}}],
    }
    await db.daily_follow_ups.insert_one(record)
    before = await db.daily_follow_ups.find_one({"_id": record["_id"]})
    report = await preview(db, owner)
    assert await db.daily_follow_ups.find_one({"_id": record["_id"]}) == before
    item = report["items"][0]
    body = IdentityDecision(
        version=1,
        customer_id=customer.id,
        application_id=app.id,
        confirmed=True,
        reason="Owner verified exact application relationship",
        preview_fingerprint=item["preview_fingerprint"],
    )
    with pytest.raises(ForbiddenError):
        await apply_link(db, employees[0][1], str(record["_id"]), body)
    result = await apply_link(db, owner, str(record["_id"]), body)
    linked = await db.daily_follow_ups.find_one({"_id": record["_id"]})
    assert linked["application_id"] == app.id and linked["remarks"] == record["remarks"]
    assert linked["history"][:1] == record["history"]
    assert (
        await open_linked(
            DailyOperationsService(db),
            OpenLinkedRequest(entity="application", record_id=app.id),
            owner,
        )
    )["id"] == str(record["_id"])
    await rollback_link(
        db,
        owner,
        str(record["_id"]),
        IdentityRollback(
            version=result["version"],
            event_id=result["event_id"],
            confirmed=True,
            reason="Owner reversed the latest synthetic link",
        ),
    )
    restored = await db.daily_follow_ups.find_one({"_id": record["_id"]})
    assert (
        not restored.get("application_id")
        and not restored.get("working_key")
        and not restored.get("customer_id")
    )
    assert restored["remarks"] == record["remarks"] and len(restored["history"]) == 3
    assert (
        await db.audit_logs.count_documents(
            {
                "event_type": {
                    "$in": ["daily_identity_link", "daily_identity_link_rollback"]
                }
            }
        )
        == 2
    )


async def test_existing_historical_reference_blocks_creation_of_second_workspace(
    workspace,
):
    db, owner, _, _, app = workspace
    await db.daily_follow_ups.insert_one(
        {"application_id": app.id, "import_key": "legacy", "is_deleted": False}
    )
    with pytest.raises(ConflictError):
        await open_linked(
            DailyOperationsService(db),
            OpenLinkedRequest(entity="application", record_id=app.id),
            owner,
        )
    assert await db.daily_follow_ups.count_documents({}) == 1


async def test_workspace_audit_failures_roll_back(workspace):
    from app.features.daily_operations.workspace_activity import commit

    db, owner, _, _, app = workspace
    request = OpenLinkedRequest(entity="application", record_id=app.id)
    await db.audit_logs.create_index("event_type", unique=True)
    await db.audit_logs.insert_one({"event_type": "daily_follow_up_linked"})
    with pytest.raises(ConflictError):
        await open_linked(DailyOperationsService(db), request, owner)
    assert await db.daily_follow_ups.count_documents({}) == 0
    await db.audit_logs.delete_many({})
    row = await open_linked(DailyOperationsService(db), request, owner)
    raw = await db.daily_follow_ups.find_one({"_id": ObjectId(row["id"])})
    await db.audit_logs.insert_one({"event_type": "daily_follow_up_updated"})
    with pytest.raises(ConflictError):
        await commit(
            db,
            raw,
            raw["version"],
            {"remarks": "Must roll back"},
            {
                "source": "manual",
                "before": {"remarks": raw["remarks"]},
                "after": {"remarks": "Must roll back"},
            },
            owner,
            {},
        )
    assert await db.daily_follow_ups.find_one({"_id": raw["_id"]}) == raw


async def test_review_decisions_preserve_rejected_records_and_require_owner(
    workspace, client, mock_redis
):
    from app.config.database import get_database
    from app.features.auth.service import AuthService, RequestContext

    db, owner, employees, customer, _ = workspace
    ctx = RequestContext(ip_address="127.0.0.1", user_agent="synthetic")
    token = await AuthService(db, mock_redis).issue_session(
        user=owner, ctx=ctx, login_method="password"
    )
    client._transport.app.dependency_overrides[get_database] = lambda: db
    headers = {"Authorization": "Bearer " + token.access_token}
    record = {
        "_id": ObjectId(),
        "version": 1,
        "is_deleted": False,
        "import_key": "review-decision",
        "customer_name": customer.full_name,
        "customer_number": customer.mobile,
        "status": "DISBURSE",
        "history": [],
        "remarks": "Original note",
    }
    await db.daily_follow_ups.insert_one(record)
    base = "/api/v1/daily-operations/identity-review"
    report = await client.get(base + "/duplicates", headers=headers)
    assert report.status_code == 200 and report.json()["data"]["mode"] == "read_only"
    assert await db.daily_follow_ups.find_one({"_id": record["_id"]}) == record
    response = await client.post(
        f"{base}/{record['_id']}/decision",
        headers=headers,
        json={
            "version": 1,
            "decision": "reject_suggestion",
            "reason": "Owner rejected this synthetic suggestion",
        },
    )
    assert response.status_code == 200 and response.json()["data"]["record_unchanged"]
    assert await db.daily_follow_ups.find_one({"_id": record["_id"]}) == record
    response = await client.post(
        f"{base}/{record['_id']}/decision",
        headers=headers,
        json={
            "version": 1,
            "decision": "manual_review",
            "reason": "Owner requires further identity verification",
        },
    )
    assert response.status_code == 200
    reviewed = await db.daily_follow_ups.find_one({"_id": record["_id"]})
    assert (
        reviewed["identity_review_state"] == "pending"
        and reviewed["version"] == 2
        and reviewed["remarks"] == "Original note"
    )
    token = await AuthService(db, mock_redis).issue_session(
        user=employees[0][1], ctx=ctx, login_method="password"
    )
    headers = {"Authorization": "Bearer " + token.access_token}
    assert (await client.get(base + "/duplicates", headers=headers)).status_code == 403
    assert (
        await client.post(
            f"{base}/{record['_id']}/decision",
            headers=headers,
            json={
                "version": 2,
                "decision": "leave_standalone",
                "reason": "Unauthorized employee decision",
            },
        )
    ).status_code == 403
    assert await db.daily_follow_ups.find_one({"_id": record["_id"]}) == reviewed


async def test_owner_linked_sibling_applications_keep_independent_activity_keys(
    workspace,
):
    from app.features.daily_operations.identity import fingerprint

    db, owner, employees, customer, app = workspace
    original_app = await db.applications.find_one({"_id": ObjectId(app.id)})
    sibling = dict(original_app)
    sibling["_id"] = ObjectId()
    sibling["application_code"] = "SYNTHETIC-INDEPENDENT-APP"
    await db.applications.insert_one(sibling)
    records = []
    for index, application_id in enumerate([app.id, str(sibling["_id"])]):
        record = {
            "_id": ObjectId(),
            "version": 1,
            "is_deleted": False,
            "activity_key": fingerprint(["historical", index]),
            "import_key": f"synthetic-historical-activity-{index}",
            "activity_slot": "primary",
            "customer_name": customer.full_name,
            "customer_number": customer.mobile,
            "assigned_to": employees[0][0].id,
            "remarks": "Original historical note",
            "history": [
                {"source": "manual", "after": {"remarks": "Original historical note"}}
            ],
        }
        await db.daily_follow_ups.insert_one(record)
        report = await preview(db, owner)
        item = next(row for row in report["items"] if row["id"] == str(record["_id"]))
        await apply_link(
            db,
            owner,
            str(record["_id"]),
            IdentityDecision(
                version=1,
                customer_id=customer.id,
                application_id=application_id,
                confirmed=True,
                reason="Owner verified this separate application",
                preview_fingerprint=item["preview_fingerprint"],
            ),
        )
        records.append(record)
    service = DailyOperationsService(db)
    for record in records:
        await service.save(
            "follow-ups",
            FollowUpInput(
                date="2026-11-26",
                remarks_date="2026-11-26",
                customer_name=customer.full_name,
                customer_number=customer.mobile,
                assigned_to=employees[0][0].id,
                bank="Synthetic Bank",
                status="DISBURSE",
                remarks="Independent same-day activity",
            ),
            owner,
            record_id=str(record["_id"]),
            version=2,
        )
    rows = [
        await db.daily_follow_ups.find_one({"_id": record["_id"]}) for record in records
    ]
    assert len({row["activity_key"] for row in rows}) == 2
    assert len({row["working_key"] for row in rows}) == 2
    assert all(row["history"][0] == records[0]["history"][0] for row in rows)
    assert await db.daily_follow_ups.count_documents({}) == 2
    assert await db.applications.find_one({"_id": ObjectId(app.id)}) == original_app
    assert await db.applications.find_one({"_id": sibling["_id"]}) == sibling
