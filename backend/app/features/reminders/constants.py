"""Module 6D — Reminder & Notification Engine constants.

Per explicit instruction: "Don't hardcode reminder timings. Instead, create Reminder
Rules in the database." `ReminderRule` is one collection, discriminated by `rule_type`,
mirroring the "engine is code, catalog is data" split used since Access Control's
`PermissionEngine`/`Permission` and 6C's `WorkflowEngine`/`WorkflowDefinition`.
"""


class TaskStatus:
    PENDING = "pending"
    COMPLETED = "completed"

    ALL = (PENDING, COMPLETED)


class ReminderRuleType:
    RE_ELIGIBILITY = "re_eligibility"
    TASK_DUE = "task_due"

    ALL = (RE_ELIGIBILITY, TASK_DUE)


class ReminderType:
    RE_ELIGIBILITY = "re_eligibility"
    TASK_DUE = "task_due"
    TASK_ESCALATION = "task_escalation"
    TASK_OWNER_ESCALATION = "task_owner_escalation"

    ALL = (RE_ELIGIBILITY, TASK_DUE, TASK_ESCALATION, TASK_OWNER_ESCALATION)


class ReminderStatus:
    PENDING = "pending"
    FIRED = "fired"

    ALL = (PENDING, FIRED)


class ReminderTargetType:
    LOAN_CASE = "loan_case"
    INSURANCE_CASE = "insurance_case"
    TASK = "task"

    ALL = (LOAN_CASE, INSURANCE_CASE, TASK)


class NotificationType:
    LEAD_ASSIGNED = "lead_assigned"
    DOCUMENT_UPLOADED = "document_uploaded"
    TASK_ASSIGNED = "task_assigned"
    TASK_DUE = "task_due"
    TASK_ESCALATION = "task_escalation"
    TASK_OWNER_ESCALATION = "task_owner_escalation"
    REMINDER_TRIGGERED = "reminder_triggered"
    # Phase 5 (Customer Portal) — a Customer's "Raise a Request" (Support) with no
    # Relationship Manager assigned yet. Falls into the already-reserved `SYSTEM`
    # category (see NotificationCategory's own docstring anticipating exactly this).
    SUPPORT_REQUEST_RAISED = "support_request_raised"

    ALL = (
        LEAD_ASSIGNED, DOCUMENT_UPLOADED, TASK_ASSIGNED, TASK_DUE, TASK_ESCALATION, TASK_OWNER_ESCALATION,
        REMINDER_TRIGGERED, SUPPORT_REQUEST_RAISED,
    )


class NotificationCategory:
    """Coarser grouping than `NotificationType`, so a user can filter their inbox
    without knowing every specific type — e.g. "show me everything Task-related."
    `WORKFLOW`/`SYSTEM`/`SECURITY` have no producer yet in this module (no current
    `NotificationType` maps to them) but are reserved now so a future notification type
    (e.g. a Loan/Insurance Case status change, or a password-changed notice) can be
    added without another schema change — the category taxonomy is already complete.
    """

    ASSIGNMENT = "assignment"
    REMINDER = "reminder"
    TASK = "task"
    WORKFLOW = "workflow"
    DOCUMENT = "document"
    SYSTEM = "system"
    SECURITY = "security"

    ALL = (ASSIGNMENT, REMINDER, TASK, WORKFLOW, DOCUMENT, SYSTEM, SECURITY)


# Every NotificationType maps to exactly one category — derived automatically at
# creation (RemindersService.create_notification), never chosen by the caller, so a
# type can never drift to a different category on different calls.
CATEGORY_BY_NOTIFICATION_TYPE: dict[str, str] = {
    NotificationType.LEAD_ASSIGNED: NotificationCategory.ASSIGNMENT,
    NotificationType.TASK_ASSIGNED: NotificationCategory.ASSIGNMENT,
    NotificationType.DOCUMENT_UPLOADED: NotificationCategory.DOCUMENT,
    NotificationType.TASK_DUE: NotificationCategory.TASK,
    NotificationType.TASK_ESCALATION: NotificationCategory.TASK,
    NotificationType.TASK_OWNER_ESCALATION: NotificationCategory.TASK,
    NotificationType.REMINDER_TRIGGERED: NotificationCategory.REMINDER,
    NotificationType.SUPPORT_REQUEST_RAISED: NotificationCategory.SYSTEM,
}


class NotificationStatus:
    UNREAD = "unread"
    READ = "read"
    ARCHIVED = "archived"
    DISMISSED = "dismissed"

    ALL = (UNREAD, READ, ARCHIVED, DISMISSED)


class AuditEvent:
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    TASK_COMPLETED = "task_completed"
    REMINDER_RULE_CREATED = "reminder_rule_created"
    REMINDER_RULE_UPDATED = "reminder_rule_updated"
    NOTIFICATION_CREATED = "notification_created"


# Audit-log event types (written by frozen modules, never modified) this module polls
# to generate notifications — see docs/decisions/DECISIONS.md for why polling rather
# than a live event hook.
POLLED_AUDIT_EVENT_TYPES = ("lead_assigned", "document_uploaded")
