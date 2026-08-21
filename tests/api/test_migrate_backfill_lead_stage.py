"""Tests for scripts/migrate_backfill_lead_stage.py — the one-time backfill that sets
`Lead.stage` on every pre-existing lead (decision 125, Leads workflow redesign Phase 1)
and adds the "reject" action to an already-seeded `leads:leads` Permission catalog
document. Imports the script directly and monkeypatches its `get_database()` reference
to the test's own mongomock instance, mirroring
`tests/api/test_migrate_decouple_leads_tasks_grants.py`.
"""

import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import migrate_backfill_lead_stage as migration  # noqa: E402


async def _lead_master_data(mock_db) -> dict:
    from app.features.system_settings.models import InsuranceProduct, LeadSource, LoanProduct

    source = LeadSource(name="Website")
    loan_product = LoanProduct(name="Personal Loan")
    insurance_product = InsuranceProduct(name="Health")
    source_id = (await mock_db["lead_sources"].insert_one(source.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    loan_id = (await mock_db["loan_products"].insert_one(loan_product.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    insurance_id = (await mock_db["insurance_products"].insert_one(insurance_product.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    return {"source_id": str(source_id), "loan_product_id": str(loan_id), "insurance_product_id": str(insurance_id)}


async def _create_employee(client, owner_headers, master_data, mobile, email):
    payload = {
        "mobile": mobile, "initial_password": "InitialPass1!", "first_name": "Staff", "last_name": "Member", "email": email,
        "department_id": master_data["department_id"], "designation_id": master_data["designation_id"], "branch_id": master_data["branch_id"],
        "joining_date": "2026-01-15", "employment_type": "full_time",
    }
    r = await client.post("/api/v1/employees", json=payload, headers=owner_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _create_lead(client, owner_headers, lmd, mobile):
    payload = {
        "full_name": "Ravi Kumar", "mobile": mobile, "source_id": lmd["source_id"],
        "product_category": "loan", "product_id": lmd["loan_product_id"],
    }
    r = await client.post("/api/v1/leads", json=payload, headers=owner_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


@pytest.fixture
def _patched_db(mock_db, monkeypatch):
    monkeypatch.setattr(migration, "get_database", lambda: mock_db)
    return mock_db


async def _strip_stage(mock_db, lead_id: str) -> None:
    """Simulates a lead created before `stage` existed — the migration itself is what's
    supposed to backfill it, so tests must first remove the field Pydantic's own default
    would otherwise silently supply on read."""
    from app.utils.helpers import to_object_id

    await mock_db["leads"].update_one({"_id": to_object_id(lead_id)}, {"$unset": {"stage": ""}})


async def test_migration_backfills_assigned_and_fresh_correctly(client, mock_db, owner_headers, master_data, _patched_db):
    lmd = await _lead_master_data(mock_db)
    employee = await _create_employee(client, owner_headers, master_data, "9500000301", "stage1@example.com")

    fresh_lead = await _create_lead(client, owner_headers, lmd, "9611140001")
    assigned_lead = await _create_lead(client, owner_headers, lmd, "9611140002")
    await client.post(f"/api/v1/leads/{assigned_lead['id']}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)

    await _strip_stage(mock_db, fresh_lead["id"])
    await _strip_stage(mock_db, assigned_lead["id"])

    await migration.main()

    r = await client.get(f"/api/v1/leads/{fresh_lead['id']}", headers=owner_headers)
    assert r.json()["data"]["stage"] == "fresh"

    r = await client.get(f"/api/v1/leads/{assigned_lead['id']}", headers=owner_headers)
    assert r.json()["data"]["stage"] == "assigned"


async def test_migration_idempotent_second_run_does_not_touch_already_staged_leads(client, mock_db, owner_headers, master_data, _patched_db):
    lmd = await _lead_master_data(mock_db)
    employee = await _create_employee(client, owner_headers, master_data, "9500000302", "stage2@example.com")
    lead = await _create_lead(client, owner_headers, lmd, "9611140003")
    await client.post(f"/api/v1/leads/{lead['id']}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)
    await _strip_stage(mock_db, lead["id"])

    await migration.main()
    r = await client.get(f"/api/v1/leads/{lead['id']}", headers=owner_headers)
    assert r.json()["data"]["stage"] == "assigned"

    # Move the lead on, THEN re-run the migration — a true no-op backfill (it only ever
    # targets documents with no `stage` field at all) must never revert real progress.
    await client.post(f"/api/v1/leads/{lead['id']}/stage", json={"stage": "document_collection"}, headers=owner_headers)
    await migration.main()

    r = await client.get(f"/api/v1/leads/{lead['id']}", headers=owner_headers)
    assert r.json()["data"]["stage"] == "document_collection"


async def test_migration_adds_reject_action_to_existing_permission_without_wiping_others(client, mock_db, owner_headers, _patched_db):
    r = await client.post(
        "/api/v1/permissions", json={"module": "leads", "resource": "leads", "actions": ["view", "create", "edit", "assign", "export"]},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    permission_id = r.json()["data"]["id"]

    await migration.main()

    r = await client.get("/api/v1/permissions", headers=owner_headers)
    permission = next(p for p in r.json()["data"] if p["id"] == permission_id)
    assert set(permission["actions"]) == {"view", "create", "edit", "assign", "export", "reject"}


async def test_migration_reject_action_backfill_is_idempotent(client, mock_db, owner_headers, _patched_db):
    await client.post(
        "/api/v1/permissions", json={"module": "leads", "resource": "leads", "actions": ["view", "create", "edit", "assign", "export"]},
        headers=owner_headers,
    )

    await migration.main()
    await migration.main()

    r = await client.get("/api/v1/permissions", headers=owner_headers)
    permission = next(p for p in r.json()["data"] if p["module"] == "leads" and p["resource"] == "leads")
    assert permission["actions"].count("reject") == 1
