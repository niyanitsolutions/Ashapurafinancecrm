"""Enrich an existing profile from its own submitted application's canonical fields."""

from datetime import UTC, date, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError

from app.features.customer.identity_name import application_name
from app.features.customer.models import Application
from app.features.customer.schemas import CompleteProfileRequest
from app.shared.audit_log import write_audit_log
from app.shared.customer_identity import normalized_name
from app.utils.datetime import utc_now

PLACEHOLDERS = {"", "customer"}


async def enrich_submitted_identity(
    db: AsyncIOMotorDatabase[Any], application: Application
) -> None:
    if application.status != "submitted" or not application.customer_id:
        return
    query = {
        "_id": ObjectId(application.customer_id),
        "user_id": application.user_id,
        "is_deleted": False,
    }
    customer = await db.customers.find_one(query)
    if not customer:
        return
    # Only exact canonical keys from the stored schema. Never infer identity from labels,
    # co-applicants, untrusted pending_profile, names or matching phone numbers.
    schema = await db.application_form_definitions.find_one(
        {"_id": ObjectId(application.form_definition_id)}
    )
    resolved_name = application_name(application, schema)
    values = {"full_name": resolved_name} if resolved_name else {}
    name = values.get("full_name")
    if name is not None and (not isinstance(name, str) or normalized_name(name) in PLACEHOLDERS):
        values.pop("full_name", None)
    candidates: dict[str, Any] = {}
    for key, input_value in values.items():
        try:
            profile = CompleteProfileRequest.model_validate(
                {"full_name": customer["full_name"], key: input_value}
            )
        except ValidationError:
            # A product field can differ from profile format. Skip that field without
            # preventing other valid identity fields or a valid application submission.
            continue
        candidates[key] = getattr(profile, key)
    changed = []
    for key, value in candidates.items():
        previous = customer.get(key)
        if key == "full_name":
            if normalized_name(previous or "") not in PLACEHOLDERS:
                continue
            value = value.strip()
        elif previous:
            continue
        if isinstance(value, date):
            value = datetime.combine(value, datetime.min.time(), tzinfo=UTC)
        elif hasattr(value, "model_dump"):
            value = value.model_dump()
        result = await db.customers.update_one(
            {**query, key: previous},
            {
                "$set": {key: value, "updated_at": utc_now(), "updated_by": application.user_id},
                "$inc": {"version": 1},
                "$push": {
                    "profile_history": {
                        "field": key,
                        "before": previous,
                        "after": value,
                        "actor_id": application.user_id,
                        "application_id": application.require_id(),
                        "at": utc_now(),
                        "source": "submitted_application",
                    }
                },
            },
        )
        if result.modified_count:
            changed.append(key)
    if changed:
        await write_audit_log(
            db,
            event_type="customer_profile_enriched",
            user_id=application.user_id,
            metadata={
                "customer_id": application.customer_id,
                "application_id": application.require_id(),
                "fields": changed,
                "source": "submitted_application",
            },
        )
    current = await db.customers.find_one(query, {"full_name": 1})
    if (
        application.lead_id
        and current
        and normalized_name(current.get("full_name", "")) not in PLACEHOLDERS
    ):
        await db.leads.update_one(
            {
                "_id": ObjectId(application.lead_id),
                "customer_id": application.customer_id,
                "full_name": {"$in": ["Customer", "customer", ""]},
                "is_deleted": False,
            },
            {
                "$set": {
                    "full_name": current["full_name"],
                    "identity_name": normalized_name(current["full_name"]),
                }
            },
        )
