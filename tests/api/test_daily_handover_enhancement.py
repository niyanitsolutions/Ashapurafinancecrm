# ruff: noqa: F811
"""Real disposable replica-set checks; no external transport or production data."""

import asyncio

import pytest
from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.features.daily_operations.catalog import install_catalog
from app.features.daily_operations.handover import (
    Reference,
    TransferRequest,
    history,
    queue,
    transfer,
)
from app.features.daily_operations.linked import OpenLinkedRequest, open_linked
from app.features.daily_operations.service import DailyOperationsService
from app.features.loan_management.schemas import DisburseRequest, ScheduleTopUpRequest
from app.features.loan_management.service import LoanCaseService
from app.features.workflow_engine.models import ApplicationWorkflow, LoanCaseDetails
from app.utils.datetime import utc_now
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from test_case_status_control import _seed_workflow_definitions
from test_pin_mongo_integration import pin_mongo  # noqa: F401
from test_unified_operations import insert, seed_identity, seed_team


@pytest.fixture
async def environment(pin_mongo):
    db = pin_mongo
    await install_catalog(db)
    owner, employees = await seed_team(db)
    await db.permissions.update_many({}, {"$addToSet": {"actions": "assign"}})
    await db.role_permissions.update_many(
        {}, {"$addToSet": {"granted_actions": "assign"}}
    )
    # Explicitly grant Daily handover; it is never a default Employee capability.
    permission = await db.permissions.find_one(
        {"module": "daily_operations", "resource": "follow-ups"}
    )
    for employee, _ in employees:
        role = await db.employee_roles.find_one({"employee_id": employee.id})
        await db.role_permissions.insert_one(
            {
                "role_id": role["role_id"],
                "permission_id": str(permission["_id"]),
                "granted_actions": ["assign"],
                "is_deleted": False,
            }
        )
    customer, app = await seed_identity(db, "Synthetic Transfer Customer")
    await db.applications.update_one(
        {"_id": ObjectId(app.id)}, {"$set": {"assigned_to": employees[0][0].id}}
    )
    return db, owner, employees, customer, app


async def workspace(environment, move=False):
    db, owner, _, _, app = environment
    return await open_linked(
        DailyOperationsService(db),
        OpenLinkedRequest(entity="application", record_id=app.id),
        owner,
        move=move,
    )


async def loan(environment):
    db, _, employees, customer, app = environment
    await _seed_workflow_definitions(db)
    case = ApplicationWorkflow(
        case_code="SYNTHETIC-LOAN",
        case_type="loan",
        application_id=app.id,
        customer_id=customer.id,
        product_id=app.product_id,
        product_category="loan",
        assigned_to=employees[0][0].id,
        current_status="send_for_disbursement",
        loan_details=LoanCaseDetails(offered_amount=100000),
        moved_to_loan_management_at=utc_now(),
    )
    case.id = await insert(db, "application_workflows", case)
    return case


def request(row, eid, key="synthetic-transfer-key-0001", collection="applications"):
    return TransferRequest(
        records=[
            Reference(
                collection=collection, id=str(row["_id"]), version=row.get("version", 1)
            )
        ],
        employee_id=eid,
        request_id=key,
        remarks="Synthetic workload handover",
    )


@pytest.mark.parametrize(
    "verification", ["pending", "verified", "rejected", "not_available"]
)
async def test_movement_preserves_original_documents_and_identity(
    environment, verification
):
    db, _owner, _, _customer, app = environment
    document = {
        "application_id": app.id,
        "verification_status": "pending"
        if verification == "not_available"
        else verification,
        "document_status": "not_available"
        if verification == "not_available"
        else "uploaded",
        "s3_key": "synthetic-only",
        "is_current": True,
    }
    oid = (await db.application_documents.insert_one(document)).inserted_id
    required_ids = [str(ObjectId()) for _ in range(5)]
    await db.application_form_definitions.update_one(
        {"_id": ObjectId(app.form_definition_id)},
        {
            "$set": {
                "required_documents": [
                    {"document_type_id": i, "required": True} for i in required_ids
                ]
            }
        },
    )
    await db.application_documents.update_one(
        {"_id": oid}, {"$set": {"document_type_id": required_ids[0]}}
    )
    document["document_type_id"] = required_ids[0]
    for doc_id in required_ids[1:]:
        await db.application_documents.insert_one(
            {
                **{k: v for k, v in document.items() if k != "_id"},
                "document_type_id": doc_id,
            }
        )
    before = await db.applications.find_one({"_id": ObjectId(app.id)})
    first = await workspace(environment, True)
    again = await workspace(environment, True)
    after = await db.applications.find_one({"_id": ObjectId(app.id)})
    assert first["id"] == again["id"]
    assert all(
        after[k] == before[k]
        for k in ("form_data", "customer_id", "status", "user_id", "assigned_to")
    )
    assert after["daily_followup_moved_at"]
    assert await db.application_documents.find_one({"_id": oid}) == {
        **document,
        "_id": oid,
    }
    assert (
        await db.audit_logs.count_documents(
            {"event_type": "application_moved_to_daily_followup"}
        )
        == 1
    )
    assert await db.application_workflows.count_documents({}) == 0


async def test_movement_audit_failure_rolls_back_every_write(environment):
    db, _, _, _, app = environment
    await db.audit_logs.create_index("event_type", unique=True)
    await db.audit_logs.insert_one(
        {"event_type": "application_moved_to_daily_followup"}
    )
    with pytest.raises((ConflictError, DuplicateKeyError)):
        await workspace(environment, True)
    assert await db.daily_follow_ups.count_documents({}) == 0
    assert not (await db.applications.find_one({"_id": ObjectId(app.id)})).get(
        "daily_followup_moved_at"
    )


async def test_transfer_repeated_chain_preserves_ids_history_and_exclusive_access(
    environment,
):
    db, _owner, employees, _, app = environment
    w = await workspace(environment)
    original = await db.daily_follow_ups.find_one({"_id": ObjectId(w["id"])})
    for i, (sender, recipient) in enumerate([(0, 1), (1, 0), (0, 2)]):
        row = await db.applications.find_one({"_id": ObjectId(app.id)})
        body = request(row, employees[recipient][0].id, f"synthetic-chain-key-{i:04d}")
        result = await transfer(db, employees[sender][1], body)
        assert await transfer(db, employees[sender][1], body) == result
        with pytest.raises(ForbiddenError):
            await DailyOperationsService(db).get(
                "follow-ups", w["id"], employees[sender][1]
            )
        received = await DailyOperationsService(db).get(
            "follow-ups", w["id"], employees[recipient][1]
        )
        assert received["assigned_to"] == employees[recipient][0].id
        active = await queue(db, employees[recipient][1])
        assert any(r["id"] == app.id and r["can_work"] for r in active["items"])
    current = await db.daily_follow_ups.find_one({"_id": original["_id"]})
    assert current["history"] == original["history"]
    assert await db.applications.count_documents({}) == 1
    assert (
        len((await history(db, employees[0][1], "applications", app.id))["items"]) == 3
    )
    assert (
        await db.audit_logs.count_documents({"event_type": "crm_record_transferred"})
        == 6
    )


async def test_transfer_invalid_receiver_or_stale_version_changes_nothing(environment):
    db, owner, employees, _, app = environment
    row = await db.applications.find_one({"_id": ObjectId(app.id)})
    await db.employees.update_one(
        {"_id": ObjectId(employees[1][0].id)}, {"$set": {"status": "inactive"}}
    )
    with pytest.raises(ValidationError):
        await transfer(db, owner, request(row, employees[1][0].id))
    with pytest.raises(ConflictError):
        await transfer(db, owner, request({**row, "version": 2}, employees[2][0].id))
    with pytest.raises(ForbiddenError):
        await transfer(db, employees[1][1], request(row, employees[2][0].id))
    assert await db.applications.find_one({"_id": row["_id"]}) == row
    assert (
        await db.audit_logs.count_documents({"event_type": "crm_record_transferred"})
        == 0
    )


async def test_concurrent_transfer_has_one_winner(environment):
    db, owner, employees, _, app = environment
    row = await db.applications.find_one({"_id": ObjectId(app.id)})
    results = await asyncio.gather(
        *(
            transfer(
                db, owner, request(row, employees[i][0].id, f"synthetic-concurrent-{i}")
            )
            for i in [1, 2]
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(r, dict) for r in results) == 1
    assert all(isinstance(r, (dict, ConflictError)) for r in results)
    assert (
        await db.audit_logs.count_documents({"event_type": "crm_record_transferred"})
        == 1
    )


async def test_bulk_failure_has_no_partial_transfer(environment):
    db, owner, employees, _, app = environment
    row = await db.applications.find_one({"_id": ObjectId(app.id)})
    clone = {**row, "_id": ObjectId(), "application_code": "SYNTHETIC-SECOND"}
    await db.applications.insert_one(clone)
    await db.audit_logs.create_index("event_type", unique=True)
    body = request(row, employees[1][0].id)
    body.records.append(
        Reference(collection="applications", id=str(clone["_id"]), version=1)
    )
    with pytest.raises(ConflictError):
        await transfer(db, owner, body)
    assert await db.applications.find_one({"_id": row["_id"]}) == row
    assert await db.applications.find_one({"_id": clone["_id"]}) == clone
    assert (
        await db.audit_logs.count_documents({"event_type": "crm_transfer_batch"}) == 0
    )


async def test_disbursement_shared_ledger_and_workspace_are_atomic(environment):
    db, owner, _, _, _app = environment
    case = await loan(environment)
    w = await workspace(environment)
    result = await LoanCaseService(db).disburse(
        case.id,
        DisburseRequest(
            approved_amount=100000,
            disbursed_amount=90000,
            disbursed_reference="SYNTHETIC-REF",
            disbursement_date="2026-11-26",
            remarks="Synthetic disbursement",
        ),
        owner,
    )
    assert (
        result.current_status == "disbursed"
        and result.loan_details.disbursed_amount == 90000
    )
    row = await db.daily_follow_ups.find_one({"_id": ObjectId(w["id"])})
    assert (
        row["status"] == "DISBURSE"
        and row["history"][-1]["source"] == "loan_disbursement"
    )
    assert (
        await db.application_status_history.count_documents(
            {"application_workflow_id": case.id, "to_status": "disbursed"}
        )
        == 1
    )
    with pytest.raises(ConflictError):
        await LoanCaseService(db).disburse(
            case.id,
            DisburseRequest(
                disbursed_amount=90000, disbursed_reference="SYNTHETIC-REF"
            ),
            owner,
        )


async def test_disbursement_audit_failure_rolls_back_case_and_followup(environment):
    db, owner, _, _, _ = environment
    case = await loan(environment)
    w = await workspace(environment)
    before_case = await db.application_workflows.find_one({"_id": ObjectId(case.id)})
    before_follow = await db.daily_follow_ups.find_one({"_id": ObjectId(w["id"])})
    await db.audit_logs.create_index("event_type", unique=True)
    await db.audit_logs.insert_one({"event_type": "daily_followup_disbursed"})
    with pytest.raises((ConflictError, DuplicateKeyError)):
        await LoanCaseService(db).disburse(
            case.id,
            DisburseRequest(disbursed_amount=90000, disbursed_reference="SYNTHETIC"),
            owner,
        )
    assert (
        await db.application_workflows.find_one({"_id": ObjectId(case.id)})
        == before_case
    )
    assert (
        await db.daily_follow_ups.find_one({"_id": ObjectId(w["id"])}) == before_follow
    )


async def test_topup_uses_same_case_note_and_retry_receipt(environment):
    db, owner, _, _, _ = environment
    case = await loan(environment)
    await LoanCaseService(db).disburse(
        case.id,
        DisburseRequest(disbursed_amount=90000, disbursed_reference="SYNTHETIC"),
        owner,
    )
    body = ScheduleTopUpRequest(
        period="3_months",
        remarks="Synthetic top-up",
        request_id="synthetic-topup-idempotency",
    )
    first = await LoanCaseService(db).schedule_top_up(case.id, body, owner)
    second = await LoanCaseService(db).schedule_top_up(case.id, body, owner)
    assert (
        first.loan_details.top_up_eligibility_date
        == second.loan_details.top_up_eligibility_date
    )
    assert (
        await db.application_notes.count_documents({"application_workflow_id": case.id})
        == 1
    )
    assert await db.application_workflows.count_documents({}) == 1


@pytest.mark.parametrize("amount", [0, -1, 100001, 90000.001])
async def test_disbursement_invalid_amount_never_changes_case(environment, amount):
    db, owner, _, _, _ = environment
    case = await loan(environment)
    with pytest.raises((ValueError, ValidationError)):
        await LoanCaseService(db).disburse(
            case.id,
            DisburseRequest(disbursed_amount=amount, disbursed_reference="SYNTHETIC"),
            owner,
        )
    assert (await db.application_workflows.find_one({"_id": ObjectId(case.id)}))[
        "current_status"
    ] == "send_for_disbursement"


async def test_ten_leads_partial_return_and_third_employee_chain(environment):
    from app.features.leads.models import Lead
    from app.features.leads.service import LeadService

    db, owner, employees, _, app = environment
    ids = []
    for index in range(10):
        lead = Lead(
            lead_code=f"SYNTHETIC-TEN-{index}",
            full_name=f"Synthetic Prospect {index}",
            mobile=f"900060{index:04d}",
            source_id=str(ObjectId()),
            product_category="loan",
            product_id=app.product_id,
            assigned_to=employees[0][0].id,
            stage="assigned",
        )
        ids.append(await insert(db, "leads", lead))

    async def send(sender, recipient, selected, key):
        rows = await db.leads.find(
            {"_id": {"$in": [ObjectId(i) for i in selected]}}
        ).to_list(10)
        return await transfer(
            db,
            employees[sender][1],
            TransferRequest(
                records=[
                    Reference(
                        collection="leads", id=str(r["_id"]), version=r["version"]
                    )
                    for r in rows
                ],
                employee_id=employees[recipient][0].id,
                request_id=key,
            ),
        )

    await send(0, 1, ids, "synthetic-ten-first-batch")
    received = await queue(db, employees[1][1])
    assert received["total"] == 10 and all(r["can_work"] for r in received["items"])
    for rid in ids[:5]:
        # Existing Lead follow-up service writes its own append-only note/activity.
        await LeadService(db).set_follow_up(
            rid, utc_now().date(), "Synthetic worked lead", employees[1][1]
        )
    await send(1, 0, ids[5:], "synthetic-ten-return-batch")
    assert await db.leads.count_documents({"assigned_to": employees[1][0].id}) == 5
    assert await db.leads.count_documents({"assigned_to": employees[0][0].id}) == 5
    await send(0, 2, ids[5:7], "synthetic-ten-third-batch")
    for rid in ids[5:7]:
        with pytest.raises(ForbiddenError):
            await LeadService(db).get_lead_scoped(rid, employees[0][1])
        assert (await LeadService(db).get_lead_scoped(rid, employees[2][1])).id == rid
        assert len((await history(db, owner, "leads", rid))["items"]) == 3
    assert await db.leads.count_documents({}) == 10


async def test_metrics_count_persisted_case_once_and_scope_employee(environment):
    from app.features.dashboard.filters import resolve_dashboard_filters
    from app.features.dashboard.followup_metrics import summary

    db, owner, employees, _, _ = environment
    case = await loan(environment)
    await workspace(environment)
    await LoanCaseService(db).disburse(
        case.id,
        DisburseRequest(disbursed_amount=90000, disbursed_reference="SYNTHETIC"),
        owner,
    )
    filters = resolve_dashboard_filters(
        date_range="this_month",
        start_date=None,
        end_date=None,
        product_category=None,
        source_id=None,
    )
    result = await summary(db, owner, filters)
    assert (
        result["metrics"]["disbursed_cases"] == 1
        and result["metrics"]["disbursed_amount"] == 90000
    )
    assert result["metrics"]["approved_amount"] == 100000
    other = await summary(db, employees[1][1], filters)
    assert (
        other["metrics"]["disbursed_cases"] == 0 and other["metrics"]["followups"] == 0
    )


async def test_previous_participant_has_history_without_record_access_and_unrelated_staff_forbidden(
    environment,
):
    db, owner, employees, _, app = environment
    row = await db.applications.find_one({"_id": ObjectId(app.id)})
    await transfer(db, owner, request(row, employees[1][0].id))
    assert (await history(db, employees[0][1], "applications", app.id))["items"]
    with pytest.raises(ForbiddenError):
        await history(db, employees[2][1], "applications", app.id)
    assert (await queue(db, employees[2][1]))["total"] == 0


async def test_open_after_existing_disbursement_has_consistent_followup_status(
    environment,
):
    db, owner, _, _, _ = environment
    case = await loan(environment)
    await LoanCaseService(db).disburse(
        case.id,
        DisburseRequest(disbursed_amount=90000, disbursed_reference="SYNTHETIC"),
        owner,
    )
    row = await workspace(environment)
    assert row["status"] == "DISBURSE" and row["due_date"] is None
    assert await db.application_workflows.count_documents({}) == 1


async def test_owner_self_assignment_and_employee_membership_receiver_keep_identity(
    environment,
):
    from app.features.auth.repository import UserRepository
    from app.features.customer.service import CustomerService
    from app.features.daily_operations.handover import ReceiverQuery, eligible_receivers

    db, owner, employees, _, app = environment
    row = await db.applications.find_one({"_id": ObjectId(app.id)})
    body = request(row, owner.id, "synthetic-owner-self-assignment")
    options = await eligible_receivers(db, owner, ReceiverQuery(records=body.records))
    assert any(r["id"] == owner.id for r in options["items"])
    await transfer(db, owner, body)
    _, _, names = await LoanCaseService(db).resolve_names([])
    assert not names
    from app.features.customer.models import Application

    actual = Application.model_validate(
        await db.applications.find_one({"_id": row["_id"]})
    )
    _, _, names = await CustomerService(db, None).resolve_names_for_applications(
        [actual]
    )
    assert names[owner.id] == "Owner"
    target = employees[1][1]
    await db.users.update_one(
        {"_id": ObjectId(target.id)},
        {
            "$set": {
                "role": "customer",
                "pin_hash": "synthetic-existing-pin-hash",
                "employee_access": {
                    "enabled": True,
                    "password_hash": "synthetic-employee-hash",
                },
            }
        },
    )
    before = await db.users.find_one({"_id": ObjectId(target.id)})
    current = await db.applications.find_one({"_id": row["_id"]})
    await transfer(
        db,
        owner,
        request(current, employees[1][0].id, "synthetic-added-employee-transfer"),
    )
    after = await db.users.find_one({"_id": ObjectId(target.id)})
    assert after["role"] == "customer" and after["pin_hash"] == before["pin_hash"]
    assert after["employee_access"] == before["employee_access"]
    assert (await UserRepository(db).find_by_id(target.id)).role == "customer"


async def test_additive_catalog_and_indexes_preserve_historical_records(environment):
    db, _, _, _, app = environment
    legacy = {
        "event_type": "synthetic_legacy_assignment",
        "metadata": {"record_id": app.id},
        "created_at": utc_now(),
    }
    oid = (await db.audit_logs.insert_one(legacy)).inserted_id
    legacy_before = await db.audit_logs.find_one({"_id": oid})
    before = await db.applications.find_one({"_id": ObjectId(app.id)})
    await install_catalog(db)
    await install_catalog(db)
    assert await db.applications.find_one({"_id": before["_id"]}) == before
    assert await db.audit_logs.find_one({"_id": oid}) == legacy_before
    assert (
        await db.audit_logs.count_documents({"event_type": "crm_record_transferred"})
        == 0
    )
    indexes = await db.audit_logs.index_information()
    for name in ["handover_from_employee_id", "handover_to_employee_id"]:
        assert not indexes[name].get("unique", False)
        assert indexes[name]["partialFilterExpression"]["metadata.primary"] is True
    users = await db.users.index_information()
    assert users["mobile_1"]["unique"] is True


async def test_daily_disbursement_api_returns_safe_serializable_history(
    environment, client, mock_redis
):
    from app.config.database import get_database
    from app.features.auth.service import AuthService, RequestContext

    db, owner, _, _, _ = environment
    await loan(environment)
    opened = await workspace(environment)
    client._transport.app.dependency_overrides[get_database] = lambda: db
    token = await AuthService(db, mock_redis).issue_session(
        user=owner,
        ctx=RequestContext(ip_address="127.0.0.1", user_agent="synthetic"),
        login_method="password",
    )
    headers = {"Authorization": "Bearer " + token.access_token}
    url = "/api/v1/daily-operations/follow-ups/" + opened["id"]
    current = (await client.get(url, headers=headers)).json()["data"]
    response = await client.post(
        url + "/disburse",
        headers=headers,
        json={
            "followup": {
                "version": current["version"],
                "date": "2026-11-26",
                "remarks_date": "2026-11-26",
                "customer_name": current["customer_name"],
                "customer_number": current["customer_number"],
                "status": "DISBURSE",
                "bank": "Synthetic API Bank",
                "remarks": "Synthetic API disbursement",
            },
            "details": {
                "approved_amount": 100000,
                "disbursed_amount": 90000,
                "disbursed_reference": "SYNTHETIC-API",
                "disbursement_date": "2026-11-26",
                "remarks": "Synthetic API disbursement",
            },
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "DISBURSE" and data["disbursed_amount"] == 90000
    assert "case_oid" not in data["history"][-1]["after"]
    assert isinstance(data["history"][-1]["after"]["case_id"], str)


async def test_financial_context_requires_current_loan_view_permission(environment):
    db, owner, employees, _, _ = environment
    case = await loan(environment)
    opened = await workspace(environment)
    await LoanCaseService(db).disburse(
        case.id,
        DisburseRequest(disbursed_amount=90000, disbursed_reference="SYNTHETIC"),
        owner,
    )
    permission = await db.permissions.find_one(
        {"module": "loan_management", "resource": "applications"}
    )
    role = await db.employee_roles.find_one({"employee_id": employees[0][0].id})
    await db.role_permissions.update_one(
        {"role_id": role["role_id"], "permission_id": str(permission["_id"])},
        {"$set": {"granted_actions": []}},
    )
    hidden = await DailyOperationsService(db).get(
        "follow-ups", opened["id"], employees[0][1]
    )
    assert hidden["disbursed_amount"] is None and hidden["approved_amount"] is None
    visible = await DailyOperationsService(db).get("follow-ups", opened["id"], owner)
    assert visible["disbursed_amount"] == 90000


async def test_topup_calendar_uses_ist_month_end_for_explicit_disbursement_date(
    environment,
):
    from app.utils.datetime import to_ist

    db, owner, _, _, _ = environment
    case = await loan(environment)
    await LoanCaseService(db).disburse(
        case.id,
        DisburseRequest(
            disbursed_amount=90000,
            disbursed_reference="SYNTHETIC",
            disbursement_date="2026-01-31",
        ),
        owner,
    )
    result = await LoanCaseService(db).schedule_top_up(
        case.id,
        ScheduleTopUpRequest(period="3_months", remarks="Synthetic calendar test"),
        owner,
    )
    assert (
        to_ist(result.loan_details.top_up_eligibility_date).date().isoformat()
        == "2026-04-30"
    )
