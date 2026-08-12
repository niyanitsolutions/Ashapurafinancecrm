"""Module 9A — the Meta OAuth token refresh queue's scheduled half.
`IntegrationsService.refresh_expiring_meta_tokens` holds all the actual logic (exchange
the long-lived User token before it expires, re-derive the Page token, record
success/failure) — this is just the Arq cron entry point, the same thin-wrapper shape
every prior scheduled job in this project uses (`app/worker/tasks/lead_capture.py`).
"""

from typing import Any

from app.config.database import get_database
from app.config.redis import get_redis
from app.features.integrations.service import IntegrationsService


async def refresh_meta_tokens(_ctx: dict[Any, Any], *_args: Any, **_kwargs: Any) -> Any:
    db = get_database()
    service = IntegrationsService(db, get_redis())
    await service.refresh_expiring_meta_tokens()
