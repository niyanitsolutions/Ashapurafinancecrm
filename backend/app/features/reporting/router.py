"""Module 8 — Reporting Framework routes. Running/exporting a report is
`require_permission("reporting", "reports", "view"|"export")` — delegable, matching the
majority pattern (unlike Module 7, this brief doesn't restrict reports to Owner only).
Saved Filters are self-service (each user's own presets, like Reminders' Notification
inbox). Scheduled Reports (CRUD only — no execution, see models.py) are
`require_permission("reporting", "scheduled_reports", ...)`.
"""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response

from app.core.response import ApiResponse
from app.features.access_control.permission_engine import require_permission
from app.features.auth.models import User
from app.features.reporting import mappers
from app.features.reporting.dependencies import CurrentUserDep, StaffDep, get_reporting_service
from app.features.reporting.schemas import (
    CreateSavedFilterRequest,
    CreateScheduledReportRequest,
    ReportDefinitionResponse,
    ReportResult,
    SavedFilterResponse,
    ScheduledReportResponse,
    UpdateScheduledReportRequest,
)
from app.features.reporting.service import ReportingService

router = APIRouter(tags=["reporting"])

ServiceDep = Annotated[ReportingService, Depends(get_reporting_service)]
_MODULE = "reporting"


def _perm(resource: str, action: str) -> Any:
    return require_permission(_MODULE, resource, action)


# ---------------------------------------------------------------------- report engine


@router.get("/reports")
async def list_reports(service: ServiceDep, _actor: Annotated[User, _perm("reports", "view")]) -> ApiResponse[list[ReportDefinitionResponse]]:
    items = [mappers.definition_to_response(d) for d in await service.list_report_definitions()]
    return ApiResponse[list[ReportDefinitionResponse]].ok(items)


@router.get("/reports/{report_key}")
async def run_report(
    report_key: str, service: ServiceDep, _actor: Annotated[User, _perm("reports", "view")], date_from: date | None = None, date_to: date | None = None
) -> ApiResponse[ReportResult]:
    result = await service.run_report(report_key, date_from=date_from, date_to=date_to)
    return ApiResponse[ReportResult].ok(result)


@router.get("/reports/{report_key}/export")
async def export_report(
    report_key: str, service: ServiceDep, actor: Annotated[User, _perm("reports", "export")], date_from: date | None = None, date_to: date | None = None
) -> Response:
    csv_content = await service.export_report_csv(report_key, date_from=date_from, date_to=date_to, actor=actor)
    return Response(content=csv_content, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={report_key}.csv"})


# ---------------------------------------------------------------------- saved filters (self-service)


@router.post("/saved-filters")
async def create_saved_filter(
    payload: CreateSavedFilterRequest, service: ServiceDep, current_user: CurrentUserDep, _staff: StaffDep
) -> ApiResponse[SavedFilterResponse]:
    saved_filter = await service.create_saved_filter(payload, current_user)
    return ApiResponse[SavedFilterResponse].ok(mappers.saved_filter_to_response(saved_filter))


@router.get("/saved-filters")
async def list_saved_filters(
    service: ServiceDep, current_user: CurrentUserDep, _staff: StaffDep, report_key: str | None = None
) -> ApiResponse[list[SavedFilterResponse]]:
    saved_filters = await service.list_own_saved_filters(current_user, report_key=report_key)
    return ApiResponse[list[SavedFilterResponse]].ok([mappers.saved_filter_to_response(f) for f in saved_filters])


@router.delete("/saved-filters/{filter_id}")
async def delete_saved_filter(filter_id: str, service: ServiceDep, current_user: CurrentUserDep, _staff: StaffDep) -> ApiResponse[None]:
    await service.delete_saved_filter(filter_id, current_user)
    return ApiResponse[None].ok(None)


# ---------------------------------------------------------------------- scheduled reports (framework only)


@router.post("/scheduled-reports")
async def create_scheduled_report(
    payload: CreateScheduledReportRequest, service: ServiceDep, actor: Annotated[User, _perm("scheduled_reports", "create")]
) -> ApiResponse[ScheduledReportResponse]:
    scheduled = await service.create_scheduled_report(payload, actor)
    return ApiResponse[ScheduledReportResponse].ok(mappers.scheduled_report_to_response(scheduled))


@router.get("/scheduled-reports")
async def list_scheduled_reports(service: ServiceDep, _actor: Annotated[User, _perm("scheduled_reports", "view")]) -> ApiResponse[list[ScheduledReportResponse]]:
    scheduled_reports = await service.list_scheduled_reports()
    return ApiResponse[list[ScheduledReportResponse]].ok([mappers.scheduled_report_to_response(s) for s in scheduled_reports])


@router.get("/scheduled-reports/{scheduled_report_id}")
async def get_scheduled_report(
    scheduled_report_id: str, service: ServiceDep, _actor: Annotated[User, _perm("scheduled_reports", "view")]
) -> ApiResponse[ScheduledReportResponse]:
    scheduled = await service.get_scheduled_report(scheduled_report_id)
    return ApiResponse[ScheduledReportResponse].ok(mappers.scheduled_report_to_response(scheduled))


@router.patch("/scheduled-reports/{scheduled_report_id}")
async def update_scheduled_report(
    scheduled_report_id: str, payload: UpdateScheduledReportRequest, service: ServiceDep, actor: Annotated[User, _perm("scheduled_reports", "edit")]
) -> ApiResponse[ScheduledReportResponse]:
    scheduled = await service.update_scheduled_report(scheduled_report_id, payload, actor)
    return ApiResponse[ScheduledReportResponse].ok(mappers.scheduled_report_to_response(scheduled))


@router.delete("/scheduled-reports/{scheduled_report_id}")
async def delete_scheduled_report(scheduled_report_id: str, service: ServiceDep, actor: Annotated[User, _perm("scheduled_reports", "delete")]) -> ApiResponse[None]:
    await service.delete_scheduled_report(scheduled_report_id, actor)
    return ApiResponse[None].ok(None)
