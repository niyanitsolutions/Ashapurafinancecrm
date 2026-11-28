"""Owner referral review over canonical Applications, with locked financial history."""

from typing import Any

from pydantic import Field

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.features.referral_partner_management.kyc import event, oid, public
from app.features.referral_partner_management.portal_models import StrictInput
from app.utils.datetime import utc_now


class AttributionCorrection(StrictInput):
    version: int = Field(ge=1)
    partner_id: str
    reason: str = Field(min_length=3, max_length=1000)
    acknowledge_financial_history: bool


async def correct_attribution(
    db: Any, application_id: str, payload: AttributionCorrection, actor: Any
) -> dict[str, Any]:
    if actor.role != "owner":
        raise ForbiddenError("Only Owner can correct referral attribution.")
    if not payload.acknowledge_financial_history:
        raise ValidationError(
            "Acknowledge that existing earnings and payments remain unchanged and require separate financial review."
        )
    async with await db.client.start_session() as session, session.start_transaction():
        application = await db.applications.find_one(
            {"_id": oid(application_id), "is_deleted": False, "version": payload.version},
            session=session,
        )
        if not application:
            raise ConflictError("Application changed or is unavailable. Reload before correction.")
        original = application.get("referral_attribution")
        if not original:
            raise ValidationError(
                "This Application has no original Partner attribution to correct."
            )
        partner = await db.referral_partners.find_one(
            {
                "_id": oid(payload.partner_id),
                "is_deleted": False,
                "account_active": {"$ne": False},
                "approval_status": "active",
                "kyc_status": "approved",
            },
            session=session,
        )
        if not partner:
            raise NotFoundError("Select an active approved Partner.")
        if original["partner_id"] == payload.partner_id:
            raise ValidationError("Select a different Partner for an attribution correction.")
        if (
            partner.get("applicable_product_ids")
            and application["product_id"] not in partner["applicable_product_ids"]
        ):
            raise ValidationError("The replacement Partner is not permitted for this product.")
        # Touch both the Partner and case: contend with eligibility changes and financial commits.
        await db.referral_partners.update_one(
            {"_id": partner["_id"]}, {"$inc": {"attribution_guard": 1}}, session=session
        )
        case = await db.application_workflows.find_one(
            {"application_id": application_id, "is_deleted": False}, session=session
        )
        if case:
            await db.application_workflows.update_one(
                {"_id": case["_id"]}, {"$inc": {"attribution_guard": 1}}, session=session
            )
        entries = [
            str(row["_id"])
            async for row in db.commission_entries.find(
                {"application_id": application_id}, {"_id": 1}, session=session
            )
        ]
        corrected = {
            **original,
            "partner_id": payload.partner_id,
            "partner_name": partner["full_name"],
            "corrected_at": utc_now(),
            "corrected_by": actor.require_id(),
        }
        result = await db.applications.update_one(
            {"_id": application["_id"], "version": payload.version},
            {
                "$set": {
                    "referral_attribution": corrected,
                    "updated_at": utc_now(),
                    "updated_by": actor.require_id(),
                },
                "$inc": {"version": 1},
            },
            session=session,
        )
        if not result.matched_count:
            raise ConflictError("Application changed; no correction committed.")
        await event(
            db,
            actor,
            "partner_referral_attribution_corrected",
            payload.partner_id,
            session=session,
            detail={
                "application_id": application_id,
                "before": public(original),
                "after": public(corrected),
                "reason": payload.reason,
                "unchanged_commission_entry_ids": entries,
            },
        )
    return {
        "id": application_id,
        "version": payload.version + 1,
        "referral_attribution": public(corrected),
        "financial_history_unchanged": True,
    }
