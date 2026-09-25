from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId
from test_insurance_employee_visibility import _employee_with_permissions

from app.features.recruitment.models import Advisor, AdvisorBusiness
from app.features.system_settings.models import InsuranceProduct
from app.features.workflow_engine.constants import CaseType, InsuranceStatus
from app.features.workflow_engine.models import ApplicationWorkflow, InsuranceCaseDetails

pytestmark = pytest.mark.asyncio
BASE = "/api/v1/insurance-analytics"


async def _insert(collection, model):
    result = await collection.insert_one(model.model_dump(by_alias=True, exclude={"id"}))
    return str(result.inserted_id)


async def _seed_analytics(mock_db):
    advisor = Advisor(
        advisor_code="AFS-ADV-000001",
        recruitment_lead_id=str(ObjectId()),
        full_name="Kishan",
        mobile="9811111111",
    )
    advisor_id = await _insert(mock_db["advisors"], advisor)
    now = datetime.now(UTC)
    for name, premium in (("Smart Term", 80000.10), ("Health Secure", 55000.20)):
        business = AdvisorBusiness(
            advisor_id=advisor_id,
            customer_name=f"{name} Customer",
            product_category="protection",
            product_name=name,
            premium=premium,
            ppt=10,
            pt=40,
            policy_issue_date=now,
        )
        await _insert(mock_db["advisor_business"], business)
    product = InsuranceProduct(name="Smart Term", category_id=str(ObjectId()))
    product_id = await _insert(mock_db["insurance_products"], product)
    case_ids = []
    for index, (status, premium) in enumerate(
        ((InsuranceStatus.POLICY_ISSUED, 64000.10), (InsuranceStatus.PAYMENT, 55000.20)), 1
    ):
        case = ApplicationWorkflow(
            case_code=f"AFS-INS-{index:06d}",
            case_type=CaseType.INSURANCE,
            application_id=str(ObjectId()),
            customer_id=str(ObjectId()),
            product_id=product_id,
            product_category="insurance",
            assigned_to=advisor_id,
            current_status=status,
            insurance_details=InsuranceCaseDetails(
                premium_amount=premium,
                policy_issue_date=now if status == InsuranceStatus.POLICY_ISSUED else None,
            ),
        )
        case_ids.append(await _insert(mock_db["application_workflows"], case))
    return advisor_id, product_id, case_ids


async def test_owner_analytics_keeps_business_and_policy_datasets_separate_and_drillable(
    client, mock_db, owner_headers
):
    advisor_id, product_id, case_ids = await _seed_analytics(mock_db)
    overview = await client.get(f"{BASE}/overview", headers=owner_headers)
    assert overview.status_code == 200, overview.text
    data = overview.json()["data"]
    assert data["summary"] == {
        "total_advisors": 1,
        "total_business": 2,
        "business_premium": 135000.3,
        "total_policy_leads": 2,
        "total_policy_issued": 1,
        "policy_premium": 119000.3,
    }
    assert {item["stage"]: item["count"] for item in data["pipeline"]}["policy_issued"] == 1

    advisors = await client.get(f"{BASE}/advisors", headers=owner_headers)
    assert advisors.json()["data"][0]["businesses"] == 2
    work = await client.get(f"{BASE}/advisors/{advisor_id}", headers=owner_headers)
    assert {
        item["product_name"]: item["businesses"] for item in work.json()["data"]["products"]
    } == {"Health Secure": 1, "Smart Term": 1}

    products = await client.get(f"{BASE}/products", headers=owner_headers)
    assert products.json()["data"] == [
        {
            "product_id": product_id,
            "product_name": "Smart Term",
            "leads": 2,
            "issued": 1,
            "premium": 119000.3,
        }
    ]
    detail = await client.get(f"{BASE}/products/{product_id}", headers=owner_headers)
    assert {item["id"] for item in detail.json()["data"]["leads"]} == set(case_ids)


async def test_filters_use_created_date_and_canonical_policy_fields(client, mock_db, owner_headers):
    advisor_id, product_id, _ = await _seed_analytics(mock_db)
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).date().isoformat()
    empty = await client.get(
        f"{BASE}/overview?date_from={tomorrow}&date_to={tomorrow}&advisor_id={advisor_id}&product_id={product_id}&stage=policy_issued",
        headers=owner_headers,
    )
    assert empty.status_code == 200
    assert empty.json()["data"]["summary"]["total_business"] == 0
    assert empty.json()["data"]["summary"]["total_policy_leads"] == 0
    invalid = await client.get(
        f"{BASE}/overview?date_from=2026-09-25&date_to=2026-09-01", headers=owner_headers
    )
    assert invalid.status_code == 422

    today = datetime.now(UTC).date().isoformat()
    await mock_db["application_workflows"].update_one(
        {"current_status": InsuranceStatus.POLICY_ISSUED},
        {"$set": {"created_at": datetime(2020, 1, 1, tzinfo=UTC)}},
    )
    issued_by_policy_date = await client.get(
        f"{BASE}/overview?date_from={today}&date_to={today}&stage=policy_issued",
        headers=owner_headers,
    )
    assert issued_by_policy_date.json()["data"]["summary"]["total_policy_issued"] == 1


async def test_employee_policy_analytics_reuses_case_visibility_and_cannot_query_advisor_work(
    client, mock_db, owner_headers, master_data
):
    employee, headers = await _employee_with_permissions(
        client,
        owner_headers,
        master_data,
        mobile="9811777001",
        email="analytics.employee@example.com",
        actions=["view"],
    )
    employee_doc = await mock_db["employees"].find_one({"_id": ObjectId(employee["id"])})
    product_id = await _insert(
        mock_db["insurance_products"],
        InsuranceProduct(name="Scoped Product", category_id=str(ObjectId())),
    )
    visible_advisor_id = await _insert(
        mock_db["advisors"],
        Advisor(
            advisor_code="AFS-ADV-100001",
            recruitment_lead_id=str(ObjectId()),
            full_name="Visible Advisor",
            mobile="9811777101",
        ),
    )
    hidden_advisor_id = await _insert(
        mock_db["advisors"],
        Advisor(
            advisor_code="AFS-ADV-100002",
            recruitment_lead_id=str(ObjectId()),
            full_name="Hidden Advisor",
            mobile="9811777102",
        ),
    )
    visible = ApplicationWorkflow(
        case_code="AFS-INS-100001",
        case_type=CaseType.INSURANCE,
        application_id=str(ObjectId()),
        customer_id=str(ObjectId()),
        product_id=product_id,
        product_category="insurance",
        assigned_to=visible_advisor_id,
        current_status=InsuranceStatus.FRESH_LEAD,
        insurance_details=InsuranceCaseDetails(),
        created_by=employee_doc["user_id"],
    )
    hidden = visible.model_copy(
        update={
            "case_code": "AFS-INS-100002",
            "application_id": str(ObjectId()),
            "customer_id": str(ObjectId()),
            "created_by": str(ObjectId()),
            "assigned_to": hidden_advisor_id,
        }
    )
    visible_id = await _insert(mock_db["application_workflows"], visible)
    await _insert(mock_db["application_workflows"], hidden)

    overview = await client.get(f"{BASE}/overview", headers=headers)
    assert overview.status_code == 200, overview.text
    assert overview.json()["data"]["summary"]["total_policy_leads"] == 1
    assert overview.json()["data"]["capabilities"]["advisor_business"] is False
    assert overview.json()["data"]["advisors"] == [
        {"id": visible_advisor_id, "label": "Visible Advisor"}
    ]
    hidden_filter = await client.get(
        f"{BASE}/overview?advisor_id={hidden_advisor_id}", headers=headers
    )
    assert hidden_filter.status_code == 200
    assert hidden_filter.json()["data"]["summary"]["total_policy_leads"] == 0
    product_work = await client.get(f"{BASE}/products/{product_id}", headers=headers)
    assert product_work.status_code == 200, product_work.text
    assert [item["id"] for item in product_work.json()["data"]["leads"]] == [visible_id]
    assert (await client.get(f"{BASE}/advisors", headers=headers)).status_code == 403
    assert (await client.get(f"{BASE}/advisors/{ObjectId()}", headers=headers)).status_code == 403


async def test_analytics_requires_existing_insurance_permissions(client, employee_headers):
    assert (await client.get(f"{BASE}/overview", headers=employee_headers)).status_code == 403
