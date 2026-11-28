"""Owner provisioning through the existing mobile-unique User identity."""

import hashlib
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.features.auth.models import User
from app.features.referral_partner_management.models import ReferralPartner
from app.security.password import hash_password
from app.shared.audit_log import AuditLog
from app.shared.customer_identity import mobile_match_pattern
from app.utils.id_generator import IdPrefix, generate_id


async def create_account(db: Any, payload: Any, actor: User) -> ReferralPartner:
    if actor.role != "owner":
        raise ForbiddenError("Only the Owner can provision Partner credentials.")
    receipt_id = ObjectId(
        hashlib.sha256(
            ("partner-account:" + actor.require_id() + payload.request_id).encode()
        ).hexdigest()[:24]
    )
    # Receipts deliberately exclude passwords, including password fingerprints.
    identity = {
        "mobile": payload.mobile,
        "full_name": payload.full_name,
        "email": str(payload.email) if payload.email else None,
    }
    receipt = await db.audit_logs.find_one({"_id": receipt_id})
    if receipt:
        if receipt["metadata"]["identity"] != identity:
            raise ConflictError("This request key was already used for another account.")
        row = await db.referral_partners.find_one(
            {"_id": ObjectId(receipt["metadata"]["partner_id"])}
        )
        return ReferralPartner.model_validate(row)
    # Match formatted and deleted identities too; uniqueness must never be bypassed.
    existing = await db.users.find_one({"mobile": {"$regex": mobile_match_pattern(payload.mobile)}})
    if existing and (
        not payload.reuse_existing_identity
        or existing.get("role") != "referral_partner"
        or existing.get("is_deleted")
        or existing.get("status") != "active"
        or not existing.get("password_hash")
    ):
        raise ConflictError(
            "This mobile already belongs to a CRM identity. Use its existing account; credentials were not changed."
        )
    if payload.reuse_existing_identity and not existing:
        raise ValidationError("No active Partner identity exists for this mobile.")
    if existing and await db.referral_partners.find_one({"user_id": str(existing["_id"])}):
        raise ConflictError(
            "This identity already has a Partner profile. Open the existing record."
        )
    user = (
        User.model_validate(existing)
        if existing
        else User(
            mobile=payload.mobile,
            role="referral_partner",
            password_hash=hash_password(payload.initial_password),
            must_change_password=payload.temporary_password,
            created_by=actor.require_id(),
        )
    )
    user_id, partner_id = (existing["_id"] if existing else ObjectId()), ObjectId()
    partner = ReferralPartner(
        partner_code=await generate_id(db, IdPrefix.REFERRAL_PARTNER),
        user_id=str(user_id),
        full_name=payload.full_name.strip(),
        mobile=payload.mobile,
        email=str(payload.email) if payload.email else None,
        business_name=payload.business_name,
        created_by=actor.require_id(),
    )
    audit = AuditLog(
        event_type="referral_partner_created",
        user_id=actor.require_id(),
        metadata={
            "partner_id": str(partner_id),
            "identity": identity,
            "credential_delivery": "owner_handover",
            "temporary_password": payload.temporary_password,
        },
    )
    try:
        async with await db.client.start_session() as session, session.start_transaction():
            if existing:
                guard = await db.users.update_one(
                    {
                        "_id": user_id,
                        "role": "referral_partner",
                        "status": "active",
                        "is_deleted": False,
                    },
                    {"$inc": {"partner_profile_guard": 1}},
                    session=session,
                )
                if not guard.matched_count:
                    raise ConflictError("Existing identity changed; refresh before association.")
            else:
                await db.users.insert_one(
                    {**user.model_dump(exclude={"id"}), "_id": user_id}, session=session
                )
            await db.referral_partners.insert_one(
                {**partner.model_dump(exclude={"id"}), "_id": partner_id}, session=session
            )
            await db.audit_logs.insert_one(
                {**audit.model_dump(exclude={"id"}), "_id": receipt_id}, session=session
            )
            from app.features.referral_partner_management.notifications import notify

            await notify(db, actor, "partner_account_created", str(partner_id), session)
    except DuplicateKeyError:
        raise ConflictError("Account or request already exists. Refresh before retrying.") from None
    partner.id = str(partner_id)
    return partner
