"""Commit existing workspace updates, append-only history and both audit trails together."""

from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, OperationFailure

from app.core.exceptions import ConflictError
from app.features.leads.models import LeadActivity
from app.shared.audit_log import AuditLog


async def commit(
    db: Any,
    row: dict[str, Any],
    version: int | None,
    updates: dict[str, Any],
    event: dict[str, Any],
    actor: Any,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    audit = AuditLog(
        event_type="daily_follow_up_updated", user_id=actor.require_id(), metadata=metadata
    )
    try:
        async with await db.client.start_session() as session, session.start_transaction():
            updated = await db.daily_follow_ups.find_one_and_update(
                {
                    "_id": row["_id"],
                    "version": version,
                    "is_deleted": False,
                    "working_key": row["working_key"],
                },
                {"$set": updates, "$inc": {"version": 1}, "$push": {"history": event}},
                return_document=ReturnDocument.AFTER,
                session=session,
            )
            if not updated:
                raise ConflictError("This record changed. Reload before saving again.")
            await db.audit_logs.insert_one(
                audit.model_dump(by_alias=True, exclude={"id"}), session=session
            )
            if row.get("lead_id"):
                activity = LeadActivity(
                    lead_id=row["lead_id"],
                    event_type="daily_follow_up_updated",
                    metadata=metadata,
                    created_by=actor.require_id(),
                )
                await db.lead_activities.insert_one(
                    activity.model_dump(by_alias=True, exclude={"id"}), session=session
                )
    except DuplicateKeyError:
        raise ConflictError("Workspace changed. Reload before continuing.") from None
    except OperationFailure as exc:
        if exc.code == 112 or exc.has_error_label("TransientTransactionError"):
            raise ConflictError("Concurrent activity change. Reload before continuing.") from None
        raise
    return dict(updated)
