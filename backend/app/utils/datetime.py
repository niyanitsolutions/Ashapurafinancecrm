from datetime import UTC, datetime, timedelta


def utc_now() -> datetime:
    return datetime.now(UTC)


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
    midnight (e.g. 22:00-06:00), same known limitation as before extraction."""
    if not (start_date.date() <= now.date() <= end_date.date()):
        return False
    current = now.strftime("%H:%M")
    return start_time <= current <= end_time


def ensure_utc(dt: datetime) -> datetime:
    """Mongo/Motor round-trips a stored datetime as naive (no `tz_aware=True` configured
    on the client) even though every write in this project uses `utc_now()` (tz-aware) —
    a naive value read back is always UTC, since that's the only thing ever written.
    Needed before comparing a value just read from the database against a fresh
    `utc_now()` (see Module 6D's scheduler jobs, `app/worker/tasks/reminders.py`)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
