# ruff: noqa: F811
"""Synthetic enterprise CRM regressions; no external services."""

import pytest
from app.features.customer.schemas import CompleteProfileRequest, UpdateProfileRequest
from app.features.leads.document_collection import CollectionFilters, grouped
from app.features.search.service import search_records
from bson import ObjectId
from pydantic import ValidationError as SchemaError
from test_invoice_mongo_integration import real_invoice_db  # noqa: F401
from test_unified_operations import seed_identity, seed_team


@pytest.mark.parametrize("pan", ["gdips8425l", "Gdips8425l", "GDIPS8425L"])
def test_profile_pan_normalizes(pan):
    assert (
        CompleteProfileRequest(full_name="Test", pan_number=pan).pan_number
        == "GDIPS8425L"
    )
    assert UpdateProfileRequest(pan_number=pan).pan_number == "GDIPS8425L"


def test_invalid_pan_rejected():
    with pytest.raises(SchemaError):
        UpdateProfileRequest(pan_number="not-a-pan")


async def test_real_grouped_full_dataset_scope_and_filters(client, real_invoice_db):
    db = real_invoice_db
    owner, employees = await seed_team(db)
    customer, app = await seed_identity(db, "Actual Customer")
    await db.applications.update_one(
        {"_id": ObjectId(app.require_id())},
        {"$set": {"assigned_to": employees[0][0].require_id()}},
    )
    documents = []
    for index in range(1006):
        payload = app.model_dump(by_alias=True, exclude={"id"})
        payload.update(
            application_code=f"BATCH-{index:06d}",
            assigned_to=employees[0][0].require_id(),
        )
        if index == 1005:
            payload["application_code"] = "AFS-APP-TAIL-1005"
        documents.append(payload)
    await db.applications.insert_many(documents)
    result = await grouped(db, owner, CollectionFilters(), 1, 200, None)
    assert result.data["total"] == 1
    assert result.data["items"][0]["application_count"] == 1007
    result = await grouped(
        db, owner, CollectionFilters(search="AFS-APP-TAIL-1005"), 1, 200, None
    )
    assert (
        result.data["total"] == 1 and result.data["items"][0]["application_count"] == 1
    )
    for key in [customer.customer_code, customer.mobile, "Actual Customer"]:
        assert (
            await grouped(db, owner, CollectionFilters(search=key), 1, 200, None)
        ).data["total"] == 1
    assert (
        await grouped(
            db,
            owner,
            CollectionFilters(
                search=customer.customer_code, application_status="draft"
            ),
            1,
            200,
            None,
        )
    ).data["total"] == 0
    assert (await grouped(db, employees[1][1], CollectionFilters(), 1, 200, None)).data[
        "total"
    ] == 0
    detail = await grouped(db, owner, CollectionFilters(), 1, 25, customer.require_id())
    second = await grouped(db, owner, CollectionFilters(), 2, 25, customer.require_id())
    assert len(detail.data["items"]) == 25
    assert not {row["id"] for row in detail.data["items"]} & {
        row["id"] for row in second.data["items"]
    }
    results = await search_records(db, owner, "AFS-APP-TAIL-1005")
    assert any(row["type"] == "application" for row in results)
    assert not await search_records(db, employees[1][1], "AFS-APP-TAIL-1005")
    assert await db.applications.count_documents({}) == 1007
    assert await db.customers.count_documents({}) == 1

    # More than one full default page of distinct customer groups; paginate in Mongo.
    for index in range(205):
        cid, uid = ObjectId(), str(ObjectId())
        await db.customers.insert_one(
            {
                "_id": cid,
                "user_id": uid,
                "is_deleted": False,
                "full_name": f"Group {index}",
                "customer_code": f"AFS-CUS-GROUP-{index}",
                "mobile": "9000000000",
            }
        )
        payload = app.model_dump(by_alias=True, exclude={"id"})
        payload.update(
            customer_id=str(cid), user_id=uid, application_code=f"AFS-APP-GROUP-{index}"
        )
        await db.applications.insert_one(payload)
    first = (await grouped(db, owner, CollectionFilters(), 1, 200, None)).data
    second = (await grouped(db, owner, CollectionFilters(), 2, 200, None)).data
    assert (
        first["total"] == 206
        and len(first["items"]) == 200
        and len(second["items"]) == 6
    )
    assert not {row["id"] for row in first["items"]} & {
        row["id"] for row in second["items"]
    }
    for size in [10, 25, 50, 100]:
        assert (
            len(
                (await grouped(db, owner, CollectionFilters(), 1, size, None)).data[
                    "items"
                ]
            )
            == size
        )


async def test_profile_edit_history_concurrency_and_snapshot(mock_db, mock_redis):
    from app.core.exceptions import ConflictError, ForbiddenError
    from app.features.customer.profile_edit import update_profile
    from app.features.customer.schemas import StaffProfileUpdate
    from app.features.customer.service import CustomerService

    owner, employees = await seed_team(mock_db)
    customer, application = await seed_identity(mock_db, "Before Name")
    await mock_db.applications.update_one(
        {"_id": ObjectId(application.require_id())},
        {"$set": {"assigned_to": employees[0][0].require_id()}},
    )
    service = CustomerService(mock_db, mock_redis)
    before = await mock_db.applications.find_one(
        {"_id": ObjectId(application.require_id())}
    )
    updated = await update_profile(
        service,
        mock_db,
        customer.require_id(),
        owner,
        StaffProfileUpdate(
            version=customer.version,
            full_name="Correct Name",
            reason="Verified spelling",
        ),
    )
    assert updated.full_name == "Correct Name"
    row = await mock_db.customers.find_one({"_id": ObjectId(customer.require_id())})
    assert row["profile_history"][0]["before"] == "Before Name"
    assert row["profile_history"][0]["after"] == "Correct Name"
    assert await mock_db.applications.find_one({"_id": before["_id"]}) == before
    with pytest.raises(ConflictError):
        await update_profile(
            service,
            mock_db,
            customer.require_id(),
            owner,
            StaffProfileUpdate(
                version=customer.version, full_name="Stale Name", reason="Stale edit"
            ),
        )
    with pytest.raises(ForbiddenError):
        await update_profile(
            service,
            mock_db,
            customer.require_id(),
            employees[0][1],
            StaffProfileUpdate(
                version=updated.version, pan_number="gdips8425l", reason="KYC change"
            ),
        )
    with pytest.raises(ForbiddenError):
        await update_profile(
            service,
            mock_db,
            customer.require_id(),
            employees[1][1],
            StaffProfileUpdate(
                version=updated.version, full_name="Forbidden", reason="Out of scope"
            ),
        )


async def test_bin_customer_dependency_and_retention(mock_db):
    from app.core.exceptions import ValidationError
    from app.features.bin.registry import get_resource
    from app.features.bin.service import BinService

    customer, application = await seed_identity(mock_db)
    row = await mock_db.customers.find_one({"_id": ObjectId(customer.require_id())})
    with pytest.raises(ValidationError):
        await get_resource("customers").guard(row, mock_db)
    owner, _ = await seed_team(mock_db)
    service = BinService(mock_db)
    await service.delete("applications", application.require_id(), owner)
    assert await mock_db.customers.count_documents({"is_deleted": False}) == 1
    assert await mock_db.applications.count_documents({"is_deleted": True}) == 1
    entries = await mock_db.bin_entries.find({}).to_list(None)
    assert len(entries) == 1
    await service.restore(str(entries[0]["_id"]), owner)
    assert await mock_db.applications.count_documents({"is_deleted": False}) == 1


@pytest.mark.parametrize("key", ["pan_number", "pan_card_number"])
def test_seeded_pan_keys_gain_validation_without_rewriting_schema(key):
    from app.features.customer.field_validation import (
        normalize_field_value,
        validate_field_value,
    )
    from app.features.customer.models import FormFieldDefinition

    field = FormFieldDefinition(key=key, label="PAN Number", field_type="text")
    value = normalize_field_value(field, " gdips8425l ")
    assert value == "GDIPS8425L" and validate_field_value(field, value) is None
    assert validate_field_value(field, "invalid") is not None


async def test_combined_intake_dimensions_and_document_filters(real_invoice_db):
    from datetime import timedelta

    from app.features.leads.document_collection import filter_options
    from app.utils.datetime import to_ist, utc_now

    db = real_invoice_db
    owner, employees = await seed_team(db)
    customer, application = await seed_identity(db, "Verified Profile")
    employee = employees[0][0].require_id()
    branch, designation, source, doc_type, bank, lead = [ObjectId() for _ in range(6)]
    await db.branches.insert_one({"_id": branch, "name": "Test Branch"})
    await db.designations.insert_one({"_id": designation, "name": "Test Designation"})
    await db.lead_sources.insert_one({"_id": source, "name": "Test Source"})
    await db.employees.update_one(
        {"_id": ObjectId(employee)},
        {"$set": {"branch_id": str(branch), "designation_id": str(designation)}},
    )
    await db.leads.insert_one(
        {
            "_id": lead,
            "lead_code": "AFS-LEAD-EXACT",
            "stage": "document_collection",
            "is_deleted": False,
            "source_id": str(source),
            "assigned_to": employee,
            "customer_id": customer.require_id(),
            "user_id": application.user_id,
            "product_id": application.product_id,
            "product_category": "loan",
            "full_name": "Stale lead name",
        }
    )
    now = utc_now()
    await db.applications.update_one(
        {"_id": ObjectId(application.require_id())},
        {
            "$set": {
                "lead_id": str(lead),
                "assigned_to": employee,
                "assigned_by": owner.require_id(),
                "assigned_at": now,
            }
        },
    )
    await db.application_documents.insert_one(
        {
            "application_id": application.require_id(),
            "document_type_id": str(doc_type),
            "is_deleted": False,
            "is_current": True,
            "document_status": "uploaded",
            "verification_status": "verified",
        }
    )
    await db.application_form_definitions.update_one(
        {"_id": ObjectId(application.form_definition_id)},
        {
            "$set": {
                "required_documents": [
                    {"document_type_id": str(doc_type), "required": True}
                ]
            }
        },
    )
    await db.daily_follow_ups.insert_one(
        {
            "application_id": application.require_id(),
            "is_deleted": False,
            "assigned_to": employee,
            "status": "FOLLOW UP PENDING",
            "due_date": now - timedelta(days=1),
            "banks": [{"option_id": str(bank), "name": "Test Bank"}],
        }
    )
    f = CollectionFilters(
        search="AFS-LEAD-EXACT",
        assigned_to=employee,
        assigned_by=owner.require_id(),
        assigned_from=to_ist(now).date(),
        assigned_until=to_ist(now).date(),
        product_id=application.product_id,
        product_category="loan",
        application_status="submitted",
        created_from=to_ist(now).date(),
        created_until=to_ist(now).date(),
        source_id=str(source),
        branch_id=str(branch),
        designation_id=str(designation),
        customer_status="active",
        follow_up_status="FOLLOW UP PENDING",
        follow_up_employee=employee,
        overdue=True,
        bank_id=str(bank),
        document_status="verified",
    )
    data = (await grouped(db, owner, f, 1, 200, None)).data
    assert data["total"] == 1 and data["items"][0]["name"] == "Verified Profile"
    choices = (await filter_options(db, owner)).data
    assert {"value": str(bank), "label": "Test Bank"} in choices["bank_id"]
    for state in ["pending", "rejected"]:
        assert (
            await grouped(
                db, owner, f.model_copy(update={"document_status": state}), 1, 200, None
            )
        ).data["total"] == 0
    assert (
        await grouped(
            db, owner, f.model_copy(update={"document_status": "missing"}), 1, 200, None
        )
    ).data["total"] == 0
    await db.application_documents.update_many({}, {"$set": {"is_current": False}})
    assert (
        await grouped(
            db, owner, f.model_copy(update={"document_status": "missing"}), 1, 200, None
        )
    ).data["total"] == 1
    assert (
        await db.applications.count_documents({}) == 1
        and await db.customers.count_documents({}) == 1
    )
