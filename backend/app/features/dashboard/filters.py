"""Dashboard-only filtering primitives.

Dates selected in the UI are business-calendar dates.  We turn them into UTC bounds
once, at the API boundary, so every dashboard aggregation uses the same inclusive
range without changing any workflow data or access rule.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.core.exceptions import ValidationError
from app.utils.datetime import add_calendar_months, ist_date_range_to_utc_bounds, now_ist, to_ist

DATE_RANGES = {
    "this_week", "last_week", "this_month", "last_month", "last_3_months", "last_6_months", "last_1_year", "custom",
}


@dataclass(frozen=True)
class DashboardFilters:
    start: datetime
    end: datetime
    date_range: str
    product_category: str | None = None
    source_id: str | None = None


def resolve_dashboard_filters(
    *, date_range: str, start_date: date | None, end_date: date | None, product_category: str | None, source_id: str | None,
) -> DashboardFilters:
    if date_range not in DATE_RANGES:
        raise ValidationError("Unsupported dashboard date range.")
    if product_category not in (None, "loan", "insurance"):
        raise ValidationError("product_category must be 'loan' or 'insurance'.")

    now = now_ist()
    today = now.date()
    if date_range == "custom":
        if start_date is None or end_date is None:
            raise ValidationError("Custom date range requires both start_date and end_date.")
        if start_date > end_date:
            raise ValidationError("Start date cannot be after end date.")
        if end_date == date.max:
            raise ValidationError("End date must be before 9999-12-31.")
        lower, upper = ist_date_range_to_utc_bounds(start_date, end_date)
    else:
        if date_range == "this_week":
            start_date, end_date = today - timedelta(days=today.weekday()), today
        elif date_range == "last_week":
            end_date = today - timedelta(days=today.weekday() + 1)
            start_date = end_date - timedelta(days=6)
        elif date_range == "this_month":
            start_date, end_date = today.replace(day=1), today
        elif date_range == "last_month":
            end_date = today.replace(day=1) - timedelta(days=1)
            start_date = end_date.replace(day=1)
        else:
            months = {"last_3_months": 3, "last_6_months": 6, "last_1_year": 12}[date_range]
            start_date, end_date = to_ist(add_calendar_months(now, -months)).date(), today
        lower, upper = ist_date_range_to_utc_bounds(start_date, end_date)
    assert lower is not None and upper is not None
    return DashboardFilters(lower, upper, date_range, product_category, source_id)
