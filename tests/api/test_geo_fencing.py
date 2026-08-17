"""Tests for Geo Fencing (Stage 1 of the Geo Fencing / Temporary Permissions / MSG91
work): named GeoFence CRUD, GeoException as a bypass of Geo Fence enforcement (not a
second, competing location restriction — see access_control/models.py:GeoException), and
the enforcement engine (`app/features/geo_fencing/enforcement.py`) that actually gates
real activities.

End-to-end enforcement is proven through `POST /leads` (create_lead) — the same
`enforce_geo_fence` function is called identically (just a different `activity` string)
from loan/insurance "Verify Documents", which is unit-tested directly here rather than
duplicated end-to-end through a full loan/insurance case lifecycle (see test_workflow.py
for how heavy that fixture chain is) — not re-proving the shared function, just its wiring.
"""

from datetime import timedelta

import pytest

from app.core.exceptions import ForbiddenError
from app.features.access_control.models import GeoException
from app.features.auth.models import ACCOUNT_STATUS_ACTIVE, User
from app.features.employee.models import Branch, Department, Designation, Employee
from app.features.geo_fencing.constants import GeoActivity
from app.features.geo_fencing.enforcement import enforce_geo_fence
from app.features.system_settings.models import LeadSource, LoanProduct
from app.utils.datetime import utc_now

# Bangalore HQ-ish coordinates for a 5km fence.
_HQ_LAT, _HQ_LON = 12.9716, 77.5946
_INSIDE_LAT, _INSIDE_LON = 12.9750, 77.5980  # ~500m away
_OUTSIDE_LAT, _OUTSIDE_LON = 13.0827, 80.2707  # Chennai — hundreds of km away


async def _create_employee(client, owner_headers, master_data, mobile="9411111111", email="geo.test@example.com"):
    payload = {
        "mobile": mobile, "initial_password": "InitialPass1!", "first_name": "Geo", "last_name": "Tester",
        "email": email, "department_id": master_data["department_id"], "designation_id": master_data["designation_id"],
        "branch_id": master_data["branch_id"], "joining_date": "2026-01-15", "employment_type": "full_time",
    }
    r = await client.post("/api/v1/employees", json=payload, headers=owner_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _create_role_with_permission(client, owner_headers, employee_id, *, module, resource, actions):
    r = await client.post("/api/v1/permissions", json={"module": module, "resource": resource, "actions": actions}, headers=owner_headers)
    assert r.status_code == 200, r.text
    permission = r.json()["data"]
    r = await client.post("/api/v1/roles", json={"name": f"Role for {module}:{resource}"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    role = r.json()["data"]
    r = await client.put(
        f"/api/v1/roles/{role['id']}/permissions",
        json={"grants": [{"permission_id": permission["id"], "granted_actions": actions}]},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/roles/{role['id']}/assign", json={"employee_id": employee_id}, headers=owner_headers)
    assert r.status_code == 200, r.text


def _fence_payload(**overrides):
    payload = {
        "area_name": "Bangalore HQ", "address": "MG Road, Bangalore",
        "latitude": _HQ_LAT, "longitude": _HQ_LON, "radius_meters": 5000,
        "allowed_activities": [GeoActivity.LEAD_CREATION],
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------- CRUD


async def test_create_geo_fence_valid(client, owner_headers):
    r = await client.post("/api/v1/geo-fences", json=_fence_payload(), headers=owner_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "active"
    assert data["area_name"] == "Bangalore HQ"


@pytest.mark.parametrize(
    "overrides",
    [
        {"latitude": 95.0},
        {"latitude": -95.0},
        {"longitude": 190.0},
        {"longitude": -190.0},
        {"radius_meters": 0},
        {"radius_meters": -50},
    ],
)
async def test_create_geo_fence_rejects_invalid_values(client, owner_headers, overrides):
    r = await client.post("/api/v1/geo-fences", json=_fence_payload(**overrides), headers=owner_headers)
    assert r.status_code == 422, r.text


async def test_create_geo_fence_missing_required_fields(client, owner_headers):
    r = await client.post("/api/v1/geo-fences", json={"area_name": "Incomplete"}, headers=owner_headers)
    assert r.status_code == 422, r.text


async def test_create_geo_fence_rejects_unknown_activity(client, owner_headers):
    r = await client.post("/api/v1/geo-fences", json=_fence_payload(allowed_activities=["skydiving"]), headers=owner_headers)
    assert r.status_code == 422, r.text


async def test_edit_activate_deactivate_geo_fence(client, owner_headers):
    r = await client.post("/api/v1/geo-fences", json=_fence_payload(), headers=owner_headers)
    fence_id = r.json()["data"]["id"]

    r = await client.patch(f"/api/v1/geo-fences/{fence_id}", json={"radius_meters": 3000}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["radius_meters"] == 3000

    r = await client.patch(f"/api/v1/geo-fences/{fence_id}/deactivate", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "inactive"

    r = await client.patch(f"/api/v1/geo-fences/{fence_id}/activate", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "active"


async def test_overlap_warning_is_non_blocking(client, owner_headers):
    r = await client.post("/api/v1/geo-fences", json=_fence_payload(area_name="Fence A"), headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.post(
        "/api/v1/geo-fences", json=_fence_payload(area_name="Fence B", latitude=_HQ_LAT + 0.001, longitude=_HQ_LON), headers=owner_headers
    )
    assert r.status_code == 200, r.text  # not blocked
    assert "Fence A" in r.json()["data"]["overlaps_with"]


async def test_delete_unaffected_by_active_geo_exceptions(client, owner_headers, master_data):
    """A GeoException no longer references any one fence — it's a bypass of whichever
    fence(s) would otherwise apply to the employee/activity (see this file's own module
    docstring) — so an active exception for an employee must never block deleting an
    unrelated GeoFence."""
    employee = await _create_employee(client, owner_headers, master_data)
    r = await client.post("/api/v1/geo-fences", json=_fence_payload(), headers=owner_headers)
    fence_id = r.json()["data"]["id"]

    now = utc_now()
    r = await client.post(
        "/api/v1/geo-exceptions",
        json={
            "employee_id": employee["id"],
            "start_date": now.date().isoformat(), "end_date": (now + timedelta(days=1)).date().isoformat(),
            "start_time": "09:00", "end_time": "18:00", "reason": "Field visit",
        },
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text

    r = await client.delete(f"/api/v1/geo-fences/{fence_id}", headers=owner_headers)
    assert r.status_code == 200, r.text


async def test_delete_allowed_with_no_referencing_exceptions(client, owner_headers):
    r = await client.post("/api/v1/geo-fences", json=_fence_payload(), headers=owner_headers)
    fence_id = r.json()["data"]["id"]
    r = await client.delete(f"/api/v1/geo-fences/{fence_id}", headers=owner_headers)
    assert r.status_code == 200, r.text
    r = await client.get(f"/api/v1/geo-fences/{fence_id}", headers=owner_headers)
    assert r.status_code == 404, r.text


async def test_search_filter_and_pagination(client, owner_headers):
    await client.post("/api/v1/geo-fences", json=_fence_payload(area_name="Bangalore HQ"), headers=owner_headers)
    await client.post(
        "/api/v1/geo-fences",
        json=_fence_payload(area_name="Chennai Office", latitude=13.0827, longitude=80.2707, allowed_activities=[GeoActivity.DOCUMENT_COLLECTION]),
        headers=owner_headers,
    )

    r = await client.get("/api/v1/geo-fences?page=1&page_size=1", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 1
    assert r.json()["meta"]["pagination"]["total"] == 2

    r = await client.get("/api/v1/geo-fences?search=Chennai", headers=owner_headers)
    assert len(r.json()["data"]) == 1
    assert r.json()["data"][0]["area_name"] == "Chennai Office"

    r = await client.get(f"/api/v1/geo-fences?activity={GeoActivity.DOCUMENT_COLLECTION}", headers=owner_headers)
    assert len(r.json()["data"]) == 1
    assert r.json()["data"][0]["area_name"] == "Chennai Office"


# ---------------------------------------------------------------------- permission gating / IDOR


async def test_employee_without_permission_is_denied(client, employee_headers):
    r = await client.get("/api/v1/geo-fences", headers=employee_headers)
    assert r.status_code == 403, r.text
    r = await client.post("/api/v1/geo-fences", json=_fence_payload(), headers=employee_headers)
    assert r.status_code == 403, r.text


async def test_employee_with_granted_permission_is_allowed(client, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data, mobile="9422222222", email="geo.granted@example.com")
    r = await client.post("/api/v1/auth/login", json={"mobile": "9422222222", "password": "InitialPass1!"})
    assert r.status_code == 200, r.text
    own_headers = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    r = await client.post("/api/v1/geo-fences", json=_fence_payload(), headers=own_headers)
    assert r.status_code == 403, r.text  # not granted yet

    await _create_role_with_permission(client, owner_headers, employee["id"], module="geo_fencing", resource="fences", actions=["view", "create"])

    r = await client.post("/api/v1/geo-fences", json=_fence_payload(), headers=own_headers)
    assert r.status_code == 200, r.text

    # "delete" was never granted — must still be denied (no IDOR via guessing a real id).
    fence_id = r.json()["data"]["id"]
    r = await client.delete(f"/api/v1/geo-fences/{fence_id}", headers=own_headers)
    assert r.status_code == 403, r.text


async def test_unauthenticated_request_is_rejected(client):
    r = await client.get("/api/v1/geo-fences")
    assert r.status_code in (401, 403), r.text


# ---------------------------------------------------------------------- enforcement engine


async def _make_employee_user(mock_db, *, mobile: str) -> tuple[User, Employee]:
    department = Department(name="Field")
    designation = Designation(name="Officer")
    branch = Branch(name="HQ", code="HQ1")
    dept_id = (await mock_db["departments"].insert_one(department.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    desig_id = (await mock_db["designations"].insert_one(designation.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    branch_id = (await mock_db["branches"].insert_one(branch.model_dump(by_alias=True, exclude={"id"}))).inserted_id

    user = User(mobile=mobile, role="employee", status=ACCOUNT_STATUS_ACTIVE, password_hash="x")
    user_id = (await mock_db["users"].insert_one(user.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    user = user.model_copy(update={"id": str(user_id)})

    employee = Employee(
        user_id=str(user_id), employee_code=f"EMP-GEO-{mobile}", first_name="Field", last_name="Officer", display_name="Field Officer",
        mobile=mobile, email=f"{mobile}@example.com", department_id=str(dept_id), designation_id=str(desig_id),
        branch_id=str(branch_id), joining_date=utc_now(), employment_type="full_time",
    )
    emp_id = (await mock_db["employees"].insert_one(employee.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    employee = employee.model_copy(update={"id": str(emp_id)})
    return user, employee


async def _make_fence(mock_db, *, activities, status="active"):
    from app.features.geo_fencing.models import GeoFence

    fence = GeoFence(
        area_name="Test Fence", address="Test Address", latitude=_HQ_LAT, longitude=_HQ_LON,
        radius_meters=5000, allowed_activities=list(activities), status=status,
    )
    fence_id = (await mock_db["geo_fences"].insert_one(fence.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    return str(fence_id)


async def test_enforcement_noop_when_no_fence_configured_for_activity(mock_db):
    user, _employee = await _make_employee_user(mock_db, mobile="9500000001")
    # No fences at all — must not raise, regardless of coordinates.
    await enforce_geo_fence(mock_db, actor=user, activity=GeoActivity.LEAD_CREATION, latitude=None, longitude=None)


async def test_enforcement_allows_inside_radius(mock_db):
    user, _employee = await _make_employee_user(mock_db, mobile="9500000002")
    await _make_fence(mock_db, activities=[GeoActivity.LEAD_CREATION])
    await enforce_geo_fence(mock_db, actor=user, activity=GeoActivity.LEAD_CREATION, latitude=_INSIDE_LAT, longitude=_INSIDE_LON)


async def test_enforcement_denies_outside_radius(mock_db):
    user, _employee = await _make_employee_user(mock_db, mobile="9500000003")
    await _make_fence(mock_db, activities=[GeoActivity.LEAD_CREATION])
    with pytest.raises(ForbiddenError, match="outside the permitted work area"):
        await enforce_geo_fence(mock_db, actor=user, activity=GeoActivity.LEAD_CREATION, latitude=_OUTSIDE_LAT, longitude=_OUTSIDE_LON)


async def test_enforcement_requires_coordinates_when_fence_configured(mock_db):
    user, _employee = await _make_employee_user(mock_db, mobile="9500000004")
    await _make_fence(mock_db, activities=[GeoActivity.LEAD_CREATION])
    with pytest.raises(ForbiddenError, match="Location is required"):
        await enforce_geo_fence(mock_db, actor=user, activity=GeoActivity.LEAD_CREATION, latitude=None, longitude=None)


async def test_enforcement_inactive_fence_does_not_apply(mock_db):
    user, _employee = await _make_employee_user(mock_db, mobile="9500000005")
    await _make_fence(mock_db, activities=[GeoActivity.LEAD_CREATION], status="inactive")
    # Inactive fence means nothing is configured for this activity -> no-op, no rejection.
    await enforce_geo_fence(mock_db, actor=user, activity=GeoActivity.LEAD_CREATION, latitude=None, longitude=None)


async def test_enforcement_valid_geo_exception_overrides_outside_radius(mock_db):
    user, employee = await _make_employee_user(mock_db, mobile="9500000006")
    await _make_fence(mock_db, activities=[GeoActivity.LEAD_CREATION])
    now = utc_now()
    exception = GeoException(
        employee_id=employee.require_id(),
        start_date=now - timedelta(days=1), end_date=now + timedelta(days=1),
        start_time="00:00", end_time="23:59", reason="Approved remote work", status="active",
    )
    await mock_db["geo_exceptions"].insert_one(exception.model_dump(by_alias=True, exclude={"id"}))

    # Outside every fence, but a currently-valid exception exists for this employee -> allowed.
    await enforce_geo_fence(mock_db, actor=user, activity=GeoActivity.LEAD_CREATION, latitude=_OUTSIDE_LAT, longitude=_OUTSIDE_LON)


async def test_enforcement_expired_geo_exception_does_not_override(mock_db):
    user, employee = await _make_employee_user(mock_db, mobile="9500000007")
    await _make_fence(mock_db, activities=[GeoActivity.LEAD_CREATION])
    now = utc_now()
    exception = GeoException(
        employee_id=employee.require_id(),
        start_date=now - timedelta(days=10), end_date=now - timedelta(days=5),
        start_time="00:00", end_time="23:59", reason="Expired", status="active",
    )
    await mock_db["geo_exceptions"].insert_one(exception.model_dump(by_alias=True, exclude={"id"}))

    with pytest.raises(ForbiddenError, match="outside the permitted work area"):
        await enforce_geo_fence(mock_db, actor=user, activity=GeoActivity.LEAD_CREATION, latitude=_OUTSIDE_LAT, longitude=_OUTSIDE_LON)


async def test_enforcement_revoked_geo_exception_does_not_override(mock_db):
    """A revoked exception must stop bypassing immediately — the employee falls straight
    back under normal Geo Fence enforcement (find_active_for_employee only ever
    considers status=active)."""
    user, employee = await _make_employee_user(mock_db, mobile="9500000010")
    await _make_fence(mock_db, activities=[GeoActivity.LEAD_CREATION])
    now = utc_now()
    exception = GeoException(
        employee_id=employee.require_id(),
        start_date=now - timedelta(days=1), end_date=now + timedelta(days=1),
        start_time="00:00", end_time="23:59", reason="Revoked before use", status="revoked",
    )
    await mock_db["geo_exceptions"].insert_one(exception.model_dump(by_alias=True, exclude={"id"}))

    with pytest.raises(ForbiddenError, match="outside the permitted work area"):
        await enforce_geo_fence(mock_db, actor=user, activity=GeoActivity.LEAD_CREATION, latitude=_OUTSIDE_LAT, longitude=_OUTSIDE_LON)


async def test_enforcement_blanket_exception_bypasses_every_enforced_activity(mock_db):
    """activity=None ("All Activities" in the UI) must exempt the employee from every
    enforced activity's Geo Fence, not just the one under test elsewhere in this file."""
    user, employee = await _make_employee_user(mock_db, mobile="9500000011")
    await _make_fence(mock_db, activities=[GeoActivity.LEAD_CREATION])
    await _make_fence(mock_db, activities=[GeoActivity.DOCUMENT_COLLECTION])
    now = utc_now()
    exception = GeoException(
        employee_id=employee.require_id(),
        start_date=now - timedelta(days=1), end_date=now + timedelta(days=1),
        start_time="00:00", end_time="23:59", reason="All Activities, work from home", activity=None, status="active",
    )
    await mock_db["geo_exceptions"].insert_one(exception.model_dump(by_alias=True, exclude={"id"}))

    await enforce_geo_fence(mock_db, actor=user, activity=GeoActivity.LEAD_CREATION, latitude=_OUTSIDE_LAT, longitude=_OUTSIDE_LON)
    await enforce_geo_fence(mock_db, actor=user, activity=GeoActivity.DOCUMENT_COLLECTION, latitude=_OUTSIDE_LAT, longitude=_OUTSIDE_LON)


async def test_enforcement_activity_scoped_exception_does_not_bypass_other_activities(mock_db):
    """A Login-only exception must never also exempt the same employee from Lead
    Creation's Geo Fence — only the exact activity it names is bypassed."""
    user, employee = await _make_employee_user(mock_db, mobile="9500000012")
    await _make_fence(mock_db, activities=[GeoActivity.LOGIN])
    await _make_fence(mock_db, activities=[GeoActivity.LEAD_CREATION])
    now = utc_now()
    exception = GeoException(
        employee_id=employee.require_id(),
        start_date=now - timedelta(days=1), end_date=now + timedelta(days=1),
        start_time="00:00", end_time="23:59", reason="Login only", activity=GeoActivity.LOGIN, status="active",
    )
    await mock_db["geo_exceptions"].insert_one(exception.model_dump(by_alias=True, exclude={"id"}))

    await enforce_geo_fence(mock_db, actor=user, activity=GeoActivity.LOGIN, latitude=_OUTSIDE_LAT, longitude=_OUTSIDE_LON)
    with pytest.raises(ForbiddenError, match="outside the permitted work area"):
        await enforce_geo_fence(mock_db, actor=user, activity=GeoActivity.LEAD_CREATION, latitude=_OUTSIDE_LAT, longitude=_OUTSIDE_LON)


async def test_enforcement_multiple_matching_fences_any_match_allows(mock_db):
    user, _employee = await _make_employee_user(mock_db, mobile="9500000008")
    await _make_fence(mock_db, activities=[GeoActivity.LEAD_CREATION])  # Bangalore HQ area

    from app.features.geo_fencing.models import GeoFence

    far_fence = GeoFence(
        area_name="Chennai Office", address="Chennai", latitude=_OUTSIDE_LAT, longitude=_OUTSIDE_LON,
        radius_meters=2000, allowed_activities=[GeoActivity.LEAD_CREATION], status="active",
    )
    await mock_db["geo_fences"].insert_one(far_fence.model_dump(by_alias=True, exclude={"id"}))

    # Inside the (far) Chennai fence, outside the Bangalore one — still allowed.
    await enforce_geo_fence(mock_db, actor=user, activity=GeoActivity.LEAD_CREATION, latitude=_OUTSIDE_LAT, longitude=_OUTSIDE_LON)


async def test_enforcement_owner_bypasses(mock_db):
    owner = User(mobile="9600000000", role="owner", status=ACCOUNT_STATUS_ACTIVE, password_hash="x")
    owner_id = (await mock_db["users"].insert_one(owner.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    owner = owner.model_copy(update={"id": str(owner_id)})
    await _make_fence(mock_db, activities=[GeoActivity.LEAD_CREATION])

    # Owner outside every fence, no coordinates at all — never restricted.
    await enforce_geo_fence(mock_db, actor=owner, activity=GeoActivity.LEAD_CREATION, latitude=None, longitude=None)


async def test_enforcement_document_collection_activity_is_wired(mock_db):
    """Confirms the same shared engine works for the second enforced activity
    (loan/insurance 'Verify Documents' call this with GeoActivity.DOCUMENT_COLLECTION) —
    see this file's own module docstring for why the full case lifecycle isn't
    duplicated here just to prove the identical function again end-to-end."""
    user, _employee = await _make_employee_user(mock_db, mobile="9500000009")
    await _make_fence(mock_db, activities=[GeoActivity.DOCUMENT_COLLECTION])
    with pytest.raises(ForbiddenError, match="outside the permitted work area"):
        await enforce_geo_fence(mock_db, actor=user, activity=GeoActivity.DOCUMENT_COLLECTION, latitude=_OUTSIDE_LAT, longitude=_OUTSIDE_LON)
    await enforce_geo_fence(mock_db, actor=user, activity=GeoActivity.DOCUMENT_COLLECTION, latitude=_INSIDE_LAT, longitude=_INSIDE_LON)


# ---------------------------------------------------------------------- end-to-end via a real endpoint (create_lead)


async def _lead_master_data(mock_db) -> dict:
    source = LeadSource(name="Field Visit")
    loan_product = LoanProduct(name="Personal Loan")
    source_id = (await mock_db["lead_sources"].insert_one(source.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    loan_id = (await mock_db["loan_products"].insert_one(loan_product.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    return {"source_id": str(source_id), "loan_product_id": str(loan_id)}


def _lead_payload(lead_master_data, **overrides):
    payload = {
        "full_name": "Geo Test Lead", "mobile": "9711111111", "source_id": lead_master_data["source_id"],
        "product_category": "loan", "product_id": lead_master_data["loan_product_id"],
    }
    payload.update(overrides)
    return payload


async def test_create_lead_end_to_end_denied_outside_fence(client, mock_db, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data, mobile="9433333333", email="geo.lead1@example.com")
    r = await client.post("/api/v1/auth/login", json={"mobile": "9433333333", "password": "InitialPass1!"})
    own_headers = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    await _create_role_with_permission(client, owner_headers, employee["id"], module="leads", resource="leads", actions=["view", "create"])

    lead_master_data = await _lead_master_data(mock_db)
    r = await client.post("/api/v1/geo-fences", json=_fence_payload(allowed_activities=[GeoActivity.LEAD_CREATION]), headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.post("/api/v1/leads", json=_lead_payload(lead_master_data, latitude=_OUTSIDE_LAT, longitude=_OUTSIDE_LON), headers=own_headers)
    assert r.status_code == 403, r.text
    assert "outside the permitted work area" in r.json()["error"]["message"]


async def test_create_lead_end_to_end_allowed_inside_fence(client, mock_db, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data, mobile="9433333334", email="geo.lead2@example.com")
    r = await client.post("/api/v1/auth/login", json={"mobile": "9433333334", "password": "InitialPass1!"})
    own_headers = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    await _create_role_with_permission(client, owner_headers, employee["id"], module="leads", resource="leads", actions=["view", "create"])

    lead_master_data = await _lead_master_data(mock_db)
    await client.post("/api/v1/geo-fences", json=_fence_payload(allowed_activities=[GeoActivity.LEAD_CREATION]), headers=owner_headers)

    r = await client.post(
        "/api/v1/leads", json=_lead_payload(lead_master_data, mobile="9711111112", latitude=_INSIDE_LAT, longitude=_INSIDE_LON), headers=own_headers
    )
    assert r.status_code == 200, r.text


async def test_create_lead_end_to_end_unaffected_when_no_fence_configured(client, mock_db, owner_headers, master_data):
    """Backward compatibility: no Geo Fence configured for lead_creation -> a caller that
    never sends latitude/longitude (e.g. an existing mobile client) behaves exactly as
    before this feature existed."""
    employee = await _create_employee(client, owner_headers, master_data, mobile="9433333335", email="geo.lead3@example.com")
    r = await client.post("/api/v1/auth/login", json={"mobile": "9433333335", "password": "InitialPass1!"})
    own_headers = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    await _create_role_with_permission(client, owner_headers, employee["id"], module="leads", resource="leads", actions=["view", "create"])

    lead_master_data = await _lead_master_data(mock_db)
    r = await client.post("/api/v1/leads", json=_lead_payload(lead_master_data, mobile="9711111113"), headers=own_headers)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------- Login Geo-Fencing (Auth integration)
#
# `AuthService.login` reuses `enforce_geo_fence` unchanged (see auth/service.py) — these
# tests prove the wiring (activity="login", the distinct login_geo_fence_denied error
# code/message, and the Login-scoped GeoException.activity field) rather than re-proving
# the shared engine's own distance/window logic already covered above.


async def _login_raw(client, mobile, password, *, latitude=None, longitude=None):
    payload = {"mobile": mobile, "password": password}
    if latitude is not None:
        payload["latitude"] = latitude
    if longitude is not None:
        payload["longitude"] = longitude
    return await client.post("/api/v1/auth/login", json=payload)


async def test_login_unaffected_when_no_login_fence_configured(client, owner_headers, master_data):
    """Backward compatibility baseline: an existing employee's login must behave exactly
    as before this feature existed when no Geo Fence has "login" in its
    allowed_activities — even a fence configured for a different activity must not
    affect login at all."""
    await _create_employee(client, owner_headers, master_data, mobile="9455555501", email="login.baseline@example.com")
    await client.post("/api/v1/geo-fences", json=_fence_payload(allowed_activities=[GeoActivity.LEAD_CREATION]), headers=owner_headers)

    r = await _login_raw(client, "9455555501", "InitialPass1!", latitude=_OUTSIDE_LAT, longitude=_OUTSIDE_LON)
    assert r.status_code == 200, r.text


async def test_login_allowed_inside_configured_login_fence(client, owner_headers, master_data):
    await _create_employee(client, owner_headers, master_data, mobile="9455555502", email="login.inside@example.com")
    await client.post("/api/v1/geo-fences", json=_fence_payload(allowed_activities=[GeoActivity.LOGIN]), headers=owner_headers)

    r = await _login_raw(client, "9455555502", "InitialPass1!", latitude=_INSIDE_LAT, longitude=_INSIDE_LON)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["access_token"]


async def test_login_denied_outside_configured_login_fence_with_distinct_message(client, owner_headers, master_data):
    await _create_employee(client, owner_headers, master_data, mobile="9455555503", email="login.outside@example.com")
    await client.post("/api/v1/geo-fences", json=_fence_payload(allowed_activities=[GeoActivity.LOGIN]), headers=owner_headers)

    r = await _login_raw(client, "9455555503", "InitialPass1!", latitude=_OUTSIDE_LAT, longitude=_OUTSIDE_LON)
    assert r.status_code == 403, r.text
    body = r.json()
    assert body["error"]["code"] == "login_geo_fence_denied"
    assert "authorized location" in body["error"]["message"]


async def test_login_denied_when_login_fence_configured_and_no_coordinates_supplied(client, owner_headers, master_data):
    """GPS failure must never silently bypass Geo-Fenced Login."""
    await _create_employee(client, owner_headers, master_data, mobile="9455555504", email="login.nogps@example.com")
    await client.post("/api/v1/geo-fences", json=_fence_payload(allowed_activities=[GeoActivity.LOGIN]), headers=owner_headers)

    r = await _login_raw(client, "9455555504", "InitialPass1!")  # no latitude/longitude at all
    assert r.status_code == 403, r.text
    # AuthService.login catches every ForbiddenError enforce_geo_fence can raise
    # (missing-coordinates included) and re-raises as the same distinct
    # login_geo_fence_denied code/message — not silently bypassed, and not the
    # generic "forbidden" every other permission denial uses.
    body = r.json()
    assert body["error"]["code"] == "login_geo_fence_denied"
    assert "authorized location" in body["error"]["message"]


async def test_login_geo_fence_never_applies_to_owner(client, owner_headers):
    await client.post("/api/v1/geo-fences", json=_fence_payload(allowed_activities=[GeoActivity.LOGIN]), headers=owner_headers)
    r = await _login_raw(client, "9000000001", "OwnerPass1!", latitude=_OUTSIDE_LAT, longitude=_OUTSIDE_LON)
    assert r.status_code == 200, r.text
    r = await _login_raw(client, "9000000001", "OwnerPass1!")  # not even coordinates supplied
    assert r.status_code == 200, r.text


async def test_login_denial_does_not_count_toward_failed_login_lockout(client, owner_headers, master_data):
    """Deliberate design decision (see AuthService.login's own comment): a geo-fence
    denial is a location problem, not a credentials-guessing one, so repeated denied
    logins with CORRECT credentials must never lock the account the way repeated wrong
    passwords would."""
    await _create_employee(client, owner_headers, master_data, mobile="9455555505", email="login.lockout@example.com")
    await client.post("/api/v1/geo-fences", json=_fence_payload(allowed_activities=[GeoActivity.LOGIN]), headers=owner_headers)

    for _ in range(6):  # well past this app's failed-attempt lockout threshold
        r = await _login_raw(client, "9455555505", "InitialPass1!", latitude=_OUTSIDE_LAT, longitude=_OUTSIDE_LON)
        assert r.status_code == 403, r.text
        assert r.json()["error"]["code"] == "login_geo_fence_denied"

    # Correct credentials from an allowed location still succeed — never locked out.
    r = await _login_raw(client, "9455555505", "InitialPass1!", latitude=_INSIDE_LAT, longitude=_INSIDE_LON)
    assert r.status_code == 200, r.text


async def test_login_scoped_geo_exception_allows_outside_radius(client, mock_db, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data, mobile="9455555506", email="login.exception@example.com")
    await client.post("/api/v1/geo-fences", json=_fence_payload(allowed_activities=[GeoActivity.LOGIN]), headers=owner_headers)

    now = utc_now()
    exception = GeoException(
        employee_id=employee["id"],
        start_date=now - timedelta(days=1), end_date=now + timedelta(days=1),
        start_time="00:00", end_time="23:59", reason="Work from home", activity=GeoActivity.LOGIN, status="active",
    )
    await mock_db["geo_exceptions"].insert_one(exception.model_dump(by_alias=True, exclude={"id"}))

    r = await _login_raw(client, "9455555506", "InitialPass1!", latitude=_OUTSIDE_LAT, longitude=_OUTSIDE_LON)
    assert r.status_code == 200, r.text


async def test_login_scoped_geo_exception_denied_after_expiry(client, mock_db, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data, mobile="9455555507", email="login.expired@example.com")
    await client.post("/api/v1/geo-fences", json=_fence_payload(allowed_activities=[GeoActivity.LOGIN]), headers=owner_headers)

    now = utc_now()
    exception = GeoException(
        employee_id=employee["id"],
        start_date=now - timedelta(days=10), end_date=now - timedelta(days=5),
        start_time="00:00", end_time="23:59", reason="Expired", activity=GeoActivity.LOGIN, status="active",
    )
    await mock_db["geo_exceptions"].insert_one(exception.model_dump(by_alias=True, exclude={"id"}))

    r = await _login_raw(client, "9455555507", "InitialPass1!", latitude=_OUTSIDE_LAT, longitude=_OUTSIDE_LON)
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "login_geo_fence_denied"


async def test_login_exception_belonging_to_different_employee_does_not_apply(client, mock_db, owner_headers, master_data):
    await _create_employee(client, owner_headers, master_data, mobile="9455555508", email="login.notmine@example.com")
    other_employee = await _create_employee(client, owner_headers, master_data, mobile="9455555509", email="login.other@example.com")
    await client.post("/api/v1/geo-fences", json=_fence_payload(allowed_activities=[GeoActivity.LOGIN]), headers=owner_headers)

    now = utc_now()
    exception = GeoException(
        employee_id=other_employee["id"],
        start_date=now - timedelta(days=1), end_date=now + timedelta(days=1),
        start_time="00:00", end_time="23:59", reason="Not this employee", activity=GeoActivity.LOGIN, status="active",
    )
    await mock_db["geo_exceptions"].insert_one(exception.model_dump(by_alias=True, exclude={"id"}))

    r = await _login_raw(client, "9455555508", "InitialPass1!", latitude=_OUTSIDE_LAT, longitude=_OUTSIDE_LON)
    assert r.status_code == 403, r.text


async def test_login_blanket_pre_existing_exception_still_applies_to_login(client, mock_db, owner_headers, master_data):
    """Backward compatibility: an exception granted before the `activity` field existed
    (or explicitly created with no activity) reads back as `activity=None` and must keep
    exempting the employee from every enforced activity, login included."""
    employee = await _create_employee(client, owner_headers, master_data, mobile="9455555510", email="login.blanket@example.com")
    await client.post("/api/v1/geo-fences", json=_fence_payload(allowed_activities=[GeoActivity.LOGIN]), headers=owner_headers)

    now = utc_now()
    exception = GeoException(
        employee_id=employee["id"],
        start_date=now - timedelta(days=1), end_date=now + timedelta(days=1),
        start_time="00:00", end_time="23:59", reason="Blanket, pre-dates activity field", activity=None, status="active",
    )
    await mock_db["geo_exceptions"].insert_one(exception.model_dump(by_alias=True, exclude={"id"}))

    r = await _login_raw(client, "9455555510", "InitialPass1!", latitude=_OUTSIDE_LAT, longitude=_OUTSIDE_LON)
    assert r.status_code == 200, r.text


async def test_login_boundary_distance_equal_to_radius_is_allowed(client, owner_headers, master_data):
    """Inherits enforce_geo_fence's existing `<=` comparison — not new behavior, just
    confirmed to hold for the login activity too."""
    await _create_employee(client, owner_headers, master_data, mobile="9455555511", email="login.boundary@example.com")
    r = await client.post(
        "/api/v1/geo-fences",
        json=_fence_payload(allowed_activities=[GeoActivity.LOGIN], radius_meters=1),
        headers=owner_headers,
    )
    fence = r.json()["data"]

    r = await _login_raw(client, "9455555511", "InitialPass1!", latitude=fence["latitude"], longitude=fence["longitude"])
    assert r.status_code == 200, r.text  # distance 0 <= radius 1
