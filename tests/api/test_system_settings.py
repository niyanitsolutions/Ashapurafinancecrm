"""End-to-end tests for Module 4 (Settings / Master Data): the generic named-master CRUD
(Lead Sources standing in for Loan Products/Insurance Products/Document Types, which
share the same code path), Status Masters, Notification Templates, API Settings, Company
Settings, Department/Designation/Branch edit, and — importantly — that these routes
really are gated by `require_permission` (Access Control, Module 3), not a bespoke role
check: an Employee is denied without a granted permission and allowed once one exists.
"""


async def _create_permission(client, owner_headers, module="system_settings", resource="lead_sources", actions=None):
    actions = actions or ["view", "create", "edit", "delete"]
    r = await client.post("/api/v1/permissions", json={"module": module, "resource": resource, "actions": actions}, headers=owner_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _create_role_with_permission(client, owner_headers, employee_id, *, resource, actions):
    permission = await _create_permission(client, owner_headers, resource=resource, actions=actions)
    r = await client.post("/api/v1/roles", json={"name": f"Role for {resource}"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    role = r.json()["data"]
    r = await client.put(
        f"/api/v1/roles/{role['id']}/permissions",
        json={"grants": [{"permission_id": permission["id"], "granted_actions": actions}]},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/roles/{role['id']}/assign", json={"employee_id": employee_id}, headers=owner_headers)
    assert r.status_code == 200, r.text


async def _create_employee(client, owner_headers, master_data, mobile="9311111111", email="settings.test@example.com"):
    payload = {
        "mobile": mobile,
        "initial_password": "InitialPass1!",
        "first_name": "Settings",
        "last_name": "Tester",
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


# ---------------------------------------------------------------------- named master data (lead sources)


async def test_lead_source_crud_and_duplicate_name(client, owner_headers):
    r = await client.post("/api/v1/lead-sources", json={"name": "Website", "description": "Organic site traffic"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    lead_source = r.json()["data"]
    assert lead_source["status"] == "active"

    r = await client.post("/api/v1/lead-sources", json={"name": "Website"}, headers=owner_headers)
    assert r.status_code == 409, r.text

    r = await client.get("/api/v1/lead-sources", headers=owner_headers)
    assert any(x["name"] == "Website" for x in r.json()["data"])

    r = await client.get(f"/api/v1/lead-sources/{lead_source['id']}", headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.patch(f"/api/v1/lead-sources/{lead_source['id']}", json={"description": "Updated"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["description"] == "Updated"

    r = await client.patch(f"/api/v1/lead-sources/{lead_source['id']}/deactivate", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "inactive"

    r = await client.patch(f"/api/v1/lead-sources/{lead_source['id']}/activate", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "active"


async def test_loan_product_and_insurance_product_and_document_type_create(client, owner_headers):
    r = await client.post("/api/v1/loan-products", json={"name": "Personal Loan"}, headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.post("/api/v1/insurance-products", json={"name": "Health"}, headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.post("/api/v1/document-types", json={"name": "PAN"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["supports_password"] is False


async def test_document_type_supports_password_flag_create_and_update(client, owner_headers):
    """Bank Statement password support (Part 1A) — the Owner marks a document type as
    password-capable once, on the master-data row itself; every product schema
    referencing it inherits the flag automatically."""
    r = await client.post("/api/v1/document-types", json={"name": "Bank Statement", "supports_password": True}, headers=owner_headers)
    assert r.status_code == 200, r.text
    doc_type = r.json()["data"]
    assert doc_type["supports_password"] is True

    r = await client.patch(f"/api/v1/document-types/{doc_type['id']}", json={"supports_password": False}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["supports_password"] is False

    # Updating name/description alone must not accidentally clear an already-set flag.
    r = await client.post("/api/v1/document-types", json={"name": "Passbook", "supports_password": True}, headers=owner_headers)
    doc_type_id = r.json()["data"]["id"]
    r = await client.patch(f"/api/v1/document-types/{doc_type_id}", json={"description": "Bank passbook"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["supports_password"] is True


# ---------------------------------------------------------------------- status masters


async def test_status_master_create_duplicate_and_filter_by_category(client, owner_headers):
    r = await client.post("/api/v1/status-masters", json={"category": "loan_status", "name": "Disbursed", "sequence": 10}, headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.post("/api/v1/status-masters", json={"category": "loan_status", "name": "Disbursed"}, headers=owner_headers)
    assert r.status_code == 409, r.text

    r = await client.post("/api/v1/status-masters", json={"category": "insurance_status", "name": "Disbursed"}, headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.get("/api/v1/status-masters?category=loan_status", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert all(x["category"] == "loan_status" for x in r.json()["data"])
    assert len(r.json()["data"]) == 1


# ---------------------------------------------------------------------- notification templates


async def test_notification_template_crud(client, owner_headers):
    r = await client.post(
        "/api/v1/notification-templates",
        json={"channel": "sms", "key": "otp_signup", "body": "Your OTP is {{otp}}", "available_variables": ["otp"]},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    template = r.json()["data"]

    r = await client.post(
        "/api/v1/notification-templates", json={"channel": "sms", "key": "otp_signup", "body": "dup"}, headers=owner_headers
    )
    assert r.status_code == 409, r.text

    r = await client.patch(f"/api/v1/notification-templates/{template['id']}", json={"body": "Updated body {{otp}}"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["body"] == "Updated body {{otp}}"

    r = await client.get("/api/v1/notification-templates?channel=sms", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 1


# ---------------------------------------------------------------------- API settings


async def test_api_setting_config_never_returned_plaintext_and_merges_on_update(client, owner_headers):
    r = await client.post(
        "/api/v1/api-settings",
        json={"provider": "sms", "label": "Primary SMS Gateway", "config": {"api_key": "secret-123", "sender_id": "AFSFIN"}},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    setting = r.json()["data"]
    assert "config" not in setting
    assert set(setting["configured_keys"]) == {"api_key", "sender_id"}

    r = await client.patch(f"/api/v1/api-settings/{setting['id']}", json={"config": {"auth_token": "another-secret"}}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert set(r.json()["data"]["configured_keys"]) == {"api_key", "sender_id", "auth_token"}

    r = await client.patch(f"/api/v1/api-settings/{setting['id']}/deactivate", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "inactive"


# ---------------------------------------------------------------------- company settings (singleton)


async def test_company_settings_singleton_get_and_update(client, owner_headers):
    r = await client.get("/api/v1/company-settings", headers=owner_headers)
    assert r.status_code == 200, r.text
    first = r.json()["data"]
    assert first["company_name"]

    r = await client.patch(
        "/api/v1/company-settings",
        json={"company_name": "Ashapura Financial Services Pvt Ltd", "business_hours": [{"day": "mon", "open_time": "10:00", "close_time": "18:00"}]},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    updated = r.json()["data"]
    assert updated["company_name"] == "Ashapura Financial Services Pvt Ltd"
    assert updated["id"] == first["id"]
    assert updated["business_hours"][0]["day"] == "mon"

    r = await client.get("/api/v1/company-settings", headers=owner_headers)
    assert r.json()["data"]["id"] == first["id"]


async def test_company_settings_address_and_contact_fields(client, owner_headers):
    r = await client.patch(
        "/api/v1/company-settings",
        json={
            "contact_email": "info@ashapura.example",
            "contact_phone": "9876500000",
            "address": {"line1": "1st Floor, ABC Tower", "city": "Ahmedabad", "state": "Gujarat", "pincode": "380001"},
        },
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    updated = r.json()["data"]
    assert updated["contact_email"] == "info@ashapura.example"
    assert updated["contact_phone"] == "9876500000"
    assert updated["address"]["city"] == "Ahmedabad"
    assert updated["address"]["country"] == "India"

    r = await client.get("/api/v1/company-settings", headers=owner_headers)
    assert r.json()["data"]["address"]["pincode"] == "380001"


async def test_company_logo_upload_url_and_confirm(client, owner_headers):
    r = await client.post("/api/v1/company-settings/logo/upload-url", headers=owner_headers)
    assert r.status_code == 200, r.text
    s3_key = r.json()["data"]["s3_key"]

    r = await client.patch("/api/v1/company-settings/logo", json={"s3_key": s3_key}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["logo_s3_key"] == s3_key


# ---------------------------------------------------------------------- departments / designations / branches (edit only)


async def test_department_edit_activate_deactivate(client, owner_headers, master_data):
    department_id = master_data["department_id"]

    r = await client.patch(f"/api/v1/departments/{department_id}", json={"description": "Handles loan processing"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["description"] == "Handles loan processing"

    r = await client.patch(f"/api/v1/departments/{department_id}/deactivate", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "inactive"

    r = await client.patch(f"/api/v1/departments/{department_id}/activate", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "active"


async def test_branch_edit_rejects_duplicate_code(client, owner_headers, master_data):
    r = await client.post("/api/v1/branches", json={"name": "Second Branch", "code": "SB01"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    second_branch = r.json()["data"]

    r = await client.patch(f"/api/v1/branches/{second_branch['id']}", json={"code": "HO"}, headers=owner_headers)
    assert r.status_code == 409, r.text

    r = await client.patch(f"/api/v1/branches/{second_branch['id']}", json={"name": "Renamed Branch"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["name"] == "Renamed Branch"


# ---------------------------------------------------------------------- permission gating (require_permission consumption)


async def test_employee_without_permission_is_denied(client, employee_headers):
    r = await client.post("/api/v1/lead-sources", json={"name": "Meta"}, headers=employee_headers)
    assert r.status_code == 403, r.text


async def test_employee_with_granted_permission_is_allowed(client, owner_headers, master_data):
    # A fresh Employee created via the API (so both users + employees docs exist,
    # matching how PermissionEngine resolves an employee via
    # EmployeeRepository.find_by_user_id) — then logged in as itself, not via the
    # employee_headers fixture (which has no Employee profile behind it).
    employee = await _create_employee(client, owner_headers, master_data, mobile="9322222222", email="perm.employee@example.com")
    r = await client.post("/api/v1/auth/login", json={"mobile": "9322222222", "password": "InitialPass1!"})
    assert r.status_code == 200, r.text
    own_headers = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    r = await client.post("/api/v1/lead-sources", json={"name": "Referral"}, headers=own_headers)
    assert r.status_code == 403, r.text  # no permission granted yet

    await _create_role_with_permission(client, owner_headers, employee["id"], resource="lead_sources", actions=["view", "create"])

    r = await client.post("/api/v1/lead-sources", json={"name": "Referral"}, headers=own_headers)
    assert r.status_code == 200, r.text
    lead_source_id = r.json()["data"]["id"]

    # "edit" was never granted (only view+create) — deactivate must still be denied.
    r = await client.patch(f"/api/v1/lead-sources/{lead_source_id}/deactivate", headers=own_headers)
    assert r.status_code == 403, r.text
