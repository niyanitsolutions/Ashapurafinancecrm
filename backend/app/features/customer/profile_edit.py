"""Versioned staff edits of the current profile; submitted facts remain untouched."""

from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.constants.roles import EMPLOYEE, OWNER
from app.core.exceptions import ConflictError, ForbiddenError
from app.features.auth.models import User
from app.features.customer.models import Customer
from app.features.customer.schemas import StaffProfileUpdate
from app.features.customer.service import CustomerService
from app.security.encryption import encrypt
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now


async def update_profile(
    service: CustomerService,
    db: AsyncIOMotorDatabase[Any],
    customer_id: str,
    actor: User,
    payload: StaffProfileUpdate,
) -> Customer:
    if actor.role not in {OWNER, EMPLOYEE}:
        raise ForbiddenError("Staff access is required.")
    current = await service.get_customer_for_staff(customer_id, actor)
    data = payload.model_dump(exclude_unset=True, exclude={"version", "reason"})
    sensitive = {"pan_number", "aadhaar_number", "date_of_birth"}
    if actor.role != OWNER and sensitive.intersection(data):
        raise ForbiddenError("Only an Owner can change identity verification fields.")
    changes: dict[str, Any] = {}
    for key, value in data.items():
        if key in {"pan_number", "aadhaar_number"}:
            if value is not None:
                changes[key + "_encrypted"] = encrypt(value)
                if key == "pan_number":
                    from app.shared.customer_identity import pan_search_digest

                    changes["pan_search_digest"] = pan_search_digest(value)
        elif key == "date_of_birth":
            from datetime import UTC, datetime

            changes[key] = (
                datetime.combine(value, datetime.min.time(), tzinfo=UTC) if value else None
            )
        elif key == "full_name":
            if not value or not value.strip():
                from app.core.exceptions import ValidationError

                raise ValidationError("Customer name is required.")
            changes[key] = value.strip()
        else:
            changes[key] = value
    before = current.model_dump()
    history = [
        {
            "field": key,
            "before": before.get(key),
            "after": value,
            "actor_id": actor.require_id(),
            "at": utc_now(),
            "reason": payload.reason,
            "source": "staff_profile_edit",
        }
        for key, value in changes.items()
        if before.get(key) != value
    ]
    if not history:
        return current
    result = await db.customers.update_one(
        {"_id": ObjectId(customer_id), "is_deleted": False, "version": payload.version},
        {
            "$set": {**changes, "updated_at": utc_now(), "updated_by": actor.require_id()},
            "$inc": {"version": 1},
            "$push": {"profile_history": {"$each": history}},
        },
    )
    if not result.modified_count:
        raise ConflictError("This profile changed. Reload it before saving again.")
    await write_audit_log(
        db,
        event_type="customer_profile_edited",
        user_id=actor.require_id(),
        metadata={
            "customer_id": customer_id,
            "fields": [h["field"] for h in history],
            "version": payload.version + 1,
        },
    )
    return await service.get_customer_for_staff(customer_id, actor)
