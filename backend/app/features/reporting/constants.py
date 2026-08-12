"""Module 8 — Reporting Framework constants.

Per explicit instruction: build the framework first (Report Engine, Saved Filters,
Export, Date Range, Scheduled Reports as a framework only, Aggregation Layer), then
Business Reports become registry entries on top of it rather than one-off hand-built
screens — the same "engine is code, catalog is data" split used since Access Control's
`PermissionEngine`, 6C's `WorkflowEngine`, 6D's `ReminderRule`, and 7's `CommissionRule`.
"""


class ReportCategory:
    LEAD = "lead"
    LOAN = "loan"
    INSURANCE = "insurance"
    EMPLOYEE = "employee"
    REFERRAL = "referral"
    DASHBOARD = "dashboard"

    ALL = (LEAD, LOAN, INSURANCE, EMPLOYEE, REFERRAL, DASHBOARD)


class ReportType:
    """`count`/`sum`/`list` are pure configuration — a generic executor in `reports.py`
    runs them straight from the `ReportDefinition` row's own fields, no Python needed
    per report. `custom` still needs a matching function in `reports.py:
    CUSTOM_REPORT_RUNNERS` (decision 090)."""

    COUNT = "count"
    SUM = "sum"
    LIST = "list"
    CUSTOM = "custom"

    ALL = (COUNT, SUM, LIST, CUSTOM)


class ScheduleFrequency:
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

    ALL = (DAILY, WEEKLY, MONTHLY)


class AuditEvent:
    SAVED_FILTER_CREATED = "saved_filter_created"
    SAVED_FILTER_DELETED = "saved_filter_deleted"
    SCHEDULED_REPORT_CREATED = "scheduled_report_created"
    SCHEDULED_REPORT_UPDATED = "scheduled_report_updated"
    SCHEDULED_REPORT_DELETED = "scheduled_report_deleted"
    REPORT_EXPORTED = "report_exported"
