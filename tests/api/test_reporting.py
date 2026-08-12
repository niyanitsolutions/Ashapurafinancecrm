"""End-to-end tests for Module 8 (Reporting Framework): permission gating on the Report
Engine, each Business Report's aggregation math against directly-seeded data (mirroring
6C/7's own "insert the frozen collections' documents directly, then call the new
module's read-only endpoints" test convention), CSV export, date-range filtering, Saved
Filters (self-service + ownership), and Scheduled Reports CRUD (framework only — no
execution job exists, so only the CRUD surface is tested).
"""

from datetime import timedelta

import pytest

from app.features.customer.models import Application
from app.features.leads.models import Lead
from app.features.referral_partner_management.models import CommissionEntry, ReferralLead, ReferralPartner
from app.features.reminders.models import Task
from app.features.reporting.constants import ReportCategory, ReportType
from app.features.reporting.models import ReportDefinition, ReportDefinitionColumn
from app.features.system_settings.models import InsuranceProduct, LeadSource, LoanProduct
from app.features.workflow_engine.constants import CaseType, InsuranceStatus, LoanStatus
from app.features.workflow_engine.models import ApplicationWorkflow, InsuranceCaseDetails, LoanCaseDetails
from app.utils.datetime import utc_now


def _col(key: str, label: str) -> ReportDefinitionColumn:
    return ReportDefinitionColumn(key=key, label=label)


# Mirrors scripts/seed.py:seed_report_definitions — tests run against a fresh mongomock
# database, not the seed script, so this data must be inserted directly (same precedent
# as test_workflow.py's own _seed_workflow_definitions).
_REPORT_ROWS = [
    ReportDefinition(
        key="lead_by_source", label="Leads by Source", category=ReportCategory.LEAD, description="", report_type=ReportType.COUNT,
        columns=[_col("source", "Source"), _col("count", "Leads")], collection="leads", group_field="source_id", date_field="created_at",
        name_resolution_collection="lead_sources", name_resolution_field="name",
    ),
    ReportDefinition(
        key="lead_conversion", label="Lead Conversion", category=ReportCategory.LEAD, description="", report_type=ReportType.CUSTOM,
        columns=[_col("source", "Source"), _col("total_leads", "Total Leads"), _col("converted", "Converted"), _col("conversion_rate_pct", "Conversion %")],
    ),
    ReportDefinition(
        key="lead_by_employee", label="Leads by Employee", category=ReportCategory.LEAD, description="", report_type=ReportType.COUNT,
        columns=[_col("employee", "Employee"), _col("count", "Leads")], collection="leads", group_field="assigned_to", date_field="created_at",
        name_resolution_collection="employees", name_resolution_field="display_name",
    ),
    ReportDefinition(
        key="lead_by_product", label="Leads by Product", category=ReportCategory.LEAD, description="", report_type=ReportType.CUSTOM,
        columns=[_col("product_category", "Category"), _col("product", "Product"), _col("count", "Leads")],
    ),
    ReportDefinition(
        key="loan_applications", label="Loan Applications", category=ReportCategory.LOAN, description="", report_type=ReportType.COUNT,
        columns=[_col("status", "Status"), _col("count", "Applications")], collection="application_workflows", group_field="current_status",
        date_field="created_at", extra_match={"case_type": "loan"},
    ),
    ReportDefinition(
        key="loan_approved", label="Loan Approved", category=ReportCategory.LOAN, description="", report_type=ReportType.LIST,
        columns=[_col("case_code", "Case"), _col("status", "Status"), _col("amount", "Offered Amount"), _col("date", "Date")],
        collection="application_workflows", date_field="created_at", amount_field="offered_amount",
        extra_match={"case_type": "loan", "loan_details.offer_decision": "accepted"},
    ),
    ReportDefinition(
        key="loan_rejected", label="Loan Rejected", category=ReportCategory.LOAN, description="", report_type=ReportType.LIST,
        columns=[_col("case_code", "Case"), _col("status", "Status"), _col("date", "Date")], collection="application_workflows", date_field="updated_at",
        extra_match={"case_type": "loan", "current_status": LoanStatus.REJECTED},
    ),
    ReportDefinition(
        key="loan_disbursed", label="Loan Disbursed", category=ReportCategory.LOAN, description="", report_type=ReportType.LIST,
        columns=[_col("case_code", "Case"), _col("status", "Status"), _col("amount", "Disbursed Amount"), _col("date", "Disbursed At")],
        collection="application_workflows", date_field="loan_details.disbursed_at", amount_field="disbursed_amount",
        extra_match={"case_type": "loan", "current_status": LoanStatus.DISBURSED},
    ),
    ReportDefinition(
        key="bank_performance", label="Bank Performance", category=ReportCategory.LOAN, description="", report_type=ReportType.SUM,
        columns=[_col("bank", "Bank / NBFC"), _col("disbursed_count", "Disbursed Count"), _col("disbursed_amount", "Disbursed Amount")],
        collection="application_workflows", group_field="loan_details.bank_nbfc_name", sum_field="loan_details.disbursed_amount",
        date_field="loan_details.disbursed_at", extra_match={"case_type": "loan", "current_status": LoanStatus.DISBURSED},
    ),
    ReportDefinition(
        key="insurance_applications", label="Insurance Applications", category=ReportCategory.INSURANCE, description="", report_type=ReportType.COUNT,
        columns=[_col("status", "Status"), _col("count", "Applications")], collection="application_workflows", group_field="current_status",
        date_field="created_at", extra_match={"case_type": "insurance"},
    ),
    ReportDefinition(
        key="insurance_policies_issued", label="Policies Issued", category=ReportCategory.INSURANCE, description="", report_type=ReportType.LIST,
        columns=[_col("case_code", "Case"), _col("status", "Status"), _col("amount", "Premium Amount"), _col("date", "Policy Issued At")],
        collection="application_workflows", date_field="insurance_details.policy_issued_at", amount_field="premium_amount",
        extra_match={"case_type": "insurance", "current_status": InsuranceStatus.POLICY_ISSUED},
    ),
    ReportDefinition(
        key="insurance_rejections", label="Insurance Rejections", category=ReportCategory.INSURANCE, description="", report_type=ReportType.LIST,
        columns=[_col("case_code", "Case"), _col("status", "Status"), _col("date", "Date")], collection="application_workflows", date_field="updated_at",
        extra_match={"case_type": "insurance", "current_status": InsuranceStatus.REJECTED},
    ),
    ReportDefinition(
        key="employee_task_summary", label="Employee Task Summary", category=ReportCategory.EMPLOYEE, description="", report_type=ReportType.CUSTOM,
        columns=[_col("employee", "Employee"), _col("assigned", "Assigned"), _col("completed", "Completed"), _col("pending", "Pending")],
    ),
    ReportDefinition(
        key="referral_leads", label="Referral Leads", category=ReportCategory.REFERRAL, description="", report_type=ReportType.CUSTOM,
        columns=[_col("partner", "Referral Partner"), _col("lead_code", "Lead"), _col("full_name", "Name"), _col("external_status", "Status"), _col("submitted_at", "Submitted At")],
    ),
    ReportDefinition(
        key="referral_conversions", label="Referral Conversions", category=ReportCategory.REFERRAL, description="", report_type=ReportType.CUSTOM,
        columns=[_col("partner", "Referral Partner"), _col("total_leads", "Total Leads"), _col("approved", "Approved"), _col("conversion_rate_pct", "Conversion %")],
    ),
    ReportDefinition(
        key="referral_commission", label="Referral Commission", category=ReportCategory.REFERRAL, description="", report_type=ReportType.CUSTOM,
        columns=[
            _col("partner", "Referral Partner"), _col("commission_pending", "Pending"), _col("commission_approved", "Approved"),
            _col("commission_paid", "Paid"), _col("commission_balance", "Balance"),
        ],
    ),
    ReportDefinition(
        key="dashboard_analytics", label="Dashboard Analytics", category=ReportCategory.DASHBOARD, description="", report_type=ReportType.CUSTOM,
        columns=[_col("metric", "Metric"), _col("value", "Value")],
    ),
]


@pytest.fixture(autouse=True)
async def _seed_report_definitions(mock_db):
    for row in _REPORT_ROWS:
        await mock_db["report_definitions"].insert_one(row.model_dump(by_alias=True, exclude={"id"}))


async def _grant_permission(client, owner_headers, employee_id, *, module, resource, actions):
    r = await client.post("/api/v1/permissions", json={"module": module, "resource": resource, "actions": actions}, headers=owner_headers)
    if r.status_code == 409:
        existing = await client.get("/api/v1/permissions", headers=owner_headers)
        permission = next(p for p in existing.json()["data"] if p["module"] == module and p["resource"] == resource)
    else:
        assert r.status_code == 200, r.text
        permission = r.json()["data"]
    r = await client.post("/api/v1/roles", json={"name": f"Role for {module}:{resource}:{employee_id}"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    role = r.json()["data"]
    r = await client.put(
        f"/api/v1/roles/{role['id']}/permissions", json={"grants": [{"permission_id": permission["id"], "granted_actions": actions}]}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/roles/{role['id']}/assign", json={"employee_id": employee_id}, headers=owner_headers)
    assert r.status_code == 200, r.text


async def _login(client, mobile, password):
    r = await client.post("/api/v1/auth/login", json={"mobile": mobile, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def _create_employee(client, owner_headers, master_data, mobile, email):
    payload = {
        "mobile": mobile, "initial_password": "InitialPass1", "first_name": "Staff", "last_name": "Member", "email": email,
        "department_id": master_data["department_id"], "designation_id": master_data["designation_id"], "branch_id": master_data["branch_id"],
        "joining_date": "2026-01-15", "employment_type": "full_time",
    }
    r = await client.post("/api/v1/employees", json=payload, headers=owner_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _insert_lead(mock_db, *, full_name, mobile, source_id, product_category, product_id, assigned_to=None, created_at=None):
    lead = Lead(
        lead_code=f"AFS-LEAD-{mobile}", full_name=full_name, mobile=mobile, source_id=source_id, product_category=product_category,
        product_id=product_id, assigned_to=assigned_to, created_at=created_at or utc_now(),
    )
    result = await mock_db["leads"].insert_one(lead.model_dump(by_alias=True, exclude={"id"}))
    return str(result.inserted_id)


async def _insert_application(mock_db, *, lead_id, product_category, product_id):
    application = Application(
        application_code=f"AFS-APP-{lead_id}", user_id="000000000000000000000001", lead_id=lead_id, product_category=product_category,
        product_id=product_id, form_definition_id="000000000000000000000002",
    )
    result = await mock_db["applications"].insert_one(application.model_dump(by_alias=True, exclude={"id"}))
    return str(result.inserted_id)


async def test_reports_permission_gating_and_catalog(client, owner_headers, employee_headers, master_data):
    r = await client.get("/api/v1/reports", headers=owner_headers)
    assert r.status_code == 200, r.text
    keys = {d["key"] for d in r.json()["data"]}
    assert "lead_by_source" in keys
    assert "dashboard_analytics" in keys
    assert len(keys) == 17

    r = await client.get("/api/v1/reports/lead_by_source", headers=employee_headers)
    assert r.status_code == 403, r.text

    employee = await _create_employee(client, owner_headers, master_data, mobile="9800000101", email="reports.viewer@example.com")
    await _grant_permission(client, owner_headers, employee["id"], module="reporting", resource="reports", actions=["view", "export"])
    granted_headers = await _login(client, "9800000101", "InitialPass1")

    r = await client.get("/api/v1/reports/lead_by_source", headers=granted_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["rows"] == []

    r = await client.get("/api/v1/reports/unknown_report_key", headers=owner_headers)
    assert r.status_code == 404, r.text


async def test_lead_reports_by_source_employee_product_and_conversion(client, mock_db, owner_headers, master_data):
    source = LeadSource(name="Website")
    source_id = str((await mock_db["lead_sources"].insert_one(source.model_dump(by_alias=True, exclude={"id"}))).inserted_id)
    product = LoanProduct(name="Personal Loan")
    product_id = str((await mock_db["loan_products"].insert_one(product.model_dump(by_alias=True, exclude={"id"}))).inserted_id)

    employee = await _create_employee(client, owner_headers, master_data, mobile="9800000102", email="lead.owner@example.com")

    lead1_id = await _insert_lead(mock_db, full_name="Lead One", mobile="9800000201", source_id=source_id, product_category="loan", product_id=product_id, assigned_to=employee["id"])
    await _insert_lead(mock_db, full_name="Lead Two", mobile="9800000202", source_id=source_id, product_category="loan", product_id=product_id)
    await _insert_application(mock_db, lead_id=lead1_id, product_category="loan", product_id=product_id)

    r = await client.get("/api/v1/reports/lead_by_source", headers=owner_headers)
    assert r.status_code == 200, r.text
    rows = r.json()["data"]["rows"]
    assert rows == [{"source": "Website", "count": 2}]

    r = await client.get("/api/v1/reports/lead_by_employee", headers=owner_headers)
    rows = {row["employee"]: row["count"] for row in r.json()["data"]["rows"]}
    assert rows["Staff Member"] == 1
    assert rows["Unassigned"] == 1

    r = await client.get("/api/v1/reports/lead_by_product", headers=owner_headers)
    rows = r.json()["data"]["rows"]
    assert rows == [{"product_category": "Loan", "product": "Personal Loan", "count": 2}]

    r = await client.get("/api/v1/reports/lead_conversion", headers=owner_headers)
    rows = r.json()["data"]["rows"]
    assert rows == [{"source": "Website", "total_leads": 2, "converted": 1, "conversion_rate_pct": 50.0}]


async def test_loan_and_insurance_reports(client, mock_db, owner_headers):
    loan_case = ApplicationWorkflow(
        case_code="AFS-LOAN-000001", case_type=CaseType.LOAN, application_id="000000000000000000000001", customer_id="000000000000000000000002",
        product_id="000000000000000000000003", product_category="loan", current_status=LoanStatus.DISBURSED,
        loan_details=LoanCaseDetails(offer_decision="accepted", offered_amount=90000.0, disbursed_amount=100000.0, disbursed_at=utc_now(), bank_nbfc_name="ABC Bank"),
    )
    await mock_db["application_workflows"].insert_one(loan_case.model_dump(by_alias=True, exclude={"id"}))

    rejected_loan = ApplicationWorkflow(
        case_code="AFS-LOAN-000002", case_type=CaseType.LOAN, application_id="000000000000000000000004", customer_id="000000000000000000000002",
        product_id="000000000000000000000003", product_category="loan", current_status=LoanStatus.REJECTED, loan_details=LoanCaseDetails(),
    )
    await mock_db["application_workflows"].insert_one(rejected_loan.model_dump(by_alias=True, exclude={"id"}))

    insurance_case = ApplicationWorkflow(
        case_code="AFS-INS-000001", case_type=CaseType.INSURANCE, application_id="000000000000000000000005", customer_id="000000000000000000000002",
        product_id="000000000000000000000006", product_category="insurance", current_status=InsuranceStatus.POLICY_ISSUED,
        insurance_details=InsuranceCaseDetails(premium_amount=5000.0, policy_issued_at=utc_now(), policy_number="POL-1"),
    )
    await mock_db["application_workflows"].insert_one(insurance_case.model_dump(by_alias=True, exclude={"id"}))

    rejected_insurance = ApplicationWorkflow(
        case_code="AFS-INS-000002", case_type=CaseType.INSURANCE, application_id="000000000000000000000007", customer_id="000000000000000000000002",
        product_id="000000000000000000000006", product_category="insurance", current_status=InsuranceStatus.REJECTED, insurance_details=InsuranceCaseDetails(),
    )
    await mock_db["application_workflows"].insert_one(rejected_insurance.model_dump(by_alias=True, exclude={"id"}))

    r = await client.get("/api/v1/reports/loan_applications", headers=owner_headers)
    rows = {row["status"]: row["count"] for row in r.json()["data"]["rows"]}
    assert rows["Disbursed"] == 1
    assert rows["Rejected"] == 1

    r = await client.get("/api/v1/reports/loan_approved", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]["rows"]) == 1
    assert r.json()["data"]["rows"][0]["case_code"] == "AFS-LOAN-000001"

    r = await client.get("/api/v1/reports/loan_rejected", headers=owner_headers)
    assert r.json()["data"]["summary"]["total"] == 1
    assert r.json()["data"]["rows"][0]["case_code"] == "AFS-LOAN-000002"

    r = await client.get("/api/v1/reports/loan_disbursed", headers=owner_headers)
    body = r.json()["data"]
    assert body["summary"]["total"] == 1
    assert body["summary"]["total_amount"] == 100000.0
    assert body["rows"][0]["amount"] == 100000.0

    r = await client.get("/api/v1/reports/bank_performance", headers=owner_headers)
    rows = r.json()["data"]["rows"]
    assert rows == [{"bank": "ABC Bank", "disbursed_count": 1, "disbursed_amount": 100000.0}]

    r = await client.get("/api/v1/reports/insurance_applications", headers=owner_headers)
    rows = {row["status"]: row["count"] for row in r.json()["data"]["rows"]}
    assert rows["Policy Issued"] == 1
    assert rows["Rejected"] == 1

    r = await client.get("/api/v1/reports/insurance_policies_issued", headers=owner_headers)
    body = r.json()["data"]
    assert body["summary"]["total"] == 1
    assert body["summary"]["total_amount"] == 5000.0

    r = await client.get("/api/v1/reports/insurance_rejections", headers=owner_headers)
    assert r.json()["data"]["summary"]["total"] == 1
    assert r.json()["data"]["rows"][0]["case_code"] == "AFS-INS-000002"


async def test_employee_task_summary_report(client, mock_db, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data, mobile="9800000103", email="task.owner@example.com")
    now = utc_now()
    for i, status in enumerate(["completed", "pending", "pending"]):
        task = Task(title=f"Task {i}", assigned_to=employee["id"], assigned_by="000000000000000000000001", due_at=now + timedelta(hours=1), status=status)
        await mock_db["tasks"].insert_one(task.model_dump(by_alias=True, exclude={"id"}))

    r = await client.get("/api/v1/reports/employee_task_summary", headers=owner_headers)
    assert r.status_code == 200, r.text
    row = r.json()["data"]["rows"][0]
    assert row["employee"] == "Staff Member"
    assert row["assigned"] == 3
    assert row["completed"] == 1
    assert row["pending"] == 2


async def test_referral_reports_leads_conversions_and_commission(client, mock_db, owner_headers):
    partner = ReferralPartner(partner_code="AFS-REF-000001", user_id="000000000000000000000009", full_name="Referral Co", mobile="9700000001", approval_status="active")
    partner_id = str((await mock_db["referral_partners"].insert_one(partner.model_dump(by_alias=True, exclude={"id"}))).inserted_id)

    source = LeadSource(name="Referral")
    source_id = str((await mock_db["lead_sources"].insert_one(source.model_dump(by_alias=True, exclude={"id"}))).inserted_id)
    product = LoanProduct(name="Personal Loan")
    product_id = str((await mock_db["loan_products"].insert_one(product.model_dump(by_alias=True, exclude={"id"}))).inserted_id)

    approved_lead_id = await _insert_lead(mock_db, full_name="Approved Lead", mobile="9800000301", source_id=source_id, product_category="loan", product_id=product_id)
    pending_lead_id = await _insert_lead(mock_db, full_name="Pending Lead", mobile="9800000302", source_id=source_id, product_category="loan", product_id=product_id)
    for lead_id in (approved_lead_id, pending_lead_id):
        mapping = ReferralLead(partner_id=partner_id, lead_id=lead_id)
        await mock_db["referral_leads"].insert_one(mapping.model_dump(by_alias=True, exclude={"id"}))

    application_id = await _insert_application(mock_db, lead_id=approved_lead_id, product_category="loan", product_id=product_id)
    disbursed_case = ApplicationWorkflow(
        case_code="AFS-LOAN-REF001", case_type=CaseType.LOAN, application_id=application_id, customer_id="000000000000000000000002",
        product_id=product_id, product_category="loan", current_status=LoanStatus.DISBURSED, loan_details=LoanCaseDetails(disbursed_amount=100000.0, disbursed_at=utc_now()),
    )
    case_id = str((await mock_db["application_workflows"].insert_one(disbursed_case.model_dump(by_alias=True, exclude={"id"}))).inserted_id)

    entry = CommissionEntry(
        partner_id=partner_id, lead_id=approved_lead_id, case_type="loan", case_id=case_id, rule_id="000000000000000000000099",
        calculation_type="percentage", rate_or_amount=2.0, base_amount=100000.0, commission_amount=2000.0, status="paid",
    )
    await mock_db["commission_entries"].insert_one(entry.model_dump(by_alias=True, exclude={"id"}))

    r = await client.get("/api/v1/reports/referral_leads", headers=owner_headers)
    assert r.status_code == 200, r.text
    rows = {row["full_name"]: row["external_status"] for row in r.json()["data"]["rows"]}
    assert rows["Approved Lead"] == "Approved"
    assert rows["Pending Lead"] == "Submitted"

    r = await client.get("/api/v1/reports/referral_conversions", headers=owner_headers)
    row = r.json()["data"]["rows"][0]
    assert row["partner"] == "Referral Co"
    assert row["total_leads"] == 2
    assert row["approved"] == 1
    assert row["conversion_rate_pct"] == 50.0

    r = await client.get("/api/v1/reports/referral_commission", headers=owner_headers)
    row = r.json()["data"]["rows"][0]
    assert row["partner"] == "Referral Co"
    assert row["commission_paid"] == 2000.0
    assert row["commission_pending"] == 0.0
    assert row["commission_balance"] == 0.0


async def test_dashboard_analytics_report(client, mock_db, owner_headers):
    await _insert_lead(mock_db, full_name="Some Lead", mobile="9800000401", source_id="000000000000000000000001", product_category="loan", product_id="000000000000000000000002")
    r = await client.get("/api/v1/reports/dashboard_analytics", headers=owner_headers)
    assert r.status_code == 200, r.text
    summary = r.json()["data"]["summary"]
    assert summary["total_leads"] == 1
    assert "loans_disbursed" in summary
    assert "active_referral_partners" in summary


async def test_report_date_range_filters(client, mock_db, owner_headers):
    old = utc_now() - timedelta(days=365)
    await _insert_lead(mock_db, full_name="Old Lead", mobile="9800000501", source_id="000000000000000000000001", product_category="loan", product_id="000000000000000000000002", created_at=old)
    await _insert_lead(mock_db, full_name="New Lead", mobile="9800000502", source_id="000000000000000000000001", product_category="loan", product_id="000000000000000000000002")

    r = await client.get("/api/v1/reports/dashboard_analytics", headers=owner_headers)
    assert r.json()["data"]["summary"]["total_leads"] == 2

    today = utc_now().date().isoformat()
    r = await client.get(f"/api/v1/reports/dashboard_analytics?date_from={today}&date_to={today}", headers=owner_headers)
    assert r.json()["data"]["summary"]["total_leads"] == 1


async def test_csv_export(client, mock_db, owner_headers):
    await _insert_lead(mock_db, full_name="Export Lead", mobile="9800000601", source_id="000000000000000000000001", product_category="loan", product_id="000000000000000000000002")
    r = await client.get("/api/v1/reports/dashboard_analytics/export", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert "Metric,Value" in r.text


async def test_saved_filters_self_service_and_ownership(client, owner_headers, employee_headers):
    r = await client.post(
        "/api/v1/saved-filters", json={"report_key": "lead_by_source", "label": "This Month", "filters": {"date_from": "2026-07-01"}}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    saved = r.json()["data"]

    r = await client.get("/api/v1/saved-filters", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert any(f["id"] == saved["id"] for f in r.json()["data"])

    r = await client.get("/api/v1/saved-filters", headers=employee_headers)
    assert r.json()["data"] == []  # each user sees only their own presets

    r = await client.delete(f"/api/v1/saved-filters/{saved['id']}", headers=employee_headers)
    assert r.status_code == 404, r.text  # not the caller's own preset

    r = await client.delete(f"/api/v1/saved-filters/{saved['id']}", headers=owner_headers)
    assert r.status_code == 200, r.text


async def test_scheduled_reports_crud_is_permission_gated(client, owner_headers, employee_headers):
    r = await client.post(
        "/api/v1/scheduled-reports", json={"report_key": "dashboard_analytics", "label": "Weekly Summary", "frequency": "weekly", "recipient_user_ids": []},
        headers=employee_headers,
    )
    assert r.status_code == 403, r.text

    r = await client.post(
        "/api/v1/scheduled-reports", json={"report_key": "dashboard_analytics", "label": "Weekly Summary", "frequency": "weekly", "recipient_user_ids": []},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    scheduled = r.json()["data"]
    assert scheduled["is_active"] is True
    assert scheduled["last_run_at"] is None  # framework only — nothing ever runs this

    r = await client.patch(f"/api/v1/scheduled-reports/{scheduled['id']}", json={"is_active": False}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["is_active"] is False

    r = await client.delete(f"/api/v1/scheduled-reports/{scheduled['id']}", headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/scheduled-reports/{scheduled['id']}", headers=owner_headers)
    assert r.status_code == 404, r.text
