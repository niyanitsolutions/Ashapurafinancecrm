"""Module 8 — Reporting Framework domain models.

Three collections belong to the framework itself — `ReportDefinition`, `SavedFilter`,
and `ScheduledReport`. Report *results* are never stored; every report is computed live
against its source collections each time it's run (see `reports.py`), the same
"compute on read" posture already used for Referral Partner's external status mapping.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.features.reporting.constants import ReportType, ScheduleFrequency
from app.shared.base_document import BaseDocument


class ReportDefinitionColumn(BaseModel):
    key: str
    label: str


class ReportDefinition(BaseDocument):
    """The Report Engine's catalog — decision 090. For `report_type` `count`/`sum`/
    `list`, every field below fully describes the query; a generic executor in
    `reports.py` runs it, so adding one of these is a new row here, never new Python.
    `report_type="custom"` still needs a matching function in `reports.py:
    CUSTOM_REPORT_RUNNERS` (a handful of reports have logic — joins, reused service
    calls, multi-branch conditionals — that can't be expressed as parameters without a
    much larger query DSL) — but even those rows carry real metadata (label/category/
    columns/description) here, so the catalog listing never needs a code change either.
    """

    key: str  # unique
    label: str
    category: str
    description: str
    report_type: str = Field(pattern=f"^({'|'.join(ReportType.ALL)})$")
    columns: list[ReportDefinitionColumn] = Field(default_factory=list)

    # report_type in (count, sum, list) — generic aggregation parameters only.
    collection: str | None = None
    group_field: str | None = None  # count, sum
    sum_field: str | None = None  # sum
    amount_field: str | None = None  # list — nested under loan_details/insurance_details per extra_match["case_type"]
    date_field: str | None = None
    extra_match: dict[str, Any] = Field(default_factory=dict)
    name_resolution_collection: str | None = None
    name_resolution_field: str | None = None


class SavedFilter(BaseDocument):
    """A user's own named filter preset for a given report — self-service, never
    shared (mirrors Reminders' Notification inbox: strictly per-user, no admin
    oversight view). `filters` is a free-form dict matching whatever query params that
    report's definition accepts (date_from/date_to plus its own optional extra filter)."""

    user_id: str  # ref: users — owner of this preset
    report_key: str
    label: str
    filters: dict[str, Any] = Field(default_factory=dict)


class ScheduledReport(BaseDocument):
    """Framework only — CRUD and storage exist, but nothing reads this collection to
    actually run and distribute a report yet (no Arq job registered). Reserved the same
    way Referral Partner's `parent_partner_id` is reserved (decision 080): the schema
    exists so a future round can wire real execution without a migration, but zero
    business logic depends on it today. See docs/KNOWN_LIMITATIONS.md."""

    report_key: str
    label: str
    filters: dict[str, Any] = Field(default_factory=dict)
    frequency: str = Field(pattern=f"^({'|'.join(ScheduleFrequency.ALL)})$")
    recipient_user_ids: list[str] = Field(default_factory=list)
    is_active: bool = True
    last_run_at: datetime | None = None  # never set by any code yet — see module docstring
