"""Shared audit log writer. `audit_logs` (see docs/database/COLLECTIONS.md) is written by
many features over time, not just one — this lives in `shared/` rather than inside a
single feature's folder for that reason. Auth is the first writer; the full Audit
*feature* (viewing/filtering UI, retention policy) remains future scope — this module
only establishes the collection and the write path every feature will reuse.

Append-only by design: no update or delete function is provided here, intentionally.
"""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.shared.base_document import BaseDocument

_COLLECTION_NAME = "audit_logs"


class AuditLog(BaseDocument):
    event_type: str
    user_id: str | None = None
    mobile: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    metadata: dict[str, Any] | None = None


async def write_audit_log(
    db: AsyncIOMotorDatabase[Any],
    *,
    event_type: str,
    user_id: str | None = None,
    mobile: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    entry = AuditLog(
        event_type=event_type,
        user_id=user_id,
        mobile=mobile,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata=metadata,
    )
    payload = entry.model_dump(by_alias=True, exclude={"id"})
    await db[_COLLECTION_NAME].insert_one(payload)
