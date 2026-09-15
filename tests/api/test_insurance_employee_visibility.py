"""Regression coverage for Insurance employee visibility and case-scoped documents.

Insurance keeps its Advisor assignment on ``ApplicationWorkflow.assigned_to``.  The
employee who may work a policy lead is instead the authoritative
``Application.assigned_to`` employee, alongside the workflow/application creator.
"""

import pytest
from bson import ObjectId
from test_insurance_manual_lead import _create
from test_insurance_policy_leads import _insurance_product_with_schema
from test_workflow import _create_employee, _login, _seed_workflow_definitions

pytestmark = pytest.mark.asyncio


async def _grant_insurance_permissions(client, owner_headers, employee_id: str, actions: list[str]):
    """Use the existing catalog row when more than one employee needs a test role."""
    permission_response = await client.post(
        "/api/v1/permissions",
        json={"module": "insurance_management", "resource": "applications", "actions": ["view", "edit", "assign"]},
        headers=owner_headers,
    )
    if permission_response.status_code == 409:
        permissions = await client.get("/api/v1/permissions", headers=owner_headers)
        assert permissions.status_code == 200, permissions.text
        permission = next(
            item for item in permissions.json()["data"]
            if item["module"] == "insurance_management" and item["resource"] == "applications"
        )
    else:
        assert permission_response.status_code == 200, permission_response.text
        permission = permission_response.json()["data"]
    role_response = await client.post(
        "/api/v1/roles", json={"name": f"Insurance visibility {employee_id}"}, headers=owner_headers
    )
    assert role_response.status_code == 200, role_response.text
    role = role_response.json()["data"]
    grant = await client.put(
        f"/api/v1/roles/{role['id']}/permissions",
        json={"grants": [{"permission_id": permission["id"], "granted_actions": actions}]}, headers=owner_headers,
    )
    assert grant.status_code == 200, grant.text
    assigned = await client.post(f"/api/v1/roles/{role['id']}/assign", json={"employee_id": employee_id}, headers=owner_headers)
    assert assigned.status_code == 200, assigned.text


async def _employee_with_permissions(client, owner_headers, master_data, *, mobile: str, email: str, actions: list[str]):
    employee = await _create_employee(client, owner_headers, master_data, mobile=mobile, email=email)
    await _grant_insurance_permissions(client, owner_headers, employee["id"], actions)
    return employee, await _login(client, mobile, "InitialPass1!")


async def _case_created_by_employee(client, mock_db, owner_headers, master_data):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name="Employee Visibility Plan", docs=["PAN"])
    creator, creator_headers = await _employee_with_permissions(
        client, owner_headers, master_data, mobile="9811000001", email="insurance.creator@example.com",
        actions=["view", "edit", "assign"],
    )
    assignee, assignee_headers = await _employee_with_permissions(
        client, owner_headers, master_data, mobile="9811000002", email="insurance.assignee@example.com",
        actions=["view", "edit"],
    )
    unrelated, unrelated_headers = await _employee_with_permissions(
        client, owner_headers, master_data, mobile="9811000003", email="insurance.unrelated@example.com",
        actions=["view", "edit"],
    )
    response = await _create(client, creator_headers, product, mobile="9811000010", stage="policy_document")
    assert response.status_code == 200, response.text
    case = response.json()["data"]
    application_id = case["application_id"]
    return {
        "case": case,
        "application_id": application_id,
        "creator": creator,
        "creator_headers": creator_headers,
        "assignee": assignee,
        "assignee_headers": assignee_headers,
        "unrelated": unrelated,
        "unrelated_headers": unrelated_headers,
        "product": product,
    }


async def _assign_application(client, owner_headers, application_id: str, employee_id: str):
    response = await client.post(
        f"/api/v1/applications/{application_id}/assign", json={"employee_id": employee_id}, headers=owner_headers
    )
    assert response.status_code == 200, response.text


async def test_owner_creator_and_application_assignee_share_insurance_case_visibility(
    client, mock_db, owner_headers, master_data
):
    data = await _case_created_by_employee(client, mock_db, owner_headers, master_data)
    case_id = data["case"]["id"]
    await _assign_application(client, owner_headers, data["application_id"], data["assignee"]["id"])

    # Owner, creator and current Application assignee can all list and open the case.
    for headers in (owner_headers, data["creator_headers"], data["assignee_headers"]):
        listed = await client.get("/api/v1/insurance-cases", headers=headers)
        assert listed.status_code == 200, listed.text
        assert case_id in {item["id"] for item in listed.json()["data"]}
        detail = await client.get(f"/api/v1/insurance-cases/{case_id}", headers=headers)
        assert detail.status_code == 200, detail.text

    # The Advisor assignment remains untouched when an Application employee is assigned.
    workflow = await mock_db["application_workflows"].find_one({"_id": ObjectId(case_id)})
    assert workflow["assigned_to"] is None

    listed = await client.get("/api/v1/insurance-cases", headers=data["unrelated_headers"])
    assert listed.status_code == 200, listed.text
    assert case_id not in {item["id"] for item in listed.json()["data"]}
    assert (await client.get(f"/api/v1/insurance-cases/{case_id}", headers=data["unrelated_headers"])).status_code == 403
    assert (await client.get(f"/api/v1/insurance-cases/{case_id}/timeline", headers=data["unrelated_headers"])).status_code == 403


async def test_application_reassignment_updates_active_insurance_employee_access(client, mock_db, owner_headers, master_data):
    data = await _case_created_by_employee(client, mock_db, owner_headers, master_data)
    case_id = data["case"]["id"]
    replacement, replacement_headers = await _employee_with_permissions(
        client, owner_headers, master_data, mobile="9811000004", email="insurance.replacement@example.com",
        actions=["view", "edit"],
    )

    await _assign_application(client, owner_headers, data["application_id"], data["assignee"]["id"])
    assert (await client.get(f"/api/v1/insurance-cases/{case_id}", headers=data["assignee_headers"])).status_code == 200

    await _assign_application(client, owner_headers, data["application_id"], replacement["id"])
    # The creator retains access, while the former employee assignee does not.
    assert (await client.get(f"/api/v1/insurance-cases/{case_id}", headers=data["creator_headers"])).status_code == 200
    assert (await client.get(f"/api/v1/insurance-cases/{case_id}", headers=data["assignee_headers"])).status_code == 403
    assert (await client.get(f"/api/v1/insurance-cases/{case_id}", headers=replacement_headers)).status_code == 200


async def test_self_assignment_does_not_expose_case_to_other_employees(client, mock_db, owner_headers, master_data):
    data = await _case_created_by_employee(client, mock_db, owner_headers, master_data)
    case_id = data["case"]["id"]
    await _assign_application(client, owner_headers, data["application_id"], data["creator"]["id"])

    assert (await client.get(f"/api/v1/insurance-cases/{case_id}", headers=data["creator_headers"])).status_code == 200
    assert (await client.get(f"/api/v1/insurance-cases/{case_id}", headers=data["assignee_headers"])).status_code == 403
    assert (await client.get(f"/api/v1/insurance-cases/{case_id}", headers=data["unrelated_headers"])).status_code == 403


async def test_policy_document_upload_history_and_idor_use_case_visibility(client, mock_db, owner_headers, master_data):
    data = await _case_created_by_employee(client, mock_db, owner_headers, master_data)
    case_id = data["case"]["id"]
    document_type_id = data["product"]["document_type_id"]
    await _assign_application(client, owner_headers, data["application_id"], data["assignee"]["id"])

    # Creator receives the Insurance-scoped presigned URL and confirms the upload.
    upload = await client.post(
        f"/api/v1/insurance-cases/{case_id}/documents/upload-url",
        json={"document_type_id": document_type_id, "file_name": "creator-pan.pdf", "content_type": "application/pdf"},
        headers=data["creator_headers"],
    )
    assert upload.status_code == 200, upload.text
    confirmed = await client.post(
        f"/api/v1/insurance-cases/{case_id}/documents/confirm",
        json={"document_type_id": document_type_id, "file_name": "creator-pan.pdf", "content_type": "application/pdf", "s3_key": upload.json()["data"]["s3_key"]},
        headers=data["creator_headers"],
    )
    assert confirmed.status_code == 200, confirmed.text

    # Refresh/list and history are available to the different current assignee.
    refreshed = await client.get(f"/api/v1/insurance-cases/{case_id}/documents", headers=data["assignee_headers"])
    assert refreshed.status_code == 200, refreshed.text
    assert [doc["file_name"] for doc in refreshed.json()["data"]] == ["creator-pan.pdf"]
    history = await client.get(
        f"/api/v1/insurance-cases/{case_id}/documents/{document_type_id}/history", headers=data["assignee_headers"]
    )
    assert history.status_code == 200, history.text
    assert history.json()["data"][0]["file_name"] == "creator-pan.pdf"

    # A permitted but unrelated employee cannot enumerate, mint an upload URL, or
    # confirm an upload using a guessed case ID.
    assert (await client.get(f"/api/v1/insurance-cases/{case_id}/documents", headers=data["unrelated_headers"])).status_code == 403
    denied_url = await client.post(
        f"/api/v1/insurance-cases/{case_id}/documents/upload-url",
        json={"document_type_id": document_type_id, "file_name": "stolen.pdf"}, headers=data["unrelated_headers"],
    )
    assert denied_url.status_code == 403
    denied_confirm = await client.post(
        f"/api/v1/insurance-cases/{case_id}/documents/confirm",
        json={"document_type_id": document_type_id, "file_name": "stolen.pdf", "s3_key": "untrusted"},
        headers=data["unrelated_headers"],
    )
    assert denied_confirm.status_code == 403


async def test_case_scoped_upload_still_requires_existing_edit_permission(client, mock_db, owner_headers, master_data):
    data = await _case_created_by_employee(client, mock_db, owner_headers, master_data)
    case_id = data["case"]["id"]
    view_only, view_only_headers = await _employee_with_permissions(
        client, owner_headers, master_data, mobile="9811000005", email="insurance.viewonly@example.com", actions=["view"]
    )
    await _assign_application(client, owner_headers, data["application_id"], view_only["id"])

    assert (await client.get(f"/api/v1/insurance-cases/{case_id}", headers=view_only_headers)).status_code == 200
    upload = await client.post(
        f"/api/v1/insurance-cases/{case_id}/documents/upload-url",
        json={"document_type_id": data["product"]["document_type_id"], "file_name": "no-edit.pdf"}, headers=view_only_headers,
    )
    assert upload.status_code == 403
