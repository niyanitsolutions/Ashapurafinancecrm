"""Synthetic integration coverage; no external SMS, Meta or document network calls."""

import asyncio
from datetime import timedelta

import pytest
from app.core.exceptions import ForbiddenError
from app.features.access_control.models import (
    EmployeeRole,
    Permission,
    Role,
    RolePermission,
)
from app.features.auth.models import User
from app.features.customer.models import (
    Application,
    ApplicationFormDefinition,
    Customer,
    FormFieldDefinition,
)
from app.features.customer.submitted_identity import enrich_submitted_identity
from app.features.daily_operations.catalog import install_catalog
from app.features.daily_operations.linked import OpenLinkedRequest, open_linked
from app.features.daily_operations.service import DailyOperationsService
from app.features.dashboard.filters import resolve_dashboard_filters
from app.features.dashboard.operations import operational_summary
from app.features.employee.models import Employee
from app.features.leads.auto_assignment import AssignmentSettings, AutoAssignment
from app.features.leads.indexes import ensure_lead_indexes
from app.features.leads.schemas import CreateLeadRequest
from app.features.leads.service import LeadService
from app.security.password import hash_password
from app.utils.datetime import utc_now
from bson import ObjectId
from test_leads import _lead_master_data, _lead_payload, _login


async def insert(db, name, model):
    return str(
        (await db[name].insert_one(model.model_dump(exclude={"id"}))).inserted_id
    )


async def seed_team(db):
    owner = User(mobile="9000080000", role="owner")
    owner.id = await insert(db, "users", owner)
    employees = []
    for index in range(3):
        user = User(
            mobile=f"900008000{index + 1}",
            role="employee",
            password_hash=hash_password("InitialPass1!"),
        )
        user.id = await insert(db, "users", user)
        employee = Employee(
            user_id=user.require_id(),
            employee_code=f"TEST-{index}",
            first_name=f"Team {index}",
            last_name="Member",
            display_name=f"Team {index}",
            mobile=user.mobile,
            email=f"team{index}@example.com",
            department_id=str(ObjectId()),
            designation_id=str(ObjectId()),
            branch_id=str(ObjectId()),
            joining_date=utc_now().replace(hour=0, minute=0, second=0, microsecond=0),
            employment_type="full_time",
        )
        employee.id = await insert(db, "employees", employee)
        role_id = await insert(db, "roles", Role(name=f"Team {index} role"))
        await insert(
            db,
            "employee_roles",
            EmployeeRole(employee_id=employee.require_id(), role_id=role_id),
        )
        for module, resource in (
            ("loan_management", "applications"),
            ("leads", "leads"),
            ("customer", "customers"),
        ):
            existing = await db.permissions.find_one(
                {"module": module, "resource": resource, "is_deleted": False}
            )
            pid = (
                str(existing["_id"])
                if existing
                else await insert(
                    db,
                    "permissions",
                    Permission(
                        module=module,
                        resource=resource,
                        actions=["view", "create", "edit"],
                    ),
                )
            )
            await insert(
                db,
                "role_permissions",
                RolePermission(
                    role_id=role_id,
                    permission_id=pid,
                    granted_actions=["view", "create", "edit"],
                ),
            )
        employees.append((employee, user))
    return owner, employees


@pytest.fixture
async def team(mock_db):
    await ensure_lead_indexes(mock_db)
    owner, employees = await seed_team(mock_db)
    master = await _lead_master_data(mock_db)
    return mock_db, owner, employees, master


async def make_lead(team, index=0, **kwargs):
    db, owner, _, master = team
    return await LeadService(db).create_lead(
        CreateLeadRequest(**_lead_payload(master, mobile=f"900009{index:04d}")),
        owner,
        **kwargs,
    )


@pytest.mark.parametrize("size", [1, 2, 3])
async def test_rotation_preserves_fresh_and_exact_counts(team, size):
    db, owner, employees, _ = team
    pool = [e.require_id() for e, _ in employees[:size]]
    await AutoAssignment(db).save(
        AssignmentSettings(enabled=True, employee_ids=pool), owner
    )
    leads = [await make_lead(team, i) for i in range(6)]
    assert [lead.assigned_to for lead in leads] == [pool[i % size] for i in range(6)]
    assert all(lead.stage == "fresh" for lead in leads)
    items, count = await LeadService(db).list_leads(
        search=None,
        source_id=None,
        product_category=None,
        product_id=None,
        assigned_to="__unassigned__",
        status=None,
        stage="fresh",
        skip=0,
        limit=20,
        sort=[("created_at", 1)],
        actor=owner,
    )
    assert (
        count == len(items) == (await LeadService(db).get_tab_counts(owner)).fresh == 6
    )
    assert (
        await db.notifications.count_documents({"notification_type": "lead_assigned"})
        == 6
    )


async def test_concurrent_intake_and_duplicate_event_preserve_rotation(team):
    db, owner, employees, _ = team
    pool = [e.require_id() for e, _ in employees]
    await AutoAssignment(db).save(
        AssignmentSettings(enabled=True, employee_ids=pool), owner
    )
    await asyncio.gather(*(make_lead(team, i) for i in range(12)))
    rows = await db.leads.find({}).sort("assignment_sequence", 1).to_list(20)
    assert [r["assignment_sequence"] for r in rows] == list(range(1, 13))
    assert [r["assigned_to"] for r in rows] == pool * 4
    results = await asyncio.gather(
        *(make_lead(team, 50, intake_key="synthetic-meta-event") for _ in range(4))
    )
    assert len({r.require_id() for r in results}) == 1
    assert (await AutoAssignment(db).settings())["sequence"] == 13


async def test_inactive_employee_and_failed_assignment_recovery(team):
    db, owner, employees, _ = team
    service = AutoAssignment(db)
    pool = [e.require_id() for e, _ in employees[:2]]
    await service.save(AssignmentSettings(enabled=True, employee_ids=pool), owner)
    await db.users.update_one(
        {"_id": ObjectId(employees[0][1].require_id())},
        {"$set": {"status": "inactive"}},
    )
    assert (await make_lead(team)).assigned_to == pool[1]
    await db.employees.update_one(
        {"_id": ObjectId(pool[1])}, {"$set": {"status": "inactive"}}
    )
    lead = await make_lead(team, 1)
    assert lead.assigned_to is None and lead.stage == "fresh"
    row = await db.leads.find_one({"_id": ObjectId(lead.require_id())})
    assert row["assignment_error"] == "assignment_unavailable"
    for _ in range(4):
        await service.recover()
    assert (await db.leads.find_one({"_id": row["_id"]}))["assignment_attempts"] == 3
    await db.employees.update_one(
        {"_id": ObjectId(pool[1])}, {"$set": {"status": "active"}}
    )
    await service.assign(
        "leads", lead.require_id(), owner
    )  # explicit owner retry after limit
    assert (await LeadService(db).get_lead(lead.require_id())).assigned_to == pool[1]
    assert await db.leads.count_documents({}) == 2


async def test_manual_ownership_and_replayed_outbox_are_preserved(team):
    db, owner, employees, _ = team
    service = AutoAssignment(db)
    pool = [e.require_id() for e, _ in employees[:2]]
    await service.save(AssignmentSettings(enabled=True, employee_ids=pool), owner)
    lead = await make_lead(team)
    row = await db.leads.find_one({"_id": ObjectId(lead.require_id())})
    event = {
        "employee_id": pool[0],
        "sequence": row["assignment_sequence"],
        "actor_id": owner.require_id(),
        "at": row["assigned_at"],
    }
    for _ in range(2):
        await db.leads.update_one(
            {"_id": row["_id"]}, {"$set": {"assignment_event_pending": event}}
        )
        await service.recover()
    assert await db.audit_logs.count_documents({"event_type": "crm_auto_assigned"}) == 1
    assert await db.lead_activities.count_documents({"event_type": "assigned"}) == 1
    assert (
        await db.notifications.count_documents({"notification_type": "lead_assigned"})
        == 1
    )
    await LeadService(db).assign_lead(lead.require_id(), pool[1], owner)
    await service.assign("leads", lead.require_id(), owner)
    assert (await LeadService(db).get_lead(lead.require_id())).assigned_to == pool[1]


async def test_employee_creator_keeps_fresh_and_owner_controls_are_forbidden(team):
    db, _, employees, master = team
    employee, user = employees[0]
    lead = await LeadService(db).create_lead(
        CreateLeadRequest(**_lead_payload(master)), user
    )
    assert lead.assigned_to == employee.require_id() and lead.stage == "fresh"
    with pytest.raises(ForbiddenError):
        await AutoAssignment(db).save(AssignmentSettings(), user)
    assert (await LeadService(db).get_tab_counts(user)).fresh == 1


async def test_removed_pool_member_does_not_receive_a_reserved_retry(team):
    db, owner, employees, _ = team
    lead = await make_lead(team)
    first, second = [e.require_id() for e, _ in employees[:2]]
    await db.leads.update_one(
        {"_id": ObjectId(lead.require_id())},
        {"$set": {"assignment_reserved_employee": first, "assignment_sequence": 99}},
    )
    service = AutoAssignment(db)
    await service.save(AssignmentSettings(enabled=True, employee_ids=[second]), owner)
    await db.auto_assignment_settings.update_one(
        {"_id": "default"}, {"$set": {"sequence": 99}}
    )
    await service.assign("leads", lead.require_id(), owner)
    row = await db.leads.find_one({"_id": ObjectId(lead.require_id())})
    assert row["assigned_to"] == second and row["assignment_sequence"] == 100


async def test_linked_daily_workspace_is_idempotent_and_follows_reassignment(team):
    db, owner, employees, _ = team
    await install_catalog(db)
    lead = await make_lead(team)
    await LeadService(db).assign_lead(
        lead.require_id(), employees[0][0].require_id(), owner
    )
    service = DailyOperationsService(db)
    request = OpenLinkedRequest(entity="lead", record_id=lead.require_id())
    rows = await asyncio.gather(
        *(open_linked(service, request, employees[0][1]) for _ in range(5))
    )
    assert len({r["id"] for r in rows}) == 1
    assert (
        await open_linked(
            service,
            OpenLinkedRequest(entity="lead", record_id=lead.require_id().upper()),
            employees[0][1],
        )
    )["id"] == rows[0]["id"]
    assert rows[0]["lead_id"] == lead.require_id()
    assert len(rows[0]["history"]) == 1
    assert await db.leads.count_documents({}) == 1
    stage = (await LeadService(db).get_lead(lead.require_id())).stage
    await LeadService(db).assign_lead(
        lead.require_id(), employees[1][0].require_id(), owner
    )
    with pytest.raises(ForbiddenError):
        await service.get("follow-ups", rows[0]["id"], employees[0][1])
    visible = await service.list_records("follow-ups", employees[1][1])
    assert visible["total"] == 1
    assert "linked_customer" not in visible["items"][0]
    from app.features.daily_operations.schemas import FollowUpInput
    from app.utils.datetime import to_ist

    current = await service.get("follow-ups", rows[0]["id"], employees[1][1])
    payload = FollowUpInput(
        date=to_ist(current["date"]).date(),
        lead_id=lead.require_id(),
        customer_name=current["customer_name"],
        customer_number=current["customer_number"],
        assigned_to=employees[1][0].require_id(),
        employee_name=current["employee_name"],
        bank="Test Bank",
        status="FOLLOW UP PENDING",
        remarks="Documents requested",
        remarks_date=to_ist(current["remarks_date"]).date(),
        next_action="Review documents",
        due_date=to_ist(current["due_date"]).date(),
    )
    saved = await service.save(
        "follow-ups", payload, employees[1][1], rows[0]["id"], current["version"]
    )
    assert len(saved["history"]) == 2
    assert (
        await db.lead_activities.count_documents(
            {"lead_id": lead.require_id(), "event_type": "daily_follow_up_updated"}
        )
        == 1
    )
    assert (await LeadService(db).get_lead(lead.require_id())).stage == stage


async def seed_identity(db, name="Customer"):
    user = User(mobile="9000070001", role="customer")
    user.id = await insert(db, "users", user)
    customer = Customer(
        customer_code="TEST-CUSTOMER",
        full_name=name,
        mobile=user.mobile,
        user_id=user.require_id(),
    )
    customer.id = await insert(db, "customers", customer)
    form = ApplicationFormDefinition(
        product_category="loan",
        product_id=str(ObjectId()),
        fields=[
            FormFieldDefinition(
                key="full_name", label="Name", field_type="text", required=True
            ),
            FormFieldDefinition(key="email", label="Email", field_type="text"),
        ],
    )
    form.id = await insert(db, "application_form_definitions", form)
    app = Application(
        application_code="TEST-APPLICATION",
        user_id=user.require_id(),
        customer_id=customer.require_id(),
        product_category="loan",
        product_id=form.product_id,
        form_definition_id=form.require_id(),
        status="submitted",
        form_data={
            "full_name": "Ramesh Test",
            "email": "ramesh@example.com",
            "mobile": "9000079999",
        },
    )
    app.id = await insert(db, "applications", app)
    return customer, app


@pytest.mark.parametrize(
    "existing,expected",
    [("Customer", "Ramesh Test"), ("Verified Person", "Verified Person")],
)
async def test_submission_identity_updates_only_existing_placeholder_profile(
    mock_db, existing, expected
):
    customer, app = await seed_identity(mock_db, existing)
    await asyncio.gather(*(enrich_submitted_identity(mock_db, app) for _ in range(3)))
    row = await mock_db.customers.find_one({"_id": ObjectId(customer.require_id())})
    assert row["full_name"] == expected and row["email"] == "ramesh@example.com"
    assert row["mobile"] == customer.mobile
    assert await mock_db.customers.count_documents({}) == 1
    app.form_data["full_name"] = "Customer"
    await enrich_submitted_identity(mock_db, app)
    assert (await mock_db.customers.find_one({"_id": row["_id"]}))[
        "full_name"
    ] == expected


async def test_operational_dashboard_scopes_employee_and_tab_counts(team):
    db, owner, employees, _ = team
    await make_lead(team)
    lead = await make_lead(team, 1)
    await LeadService(db).assign_lead(
        lead.require_id(), employees[0][0].require_id(), owner
    )
    await db.leads.update_one(
        {"_id": ObjectId(lead.require_id())},
        {"$set": {"next_follow_up_date": utc_now() - timedelta(days=2)}},
    )
    filters = resolve_dashboard_filters(
        date_range="this_month",
        start_date=None,
        end_date=None,
        product_category=None,
        source_id=None,
    )
    summary = await operational_summary(
        db, employees[0][1], filters, employee=employees[1][0].require_id()
    )
    assert summary["cohort_leads"] == 1
    assert summary["followups"]["overdue"] == 1
    assert summary["priorities"][0]["id"] == lead.require_id()
    assert "assignment" not in summary
    assert (
        summary["tabs"]
        == (await LeadService(db).get_tab_counts(employees[0][1])).model_dump()
    )
    assert (await operational_summary(db, owner, filters))["cohort_leads"] == 2


async def test_assignment_settings_endpoint_rejects_non_owner(
    client, mock_db, owner_headers
):
    _, employees = await seed_team(mock_db)
    headers = await _login(client, employees[0][1].mobile)
    for method, suffix, body in (
        ("GET", "", None),
        ("PUT", "", {"enabled": True, "employee_ids": []}),
        ("GET", "/history", None),
        ("GET", "/pending", None),
    ):
        response = await client.request(
            method,
            f"/api/v1/leads/auto-assignment{suffix}",
            headers=headers,
            **({"json": body} if body else {}),
        )
        assert response.status_code == 403
    assert (
        await client.get("/api/v1/leads/auto-assignment", headers=owner_headers)
    ).status_code == 200
