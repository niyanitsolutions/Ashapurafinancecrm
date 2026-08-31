"""Top Up Loan (production add-on to the existing Disbursed stage) — a disbursed loan
case is scheduled for a future "Top Up eligibility" date (3/6/12 calendar months from
its OWN stored `disbursed_at`, "No", or a validated custom date); once that date is
reached the case automatically shows up in the Top Up Loan tab (a derived filter over
`disbursed` cases — never a new `LoanStatus`, never a background job flipping status).
From there, staff can either reschedule ("Rejected", reusing the exact same scheduling
endpoint/popup concept) or "Move to Document Collection", which creates a brand-new,
ordinary Lead-less Application for the same customer — the existing, completely
unmodified Leads -> Document Collection -> Loan Management pipeline picks it up from
there, with zero new Document Collection logic.

Reuses `test_case_status_control.py`'s own fixtures (`_seed_workflow_definitions`,
`_seed_product_and_form`, `_create_employee`, `_login`, `_grant_case_permission`,
`_loan_case`) rather than re-implementing them — `_loan_case` already drives a case to
`new_customer` and assigns+logs in an employee with `view/edit/approve/assign`, exactly
what every Top Up action needs (`edit` for schedule/move, `approve` for disburse).
"""

from datetime import UTC, datetime

from app.utils.datetime import add_calendar_months, ensure_utc, ist_date_to_utc_midnight, to_ist
from test_case_status_control import (
    _create_employee,
    _grant_case_permission,
    _loan_case,
    _login,
    _seed_product_and_form,
    _seed_workflow_definitions,
)


async def _drive_to_disbursed(client, case_id: str, employee_headers: dict, *, disbursed_amount: float = 90000, reference: str = "UTR-TOPUP") -> None:
    """The exact stage-by-stage sequence `test_workflow.py::
    test_loan_pipeline_happy_path_to_disbursed` already established, extracted here for
    reuse — `_loan_case` stops at `new_customer`; this carries it the rest of the way to
    `disbursed`, using each stage's own dedicated action (no shortcuts/direct DB writes
    for the pipeline itself — only `disbursed_at` backdating, done separately, is a
    legitimate test-only exception, mirroring `_loan_case`'s own document-verification
    backdoor)."""
    r = await client.post(f"/api/v1/loan-cases/{case_id}/new-customer-details", json={}, headers=employee_headers)
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/api/v1/loan-cases/{case_id}/bank-offers",
        json={"bank_name": "HDFC Bank", "decision": "approved", "approved_amount": disbursed_amount, "emi_per_month": 4200},
        headers=employee_headers,
    )
    assert r.status_code == 200, r.text
    offer_id = r.json()["data"]["id"]
    r = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers/{offer_id}/select", headers=employee_headers)
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/loan-cases/{case_id}/offer-acceptance/confirm", headers=employee_headers)
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/loan-cases/{case_id}/documents/verify", headers=employee_headers)
    assert r.status_code == 200, r.text  # no Additional Documents ever requested -> vacuously complete
    r = await client.post(
        f"/api/v1/loan-cases/{case_id}/rv-ov-ref",
        json={
            "rv_ov_ref_type": "Residence Verification", "rv_ov_ref_status": "completed", "rv_ov_ref_date": "2026-08-20T00:00:00Z",
            "rv_ov_ref_verified_by": "Field Agent", "rv_ov_ref_result": "positive", "rv_ov_ref_remarks": "Verification completed",
        },
        headers=employee_headers,
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/api/v1/loan-cases/{case_id}/esign-nach-kyc",
        json={"esign_completed": True, "nach_completed": True, "kyc_completed": True}, headers=employee_headers,
    )
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/loan-cases/{case_id}/final-evaluation", json={"remarks": "All good", "decision": "approved"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/api/v1/loan-cases/{case_id}/disburse", json={"disbursed_amount": disbursed_amount, "disbursed_reference": reference}, headers=employee_headers
    )
    assert r.status_code == 200, r.text


async def _disbursed_case(client, mock_db, owner_headers, master_data, *, mobile_suffix: str) -> tuple[str, dict, dict, str]:
    case_id, employee_headers, customer_headers, application_id = await _loan_case(
        client, mock_db, owner_headers, master_data, mobile_suffix=mobile_suffix
    )
    await _drive_to_disbursed(client, case_id, employee_headers, reference=f"UTR-{mobile_suffix}")
    return case_id, employee_headers, customer_headers, application_id


async def _backdate_disbursed_at(mock_db, application_id: str, disbursed_at: datetime) -> None:
    """Legitimate, minimal test-only exception (mirrors `_loan_case`'s own document-
    verification backdoor): the real pipeline always disburses "now", but the whole
    point of Top Up eligibility is a FUTURE-dated automatic trigger — backdating lets a
    single test exercise "eligibility already reached" without waiting real months."""
    result = await mock_db["application_workflows"].update_one(
        {"application_id": application_id}, {"$set": {"loan_details.disbursed_at": disbursed_at}}
    )
    assert result.matched_count == 1


# ---------------------------------------------------------------------- 1-3: calendar-month scheduling


async def test_schedule_top_up_three_months_uses_calendar_months_from_disbursed_at(client, mock_db, owner_headers, master_data):
    await _seed_workflow_definitions(mock_db)
    case_id, employee_headers, _c, application_id = await _disbursed_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000201")
    disbursed_at = datetime(2026, 8, 25, 4, 0, tzinfo=UTC)
    await _backdate_disbursed_at(mock_db, application_id, disbursed_at)

    r = await client.post(f"/api/v1/loan-cases/{case_id}/top-up/schedule", json={"period": "3_months"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    details = r.json()["data"]["loan_details"]
    assert details["top_up_period"] == "3_months"
    expected = add_calendar_months(disbursed_at, 3)
    assert to_ist(datetime.fromisoformat(details["top_up_eligibility_date"])).date() == to_ist(expected).date()
    assert to_ist(expected).strftime("%d %b %Y") == "25 Nov 2026"  # the spec's own worked example


async def test_schedule_top_up_six_months(client, mock_db, owner_headers, master_data):
    await _seed_workflow_definitions(mock_db)
    case_id, employee_headers, _c, application_id = await _disbursed_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000202")
    disbursed_at = datetime(2026, 8, 25, 4, 0, tzinfo=UTC)
    await _backdate_disbursed_at(mock_db, application_id, disbursed_at)

    r = await client.post(f"/api/v1/loan-cases/{case_id}/top-up/schedule", json={"period": "6_months"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    eligibility = to_ist(datetime.fromisoformat(r.json()["data"]["loan_details"]["top_up_eligibility_date"]))
    assert eligibility.strftime("%d %b %Y") == "25 Feb 2027"


async def test_schedule_top_up_twelve_months(client, mock_db, owner_headers, master_data):
    await _seed_workflow_definitions(mock_db)
    case_id, employee_headers, _c, application_id = await _disbursed_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000203")
    disbursed_at = datetime(2026, 8, 25, 4, 0, tzinfo=UTC)
    await _backdate_disbursed_at(mock_db, application_id, disbursed_at)

    r = await client.post(f"/api/v1/loan-cases/{case_id}/top-up/schedule", json={"period": "12_months"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    eligibility = to_ist(datetime.fromisoformat(r.json()["data"]["loan_details"]["top_up_eligibility_date"]))
    assert eligibility.strftime("%d %b %Y") == "25 Aug 2027"


# ---------------------------------------------------------------------- 4-6: No / Custom


async def test_schedule_top_up_no_schedules_nothing(client, mock_db, owner_headers, master_data):
    await _seed_workflow_definitions(mock_db)
    case_id, employee_headers, _c, _a = await _disbursed_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000204")

    r = await client.post(f"/api/v1/loan-cases/{case_id}/top-up/schedule", json={"period": "no", "remarks": "Not interested"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    details = r.json()["data"]["loan_details"]
    assert details["top_up_period"] == "no"
    assert details["top_up_eligibility_date"] is None
    assert r.json()["data"]["current_status"] == "disbursed"  # unchanged — no auto-move


async def test_schedule_top_up_custom_valid_date_accepted(client, mock_db, owner_headers, master_data):
    await _seed_workflow_definitions(mock_db)
    case_id, employee_headers, _c, application_id = await _disbursed_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000205")
    await _backdate_disbursed_at(mock_db, application_id, datetime(2026, 8, 25, 4, 0, tzinfo=UTC))

    r = await client.post(
        f"/api/v1/loan-cases/{case_id}/top-up/schedule", json={"period": "custom", "custom_date": "2026-12-15"}, headers=employee_headers
    )
    assert r.status_code == 200, r.text
    eligibility = to_ist(datetime.fromisoformat(r.json()["data"]["loan_details"]["top_up_eligibility_date"]))
    assert eligibility.date() == ist_date_to_utc_midnight(datetime(2026, 12, 15).date()).astimezone(eligibility.tzinfo).date()


async def test_schedule_top_up_custom_date_before_disbursement_rejected(client, mock_db, owner_headers, master_data):
    await _seed_workflow_definitions(mock_db)
    case_id, employee_headers, _c, application_id = await _disbursed_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000206")
    await _backdate_disbursed_at(mock_db, application_id, datetime(2026, 8, 25, 4, 0, tzinfo=UTC))

    r = await client.post(
        f"/api/v1/loan-cases/{case_id}/top-up/schedule", json={"period": "custom", "custom_date": "2026-08-20"}, headers=employee_headers
    )
    assert r.status_code >= 400, r.text
    assert "earlier than the disbursed date" in r.json()["error"]["message"]


# ---------------------------------------------------------------------- 7-8: automatic eligibility


async def test_top_up_loan_list_shows_case_once_eligibility_date_reached(client, mock_db, owner_headers, master_data):
    await _seed_workflow_definitions(mock_db)
    case_id, employee_headers, _c, application_id = await _disbursed_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000207")
    # Backdate far enough that "3 months" has already elapsed relative to "now".
    await _backdate_disbursed_at(mock_db, application_id, datetime(2020, 1, 25, 4, 0, tzinfo=UTC))
    r = await client.post(f"/api/v1/loan-cases/{case_id}/top-up/schedule", json={"period": "3_months"}, headers=employee_headers)
    assert r.status_code == 200, r.text

    r = await client.get("/api/v1/loan-cases?top_up_eligible=true", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert case_id in {c["id"] for c in r.json()["data"]}

    r = await client.get("/api/v1/loan-cases/counts", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["top_up_eligible"] >= 1
    # Still plainly `disbursed` underneath — never a new status.
    r = await client.get(f"/api/v1/loan-cases/{case_id}", headers=employee_headers)
    assert r.json()["data"]["current_status"] == "disbursed"


async def test_top_up_loan_list_excludes_case_not_yet_eligible(client, mock_db, owner_headers, master_data):
    await _seed_workflow_definitions(mock_db)
    case_id, employee_headers, _c, application_id = await _disbursed_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000208")
    await _backdate_disbursed_at(mock_db, application_id, ensure_utc(datetime.now(UTC)))
    r = await client.post(f"/api/v1/loan-cases/{case_id}/top-up/schedule", json={"period": "12_months"}, headers=employee_headers)
    assert r.status_code == 200, r.text

    r = await client.get("/api/v1/loan-cases?top_up_eligible=true", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert case_id not in {c["id"] for c in r.json()["data"]}


# ---------------------------------------------------------------------- 9: Move to Document Collection


async def test_move_top_up_to_document_collection_creates_new_application_and_preserves_disbursement(client, mock_db, owner_headers, master_data):
    await _seed_workflow_definitions(mock_db)
    case_id, employee_headers, _c, application_id = await _disbursed_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000209")
    await _backdate_disbursed_at(mock_db, application_id, datetime(2020, 1, 25, 4, 0, tzinfo=UTC))
    await client.post(f"/api/v1/loan-cases/{case_id}/top-up/schedule", json={"period": "3_months"}, headers=employee_headers)

    before = await mock_db["application_workflows"].find_one({"application_id": application_id})

    r = await client.post(f"/api/v1/loan-cases/{case_id}/top-up/move-to-document-collection", json={}, headers=employee_headers)
    assert r.status_code == 200, r.text
    after = r.json()["data"]
    assert after["current_status"] == "disbursed"  # original case's own status never changes
    assert after["loan_details"]["disbursed_amount"] == before["loan_details"]["disbursed_amount"]
    assert after["loan_details"]["disbursed_reference"] == before["loan_details"]["disbursed_reference"]
    assert after["loan_details"]["top_up_eligibility_date"] is None  # this Top Up slot consumed

    # No longer listed as Top Up eligible (consumed).
    r = await client.get("/api/v1/loan-cases?top_up_eligible=true", headers=employee_headers)
    assert case_id not in {c["id"] for c in r.json()["data"]}

    # A brand-new Lead-less Application now exists for the same customer, immediately
    # visible in Document Collection — the EXISTING, unmodified pipeline, not a new one.
    r = await client.get("/api/v1/leads?stage=document_collection", headers=owner_headers)
    assert r.status_code == 200, r.text
    new_rows = [row for row in r.json()["data"] if row["is_lead_less"] and row["application_id"] != application_id]
    assert len(new_rows) == 1


# ---------------------------------------------------------------------- 10: Rejected (reschedule)


async def test_reject_top_up_reschedules_via_same_endpoint(client, mock_db, owner_headers, master_data):
    await _seed_workflow_definitions(mock_db)
    case_id, employee_headers, _c, application_id = await _disbursed_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000210")
    disbursed_at = datetime(2020, 1, 25, 4, 0, tzinfo=UTC)
    await _backdate_disbursed_at(mock_db, application_id, disbursed_at)
    r = await client.post(f"/api/v1/loan-cases/{case_id}/top-up/schedule", json={"period": "3_months"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    first_eligibility = r.json()["data"]["loan_details"]["top_up_eligibility_date"]

    r = await client.get("/api/v1/loan-cases?top_up_eligible=true", headers=employee_headers)
    assert case_id in {c["id"] for c in r.json()["data"]}  # confirmed eligible before "rejecting"

    # "Rejected" on the Top Up Loan row -> the SAME scheduling endpoint, reschedules.
    r = await client.post(
        f"/api/v1/loan-cases/{case_id}/top-up/schedule", json={"period": "3_months", "remarks": "Customer not ready yet"}, headers=employee_headers
    )
    assert r.status_code == 200, r.text
    second_eligibility = r.json()["data"]["loan_details"]["top_up_eligibility_date"]
    assert second_eligibility == first_eligibility  # same disbursed_at, same period -> same anchor (repeatable, not drifting off "now")

    # Still not moved to Document Collection — only rescheduled.
    r = await client.get(f"/api/v1/loan-cases/{case_id}", headers=employee_headers)
    assert r.json()["data"]["current_status"] == "disbursed"


# ---------------------------------------------------------------------- 11: original disbursement preserved


async def test_scheduling_and_rescheduling_top_up_never_touches_original_disbursement_fields(client, mock_db, owner_headers, master_data):
    await _seed_workflow_definitions(mock_db)
    case_id, employee_headers, _c, application_id = await _disbursed_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000211")
    disbursed_at = datetime(2026, 8, 25, 4, 0, tzinfo=UTC)
    await _backdate_disbursed_at(mock_db, application_id, disbursed_at)

    before = await client.get(f"/api/v1/loan-cases/{case_id}", headers=employee_headers)
    before_details = before.json()["data"]["loan_details"]

    for period in ("3_months", "6_months", "no", "12_months"):
        r = await client.post(f"/api/v1/loan-cases/{case_id}/top-up/schedule", json={"period": period}, headers=employee_headers)
        assert r.status_code == 200, r.text
        after_details = r.json()["data"]["loan_details"]
        assert after_details["disbursed_amount"] == before_details["disbursed_amount"]
        assert after_details["disbursed_reference"] == before_details["disbursed_reference"]
        assert after_details["disbursed_at"] == before_details["disbursed_at"]


# ---------------------------------------------------------------------- 12: unauthorized employee


async def test_top_up_actions_denied_for_employee_not_assigned_to_the_case(client, mock_db, owner_headers, master_data):
    await _seed_workflow_definitions(mock_db)
    case_id, _employee_headers, _c, application_id = await _disbursed_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000212")
    await _backdate_disbursed_at(mock_db, application_id, datetime(2020, 1, 25, 4, 0, tzinfo=UTC))

    other_employee = await _create_employee(client, owner_headers, master_data, mobile="98" + "00000212", email="unassigned-topup@example.com")
    await _grant_case_permission(client, owner_headers, other_employee["id"], module="loan_management", actions=["view", "edit", "approve", "assign"])
    other_headers = await _login(client, "98" + "00000212")

    r = await client.post(f"/api/v1/loan-cases/{case_id}/top-up/schedule", json={"period": "3_months"}, headers=other_headers)
    assert r.status_code == 403, r.text

    r = await client.post(f"/api/v1/loan-cases/{case_id}/top-up/move-to-document-collection", json={}, headers=other_headers)
    assert r.status_code == 403, r.text


async def test_disbursed_case_never_becomes_top_up_eligible_without_scheduling(client, mock_db, owner_headers, master_data):
    """Edge case #12 (spec) — a loan that is Disbursed but was never scheduled for Top
    Up (top_up_eligibility_date stays None by default) must never appear as eligible,
    however far in the past its disbursed_at is backdated."""
    await _seed_workflow_definitions(mock_db)
    case_id, employee_headers, _c, application_id = await _disbursed_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000213")
    await _backdate_disbursed_at(mock_db, application_id, datetime(2015, 1, 1, tzinfo=UTC))

    r = await client.get("/api/v1/loan-cases?top_up_eligible=true", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert case_id not in {c["id"] for c in r.json()["data"]}


async def test_schedule_top_up_rejected_for_a_non_disbursed_case(client, mock_db, owner_headers, master_data):
    """A case not yet Disbursed must never be schedulable/eligible for Top Up."""
    await _seed_workflow_definitions(mock_db)
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000214")
    assert (await client.get(f"/api/v1/loan-cases/{case_id}", headers=employee_headers)).json()["data"]["current_status"] == "new_customer"

    r = await client.post(f"/api/v1/loan-cases/{case_id}/top-up/schedule", json={"period": "3_months"}, headers=employee_headers)
    assert r.status_code >= 400, r.text

    r = await client.post(f"/api/v1/loan-cases/{case_id}/top-up/move-to-document-collection", json={}, headers=employee_headers)
    assert r.status_code >= 400, r.text
