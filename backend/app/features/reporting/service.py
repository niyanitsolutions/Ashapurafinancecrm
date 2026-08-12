"""Module 8 — Reporting Framework business logic. `run_report`/`export_report_csv` are
the Report Engine's only two entry points — every report, whether backed by a generic
`report_definitions` row or a `CUSTOM_REPORT_RUNNERS` function (decision 090), is
reached through them, never a bespoke per-report service method.
"""

import csv
import io
from datetime import date
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import NotFoundError
from app.features.auth.models import User
from app.features.reporting.constants import AuditEvent, ReportType
from app.features.reporting.models import ReportDefinition, SavedFilter, ScheduledReport
from app.features.reporting.reports import (
    CUSTOM_REPORT_RUNNERS,
    run_count_report,
    run_list_report,
    run_sum_report,
)
from app.features.reporting.repository import (
    ReportDefinitionRepository,
    SavedFilterRepository,
    ScheduledReportRepository,
)
from app.features.reporting.schemas import (
    CreateSavedFilterRequest,
    CreateScheduledReportRequest,
    ReportResult,
    UpdateScheduledReportRequest,
)
from app.shared.audit_log import write_audit_log


class ReportingService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self._db = db
        self._report_definitions = ReportDefinitionRepository(db)
        self._saved_filters = SavedFilterRepository(db)
        self._scheduled_reports = ScheduledReportRepository(db)

    # ================================================================== Report Engine

    async def list_report_definitions(self) -> list[ReportDefinition]:
        return await self._report_definitions.list_all()

    async def _get_definition(self, report_key: str) -> ReportDefinition:
        definition = await self._report_definitions.find_by_key(report_key)
        if definition is None:
            raise NotFoundError(f"Unknown report '{report_key}'.")
        return definition

    async def run_report(self, report_key: str, *, date_from: date | None, date_to: date | None) -> ReportResult:
        definition = await self._get_definition(report_key)
        if definition.report_type == ReportType.COUNT:
            return await run_count_report(self._db, definition, date_from, date_to)
        if definition.report_type == ReportType.SUM:
            return await run_sum_report(self._db, definition, date_from, date_to)
        if definition.report_type == ReportType.LIST:
            return await run_list_report(self._db, definition, date_from, date_to)
        runner = CUSTOM_REPORT_RUNNERS[report_key]
        return await runner(self._db, date_from, date_to)

    async def export_report_csv(self, report_key: str, *, date_from: date | None, date_to: date | None, actor: User) -> str:
        result = await self.run_report(report_key, date_from=date_from, date_to=date_to)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([c.label for c in result.columns])
        for row in result.rows:
            writer.writerow([row.get(c.key, "") for c in result.columns])
        await write_audit_log(self._db, event_type=AuditEvent.REPORT_EXPORTED, user_id=actor.require_id(), metadata={"report_key": report_key})
        return buffer.getvalue()

    # ================================================================== Saved Filters (self-service)

    async def create_saved_filter(self, payload: CreateSavedFilterRequest, actor: User) -> SavedFilter:
        await self._get_definition(payload.report_key)
        saved_filter = SavedFilter(user_id=actor.require_id(), report_key=payload.report_key, label=payload.label, filters=payload.filters, created_by=actor.require_id())
        filter_id = await self._saved_filters.insert(saved_filter)
        await write_audit_log(self._db, event_type=AuditEvent.SAVED_FILTER_CREATED, user_id=actor.require_id(), metadata={"filter_id": filter_id})
        found = await self._saved_filters.find_by_id(filter_id)
        assert found is not None
        return found

    async def list_own_saved_filters(self, actor: User, *, report_key: str | None) -> list[SavedFilter]:
        return await self._saved_filters.find_for_user(actor.require_id(), report_key=report_key)

    async def delete_saved_filter(self, filter_id: str, actor: User) -> None:
        saved_filter = await self._saved_filters.find_by_id(filter_id)
        if saved_filter is None or saved_filter.user_id != actor.require_id():
            raise NotFoundError("Saved filter not found.")
        await self._saved_filters.soft_delete(filter_id, deleted_by=actor.require_id())
        await write_audit_log(self._db, event_type=AuditEvent.SAVED_FILTER_DELETED, user_id=actor.require_id(), metadata={"filter_id": filter_id})

    # ================================================================== Scheduled Reports (framework only — see models.py)

    async def create_scheduled_report(self, payload: CreateScheduledReportRequest, actor: User) -> ScheduledReport:
        await self._get_definition(payload.report_key)
        scheduled = ScheduledReport(**payload.model_dump(), created_by=actor.require_id())
        scheduled_id = await self._scheduled_reports.insert(scheduled)
        await write_audit_log(self._db, event_type=AuditEvent.SCHEDULED_REPORT_CREATED, user_id=actor.require_id(), metadata={"scheduled_report_id": scheduled_id})
        found = await self._scheduled_reports.find_by_id(scheduled_id)
        assert found is not None
        return found

    async def list_scheduled_reports(self) -> list[ScheduledReport]:
        return await self._scheduled_reports.find_many({}, limit=200, sort=[("created_at", -1)])

    async def get_scheduled_report(self, scheduled_report_id: str) -> ScheduledReport:
        scheduled = await self._scheduled_reports.find_by_id(scheduled_report_id)
        if scheduled is None:
            raise NotFoundError("Scheduled report not found.")
        return scheduled

    async def update_scheduled_report(self, scheduled_report_id: str, payload: UpdateScheduledReportRequest, actor: User) -> ScheduledReport:
        updates = payload.model_dump(exclude_unset=True)
        updated = await self._scheduled_reports.update(scheduled_report_id, updates, updated_by=actor.require_id()) if updates else await self._scheduled_reports.find_by_id(scheduled_report_id)
        if updated is None:
            raise NotFoundError("Scheduled report not found.")
        await write_audit_log(self._db, event_type=AuditEvent.SCHEDULED_REPORT_UPDATED, user_id=actor.require_id(), metadata={"scheduled_report_id": scheduled_report_id})
        return updated

    async def delete_scheduled_report(self, scheduled_report_id: str, actor: User) -> None:
        await self.get_scheduled_report(scheduled_report_id)
        await self._scheduled_reports.soft_delete(scheduled_report_id, deleted_by=actor.require_id())
        await write_audit_log(self._db, event_type=AuditEvent.SCHEDULED_REPORT_DELETED, user_id=actor.require_id(), metadata={"scheduled_report_id": scheduled_report_id})
