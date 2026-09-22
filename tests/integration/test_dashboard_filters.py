from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

from app.constants.roles import EMPLOYEE, OWNER
from app.core.exceptions import ValidationError
from app.features.auth.models import User
from app.features.dashboard import filters as filter_module
from app.features.dashboard.filters import resolve_dashboard_filters
from app.features.dashboard.widget_providers import compute_widget_data
from app.utils.datetime import to_ist


def resolve(**overrides):
    values = {
        "date_range": "custom", "start_date": date(2026, 9, 1), "end_date": date(2026, 9, 1),
        "product_category": None, "source_id": None,
    }
    return resolve_dashboard_filters(**(values | overrides))


@pytest.mark.parametrize("overrides", [
    {"date_range": "invalid"}, {"start_date": None}, {"end_date": None},
    {"start_date": date(2026, 9, 2)}, {"product_category": "invalid"}, {"end_date": date.max},
])
def test_rejects_invalid_filters(overrides):
    with pytest.raises(ValidationError):
        resolve(**overrides)


def test_custom_range_includes_full_ist_end_day():
    filters = resolve()
    assert filters.start == datetime(2026, 8, 31, 18, 30, tzinfo=UTC)
    assert filters.end == datetime(2026, 9, 1, 18, 30, tzinfo=UTC)


@pytest.mark.parametrize(("period", "start", "end"), [
    ("this_week", date(2026, 3, 30), date(2026, 4, 1)),
    ("last_week", date(2026, 3, 23), date(2026, 3, 30)),
    ("this_month", date(2026, 3, 1), date(2026, 4, 1)),
    ("last_month", date(2026, 2, 1), date(2026, 3, 1)),
    ("last_3_months", date(2025, 12, 31), date(2026, 4, 1)),
    ("last_6_months", date(2025, 9, 30), date(2026, 4, 1)),
    ("last_1_year", date(2025, 3, 31), date(2026, 4, 1)),
])
def test_presets_use_business_calendar(monkeypatch, period, start, end):
    monkeypatch.setattr(filter_module, "now_ist", lambda: to_ist(datetime(2026, 3, 31, 10, tzinfo=UTC)))
    filters = resolve(date_range=period)
    assert to_ist(filters.start).date() == start
    assert to_ist(filters.end).date() == end


async def test_filtered_leads_respect_boundaries_products_sources_and_assignment():
    db = AsyncMongoMockClient(tz_aware=True)["dashboard_filters"]
    employee = User(id=str(ObjectId()), mobile="9000000001", role=EMPLOYEE)
    employee_id = str((await db.employees.insert_one({"user_id": employee.id, "is_deleted": False})).inserted_id)
    source_id, other_source = ObjectId(), ObjectId()
    await db.lead_sources.insert_many([{"_id": source_id, "name": "Website"}, {"_id": other_source, "name": "Referral"}])
    filters = resolve(product_category="loan", source_id=str(source_id))
    lead = {"is_deleted": False, "assigned_to": employee_id, "source_id": str(source_id), "product_category": "loan", "created_at": filters.start}
    result = await db.leads.insert_many([
        lead.copy(), lead | {"created_at": filters.end - timedelta(milliseconds=1)},
        lead | {"created_at": filters.end}, lead | {"created_at": filters.start - timedelta(milliseconds=1)},
        lead | {"assigned_to": "other"}, lead | {"product_category": "insurance"},
        lead | {"source_id": str(other_source)}, lead | {"is_deleted": True},
    ])
    await db.applications.insert_many([
        {"is_deleted": False, "status": "submitted", "lead_id": str(result.inserted_ids[0])},
        {"is_deleted": False, "status": "submitted", "lead_id": str(result.inserted_ids[0])},
    ])
    for key in ("total_leads", "assigned_leads"):
        assert (await compute_widget_data(db, employee, key, filters))["value"] == 2
    chart = await compute_widget_data(db, employee, "lead_source_chart", filters)
    assert chart["trend"] == [{"label": "2026-09-01", "total": 2, "assigned": 2, "converted": 1}]
    assert chart["items"] == [{"id": str(source_id), "label": "Website", "value": 2}]
    assert {item["id"] for item in chart["source_options"]} == {str(source_id), str(other_source)}
    empty_chart = await compute_widget_data(db, employee, "lead_source_chart", replace(filters, start=filters.end),)
    assert empty_chart["items"] == []
    assert empty_chart["source_options"] == chart["source_options"]
    orphan = User(id=str(ObjectId()), mobile="9000000002", role=EMPLOYEE)
    assert (await compute_widget_data(db, orphan, "total_leads", filters))["value"] == 0


async def test_case_widgets_share_source_scope_and_keep_employee_assignment():
    db = AsyncMongoMockClient(tz_aware=True)["dashboard_cases"]
    owner = User(id=str(ObjectId()), mobile="9000000003", role=OWNER)
    employee = User(id=str(ObjectId()), mobile="9000000004", role=EMPLOYEE)
    employee_id = str((await db.employees.insert_one({"user_id": employee.id, "is_deleted": False})).inserted_id)
    source_id = str(ObjectId())
    lead = await db.leads.insert_one({"is_deleted": False, "source_id": source_id})
    app = await db.applications.insert_one({"is_deleted": False, "lead_id": str(lead.inserted_id)})
    filters = resolve(source_id=source_id)
    case = {
        "is_deleted": False, "case_type": "loan", "current_status": "disbursed",
        "application_id": str(app.inserted_id), "assigned_to": employee_id,
        "updated_at": filters.start,
        "loan_details": {"disbursed_at": filters.start, "disbursed_amount": 100, "offered_amount": 500},
    }
    await db.application_workflows.insert_many([
        case.copy(), case | {"assigned_to": "other"}, case | {"application_id": "other"},
        case | {"is_deleted": True},
        case | {"loan_details": {"disbursed_at": filters.end, "disbursed_amount": 200}},
        case | {"loan_details": {"disbursed_at": filters.start, "disbursed_amount": 0, "offered_amount": 900}},
        case | {"case_type": "insurance", "current_status": "policy_issued", "insurance_details": {"policy_issued_at": filters.start}},
        case | {"case_type": "insurance", "application_id": "other", "current_status": "policy_issued", "insurance_details": {"policy_issued_at": filters.start}},
        case | {"current_status": "new_customer"},
    ])
    await db.workflow_definitions.insert_many([
        {"case_type": "loan", "is_deleted": False, "status": "disbursed", "label": "Disbursed", "sequence": 10},
        {"case_type": "loan", "is_deleted": False, "status": "new_customer", "label": "New Customer", "sequence": 1},
    ])
    assert (await compute_widget_data(db, employee, "monthly_revenue", filters))["value"] == 100
    assert (await compute_widget_data(db, owner, "monthly_revenue", filters))["value"] == 200
    assert (await compute_widget_data(db, employee, "revenue_trend_chart", filters))["items"] == [{"label": "2026-09-01", "value": 100}]
    assert (await compute_widget_data(db, employee, "policies_issued", filters))["value"] == 1
    pipeline = await compute_widget_data(db, employee, "loan_pipeline_chart", filters)
    assert pipeline["items"] == [
        {"status": "new_customer", "label": "New Customer", "value": 1},
        {"status": "disbursed", "label": "Disbursed", "value": 3},
    ]
    insurance = replace(filters, product_category="insurance")
    assert (await compute_widget_data(db, employee, "monthly_revenue", insurance))["value"] == 0
    assert (await compute_widget_data(db, employee, "loan_pipeline_chart", insurance))["items"] == []
    assert (await compute_widget_data(db, employee, "revenue_trend_chart", insurance))["items"] == []


async def test_customer_count_deduplicates_and_filters_submitted_applications():
    db = AsyncMongoMockClient(tz_aware=True)["dashboard_customers"]
    owner = User(id=str(ObjectId()), mobile="9000000005", role=OWNER)
    source_id = str(ObjectId())
    lead = await db.leads.insert_one({"is_deleted": False, "source_id": source_id})
    filters = resolve(source_id=source_id, product_category="loan")
    app = {"is_deleted": False, "lead_id": str(lead.inserted_id), "customer_id": "customer", "status": "submitted", "submitted_at": filters.start, "product_category": "loan"}
    await db.applications.insert_many([
        app.copy(), app.copy(), app | {"customer_id": "other", "lead_id": "other"},
        app | {"customer_id": "draft", "status": "draft"},
        app | {"customer_id": "late", "submitted_at": filters.end},
        app | {"customer_id": "insurance", "product_category": "insurance"},
    ])
    assert (await compute_widget_data(db, owner, "customers_summary", filters))["value"] == 1
