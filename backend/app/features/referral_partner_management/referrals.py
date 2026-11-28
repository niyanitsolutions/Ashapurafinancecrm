"""Partner workflow around canonical Customer Applications and existing form validation."""

import hashlib
import json
import secrets
from datetime import timedelta
from typing import Any

from bson import ObjectId
from pydantic import EmailStr, Field

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.customer.models import Application, Customer
from app.features.customer.service import CustomerService
from app.features.referral_partner_management.kyc import PartnerKyc, event, oid
from app.features.referral_partner_management.portal_models import StrictInput
from app.security.encryption import decrypt, encrypt
from app.shared.customer_identity import mobile_match_pattern
from app.utils.datetime import utc_now
from app.utils.id_generator import IdPrefix, generate_id


class ReferralDraft(StrictInput):
    product_id: str
    full_name: str = Field(min_length=1, max_length=150)
    mobile: str = Field(pattern=r"^[6-9][0-9]{9}$")
    email: EmailStr | None = None
    form_data: dict[str, Any] = Field(default_factory=dict)
    request_id: str = Field(min_length=16, max_length=100)


class ReferralEdit(StrictInput):
    version: int = Field(ge=1)
    form_data: dict[str, Any]


class ClaimLink(StrictInput):
    token: str = Field(min_length=40, max_length=100, repr=False)


class LinkInput(StrictInput):
    product_id: str = Field(pattern=r"^[a-fA-F0-9]{24}$")
    expires_days: int = Field(default=7, ge=1, le=30)
    request_id: str = Field(min_length=16, max_length=100)


async def guard_customer_referral(db: Any, user_id: str, product_id: str, session: Any) -> None:
    """Serialize referral creation on the real identity; disclose no other referral."""
    result = await db.users.update_one(
        {"_id": oid(user_id), "is_deleted": False, "role": "customer"},
        {"$inc": {"partner_referral_guard": 1}},
        session=session,
    )
    if not result.matched_count:
        raise ConflictError("Customer identity changed. Sign in again or contact AFS.")
    async for application in db.applications.find(
        {
            "user_id": user_id,
            "product_id": product_id,
            "is_deleted": False,
            "status": {"$nin": ["cancelled", "rejected", "withdrawn", "closed"]},
        },
        {"_id": 1},
        session=session,
    ):
        case = await db.application_workflows.find_one(
            {"application_id": str(application["_id"]), "is_deleted": False},
            {"current_status": 1, "loan_details.disbursement_final": 1},
            session=session,
        )
        if case and (
            case["current_status"] in {"rejected", "policy_issued", "closed"}
            or case["current_status"] == "disbursed"
            and case.get("loan_details", {}).get("disbursement_final", True)
        ):
            continue
        raise ConflictError(
            "An existing application requires AFS duplicate review. No new referral or attribution was created."
        )


async def eligible(db: Any, actor: Any, product_id: str | None = None) -> dict[str, Any]:
    partner = await PartnerKyc(db).partner(actor)
    if (
        not partner.get("account_active", True)
        or partner.get("kyc_status") != "approved"
        or partner.get("approval_status") != "active"
    ):
        raise ForbiddenError("An active account and approved KYC are required for referrals.")
    if product_id:
        if (
            partner.get("applicable_product_ids")
            and product_id not in partner["applicable_product_ids"]
        ):
            raise ForbiddenError("This product is not available to this Partner.")
        if not await db.loan_products.find_one(
            {"_id": oid(product_id), "is_deleted": False, "status": "active"}
        ):
            raise ValidationError("Select an active Loan Product.")
    config = await PartnerKyc(db).configuration()
    submission = await db.partner_kyc_submissions.find_one(
        {"_id": oid(partner.get("current_kyc_id") or "")}
    )
    if not submission or not set(config["required_agreement_ids"]).issubset(
        submission.get("accepted_agreement_ids", [])
    ):
        raise ForbiddenError(
            "Accept and complete review of the current required agreement versions before referral activity."
        )
    return partner


class PartnerReferrals:
    def __init__(self, db: Any, redis: Any = None):
        self.db = db
        self.customers = CustomerService(db, redis)

    async def own(self, application_id: str, actor: Any, *, edit: bool = False) -> dict[str, Any]:
        partner = await PartnerKyc(self.db).partner(actor)
        row = await self.db.applications.find_one(
            {
                "_id": oid(application_id),
                "referral_attribution.partner_id": str(partner["_id"]),
                "is_deleted": False,
            }
        )
        if not row:
            raise NotFoundError("Referral not found.")
        if edit:
            await eligible(self.db, actor, row["product_id"])
            if row["referral_attribution"].get("submitted_to_afs_at") or row["status"] != "draft":
                raise ConflictError("Submitted referrals are locked against ordinary editing.")
        return dict(row)

    async def manual(self, payload: ReferralDraft, actor: Any) -> dict[str, Any]:
        if len(json.dumps(payload.form_data).encode()) > 1000000:
            raise ValidationError("Application draft data exceeds the supported size.")
        fingerprint = hashlib.sha256(
            payload.model_dump_json(exclude={"request_id"}).encode()
        ).hexdigest()
        partner = await eligible(self.db, actor, payload.product_id)
        key = "partner-manual:" + str(partner["_id"]) + ":" + payload.request_id
        existing = await self.db.applications.find_one({"referral_attribution.request_key": key})
        if existing:
            if existing["referral_attribution"].get("request_fingerprint") != fingerprint:
                raise ConflictError(
                    "This referral request key was already used for different data."
                )
            return await self.detail(str(existing["_id"]), actor)
        form = await self.customers._get_or_error_form_definition("loan", payload.product_id)
        user_row = await self.db.users.find_one(
            {"mobile": {"$regex": mobile_match_pattern(payload.mobile)}}
        )
        if user_row and (
            user_row.get("is_deleted")
            or user_row["role"] != "customer"
            or user_row.get("status") == "disabled"
        ):
            raise ConflictError(
                "This mobile cannot be used for a Customer referral. Existing credentials were not changed."
            )
        uid = user_row["_id"] if user_row else ObjectId()
        customer_row = await self.db.customers.find_one({"user_id": str(uid)})
        if customer_row and customer_row.get("is_deleted"):
            raise ConflictError("Customer identity requires Owner review.")
        customer = (
            Customer.model_validate(customer_row)
            if customer_row
            else Customer(
                customer_code=await generate_id(self.db, IdPrefix.CUSTOMER),
                user_id=str(uid),
                full_name=payload.full_name,
                mobile=payload.mobile,
                email=str(payload.email) if payload.email else None,
                created_by=actor.require_id(),
            )
        )
        referral_id = str(ObjectId())
        attribution = {
            "partner_id": str(partner["_id"]),
            "referral_id": referral_id,
            "source": "referral_partner",
            "origin": "manual",
            "submission_mode": "partner_review",
            "created_at": utc_now(),
            "request_key": key,
            "request_fingerprint": fingerprint,
            "submitted_to_afs_at": None,
            "partner_name": partner["full_name"],
        }
        async with await self.db.client.start_session() as session, session.start_transaction():
            await self.guard(partner, session)
            if not user_row:
                user = User(
                    mobile=payload.mobile,
                    role="customer",
                    status="pending_password",
                    provisioning_source="partner_manual_referral",
                    created_by=actor.require_id(),
                )
                await self.db.users.insert_one(
                    {**user.model_dump(exclude={"id"}), "_id": uid}, session=session
                )
            if not customer_row:
                result = await self.db.customers.insert_one(
                    customer.model_dump(exclude={"id"}), session=session
                )
                customer.id = str(result.inserted_id)
            await guard_customer_referral(self.db, str(uid), payload.product_id, session)
            application = await self.customers._create_application(
                user_id=str(uid),
                customer_id=customer.require_id(),
                lead_id=None,
                product_category="loan",
                product_id=payload.product_id,
                form_definition=form,
                actor=actor,
                request_key=key,
                referral_attribution=attribution,
                session=session,
            )
            data = {**payload.form_data, "full_name": payload.full_name, "mobile": payload.mobile}
            if payload.email:
                data["email"] = str(payload.email)
            await self.db.applications.update_one(
                {"_id": oid(application.require_id())},
                {"$set": {"form_data": data}},
                session=session,
            )
            await event(
                self.db,
                actor,
                "partner_manual_referral_drafted",
                str(partner["_id"]),
                session=session,
                detail={"application_id": application.require_id(), "referral_id": referral_id},
            )
        return await self.detail(application.require_id(), actor)

    async def guard(self, partner: dict[str, Any], session: Any) -> None:
        config = await self.db.partner_kyc_forms.find_one(
            {}, sort=[("version", -1)], session=session
        )
        submission = await self.db.partner_kyc_submissions.find_one(
            {"_id": oid(partner.get("current_kyc_id") or "")}, session=session
        )
        if not submission or (
            config
            and not set(config["required_agreement_ids"]).issubset(
                submission.get("accepted_agreement_ids", [])
            )
        ):
            raise ForbiddenError("Current Partner agreements require acceptance and review.")
        await self.db.counters.update_one(
            {"_id": "partner_kyc_publish"}, {"$inc": {"epoch": 1}}, upsert=True, session=session
        )
        result = await self.db.referral_partners.update_one(
            {
                "_id": partner["_id"],
                "version": partner["version"],
                "account_active": {"$ne": False},
                "kyc_status": "approved",
                "approval_status": "active",
            },
            {"$inc": {"referral_guard": 1}},
            session=session,
        )
        if not result.matched_count:
            raise ConflictError("Partner settings changed; refresh.")

    async def detail(self, application_id: str, actor: Any) -> dict[str, Any]:
        row = await self.own(application_id, actor)
        form = await self.customers._form_defs.find_by_id(row["form_definition_id"])
        # Return only the attributed Application, never the shared Customer's unrelated profile.
        return {
            "id": str(row["_id"]),
            "application_code": row["application_code"],
            "version": row["version"],
            "status": row["status"],
            "form_data": row["form_data"],
            "referral": row["referral_attribution"],
            "form": await self.form_payload(form) if form else None,
        }

    async def form_payload(self, form: Any) -> dict[str, Any]:
        from app.features.customer.router import _resolve_form_definition_response

        payload = (await _resolve_form_definition_response(self.customers, form)).model_dump(
            mode="json"
        )
        return {
            key: payload[key]
            for key in (
                "id",
                "product_category",
                "product_id",
                "product_name",
                "fields",
                "required_documents",
                "repeatable_groups",
            )
        }

    async def edit(self, application_id: str, payload: ReferralEdit, actor: Any) -> dict[str, Any]:
        row = await self.own(application_id, actor, edit=True)
        if len(json.dumps(payload.form_data).encode()) > 1024 * 1024:
            raise ValidationError("Application answers exceed the allowed size.")
        async with await self.db.client.start_session() as session, session.start_transaction():
            result = await self.db.applications.update_one(
                {
                    "_id": row["_id"],
                    "version": payload.version,
                    "status": "draft",
                    "referral_attribution.submitted_to_afs_at": None,
                },
                {
                    "$set": {
                        "form_data": payload.form_data,
                        "updated_at": utc_now(),
                        "updated_by": actor.require_id(),
                    },
                    "$inc": {"version": 1},
                },
                session=session,
            )
            if not result.matched_count:
                raise ConflictError("Referral changed; reload.")
            await event(
                self.db,
                actor,
                "partner_referral_draft_saved",
                row["referral_attribution"]["partner_id"],
                session=session,
                detail={"application_id": application_id},
            )
        return await self.detail(application_id, actor)

    async def submit(self, application_id: str, version: int, actor: Any) -> dict[str, Any]:
        row = await self.own(application_id, actor)
        attribution = row["referral_attribution"]
        if attribution.get("submitted_to_afs_at"):
            return await self.detail(application_id, actor)
        partner = await eligible(self.db, actor, row["product_id"])
        if row["version"] != version:
            raise ConflictError("Review the latest saved referral before submission.")
        application = Application.model_validate(row)
        await self.customers.validate_submission(application)
        now = utc_now()
        async with await self.db.client.start_session() as session, session.start_transaction():
            await self.guard(partner, session)
            result = await self.db.applications.update_one(
                {
                    "_id": row["_id"],
                    "version": version,
                    "referral_attribution.submitted_to_afs_at": None,
                },
                {
                    "$set": {
                        "status": "submitted",
                        "submitted_at": row.get("submitted_at") or now,
                        "referral_attribution.submitted_to_afs_at": now,
                        "referral_attribution.reviewed_by": actor.require_id(),
                        "referral_attribution.reviewed_at": now,
                        "auto_assignment_eligible": True,
                    },
                    "$inc": {"version": 1},
                },
                session=session,
            )
            if not result.matched_count:
                raise ConflictError("Referral changed; reload.")
            await event(
                self.db,
                actor,
                "partner_referral_submitted_to_afs",
                str(partner["_id"]),
                session=session,
                detail={
                    "application_id": application_id,
                    "referral_id": attribution["referral_id"],
                },
            )
        updated = await self.db.applications.find_one({"_id": row["_id"]})
        await self.customers._ensure_submitted_case(Application.model_validate(updated))
        return await self.detail(application_id, actor)

    async def link(self, payload: LinkInput, actor: Any) -> dict[str, Any]:
        partner = await eligible(self.db, actor, payload.product_id)
        previous = await self.db.partner_referral_links.find_one(
            {"partner_id": str(partner["_id"]), "request_id": payload.request_id}
        )
        if previous:
            if (
                previous["product_id"] != payload.product_id
                or previous.get("expires_days", 7) != payload.expires_days
            ):
                raise ConflictError("Link request key already used for another product or expiry.")
            return {
                "referral_id": previous["referral_id"],
                "expires_at": previous["expires_at"],
                "path": "/partner-referral#" + decrypt(previous["token_cipher"]),
            }
        token = secrets.token_urlsafe(32)
        reference = str(ObjectId())
        row = {
            "partner_id": str(partner["_id"]),
            "token_hash": hashlib.sha256(token.encode()).hexdigest(),
            "token_cipher": encrypt(token),
            "product_id": payload.product_id,
            "submission_mode": partner.get("submission_mode", "partner_review"),
            "referral_id": reference,
            "created_at": utc_now(),
            "expires_at": utc_now() + timedelta(days=payload.expires_days),
            "status": "active",
            "request_id": payload.request_id,
            "expires_days": payload.expires_days,
        }
        async with await self.db.client.start_session() as session, session.start_transaction():
            await self.guard(partner, session)
            await self.db.partner_referral_links.insert_one(row, session=session)
            await event(
                self.db,
                actor,
                "partner_referral_link_created",
                str(partner["_id"]),
                session=session,
                detail={"referral_id": reference},
            )
        return {
            "token": token,
            "referral_id": reference,
            "expires_at": row["expires_at"],
            "path": "/partner-referral#" + token,
        }

    async def redeem(self, token: str, actor: Any) -> dict[str, Any]:
        if actor.role != "customer":
            raise ForbiddenError("Sign in through the existing Customer login to use this link.")
        digest = hashlib.sha256(token.encode()).hexdigest()
        link = await self.db.partner_referral_links.find_one(
            {
                "token_hash": digest,
                "status": {"$in": ["active", "used"]},
                "expires_at": {"$gt": utc_now()},
            }
        )
        if not link or (link.get("user_id") and link["user_id"] != actor.require_id()):
            raise NotFoundError("Referral link expired, revoked or already used.")
        if link.get("application_id"):
            return {"application_id": link["application_id"]}
        partner = await self.db.referral_partners.find_one(
            {"_id": oid(link["partner_id"]), "is_deleted": False}
        )
        if not partner:
            raise NotFoundError("Partner unavailable.")
        partner_user = await self.db.users.find_one(
            {"_id": oid(partner["user_id"]), "is_deleted": False, "status": "active"}
        )
        if not partner_user:
            raise ForbiddenError("Partner unavailable.")
        await eligible(self.db, User.model_validate(partner_user), link["product_id"])
        form = await self.customers._get_or_error_form_definition("loan", link["product_id"])
        customer = await self.db.customers.find_one(
            {"user_id": actor.require_id(), "is_deleted": False}
        )
        attribution = {
            "partner_id": link["partner_id"],
            "partner_name": partner["full_name"],
            "referral_id": link["referral_id"],
            "source": "referral_partner",
            "origin": "link",
            "submission_mode": link["submission_mode"],
            "created_at": utc_now(),
            "submitted_to_afs_at": None,
        }
        async with await self.db.client.start_session() as session, session.start_transaction():
            await self.guard(partner, session)
            await guard_customer_referral(self.db, actor.require_id(), link["product_id"], session)
            result = await self.db.partner_referral_links.update_one(
                {"_id": link["_id"], "status": "active"},
                {"$set": {"status": "used", "user_id": actor.require_id()}},
                session=session,
            )
            if not result.matched_count:
                raise ConflictError(
                    "Link was just claimed. Reload to resume your existing Application."
                )
            application = await self.customers._create_application(
                user_id=actor.require_id(),
                customer_id=str(customer["_id"]) if customer else None,
                lead_id=None,
                product_category="loan",
                product_id=link["product_id"],
                form_definition=form,
                actor=actor,
                request_key=link["referral_id"],
                referral_attribution=attribution,
                session=session,
            )
            await self.db.partner_referral_links.update_one(
                {"_id": link["_id"]},
                {"$set": {"application_id": application.require_id()}},
                session=session,
            )
            await event(
                self.db,
                actor,
                "partner_referral_link_claimed",
                link["partner_id"],
                session=session,
                detail={
                    "application_id": application.require_id(),
                    "referral_id": link["referral_id"],
                },
            )
        return {"application_id": application.require_id()}


async def customer_submission_updates(
    db: Any, application: Application, actor: Any, at: Any
) -> dict[str, Any]:
    attribution = application.referral_attribution or {}
    if attribution.get("origin") != "link":
        raise ForbiddenError("Manual referrals require explicit Partner review and submission.")
    partner = await db.referral_partners.find_one(
        {"_id": oid(attribution["partner_id"]), "is_deleted": False}
    )
    if (
        not partner
        or not partner.get("account_active", True)
        or partner.get("kyc_status") != "approved"
        or partner.get("approval_status") != "active"
    ):
        raise ForbiddenError("The referring Partner is unavailable for submission. Contact AFS.")
    updates = {"referral_attribution.customer_submitted_at": at}
    if attribution["submission_mode"] == "direct_to_afs":
        updates["referral_attribution.submitted_to_afs_at"] = at
    return updates


async def activate_reserved_identity(
    db: Any, payload: Any, proof: dict[str, Any], proof_filter: dict[str, Any]
) -> bool:
    """Normal OTP-verified registration can activate only its exact manual reservation.

    Never claims historical identities by mobile alone, changes another role, or
    replaces existing credentials. Customer, User and Application IDs stay intact.
    """
    from app.security.pin import hash_pin

    query = {
        "mobile": payload.mobile,
        "role": "customer",
        "status": "pending_password",
        "provisioning_source": "partner_manual_referral",
        "is_deleted": False,
        "pin_hash": None,
        "password_hash": None,
        "is_mobile_verified": False,
    }
    reserved = await db.users.find_one(query)
    if not reserved:
        return False
    if proof.get("user_id") != str(reserved["_id"]):
        raise ConflictError(
            "This reservation changed after verification began. Request a new ownership verification."
        )
    if not await db.applications.find_one(
        {
            "user_id": str(reserved["_id"]),
            "referral_attribution.origin": "manual",
            "is_deleted": False,
        }
    ):
        raise ConflictError("Customer reservation requires Owner review.")
    hashed = hash_pin(payload.pin)
    now = utc_now()
    async with await db.client.start_session() as session, session.start_transaction():
        claimed = await db.auth_pin_challenges.update_one(
            proof_filter,
            {"$set": {"state": "consumed"}, "$unset": {"authorization_hash": ""}},
            session=session,
        )
        if not claimed.matched_count:
            raise ConflictError("Ownership verification was already used or expired.")
        result = await db.users.update_one(
            {**query, "_id": reserved["_id"]},
            {
                "$set": {
                    "status": "active",
                    "pin_hash": hashed,
                    "pin_epoch": 1,
                    "pin_updated_at": now,
                    "mobile_verified_at": now,
                    "is_mobile_verified": True,
                    "registration_method": "mobile_pin",
                    "provisioning_source": "partner_manual_referral_activated",
                },
                "$inc": {"version": 1},
            },
            session=session,
        )
        if not result.matched_count:
            raise ConflictError("Customer credentials changed; nothing was activated.")
        await event(
            db,
            User.model_validate(reserved),
            "partner_customer_reservation_activated",
            "identity",
            session=session,
            detail={"user_id": str(reserved["_id"]), "registration_method": "verified_mobile_pin"},
        )
    return True
