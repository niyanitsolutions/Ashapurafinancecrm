# ruff: noqa: F811
"""Synthetic identity/role boundaries using disposable loopback transactions."""

import asyncio

import pytest
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    UnauthorizedError,
    ValidationError,
)
from app.features.auth.models import User
from app.features.auth.role_context import effective_user
from app.features.auth.service import AuthService, RequestContext
from app.features.employee.identity import preview
from app.features.employee.indexes import ensure_employee_indexes
from app.features.employee.models import Branch, Department, Designation
from app.features.employee.schemas import CreateEmployeeRequest
from app.features.employee.service import EmployeeService
from app.security.password import hash_password
from bson import ObjectId
from test_pin_mongo_integration import pin_mongo  # noqa: F401


def test_registration_and_user_models_share_mobile_policy_without_suffix_matching():
    from app.features.customer.schemas import DirectRegisterRequest
    from pydantic import ValidationError as ModelValidationError

    assert User(mobile=" +91 (90000) 10002 ", role="customer").mobile == "9000010002"
    assert (
        DirectRegisterRequest(
            mobile="0091 90000-10002", pin="4826", confirm_pin="4826"
        ).mobile
        == "9000010002"
    )
    for mobile in ("+1 9000010002", "+44 9000010002", "1000010002"):
        with pytest.raises(ModelValidationError):
            DirectRegisterRequest(mobile=mobile, pin="4826", confirm_pin="4826")
        with pytest.raises(ModelValidationError):
            User(mobile=mobile, role="customer")


async def test_deleted_formatted_identity_cannot_be_replaced(mock_db):
    from app.features.auth.repository import UserRepository

    await mock_db.users.insert_one(
        {"mobile": "+91 (90000) 10002", "role": "customer", "is_deleted": True}
    )
    with pytest.raises(ConflictError):
        await UserRepository(mock_db).insert(User(mobile="9000010002", role="employee"))
    assert await mock_db.users.count_documents({}) == 1


async def setup(db, redis, role=None):
    await ensure_employee_indexes(db)
    refs = {}
    for collection, field, model in (
        ("departments", "department_id", Department(name="Synthetic Department")),
        ("designations", "designation_id", Designation(name="Synthetic Designation")),
        ("branches", "branch_id", Branch(name="Synthetic Branch", code="SYN")),
    ):
        refs[field] = str(
            (
                await db[collection].insert_one(model.model_dump(exclude={"id"}))
            ).inserted_id
        )
    owner = User(id=str(ObjectId()), mobile="9000010001", role="owner")
    payload = dict(
        mobile="9000010002",
        initial_password="EmployeeTemp1!",
        first_name="Synthetic",
        last_name="Employee",
        email="synthetic@example.com",
        joining_date="2026-11-26",
        employment_type="full_time",
        **refs,
    )
    existing = None
    if role:
        existing = User(
            id=str(ObjectId()),
            mobile=payload["mobile"],
            role=role,
            password_hash=hash_password("ExistingPassword1!"),
            pin_hash="preserved-pin-hash",
            is_mobile_verified=True,
        )
        await db.users.insert_one(
            {
                **existing.model_dump(by_alias=True, exclude={"id"}),
                "_id": ObjectId(existing.id),
            }
        )
        await db["customers" if role == "customer" else "referral_partners"].insert_one(
            {
                "user_id": existing.id,
                "full_name": "Original Profile Name",
                "mobile": existing.mobile,
                "is_deleted": False,
            }
        )
    return EmployeeService(db, redis), owner, payload, existing


@pytest.mark.parametrize("role", ["customer", "referral_partner"])
async def test_explicit_membership_preserves_identity_credentials_and_session_role(
    pin_mongo, mock_redis, role
):
    db = pin_mongo
    service, owner, values, existing = await setup(db, mock_redis, role)
    original = await db.users.find_one({"_id": ObjectId(existing.id)})
    profile_collection = db["customers" if role == "customer" else "referral_partners"]
    original_profile = await profile_collection.find_one({})
    with pytest.raises(ConflictError):
        await service.create_employee(CreateEmployeeRequest(**values), owner)
    info = await preview(db, "+91 90000 10002", owner)
    assert info["partner_id" if role == "referral_partner" else "customer_id"]
    values.update(
        existing_user_id=existing.id,
        identity_version=info["version"],
        identity_confirmed=True,
        identity_reason="Owner verified original identity association",
    )
    employee = await service.create_employee(CreateEmployeeRequest(**values), owner)
    saved = await db.users.find_one({"_id": ObjectId(existing.id)})
    assert (
        saved["role"] == role
        and saved["password_hash"] == original["password_hash"]
        and saved["pin_hash"] == original["pin_hash"]
    )
    assert await db.users.count_documents({}) == 1 and employee.user_id == existing.id
    assert await profile_collection.find_one({}) == original_profile
    assert "password_hash" not in str(await preview(db, existing.mobile, owner))
    with pytest.raises(ValidationError):
        await service.reset_employee_password(employee.require_id(), owner)
    assert (await effective_user(db, User.model_validate(saved), None)).role == role
    auth = AuthService(db, mock_redis)
    ctx = RequestContext(ip_address="127.0.0.1", user_agent="synthetic")
    login = await auth.login(
        mobile=existing.mobile,
        password="EmployeeTemp1!",
        login_role="employee",
        ctx=ctx,
    )
    assert login.role == "employee" and login.must_change_password
    session = await db.sessions.find_one({"user_id": existing.id})
    assert session["active_role"] == "employee"
    refreshed = await auth.refresh(refresh_token=login.refresh_token, ctx=ctx)
    assert refreshed.access_token
    await auth.change_password(
        user_id=existing.id,
        current_password="EmployeeTemp1!",
        new_password="EmployeeOwnPass2!",
        active_role="employee",
    )
    changed = await db.users.find_one({"_id": ObjectId(existing.id)})
    assert (
        changed["password_hash"] == original["password_hash"]
        and changed["pin_hash"] == original["pin_hash"]
    )
    assert not changed["employee_access"]["must_change_password"]
    if role == "referral_partner":
        primary_login = await auth.login(
            mobile=existing.mobile, password="ExistingPassword1!", ctx=ctx
        )
        assert primary_login.role == "referral_partner"
    with pytest.raises(ForbiddenError):
        await service.get_own_employee(existing)
    await service.deactivate_employee(employee.require_id(), owner)
    deactivated = User.model_validate(
        await db.users.find_one({"_id": ObjectId(existing.id)})
    )
    assert deactivated.status == "active"
    with pytest.raises(UnauthorizedError):
        await effective_user(db, deactivated, "employee")


async def test_new_and_existing_employee_concurrency(pin_mongo, mock_redis):
    db = pin_mongo
    service, owner, values, _ = await setup(db, mock_redis)
    values["mobile"] = "+91 (90000) 10002"

    async def create():
        try:
            return await service.create_employee(CreateEmployeeRequest(**values), owner)
        except ConflictError:
            return None

    results = await asyncio.gather(*(create() for _ in range(4)))
    assert sum(r is not None for r in results) == 1
    assert (
        await db.users.count_documents({})
        == await db.employees.count_documents({})
        == 1
    )
    info = await preview(db, "9000010002", owner)
    assert info["state"] == "employee" and info["employee_id"]
    assert await db.audit_logs.count_documents({"event_type": "employee_created"}) == 1


async def test_non_owner_and_unverified_identity_cannot_attach(pin_mongo, mock_redis):
    db = pin_mongo
    service, owner, values, existing = await setup(db, mock_redis, "customer")
    with pytest.raises(ForbiddenError):
        await service.create_employee(CreateEmployeeRequest(**values), existing)
    await db.users.update_one(
        {"_id": ObjectId(existing.id)}, {"$set": {"is_mobile_verified": False}}
    )
    assert not (await preview(db, existing.mobile, owner))["can_add_employee"]
    with pytest.raises(ConflictError):
        await service.create_employee(CreateEmployeeRequest(**values), owner)
    assert await db.employees.count_documents({}) == 0


async def test_creation_audit_failure_rolls_back_both_records(pin_mongo, mock_redis):
    db = pin_mongo
    service, owner, values, _ = await setup(db, mock_redis)
    await db.audit_logs.create_index("event_type", unique=True)
    await db.audit_logs.insert_one({"event_type": "employee_created"})
    with pytest.raises(ConflictError):
        await service.create_employee(CreateEmployeeRequest(**values), owner)
    assert await db.users.count_documents({}) == 0
    assert await db.employees.count_documents({}) == 0


async def test_api_sessions_bind_role_and_refresh_without_union_grants(
    pin_mongo, mock_redis, client
):
    from app.config.database import get_database

    db = pin_mongo
    service, owner, values, existing = await setup(db, mock_redis, "customer")
    info = await preview(db, existing.mobile, owner)
    values.update(
        existing_user_id=existing.id,
        identity_version=info["version"],
        identity_confirmed=True,
        identity_reason="Owner verified synthetic identity",
    )
    employee = await service.create_employee(CreateEmployeeRequest(**values), owner)
    client._transport.app.dependency_overrides[get_database] = lambda: db
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "mobile": existing.mobile,
            "password": "EmployeeTemp1!",
            "login_role": "employee",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    headers = {"Authorization": "Bearer " + data["access_token"]}
    assert (await client.get("/api/v1/auth/profile", headers=headers)).json()["data"][
        "role"
    ] == "employee"
    assert (await client.get("/api/v1/employees/me", headers=headers)).json()["data"][
        "id"
    ] == employee.id
    assert (await client.get("/api/v1/employees", headers=headers)).status_code == 403
    assert (
        await client.get("/api/v1/customers/me", headers=headers)
    ).status_code == 403
    refresh = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]}
    )
    assert refresh.status_code == 200, refresh.text
    refreshed_headers = {
        "Authorization": "Bearer " + refresh.json()["data"]["access_token"]
    }
    assert (await client.get("/api/v1/auth/profile", headers=refreshed_headers)).json()[
        "data"
    ]["role"] == "employee"
    primary = await AuthService(db, mock_redis).issue_session(
        user=existing,
        ctx=RequestContext(ip_address="127.0.0.1", user_agent="synthetic"),
        login_method="pin",
    )
    primary_headers = {"Authorization": "Bearer " + primary.access_token}
    assert (await client.get("/api/v1/auth/profile", headers=primary_headers)).json()[
        "data"
    ]["role"] == "customer"
    assert (
        await client.get("/api/v1/employees/me", headers=primary_headers)
    ).status_code == 403
    from app.features.daily_operations.attendance import daily_sessions
    from app.features.daily_operations.service import DailyOperationsService

    attendance = await daily_sessions(DailyOperationsService(db), owner)
    employee_day = next(
        row for row in attendance["items"] if row["employee_id"] == employee.id
    )
    pin_family = (
        await db.sessions.find_one({"user_id": existing.id, "active_role": "customer"})
    )["family_id"]
    assert employee_day["sessions"] and all(
        item["id"] != pin_family for item in employee_day["sessions"]
    )
    await service.deactivate_employee(employee.id, owner)
    assert (
        await client.get("/api/v1/employees/me", headers=refreshed_headers)
    ).status_code == 401
    assert (
        await client.get("/api/v1/auth/profile", headers=primary_headers)
    ).status_code == 200
