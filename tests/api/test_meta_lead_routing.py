"""Form-specific Meta routing: products, answers, safe failures, and destinations."""

import json

import pytest
from test_lead_capture import (
    _seed_active_meta_config,
    _seed_lead_sources_and_capture_sources,
    _seed_loan_product,
    _sign,
)
from test_workflow import _seed_workflow_definitions

from app.features.customer.constants import FieldType
from app.features.customer.models import ApplicationFormDefinition, FormFieldDefinition
from app.features.lead_capture import meta_client
from app.features.lead_capture.models import MetaLeadRouting
from app.features.system_settings.models import InsuranceCategory, InsuranceProduct, LoanProduct


async def _loan_product(mock_db, name: str, *, status: str = "active") -> str:
    result = await mock_db["loan_products"].insert_one(
        LoanProduct(name=name, status=status).model_dump(by_alias=True, exclude={"id"})
    )
    return str(result.inserted_id)


async def _route(mock_db, form_id: str, *, category: str, product_mode: str, destination: str,
                 product_id: str | None = None, question: str | None = None,
                 mappings: dict[str, str] | None = None, status: str = "active") -> None:
    route = MetaLeadRouting(
        meta_form_id=form_id, form_name=form_id, category=category, product_mode=product_mode,
        default_product_id=product_id, destination_module=destination,
        product_question_key=question, answer_mappings=mappings or {}, status=status,
    )
    await mock_db["meta_lead_routings"].insert_one(route.model_dump(by_alias=True, exclude={"id"}))


async def _post_meta(client, *, form_id: str, leadgen_id: str, secret: str = "routing-secret"):
    body = json.dumps({"entry": [{"changes": [{"value": {"leadgen_id": leadgen_id, "form_id": form_id}}]}]}).encode()
    return await client.post(
        "/api/v1/lead-capture/webhooks/meta", content=body,
        headers={"X-Hub-Signature-256": _sign(body, secret)},
    )


async def test_single_product_forms_route_personal_business_and_home(client, mock_db, owner_headers, monkeypatch):
    personal = await _seed_loan_product(mock_db)
    await _seed_lead_sources_and_capture_sources(mock_db, product_id=personal)
    business = await _loan_product(mock_db, "Business Loan")
    home = await _loan_product(mock_db, "Home Loan")
    await _seed_active_meta_config(mock_db, app_secret="routing-secret")
    for form_id, product_id in (("PERSONAL", personal), ("BUSINESS", business), ("HOME", home)):
        await _route(mock_db, form_id, category="loan", product_mode="default", destination="leads", product_id=product_id)
    rows = {
        "P": ("PERSONAL", "9876501001"), "B": ("BUSINESS", "9876501002"), "H": ("HOME", "9876501003"),
    }

    async def fetch(leadgen_id, *, access_token):
        form_id, mobile = rows[leadgen_id]
        return {"field_data": [{"name": "full_name", "values": [form_id]}, {"name": "phone_number", "values": [mobile]}]}

    monkeypatch.setattr(meta_client, "fetch_lead_fields", fetch)
    for leadgen_id, (form_id, mobile) in rows.items():
        assert (await _post_meta(client, form_id=form_id, leadgen_id=leadgen_id)).status_code == 200
        lead = await mock_db["leads"].find_one({"mobile": mobile})
        failure = await mock_db["capture_failures"].find_one({"raw_payload.leadgen_id": leadgen_id})
        assert lead is not None, failure and failure.get("error_detail")
        expected = {"PERSONAL": personal, "BUSINESS": business, "HOME": home}[form_id]
        assert lead["product_category"] == "loan" and lead["product_id"] == expected


@pytest.mark.parametrize(
    ("answer", "mobile", "expected_key"),
    [("Personal Loan", "9876501011", "personal"), ("Business Loan", "9876501012", "business"), ("Home Loan", "9876501013", "home")],
)
async def test_all_loans_customer_answer_mapping(client, mock_db, owner_headers, monkeypatch, answer, mobile, expected_key):
    personal = await _seed_loan_product(mock_db)
    await _seed_lead_sources_and_capture_sources(mock_db, product_id=personal)
    products = {"personal": personal, "business": await _loan_product(mock_db, "Business Loan"), "home": await _loan_product(mock_db, "Home Loan")}
    await _seed_active_meta_config(mock_db, app_secret="routing-secret")
    await _route(
        mock_db, "ALL_LOANS", category="loan", product_mode="customer_answer", destination="leads",
        question="What type of loan are you interested in?",
        mappings={"Personal Loan": products["personal"], "Business Loan": products["business"], "Home Loan": products["home"]},
    )

    async def fetch(*_args, **_kwargs):
        return {"field_data": [
            {"name": "full_name", "values": ["All Loans Prospect"]},
            {"name": "phone_number", "values": [mobile]},
            {"name": "What type of loan are you interested in ?", "values": [answer]},
        ]}

    monkeypatch.setattr(meta_client, "fetch_lead_fields", fetch)
    assert (await _post_meta(client, form_id="ALL_LOANS", leadgen_id=f"ALL-{expected_key}")).status_code == 200
    lead = await mock_db["leads"].find_one({"mobile": mobile})
    assert lead["product_id"] == products[expected_key]


@pytest.mark.parametrize(
    ("field_data", "reason"),
    [
        ([{"name": "different_question", "values": ["Business Loan"]}], "question_not_found"),
        ([{"name": "loan_type", "values": []}], "answer_not_found"),
        ([{"name": "loan_type", "values": ["Education Loan"]}], "answer_not_mapped"),
    ],
)
async def test_missing_question_and_unknown_answer_are_safe_failures(client, mock_db, owner_headers, monkeypatch, field_data, reason):
    personal = await _seed_loan_product(mock_db)
    await _seed_lead_sources_and_capture_sources(mock_db, product_id=personal)
    await _seed_active_meta_config(mock_db, app_secret="routing-secret")
    await _route(mock_db, "SAFE", category="loan", product_mode="customer_answer", destination="leads", question="loan_type", mappings={"Personal Loan": personal})

    async def fetch(*_args, **_kwargs):
        return {"field_data": [{"name": "full_name", "values": ["Safe"]}, {"name": "phone_number", "values": ["9876501020"]}, *field_data]}

    monkeypatch.setattr(meta_client, "fetch_lead_fields", fetch)
    assert (await _post_meta(client, form_id="SAFE", leadgen_id=f"SAFE-{reason}")).status_code == 200
    assert await mock_db["leads"].count_documents({"mobile": "9876501020"}) == 0
    failure = await mock_db["capture_failures"].find_one({"raw_payload.leadgen_id": f"SAFE-{reason}"})
    assert failure["failure_reason"] == reason
    assert failure["status"] == "needs_routing_configuration"


async def test_inactive_product_is_a_precise_routing_failure(client, mock_db, owner_headers, monkeypatch):
    personal = await _seed_loan_product(mock_db)
    await _seed_lead_sources_and_capture_sources(mock_db, product_id=personal)
    inactive = await _loan_product(mock_db, "Inactive", status="inactive")
    await _seed_active_meta_config(mock_db, app_secret="routing-secret")
    await _route(mock_db, "INACTIVE", category="loan", product_mode="default", destination="leads", product_id=inactive)

    async def fetch(*_args, **_kwargs):
        return {"field_data": [{"name": "full_name", "values": ["Inactive"]}, {"name": "phone_number", "values": ["9876501030"]}]}

    monkeypatch.setattr(meta_client, "fetch_lead_fields", fetch)
    await _post_meta(client, form_id="INACTIVE", leadgen_id="INACTIVE-1")
    failure = await mock_db["capture_failures"].find_one({"raw_payload.leadgen_id": "INACTIVE-1"})
    assert failure["failure_reason"] == "inactive_product"


async def test_insurance_answer_routes_to_policy_leads_not_general_leads(client, mock_db, owner_headers, monkeypatch):
    personal = await _seed_loan_product(mock_db)
    await _seed_lead_sources_and_capture_sources(mock_db, product_id=personal)
    await _seed_workflow_definitions(mock_db)
    category_id = str((await mock_db["insurance_categories"].insert_one(
        InsuranceCategory(name="Health Insurance").model_dump(by_alias=True, exclude={"id"})
    )).inserted_id)
    product_id = str((await mock_db["insurance_products"].insert_one(
        InsuranceProduct(name="Health Insurance", category_id=category_id).model_dump(by_alias=True, exclude={"id"})
    )).inserted_id)
    form = ApplicationFormDefinition(
        product_category="insurance", product_id=product_id, insurance_category_id=category_id,
        fields=[FormFieldDefinition(key="amount", label="Amount", field_type=FieldType.NUMBER, required=False)], status="active",
    )
    await mock_db["application_form_definitions"].insert_one(form.model_dump(by_alias=True, exclude={"id"}))
    await _seed_active_meta_config(mock_db, app_secret="routing-secret")
    await _route(mock_db, "INSURANCE", category="insurance", product_mode="customer_answer", destination="insurance_policy_leads", question="insurance_type", mappings={"Health Insurance": product_id})

    async def fetch(*_args, **_kwargs):
        return {"field_data": [{"name": "full_name", "values": ["Policy Prospect"]}, {"name": "phone_number", "values": ["9876501040"]}, {"name": "insurance_type", "values": ["Health Insurance"]}]}

    monkeypatch.setattr(meta_client, "fetch_lead_fields", fetch)
    assert (await _post_meta(client, form_id="INSURANCE", leadgen_id="INS-1")).status_code == 200
    assert await mock_db["leads"].count_documents({"mobile": "9876501040"}) == 0
    customer_user = await mock_db["users"].find_one({"mobile": "9876501040"})
    customer = await mock_db["customers"].find_one({"user_id": str(customer_user["_id"])})
    application = await mock_db["applications"].find_one({"customer_id": str(customer["_id"])})
    case = await mock_db["application_workflows"].find_one({"application_id": str(application["_id"])})
    assert case["case_type"] == "insurance" and case["current_status"] == "fresh_lead"
    receipt = await mock_db["capture_receipts"].find_one({"external_id": "INS-1"})
    assert receipt["destination_module"] == "insurance_policy_leads" and receipt["lead_id"] is None


async def test_duplicate_form_configuration_is_rejected(client, mock_db, owner_headers):
    product_id = await _seed_loan_product(mock_db)
    await _seed_lead_sources_and_capture_sources(mock_db, product_id=product_id)
    payload = {"form_name": "Duplicate", "category": "loan", "product_mode": "default", "default_product_id": product_id, "destination_module": "leads", "answer_mappings": {}, "active": True}
    first = await client.post("/api/v1/lead-capture/meta-routings/DUPLICATE", json=payload, headers=owner_headers)
    assert first.status_code == 200, first.text
    second = await client.post("/api/v1/lead-capture/meta-routings/DUPLICATE", json=payload, headers=owner_headers)
    assert second.status_code == 409
