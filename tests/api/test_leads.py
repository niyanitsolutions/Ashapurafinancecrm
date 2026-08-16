"""End-to-end tests for Module 6A (Lead Foundation): CRUD, duplicate detection
(flags, never blocks), assignment, Notes/Activities merged into one Timeline,
search/filter, CSV export, permission gating (leads:leads), and that Dashboard's
today_leads/assigned_leads widgets now compute real data (decision 039).
"""

from app.features.customer.models import ApplicationFormDefinition, FormFieldDefinition
from app.features.dashboard.constants import WidgetType
from app.features.dashboard.models import DashboardWidget
from app.features.system_settings.models import InsuranceProduct, LeadSource, LoanProduct


async def _lead_master_data(mock_db) -> dict:
    source = LeadSource(name="Website")
    loan_product = LoanProduct(name="Personal Loan")
    insurance_product = InsuranceProduct(name="Health")

    source_id = (await mock_db["lead_sources"].insert_one(source.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    loan_id = (await mock_db["loan_products"].insert_one(loan_product.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    insurance_id = (await mock_db["insurance_products"].insert_one(insurance_product.model_dump(by_alias=True, exclude={"id"}))).inserted_id

    return {"source_id": str(source_id), "loan_product_id": str(loan_id), "insurance_product_id": str(insurance_id)}


def _lead_payload(lead_master_data, mobile="9611111111", **overrides):
    payload = {
        "full_name": "Ravi Kumar",
        "mobile": mobile,
        "email": "ravi@example.com",
        "source_id": lead_master_data["source_id"],
        "product_category": "loan",
        "product_id": lead_master_data["loan_product_id"],
        "remarks": "Interested in a personal loan",
    }
    payload.update(overrides)
    return payload


async def _create_lead(client, headers, lead_master_data, **overrides):
    r = await client.post("/api/v1/leads", json=_lead_payload(lead_master_data, **overrides), headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _create_employee(client, owner_headers, master_data, mobile="9511111111", email="lead.employee@example.com"):
    payload = {
        "mobile": mobile,
        "initial_password": "InitialPass1!",
        "first_name": "Lead",
        "last_name": "Handler",
        "email": email,
        "department_id": master_data["department_id"],
        "designation_id": master_data["designation_id"],
        "branch_id": master_data["branch_id"],
        "joining_date": "2026-01-15",
        "employment_type": "full_time",
    }
    r = await client.post("/api/v1/employees", json=payload, headers=owner_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


# ---------------------------------------------------------------------- create / read / update


async def test_create_lead_and_get(client, mock_db, owner_headers):
    lmd = await _lead_master_data(mock_db)
    lead = await _create_lead(client, owner_headers, lmd)

    assert lead["lead_code"].startswith("AFS-LEAD-")
    assert lead["source_name"] == "Website"
    assert lead["product_name"] == "Personal Loan"
    assert lead["status"] == "new"
    assert lead["is_potential_duplicate"] is False

    r = await client.get(f"/api/v1/leads/{lead['id']}", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["full_name"] == "Ravi Kumar"


async def test_create_lead_never_validates_product_schema_fields(client, mock_db, owner_headers):
    """Regression test: Create Lead collects only basic lead info (Name/Mobile/Email/
    Source/Product/City/Preferred Amount/Remarks) — the Product Schema Engine's own
    required fields (e.g. a Personal Loan's Loan Amount/Purpose/Tenure/Employer) belong
    solely to the Customer's later Application, and must never block Lead creation even
    when the selected product has a schema with required fields and no product_form_data
    is supplied (the Create Lead page never collects or sends it)."""
    lmd = await _lead_master_data(mock_db)
    schema = ApplicationFormDefinition(
        product_category="loan",
        product_id=lmd["loan_product_id"],
        status="active",
        fields=[
            FormFieldDefinition(key="loan_amount", label="Loan Amount", field_type="number", required=True, section="Basic Information"),
            FormFieldDefinition(key="loan_purpose", label="Loan Purpose", field_type="text", required=True, section="Basic Information"),
            FormFieldDefinition(key="employer_name", label="Employer Name", field_type="text", required=True, section="Basic Information"),
        ],
    )
    await mock_db["application_form_definitions"].insert_one(schema.model_dump(by_alias=True, exclude={"id"}))

    lead = await _create_lead(client, owner_headers, lmd)  # no product_form_data supplied
    assert lead["lead_code"].startswith("AFS-LEAD-")
    assert lead["form_definition_id"] is not None  # still stamped, for later reference
    assert lead["product_form_data"] is None


async def test_create_lead_rejects_unknown_source_and_product(client, mock_db, owner_headers):
    lmd = await _lead_master_data(mock_db)

    r = await client.post("/api/v1/leads", json=_lead_payload(lmd, source_id="000000000000000000000000"), headers=owner_headers)
    assert r.status_code == 422, r.text

    r = await client.post("/api/v1/leads", json=_lead_payload(lmd, product_id="000000000000000000000000"), headers=owner_headers)
    assert r.status_code == 422, r.text


async def test_update_lead(client, mock_db, owner_headers):
    lmd = await _lead_master_data(mock_db)
    lead = await _create_lead(client, owner_headers, lmd)

    r = await client.patch(f"/api/v1/leads/{lead['id']}", json={"remarks": "Called back, wants a callback tomorrow"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["remarks"] == "Called back, wants a callback tomorrow"


# ---------------------------------------------------------------------- duplicate detection


async def test_duplicate_detection_flags_but_never_blocks(client, mock_db, owner_headers):
    lmd = await _lead_master_data(mock_db)
    first = await _create_lead(client, owner_headers, lmd, mobile="9622222222")
    assert first["is_potential_duplicate"] is False

    second = await _create_lead(client, owner_headers, lmd, mobile="9622222222")
    assert second["is_potential_duplicate"] is True

    detail = await client.get(f"/api/v1/leads/{second['id']}", headers=owner_headers)
    assert detail.json()["data"]["duplicate_of_lead_ids"] == [first["id"]]


async def test_check_duplicate_endpoint(client, mock_db, owner_headers):
    lmd = await _lead_master_data(mock_db)
    lead = await _create_lead(client, owner_headers, lmd, mobile="9633333333")

    r = await client.get("/api/v1/leads/check-duplicate?mobile=9633333333", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert [m["id"] for m in r.json()["data"]["matches"]] == [lead["id"]]

    r = await client.get("/api/v1/leads/check-duplicate?mobile=9000000000", headers=owner_headers)
    assert r.json()["data"]["matches"] == []


# ---------------------------------------------------------------------- search / filter


async def test_list_leads_search_and_filter(client, mock_db, owner_headers):
    lmd = await _lead_master_data(mock_db)
    await _create_lead(client, owner_headers, lmd, mobile="9644444441", full_name="Amit Shah")
    await _create_lead(
        client, owner_headers, lmd, mobile="9644444442", full_name="Sunita Rao",
        product_category="insurance", product_id=lmd["insurance_product_id"],
    )

    r = await client.get("/api/v1/leads?search=Amit", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert [x["full_name"] for x in r.json()["data"]] == ["Amit Shah"]

    r = await client.get("/api/v1/leads?product_category=insurance", headers=owner_headers)
    assert [x["full_name"] for x in r.json()["data"]] == ["Sunita Rao"]

    r = await client.get("/api/v1/leads", headers=owner_headers)
    assert len(r.json()["data"]) == 2
    assert r.json()["meta"]["pagination"]["total"] == 2


# ---------------------------------------------------------------------- assignment


async def test_assign_and_unassign_lead(client, mock_db, owner_headers, master_data):
    lmd = await _lead_master_data(mock_db)
    lead = await _create_lead(client, owner_headers, lmd)
    employee = await _create_employee(client, owner_headers, master_data)

    r = await client.post("/api/v1/leads/000000000000000000000000/assign", json={"employee_id": "bogus"}, headers=owner_headers)
    assert r.status_code in (404, 422), r.text

    r = await client.post(f"/api/v1/leads/{lead['id']}/assign", json={"employee_id": "000000000000000000000000"}, headers=owner_headers)
    assert r.status_code == 422, r.text

    r = await client.post(f"/api/v1/leads/{lead['id']}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["assigned_to"] == employee["id"]
    assert r.json()["data"]["assigned_to_name"] == employee["display_name"]

    r = await client.post(f"/api/v1/leads/{lead['id']}/unassign", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["assigned_to"] is None


async def test_assign_lead_rejects_inactive_employee(client, mock_db, owner_headers, master_data):
    lmd = await _lead_master_data(mock_db)
    lead = await _create_lead(client, owner_headers, lmd)
    employee = await _create_employee(client, owner_headers, master_data, mobile="9766666601", email="inactive.assignee@example.com")

    r = await client.patch(f"/api/v1/employees/{employee['id']}/deactivate", headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.post(f"/api/v1/leads/{lead['id']}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)
    assert r.status_code == 422, r.text


async def test_assign_lead_works_across_ownership_boundary_for_permitted_actor(client, mock_db, owner_headers, master_data):
    """Assignment is gated by the coarser `leads:leads:assign` permission, never by
    per-record ownership — an employee holding `assign` must be able to reassign a lead
    they neither created nor are currently assigned to. This must keep working exactly
    as before after the created_by/assigned_to visibility rework (see get_lead_scoped)."""
    lmd = await _lead_master_data(mock_db)
    lead = await _create_lead(client, owner_headers, lmd)  # created_by = Owner

    assigner = await _create_employee(client, owner_headers, master_data, mobile="9766666602", email="assigner@example.com")
    await _grant_leads_assign(client, owner_headers, assigner["id"], role_name="Assigner Role")
    r = await client.post("/api/v1/auth/login", json={"mobile": "9766666602", "password": "InitialPass1!"})
    assigner_headers = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    target = await _create_employee(client, owner_headers, master_data, mobile="9766666603", email="target@example.com")

    r = await client.post(f"/api/v1/leads/{lead['id']}/assign", json={"employee_id": target["id"]}, headers=assigner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["assigned_to"] == target["id"]


# ---------------------------------------------------------------------- lead visibility scoping (created_by OR assigned_to)


async def _full_leads_permission_id(client, owner_headers) -> str:
    # Distinct from `_leads_permission_id` (below, in the eligible-assignees section)
    # which deliberately only registers ["view", "assign"] for its own narrower tests —
    # this one needs "create"/"edit" too, matching the real seeded catalog's full action
    # set for leads:leads.
    r = await client.post(
        "/api/v1/permissions", json={"module": "leads", "resource": "leads", "actions": ["view", "create", "edit", "assign", "export"]},
        headers=owner_headers,
    )
    if r.status_code == 200:
        return r.json()["data"]["id"]
    existing = await client.get("/api/v1/permissions", headers=owner_headers)
    return next(p["id"] for p in existing.json()["data"] if p["module"] == "leads" and p["resource"] == "leads")


async def _grant_leads_view_create(client, owner_headers, employee_id, role_name="Lead Handler"):
    leads_permission_id = await _full_leads_permission_id(client, owner_headers)
    role = await client.post("/api/v1/roles", json={"name": role_name}, headers=owner_headers)
    role_id = role.json()["data"]["id"]
    await client.put(
        f"/api/v1/roles/{role_id}/permissions",
        json={"grants": [{"permission_id": leads_permission_id, "granted_actions": ["view", "create", "edit"]}]},
        headers=owner_headers,
    )
    await client.post(f"/api/v1/roles/{role_id}/assign", json={"employee_id": employee_id}, headers=owner_headers)


async def _grant_leads_actions(client, owner_headers, employee_id, actions, role_name):
    """Grants exactly `actions` (a subset of view/create/edit/assign/export) on
    leads:leads to a fresh role assigned to `employee_id` — for the explicit
    view-only / view+create / view+create+edit / no-permission truth-table tests below.
    An empty `actions` list assigns a role with zero grants (still distinct from "no
    role at all" — both must behave identically as "no permission")."""
    leads_permission_id = await _full_leads_permission_id(client, owner_headers)
    role = await client.post("/api/v1/roles", json={"name": role_name}, headers=owner_headers)
    role_id = role.json()["data"]["id"]
    grants = [{"permission_id": leads_permission_id, "granted_actions": actions}] if actions else []
    await client.put(f"/api/v1/roles/{role_id}/permissions", json={"grants": grants}, headers=owner_headers)
    await client.post(f"/api/v1/roles/{role_id}/assign", json={"employee_id": employee_id}, headers=owner_headers)


async def _login(client, mobile, password="InitialPass1!"):
    r = await client.post("/api/v1/auth/login", json={"mobile": mobile, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def test_owner_sees_full_unassigned_pool(client, mock_db, owner_headers, master_data):
    lmd = await _lead_master_data(mock_db)
    employee_a = await _create_employee(client, owner_headers, master_data, mobile="9766666701", email="a@example.com")
    employee_b = await _create_employee(client, owner_headers, master_data, mobile="9766666702", email="b@example.com")
    await _grant_leads_view_create(client, owner_headers, employee_a["id"], role_name="A Role")
    await _grant_leads_view_create(client, owner_headers, employee_b["id"], role_name="B Role")
    headers_a = await _login(client, "9766666701")
    headers_b = await _login(client, "9766666702")

    lead_a = await _create_lead(client, headers_a, lmd, mobile="9611111101")
    lead_b = await _create_lead(client, headers_b, lmd, mobile="9611111102")

    r = await client.get("/api/v1/leads?assigned_to=__unassigned__", headers=owner_headers)
    assert r.status_code == 200, r.text
    ids = {x["id"] for x in r.json()["data"]}
    assert {lead_a["id"], lead_b["id"]} <= ids


async def test_employee_unassigned_view_scoped_to_own_created_leads_only(client, mock_db, owner_headers, master_data):
    lmd = await _lead_master_data(mock_db)
    employee_a = await _create_employee(client, owner_headers, master_data, mobile="9766666703", email="a2@example.com")
    employee_b = await _create_employee(client, owner_headers, master_data, mobile="9766666704", email="b2@example.com")
    await _grant_leads_view_create(client, owner_headers, employee_a["id"], role_name="A2 Role")
    await _grant_leads_view_create(client, owner_headers, employee_b["id"], role_name="B2 Role")
    headers_a = await _login(client, "9766666703")
    headers_b = await _login(client, "9766666704")

    lead_a = await _create_lead(client, headers_a, lmd, mobile="9611111103")
    lead_b = await _create_lead(client, headers_b, lmd, mobile="9611111104")

    r = await client.get("/api/v1/leads?assigned_to=__unassigned__", headers=headers_a)
    assert r.status_code == 200, r.text
    assert [x["id"] for x in r.json()["data"]] == [lead_a["id"]]

    r = await client.get("/api/v1/leads?assigned_to=__unassigned__", headers=headers_b)
    assert [x["id"] for x in r.json()["data"]] == [lead_b["id"]]


async def test_employee_cannot_see_meta_captured_unassigned_lead(client, mock_db, owner_headers, master_data):
    lmd = await _lead_master_data(mock_db)
    employee = await _create_employee(client, owner_headers, master_data, mobile="9766666705", email="c2@example.com")
    await _grant_leads_view_create(client, owner_headers, employee["id"], role_name="C2 Role")
    headers = await _login(client, "9766666705")

    meta_lead = await _create_lead(client, owner_headers, lmd, mobile="9611111105")
    # Simulates lead_capture/service.py::_process_raw_payload's deliberate
    # created_by=None stamp for a Meta-captured lead, without spinning up the full
    # webhook/HMAC flow — see plan section A6.
    from app.utils.helpers import to_object_id

    await mock_db["leads"].update_one({"_id": to_object_id(meta_lead["id"])}, {"$set": {"created_by": None}})

    r = await client.get("/api/v1/leads?assigned_to=__unassigned__", headers=headers)
    assert r.status_code == 200, r.text
    assert meta_lead["id"] not in {x["id"] for x in r.json()["data"]}

    r = await client.get("/api/v1/leads?assigned_to=__unassigned__", headers=owner_headers)
    assert meta_lead["id"] in {x["id"] for x in r.json()["data"]}


async def test_get_lead_scoped_allows_own_unassigned_draft_denies_others(client, mock_db, owner_headers, master_data):
    lmd = await _lead_master_data(mock_db)
    employee_a = await _create_employee(client, owner_headers, master_data, mobile="9766666706", email="a3@example.com")
    employee_b = await _create_employee(client, owner_headers, master_data, mobile="9766666707", email="b3@example.com")
    await _grant_leads_view_create(client, owner_headers, employee_a["id"], role_name="A3 Role")
    await _grant_leads_view_create(client, owner_headers, employee_b["id"], role_name="B3 Role")
    headers_a = await _login(client, "9766666706")
    headers_b = await _login(client, "9766666707")

    lead_a = await _create_lead(client, headers_a, lmd, mobile="9611111106")

    r = await client.get(f"/api/v1/leads/{lead_a['id']}", headers=headers_a)
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/leads/{lead_a['id']}", headers=headers_b)
    assert r.status_code == 403, r.text


async def test_check_duplicate_includes_own_unassigned_leads(client, mock_db, owner_headers, master_data):
    lmd = await _lead_master_data(mock_db)
    employee = await _create_employee(client, owner_headers, master_data, mobile="9766666708", email="d3@example.com")
    await _grant_leads_view_create(client, owner_headers, employee["id"], role_name="D3 Role")
    headers = await _login(client, "9766666708")

    lead = await _create_lead(client, headers, lmd, mobile="9611111107")

    r = await client.get("/api/v1/leads/check-duplicate?mobile=9611111107", headers=headers)
    assert r.status_code == 200, r.text
    assert [m["id"] for m in r.json()["data"]["matches"]] == [lead["id"]]


# ---------------------------------------------------------------------- lookup data (Create Lead form)


async def test_lead_lookup_available_to_leads_view_without_settings_permission(client, mock_db, owner_headers, master_data):
    """Regression test for a real production bug: an employee with only leads:leads
    granted (no system_settings:lead_sources/loan_products/insurance_products) must be
    able to load the Create Lead form's dropdowns via GET /leads/lookup — it must not
    require Settings administration access."""
    lmd = await _lead_master_data(mock_db)
    employee = await _create_employee(client, owner_headers, master_data, mobile="9766668001", email="lookup@example.com")
    await _grant_leads_view_create(client, owner_headers, employee["id"], role_name="Lookup Role")
    headers = await _login(client, "9766668001")

    r = await client.get("/api/v1/leads/lookup", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert any(s["id"] == lmd["source_id"] for s in data["sources"])
    assert any(p["id"] == lmd["loan_product_id"] for p in data["loan_products"])
    assert any(p["id"] == lmd["insurance_product_id"] for p in data["insurance_products"])

    # Confirm this employee genuinely has no Settings grant — the lookup succeeding is
    # not because they were accidentally also granted system_settings access.
    r = await client.get("/api/v1/lead-sources", headers=headers)
    assert r.status_code == 403, r.text


async def test_lead_lookup_denied_without_leads_view(client, mock_db, employee_headers):
    r = await client.get("/api/v1/leads/lookup", headers=employee_headers)
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------- permission truth table (view/create/edit independence)


async def test_leads_view_only_permission_truth_table(client, mock_db, owner_headers, master_data):
    lmd = await _lead_master_data(mock_db)
    employee = await _create_employee(client, owner_headers, master_data, mobile="9766667001", email="viewonly@example.com")
    await _grant_leads_actions(client, owner_headers, employee["id"], ["view"], role_name="View Only")
    headers = await _login(client, "9766667001")

    r = await client.get("/api/v1/leads", headers=headers)
    assert r.status_code == 200, r.text

    r = await client.post("/api/v1/leads", json=_lead_payload(lmd, mobile="9611112001"), headers=headers)
    assert r.status_code == 403, r.text
    assert "leads:leads:create" in r.json()["error"]["message"]

    existing = await _create_lead(client, owner_headers, lmd, mobile="9611112002")
    r = await client.patch(f"/api/v1/leads/{existing['id']}", json={"remarks": "attempt"}, headers=headers)
    assert r.status_code == 403, r.text
    assert "leads:leads:edit" in r.json()["error"]["message"]


async def test_leads_view_create_permission_truth_table(client, mock_db, owner_headers, master_data):
    lmd = await _lead_master_data(mock_db)
    employee = await _create_employee(client, owner_headers, master_data, mobile="9766667002", email="viewcreate@example.com")
    await _grant_leads_actions(client, owner_headers, employee["id"], ["view", "create"], role_name="View Create")
    headers = await _login(client, "9766667002")

    r = await client.get("/api/v1/leads", headers=headers)
    assert r.status_code == 200, r.text

    r = await client.post("/api/v1/leads", json=_lead_payload(lmd, mobile="9611112003"), headers=headers)
    assert r.status_code == 200, r.text

    existing = await _create_lead(client, owner_headers, lmd, mobile="9611112004")
    r = await client.patch(f"/api/v1/leads/{existing['id']}", json={"remarks": "attempt"}, headers=headers)
    assert r.status_code == 403, r.text
    assert "leads:leads:edit" in r.json()["error"]["message"]


async def test_leads_view_create_edit_permission_truth_table(client, mock_db, owner_headers, master_data):
    lmd = await _lead_master_data(mock_db)
    employee = await _create_employee(client, owner_headers, master_data, mobile="9766667003", email="full@example.com")
    await _grant_leads_actions(client, owner_headers, employee["id"], ["view", "create", "edit"], role_name="View Create Edit")
    headers = await _login(client, "9766667003")

    r = await client.get("/api/v1/leads", headers=headers)
    assert r.status_code == 200, r.text

    created = await _create_lead(client, headers, lmd, mobile="9611112005")
    r = await client.patch(f"/api/v1/leads/{created['id']}", json={"remarks": "attempt"}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["remarks"] == "attempt"


async def test_leads_no_permission_truth_table(client, mock_db, owner_headers, master_data):
    lmd = await _lead_master_data(mock_db)
    employee = await _create_employee(client, owner_headers, master_data, mobile="9766667004", email="none@example.com")
    await _grant_leads_actions(client, owner_headers, employee["id"], [], role_name="No Grants")
    headers = await _login(client, "9766667004")

    r = await client.get("/api/v1/leads", headers=headers)
    assert r.status_code == 403, r.text

    r = await client.post("/api/v1/leads", json=_lead_payload(lmd, mobile="9611112006"), headers=headers)
    assert r.status_code == 403, r.text

    existing = await _create_lead(client, owner_headers, lmd, mobile="9611112007")
    r = await client.patch(f"/api/v1/leads/{existing['id']}", json={"remarks": "attempt"}, headers=headers)
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------- notes / timeline


async def test_add_note_and_timeline_merges_activities_and_notes(client, mock_db, owner_headers):
    lmd = await _lead_master_data(mock_db)
    lead = await _create_lead(client, owner_headers, lmd)

    r = await client.post(f"/api/v1/leads/{lead['id']}/notes", json={"text": "Spoke to customer, follow up next week"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["text"] == "Spoke to customer, follow up next week"

    r = await client.get(f"/api/v1/leads/{lead['id']}/timeline", headers=owner_headers)
    assert r.status_code == 200, r.text
    entries = r.json()["data"]
    types = {e["type"] for e in entries}
    assert types == {"activity", "note"}
    event_types = {e["event_type"] for e in entries if e["type"] == "activity"}
    assert "created" in event_types
    assert "note_added" in event_types
    note_entry = next(e for e in entries if e["type"] == "note")
    assert note_entry["text"] == "Spoke to customer, follow up next week"


# ---------------------------------------------------------------------- export


async def test_export_leads_csv(client, mock_db, owner_headers):
    lmd = await _lead_master_data(mock_db)
    await _create_lead(client, owner_headers, lmd)

    r = await client.get("/api/v1/leads/export", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert "Ravi Kumar" in r.text


# ---------------------------------------------------------------------- permission gating


async def test_leads_require_permission_for_employee(client, mock_db, owner_headers, employee_headers):
    lmd = await _lead_master_data(mock_db)
    r = await client.post("/api/v1/leads", json=_lead_payload(lmd), headers=employee_headers)
    assert r.status_code == 403, r.text


async def test_leads_grantable_to_employee_via_role(client, mock_db, owner_headers, master_data):
    lmd = await _lead_master_data(mock_db)
    employee = await _create_employee(client, owner_headers, master_data, mobile="9655555555", email="grantee@example.com")
    r = await client.post("/api/v1/auth/login", json={"mobile": "9655555555", "password": "InitialPass1!"})
    own_headers = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    r = await client.post("/api/v1/leads", json=_lead_payload(lmd), headers=own_headers)
    assert r.status_code == 403, r.text

    permission = await client.post(
        "/api/v1/permissions", json={"module": "leads", "resource": "leads", "actions": ["view", "create"]}, headers=owner_headers
    )
    role = await client.post("/api/v1/roles", json={"name": "Lead Handler"}, headers=owner_headers)
    role_id = role.json()["data"]["id"]
    await client.put(
        f"/api/v1/roles/{role_id}/permissions",
        json={"grants": [{"permission_id": permission.json()["data"]["id"], "granted_actions": ["view", "create"]}]},
        headers=owner_headers,
    )
    await client.post(f"/api/v1/roles/{role_id}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)

    r = await client.post("/api/v1/leads", json=_lead_payload(lmd), headers=own_headers)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------- dashboard widget integration


async def test_create_and_update_lead_with_city_and_preferred_amount(client, mock_db, owner_headers):
    lmd = await _lead_master_data(mock_db)
    lead = await _create_lead(client, owner_headers, lmd, city="Hyderabad", preferred_amount=500000)

    assert lead["city"] == "Hyderabad"
    assert lead["preferred_amount"] == 500000

    r = await client.get(f"/api/v1/leads/{lead['id']}", headers=owner_headers)
    assert r.json()["data"]["city"] == "Hyderabad"
    assert r.json()["data"]["preferred_amount"] == 500000

    r = await client.patch(f"/api/v1/leads/{lead['id']}", json={"city": "Bangalore", "preferred_amount": 750000}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["city"] == "Bangalore"
    assert r.json()["data"]["preferred_amount"] == 750000


async def test_create_lead_rejects_non_positive_preferred_amount(client, mock_db, owner_headers):
    lmd = await _lead_master_data(mock_db)
    r = await client.post("/api/v1/leads", json=_lead_payload(lmd, preferred_amount=0), headers=owner_headers)
    assert r.status_code == 422, r.text


async def test_create_lead_without_city_or_amount_still_works(client, mock_db, owner_headers):
    lmd = await _lead_master_data(mock_db)
    lead = await _create_lead(client, owner_headers, lmd)
    assert lead["city"] is None
    assert lead["preferred_amount"] is None


# ---------------------------------------------------------------------- eligible assignees


async def _leads_permission_id(client, owner_headers) -> str:
    r = await client.post(
        "/api/v1/permissions", json={"module": "leads", "resource": "leads", "actions": ["view", "assign"]}, headers=owner_headers
    )
    if r.status_code == 200:
        return r.json()["data"]["id"]
    # Already created by an earlier call in this test — look it up instead.
    existing = await client.get("/api/v1/permissions", headers=owner_headers)
    return next(p["id"] for p in existing.json()["data"] if p["module"] == "leads" and p["resource"] == "leads")


async def _loan_management_permission_id(client, owner_headers) -> str:
    r = await client.post(
        "/api/v1/permissions", json={"module": "loan_management", "resource": "applications", "actions": ["view"]}, headers=owner_headers
    )
    if r.status_code == 200:
        return r.json()["data"]["id"]
    existing = await client.get("/api/v1/permissions", headers=owner_headers)
    return next(p["id"] for p in existing.json()["data"] if p["module"] == "loan_management" and p["resource"] == "applications")


async def _grant_leads_assign(client, owner_headers, employee_id, role_name="Assigner"):
    # `LeadService.list_eligible_assignees` deliberately gates eligibility on module
    # access (any granted permission under the lead's product-category module, e.g.
    # "loan_management" — see PRODUCT_CATEGORY_MODULE), not a separate `leads:assign`
    # permission (its own docstring: "an Owner already grants module access... should
    # never need to configure a second, separate assignment permission"). Both are
    # granted on the same role here so this helper still also covers the
    # `POST /leads/{id}/assign` action itself, which IS gated on `leads:leads:assign`.
    leads_permission_id = await _leads_permission_id(client, owner_headers)
    loan_permission_id = await _loan_management_permission_id(client, owner_headers)
    role = await client.post("/api/v1/roles", json={"name": role_name}, headers=owner_headers)
    role_id = role.json()["data"]["id"]
    await client.put(
        f"/api/v1/roles/{role_id}/permissions",
        json={
            "grants": [
                {"permission_id": leads_permission_id, "granted_actions": ["view", "assign"]},
                {"permission_id": loan_permission_id, "granted_actions": ["view"]},
            ]
        },
        headers=owner_headers,
    )
    await client.post(f"/api/v1/roles/{role_id}/assign", json={"employee_id": employee_id}, headers=owner_headers)


async def test_eligible_assignees_empty_when_no_employees(client, mock_db, owner_headers):
    lmd = await _lead_master_data(mock_db)
    lead = await _create_lead(client, owner_headers, lmd)
    r = await client.get(f"/api/v1/leads/eligible-assignees?product_category=loan&product_id={lmd['loan_product_id']}", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []
    assert lead is not None  # sanity: lead exists but is irrelevant to this endpoint


async def test_eligible_assignees_excludes_employees_without_assign_permission(client, mock_db, owner_headers, master_data):
    await _create_employee(client, owner_headers, master_data, mobile="9711111111", email="noperm@example.com")
    r = await client.get("/api/v1/leads/eligible-assignees?product_category=loan", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []


async def test_eligible_assignees_excludes_inactive_employees(client, mock_db, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data, mobile="9722222222", email="inactive@example.com")
    await _grant_leads_assign(client, owner_headers, employee["id"])
    r = await client.patch(f"/api/v1/employees/{employee['id']}/deactivate", headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.get("/api/v1/leads/eligible-assignees?product_category=loan", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []


async def test_eligible_assignees_includes_active_permitted_employee_with_context(client, mock_db, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data, mobile="9733333333", email="eligible@example.com")
    await _grant_leads_assign(client, owner_headers, employee["id"])

    r = await client.get("/api/v1/leads/eligible-assignees?product_category=loan", headers=owner_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == employee["id"]
    assert data[0]["display_name"] == employee["display_name"]
    assert data[0]["designation_name"] == "Executive"
    assert data[0]["branch_name"] == "Head Office"
    assert data[0]["current_lead_count"] == 0
    assert data[0]["recommended"] is True


async def test_eligible_assignees_recommends_product_match_and_lowest_workload(client, mock_db, owner_headers, master_data):
    lmd = await _lead_master_data(mock_db)

    specialist = await _create_employee(client, owner_headers, master_data, mobile="9744444444", email="specialist@example.com")
    generalist = await _create_employee(client, owner_headers, master_data, mobile="9755555555", email="generalist@example.com")
    await _grant_leads_assign(client, owner_headers, specialist["id"], role_name="Specialist Role")
    await _grant_leads_assign(client, owner_headers, generalist["id"], role_name="Generalist Role")

    await client.patch(
        f"/api/v1/employees/{specialist['id']}", json={"product_ids": [lmd["loan_product_id"]]}, headers=owner_headers
    )

    # Give the generalist zero leads and the specialist one lead, so a naive
    # lowest-workload-only sort would pick the generalist — product match must win instead.
    lead = await _create_lead(client, owner_headers, lmd)
    await client.post(f"/api/v1/leads/{lead['id']}/assign", json={"employee_id": specialist["id"]}, headers=owner_headers)

    r = await client.get(f"/api/v1/leads/eligible-assignees?product_category=loan&product_id={lmd['loan_product_id']}", headers=owner_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    by_id = {d["id"]: d for d in data}
    assert by_id[specialist["id"]]["product_match"] is True
    assert by_id[generalist["id"]]["product_match"] is False
    assert data[0]["id"] == specialist["id"]
    assert data[0]["recommended"] is True
    assert data[1]["recommended"] is False


async def test_eligible_assignees_falls_back_to_workload_when_nobody_specializes(client, mock_db, owner_headers, master_data):
    """Neither candidate has a product match — product_match must not distort the
    ranking in this case; lowest workload alone should decide, same as before product
    match was made the primary sort key."""
    lmd = await _lead_master_data(mock_db)

    busier = await _create_employee(client, owner_headers, master_data, mobile="9744444450", email="busier@example.com")
    freer = await _create_employee(client, owner_headers, master_data, mobile="9744444451", email="freer@example.com")
    await _grant_leads_assign(client, owner_headers, busier["id"], role_name="Busier Role")
    await _grant_leads_assign(client, owner_headers, freer["id"], role_name="Freer Role")

    lead = await _create_lead(client, owner_headers, lmd)
    await client.post(f"/api/v1/leads/{lead['id']}/assign", json={"employee_id": busier["id"]}, headers=owner_headers)

    r = await client.get(f"/api/v1/leads/eligible-assignees?product_category=loan&product_id={lmd['loan_product_id']}", headers=owner_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    by_id = {d["id"]: d for d in data}
    assert by_id[busier["id"]]["product_match"] is False
    assert by_id[freer["id"]]["product_match"] is False
    assert data[0]["id"] == freer["id"]  # lower workload wins when specialization is tied


async def test_eligible_assignees_workload_breaks_tie_among_equally_specialized(client, mock_db, owner_headers, master_data):
    """Both candidates specialize in the product — product_match is a tie, so workload
    must still decide between them, not an arbitrary/unstable order."""
    lmd = await _lead_master_data(mock_db)

    busier_specialist = await _create_employee(client, owner_headers, master_data, mobile="9744444452", email="busier.specialist@example.com")
    freer_specialist = await _create_employee(client, owner_headers, master_data, mobile="9744444453", email="freer.specialist@example.com")
    await _grant_leads_assign(client, owner_headers, busier_specialist["id"], role_name="Busier Specialist Role")
    await _grant_leads_assign(client, owner_headers, freer_specialist["id"], role_name="Freer Specialist Role")
    await client.patch(f"/api/v1/employees/{busier_specialist['id']}", json={"product_ids": [lmd["loan_product_id"]]}, headers=owner_headers)
    await client.patch(f"/api/v1/employees/{freer_specialist['id']}", json={"product_ids": [lmd["loan_product_id"]]}, headers=owner_headers)

    lead = await _create_lead(client, owner_headers, lmd)
    await client.post(f"/api/v1/leads/{lead['id']}/assign", json={"employee_id": busier_specialist["id"]}, headers=owner_headers)

    r = await client.get(f"/api/v1/leads/eligible-assignees?product_category=loan&product_id={lmd['loan_product_id']}", headers=owner_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    by_id = {d["id"]: d for d in data}
    assert by_id[busier_specialist["id"]]["product_match"] is True
    assert by_id[freer_specialist["id"]]["product_match"] is True
    assert data[0]["id"] == freer_specialist["id"]  # tied on specialization, lower workload wins


async def test_eligible_assignees_ineligible_employee_excluded_even_with_product_match(client, mock_db, owner_headers, master_data):
    """A product-specialization match must never bypass the module-access eligibility
    gate — an employee with no grant under the lead's product-category module stays
    excluded from the results entirely, even if their `product_ids` would otherwise match."""
    lmd = await _lead_master_data(mock_db)

    ineligible = await _create_employee(client, owner_headers, master_data, mobile="9744444454", email="ineligible@example.com")
    await client.patch(f"/api/v1/employees/{ineligible['id']}", json={"product_ids": [lmd["loan_product_id"]]}, headers=owner_headers)
    # No _grant_leads_assign call — this employee has no loan_management module access.

    r = await client.get(f"/api/v1/leads/eligible-assignees?product_category=loan&product_id={lmd['loan_product_id']}", headers=owner_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert all(d["id"] != ineligible["id"] for d in data)


async def test_eligible_assignees_alphabetical_tiebreak_when_all_else_equal(client, mock_db, owner_headers, master_data):
    zara = await _create_employee(client, owner_headers, master_data, mobile="9766666661", email="zara@example.com")
    amit = await _create_employee(client, owner_headers, master_data, mobile="9766666662", email="amit@example.com")
    await client.patch(f"/api/v1/employees/{zara['id']}", json={"display_name": "Zara Employee"}, headers=owner_headers)
    await client.patch(f"/api/v1/employees/{amit['id']}", json={"display_name": "Amit Employee"}, headers=owner_headers)
    await _grant_leads_assign(client, owner_headers, zara["id"], role_name="Zara Role")
    await _grant_leads_assign(client, owner_headers, amit["id"], role_name="Amit Role")

    r = await client.get("/api/v1/leads/eligible-assignees?product_category=loan", headers=owner_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert [d["display_name"] for d in data] == ["Amit Employee", "Zara Employee"]


async def test_eligible_assignees_prefers_never_assigned_over_recently_assigned(client, mock_db, owner_headers, master_data):
    lmd = await _lead_master_data(mock_db)
    recently_assigned = await _create_employee(client, owner_headers, master_data, mobile="9777777771", email="recent@example.com")
    never_assigned = await _create_employee(client, owner_headers, master_data, mobile="9777777772", email="never@example.com")
    await _grant_leads_assign(client, owner_headers, recently_assigned["id"], role_name="Recent Role")
    await _grant_leads_assign(client, owner_headers, never_assigned["id"], role_name="Never Role")

    # Assign then unassign so `recently_assigned` ties on current_lead_count (back to 0)
    # but still has a strictly more recent `lead_assigned` activity than `never_assigned`,
    # who has none at all — least-recently-assigned must break the tie in their favor.
    lead = await _create_lead(client, owner_headers, lmd)
    await client.post(f"/api/v1/leads/{lead['id']}/assign", json={"employee_id": recently_assigned["id"]}, headers=owner_headers)
    await client.post(f"/api/v1/leads/{lead['id']}/unassign", headers=owner_headers)

    r = await client.get("/api/v1/leads/eligible-assignees?product_category=loan", headers=owner_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data[0]["id"] == never_assigned["id"]
    assert data[1]["id"] == recently_assigned["id"]


async def test_eligible_assignees_prefers_same_branch_as_assigning_employee(client, mock_db, owner_headers, master_data):
    branch_b = await client.post("/api/v1/branches", json={"name": "Second Branch", "code": "SB"}, headers=owner_headers)
    assert branch_b.status_code == 200, branch_b.text
    branch_b_id = branch_b.json()["data"]["id"]

    # The assigning employee themselves sits in `master_data`'s branch ("Head Office").
    assigner = await _create_employee(client, owner_headers, master_data, mobile="9788888881", email="assigner@example.com")
    await _grant_leads_assign(client, owner_headers, assigner["id"], role_name="Assigner Role")
    r = await client.post("/api/v1/auth/login", json={"mobile": "9788888881", "password": "InitialPass1!"})
    assigner_headers = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    same_branch = await _create_employee(client, owner_headers, master_data, mobile="9788888882", email="samebranch@example.com")
    other_branch_payload = {**master_data, "branch_id": branch_b_id}
    other_branch = await _create_employee(client, owner_headers, other_branch_payload, mobile="9788888883", email="otherbranch@example.com")
    await _grant_leads_assign(client, owner_headers, same_branch["id"], role_name="Same Branch Role")
    await _grant_leads_assign(client, owner_headers, other_branch["id"], role_name="Other Branch Role")

    r = await client.get("/api/v1/leads/eligible-assignees?product_category=loan", headers=assigner_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    ids = [d["id"] for d in data if d["id"] in (same_branch["id"], other_branch["id"])]
    assert ids[0] == same_branch["id"]


async def test_timeline_assigned_activity_includes_employee_name(client, mock_db, owner_headers, master_data):
    lmd = await _lead_master_data(mock_db)
    lead = await _create_lead(client, owner_headers, lmd)
    employee = await _create_employee(client, owner_headers, master_data)

    await client.post(f"/api/v1/leads/{lead['id']}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)

    r = await client.get(f"/api/v1/leads/{lead['id']}/timeline", headers=owner_headers)
    assert r.status_code == 200, r.text
    assigned_entry = next(e for e in r.json()["data"] if e["type"] == "activity" and e["event_type"] == "assigned")
    assert assigned_entry["metadata"]["employee_name"] == employee["display_name"]


async def test_dashboard_today_leads_and_assigned_leads_widgets_reflect_real_data(client, mock_db, owner_headers, master_data):
    async def _seed_widget(key, widget_type=WidgetType.METRIC):
        widget = DashboardWidget(
            key=key, label=key, category="leads", widget_type=widget_type,
            required_module="leads", required_resource="leads", required_action="view",
        )
        await mock_db["dashboard_widgets"].insert_one(widget.model_dump(by_alias=True, exclude={"id"}))

    await _seed_widget("today_leads")
    await _seed_widget("assigned_leads")

    lmd = await _lead_master_data(mock_db)
    lead = await _create_lead(client, owner_headers, lmd)
    employee = await _create_employee(client, owner_headers, master_data)
    await client.post(f"/api/v1/leads/{lead['id']}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)

    r = await client.get("/api/v1/dashboard", headers=owner_headers)
    assert r.status_code == 200, r.text
    widgets = {w["key"]: w["data"] for w in r.json()["data"]}
    assert widgets["today_leads"] == {"available": True, "value": 1}
    assert widgets["assigned_leads"] == {"available": True, "value": 1}
