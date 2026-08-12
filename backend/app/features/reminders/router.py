"""Module 6D — Reminder & Notification Engine routes. Tasks and Reminder Rules are
gated by `require_permission("reminders", resource, action)` (Access Control) — no new
authorization mechanism, consistent with 6C's decision 059. Notifications are
self-service (each user reads only their own inbox), gated by a plain `require_staff`
role check, the same posture 6B/6C used for their own self-service endpoints.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.core.pagination import PageParams, page_params
from app.core.response import ApiResponse, ResponseMeta
from app.features.access_control.permission_engine import require_permission
from app.features.auth.models import User
from app.features.reminders import mappers
from app.features.reminders.dependencies import CurrentUserDep, StaffDep, get_reminders_service
from app.features.reminders.schemas import (
    CreateReminderRuleRequest,
    CreateTaskRequest,
    NotificationResponse,
    ReminderRuleResponse,
    TaskResponse,
    UpdateReminderRuleRequest,
    UpdateTaskRequest,
)
from app.features.reminders.service import RemindersService

router = APIRouter(tags=["reminders"])

ServiceDep = Annotated[RemindersService, Depends(get_reminders_service)]
PageParamsDep = Annotated[PageParams, Depends(page_params)]
_MODULE = "reminders"


def _perm(resource: str, action: str) -> Any:
    return require_permission(_MODULE, resource, action)


# ---------------------------------------------------------------------- tasks


@router.post("/tasks")
async def create_task(payload: CreateTaskRequest, service: ServiceDep, actor: Annotated[User, _perm("tasks", "create")]) -> ApiResponse[TaskResponse]:
    task = await service.create_task(payload, actor)
    names = await service.resolve_task_names([task])
    return ApiResponse[TaskResponse].ok(mappers.task_to_response(task, names.get(task.assigned_to)))


@router.get("/tasks")
async def list_tasks(
    service: ServiceDep, actor: Annotated[User, _perm("tasks", "view")], page: PageParamsDep, status: str | None = None
) -> ApiResponse[list[TaskResponse]]:
    tasks, total = await service.list_tasks(actor, status=status, skip=page.skip, limit=page.page_size, sort=page.sort)
    names = await service.resolve_task_names(tasks)
    items = [mappers.task_to_response(t, names.get(t.assigned_to)) for t in tasks]
    return ApiResponse[list[TaskResponse]].ok(items, meta=ResponseMeta(pagination=page.build_meta(total)))


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, service: ServiceDep, actor: Annotated[User, _perm("tasks", "view")]) -> ApiResponse[TaskResponse]:
    task = await service.get_task(task_id, actor)
    names = await service.resolve_task_names([task])
    return ApiResponse[TaskResponse].ok(mappers.task_to_response(task, names.get(task.assigned_to)))


@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: str, payload: UpdateTaskRequest, service: ServiceDep, actor: Annotated[User, _perm("tasks", "edit")]
) -> ApiResponse[TaskResponse]:
    task = await service.update_task(task_id, payload, actor)
    names = await service.resolve_task_names([task])
    return ApiResponse[TaskResponse].ok(mappers.task_to_response(task, names.get(task.assigned_to)))


@router.post("/tasks/{task_id}/complete")
async def complete_task(task_id: str, service: ServiceDep, current_user: CurrentUserDep, _staff: StaffDep) -> ApiResponse[TaskResponse]:
    task = await service.complete_task(task_id, current_user)
    names = await service.resolve_task_names([task])
    return ApiResponse[TaskResponse].ok(mappers.task_to_response(task, names.get(task.assigned_to)))


# ---------------------------------------------------------------------- reminder rules


@router.post("/reminder-rules")
async def create_reminder_rule(
    payload: CreateReminderRuleRequest, service: ServiceDep, actor: Annotated[User, _perm("reminder_rules", "create")]
) -> ApiResponse[ReminderRuleResponse]:
    rule = await service.create_reminder_rule(payload, actor)
    return ApiResponse[ReminderRuleResponse].ok(mappers.reminder_rule_to_response(rule))


@router.get("/reminder-rules")
async def list_reminder_rules(service: ServiceDep, _actor: Annotated[User, _perm("reminder_rules", "view")]) -> ApiResponse[list[ReminderRuleResponse]]:
    rules = await service.list_reminder_rules()
    return ApiResponse[list[ReminderRuleResponse]].ok([mappers.reminder_rule_to_response(r) for r in rules])


@router.get("/reminder-rules/{rule_id}")
async def get_reminder_rule(rule_id: str, service: ServiceDep, _actor: Annotated[User, _perm("reminder_rules", "view")]) -> ApiResponse[ReminderRuleResponse]:
    rule = await service.get_reminder_rule(rule_id)
    return ApiResponse[ReminderRuleResponse].ok(mappers.reminder_rule_to_response(rule))


@router.patch("/reminder-rules/{rule_id}")
async def update_reminder_rule(
    rule_id: str, payload: UpdateReminderRuleRequest, service: ServiceDep, actor: Annotated[User, _perm("reminder_rules", "edit")]
) -> ApiResponse[ReminderRuleResponse]:
    rule = await service.update_reminder_rule(rule_id, payload, actor)
    return ApiResponse[ReminderRuleResponse].ok(mappers.reminder_rule_to_response(rule))


@router.patch("/reminder-rules/{rule_id}/activate")
async def activate_reminder_rule(rule_id: str, service: ServiceDep, actor: Annotated[User, _perm("reminder_rules", "edit")]) -> ApiResponse[ReminderRuleResponse]:
    rule = await service.set_reminder_rule_active(rule_id, active=True, actor=actor)
    return ApiResponse[ReminderRuleResponse].ok(mappers.reminder_rule_to_response(rule))


@router.patch("/reminder-rules/{rule_id}/deactivate")
async def deactivate_reminder_rule(rule_id: str, service: ServiceDep, actor: Annotated[User, _perm("reminder_rules", "edit")]) -> ApiResponse[ReminderRuleResponse]:
    rule = await service.set_reminder_rule_active(rule_id, active=False, actor=actor)
    return ApiResponse[ReminderRuleResponse].ok(mappers.reminder_rule_to_response(rule))


# ---------------------------------------------------------------------- notifications (self-service)


@router.get("/notifications")
async def list_notifications(
    service: ServiceDep, current_user: CurrentUserDep, _staff: StaffDep, page: PageParamsDep, status: str | None = None, category: str | None = None
) -> ApiResponse[list[NotificationResponse]]:
    notifications, total = await service.list_notifications(current_user, status=status, category=category, skip=page.skip, limit=page.page_size, sort=page.sort)
    items = [mappers.notification_to_response(n) for n in notifications]
    return ApiResponse[list[NotificationResponse]].ok(items, meta=ResponseMeta(pagination=page.build_meta(total)))


@router.get("/notifications/unread-count")
async def get_unread_count(service: ServiceDep, current_user: CurrentUserDep, _staff: StaffDep) -> ApiResponse[dict[str, int]]:
    count = await service.get_unread_count(current_user)
    return ApiResponse[dict[str, int]].ok({"unread_count": count})


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, service: ServiceDep, current_user: CurrentUserDep, _staff: StaffDep) -> ApiResponse[NotificationResponse]:
    notification = await service.mark_notification_read(notification_id, current_user)
    return ApiResponse[NotificationResponse].ok(mappers.notification_to_response(notification))


@router.post("/notifications/{notification_id}/archive")
async def archive_notification(notification_id: str, service: ServiceDep, current_user: CurrentUserDep, _staff: StaffDep) -> ApiResponse[NotificationResponse]:
    notification = await service.archive_notification(notification_id, current_user)
    return ApiResponse[NotificationResponse].ok(mappers.notification_to_response(notification))


@router.post("/notifications/{notification_id}/dismiss")
async def dismiss_notification(notification_id: str, service: ServiceDep, current_user: CurrentUserDep, _staff: StaffDep) -> ApiResponse[NotificationResponse]:
    notification = await service.dismiss_notification(notification_id, current_user)
    return ApiResponse[NotificationResponse].ok(mappers.notification_to_response(notification))
