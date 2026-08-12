from datetime import UTC, datetime, timedelta


def utc_now() -> datetime:
    return datetime.now(UTC)


def add_days(dt: datetime, days: int) -> datetime:
    return dt + timedelta(days=days)


def is_expired(expires_at: datetime) -> bool:
    return utc_now() >= expires_at


def ensure_utc(dt: datetime) -> datetime:
    """Mongo/Motor round-trips a stored datetime as naive (no `tz_aware=True` configured
    on the client) even though every write in this project uses `utc_now()` (tz-aware) —
    a naive value read back is always UTC, since that's the only thing ever written.
    Needed before comparing a value just read from the database against a fresh
    `utc_now()` (see Module 6D's scheduler jobs, `app/worker/tasks/reminders.py`)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
