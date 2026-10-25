import asyncio
from datetime import timedelta

import pytest
from app.features.daily_operations.catalog import install_catalog
from app.utils.datetime import utc_now
from bson import ObjectId
from test_daily_operations import create, preview, seed_case
from test_leads import _create_employee, _create_lead, _lead_master_data
from test_workflow import _login

BASE = "/api/v1/daily-operations"


@pytest.fixture
async def staff(client, mock_db, owner_headers, master_data):
    await install_catalog(mock_db)
    first = await _create_employee(client, owner_headers, master_data)
    second = await _create_employee(
        client,
        owner_headers,
        master_data,
        mobile="9511111122",
        email="second.synthetic@example.com",
    )
    return (
        first,
        await _login(client, "9511111111", "InitialPass1!"),
        second,
        await _login(client, "9511111122", "InitialPass1!"),
    )


def follow(**changes):
    return {
        "date": "2026-10-25",
        "remarks_date": "2026-10-25",
        "bank": "Synthetic Bank",
        "loan_type": "Personal Loan",
        "customer_name": "Synthetic Customer",
        "customer_number": "9000000000",
        "status": "NEXT FOLLOW UP",
        "next_action": "Collect documents",
        "due_date": "2026-10-26",
        "remarks": "Customer will provide documents",
        **changes,
    }


def progress(**changes):
    return {
        "date": "2026-10-25",
        "bank": "Synthetic Bank",
        "customer_name": "Synthetic Customer",
        "customer_number": "9000000000",
        "status": "Documents submitted",
        "next_action": "Call the bank",
        "due_date": "2026-10-26",
        **changes,
    }


async def test_default_access_returns_effective_actions_and_keeps_other_modules_restricted(
    client, mock_db, staff
):
    first, headers, _, _ = staff
    grants = (await client.get("/api/v1/my-permissions", headers=headers)).json()[
        "data"
    ]["grants"]
    for area in ["follow-ups", "progress", "issues"]:
        assert {"view", "create", "edit", "export", "import"} <= set(
            grants[f"daily_operations:{area}"]
        )
        assert "delete" not in grants[f"daily_operations:{area}"]
    assert set(grants["daily_operations:sessions"]) == {"view", "export"}
    assert "loan_management:applications" not in grants
    assert (await client.get("/api/v1/employees", headers=headers)).status_code == 403
    data = (await client.get(f"{BASE}/lookups", headers=headers)).json()["data"]
    assert data["self_id"] == first["id"]
    assert [e["id"] for e in data["employees"]] == [first["id"]]
    assert "mobile" not in data["employees"][0]


async def test_manual_names_do_not_create_accounts_and_employee_cannot_assign_another_account(
    client, mock_db, staff, owner_headers
):
    first, headers, second, other_headers = staff
    before_users = await mock_db.users.count_documents({})
    record = await create(
        client, headers, "follow-ups", follow(employee_name="Synthetic manual name")
    )
    assert record["lead_id"] is None
    assert record["assigned_to"] == first["id"]
    assert record["employee_name"] == "Synthetic manual name"
    assert await mock_db.users.count_documents({}) == before_users
    assert (
        await client.get(f"{BASE}/follow-ups/{record['id']}", headers=other_headers)
    ).status_code == 403
    assert (
        await client.get(
            f"{BASE}/follow-ups?employee_name=Synthetic", headers=other_headers
        )
    ).json()["data"]["total"] == 0
    assert (
        await client.get(
            f"{BASE}/follow-ups?employee_name=Synthetic", headers=owner_headers
        )
    ).json()["data"]["total"] == 1
    assert (
        await client.post(
            f"{BASE}/follow-ups", headers=headers, json=follow(assigned_to=second["id"])
        )
    ).status_code == 403
    changed = await client.patch(
        f"{BASE}/follow-ups/{record['id']}",
        headers=headers,
        json=follow(
            employee_name="Synthetic manual name", remarks="Second update", version=1
        ),
    )
    assert changed.status_code == 200, changed.text
    assert (
        changed.json()["data"]["history"][-1]["before"]["remarks"]
        == "Customer will provide documents"
    )
    exported = await client.get(f"{BASE}/follow-ups/export", headers=other_headers)
    assert "Synthetic Customer" not in exported.text


async def test_owner_can_assign_by_employee_name(client, mock_db, staff, owner_headers):
    first, headers, _, _ = staff
    employee = await mock_db.employees.find_one({"_id": ObjectId(first["id"])})
    # Make the fixture name unique so a name cannot silently select one of two accounts.
    await mock_db.employees.update_one(
        {"_id": employee["_id"]}, {"$set": {"display_name": "Synthetic First Employee"}}
    )
    record = await create(
        client,
        owner_headers,
        "follow-ups",
        follow(employee_name="Synthetic First Employee"),
    )
    assert record["assigned_to"] == first["id"]
    assert (await client.get(f"{BASE}/follow-ups", headers=headers)).json()["data"][
        "total"
    ] == 1


async def test_manual_progress_add_edit_and_owner_only_delete(
    client, mock_db, staff, owner_headers
):
    first, headers, _, other_headers = staff
    payload = progress(
        approved_amount=100000, disbursed_amount=90000, disbursed_at="2026-10-25"
    )
    record = await create(client, headers, "progress", payload)
    result = (await client.get(f"{BASE}/progress", headers=headers)).json()["data"]
    assert result["total"] == 1 and result["items"][0]["id"] == record["id"]
    assert (
        result["metrics"]["disbursed_amount"] == 0
    )  # Reported daily data is not a verified disbursement.
    assert (
        await client.get(f"{BASE}/progress/{record['id']}", headers=other_headers)
    ).status_code == 403
    changed = await client.patch(
        f"{BASE}/progress/{record['id']}",
        headers=headers,
        json={**payload, "status": "Bank review pending", "version": 1},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["data"]["version"] == 2
    assert (
        await client.patch(
            f"{BASE}/progress/{record['id']}",
            headers=headers,
            json={**payload, "version": 1},
        )
    ).status_code == 409
    assert (
        await client.request(
            "DELETE",
            f"{BASE}/progress/{record['id']}",
            headers=headers,
            json={"version": 2},
        )
    ).status_code == 403
    assert (
        await client.request(
            "DELETE",
            f"{BASE}/progress/{record['id']}",
            headers=owner_headers,
            json={"version": 1},
        )
    ).status_code == 409
    response = await client.request(
        "DELETE",
        f"{BASE}/progress/{record['id']}",
        headers=owner_headers,
        json={"version": 2},
    )
    assert response.status_code == 200, response.text
    assert (await client.get(f"{BASE}/progress", headers=owner_headers)).json()["data"][
        "total"
    ] == 0
    stored = await mock_db.daily_progress_entries.find_one(
        {"_id": ObjectId(record["id"])}
    )
    assert stored["is_deleted"] and stored["history"][-1]["action"] == "deleted"
    assert stored["assigned_to"] == first["id"]


async def test_crm_progress_edit_is_an_annotation_and_owner_removal_never_deletes_a_loan(
    client, mock_db, staff, owner_headers
):
    first, headers, _second, other_headers = staff
    master = await _lead_master_data(mock_db)
    lead = await _create_lead(client, owner_headers, master)
    await mock_db.leads.update_one(
        {"_id": ObjectId(lead["id"])}, {"$set": {"assigned_to": first["id"]}}
    )
    case_id = await seed_case(mock_db, lead["id"])
    result = (await client.get(f"{BASE}/progress", headers=headers)).json()["data"]
    assert result["total"] == 1 and result["items"][0]["version"] == 0
    payload = progress(case_id=case_id, status="Waiting for bank response")
    response = await client.patch(
        f"{BASE}/progress/{case_id}", headers=headers, json={**payload, "version": 0}
    )
    assert response.status_code == 200, response.text
    assert (await client.get(f"{BASE}/progress", headers=headers)).json()["data"][
        "total"
    ] == 1
    assert (await client.get(f"{BASE}/progress", headers=other_headers)).json()["data"][
        "total"
    ] == 0
    assert (
        await client.get(f"{BASE}/progress/{case_id}", headers=other_headers)
    ).status_code == 403
    original = await mock_db.application_workflows.find_one({"_id": ObjectId(case_id)})
    assert (
        original["current_status"] == "credit_evaluation"
        and original["loan_details"]["offered_amount"] == 1000
    )
    assert (
        await client.patch(
            f"{BASE}/progress/{case_id}",
            headers=headers,
            json={**payload, "approved_amount": 999999, "version": 1},
        )
    ).status_code == 422
    assert (
        await client.request(
            "DELETE",
            f"{BASE}/progress/{case_id}",
            headers=owner_headers,
            json={"version": 1},
        )
    ).status_code == 200
    assert (await client.get(f"{BASE}/progress", headers=owner_headers)).json()["data"][
        "total"
    ] == 0
    original = await mock_db.application_workflows.find_one({"_id": ObjectId(case_id)})
    assert (
        not original["is_deleted"] and original["current_status"] == "credit_evaluation"
    )


@pytest.mark.parametrize("area", ["follow-ups", "issues"])
async def test_delete_is_owner_only_and_retains_history(
    client, mock_db, staff, owner_headers, area
):
    _, headers, _, _ = staff
    payload = (
        follow()
        if area == "follow-ups"
        else {"date": "2026-10-25", "inquiry": "Synthetic test issue"}
    )
    row = await create(client, headers, area, payload)
    assert (
        await client.request(
            "DELETE", f"{BASE}/{area}/{row['id']}", headers=headers, json={"version": 1}
        )
    ).status_code == 403
    response = await client.request(
        "DELETE",
        f"{BASE}/{area}/{row['id']}",
        headers=owner_headers,
        json={"version": 1},
    )
    assert response.status_code == 200, response.text
    assert (
        await client.get(f"{BASE}/{area}/{row['id']}", headers=owner_headers)
    ).status_code == 404
    assert (await client.get(f"{BASE}/{area}", headers=owner_headers)).json()["data"][
        "total"
    ] == 0


async def test_owner_session_removal_preserves_authentication_data(
    client, mock_db, staff, owner_headers
):
    first, headers, _, _ = staff
    family = "synthetic-removable-session"
    now = utc_now()
    await mock_db.sessions.insert_one(
        {
            "family_id": family,
            "user_id": first["user_id"],
            "token_id": str(ObjectId()),
            "login_at": now - timedelta(hours=1),
            "logout_at": None,
            "updated_at": now,
            "status": "active",
            "is_deleted": False,
        }
    )
    assert (
        await client.request(
            "DELETE", f"{BASE}/sessions/{family}", headers=headers, json={"version": 0}
        )
    ).status_code == 403
    assert (
        await client.request(
            "DELETE",
            f"{BASE}/sessions/{family}",
            headers=owner_headers,
            json={"version": 0},
        )
    ).status_code == 200
    records = (await client.get(f"{BASE}/sessions", headers=owner_headers)).json()[
        "data"
    ]["items"]
    assert family not in [row["id"] for row in records]
    stored = await mock_db.sessions.find_one({"family_id": family})
    assert (
        stored["status"] == "active"
        and not stored["is_deleted"]
        and stored["logout_at"] is None
    )


async def test_manual_spreadsheet_imports_create_rows_without_crm_ids_and_are_retry_safe(
    client, mock_db, staff
):
    _, headers, _, _ = staff
    for area, payload in [("follow-ups", follow()), ("progress", progress())]:
        batch = await preview(client, headers, [payload], kind=area, format="xlsx")
        assert not batch["rows"][0]["errors"], batch
        url = f"{BASE}/transfers/{batch['id']}/confirm"
        response = await client.post(url, headers=headers, json={"confirmed": True})
        assert response.json()["data"]["inserted"] == 1, response.text
        assert (
            await client.post(url, headers=headers, json={"confirmed": True})
        ).json()["data"]["skipped"] == 1
    assert await mock_db.leads.count_documents({}) == 0
    assert await mock_db.application_workflows.count_documents({}) == 0


async def test_progress_concurrent_edits_allow_only_one_winner(client, mock_db, staff):
    _, headers, _, _ = staff
    row = await create(client, headers, "progress", progress())
    responses = await asyncio.gather(
        *[
            client.patch(
                f"{BASE}/progress/{row['id']}",
                headers=headers,
                json=progress(status=f"Synthetic update {index}", version=1),
            )
            for index in range(2)
        ]
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert (
        len(
            (
                await mock_db.daily_progress_entries.find_one(
                    {"_id": ObjectId(row["id"])}
                )
            )["history"]
        )
        == 2
    )


async def test_linked_follow_up_tracks_current_case_owner_after_reassignment(
    client, mock_db, staff, owner_headers
):
    first, headers, second, other_headers = staff
    master = await _lead_master_data(mock_db)
    lead = await _create_lead(client, owner_headers, master)
    await mock_db.leads.update_one(
        {"_id": ObjectId(lead["id"])}, {"$set": {"assigned_to": first["id"]}}
    )
    case_id = await seed_case(mock_db, lead["id"])
    row = await create(client, headers, "follow-ups", follow(case_id=case_id))
    assert (await client.get(f"{BASE}/follow-ups", headers=headers)).json()["data"][
        "total"
    ] == 1
    await mock_db.application_workflows.update_one(
        {"_id": ObjectId(case_id)}, {"$set": {"assigned_to": second["id"]}}
    )
    assert (await client.get(f"{BASE}/follow-ups", headers=headers)).json()["data"][
        "total"
    ] == 0
    assert (
        await client.get(f"{BASE}/follow-ups/{row['id']}", headers=headers)
    ).status_code == 403
    assert (await client.get(f"{BASE}/follow-ups", headers=other_headers)).json()[
        "data"
    ]["total"] == 1
    response = await client.patch(
        f"{BASE}/follow-ups/{row['id']}",
        headers=other_headers,
        json=follow(case_id=case_id, version=1, remarks="New assigned employee update"),
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["assigned_to"] == second["id"]


async def test_inactive_employee_does_not_receive_default_access(
    client, mock_db, staff
):
    first, headers, _, _ = staff
    await mock_db.employees.update_one(
        {"_id": ObjectId(first["id"])}, {"$set": {"status": "inactive"}}
    )
    assert (await client.get(f"{BASE}/lookups", headers=headers)).status_code == 403
    response = await client.get("/api/v1/dashboard/nav", headers=headers)
    assert not any(item["key"].startswith("daily_") for item in response.json()["data"])


@pytest.mark.parametrize(
    "changes",
    [
        {"approved_amount": -1},
        {"approved_amount": 1.001},
        {"customer_number": "not-a-phone"},
        {"disbursed_amount": 100, "disbursed_at": None},
    ],
)
async def test_manual_progress_rejects_invalid_amounts_and_phone(
    client, staff, changes
):
    _, headers, _, _ = staff
    response = await client.post(
        f"{BASE}/progress", headers=headers, json=progress(**changes)
    )
    assert response.status_code == 422
