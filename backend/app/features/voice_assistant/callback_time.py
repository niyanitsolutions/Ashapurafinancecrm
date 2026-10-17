"""Conservative English date preview. A preview never schedules or authorizes a call."""

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.exceptions import ValidationError
from app.features.voice_assistant.scheduling import local_to_utc

VERSION = "explicit-english-time-v1"


def interpret_time(request: str, timezone: str, now: datetime) -> dict[str, object]:
    local_now = now.astimezone(ZoneInfo(timezone))
    result: dict[str, object] = {
        "interpretation_version": VERSION,
        "reference_at": now,
        "timezone": timezone,
        "requested_local": None,
        "due_at": None,
        "requires_confirmation": True,
        "persisted": False,
        "calls_placed": 0,
    }
    text = re.sub(r"\s+", " ", request.casefold()).strip().rstrip(".! ")
    text = re.sub(r"^(please )?call( me)? ", "", text)
    match = re.fullmatch(
        r"(?P<day>today|tomorrow|next (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|\d{4}-\d{2}-\d{2})"
        r"(?: at (?P<time>\d{1,2}(?::\d{2})?\s*(?:am|pm)|\d{2}:\d{2}))?",
        text,
    )
    if not match:
        return result | {
            "status": "clarification_required",
            "clarification": "Specify one exact date and time, including AM/PM or 24-hour time. Ranges, after/before, multiple alternatives and other languages need clarification.",
        }
    day_text = match["day"]
    if day_text in {"today", "tomorrow"}:
        day = local_now.date() + timedelta(days=day_text == "tomorrow")
    elif day_text.startswith("next "):
        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        delta = (weekdays.index(day_text[5:]) - local_now.weekday()) % 7 or 7
        day = local_now.date() + timedelta(days=delta)
    else:
        try:
            day = date.fromisoformat(day_text)
        except ValueError:
            return result | {
                "status": "clarification_required",
                "clarification": "That calendar date is invalid. Confirm a valid future date.",
            }
    result["interpreted_date"] = day.isoformat()
    if not match["time"]:
        return result | {
            "status": "clarification_required",
            "clarification": "Which exact time on this date, including AM/PM or 24-hour time?",
        }
    raw = match["time"].replace(" ", "")
    try:
        fmt = "%I:%M%p" if ":" in raw else "%I%p"
        time = (
            datetime.strptime(raw, fmt if raw.endswith(("am", "pm")) else "%H:%M")
            .replace(tzinfo=ZoneInfo(timezone))
            .time()
        )
        local = datetime.combine(day, time)
        due = local_to_utc(local, timezone)
    except (ValueError, ValidationError):
        return result | {
            "status": "clarification_required",
            "clarification": "Confirm a valid unambiguous local time. For a daylight-saving overlap select an occurrence in the explicit time form.",
        }
    if not now < due <= now + timedelta(days=366):
        return result | {
            "status": "clarification_required",
            "clarification": "Confirm a future time within the next year; past times are never silently advanced.",
        }
    return result | {
        "status": "proposed",
        "requested_local": local.isoformat(),
        "due_at": due,
        "clarification": "Confirm the interpreted date, time and timezone with the customer before saving and confirming the request.",
    }
