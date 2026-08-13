"""Module 6D — Reminder & Notification Engine domain models. Internal database
notifications only — no WhatsApp/SMS/Email/push/external API, per explicit instruction;
`app/features/notification_management/` (external channel delivery) stays reserved and
untouched.
"""

from datetime import datetime

from pydantic import Field

from app.features.reminders.constants import (
    NotificationCategory,
    NotificationStatus,
    NotificationType,
    ReminderRuleType,
    ReminderStatus,
    ReminderTargetType,
    ReminderType,
    TaskPriority,
    TaskStatus,
)
from app.shared.base_document import BaseDocument


class Task(BaseDocument):
    title: str
    description: str | None = None
    assigned_to: str  # ref: employees (Module 2, read-only)
    assigned_by: str  # ref: users — the Owner who created it
    due_at: datetime
    status: str = Field(default=TaskStatus.PENDING, pattern=f"^({'|'.join(TaskStatus.ALL)})$")
    completed_at: datetime | None = None
    # Set once the "still not completed" final escalation has notified the Owner, so
    # that step never repeats for the same task — see ReminderRule.escalation_max_repeats.
    owner_escalated: bool = False
    priority: str = Field(default=TaskPriority.MEDIUM, pattern=f"^({'|'.join(TaskPriority.ALL)})$")
    # Optional link to the record this task is about — same shape and same reasoning as
    # Notification.entity_type/entity_id below (unconstrained string, not an enum), so a
    # future linkable entity type never needs a schema change here.
    related_entity_type: str | None = None  # e.g. "lead" | "customer" | "application"
    related_entity_id: str | None = None


class ReminderRule(BaseDocument):
    """One collection, discriminated by `rule_type` — the *data* half of the Reminder
    Engine; the scheduler jobs in `app/worker/tasks/reminders.py` are generic code that
    reads these rather than hardcoding any timing. `status` (inherited) active/inactive
    lets an Owner turn a rule off without deleting it.

    `notify_before_days`/`notify_before_minutes` are lists, not single values — a rule
    can define multiple trigger points (e.g. 30/15/7/1 days before eligibility), each
    firing its own, independently-tracked reminder. Only one entry is seeded today, but
    adding more later is a data edit (`PATCH /reminder-rules/{id}`), never a code change.
    """

    rule_type: str = Field(pattern=f"^({'|'.join(ReminderRuleType.ALL)})$")
    label: str

    # rule_type == "re_eligibility"
    case_type: str | None = None  # "loan" | "insurance"
    eligible_after_days: int | None = None
    notify_before_days: list[int] | None = None

    # rule_type == "task_due"
    notify_before_minutes: list[int] | None = None
    escalation_repeat_minutes: int | None = None
    escalation_max_repeats: int | None = None


class Reminder(BaseDocument):
    """A scheduled/fired reminder instance — the queue the scheduler jobs work through.
    One row per (rule, target, reminder_type, trigger_offset) prevents firing the same
    reminder twice while still letting a rule's *other* configured trigger points (e.g.
    a case rejected long enough ago to have crossed both its 30-day and 10-day notice
    points) fire independently. `trigger_offset` is the specific days/minutes-before
    value this instance corresponds to — `None` for reminder types that aren't
    multi-trigger (escalations track progress via `repeat_count` instead)."""

    rule_id: str
    reminder_type: str = Field(pattern=f"^({'|'.join(ReminderType.ALL)})$")
    target_type: str = Field(pattern=f"^({'|'.join(ReminderTargetType.ALL)})$")
    target_id: str
    trigger_offset: int | None = None
    fire_at: datetime
    status: str = Field(default=ReminderStatus.PENDING, pattern=f"^({'|'.join(ReminderStatus.ALL)})$")
    fired_at: datetime | None = None
    repeat_count: int = 0


class Notification(BaseDocument):
    recipient_user_id: str  # ref: users
    notification_type: str = Field(pattern=f"^({'|'.join(NotificationType.ALL)})$")
    # Derived automatically from notification_type at creation (RemindersService.
    # create_notification) — never set independently, so it can't drift out of sync.
    category: str = Field(pattern=f"^({'|'.join(NotificationCategory.ALL)})$")
    title: str
    message: str
    entity_type: str | None = None  # e.g. "lead" | "application" | "task" | "loan_case" | "insurance_case"
    entity_id: str | None = None
    status: str = Field(default=NotificationStatus.UNREAD, pattern=f"^({'|'.join(NotificationStatus.ALL)})$")
    read_at: datetime | None = None


class NotificationCheckpoint(BaseDocument):
    """One row per polled audit-log `event_type` (`_id` is NOT the event_type here —
    Mongo's own ObjectId stays the primary key per this project's convention; the event
    type is a separate unique-indexed field), so `poll_audit_events` never rescans the
    whole (unbounded, append-only) `audit_logs` collection on every run."""

    event_type: str
    last_processed_at: datetime
