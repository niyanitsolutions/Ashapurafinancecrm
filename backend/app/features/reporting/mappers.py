from app.features.reporting.models import ReportDefinition, SavedFilter, ScheduledReport
from app.features.reporting.schemas import (
    ReportDefinitionResponse,
    SavedFilterResponse,
    ScheduledReportResponse,
)


def definition_to_response(definition: ReportDefinition) -> ReportDefinitionResponse:
    return ReportDefinitionResponse(key=definition.key, label=definition.label, category=definition.category, description=definition.description)


def saved_filter_to_response(saved_filter: SavedFilter) -> SavedFilterResponse:
    return SavedFilterResponse(
        id=saved_filter.require_id(), report_key=saved_filter.report_key, label=saved_filter.label, filters=saved_filter.filters,
        created_at=saved_filter.created_at,
    )


def scheduled_report_to_response(scheduled_report: ScheduledReport) -> ScheduledReportResponse:
    return ScheduledReportResponse(
        id=scheduled_report.require_id(), report_key=scheduled_report.report_key, label=scheduled_report.label, filters=scheduled_report.filters,
        frequency=scheduled_report.frequency, recipient_user_ids=scheduled_report.recipient_user_ids, is_active=scheduled_report.is_active,
        last_run_at=scheduled_report.last_run_at, created_at=scheduled_report.created_at, updated_at=scheduled_report.updated_at,
    )
