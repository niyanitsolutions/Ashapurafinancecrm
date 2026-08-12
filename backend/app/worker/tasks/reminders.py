"""Module 6D — Reminder & Notification Engine scheduled jobs (Arq).

None of these hook live into any frozen module. `poll_audit_events` reads the existing,
already-written `audit_logs` collection (append-only, `shared/audit_log.py`) for the two
event types the brief names — `lead_assigned` (Module 6A) and `document_uploaded`
(Module 6B) — the same "lazy scan of a read-only, already-existing signal" pattern
Module 6C used for case auto-creation (decision 058), applied here for notifications
instead of case creation. `check_re_eligible_cases` reads Module 6C's
`application_workflows`/`application_status_history` read-only. Timings are never
hardcoded here — every job reads its behavior from `reminder_rules` (an Owner-editable
collection), per explicit instruction.
"""

from datetime import timedelta
from typing import Any

from app.config.database import get_database
from app.features.customer.repository import ApplicationRepository
from app.features.employee.repository import EmployeeRepository
from app.features.reminders.constants import (
    POLLED_AUDIT_EVENT_TYPES,
    NotificationType,
    ReminderRuleType,
    ReminderTargetType,
    ReminderType,
)
from app.features.reminders.models import Reminder
from app.features.reminders.repository import (
    NotificationCheckpointRepository,
    ReminderRepository,
    ReminderRuleRepository,
    TaskRepository,
)
from app.features.reminders.service import RemindersService
from app.features.workflow_engine.constants import CaseType, LoanStatus
from app.features.workflow_engine.repository import (
    ApplicationStatusHistoryRepository,
    ApplicationWorkflowRepository,
)
from app.utils.datetime import ensure_utc, utc_now


async def poll_audit_events(_ctx: dict[Any, Any], *_args: Any, **_kwargs: Any) -> Any:
    db = get_database()
    checkpoints = NotificationCheckpointRepository(db)
    applications = ApplicationRepository(db)
    employees = EmployeeRepository(db)
    service = RemindersService(db)

    for event_type in POLLED_AUDIT_EVENT_TYPES:
        since = await checkpoints.get_last_processed_at(event_type)
        query: dict[str, Any] = {"event_type": event_type}
        if since is not None:
            query["created_at"] = {"$gt": since}
        cursor = db["audit_logs"].find(query).sort("created_at", 1).limit(500)
        latest_seen = since
        async for doc in cursor:
            metadata = doc.get("metadata") or {}
            latest_seen = doc["created_at"]

            if event_type == "lead_assigned":
                employee_id = metadata.get("employee_id")
                lead_id = metadata.get("lead_id")
                if not employee_id:
                    continue
                employee = await employees.find_by_id(employee_id)
                if employee is None:
                    continue
                await service.create_notification(
                    recipient_user_id=employee.user_id, notification_type=NotificationType.LEAD_ASSIGNED,
                    title="New Lead Assigned", message="A new lead has been assigned to you.",
                    entity_type="lead", entity_id=lead_id,
                )
            elif event_type == "document_uploaded":
                application_id = metadata.get("application_id")
                if not application_id:
                    continue
                application = await applications.find_by_id(application_id)
                if application is None or not application.assigned_to:
                    continue  # unassigned application — nobody to notify yet
                employee = await employees.find_by_id(application.assigned_to)
                if employee is None:
                    continue
                await service.create_notification(
                    recipient_user_id=employee.user_id, notification_type=NotificationType.DOCUMENT_UPLOADED,
                    title="Documents Uploaded", message="The customer has uploaded documents for their application.",
                    entity_type="application", entity_id=application_id,
                )

        if latest_seen is not None:
            await checkpoints.set_last_processed_at(event_type, latest_seen)


async def check_re_eligible_cases(_ctx: dict[Any, Any], *_args: Any, **_kwargs: Any) -> Any:
    db = get_database()
    rules = ReminderRuleRepository(db)
    workflows = ApplicationWorkflowRepository(db)
    history = ApplicationStatusHistoryRepository(db)
    reminders = ReminderRepository(db)
    employees = EmployeeRepository(db)
    service = RemindersService(db)
    now = utc_now()

    active_rules = await rules.find_active_by_type(ReminderRuleType.RE_ELIGIBILITY)
    for rule in active_rules:
        if rule.case_type is None or rule.eligible_after_days is None or not rule.notify_before_days:
            continue  # misconfigured row — skip rather than guess
        case_type = rule.case_type
        cases, _total = await workflows.search_and_filter(
            case_type=case_type, search=None, customer_id=None, assigned_to=None, unassigned_only=False,
            status=LoanStatus.REJECTED, skip=0, limit=1000, sort=None,
        )
        target_type = ReminderTargetType.LOAN_CASE if case_type == CaseType.LOAN else ReminderTargetType.INSURANCE_CASE

        for case in cases:
            case_id = case.require_id()
            case_history = await history.find_for_workflow(case_id)
            rejected_entry = next((h for h in case_history if h.to_status == LoanStatus.REJECTED), None)
            rejected_at = ensure_utc(rejected_entry.created_at if rejected_entry else case.updated_at)
            eligible_at = rejected_at + timedelta(days=rule.eligible_after_days)

            # A rule can define multiple trigger points (e.g. 30/15/7/1 days before
            # eligibility) — each fires its own, independently-tracked reminder, so a
            # case that's crossed several thresholds since the last run catches up on
            # all of them in one pass rather than only ever firing the first one.
            for offset in rule.notify_before_days:
                notify_at = eligible_at - timedelta(days=offset)
                if now < notify_at:
                    continue  # this specific trigger point hasn't arrived yet
                if await reminders.find_existing(
                    rule_id=rule.require_id(), target_type=target_type, target_id=case_id, reminder_type=ReminderType.RE_ELIGIBILITY, trigger_offset=offset
                ):
                    continue  # already notified for this specific trigger point

                reminder = Reminder(
                    rule_id=rule.require_id(), reminder_type=ReminderType.RE_ELIGIBILITY, target_type=target_type, target_id=case_id,
                    trigger_offset=offset, fire_at=notify_at,
                )
                reminder_id = await reminders.insert(reminder)
                await reminders.mark_fired(reminder_id, fired_at=now)

                if case.assigned_to:
                    employee = await employees.find_by_id(case.assigned_to)
                    if employee is not None:
                        await service.create_notification(
                            recipient_user_id=employee.user_id, notification_type=NotificationType.REMINDER_TRIGGERED,
                            title="Case Re-Eligible Soon",
                            message=f"{case.case_code} becomes eligible for re-application on {eligible_at.date().isoformat()}.",
                            entity_type=target_type, entity_id=case_id,
                        )


async def check_task_reminders(_ctx: dict[Any, Any], *_args: Any, **_kwargs: Any) -> Any:
    db = get_database()
    rules = ReminderRuleRepository(db)
    tasks_repo = TaskRepository(db)
    reminders = ReminderRepository(db)
    employees = EmployeeRepository(db)
    service = RemindersService(db)
    now = utc_now()

    active_rules = await rules.find_active_by_type(ReminderRuleType.TASK_DUE)
    if not active_rules:
        return
    rule = active_rules[0]  # one active task_due rule is the expected shape this round
    if not rule.notify_before_minutes or rule.escalation_repeat_minutes is None or rule.escalation_max_repeats is None:
        return

    pending_tasks = await tasks_repo.find_pending()
    for task in pending_tasks:
        task_id = task.require_id()
        employee = await employees.find_by_id(task.assigned_to)
        if employee is None:
            continue

        due_at = ensure_utc(task.due_at)

        if now < due_at:
            # Same multi-trigger-point support as re-eligibility reminders — a rule can
            # define several before-due notice points, each tracked independently.
            for offset in rule.notify_before_minutes:
                notify_at = due_at - timedelta(minutes=offset)
                if now < notify_at:
                    continue
                if await reminders.find_existing(
                    rule_id=rule.require_id(), target_type=ReminderTargetType.TASK, target_id=task_id, reminder_type=ReminderType.TASK_DUE, trigger_offset=offset
                ):
                    continue
                reminder = Reminder(
                    rule_id=rule.require_id(), reminder_type=ReminderType.TASK_DUE, target_type=ReminderTargetType.TASK, target_id=task_id,
                    trigger_offset=offset, fire_at=notify_at,
                )
                reminder_id = await reminders.insert(reminder)
                await reminders.mark_fired(reminder_id, fired_at=now)
                await service.create_notification(
                    recipient_user_id=employee.user_id, notification_type=NotificationType.TASK_DUE,
                    title="Task Due Soon", message=f'Task "{task.title}" is due soon.', entity_type="task", entity_id=task_id,
                )
            continue

        if task.owner_escalated:
            continue  # already escalated to the Owner — nothing more to do

        escalations = await reminders.find_for_target(target_type=ReminderTargetType.TASK, target_id=task_id, reminder_type=ReminderType.TASK_ESCALATION)
        fired_count = len(escalations)
        last_fired_at = ensure_utc(escalations[0].fired_at) if escalations and escalations[0].fired_at else None  # find_for_target sorts newest-first

        due_for_next_escalation = last_fired_at is None or (now - last_fired_at) >= timedelta(minutes=rule.escalation_repeat_minutes)
        if not due_for_next_escalation:
            continue

        reminder = Reminder(
            rule_id=rule.require_id(), reminder_type=ReminderType.TASK_ESCALATION, target_type=ReminderTargetType.TASK, target_id=task_id,
            fire_at=now, repeat_count=fired_count + 1,
        )
        reminder_id = await reminders.insert(reminder)
        await reminders.mark_fired(reminder_id, fired_at=now)
        await service.create_notification(
            recipient_user_id=employee.user_id, notification_type=NotificationType.TASK_ESCALATION,
            title="Task Overdue", message=f'Task "{task.title}" is overdue and still not completed.', entity_type="task", entity_id=task_id,
        )

        if fired_count + 1 >= rule.escalation_max_repeats:
            owners = await db["users"].find({"role": "owner", "is_deleted": False}).to_list(length=50)
            for owner_doc in owners:
                await service.create_notification(
                    recipient_user_id=str(owner_doc["_id"]), notification_type=NotificationType.TASK_OWNER_ESCALATION,
                    title="Task Still Not Completed", message=f'Task "{task.title}" (assigned to {employee.display_name}) is still not completed after repeated reminders.',
                    entity_type="task", entity_id=task_id,
                )
            await tasks_repo.update(task_id, {"owner_escalated": True})
