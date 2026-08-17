from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from app.config.settings import get_settings


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(dt: datetime) -> datetime:
    """Mongo/Motor round-trips a stored datetime as naive (no `tz_aware=True` configured
    on the client) even though every write in this project uses `utc_now()` (tz-aware) —
    a naive value read back is always UTC, since that's the only thing ever written.
    Needed before comparing a value just read from the database against a fresh
    `utc_now()` (see Module 6D's scheduler jobs, `app/worker/tasks/reminders.py`)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


# ---------------------------------------------------------------------- business timezone (IST)
#
# UTC remains the canonical storage/machine-timestamp convention everywhere (JWT `exp`,
# Redis TTLs, `BaseDocument.created_at`/`updated_at`, audit logs) — see docs/TIMEZONE.md.
# These helpers exist for the other half: any calculation that means something to a
# *business user* — "today", "this month", a Geo Fence's daily 09:00-18:00 window, a
# report's date range — must be evaluated against the business calendar/clock
# (`Settings.timezone`, "Asia/Kolkata" by default), not UTC wall-clock. Route every such
# calculation through these functions rather than a fresh `ZoneInfo(...)`/manual offset.


@lru_cache
def _business_zone() -> ZoneInfo:
    """`ZoneInfo` is itself internally cached by the stdlib per key, but this wrapper
    means the configured zone name (`Settings.timezone`) is read from one place, not
    re-typed as a literal string anywhere else in the codebase."""
    return ZoneInfo(get_settings().timezone)


def now_ist() -> datetime:
    """"Now", in the app's configured business timezone. The only correct "now" for a
    business-day/business-hour comparison — never `utc_now()` for those."""
    return datetime.now(_business_zone())


def to_ist(dt: datetime) -> datetime:
    """Converts any datetime (naive values are assumed UTC, matching this app's own
    storage convention — see `ensure_utc`) to the business timezone."""
    return ensure_utc(dt).astimezone(_business_zone())


def start_of_day_ist(dt: datetime | None = None) -> datetime:
    """The UTC instant corresponding to business-timezone midnight of `dt`'s calendar
    date (or today's, if `dt` is omitted) — the correct lower bound for a "today"/
    business-day Mongo query, since stored timestamps are compared in UTC."""
    ist_now = to_ist(dt) if dt is not None else now_ist()
    ist_midnight = ist_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return ist_midnight.astimezone(UTC)


def end_of_day_ist(dt: datetime | None = None) -> datetime:
    """Exclusive upper bound: business-timezone midnight of the *next* calendar date,
    converted to UTC."""
    return start_of_day_ist(dt) + timedelta(days=1)


def start_of_month_ist(dt: datetime | None = None) -> datetime:
    """The UTC instant corresponding to business-timezone midnight on the 1st of `dt`'s
    calendar month (or the current one, if `dt` is omitted)."""
    ist_now = to_ist(dt) if dt is not None else now_ist()
    ist_month_start = ist_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return ist_month_start.astimezone(UTC)


def ist_month_start_utc(year: int, month: int) -> datetime:
    """The UTC instant corresponding to business-timezone midnight on the 1st of the
    given (arbitrary, not necessarily current) calendar year/month — for building a
    rolling N-month range (see dashboard `_revenue_trend_chart`)."""
    return datetime(year, month, 1, tzinfo=_business_zone()).astimezone(UTC)


def ist_date_range_to_utc_bounds(date_from: date | None, date_to: date | None) -> tuple[datetime | None, datetime | None]:
    """Turns two business-calendar dates (as picked by a user in a report/date filter)
    into ($gte, $lt) UTC instant bounds for a Mongo query. `date_to` is inclusive of its
    entire business-timezone day, exclusive of the following one."""
    zone = _business_zone()
    lower = datetime(date_from.year, date_from.month, date_from.day, tzinfo=zone).astimezone(UTC) if date_from is not None else None
    upper = (
        (datetime(date_to.year, date_to.month, date_to.day, tzinfo=zone) + timedelta(days=1)).astimezone(UTC)
        if date_to is not None
        else None
    )
    return lower, upper


def add_days(dt: datetime, days: int) -> datetime:
    return dt + timedelta(days=days)


def is_expired(expires_at: datetime) -> bool:
    return utc_now() >= expires_at


def within_daily_window(start_date: datetime, end_date: datetime, start_time: str, end_time: str, now: datetime) -> bool:
    """A *daily recurring* window (date range x a "HH:MM"-"HH:MM" band repeated every day
    in that range), not one continuous start-to-end span — see decision 022 in
    docs/decisions/DECISIONS.md. Originally private to access_control's PermissionEngine
    (`_within_daily_window`); extracted here, unchanged, so geo_fencing's own enforcement
    engine can reuse the exact same evaluation instead of duplicating it. Business-hours
    style windows only — string comparison of "HH:MM" can't express a window crossing
    midnight (e.g. 22:00-06:00), same known limitation as before extraction.

    `now` must already be converted to the business timezone (pass `now_ist()`, not
    `utc_now()`) — this function does no timezone conversion of its own, it purely
    compares whatever calendar date/wall-clock time `now` carries against the stored
    date range and "HH:MM" band. `start_date`/`end_date` only ever carry Y-M-D
    components (see access_control/service.py's `_date_to_datetime`), so their own
    `tzinfo` tag doesn't affect this comparison."""
    if not (start_date.date() <= now.date() <= end_date.date()):
        return False
    current = now.strftime("%H:%M")
    return start_time <= current <= end_time
