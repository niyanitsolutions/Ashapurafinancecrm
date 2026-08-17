"""Final Phase — regression coverage for Phase 4's dashboard widget providers, focused
on the security-relevant property that was previously only checked by ad-hoc scratch
scripts: an Employee's widget data is always scoped to their own assignments, never
company-wide, while Owner sees everything. Also covers the "honest unavailable, never a
fabricated number" contract for widgets with no real data yet.
"""

from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

from app.constants.roles import EMPLOYEE, OWNER
from app.features.auth.models import User
from app.features.dashboard.widget_providers import WIDGET_PROVIDERS


async def _seed_employee(db, *, user_id: str) -> str:
    doc_id = ObjectId()
    await db["employees"].insert_one({
        "_id": doc_id, "user_id": user_id, "is_deleted": False, "status": "active", "display_name": "Test Employee",
    })
    return str(doc_id)


async def test_total_leads_scopes_to_assigned_employee_only():
    db = AsyncMongoMockClient(tz_aware=True)["test_widget_scoping"]
    employee_user_id = str(ObjectId())
    employee_id = await _seed_employee(db, user_id=employee_user_id)
    other_employee_id = str(ObjectId())

    await db["leads"].insert_one({"is_deleted": False, "assigned_to": employee_id})
    await db["leads"].insert_one({"is_deleted": False, "assigned_to": employee_id})
    await db["leads"].insert_one({"is_deleted": False, "assigned_to": other_employee_id})  # someone else's lead

    owner = User(mobile="9000000001", role=OWNER)
    owner.id = str(ObjectId())
    employee = User(mobile="9000000002", role=EMPLOYEE)
    employee.id = employee_user_id

    owner_result = await WIDGET_PROVIDERS["total_leads"](db, owner)
    employee_result = await WIDGET_PROVIDERS["total_leads"](db, employee)

    assert owner_result["value"] == 3  # company-wide
    assert employee_result["value"] == 2  # only this employee's own leads — never the other employee's


async def test_employee_with_no_employee_record_sees_zero_not_an_error():
    # An Employee-role User with no matching Employee document (e.g. deleted/misconfigured)
    # must degrade to zero, never leak company-wide data or raise.
    db = AsyncMongoMockClient(tz_aware=True)["test_widget_scoping_orphan"]
    await db["leads"].insert_one({"is_deleted": False, "assigned_to": str(ObjectId())})

    orphan_employee = User(mobile="9000000003", role=EMPLOYEE)
    orphan_employee.id = str(ObjectId())

    result = await WIDGET_PROVIDERS["total_leads"](db, orphan_employee)
    assert result == {"available": True, "value": 0}


async def test_insurance_re_eligible_is_honestly_unavailable_without_an_active_rule():
    # No `reminder_rules` row seeded at all — must report unavailable, never a fabricated 0-as-real.
    db = AsyncMongoMockClient(tz_aware=True)["test_widget_re_eligible"]
    owner = User(mobile="9000000004", role=OWNER)
    owner.id = str(ObjectId())

    result = await WIDGET_PROVIDERS["insurance_re_eligible"](db, owner)
    assert result == {"available": False, "value": 0}


async def test_referral_commission_widgets_sum_real_amounts_not_fabricated():
    db = AsyncMongoMockClient(tz_aware=True)["test_widget_commission"]
    partner_id = str(ObjectId())
    await db["commission_entries"].insert_one({"is_deleted": False, "partner_id": partner_id, "status": "pending", "commission_amount": 1500.0})
    await db["commission_entries"].insert_one({"is_deleted": False, "partner_id": partner_id, "status": "approved", "commission_amount": 500.0})
    await db["commission_entries"].insert_one({"is_deleted": False, "partner_id": partner_id, "status": "paid", "commission_amount": 900.0})

    owner = User(mobile="9000000005", role=OWNER)
    owner.id = str(ObjectId())

    pending = await WIDGET_PROVIDERS["referral_pending_commission"](db, owner)
    paid = await WIDGET_PROVIDERS["referral_paid_commission"](db, owner)

    assert pending == {"available": True, "value": 2, "amount": 2000.0}  # pending + approved
    assert paid == {"available": True, "value": 1, "amount": 900.0}
