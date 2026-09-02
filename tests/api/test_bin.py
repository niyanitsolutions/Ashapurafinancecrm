"""Centralized Bin / Trash — Owner-only soft-delete, bulk delete, restore, and the
Bin listing. The 30-day purge job is covered in test_bin_cleanup.py.
"""

from app.features.customer.models import Application
from app.features.system_settings.models import InsuranceProduct, LeadSource, LoanProduct
from app.features.workflow_engine.indexes import ensure_workflow_engine_indexes
from app.features.workflow_engine.models import ApplicationWorkflow, LoanCaseDetails, WorkflowDefinition
from app.utils.datetime import utc_now
from app.utils.helpers import to_object_id


async def _lead_master_data(mock_db) -> dict:
    source_id = (await mock_db["lead_sources"].insert_one(LeadSource(name="Website").model_dump(by_alias=True, exclude={"id"}))).inserted_id
    loan_id = (await mock_db["loan_products"].insert_one(LoanProduct(name="Personal Loan").model_dump(by_alias=True, exclude={"id"}))).inserted_id
    await mock_db["insurance_products"].insert_one(InsuranceProduct(name="Health").model_dump(by_alias=True, exclude={"id"}))
    return {"source_id": str(source_id), "loan_product_id": str(loan_id)}


async def _create_lead(client, headers, lmd, mobile="9611110001", name="Ravi Kumar"):
    r = await client.post(
        "/api/v1/leads",
        json={
            "full_name": name, "mobile": mobile, "email": f"{mobile}@example.com",
            "source_id": lmd["source_id"], "product_category": "loan", "product_id": lmd["loan_product_id"],
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def test_owner_single_delete_moves_lead_to_bin_and_out_of_lists(client, mock_db, owner_headers):
    lmd = await _lead_master_data(mock_db)
    lead = await _create_lead(client, owner_headers, lmd)

    r = await client.delete(f"/api/v1/bin/leads/{lead['id']}", headers=owner_headers)
    assert r.status_code == 200, r.text
    entry = r.json()["data"]
    assert entry["module_label"] == "Leads"
    assert entry["stage_label"] == "Fresh"
    assert entry["record_code"] == lead["lead_code"]
    assert entry["deleted_by_name"]  # resolved to a name/mobile, not just an id
    assert entry["purge_at"] > entry["deleted_at"]

    # Gone from the normal list + counts.
    listing = await client.get("/api/v1/leads", headers=owner_headers)
    assert all(item["id"] != lead["id"] for item in listing.json()["data"])
    counts = await client.get("/api/v1/leads/counts", headers=owner_headers)
    assert counts.json()["data"]["fresh"] == 0

    # Present in the Bin.
    bin_list = await client.get("/api/v1/bin", headers=owner_headers)
    assert bin_list.status_code == 200, bin_list.text
    assert any(e["record_code"] == lead["lead_code"] and e["resource_key"] == "leads" for e in bin_list.json()["data"])


async def test_employee_cannot_delete_or_view_bin(client, mock_db, owner_headers, employee_headers):
    lmd = await _lead_master_data(mock_db)
    lead = await _create_lead(client, owner_headers, lmd)

    assert (await client.delete(f"/api/v1/bin/leads/{lead['id']}", headers=employee_headers)).status_code == 403
    assert (await client.get("/api/v1/bin", headers=employee_headers)).status_code == 403
    assert (
        await client.post("/api/v1/bin/leads/bulk-delete", json={"document_ids": [lead["id"]]}, headers=employee_headers)
    ).status_code == 403
    # Untouched by the rejected calls.
    assert (await client.get(f"/api/v1/leads/{lead['id']}", headers=owner_headers)).status_code == 200


async def test_bulk_delete_is_one_operation_and_reports_skips(client, mock_db, owner_headers):
    lmd = await _lead_master_data(mock_db)
    leads = [await _create_lead(client, owner_headers, lmd, mobile=f"961111100{i}") for i in range(3)]
    ids = [lead["id"] for lead in leads]

    r = await client.post(
        "/api/v1/bin/leads/bulk-delete",
        json={"document_ids": [*ids, "000000000000000000000000"]},  # last id doesn't exist -> skipped
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert set(body["deleted"]) == set(ids)
    assert len(body["skipped"]) == 1

    bin_list = await client.get("/api/v1/bin?module=leads", headers=owner_headers)
    assert {e["document_id"] for e in bin_list.json()["data"]} == set(ids)

    # A single bulk audit row, not one per record.
    assert await mock_db["audit_logs"].count_documents({"event_type": "bin_records_bulk_deleted"}) == 1


async def test_restore_returns_the_lead_to_normal_lists_and_out_of_bin(client, mock_db, owner_headers):
    lmd = await _lead_master_data(mock_db)
    lead = await _create_lead(client, owner_headers, lmd)
    entry = (await client.delete(f"/api/v1/bin/leads/{lead['id']}", headers=owner_headers)).json()["data"]

    r = await client.post(f"/api/v1/bin/{entry['id']}/restore", headers=owner_headers)
    assert r.status_code == 200, r.text

    listing = await client.get("/api/v1/leads", headers=owner_headers)
    assert any(item["id"] == lead["id"] for item in listing.json()["data"])
    bin_list = await client.get("/api/v1/bin", headers=owner_headers)
    assert all(e["record_code"] != lead["lead_code"] for e in bin_list.json()["data"])

    # Restoring twice is refused.
    assert (await client.post(f"/api/v1/bin/{entry['id']}/restore", headers=owner_headers)).status_code == 409


async def test_double_delete_is_refused(client, mock_db, owner_headers):
    lmd = await _lead_master_data(mock_db)
    lead = await _create_lead(client, owner_headers, lmd)
    assert (await client.delete(f"/api/v1/bin/leads/{lead['id']}", headers=owner_headers)).status_code == 200
    assert (await client.delete(f"/api/v1/bin/leads/{lead['id']}", headers=owner_headers)).status_code == 404


async def test_customer_delete_guard_blocks_when_an_open_case_exists(client, mock_db, owner_headers):
    now = utc_now()
    customer_id = (
        await mock_db["customers"].insert_one(
            {"full_name": "Open Case Customer", "mobile": "9631110001", "is_deleted": False, "status": "active",
             "created_at": now, "updated_at": now, "version": 1}
        )
    ).inserted_id
    await mock_db["application_workflows"].insert_one(
        {"case_code": "AFS-LOAN-GUARD", "case_type": "loan", "application_id": "app-g", "customer_id": str(customer_id),
         "product_id": "p", "product_category": "loan", "current_status": "credit_evaluation", "pending_document_type_ids": [],
         "loan_details": {}, "is_deleted": False, "status": "active", "created_at": now, "updated_at": now, "version": 1}
    )

    r = await client.delete(f"/api/v1/bin/customers/{customer_id}", headers=owner_headers)
    assert r.status_code == 422, r.text
    # Customer not soft-deleted.
    assert (await mock_db["customers"].find_one({"_id": customer_id}))["is_deleted"] is False


async def test_resources_endpoint_lists_deletable_record_types(client, mock_db, owner_headers):
    r = await client.get("/api/v1/bin/resources", headers=owner_headers)
    assert r.status_code == 200, r.text
    keys = {row["key"] for row in r.json()["data"]}
    assert {"leads", "loan_cases", "insurance_cases", "customers"} <= keys
    # Config/master-data must NOT be deletable.
    assert "loan_products" not in keys and "roles" not in keys and "reminder_rules" not in keys


async def test_unknown_resource_key_is_rejected(client, mock_db, owner_headers):
    assert (await client.delete("/api/v1/bin/loan_products/000000000000000000000000", headers=owner_headers)).status_code == 422


# ---------------------------------------------------------------------- Loan case delete → list consistency
# Regression for the production bug: after soft-deleting a Loan case, the next
# `GET /loan-cases` (and /counts) 500'd because `_sync_new_cases` tried to re-create a
# case for the still-`submitted` Application — and the unique `application_workflows.
# application_id` index counts the soft-deleted row (DuplicateKeyError).


async def _seed_loan_new_customer_def(mock_db):
    await ensure_workflow_engine_indexes(mock_db)
    await mock_db["workflow_definitions"].insert_one(
        WorkflowDefinition(
            case_type="loan", status="new_customer", label="New Customer", sequence=1,
            allowed_next_statuses=["credit_evaluation", "rejected"], audit_event="loan_case_created",
        ).model_dump(by_alias=True, exclude={"id"})
    )


async def _make_loan_case(mock_db, code):
    now = utc_now()
    app = Application(
        application_code=f"AFS-APP-{code}", user_id="u1", customer_id="c1",
        product_category="loan", product_id="p1", form_definition_id="f1", status="submitted",
    )
    app_res = await mock_db["applications"].insert_one(app.model_dump(by_alias=True, exclude={"id"}))
    wf = ApplicationWorkflow(
        case_code=f"AFS-LOAN-{code}", case_type="loan", application_id=str(app_res.inserted_id), customer_id="c1",
        product_id="p1", product_category="loan", current_status="new_customer",
        moved_to_loan_management_at=now, loan_details=LoanCaseDetails(),
    )
    wf_res = await mock_db["application_workflows"].insert_one(wf.model_dump(by_alias=True, exclude={"id"}))
    return str(wf_res.inserted_id)


async def _loan_case_codes(client, headers, status="new_customer"):
    r = await client.get(f"/api/v1/loan-cases?status={status}", headers=headers)
    assert r.status_code == 200, r.text
    return [c["case_code"] for c in r.json()["data"]]


async def test_single_loan_delete_leaves_the_rest_of_the_list_working(client, mock_db, owner_headers):
    await _seed_loan_new_customer_def(mock_db)
    for code in ("000016", "000017"):
        await _make_loan_case(mock_db, code)
    doomed = await _make_loan_case(mock_db, "000018")

    r = await client.delete(f"/api/v1/bin/loan_cases/{doomed}", headers=owner_headers)
    assert r.status_code == 200, r.text

    # The list AND the counts endpoint must both still work (both call _sync_new_cases).
    assert set(await _loan_case_codes(client, owner_headers)) == {"AFS-LOAN-000016", "AFS-LOAN-000017"}
    counts = await client.get("/api/v1/loan-cases/counts", headers=owner_headers)
    assert counts.status_code == 200, counts.text
    assert counts.json()["data"]["new_customer"] == 2

    # And a second list call must not resurrect the deleted case (no re-sync).
    assert "AFS-LOAN-000018" not in await _loan_case_codes(client, owner_headers)
    assert any(e["record_code"] == "AFS-LOAN-000018" for e in (await client.get("/api/v1/bin", headers=owner_headers)).json()["data"])


async def test_deleting_the_only_loan_case_returns_a_clean_empty_list(client, mock_db, owner_headers):
    await _seed_loan_new_customer_def(mock_db)
    only = await _make_loan_case(mock_db, "000018")

    assert (await client.delete(f"/api/v1/bin/loan_cases/{only}", headers=owner_headers)).status_code == 200

    r = await client.get("/api/v1/loan-cases?status=new_customer", headers=owner_headers)
    assert r.status_code == 200, r.text  # NOT a 500
    body = r.json()
    assert body["data"] == []
    assert body["meta"]["pagination"]["total"] == 0


async def test_restore_returns_loan_case_to_original_stage_and_the_active_list(client, mock_db, owner_headers):
    await _seed_loan_new_customer_def(mock_db)
    case_id = await _make_loan_case(mock_db, "000018")
    entry = (await client.delete(f"/api/v1/bin/loan_cases/{case_id}", headers=owner_headers)).json()["data"]
    assert entry["stage_label"] == "New Customer"

    r = await client.post(f"/api/v1/bin/{entry['id']}/restore", headers=owner_headers)
    assert r.status_code == 200, r.text

    assert "AFS-LOAN-000018" in await _loan_case_codes(client, owner_headers)
    restored = await mock_db["application_workflows"].find_one({"_id": to_object_id(case_id)})
    assert restored["current_status"] == "new_customer"  # original stage, untouched
    assert restored["is_deleted"] is False and restored["status"] == "active"
    assert all(e["record_code"] != "AFS-LOAN-000018" for e in (await client.get("/api/v1/bin", headers=owner_headers)).json()["data"])


async def test_bulk_loan_delete_leaves_the_remaining_cases_listable(client, mock_db, owner_headers):
    await _seed_loan_new_customer_def(mock_db)
    ids = {code: await _make_loan_case(mock_db, code) for code in ("000016", "000017", "000018", "000024", "000025")}

    r = await client.post(
        "/api/v1/bin/loan_cases/bulk-delete",
        json={"document_ids": [ids["000016"], ids["000017"], ids["000018"]]}, headers=owner_headers,
    )
    assert r.status_code == 200, r.text

    assert set(await _loan_case_codes(client, owner_headers)) == {"AFS-LOAN-000024", "AFS-LOAN-000025"}
    counts = await client.get("/api/v1/loan-cases/counts", headers=owner_headers)
    assert counts.status_code == 200 and counts.json()["data"]["new_customer"] == 2
