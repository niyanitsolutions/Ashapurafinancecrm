"""Timezone calculations shared by campaigns and confirmed callbacks."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.exceptions import ValidationError


def timezone_name(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError):
        raise ValueError("Use a valid IANA timezone.") from None
    return value


def local_to_utc(local: datetime, timezone: str, fold: int | None = None) -> datetime:
    if local.tzinfo is not None:
        raise ValidationError("Supply a local time without an offset and its explicit timezone.")
    zone = ZoneInfo(timezone_name(timezone))
    candidates = {}
    for candidate_fold in (0, 1):
        candidate = local.replace(tzinfo=zone, fold=candidate_fold).astimezone(UTC)
        if candidate.astimezone(zone).replace(tzinfo=None) == local:
            candidates[candidate_fold] = candidate
    if not candidates:
        raise ValidationError(
            "That local time does not exist because of a daylight-saving transition."
        )
    if len(set(candidates.values())) > 1 and fold is None:
        raise ValidationError(
            "That local time is ambiguous. Explicitly choose the first or second occurrence."
        )
    if fold is not None and fold not in (0, 1):
        raise ValidationError("DST occurrence must be 0 or 1.")
    return candidates.get(fold if fold is not None else 0, next(iter(candidates.values())))


def next_window(
    now: datetime, timezone: str, start: str, end: str, holidays: list[str], *, fold: int = 0
) -> datetime:
    zone = ZoneInfo(timezone_name(timezone))
    local = now.astimezone(zone)
    if local.date().isoformat() not in holidays and start <= local.strftime("%H:%M") < end:
        return now
    for offset in range(367):
        day = local.date() + timedelta(days=offset)
        if day.isoformat() in holidays:
            continue
        naive = datetime.fromisoformat(day.isoformat() + "T" + start)
        try:
            candidate = local_to_utc(naive, timezone, fold)
        except ValidationError:
            continue
        if candidate >= now:
            return candidate
    raise ValidationError("No eligible calling window found in the supported year.")
