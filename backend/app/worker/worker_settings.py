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
    process_bulk_message_jobs,
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
    # TIMEZONE NOTE (see docs/TIMEZONE.md): arq's `cron(hour=..., minute=...)` matches
    # against the worker *process's own OS wall-clock* (stdlib `datetime.now()`, no tz
    # parameter) — arq has no tz-aware cron primitive, so this app cannot make these
    # trigger times IST-aware without deeper surgery (e.g. wrapping every job in its own
    # IST-based self-gating). This is a disclosed, low-risk limitation, not an oversight:
    # `check_re_eligible_cases`/`check_commission_triggers`/`refresh_meta_tokens` are
    # internal daily maintenance batches with no user-facing "must fire at exactly 2am
    # IST" promise, and their own business decisions never do a calendar-day-boundary
    # comparison: `check_re_eligible_cases` compares `now < notify_at` (an absolute
    # instant, duration-based — see `worker/tasks/reminders.py`), and
    # `check_commission_triggers`/`refresh_meta_tokens` re-scan by *status*, not by date,
    # each run (see `worker/tasks/referral_partner.py`, `worker/tasks/meta_token_
    # refresh.py`) — confirmed timezone-safe as-is. The hours below
    # assume the deployed worker process's OS clock is UTC (this app's documented
    # default, see docs/TIMEZONE.md) — recorded in docs/KNOWN_LIMITATIONS.md.
    # `check_task_reminders`/`poll_audit_events`/the communication queue jobs poll every
    # 1-15 minutes specifically so their own trigger-hour precision never matters; what
    # they decide is "due" is instant-based for the same reason.
    cron_jobs: ClassVar[list[Any]] = [
        # arq's own WorkerCoroutine Protocol doesn't structurally match a plain typed
        # async def under mypy --strict (a known friction point between arq's stubs and
        # strict mode) even though these run correctly at runtime — the signatures match
        # arq's actual calling convention (ctx, *args, **kwargs).
        cron(poll_audit_events, minute=set(range(0, 60, 5)), run_at_startup=True),  # type: ignore[arg-type]  # every 5 minutes
        cron(check_task_reminders, minute=set(range(0, 60, 15)), run_at_startup=True),  # type: ignore[arg-type]  # every 15 minutes
        cron(check_re_eligible_cases, hour={2}, minute={0}),  # type: ignore[arg-type]  # once daily, assumes server clock = UTC
        cron(check_commission_triggers, hour={3}, minute={0}),  # type: ignore[arg-type]  # once daily, assumes server clock = UTC
        cron(refresh_meta_tokens, hour={4}, minute={0}),  # type: ignore[arg-type]  # once daily, assumes server clock = UTC
        cron(retry_capture_failures, minute=set(range(0, 60, 15)), run_at_startup=True),  # type: ignore[arg-type]  # every 15 minutes
        cron(poll_business_events, minute=set(range(0, 60, 2)), run_at_startup=True),  # type: ignore[arg-type]  # every 2 minutes
        cron(process_pending_queue, minute=set(range(0, 60, 1)), run_at_startup=True),  # type: ignore[arg-type]  # every minute
        cron(process_retry_queue, minute=set(range(0, 60, 5)), run_at_startup=True),  # type: ignore[arg-type]  # every 5 minutes
        cron(process_bulk_message_jobs, minute=set(range(0, 60, 1)), run_at_startup=True),  # type: ignore[arg-type]  # every minute
    ]
    on_startup = _startup
    on_shutdown = _shutdown
    redis_settings = _redis_settings()
