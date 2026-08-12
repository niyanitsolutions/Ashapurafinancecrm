"""Arq worker entrypoint. Run with: arq app.worker.worker_settings.WorkerSettings

Module 6D (Reminder & Notification Engine) is the first to register real jobs, all
scheduled via `cron_jobs` rather than enqueued ad hoc — none of them hardcode timing;
each reads its behavior from the `reminder_rules` collection (an Owner-editable
catalog) or (for `poll_audit_events`) from a fixed, small set of audit-log event types
named explicitly in the brief. See `app/worker/tasks/reminders.py`.
"""

from typing import Any, ClassVar

from arq.connections import RedisSettings
from arq.cron import cron

from app.config.settings import get_settings
from app.logging_config import configure_logging
from app.worker.tasks.communication import (
    poll_business_events,
    process_pending_queue,
    process_retry_queue,
)
from app.worker.tasks.lead_capture import retry_capture_failures
from app.worker.tasks.meta_token_refresh import refresh_meta_tokens
from app.worker.tasks.referral_partner import check_commission_triggers
from app.worker.tasks.reminders import (
    check_re_eligible_cases,
    check_task_reminders,
    poll_audit_events,
)


async def _startup(_ctx: dict[str, Any]) -> None:
    configure_logging(process="worker")


async def _shutdown(_ctx: dict[str, Any]) -> None:
    pass


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class WorkerSettings:
    functions: ClassVar[list[Any]] = []
    cron_jobs: ClassVar[list[Any]] = [
        # arq's own WorkerCoroutine Protocol doesn't structurally match a plain typed
        # async def under mypy --strict (a known friction point between arq's stubs and
        # strict mode) even though these run correctly at runtime — the signatures match
        # arq's actual calling convention (ctx, *args, **kwargs).
        cron(poll_audit_events, minute=set(range(0, 60, 5)), run_at_startup=True),  # type: ignore[arg-type]  # every 5 minutes
        cron(check_task_reminders, minute=set(range(0, 60, 15)), run_at_startup=True),  # type: ignore[arg-type]  # every 15 minutes
        cron(check_re_eligible_cases, hour={2}, minute={0}),  # type: ignore[arg-type]  # once daily
        cron(check_commission_triggers, hour={3}, minute={0}),  # type: ignore[arg-type]  # once daily
        cron(refresh_meta_tokens, hour={4}, minute={0}),  # type: ignore[arg-type]  # once daily
        cron(retry_capture_failures, minute=set(range(0, 60, 15)), run_at_startup=True),  # type: ignore[arg-type]  # every 15 minutes
        cron(poll_business_events, minute=set(range(0, 60, 2)), run_at_startup=True),  # type: ignore[arg-type]  # every 2 minutes
        cron(process_pending_queue, minute=set(range(0, 60, 1)), run_at_startup=True),  # type: ignore[arg-type]  # every minute
        cron(process_retry_queue, minute=set(range(0, 60, 5)), run_at_startup=True),  # type: ignore[arg-type]  # every 5 minutes
    ]
    on_startup = _startup
    on_shutdown = _shutdown
    redis_settings = _redis_settings()
