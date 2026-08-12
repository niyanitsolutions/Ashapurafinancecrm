"""Module 9B — the retry queue's scheduled half. `LeadCaptureService.retry_due_failures`
holds all the actual logic (re-dispatch through the same shared pipeline, backoff,
give up after `MAX_RETRY_ATTEMPTS`) — this is just the Arq cron entry point, the same
thin-wrapper shape every prior scheduled job in this project uses (6D's
`app/worker/tasks/reminders.py`, 7's `app/worker/tasks/referral_partner.py`).
"""

from typing import Any

from app.config.database import get_database
from app.features.lead_capture.service import LeadCaptureService


async def retry_capture_failures(_ctx: dict[Any, Any], *_args: Any, **_kwargs: Any) -> Any:
    db = get_database()
    service = LeadCaptureService(db)
    await service.retry_due_failures()
