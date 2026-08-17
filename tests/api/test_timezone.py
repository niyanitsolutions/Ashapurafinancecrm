"""Global timezone standardization to IST (Asia/Kolkata) — regression tests.

Business-day/business-hour logic (Geo Fencing exceptions, Temporary Access windows,
Dashboard "today", Reports date ranges, Leads assignment tie-break) must evaluate
against India Standard Time, never UTC wall-clock — even though storage/machine
timestamps (Mongo `created_at`, JWT `exp`, OTP TTLs) stay UTC throughout. See
docs/TIMEZONE.md.

Most tests here call the IST helpers (`to_ist`, `start_of_day_ist`,
`ist_date_range_to_utc_bounds`, `within_daily_window`) with an explicit `dt`/`now`
argument — deliberately testable without freezing the real clock, since every helper in
`app/utils/datetime.py` accepts an optional override for exactly this reason. The
handful of tests that need to freeze the *ambient* clock (no explicit `now` parameter to
pass, e.g. `WIDGET_PROVIDERS["today_leads"]`) use a small local monkeypatch fixture
rather than adding a new freeze-time dependency, matching this suite's existing
no-new-dependency convention.
"""

from datetime import UTC, date
from datetime import datetime as real_datetime
from typing import ClassVar
from zoneinfo import ZoneInfo

import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

from app.constants.roles import OWNER
from app.core.exceptions import ForbiddenError
from app.features.access_control.models import GeoException
from app.features.auth.models import User
from app.features.dashboard.widget_providers import WIDGET_PROVIDERS
from app.features.geo_fencing.constants import GeoActivity
from app.features.geo_fencing.enforcement import enforce_geo_fence
from app.features.reporting.aggregations import date_range_match
from app.security.jwt import TokenType, create_access_token, decode_token
from app.utils.datetime import (
    ist_date_range_to_utc_bounds,
    now_ist,
    start_of_day_ist,
    to_ist,
    within_daily_window,
)

_IST = ZoneInfo("Asia/Kolkata")
_HQ_LAT, _HQ_LON = 12.9716, 77.5946
_OUTSIDE_LAT, _OUTSIDE_LON = 13.0827, 80.2707


# ---------------------------------------------------------------------- clock freezing

class _FrozenDateTime(real_datetime):
    """Every IST helper in app/utils/datetime.py calls `datetime.now(...)` via that
    module's own `datetime` name — patching `app.utils.datetime.datetime` to this class
    (see `freeze_utc` below) freezes every helper's ambient clock, regardless of which
    other module imported/calls those helper functions by reference (functions resolve
    globals from the module they're *defined* in, not the caller's)."""

    _frozen: ClassVar[real_datetime]

    @classmethod
    def now(cls, tz: object = None) -> real_datetime:  # type: ignore[override]
        if tz is None:
            return cls._frozen.replace(tzinfo=None)
        return cls._frozen.astimezone(tz)  # type: ignore[arg-type]


@pytest.fixture
def freeze_utc(monkeypatch: pytest.MonkeyPatch):
    def _apply(instant: real_datetime) -> None:
        frozen = type("Frozen", (_FrozenDateTime,), {"_frozen": instant})
        monkeypatch.setattr("app.utils.datetime.datetime", frozen)

    return _apply


# ---------------------------------------------------------------------- utility unit tests


def test_spec_worked_example_utc_to_ist():
    """The spec's own example: AWS system time 07:08 UTC must read as 12:38 PM IST."""
    instant = real_datetime(2026, 8, 17, 7, 8, tzinfo=UTC)
    ist = to_ist(instant)
    assert (ist.hour, ist.minute) == (12, 38)
    assert ist.tzinfo is not None


def test_within_daily_window_utc_vs_ist_worked_example():
    """The bug this fixes, isolated at the unit that changed: the SAME instant (07:08
    UTC / 12:38 IST) must be judged ACTIVE against a 09:00-18:00 window when evaluated
    in IST, and would have been wrongly judged INACTIVE if evaluated in raw UTC."""
    instant = real_datetime(2026, 8, 17, 7, 8, tzinfo=UTC)
    ist_wallclock = to_ist(instant)
    start = end = real_datetime(2026, 8, 17, tzinfo=UTC)

    assert within_daily_window(start, end, "09:00", "18:00", ist_wallclock) is True
    assert within_daily_window(start, end, "09:00", "18:00", instant) is False


@pytest.mark.parametrize(
    "hour,minute,expected",
    [
        (8, 59, False),
        (9, 0, True),
        (12, 38, True),
        (18, 0, True),
        (18, 1, False),
    ],
)
def test_within_daily_window_ist_boundaries(hour: int, minute: int, expected: bool):
    ist_now = real_datetime(2026, 8, 17, hour, minute, tzinfo=_IST)
    start = end = real_datetime(2026, 8, 17, tzinfo=UTC)
    assert within_daily_window(start, end, "09:00", "18:00", ist_now) is expected


def test_start_of_day_ist_across_midnight_boundary():
    """23:30 UTC on the 17th is 2026-08-18 00:30 IST — the IST calendar date (18th)
    differs from the UTC calendar date (17th)."""
    just_after_ist_midnight = real_datetime(2026, 8, 17, 19, 0, tzinfo=UTC)  # = 2026-08-18 00:30 IST
    ist_view = to_ist(just_after_ist_midnight)
    assert ist_view.date() == date(2026, 8, 18)

    boundary = start_of_day_ist(just_after_ist_midnight)
    # 2026-08-18 00:00 IST == 2026-08-17 18:30 UTC.
    assert boundary == real_datetime(2026, 8, 17, 18, 30, tzinfo=UTC)


def test_ist_date_range_to_utc_bounds():
    lower, upper = ist_date_range_to_utc_bounds(date(2026, 8, 17), date(2026, 8, 17))
    assert lower == real_datetime(2026, 8, 16, 18, 30, tzinfo=UTC)  # 2026-08-17 00:00 IST
    assert upper == real_datetime(2026, 8, 17, 18, 30, tzinfo=UTC)  # 2026-08-18 00:00 IST (exclusive)


def test_date_range_match_uses_ist_day_boundaries():
    d = date(2026, 8, 17)
    query = date_range_match("created_at", d, d)["created_at"]
    assert query["$gte"] == real_datetime(2026, 8, 16, 18, 30, tzinfo=UTC)
    assert query["$lt"] == real_datetime(2026, 8, 17, 18, 30, tzinfo=UTC)


# ---------------------------------------------------------------------- Mongo tz_aware regression lock


async def test_mongo_reads_are_tz_aware_utc(mock_db):
    """Locks in the root-cause fix (app/config/database.py's tz_aware=True) so it can't
    silently regress — a naive read here would reintroduce the "browser mis-parses a
    naive timestamp as local time" bug across the entire API."""
    exc = GeoException(
        employee_id=str(ObjectId()), start_date=now_ist(), end_date=now_ist(),
        start_time="09:00", end_time="18:00", reason="tz_aware regression lock",
    )
    inserted = await mock_db["geo_exceptions"].insert_one(exc.model_dump(by_alias=True, exclude={"id"}))
    doc = await mock_db["geo_exceptions"].find_one({"_id": inserted.inserted_id})
    assert doc["start_date"].tzinfo is not None
    assert doc["created_at"].tzinfo is not None


# ---------------------------------------------------------------------- Geo Fencing enforcement, end-to-end wiring


async def _make_employee_user(mock_db, *, mobile: str):
    from app.features.auth.models import ACCOUNT_STATUS_ACTIVE
    from app.features.employee.models import Branch, Department, Designation, Employee
    from app.utils.datetime import utc_now

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
        user_id=str(user_id), employee_code=f"EMP-TZ-{mobile}", first_name="Field", last_name="Officer", display_name="Field Officer",
        mobile=mobile, email=f"{mobile}@example.com", department_id=str(dept_id), designation_id=str(desig_id),
        branch_id=str(branch_id), joining_date=utc_now(), employment_type="full_time",
    )
    emp_id = (await mock_db["employees"].insert_one(employee.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    employee = employee.model_copy(update={"id": str(emp_id)})
    return user, employee


async def _make_fence(mock_db, *, activities):
    from app.features.geo_fencing.models import GeoFence

    fence = GeoFence(
        area_name="Test Fence", address="Test Address", latitude=_HQ_LAT, longitude=_HQ_LON,
        radius_meters=5000, allowed_activities=list(activities), status="active",
    )
    await mock_db["geo_fences"].insert_one(fence.model_dump(by_alias=True, exclude={"id"}))


async def test_enforce_geo_fence_uses_ist_not_utc_at_the_spec_worked_instant(mock_db, freeze_utc):
    """Full end-to-end wiring check: at the spec's own worked instant (07:08 UTC == 12:38
    IST), an employee outside every fence, with a 09:00-18:00 Geo Exception, must be
    allowed — proving `enforce_geo_fence` really does feed IST "now" into the daily
    window, not UTC."""
    freeze_utc(real_datetime(2026, 8, 17, 7, 8, tzinfo=UTC))
    user, employee = await _make_employee_user(mock_db, mobile="9700000001")
    await _make_fence(mock_db, activities=[GeoActivity.LEAD_CREATION])

    exception = GeoException(
        employee_id=employee.require_id(),
        start_date=real_datetime(2026, 8, 17, tzinfo=UTC), end_date=real_datetime(2026, 8, 17, tzinfo=UTC),
        start_time="09:00", end_time="18:00", reason="Work from home", status="active",
    )
    await mock_db["geo_exceptions"].insert_one(exception.model_dump(by_alias=True, exclude={"id"}))

    # Outside every fence, but the exception is active right now (12:38 IST) -> allowed.
    await enforce_geo_fence(mock_db, actor=user, activity=GeoActivity.LEAD_CREATION, latitude=_OUTSIDE_LAT, longitude=_OUTSIDE_LON)


async def test_enforce_geo_fence_denies_one_minute_after_ist_window_closes(mock_db, freeze_utc):
    """18:01 IST (12:31 UTC) — one minute past the exception's 18:00 end — must deny."""
    freeze_utc(real_datetime(2026, 8, 17, 12, 31, tzinfo=UTC))  # = 2026-08-17 18:01 IST
    user, employee = await _make_employee_user(mock_db, mobile="9700000002")
    await _make_fence(mock_db, activities=[GeoActivity.LEAD_CREATION])

    exception = GeoException(
        employee_id=employee.require_id(),
        start_date=real_datetime(2026, 8, 17, tzinfo=UTC), end_date=real_datetime(2026, 8, 17, tzinfo=UTC),
        start_time="09:00", end_time="18:00", reason="Work from home", status="active",
    )
    await mock_db["geo_exceptions"].insert_one(exception.model_dump(by_alias=True, exclude={"id"}))

    with pytest.raises(ForbiddenError, match="outside the permitted work area"):
        await enforce_geo_fence(mock_db, actor=user, activity=GeoActivity.LEAD_CREATION, latitude=_OUTSIDE_LAT, longitude=_OUTSIDE_LON)


# ---------------------------------------------------------------------- Temporary Access, same engine


async def test_temporary_access_within_daily_window_ist_boundary():
    """Same daily-window engine (`within_daily_window`) TemporaryAccess shares with
    GeoException, via `PermissionEngine._check_temporary_access` — proven at the shared
    unit level (already exercised end-to-end for GeoException above); this confirms the
    boundary set the spec asks for explicitly for Temporary Access too."""
    start = end = real_datetime(2026, 8, 17, tzinfo=UTC)
    active_at = real_datetime(2026, 8, 17, 12, 0, tzinfo=_IST)
    expired_at = real_datetime(2026, 8, 17, 18, 1, tzinfo=_IST)
    assert within_daily_window(start, end, "09:00", "18:00", active_at) is True
    assert within_daily_window(start, end, "09:00", "18:00", expired_at) is False


# ---------------------------------------------------------------------- Dashboard "today"


async def test_dashboard_today_leads_uses_ist_calendar_day_not_utc(freeze_utc):
    # Freeze "now" at 2026-08-17 19:00 UTC == 2026-08-18 00:30 IST — just after IST
    # midnight, so the IST calendar day (18th) differs from the UTC calendar day (17th).
    freeze_utc(real_datetime(2026, 8, 17, 19, 0, tzinfo=UTC))
    db = AsyncMongoMockClient(tz_aware=True)["test_tz_dashboard_today"]
    owner = User(mobile="9000000001", role=OWNER)
    owner.id = str(ObjectId())

    # 2026-08-17 18:50 UTC == 2026-08-18 00:20 IST — "today" in IST (the 18th), even
    # though it's still "yesterday" (the 17th) in UTC. Must be counted.
    recent = real_datetime(2026, 8, 17, 18, 50, tzinfo=UTC)
    await db["leads"].insert_one({"is_deleted": False, "created_at": recent})
    # 2026-08-17 10:00 UTC == 2026-08-17 15:30 IST — genuinely "yesterday" in IST. Must
    # NOT be counted (the old UTC-midnight logic would have wrongly included this one,
    # since it's still "today" — the 17th — by UTC's own calendar).
    yesterday_ist = real_datetime(2026, 8, 17, 10, 0, tzinfo=UTC)
    await db["leads"].insert_one({"is_deleted": False, "created_at": yesterday_ist})

    result = await WIDGET_PROVIDERS["today_leads"](db, owner)
    assert result["value"] == 1


async def test_dashboard_revenue_trend_buckets_by_ist_month_not_utc(freeze_utc):
    """Regression lock for a real bug this fix introduced and caught before merge: the
    `now_ist` import was initially missing from widget_providers.py, which `ruff`'s F821
    caught statically but no existing test exercised this widget at all — zero coverage
    let it slip past the full pytest run. Also proves the actual fix: a record whose UTC
    month differs from its IST month must bucket into the IST one."""
    freeze_utc(real_datetime(2026, 8, 17, 12, 0, tzinfo=UTC))
    db = AsyncMongoMockClient(tz_aware=True)["test_tz_revenue_trend"]
    owner = User(mobile="9000000001", role=OWNER)
    owner.id = str(ObjectId())

    # 2026-07-31 19:00 UTC == 2026-08-01 00:30 IST — UTC calendar month is July, IST
    # calendar month is August. Must land in the "2026-08" bucket, not "2026-07".
    month_boundary_crossing = real_datetime(2026, 7, 31, 19, 0, tzinfo=UTC)
    await db["application_workflows"].insert_one(
        {
            "is_deleted": False, "case_type": "loan", "current_status": "disbursed",
            "updated_at": month_boundary_crossing, "loan_details": {"offered_amount": 50_000},
        }
    )

    result = await WIDGET_PROVIDERS["revenue_trend_chart"](db, owner)
    by_label = {item["label"]: item["value"] for item in result["items"]}
    assert by_label["2026-08"] == 50_000
    assert by_label["2026-07"] == 0


# ---------------------------------------------------------------------- token/OTP expiry unaffected


def test_jwt_expiry_stays_duration_based_and_unaffected_by_ist():
    """Regression guard for the plan's own explicit constraint: token expiry must stay
    mathematically correct and timezone-independent — this touched nothing in
    app/security/jwt.py, confirmed by an end-to-end encode/decode round trip."""
    token = create_access_token("test-subject")
    payload = decode_token(token, TokenType.ACCESS)
    assert payload["sub"] == "test-subject"
    # exp - iat must equal the configured duration exactly, regardless of what
    # timezone/business-clock logic exists elsewhere in the app.
    from app.config.security import get_security_policy

    policy = get_security_policy()
    assert payload["exp"] - payload["iat"] == policy.access_token_expire_minutes * 60
