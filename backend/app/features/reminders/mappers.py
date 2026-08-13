from app.features.reminders.models import Notification, ReminderRule, Task
from app.features.reminders.schemas import NotificationResponse, ReminderRuleResponse, TaskResponse


def task_to_response(task: Task, assigned_to_name: str | None) -> TaskResponse:
    return TaskResponse(
        id=task.require_id(), title=task.title, description=task.description, assigned_to=task.assigned_to,
        assigned_to_name=assigned_to_name, assigned_by=task.assigned_by, due_at=task.due_at, status=task.status,
        completed_at=task.completed_at, owner_escalated=task.owner_escalated, priority=task.priority,
        related_entity_type=task.related_entity_type, related_entity_id=task.related_entity_id,
        created_at=task.created_at, updated_at=task.updated_at,
    )


def reminder_rule_to_response(rule: ReminderRule) -> ReminderRuleResponse:
    return ReminderRuleResponse(
        id=rule.require_id(), rule_type=rule.rule_type, label=rule.label, status=rule.status, case_type=rule.case_type,
        eligible_after_days=rule.eligible_after_days, notify_before_days=rule.notify_before_days,
        notify_before_minutes=rule.notify_before_minutes, escalation_repeat_minutes=rule.escalation_repeat_minutes,
        escalation_max_repeats=rule.escalation_max_repeats, created_at=rule.created_at, updated_at=rule.updated_at,
    )


def notification_to_response(notification: Notification) -> NotificationResponse:
    return NotificationResponse(
        id=notification.require_id(), notification_type=notification.notification_type, category=notification.category,
        title=notification.title, message=notification.message, entity_type=notification.entity_type, entity_id=notification.entity_id,
        status=notification.status, created_at=notification.created_at, read_at=notification.read_at,
    )
