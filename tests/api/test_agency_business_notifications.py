from bson import ObjectId
from test_insurance_employee_visibility import _employee_with_permissions
from test_recruitment_advisors import _add_business, _promote_advisor
from test_support import _register_customer


async def test_agency_update_preserves_historical_agent_code(client, mock_db, owner_headers):
    advisor = await _promote_advisor(client, owner_headers, mock_db)
    aid = advisor["id"]
    await mock_db.advisors.update_one(
        {"_id": ObjectId(aid)}, {"$set": {"agent_code": "HISTORICAL"}}
    )
    response = await client.patch(
        f"/api/v1/advisors/{aid}",
        headers=owner_headers,
        json={"agency_code": "25093H", "password": "AgencyPass", "joining_date": "2026-09-23"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["agency_code"] == "25093H"
    assert response.json()["data"]["has_password"] is True
    stored = await mock_db.advisors.find_one({"_id": ObjectId(aid)})
    assert stored["agent_code"] == "HISTORICAL"
    assert stored["joining_date"] is not None
    assert "AgencyPass" not in response.text


async def test_advisor_business_owner_employee_and_unauthorized(
    client, mock_db, owner_headers, master_data, employee_headers
):
    advisor = await _promote_advisor(client, owner_headers, mock_db)
    assert (await _add_business(client, owner_headers, advisor["id"])).status_code == 200
    assert (await _add_business(client, employee_headers, advisor["id"])).status_code == 403
    _employee, headers = await _employee_with_permissions(
        client,
        owner_headers,
        master_data,
        mobile="9811000091",
        email="business@example.com",
        actions=["view", "edit"],
    )
    response = await _add_business(client, headers, advisor["id"])
    assert response.status_code == 200, response.text
    assert (await _add_business(client, headers, advisor["id"], premium=-1)).status_code == 422
    # The new business permission cannot reveal passwords or edit Agency details.
    assert (
        await client.get(f"/api/v1/advisors/{advisor['id']}/password", headers=headers)
    ).status_code == 403
    assert (
        await client.patch(
            f"/api/v1/advisors/{advisor['id']}", json={"agency_code": "bad"}, headers=headers
        )
    ).status_code == 403


async def test_support_notification_references_ticket_without_bypassing_access(
    client, mock_db, owner_headers, employee_headers
):
    headers = await _register_customer(client, mock_db, mobile="9633333391")
    response = await client.post(
        "/api/v1/support-tickets",
        json={
            "issue_type": "documents",
            "priority": "medium",
            "subject": "Pan card",
            "message": "Help",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    ticket_id = response.json()["data"]["id"]
    notification = await mock_db.notifications.find_one(
        {"notification_type": "support_request_raised"}
    )
    assert notification["entity_type"] == "support_ticket"
    assert notification["entity_id"] == ticket_id
    assert (
        await client.get(f"/api/v1/support-tickets/{ticket_id}", headers=owner_headers)
    ).status_code == 200
    assert (
        await client.get(f"/api/v1/support-tickets/{ticket_id}", headers=employee_headers)
    ).status_code == 403
