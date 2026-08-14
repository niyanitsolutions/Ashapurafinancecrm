"""Tests for scripts/migrate_decouple_leads_tasks_grants.py — the one-time backfill that
gives an existing employee's "Add Employee"-created role explicit Leads/Tasks grants
once the old frontend's implicit auto-grant-on-any-business-module-checked coupling is
removed (see the Employee Permission Matrix redesign). Imports the script directly
(mirroring how the script itself locates `backend/app`) and monkeypatches its
`get_database()` reference to the test's own mongomock instance, since the script is a
standalone CLI tool, not part of the FastAPI app's dependency-injection graph.
"""

import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import migrate_decouple_leads_tasks_grants as migration  # noqa: E402


async def _create_employee(client, owner_headers, master_data, mobile, email):
    payload = {
        "mobile": mobile, "initial_password": "InitialPass1!", "first_name": "Staff", "last_name": "Member", "email": email,
        "department_id": master_data["department_id"], "designation_id": master_data["designation_id"], "branch_id": master_data["branch_id"],
        "joining_date": "2026-01-15", "employment_type": "full_time",
    }
    r = await client.post("/api/v1/employees", json=payload, headers=owner_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _seed_catalog(client, owner_headers):
    await client.post(
        "/api/v1/permissions", json={"module": "leads", "resource": "leads", "actions": ["view", "create", "edit", "assign", "export"]},
        headers=owner_headers,
    )
    await client.post(
        "/api/v1/permissions", json={"module": "reminders", "resource": "tasks", "actions": ["view", "create", "edit"]},
        headers=owner_headers,
    )
    await client.post(
        "/api/v1/permissions",
        json={"module": "loan_management", "resource": "applications", "actions": ["view", "edit", "approve", "reject", "assign"]},
        headers=owner_headers,
    )


async def _create_auto_role_with_loan_grant(client, owner_headers, employee_id) -> str:
    role = await client.post(
        "/api/v1/roles", json={"name": "Test Employee", "description": migration.AUTO_ROLE_DESCRIPTION}, headers=owner_headers
    )
    role_id = role.json()["data"]["id"]
    permissions = (await client.get("/api/v1/permissions", headers=owner_headers)).json()["data"]
    loan_permission_id = next(p["id"] for p in permissions if p["module"] == "loan_management" and p["resource"] == "applications")
    await client.put(
        f"/api/v1/roles/{role_id}/permissions",
        json={"grants": [{"permission_id": loan_permission_id, "granted_actions": ["view"]}]},
        headers=owner_headers,
    )
    await client.post(f"/api/v1/roles/{role_id}/assign", json={"employee_id": employee_id}, headers=owner_headers)
    return role_id


@pytest.fixture
def _patched_db(mock_db, monkeypatch):
    monkeypatch.setattr(migration, "get_database", lambda: mock_db)
    return mock_db


async def test_migration_backfills_leads_tasks_without_wiping_existing_grant(client, mock_db, owner_headers, master_data, _patched_db):
    await _seed_catalog(client, owner_headers)
    employee = await _create_employee(client, owner_headers, master_data, "9500000201", "migrate1@example.com")
    role_id = await _create_auto_role_with_loan_grant(client, owner_headers, employee["id"])

    await migration.main()

    grants = (await client.get(f"/api/v1/roles/{role_id}/permissions", headers=owner_headers)).json()["data"]
    by_module_resource = {(g["module"], g["resource"]): g["granted_actions"] for g in grants}

    assert by_module_resource[("loan_management", "applications")] == ["view"]  # untouched, not wiped
    assert set(by_module_resource[("leads", "leads")]) == {"view", "create", "edit", "export"}
    assert set(by_module_resource[("reminders", "tasks")]) == {"view", "create", "edit"}


async def test_migration_idempotent_second_run(client, mock_db, owner_headers, master_data, _patched_db):
    await _seed_catalog(client, owner_headers)
    employee = await _create_employee(client, owner_headers, master_data, "9500000202", "migrate2@example.com")
    role_id = await _create_auto_role_with_loan_grant(client, owner_headers, employee["id"])

    await migration.main()
    first_run_grants = (await client.get(f"/api/v1/roles/{role_id}/permissions", headers=owner_headers)).json()["data"]

    await migration.main()  # second run must be a true no-op
    second_run_grants = (await client.get(f"/api/v1/roles/{role_id}/permissions", headers=owner_headers)).json()["data"]

    assert len(second_run_grants) == len(first_run_grants) == 3
    assert {(g["module"], g["resource"]): tuple(sorted(g["granted_actions"])) for g in first_run_grants} == {
        (g["module"], g["resource"]): tuple(sorted(g["granted_actions"])) for g in second_run_grants
    }


async def test_migration_skips_role_without_business_module_grant(client, mock_db, owner_headers, master_data, _patched_db):
    await _seed_catalog(client, owner_headers)
    employee = await _create_employee(client, owner_headers, master_data, "9500000203", "migrate3@example.com")
    role = await client.post(
        "/api/v1/roles", json={"name": "Empty Role", "description": migration.AUTO_ROLE_DESCRIPTION}, headers=owner_headers
    )
    role_id = role.json()["data"]["id"]
    await client.post(f"/api/v1/roles/{role_id}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)

    await migration.main()

    grants = (await client.get(f"/api/v1/roles/{role_id}/permissions", headers=owner_headers)).json()["data"]
    assert grants == []
