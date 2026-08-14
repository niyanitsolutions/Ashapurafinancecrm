"""Module 9C — Communication Engine scheduled jobs (Arq).

`poll_business_events` never modifies a frozen module — it only reads the existing,
already-written `audit_logs` collection (the same lazy-scan pattern Module 6D
established for its own notification engine, decision 065). `process_pending_queue` and
`process_retry_queue` are the two halves of "every outgoing communication must enter a
queue... never send directly from request handlers" — nothing in this codebase calls a
provider adapter except these two jobs (and the manual Retry Action, which reuses the
same `_send_one` code path).
"""

from typing import Any

from app.config.database import get_database
from app.features.communication.service import CommunicationService


async def poll_business_events(_ctx: dict[Any, Any], *_args: Any, **_kwargs: Any) -> Any:
    service = CommunicationService(get_database())
    await service.poll_business_events()


async def process_pending_queue(_ctx: dict[Any, Any], *_args: Any, **_kwargs: Any) -> Any:
    service = CommunicationService(get_database())
    await service.process_pending_queue()


async def process_retry_queue(_ctx: dict[Any, Any], *_args: Any, **_kwargs: Any) -> Any:
    service = CommunicationService(get_database())
    await service.process_retry_queue()


async def process_bulk_message_jobs(_ctx: dict[Any, Any], *_args: Any, **_kwargs: Any) -> Any:
    service = CommunicationService(get_database())
    await service.process_bulk_message_jobs()
