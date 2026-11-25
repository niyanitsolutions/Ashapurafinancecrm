# ruff: noqa: F811
"""Real loopback transaction tests; existing staff permissions and no external services."""

import json

import pytest
from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.features.auth.models import User
from app.features.customer.schemas import UpdateApplicationRequest
from app.features.customer.service import CustomerService
from app.security.encryption import decrypt
from bson import ObjectId
from pydantic import ValidationError as SchemaError
from test_pin_mongo_integration import pin_mongo  # noqa: F401
from test_unified_operations import seed_identity, seed_team


@pytest.fixture
async def editing(pin_mongo, mock_redis):
    db = pin_mongo
    owner, employees = await seed_team(db)
    customer, app = await seed_identity(db, "Authoritative Customer")
    fields = [
        {
            "key": "full_name",
            "label": "Full Name",
            "field_type": "text",
            "required": True,
        },
        {
            "key": "salary",
            "label": "Monthly Salary",
            "field_type": "number",
            "required": False,
            "validation": {"min_value": 0},
        },
        {
            "key": "pan_number",
            "label": "PAN Number",
            "field_type": "text",
            "required": False,
        },
        {"key": "gender", "label": "Gender", "field_type": "select", "required": False},
        {
            "key": "dob",
            "label": "Date of birth",
            "field_type": "date",
            "required": False,
        },
        {
            "key": "hidden",
            "label": "Internal",
            "field_type": "text",
            "required": False,
            "hidden": True,
        },
    ]
    await db.application_form_definitions.update_one(
        {"_id": ObjectId(app.form_definition_id)},
        {
            "$set": {
                "fields": fields,
                "repeatable_groups": [
                    {
                        "key": "references",
                        "label": "References",
                        "min_count": 0,
                        "max_count": 2,
                        "fields": [
                            {
                                "key": "name",
                                "label": "Reference name",
                                "field_type": "text",
                                "required": True,
                            }
                        ],
                    }
                ],
            }
        },
    )
    await db.applications.update_one(
        {"_id": ObjectId(app.require_id())},
        {
            "$set": {
                "assigned_to": employees[0][0].require_id(),
                "form_data": {
                    "full_name": "Original Applicant",
                    "salary": 30000,
                    "pan_number": "ABCDE1234F",
                    "hidden": "keep",
                    "legacy": "retained",
                },
            }
        },
    )
    sibling = app.model_dump(by_alias=True, exclude={"id"})
    sibling["application_code"] = "SIBLING"
    sid = (await db.applications.insert_one(sibling)).inserted_id
    return db, CustomerService(db, mock_redis), owner, employees, app, customer, sid


async def test_partial_edit_history_identity_and_sibling_preservation(editing):
    db, service, owner, employees, app, customer, sid = editing
    sibling = await db.applications.find_one({"_id": sid})
    profile = await db.customers.find_one({"_id": ObjectId(customer.require_id())})
    saved = await service.update_application(
        app.require_id(),
        UpdateApplicationRequest(
            form_data={
                "salary": 45000,
                "pan_number": "abcde1234f",
                "references": [{"name": "Verified reference"}],
            },
            version=1,
            reason="Correct submitted financial details",
        ),
        employees[0][1],
    )
    assert saved.version == 2 and saved.form_data["salary"] == 45000
    assert (
        saved.form_data["pan_number"] == "ABCDE1234F"
        and saved.form_data["legacy"] == "retained"
    )
    assert saved.customer_id == customer.require_id() and saved.user_id == app.user_id
    assert (
        await db.customers.find_one({"_id": ObjectId(customer.require_id())}) == profile
    )
    assert await db.applications.find_one({"_id": sid}) == sibling
    raw = await db.applications.find_one({"_id": ObjectId(app.require_id())})
    assert (
        json.loads(decrypt(raw["answer_history"][0]["before_encrypted"]))["salary"]
        == 30000
    )
    audit = await db.audit_logs.find_one({"event_type": "application_details_edited"})
    assert audit["user_id"] == employees[0][1].require_id() and "ABCDE1234F" not in str(
        audit
    )
    with pytest.raises(ConflictError):
        await service.update_application(
            app.require_id(),
            UpdateApplicationRequest(
                form_data={"salary": 60000}, version=1, reason="Stale edit"
            ),
            owner,
        )


@pytest.mark.parametrize(
    "change",
    [
        {"salary": "not a number"},
        {"salary": -1},
        {"gender": "invalid"},
        {"dob": "2026-02-31"},
        {"pan_number": "invalid"},
        {"hidden": "tamper"},
        {"customer_id": "tamper"},
        {"references": [{"user_id": "tamper"}]},
    ],
)
async def test_invalid_protected_and_hidden_fields_are_rejected(editing, change):
    db, service, owner, _, app, _, _ = editing
    with pytest.raises(ValidationError):
        await service.update_application(
            app.require_id(),
            UpdateApplicationRequest(
                form_data=change, version=1, reason="Validate inputs"
            ),
            owner,
        )
    raw = await db.applications.find_one({"_id": ObjectId(app.require_id())})
    assert raw["version"] == 1 and not raw.get("answer_history")


async def test_permissions_assignment_customer_and_partner_isolation(editing):
    db, service, _, employees, app, _, _ = editing
    payload = UpdateApplicationRequest(
        form_data={"salary": 42000}, version=1, reason="Scope test"
    )
    with pytest.raises(ForbiddenError):
        await service.update_application(app.require_id(), payload, employees[1][1])
    customer = User(id=app.user_id, mobile="9000070001", role="customer")
    with pytest.raises(ConflictError):
        await service.update_application(app.require_id(), payload, customer)
    with pytest.raises(ForbiddenError):
        await service.update_application(
            app.require_id(),
            payload,
            User(id=str(ObjectId()), mobile="9000079999", role="referral_partner"),
        )
    permission = await db.permissions.find_one(
        {"module": "customer", "resource": "customers"}
    )
    await db.role_permissions.update_many(
        {"permission_id": str(permission["_id"])},
        {"$set": {"granted_actions": ["view"]}},
    )
    with pytest.raises(ForbiddenError):
        await service.update_application(app.require_id(), payload, employees[0][1])
    with pytest.raises(SchemaError):
        UpdateApplicationRequest.model_validate(
            {"form_data": {}, "user_id": app.user_id}
        )


async def test_audit_failure_rolls_back_application(editing):
    db, service, owner, _, app, _, _ = editing
    # Audit construction happens before the transaction; trigger a transactional insert failure instead.
    from pymongo.errors import DuplicateKeyError

    await db.audit_logs.create_index("event_type", unique=True)
    await db.audit_logs.insert_one({"event_type": "application_details_edited"})
    with pytest.raises(DuplicateKeyError):
        await service.update_application(
            app.require_id(),
            UpdateApplicationRequest(
                form_data={"salary": 99999}, version=1, reason="Test rollback"
            ),
            owner,
        )
    raw = await db.applications.find_one({"_id": ObjectId(app.require_id())})
    assert (
        raw["form_data"]["salary"] == 30000
        and raw["version"] == 1
        and "answer_history" not in raw
    )


async def test_existing_update_api_and_saved_schema_are_staff_scoped(editing, client):
    db, _, _, employees, app, _, _ = editing
    from app.config.database import get_database

    client._transport.app.dependency_overrides[get_database] = lambda: db
    login = await client.post(
        "/api/v1/auth/login",
        json={"mobile": employees[0][1].mobile, "password": "InitialPass1!"},
    )
    assert login.status_code == 200, login.text
    owner_headers = {"Authorization": "Bearer " + login.json()["data"]["access_token"]}
    response = await client.get(
        f"/api/v1/applications/{app.require_id()}/form-definition",
        headers=owner_headers,
    )
    assert (
        response.status_code == 200
        and response.json()["data"]["id"] == app.form_definition_id
    )
    response = await client.patch(
        f"/api/v1/applications/{app.require_id()}",
        json={"form_data": {"salary": 34000}, "version": 1, "reason": "API update"},
        headers=owner_headers,
    )
    assert response.status_code == 200 and response.json()["data"]["version"] == 2
    assert (
        await client.patch(
            f"/api/v1/applications/{app.require_id()}",
            json={"customer_id": "protected"},
            headers=owner_headers,
        )
    ).status_code == 422


async def test_inconsistent_customer_reference_is_never_edited(editing):
    db, service, owner, _, app, customer, _ = editing
    await db.customers.update_one(
        {"_id": ObjectId(customer.require_id())}, {"$set": {"user_id": str(ObjectId())}}
    )
    with pytest.raises(ForbiddenError):
        await service.update_application(
            app.require_id(),
            UpdateApplicationRequest(
                form_data={"salary": 44000},
                version=1,
                reason="Must not rebind identity",
            ),
            owner,
        )
    row = await db.applications.find_one({"_id": ObjectId(app.require_id())})
    assert row["version"] == 1 and row["form_data"]["salary"] == 30000
