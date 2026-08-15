"""End-to-end + engine-level tests for Access Control (Module 3): roles, permission
catalog, permission matrix, employee<->role assignment, temporary access, geo exceptions,
and the has_permission resolution engine (Owner bypass, role grants, department/branch
scope, temporary access time windows).
"""

from datetime import timedelta

from app.features.access_control.permission_engine import PermissionEngine
from app.features.auth.models import User
from app.utils.datetime import utc_now


def _employee_payload(master_data, mobile="9211111111", email="access.test@example.com"):
    return {
        "mobile": mobile,
        "initial_password": "InitialPass1!",
        "first_name": "Access",
        "last_name": "Tester",
        "email": email,
        "department_id": master_data["department_id"],
        "designation_id": master_data["designation_id"],
        "branch_id": master_data["branch_id"],
        "joining_date": "2026-01-15",
        "employment_type": "full_time",
    }


async def _create_employee(client, owner_headers, master_data, **overrides):
    payload = _employee_payload(master_data)
    payload.update(overrides)
    r = await client.post("/api/v1/employees", json=payload, headers=owner_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _create_permission(client, owner_headers, module="loan_management", resource="leads", actions=None):
    actions = actions or ["view", "create", "edit"]
    r = await client.post(
        "/api/v1/permissions", json={"module": module, "resource": resource, "actions": actions}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _create_role(client, owner_headers, name="Loan Officer"):
    r = await client.post("/api/v1/roles", json={"name": name}, headers=owner_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


# ---------------------------------------------------------------------- roles


async def test_role_crud_and_duplicate_name(client, owner_headers):
    role = await _create_role(client, owner_headers, "Branch Manager")
    assert role["status"] == "active"

    r = await client.post("/api/v1/roles", json={"name": "Branch Manager"}, headers=owner_headers)
    assert r.status_code == 409, r.text

    r = await client.get("/api/v1/roles", headers=owner_headers)
    assert any(x["name"] == "Branch Manager" for x in r.json()["data"])

    r = await client.patch(f"/api/v1/roles/{role['id']}", json={"description": "Manages a branch"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["description"] == "Manages a branch"

    r = await client.patch(f"/api/v1/roles/{role['id']}/deactivate", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "inactive"

    r = await client.patch(f"/api/v1/roles/{role['id']}/activate", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "active"


async def test_roles_require_owner(client, employee_headers):
    r = await client.get("/api/v1/roles", headers=employee_headers)
    assert r.status_code == 403, r.text


async def test_duplicate_role_copies_permission_matrix(client, owner_headers):
    permission = await _create_permission(client, owner_headers)
    role = await _create_role(client, owner_headers, "Original Role")

    r = await client.put(
        f"/api/v1/roles/{role['id']}/permissions",
        json={"grants": [{"permission_id": permission["id"], "granted_actions": ["view", "edit"]}]},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text

    r = await client.post(f"/api/v1/roles/{role['id']}/duplicate", json={"new_name": "Copied Role"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    copied_role = r.json()["data"]

    r = await client.get(f"/api/v1/roles/{copied_role['id']}/permissions", headers=owner_headers)
    assert r.status_code == 200, r.text
    grants = r.json()["data"]
    assert len(grants) == 1
    assert set(grants[0]["granted_actions"]) == {"view", "edit"}


# ---------------------------------------------------------------------- permission catalog


async def test_create_permission_rejects_unknown_action(client, owner_headers):
    r = await client.post(
        "/api/v1/permissions", json={"module": "loan_management", "resource": "leads", "actions": ["fly"]}, headers=owner_headers
    )
    assert r.status_code == 422, r.text


async def test_create_permission_duplicate_module_resource(client, owner_headers):
    await _create_permission(client, owner_headers)
    r = await client.post(
        "/api/v1/permissions", json={"module": "loan_management", "resource": "leads", "actions": ["view"]}, headers=owner_headers
    )
    assert r.status_code == 409, r.text


# ---------------------------------------------------------------------- permission matrix


async def test_set_role_permissions_rejects_action_outside_catalog(client, owner_headers):
    permission = await _create_permission(client, owner_headers, actions=["view"])
    role = await _create_role(client, owner_headers)

    r = await client.put(
        f"/api/v1/roles/{role['id']}/permissions",
        json={"grants": [{"permission_id": permission["id"], "granted_actions": ["delete"]}]},
        headers=owner_headers,
    )
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------- employee <-> role assignment


async def test_assign_and_remove_role(client, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data)
    role = await _create_role(client, owner_headers)

    r = await client.post(f"/api/v1/roles/{role['id']}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.post(f"/api/v1/roles/{role['id']}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)
    assert r.status_code == 409, r.text

    r = await client.get(f"/api/v1/employees/{employee['id']}/roles", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 1
    assert r.json()["data"][0]["role_name"] == role["name"]

    r = await client.post(f"/api/v1/roles/{role['id']}/remove", json={"employee_id": employee["id"]}, headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/employees/{employee['id']}/roles", headers=owner_headers)
    assert r.json()["data"] == []


async def test_audit_logs_written_for_role_and_permission_changes(client, mock_db, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data)
    permission = await _create_permission(client, owner_headers)
    role = await _create_role(client, owner_headers)
    await client.put(
        f"/api/v1/roles/{role['id']}/permissions",
        json={"grants": [{"permission_id": permission["id"], "granted_actions": ["view"]}]},
        headers=owner_headers,
    )
    await client.post(f"/api/v1/roles/{role['id']}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)

    events = {doc["event_type"] async for doc in mock_db["audit_logs"].find({})}
    assert {"role_created", "permission_created", "role_permissions_updated", "role_assigned"} <= events


# ---------------------------------------------------------------------- permission engine


async def test_owner_bypasses_permission_engine(mock_db, owner_headers):
    owner_user = await mock_db["users"].find_one({"role": "owner"})
    owner = User.model_validate(owner_user)
    engine = PermissionEngine(mock_db)
    allowed = await engine.has_permission(owner, module="literally_anything", resource="whatever", action="delete")
    assert allowed is True


async def test_employee_with_no_roles_has_no_permission(client, mock_db, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data)
    user_doc = await mock_db["users"].find_one({"mobile": employee["mobile"]})
    employee_user = User.model_validate(user_doc)

    engine = PermissionEngine(mock_db)
    allowed = await engine.has_permission(employee_user, module="loan_management", resource="leads", action="view")
    assert allowed is False


async def test_role_grant_gives_permission_department_scope_enforced(client, mock_db, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data)
    permission = await _create_permission(client, owner_headers)
    role = await _create_role(client, owner_headers)

    await client.put(
        f"/api/v1/roles/{role['id']}/permissions",
        json={
            "grants": [
                {
                    "permission_id": permission["id"],
                    "granted_actions": ["view"],
                    "department_ids": [master_data["department_id"]],
                }
            ]
        },
        headers=owner_headers,
    )
    await client.post(f"/api/v1/roles/{role['id']}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)

    user_doc = await mock_db["users"].find_one({"mobile": employee["mobile"]})
    employee_user = User.model_validate(user_doc)
    engine = PermissionEngine(mock_db)

    allowed = await engine.has_permission(
        employee_user, module="loan_management", resource="leads", action="view", department_id=master_data["department_id"]
    )
    assert allowed is True

    denied_wrong_dept = await engine.has_permission(
        employee_user, module="loan_management", resource="leads", action="view", department_id="000000000000000000000000"
    )
    assert denied_wrong_dept is False

    denied_wrong_action = await engine.has_permission(
        employee_user, module="loan_management", resource="leads", action="delete", department_id=master_data["department_id"]
    )
    assert denied_wrong_action is False


async def test_temporary_access_grants_permission_only_within_window(client, mock_db, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data)
    permission = await _create_permission(client, owner_headers)

    now = utc_now()
    r = await client.post(
        "/api/v1/temporary-access",
        json={
            "employee_id": employee["id"],
            "grants": [{"permission_id": permission["id"], "actions": ["view"]}],
            "start_date": (now - timedelta(days=1)).date().isoformat(),
            "end_date": (now + timedelta(days=1)).date().isoformat(),
            "start_time": "00:00",
            "end_time": "23:59",
            "reason": "Covering for absent colleague",
        },
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    temp_access_id = r.json()["data"]["id"]

    user_doc = await mock_db["users"].find_one({"mobile": employee["mobile"]})
    employee_user = User.model_validate(user_doc)
    engine = PermissionEngine(mock_db)

    allowed = await engine.has_permission(employee_user, module="loan_management", resource="leads", action="view")
    assert allowed is True

    r = await client.post(f"/api/v1/temporary-access/{temp_access_id}/revoke", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "revoked"

    allowed_after_revoke = await engine.has_permission(employee_user, module="loan_management", resource="leads", action="view")
    assert allowed_after_revoke is False


async def test_temporary_access_outside_date_window_is_denied(client, mock_db, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data)
    permission = await _create_permission(client, owner_headers)

    now = utc_now()
    r = await client.post(
        "/api/v1/temporary-access",
        json={
            "employee_id": employee["id"],
            "grants": [{"permission_id": permission["id"], "actions": ["view"]}],
            "start_date": (now - timedelta(days=10)).date().isoformat(),
            "end_date": (now - timedelta(days=5)).date().isoformat(),
            "start_time": "00:00",
            "end_time": "23:59",
            "reason": "Past window",
        },
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text

    user_doc = await mock_db["users"].find_one({"mobile": employee["mobile"]})
    employee_user = User.model_validate(user_doc)
    engine = PermissionEngine(mock_db)

    allowed = await engine.has_permission(employee_user, module="loan_management", resource="leads", action="view")
    assert allowed is False


# ---------------------------------------------------------------------- geo exceptions


async def test_geo_exception_create_list_revoke(client, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data)
    now = utc_now()

    r = await client.post(
        "/api/v1/geo-exceptions",
        json={
            "employee_id": employee["id"],
            "latitude": 19.0760,
            "longitude": 72.8777,
            "radius_meters": 500,
            "start_date": now.date().isoformat(),
            "end_date": (now + timedelta(days=7)).date().isoformat(),
            "start_time": "09:00",
            "end_time": "18:00",
            "reason": "Approved work-from-home",
        },
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    geo_exception_id = r.json()["data"]["id"]
    assert r.json()["data"]["status"] == "active"

    r = await client.get(f"/api/v1/geo-exceptions?employee_id={employee['id']}", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 1

    r = await client.post(f"/api/v1/geo-exceptions/{geo_exception_id}/revoke", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "revoked"


async def test_geo_exception_requires_either_geo_fence_id_or_coordinates(client, owner_headers, master_data):
    """Backward-compat extension for the geo_fencing module (Stage 1): geo_fence_id is a
    new, optional alternative to specifying latitude/longitude/radius_meters directly —
    but at least one path must fully resolve the exception's own area."""
    employee = await _create_employee(client, owner_headers, master_data)
    now = utc_now()
    r = await client.post(
        "/api/v1/geo-exceptions",
        json={
            "employee_id": employee["id"],
            "start_date": now.date().isoformat(), "end_date": (now + timedelta(days=1)).date().isoformat(),
            "start_time": "09:00", "end_time": "18:00", "reason": "Neither fence nor coordinates given",
        },
        headers=owner_headers,
    )
    assert r.status_code == 422, r.text


async def test_geo_exception_via_geo_fence_id_prefills_location(client, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data)
    r = await client.post(
        "/api/v1/geo-fences",
        json={
            "area_name": "Prefill Fence", "address": "Somewhere", "latitude": 19.0760, "longitude": 72.8777,
            "radius_meters": 1000, "allowed_activities": ["lead_creation"],
        },
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    fence_id = r.json()["data"]["id"]

    now = utc_now()
    r = await client.post(
        "/api/v1/geo-exceptions",
        json={
            "employee_id": employee["id"], "geo_fence_id": fence_id,
            "start_date": now.date().isoformat(), "end_date": (now + timedelta(days=1)).date().isoformat(),
            "start_time": "09:00", "end_time": "18:00", "reason": "Field visit near HQ",
        },
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["geo_fence_id"] == fence_id
    assert data["latitude"] == 19.0760
    assert data["longitude"] == 72.8777
    assert data["radius_meters"] == 1000


async def test_geo_exception_can_be_scoped_to_login_activity(client, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data)
    now = utc_now()
    r = await client.post(
        "/api/v1/geo-exceptions",
        json={
            "employee_id": employee["id"], "activity": "login",
            "latitude": 19.0760, "longitude": 72.8777, "radius_meters": 500,
            "start_date": now.date().isoformat(), "end_date": (now + timedelta(days=1)).date().isoformat(),
            "start_time": "09:00", "end_time": "23:59", "reason": "Work from home",
        },
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["activity"] == "login"

    # Default/omitted activity still reads back as None (blanket — applies to every
    # enforced activity), matching every exception granted before this field existed.
    r2 = await client.post(
        "/api/v1/geo-exceptions",
        json={
            "employee_id": employee["id"],
            "latitude": 19.0760, "longitude": 72.8777, "radius_meters": 500,
            "start_date": now.date().isoformat(), "end_date": (now + timedelta(days=1)).date().isoformat(),
            "start_time": "09:00", "end_time": "23:59", "reason": "Blanket exception",
        },
        headers=owner_headers,
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["data"]["activity"] is None


async def test_geo_exception_rejects_unknown_activity_value(client, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data)
    now = utc_now()
    r = await client.post(
        "/api/v1/geo-exceptions",
        json={
            "employee_id": employee["id"], "activity": "skydiving",
            "latitude": 19.0760, "longitude": 72.8777, "radius_meters": 500,
            "start_date": now.date().isoformat(), "end_date": (now + timedelta(days=1)).date().isoformat(),
            "start_time": "09:00", "end_time": "18:00", "reason": "Invalid activity",
        },
        headers=owner_headers,
    )
    assert r.status_code == 422, r.text


async def test_geo_exception_rejects_same_day_end_time_not_after_start_time(client, owner_headers, master_data):
    """The old date-only check (`end_date < start_date`) let a same-day window with
    end_time <= start_time through uncaught — e.g. 09:00-09:00 or 18:00-09:00 on the
    same day. Must now be rejected as an invalid period."""
    employee = await _create_employee(client, owner_headers, master_data)
    today = utc_now().date().isoformat()
    r = await client.post(
        "/api/v1/geo-exceptions",
        json={
            "employee_id": employee["id"],
            "latitude": 19.0760, "longitude": 72.8777, "radius_meters": 500,
            "start_date": today, "end_date": today,
            "start_time": "18:00", "end_time": "09:00", "reason": "Invalid same-day window",
        },
        headers=owner_headers,
    )
    assert r.status_code == 422, r.text

    r2 = await client.post(
        "/api/v1/geo-exceptions",
        json={
            "employee_id": employee["id"],
            "latitude": 19.0760, "longitude": 72.8777, "radius_meters": 500,
            "start_date": today, "end_date": today,
            "start_time": "09:00", "end_time": "09:00", "reason": "Zero-length window",
        },
        headers=owner_headers,
    )
    assert r2.status_code == 422, r2.text


async def test_geo_exception_create_list_revoke_are_owner_only(client, employee_headers, master_data, owner_headers):
    employee = await _create_employee(client, owner_headers, master_data)
    now = utc_now()
    payload = {
        "employee_id": employee["id"],
        "latitude": 19.0760, "longitude": 72.8777, "radius_meters": 500,
        "start_date": now.date().isoformat(), "end_date": (now + timedelta(days=1)).date().isoformat(),
        "start_time": "09:00", "end_time": "18:00", "reason": "Employee attempting self-service",
    }
    r = await client.post("/api/v1/geo-exceptions", json=payload, headers=employee_headers)
    assert r.status_code == 403, r.text
    r = await client.get(f"/api/v1/geo-exceptions?employee_id={employee['id']}", headers=employee_headers)
    assert r.status_code == 403, r.text

    # An Employee cannot even revoke an exception an Owner already granted to someone else.
    granted = await client.post("/api/v1/geo-exceptions", json=payload, headers=owner_headers)
    assert granted.status_code == 200, granted.text
    r = await client.post(f"/api/v1/geo-exceptions/{granted.json()['data']['id']}/revoke", headers=employee_headers)
    assert r.status_code == 403, r.text
