"""Real scoped task/history logic with mock Mongo. No telecom/model execution."""

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from bson import ObjectId

from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.features.auth.models import User
from app.features.customer.models import Customer
from app.features.employee.models import Employee
from app.features.leads.models import Lead
from app.features.reminders.models import Task
from app.features.reminders.schemas import UpdateTaskRequest
from app.features.reminders.service import RemindersService
from app.features.voice_assistant.callback_schemas import CallbackAction, CallbackInput
from app.features.voice_assistant.callback_service import CallbackService, ensure_callback_indexes
from app.features.workflow_engine.models import ApplicationWorkflow
from app.utils.datetime import utc_now


@pytest.fixture
async def callback_context(mock_db, owner_headers):
    await ensure_callback_indexes(mock_db)
    owner = User.model_validate(await mock_db.users.find_one({"role": "owner"}))
    user = User(mobile="9000000888", role="employee")
    user_id = str((await mock_db.users.insert_one(user.model_dump(by_alias=True, exclude={"id"}))).inserted_id)
    employee = Employee(user_id=user_id, employee_code="CB-TEST", first_name="Test", last_name="Supervisor", display_name="Test Supervisor", mobile=user.mobile, email="callback@example.test", department_id=str(ObjectId()), designation_id=str(ObjectId()), branch_id=str(ObjectId()), joining_date=utc_now(), employment_type="full_time")
    employee_id = str((await mock_db.employees.insert_one(employee.model_dump(by_alias=True, exclude={"id"}))).inserted_id)
    customer = Customer(customer_code="CB-CUSTOMER", user_id=str(ObjectId()), full_name="Synthetic callback fixture", mobile="9000000889")
    customer_id = str((await mock_db.customers.insert_one(customer.model_dump(by_alias=True, exclude={"id"}))).inserted_id)
    lead = Lead(lead_code="CB-LEAD", full_name="Synthetic callback fixture", mobile=customer.mobile, source_id=str(ObjectId()), product_category="loan", product_id=str(ObjectId()), customer_id=customer_id, assigned_to=employee_id, created_by=owner.require_id(), next_follow_up_date=utc_now() + timedelta(days=9))
    lead_id = str((await mock_db.leads.insert_one(lead.model_dump(by_alias=True, exclude={"id"}))).inserted_id)
    return CallbackService(mock_db), owner, employee_id, lead_id, customer_id, user_id


def request(context, **changes):
    _, _, employee, lead, _, _ = context
    values = {"entity_type": "lead", "entity_id": lead, "assigned_to": employee, "requested_local": (utc_now() + timedelta(days=1)).replace(tzinfo=None), "timezone": "UTC", "customer_request": "Please call tomorrow at the confirmed time.", "idempotency_key": uuid4().hex}
    return CallbackInput(**(values | changes))


async def test_callback_is_existing_task_and_preserves_business_followups(callback_context, mock_db):
    svc, actor, _, lead_id, _, _ = callback_context
    before = await mock_db.leads.find_one({"_id": ObjectId(lead_id)})
    result = await svc.create(request(callback_context), actor)
    task = await mock_db.tasks.find_one({"_id": ObjectId(result["id"])})
    assert task["related_entity_id"] == lead_id and task["voice_callback"]["state"] == "awaiting_confirmation"
    assert await mock_db.leads.find_one({"_id": ObjectId(lead_id)}) == before
    assert result["calls_placed"] == 0 and await mock_db.voice_calls.count_documents({}) == 0
    assert "Please call" not in task["description"]


async def test_idempotency_and_one_active_contact_across_entities(callback_context, mock_db):
    svc, actor, employee, _, customer, _ = callback_context
    payload = request(callback_context)
    first = await svc.create(payload, actor)
    assert (await svc.create(payload, actor))["id"] == first["id"]
    with pytest.raises(ConflictError):
        await svc.create(payload.model_copy(update={"customer_request": "Different request with the same key"}), actor)
    with pytest.raises(ConflictError):
        await svc.create(request(callback_context), actor)
    case = ApplicationWorkflow(case_code="CB-LOAN", case_type="loan", customer_id=customer, application_id=str(ObjectId()), product_id=str(ObjectId()), product_category="loan", current_status="new", moved_to_loan_management_at=utc_now(), assigned_to=employee)
    case_id = str((await mock_db.application_workflows.insert_one(case.model_dump(by_alias=True, exclude={"id"}))).inserted_id)
    with pytest.raises(ConflictError):
        await svc.create(request(callback_context, entity_type="loan_case", entity_id=case_id), actor)


async def test_confirmation_reschedule_and_cancel_preserve_all_history(callback_context):
    svc, actor, *_ = callback_context
    row = await svc.create(request(callback_context), actor)
    old_due = row["due_at"]
    row = await svc.action(row["id"], CallbackAction(version=row["version"], action="confirm", reason="Customer confirmed exact time"), actor)
    assert row["state"] == "scheduled" and row["confirmed_at"]
    row = await svc.action(row["id"], CallbackAction(version=row["version"], action="reschedule", reason="Customer changed preferred time", requested_local=(utc_now() + timedelta(days=2)).replace(tzinfo=None), timezone="UTC"), actor)
    assert row["state"] == "awaiting_confirmation" and row["confirmed_at"] is None
    row = await svc.action(row["id"], CallbackAction(version=row["version"], action="cancel", reason="Customer cancelled callback request"), actor)
    history = await svc.history(row["id"], actor, 1)
    assert history["total"] == 4 and history["items"][-1]["new_due_at"] == old_due
    assert history["items"][1]["old_due_at"] == old_due and "new_due_at" in history["items"][1]
    assert row["state"] == "cancelled" and row["calls_placed"] == 0


async def test_callback_versions_prevent_racing_reschedule_cancel(callback_context):
    svc, actor, *_ = callback_context
    row = await svc.create(request(callback_context), actor)
    outcomes = await asyncio.gather(svc.action(row["id"], CallbackAction(version=1, action="confirm", reason="Confirmed customer preference"), actor), svc.action(row["id"], CallbackAction(version=1, action="cancel", reason="Cancel request concurrently"), actor), return_exceptions=True)
    assert sum(isinstance(value, ConflictError) for value in outcomes) == 1


async def test_generic_task_routes_cannot_bypass_callback_history(callback_context):
    svc, actor, *_ = callback_context
    row = await svc.create(request(callback_context), actor)
    reminders = RemindersService(svc.db)
    with pytest.raises(ValidationError, match="linked AI callback"):
        await reminders.update_task(row["id"], UpdateTaskRequest(due_at=utc_now()), actor)
    with pytest.raises(ValidationError, match="actual call evidence"):
        await reminders.complete_task(row["id"], actor)
    normal = Task(title="Ordinary existing task", assigned_to=row["assigned_to"], assigned_by=actor.require_id(), due_at=utc_now())
    normal_id = str((await svc.db.tasks.insert_one(normal.model_dump(by_alias=True, exclude={"id"}))).inserted_id)
    assert (await reminders.complete_task(normal_id, actor)).status == "completed"


async def make_due(svc, row):
    await svc.db.tasks.update_one({"_id": ObjectId(row["id"])}, {"$set": {"due_at": utc_now() - timedelta(seconds=5), "voice_callback.next_review_at": utc_now() - timedelta(seconds=5)}})


async def test_due_worker_blocks_actual_dispatch_and_survives_repeat(callback_context):
    svc, actor, *_ = callback_context
    row = await svc.create(request(callback_context), actor)
    row = await svc.action(row["id"], CallbackAction(version=1, action="confirm", reason="Explicit time confirmation"), actor)
    await make_due(svc, row)
    assert await svc.sweep() == 1
    result = await svc.record(row["id"], actor)
    assert result["voice_callback"]["state"] == "blocked"
    assert "missing_or_expired_callback_consent" in result["voice_callback"]["blockers"]
    assert await svc.db.voice_calls.count_documents({}) == 0
    assert await svc.sweep() == 0


async def test_opt_out_closes_due_callback_without_dialing(callback_context):
    svc, actor, _, _, customer, _ = callback_context
    row = await svc.create(request(callback_context), actor)
    row = await svc.action(row["id"], CallbackAction(version=1, action="confirm", reason="Customer preference confirmed"), actor)
    await svc.db.voice_contact_suppressions.insert_one({"customer_id": customer, "scope": "global", "suppressed": True})
    await make_due(svc, row)
    await svc.sweep()
    result = await svc.record(row["id"], actor)
    assert result["voice_callback"]["state"] == "opted_out" and not result["voice_callback"]["active"]
    assert result["status"] == "completed"  # bookkeeping task closed, never a completed call
    assert await svc.db.voice_calls.count_documents({}) == 0


async def test_unconfirmed_requests_expire_without_a_call(callback_context):
    svc, actor, *_ = callback_context
    row = await svc.create(request(callback_context), actor)
    await make_due(svc, row)
    assert await svc.sweep() == 1
    stored = await svc.record(row["id"], actor)
    assert stored["voice_callback"]["state"] == "confirmation_expired"
    assert await svc.sweep() == 0 and await svc.db.voice_calls.count_documents({}) == 0


@pytest.mark.parametrize("kind", ["loan", "insurance"])
async def test_case_integration_uses_existing_workflow_relationship(callback_context, kind):
    svc, actor, employee, _, customer, _ = callback_context
    case = ApplicationWorkflow(case_code=f"CB-{kind}", case_type=kind, customer_id=customer, application_id=str(ObjectId()), product_id=str(ObjectId()), product_category=kind, current_status="new", moved_to_loan_management_at=utc_now() if kind == "loan" else None, assigned_to=employee)
    case_id = str((await svc.db.application_workflows.insert_one(case.model_dump(by_alias=True, exclude={"id"}))).inserted_id)
    row = await svc.create(request(callback_context, entity_type=f"{kind}_case", entity_id=case_id), actor)
    assert row["customer_id"] == customer and row["entity_id"] == case_id


async def test_http_permissions_validation_and_no_secrets(client, callback_context, owner_headers, employee_headers):
    svc, actor, _, lead, *_ = callback_context
    base = "/api/v1/voice-assistant/callbacks"
    assert (await client.get(f"{base}?entity_type=lead&entity_id={lead}", headers=employee_headers)).status_code == 403
    assert (await client.post(base, json=request(callback_context).model_dump(mode="json"), headers=owner_headers)).status_code == 200
    result = await client.get(f"{base}?entity_type=lead&entity_id={lead}", headers=owner_headers)
    assert result.json()["data"]["total"] == 1
    assert "input_hash" not in result.text and "idempotency_key" not in result.text
    assert (await client.get(f"{base}?entity_type=lead&entity_id=BAD", headers=owner_headers)).status_code == 422


async def test_cross_record_scope_denied_even_with_voice_permissions(callback_context, monkeypatch):
    svc, owner, _, _, _, staff_user = callback_context
    row = await svc.create(request(callback_context), owner)
    employee = User.model_validate(await svc.db.users.find_one({"_id": ObjectId(staff_user)}))
    async def granted(*args, **kwargs):
        return True
    monkeypatch.setattr(svc.engine, "has_permission", granted)
    await svc.db.leads.update_one({"_id": ObjectId(row["entity_id"])}, {"$set": {"assigned_to": str(ObjectId())}})
    with pytest.raises(ForbiddenError):
        await svc.record(row["id"], employee)


async def test_dst_ambiguity_requires_explicit_occurrence(callback_context):
    svc, actor, *_ = callback_context
    with pytest.raises(ValidationError, match="ambiguous"):
        await svc.create(request(callback_context, requested_local="2026-11-01T01:30:00", timezone="America/New_York"), actor)


async def test_environment_separation_and_cancelled_slot_reuse(callback_context):
    svc, actor, *_ = callback_context
    first = await svc.create(request(callback_context), actor)
    production = await svc.create(request(callback_context, environment="production"), actor)
    assert first["id"] != production["id"]
    assert (await svc.list("lead", first["entity_id"], "test", actor))["total"] == 1
    await svc.action(first["id"], CallbackAction(version=1, action="cancel", reason="Customer cancelled original time"), actor)
    replacement = await svc.create(request(callback_context), actor)
    assert replacement["id"] != first["id"] and (await svc.history(first["id"], actor, 1))["total"] == 2


async def test_active_opt_out_blocks_creation_and_reschedule(callback_context):
    svc, actor, _, _, customer, _ = callback_context
    row = await svc.create(request(callback_context), actor)
    await svc.db.voice_contact_suppressions.insert_one({"customer_id": customer, "scope": "global", "suppressed": True})
    with pytest.raises(ForbiddenError, match="do-not-call"):
        await svc.action(row["id"], CallbackAction(version=1, action="confirm", reason="Cannot override contact restriction"), actor)
    await svc.action(row["id"], CallbackAction(version=1, action="cancel", reason="Honor requested opt-out"), actor)
    with pytest.raises(ForbiddenError, match="do-not-call"):
        await svc.create(request(callback_context), actor)


async def test_disabled_creator_and_changed_binding_fail_closed(callback_context):
    svc, actor, *_ = callback_context
    row = await svc.create(request(callback_context), actor)
    row = await svc.action(row["id"], CallbackAction(version=1, action="confirm", reason="Customer time attestation"), actor)
    await make_due(svc, row)
    await svc.db.users.update_one({"_id": ObjectId(actor.require_id())}, {"$set": {"status": "disabled"}})
    assert await svc.sweep() == 1
    stored = await svc.db.tasks.find_one({"_id": ObjectId(row["id"])})
    assert "current_record_or_staff_authorization_failed" in stored["voice_callback"]["blockers"]
    assert await svc.db.voice_calls.count_documents({}) == 0


async def test_spoofed_source_call_is_rejected(callback_context):
    svc, actor, _, _, customer, _ = callback_context
    source = str((await svc.db.voice_calls.insert_one({"is_deleted": False, "customer_id": customer, "provider": "mock", "environment": "test", "owner_user_id": actor.require_id()})).inserted_id)
    with pytest.raises(ValidationError, match="Source call"):
        await svc.create(request(callback_context, source_call_id=source), actor)


async def test_readiness_recovery_uses_same_durable_task(callback_context):
    svc, actor, *_ = callback_context
    row = await svc.create(request(callback_context), actor)
    row = await svc.action(row["id"], CallbackAction(version=1, action="confirm", reason="Time explicitly confirmed"), actor)
    await make_due(svc, row)
    from app.worker.tasks.voice_assistant import review_voice_callbacks
    assert await review_voice_callbacks({"voice_db": svc.db}) == 1
    stored = await svc.record(row["id"], actor)
    assert stored["voice_callback"]["state"] == "blocked"
    assert await svc.db.tasks.count_documents({"voice_callback.active": True}) == 1


async def test_reschedule_keeps_original_local_timezone_and_fold(callback_context, monkeypatch):
    from datetime import UTC, datetime
    from app.features.voice_assistant import callback_service
    monkeypatch.setattr(callback_service, "utc_now", lambda: datetime(2026, 10, 16, tzinfo=UTC))
    svc, actor, *_ = callback_context
    row = await svc.create(request(callback_context, requested_local="2026-11-01T01:30:00", timezone="America/New_York", dst_fold=1), actor)
    row = await svc.action(row["id"], CallbackAction(version=1, action="reschedule", reason="Customer changed the time zone", requested_local=datetime(2026, 11, 2, 11), timezone="Asia/Kolkata"), actor)
    history = await svc.history(row["id"], actor, 1)
    original = history["items"][-1]
    changed = history["items"][0]
    assert original["new_requested_local"] == "2026-11-01T01:30:00" and original["new_timezone"] == "America/New_York" and original["new_dst_fold"] == 1
    assert changed["old_timezone"] == "America/New_York" and changed["old_dst_fold"] == 1 and changed["new_timezone"] == "Asia/Kolkata"


@pytest.mark.parametrize("failure", ["parent_deleted", "parent_purged", "creator_revoked", "supervisor_revoked", "binding_changed", "customer_deleted"])
async def test_lost_authority_closes_and_releases_contact_slot(callback_context, failure):
    svc, actor, _, lead, customer, supervisor = callback_context
    row = await svc.create(request(callback_context), actor)
    await make_due(svc, row)
    if failure == "parent_deleted":
        await svc.db.leads.update_one({"_id": ObjectId(lead)}, {"$set": {"is_deleted": True}})
    elif failure == "parent_purged":
        await svc.db.leads.delete_one({"_id": ObjectId(lead)})
    elif failure == "creator_revoked":
        await svc.db.users.update_one({"_id": ObjectId(actor.require_id())}, {"$set": {"status": "disabled"}})
    elif failure == "supervisor_revoked":
        await svc.db.users.update_one({"_id": ObjectId(supervisor)}, {"$set": {"status": "disabled"}})
    elif failure == "binding_changed":
        await svc.db.leads.update_one({"_id": ObjectId(lead)}, {"$set": {"customer_id": str(ObjectId())}})
    else:
        await svc.db.customers.update_one({"_id": ObjectId(customer)}, {"$set": {"is_deleted": True}})
    await svc.sweep()
    stored = await svc.db.tasks.find_one({"_id": ObjectId(row["id"])})
    assert stored["voice_callback"]["state"] == "closed_ineligible"
    assert not stored["voice_callback"]["active"]
    assert stored["voice_callback"]["history"][0]["event"] == "requested"
    assert await svc.db.tasks.count_documents({"voice_callback.active": True}) == 0
    assert await svc.sweep() == 0
    assert await svc.db.voice_calls.count_documents({}) == 0


async def test_expired_callback_rechecks_suppression_and_owner_can_close_orphan(callback_context):
    svc, actor, _, lead, customer, _ = callback_context
    row = await svc.create(request(callback_context), actor)
    await make_due(svc, row)
    await svc.sweep()
    stored = await svc.db.tasks.find_one({"_id": ObjectId(row["id"])})
    await svc.db.voice_contact_suppressions.insert_one({"customer_id": customer, "scope": "global", "suppressed": True})
    await make_due(svc, row)
    await svc.sweep()
    stored = await svc.db.tasks.find_one({"_id": ObjectId(row["id"])})
    assert stored["voice_callback"]["state"] == "opted_out" and not stored["voice_callback"]["active"]
    await svc.db.voice_contact_suppressions.delete_many({})
    replacement = await svc.create(request(callback_context), actor)
    await svc.db.leads.delete_one({"_id": ObjectId(lead)})
    payload = CallbackAction(version=replacement["version"], action="cancel", reason="Parent purged; retain history and close request")
    resolved = await svc.resolve_owner(replacement["id"], payload, actor)
    assert resolved["state"] == "cancelled" and "customer_request" not in resolved
    with pytest.raises(ConflictError):
        await svc.resolve_owner(replacement["id"], payload, actor)


async def test_owner_resolution_cannot_adopt_authority_or_allow_staff(callback_context):
    svc, actor, _, _, _, staff_id = callback_context
    row = await svc.create(request(callback_context), actor)
    staff = User.model_validate(await svc.db.users.find_one({"_id": ObjectId(staff_id)}))
    with pytest.raises(ForbiddenError):
        await svc.resolve_owner(row["id"], CallbackAction(version=1, action="cancel", reason="Unauthorized staff resolution"), staff)
    with pytest.raises(ValidationError):
        await svc.resolve_owner(row["id"], CallbackAction(version=1, action="confirm", reason="Cannot adopt original authority"), actor)


async def test_audit_failure_repaired_by_idempotent_replay_and_worker(callback_context, monkeypatch):
    svc, actor, *_ = callback_context
    payload = request(callback_context)
    original = svc.audit
    async def unavailable(*args, **kwargs):
        raise RuntimeError("Synthetic audit outage")
    monkeypatch.setattr(svc, "audit", unavailable)
    with pytest.raises(RuntimeError, match="Synthetic audit outage"):
        await svc.create(payload, actor)
    doc = await svc.db.tasks.find_one({"voice_callback.idempotency_key": payload.idempotency_key})
    assert doc["voice_callback"]["audit_pending"] and len(doc["voice_callback"]["history"]) == 1
    monkeypatch.setattr(svc, "audit", original)
    replay = await svc.create(payload, actor)
    assert replay["id"] == str(doc["_id"])
    assert await svc.db.audit_logs.count_documents({"metadata.task_id": replay["id"]}) == 1
    await svc.db.tasks.update_one({"_id": doc["_id"]}, {"$set": {"voice_callback.audit_pending": True}})
    await asyncio.gather(svc.reconcile_audit(), svc.reconcile_audit())
    assert await svc.db.audit_logs.count_documents({"metadata.task_id": replay["id"]}) == 1
    assert not (await svc.db.tasks.find_one({"_id": doc["_id"]}))["voice_callback"]["audit_pending"]


@pytest.mark.parametrize("purpose,eligible", [("callback", True), ("service_callback", False), ("marketing", False)])
async def test_callback_consent_has_explicit_purpose_compatibility(callback_context, purpose, eligible):
    svc, actor, _, _, customer, _ = callback_context
    row = await svc.create(request(callback_context), actor)
    await svc.action(row["id"], CallbackAction(version=1, action="confirm", reason="Confirmed exact request time"), actor)
    await svc.db.voice_contact_consents.insert_one({"customer_id": customer, "purpose": purpose, "action": "grant", "expires_at": utc_now() + timedelta(days=1)})
    await make_due(svc, row)
    await svc.sweep()
    stored = await svc.db.tasks.find_one({"_id": ObjectId(row["id"])})
    assert ("missing_or_expired_callback_consent" not in stored["voice_callback"]["blockers"]) is eligible
    assert await svc.db.voice_calls.count_documents({}) == 0


async def test_audit_reconciliation_detects_integrity_conflict_without_overwrite(callback_context):
    svc, actor, *_ = callback_context
    row = await svc.create(request(callback_context), actor)
    audit = await svc.db.audit_logs.find_one({"metadata.task_id": row["id"]})
    await svc.db.audit_logs.update_one({"_id": audit["_id"]}, {"$set": {"user_id": "synthetic-corruption"}})
    await svc.db.tasks.update_one({"_id": ObjectId(row["id"])}, {"$set": {"voice_callback.audit_pending": True}})
    with pytest.raises(ConflictError, match="integrity"):
        await svc.reconcile_audit()
    assert (await svc.db.audit_logs.find_one({"_id": audit["_id"]}))["user_id"] == "synthetic-corruption"
    assert (await svc.db.tasks.find_one({"_id": ObjectId(row["id"])}))["voice_callback"]["audit_pending"]
