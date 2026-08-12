"""Module 6D — Reminder & Notification Engine business logic.

Internal database notifications only — no WhatsApp/SMS/Email/push/external API this
round (explicit instruction); `app/features/notification_management/` stays reserved.
Reuses, read-only: Module 2's `EmployeeRepository` (resolving an assignee's `user_id` to
notify), Module 6C's `ApplicationWorkflowRepository`/`ApplicationStatusHistoryRepository`
(read-only, for the re-eligibility scan — see `app/worker/tasks/reminders.py`, which is
where the actual scheduled scanning lives; this service only covers the synchronous,
request-driven half: Task/ReminderRule CRUD and each user's own Notification inbox).
"""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.constants.roles import EMPLOYEE
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.employee.repository import EmployeeRepository
from app.features.reminders.constants import (
    CATEGORY_BY_NOTIFICATION_TYPE,
    AuditEvent,
    NotificationType,
)
from app.features.reminders.models import Notification, ReminderRule, Task
from app.features.reminders.repository import (
    NotificationRepository,
    ReminderRuleRepository,
    TaskRepository,
)
from app.features.reminders.schemas import (
    CreateReminderRuleRequest,
    CreateTaskRequest,
    UpdateReminderRuleRequest,
    UpdateTaskRequest,
)
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now

_NO_ASSIGNMENT_SENTINEL = "___none___"


class RemindersService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self._db = db
        self._tasks = TaskRepository(db)
        self._rules = ReminderRuleRepository(db)
        self._notifications = NotificationRepository(db)
        self._employees = EmployeeRepository(db)

    async def _acting_employee_id(self, actor: User) -> str | None:
        if actor.role != EMPLOYEE:
            return None
        employee = await self._employees.find_by_user_id(actor.require_id())
        return employee.require_id() if employee else _NO_ASSIGNMENT_SENTINEL

    # ================================================================== notifications (internal helper)

    async def create_notification(
        self, *, recipient_user_id: str, notification_type: str, title: str, message: str, entity_type: str | None = None, entity_id: str | None = None
    ) -> Notification:
        notification = Notification(
            recipient_user_id=recipient_user_id, notification_type=notification_type,
            category=CATEGORY_BY_NOTIFICATION_TYPE[notification_type], title=title, message=message,
            entity_type=entity_type, entity_id=entity_id,
        )
        notification_id = await self._notifications.insert(notification)
        await write_audit_log(
            self._db, event_type=AuditEvent.NOTIFICATION_CREATED, user_id=recipient_user_id,
            metadata={"notification_type": notification_type, "entity_type": entity_type, "entity_id": entity_id},
        )
        found = await self._notifications.find_by_id(notification_id)
        assert found is not None
        return found

    # ================================================================== tasks

    async def create_task(self, payload: CreateTaskRequest, actor: User) -> Task:
        employee = await self._employees.find_by_id(payload.assigned_to)
        if employee is None:
            raise ValidationError("Unknown assigned_to employee_id.")
        task = Task(
            title=payload.title, description=payload.description, assigned_to=payload.assigned_to,
            assigned_by=actor.require_id(), due_at=payload.due_at, created_by=actor.require_id(),
        )
        task_id = await self._tasks.insert(task)
        await write_audit_log(self._db, event_type=AuditEvent.TASK_CREATED, user_id=actor.require_id(), metadata={"task_id": task_id, "assigned_to": payload.assigned_to})

        await self.create_notification(
            recipient_user_id=employee.user_id, notification_type=NotificationType.TASK_ASSIGNED,
            title="New Task Assigned", message=f'You have been assigned a new task: "{payload.title}".',
            entity_type="task", entity_id=task_id,
        )

        found = await self._tasks.find_by_id(task_id)
        assert found is not None
        return found

    async def get_task(self, task_id: str, actor: User) -> Task:
        task = await self._tasks.find_by_id(task_id)
        if task is None:
            raise NotFoundError("Task not found.")
        if actor.role == EMPLOYEE:
            employee_id = await self._acting_employee_id(actor)
            if task.assigned_to != employee_id:
                raise ForbiddenError("This task isn't assigned to you.")
        return task

    async def list_tasks(
        self, actor: User, *, status: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None
    ) -> tuple[list[Task], int]:
        assigned_to = None
        if actor.role == EMPLOYEE:
            assigned_to = await self._acting_employee_id(actor)
        return await self._tasks.search_and_filter(assigned_to=assigned_to, status=status, skip=skip, limit=limit, sort=sort)

    async def update_task(self, task_id: str, payload: UpdateTaskRequest, actor: User) -> Task:
        # `get_task` (not a bare `find_by_id`) so this matches `complete_task`'s own
        # ownership check below — an Employee could otherwise rewrite the title/
        # description/due date of any task company-wide, including support-request tasks
        # whose description embeds a customer's verbatim message.
        await self.get_task(task_id, actor)
        updates = payload.model_dump(exclude_unset=True)
        updated = await self._tasks.update(task_id, updates, updated_by=actor.require_id()) if updates else await self._tasks.find_by_id(task_id)
        if updated is None:
            raise NotFoundError("Task not found.")
        await write_audit_log(self._db, event_type=AuditEvent.TASK_UPDATED, user_id=actor.require_id(), metadata={"task_id": task_id})
        return updated

    async def complete_task(self, task_id: str, actor: User) -> Task:
        await self.get_task(task_id, actor)
        updated = await self._tasks.update(task_id, {"status": "completed", "completed_at": utc_now()}, updated_by=actor.require_id())
        if updated is None:
            raise NotFoundError("Task not found.")
        await write_audit_log(self._db, event_type=AuditEvent.TASK_COMPLETED, user_id=actor.require_id(), metadata={"task_id": task_id})
        return updated

    async def resolve_task_names(self, tasks: list[Task]) -> dict[str, str]:
        employee_ids = {t.assigned_to for t in tasks}
        if not employee_ids:
            return {}
        employees = await self._employees.find_many({}, limit=1000)
        return {e.require_id(): e.display_name for e in employees if e.require_id() in employee_ids}

    # ================================================================== reminder rules

    async def create_reminder_rule(self, payload: CreateReminderRuleRequest, actor: User) -> ReminderRule:
        rule = ReminderRule(**payload.model_dump(), created_by=actor.require_id())
        rule_id = await self._rules.insert(rule)
        await write_audit_log(self._db, event_type=AuditEvent.REMINDER_RULE_CREATED, user_id=actor.require_id(), metadata={"rule_id": rule_id})
        found = await self._rules.find_by_id(rule_id)
        assert found is not None
        return found

    async def list_reminder_rules(self) -> list[ReminderRule]:
        return await self._rules.find_many({}, limit=200, sort=[("rule_type", 1), ("created_at", 1)])

    async def get_reminder_rule(self, rule_id: str) -> ReminderRule:
        rule = await self._rules.find_by_id(rule_id)
        if rule is None:
            raise NotFoundError("Reminder rule not found.")
        return rule

    async def update_reminder_rule(self, rule_id: str, payload: UpdateReminderRuleRequest, actor: User) -> ReminderRule:
        updates = payload.model_dump(exclude_unset=True)
        updated = await self._rules.update(rule_id, updates, updated_by=actor.require_id()) if updates else await self._rules.find_by_id(rule_id)
        if updated is None:
            raise NotFoundError("Reminder rule not found.")
        await write_audit_log(self._db, event_type=AuditEvent.REMINDER_RULE_UPDATED, user_id=actor.require_id(), metadata={"rule_id": rule_id})
        return updated

    async def set_reminder_rule_active(self, rule_id: str, *, active: bool, actor: User) -> ReminderRule:
        updated = await self._rules.update(rule_id, {"status": "active" if active else "inactive"}, updated_by=actor.require_id())
        if updated is None:
            raise NotFoundError("Reminder rule not found.")
        return updated

    # ================================================================== notifications (self-service)

    async def list_notifications(
        self, actor: User, *, status: str | None, category: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None
    ) -> tuple[list[Notification], int]:
        return await self._notifications.search_and_filter(actor.require_id(), status=status, category=category, skip=skip, limit=limit, sort=sort)

    async def get_unread_count(self, actor: User) -> int:
        return await self._notifications.count_unread(actor.require_id())

    async def _get_own_notification(self, notification_id: str, actor: User) -> Notification:
        notification = await self._notifications.find_by_id(notification_id)
        if notification is None or notification.recipient_user_id != actor.require_id():
            raise NotFoundError("Notification not found.")
        return notification

    async def mark_notification_read(self, notification_id: str, actor: User) -> Notification:
        await self._get_own_notification(notification_id, actor)
        updated = await self._notifications.update(notification_id, {"status": "read", "read_at": utc_now()}, updated_by=actor.require_id())
        assert updated is not None
        return updated

    async def archive_notification(self, notification_id: str, actor: User) -> Notification:
        await self._get_own_notification(notification_id, actor)
        updated = await self._notifications.update(notification_id, {"status": "archived"}, updated_by=actor.require_id())
        assert updated is not None
        return updated

    async def dismiss_notification(self, notification_id: str, actor: User) -> Notification:
        await self._get_own_notification(notification_id, actor)
        updated = await self._notifications.update(notification_id, {"status": "dismissed"}, updated_by=actor.require_id())
        assert updated is not None
        return updated
