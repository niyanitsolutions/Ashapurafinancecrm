"""Half-open business-calendar boundaries; all segment instants are UTC."""

import re
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

from app.core.exceptions import ValidationError
from app.utils.datetime import ensure_utc, ist_date_to_utc_midnight, to_ist


def month_bounds(value: str | None, now: datetime) -> tuple[str, date, date]:
    selected = value if value is not None else to_ist(now).date().isoformat()[:7]
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", selected):
        raise ValidationError("Month must be a valid YYYY-MM value.")
    year, month = map(int, selected.split("-"))
    try:
        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    except ValueError:
        raise ValidationError("Month is outside the supported calendar range.") from None
    return selected, start, end


def day_segments(login: datetime, finish: datetime) -> Iterator[tuple[date, datetime, datetime]]:
    login, finish = ensure_utc(login).astimezone(UTC), ensure_utc(finish).astimezone(UTC)
    if finish <= login:
        return
    day = to_ist(login).date()
    while True:
        start = ist_date_to_utc_midnight(day)
        end = ist_date_to_utc_midnight(day + timedelta(days=1))
        if start >= finish:
            return
        yield day, max(login, start), min(finish, end)
        if end >= finish:
            return
        day += timedelta(days=1)
