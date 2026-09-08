"""Reject → Re-Eligibility scheduling — shared by both case pipelines.

A rejected case can carry a per-case schedule (chosen at rejection time): `3/6/9/12`
calendar months from the rejection instant, a staff-supplied `custom` future date, or
an explicit `no` ("never automatically become Re-Eligible"). The `re_eligible_date` it
computes is consumed by `worker/tasks/reminders.py::auto_transition_re_eligible_cases`,
which flips the case `rejected -> re_eligible` on/after that instant. A `no` schedule
leaves `re_eligible_date` None and is therefore never selected by that worker.

These are pure helpers (validation + date math + copy text). The per-pipeline services
keep their own thin `_apply_re_eligibility_schedule` that does the actual writes
(details update + audit log + `ApplicationNote`) against their own `*_details` field and
audit-event vocabulary — that's what keeps the two behaviour-identical.
"""

from datetime import date
from typing import Any

from app.core.exceptions import ValidationError
from app.features.workflow_engine.constants import ReEligibilityPeriod
from app.utils.datetime import add_calendar_months, ist_date_to_utc_midnight, to_ist, utc_now

# A custom Re-Eligible date more than this far out is almost certainly a typo.
MAX_RE_ELIGIBILITY_MONTHS = 60

_LABELS: dict[str, str] = {
    ReEligibilityPeriod.THREE_MONTHS: "3 Months",
    ReEligibilityPeriod.SIX_MONTHS: "6 Months",
    ReEligibilityPeriod.NINE_MONTHS: "9 Months",
    ReEligibilityPeriod.TWELVE_MONTHS: "12 Months",
    ReEligibilityPeriod.CUSTOM: "Custom",
}


def re_eligibility_note_text(choice: str, re_eligible_date: Any) -> str:
    if choice == ReEligibilityPeriod.NO:
        return "Rejected — Re-Eligibility: No (this case will never automatically become Re-Eligible)."
    label = _LABELS.get(choice, choice)
    return f"Rejected — Re-Eligibility scheduled ({label}); eligible from {to_ist(re_eligible_date).strftime('%d %b %Y')}."


def compute_re_eligible_date(choice: str, custom_date: date | None, now: Any | None = None) -> Any:
    """The UTC instant a rejected case becomes Re-Eligible, or `None` for `no`. Raises
    `ValidationError` for an unknown choice, a missing/past/too-far custom date."""
    now = now or utc_now()
    if choice not in ReEligibilityPeriod.ALL:
        raise ValidationError(f"'{choice}' is not a valid Re-Eligibility option.")
    if choice == ReEligibilityPeriod.NO:
        return None
    if choice == ReEligibilityPeriod.CUSTOM:
        if custom_date is None:
            raise ValidationError("A Re-Eligible date is required when the Re-Eligibility option is 'custom'.")
        computed = ist_date_to_utc_midnight(custom_date)
        if computed <= now:
            raise ValidationError("The custom Re-Eligible date must be in the future.")
        if computed > add_calendar_months(now, MAX_RE_ELIGIBILITY_MONTHS):
            raise ValidationError("The custom Re-Eligible date is too far in the future.")
        return computed
    return add_calendar_months(now, ReEligibilityPeriod.MONTHS_BY_PERIOD[choice])


def re_eligibility_detail_updates(choice: str, re_eligible_date: Any, actor_id: str, now: Any) -> dict[str, Any]:
    """The fields to merge into a case's `*_details` block when a schedule is recorded."""
    return {
        "re_eligibility_choice": choice,
        "re_eligible_date": re_eligible_date,
        "re_eligibility_scheduled_at": now,
        "re_eligibility_scheduled_by": actor_id,
        "re_eligibility_auto_transitioned": False,
    }
