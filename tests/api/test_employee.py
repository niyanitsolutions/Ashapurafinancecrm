"""End-to-end API tests for User & Employee Management (Module 2), run against
mongomock + fakeredis. Exercises Owner CRUD, self-service profile, authorization
boundaries, and the Auth-reuse actions (reset-password, force-logout, sessions).
"""


def _create_payload(master_data, mobile="9111111111", email="jane.doe@example.com"):
    return {
        "mobile": mobile,
        "initial_password": "InitialPass1!",
        "first_name": "Jane",
        "last_name": "Doe",
        "email": email,
        "department_id": master_data["department_id"],
        "designation_id": master_data["designation_id"],
        "branch_id": master_data["branch_id"],
        "joining_date": "2026-01-15",
        "employment_type": "full_time",
    }


async def _create_employee(client, owner_headers, master_data, **overrides):
    payload = _create_payload(master_data)
    payload.update(overrides)
    r = await client.post("/api/v1/employees", json=payload, headers=owner_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def test_create_employee_success(client, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data)
    assert employee["employee_code"].startswith("AFS-EMP-")
    assert employee["department_name"] == "Loan"
    assert employee["status"] == "active"

    r = await client.post("/api/v1/auth/login", json={"mobile": "9111111111", "password": "InitialPass1!"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["role"] == "employee"


async def test_create_employee_duplicate_mobile(client, owner_headers, master_data):
    await _create_employee(client, owner_headers, master_data)
    r = await client.post(
        "/api/v1/employees",
        json=_create_payload(master_data, email="other@example.com"),
        headers=owner_headers,
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "conflict"


async def test_create_employee_duplicate_email(client, owner_headers, master_data):
    await _create_employee(client, owner_headers, master_data)
    r = await client.post(
        "/api/v1/employees",
        json=_create_payload(master_data, mobile="9222222222"),
        headers=owner_headers,
    )
    assert r.status_code == 409, r.text


async def test_create_employee_requires_owner(client, employee_headers, master_data):
    r = await client.post("/api/v1/employees", json=_create_payload(master_data), headers=employee_headers)
    assert r.status_code == 403, r.text


async def test_create_employee_invalid_department(client, owner_headers, master_data):
    r = await client.post(
        "/api/v1/employees", json=_create_payload(master_data, mobile="9333333333") | {"department_id": "000000000000000000000000"},
        headers=owner_headers,
    )
    assert r.status_code == 422, r.text


async def test_employee_list_requires_owner(client, employee_headers):
    r = await client.get("/api/v1/employees", headers=employee_headers)
    assert r.status_code == 403, r.text


async def test_employee_list_search_and_pagination(client, owner_headers, master_data):
    await _create_employee(client, owner_headers, master_data, mobile="9444444444", email="alice@example.com", first_name="Alice")
    await _create_employee(client, owner_headers, master_data, mobile="9555555555", email="bob@example.com", first_name="Bob")

    r = await client.get("/api/v1/employees?page=1&page_size=1", headers=owner_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["data"]) == 1
    assert body["meta"]["pagination"]["total"] == 2

    r = await client.get("/api/v1/employees?search=alice", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 1
    assert r.json()["data"][0]["first_name"] == "Alice"


async def test_employee_cannot_view_other_employee(client, owner_headers, employee_headers, master_data):
    other = await _create_employee(client, owner_headers, master_data)
    r = await client.get(f"/api/v1/employees/{other['id']}", headers=employee_headers)
    assert r.status_code == 403, r.text


async def test_self_profile_get_and_update(client, owner_headers, master_data):
    await _create_employee(client, owner_headers, master_data)
    r = await client.post("/api/v1/auth/login", json={"mobile": "9111111111", "password": "InitialPass1!"})
    self_headers = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    r = await client.get("/api/v1/employees/me", headers=self_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["first_name"] == "Jane"

    r = await client.patch("/api/v1/employees/me", json={"first_name": "Janet"}, headers=self_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["first_name"] == "Janet"


async def test_self_update_ignores_restricted_fields(client, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data)
    r = await client.post("/api/v1/auth/login", json={"mobile": "9111111111", "password": "InitialPass1!"})
    self_headers = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    # department_id isn't part of SelfUpdateEmployeeRequest — sending it is a no-op, not an error
    r = await client.patch("/api/v1/employees/me", json={"department_id": "000000000000000000000000"}, headers=self_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["department_id"] == employee["department_id"]


async def test_self_photo_upload_flow(client, owner_headers, master_data):
    await _create_employee(client, owner_headers, master_data)
    r = await client.post("/api/v1/auth/login", json={"mobile": "9111111111", "password": "InitialPass1!"})
    self_headers = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    r = await client.post("/api/v1/employees/me/photo/upload-url", headers=self_headers)
    assert r.status_code == 200, r.text
    s3_key = r.json()["data"]["s3_key"]
    assert s3_key

    r = await client.patch("/api/v1/employees/me/photo", json={"s3_key": s3_key}, headers=self_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["photo_s3_key"] == s3_key


async def test_deactivate_blocks_login_then_activate_restores(client, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data)

    r = await client.patch(f"/api/v1/employees/{employee['id']}/deactivate", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "inactive"

    r = await client.post("/api/v1/auth/login", json={"mobile": "9111111111", "password": "InitialPass1!"})
    assert r.status_code == 401, r.text

    r = await client.patch(f"/api/v1/employees/{employee['id']}/activate", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "active"

    r = await client.post("/api/v1/auth/login", json={"mobile": "9111111111", "password": "InitialPass1!"})
    assert r.status_code == 200, r.text


async def test_status_suspended_blocks_login_on_leave_does_not(client, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data)

    r = await client.patch(f"/api/v1/employees/{employee['id']}", json={"status": "suspended"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    r = await client.post("/api/v1/auth/login", json={"mobile": "9111111111", "password": "InitialPass1!"})
    assert r.status_code == 401

    r = await client.patch(f"/api/v1/employees/{employee['id']}", json={"status": "on_leave"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    r = await client.post("/api/v1/auth/login", json={"mobile": "9111111111", "password": "InitialPass1!"})
    assert r.status_code == 200, r.text


async def test_reset_employee_password_triggers_forgot_password_flow(client, mock_db, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data)

    r = await client.post(f"/api/v1/employees/{employee['id']}/reset-password", headers=owner_headers)
    assert r.status_code == 200, r.text

    events = {doc["event_type"] async for doc in mock_db["audit_logs"].find({})}
    assert "employee_password_reset_triggered" in events
    assert "otp_sent" in events  # emitted by AuthService.forgot_password, reused unmodified


async def test_force_logout_revokes_active_sessions(client, mock_db, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data)
    r = await client.post("/api/v1/auth/login", json={"mobile": "9111111111", "password": "InitialPass1!"})
    tokens = r.json()["data"]

    r = await client.post(f"/api/v1/employees/{employee['id']}/force-logout", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["sessions_revoked"] == 1

    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401, r.text


async def test_owner_views_employee_sessions_and_login_history(client, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data)
    await client.post("/api/v1/auth/login", json={"mobile": "9111111111", "password": "InitialPass1!"})

    r = await client.get(f"/api/v1/employees/{employee['id']}/sessions", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 1

    r = await client.get(f"/api/v1/employees/{employee['id']}/login-history", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert any(e["event_type"] == "login" for e in r.json()["data"])

    r = await client.get(f"/api/v1/employees/{employee['id']}/activity-summary", headers=owner_headers)
    assert r.status_code == 200, r.text
    summary = r.json()["data"]
    assert summary["total_logins"] == 1
    assert summary["active_session_count"] == 1


async def test_self_sessions_and_login_history(client, owner_headers, master_data):
    await _create_employee(client, owner_headers, master_data)
    r = await client.post("/api/v1/auth/login", json={"mobile": "9111111111", "password": "InitialPass1!"})
    self_headers = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    r = await client.get("/api/v1/employees/me/sessions", headers=self_headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 1

    r = await client.get("/api/v1/employees/me/login-history", headers=self_headers)
    assert r.status_code == 200, r.text


async def test_export_csv(client, owner_headers, master_data):
    await _create_employee(client, owner_headers, master_data)
    r = await client.get("/api/v1/employees/export", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert "text/csv" in r.headers["content-type"]
    assert "AFS-EMP-" in r.text


async def test_department_designation_branch_master_data(client, owner_headers, employee_headers):
    r = await client.post("/api/v1/departments", json={"name": "Recovery"}, headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.post("/api/v1/departments", json={"name": "Recovery"}, headers=owner_headers)
    assert r.status_code == 409, r.text

    r = await client.get("/api/v1/departments", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert any(d["name"] == "Recovery" for d in r.json()["data"])

    r = await client.get("/api/v1/departments", headers=employee_headers)
    assert r.status_code == 403, r.text

    r = await client.post("/api/v1/branches", json={"name": "Pune Branch", "code": "PUN"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    r = await client.post("/api/v1/branches", json={"name": "Pune Branch 2", "code": "PUN"}, headers=owner_headers)
    assert r.status_code == 409, r.text


async def test_employee_document_upload_flow(client, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data)

    r = await client.post(
        f"/api/v1/employees/{employee['id']}/documents/upload-url",
        json={"document_type": "pan", "file_name": "pan.pdf", "content_type": "application/pdf"},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    s3_key = r.json()["data"]["s3_key"]

    r = await client.post(
        f"/api/v1/employees/{employee['id']}/documents",
        json={"document_type": "pan", "file_name": "pan.pdf", "s3_key": s3_key},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/employees/{employee['id']}/documents", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 1
    assert r.json()["data"][0]["document_type"] == "pan"
