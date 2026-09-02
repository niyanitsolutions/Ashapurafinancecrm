"""Centralized Bin — 30-day automatic permanent deletion (Arq cron job).

Runs daily. Reuses `BinService.purge_expired`, which hard-deletes only records whose
retention window (`bin_entries.purge_at`, = deleted_at + 30 days) has elapsed, along
with their strictly-owned private child rows (see `bin/registry.py`). Never touches
`audit_logs`, `users`, `customers`, `applications`, or any financial ledger.

Timezone-safe as-is: `purge_at <= now` is an absolute-instant comparison, not a
calendar-day boundary — same reasoning as the other daily maintenance jobs (see the
TIMEZONE NOTE in `app/worker/worker_settings.py`).
"""

from typing import Any

from app.config.database import get_database
from app.features.bin.service import BinService
from app.utils.datetime import utc_now


async def purge_expired_bin_entries(_ctx: dict[Any, Any], *_args: Any, **_kwargs: Any) -> Any:
    return await BinService(get_database()).purge_expired(utc_now())
