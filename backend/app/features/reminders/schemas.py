from datetime import datetime

from pydantic import BaseModel


class CreateTaskRequest(BaseModel):
    title: str
    description: str | None = None
    assigned_to: str
    due_at: datetime
    priority: str = "medium"
    related_entity_type: str | None = None
    related_entity_id: str | None = None


class UpdateTaskRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    due_at: datetime | None = None
    priority: str | None = None
    related_entity_type: str | None = None
    related_entity_id: str | None = None


class TaskResponse(BaseModel):
    id: str
    title: str
    description: str | None
    assigned_to: str
    assigned_to_name: str | None
    assigned_by: str
    due_at: datetime
    status: str
    completed_at: datetime | None
    owner_escalated: bool
    priority: str
    related_entity_type: str | None
    related_entity_id: str | None
    created_at: datetime
    updated_at: datetime


class CreateReminderRuleRequest(BaseModel):
    rule_type: str
    label: str
    case_type: str | None = None
    eligible_after_days: int | None = None
    notify_before_days: list[int] | None = None
    notify_before_minutes: list[int] | None = None
    escalation_repeat_minutes: int | None = None
    escalation_max_repeats: int | None = None


class UpdateReminderRuleRequest(BaseModel):
    label: str | None = None
    case_type: str | None = None
    eligible_after_days: int | None = None
    notify_before_days: list[int] | None = None
    notify_before_minutes: list[int] | None = None
    escalation_repeat_minutes: int | None = None
    escalation_max_repeats: int | None = None


class ReminderRuleResponse(BaseModel):
    id: str
    rule_type: str
    label: str
    status: str
    case_type: str | None
    eligible_after_days: int | None
    notify_before_days: list[int] | None
    notify_before_minutes: list[int] | None
    escalation_repeat_minutes: int | None
    escalation_max_repeats: int | None
    created_at: datetime
    updated_at: datetime


class NotificationResponse(BaseModel):
    id: str
    notification_type: str
    category: str
    title: str
    message: str
    entity_type: str | None
    entity_id: str | None
    status: str
    created_at: datetime
    read_at: datetime | None
