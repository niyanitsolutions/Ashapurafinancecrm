"""Transactional in-app notices; no external delivery claim or provider send."""

import hashlib
from typing import Any

from bson import ObjectId

from app.features.reminders.constants import NotificationCategory, NotificationType
from app.features.reminders.models import Notification


async def notify(db: Any, actor: Any, name: str, partner_id: str, session: Any) -> None:
    if any(
        fragment in name
        for fragment in ("viewed", "sensitive_fields", "draft", "link_created", "form_published")
    ):
        return
    if not ObjectId.is_valid(partner_id):
        return
    partner = await db.referral_partners.find_one({"_id": ObjectId(partner_id)}, session=session)
    if not partner:
        return
    recipients = [partner["user_id"]]
    if actor.role != "owner":
        recipients += [
            str(u["_id"])
            async for u in db.users.find(
                {"role": "owner", "status": "active", "is_deleted": False},
                {"_id": 1},
                session=session,
            ).limit(10)
        ]
    for user_id in dict.fromkeys(recipients):
        notification = Notification(
            recipient_user_id=user_id,
            notification_type=NotificationType.PARTNER_PORTAL,
            category=NotificationCategory.SYSTEM,
            title="Partner portal update",
            message=name.replace("_", " ").capitalize()
            + ". Open the Partner Portal or KYC Review for details.",
            entity_type="partner_commission"
            if "commission" in name
            else "partner_referral"
            if "referral" in name and "account" not in name
            else "referral_partner",
            entity_id=partner_id,
        )
        await db.notifications.insert_one(notification.model_dump(exclude={"id"}), session=session)


async def notify_updated_agreements(db: Any) -> dict[str, int]:
    """Advance a bounded existing notification checkpoint; retry is idempotent."""
    from app.utils.datetime import utc_now

    key = "partner_required_agreement_versions"
    checkpoint = await db.notification_checkpoints.find_one({"event_type": key}) or {}
    current_version = checkpoint.get("current_form_version")
    form = await db.partner_kyc_forms.find_one({}, sort=[("version", -1)])
    if not form or checkpoint.get("completed_form_version", 0) >= form["version"]:
        return {"notified": 0, "processed": 0}
    if current_version != form["version"]:
        current_version = None
    query: dict[str, Any] = {
        "is_deleted": False,
        "kyc_status": "approved",
        "account_active": {"$ne": False},
    }
    if current_version and checkpoint.get("last_partner_id"):
        query["_id"] = {"$gt": ObjectId(checkpoint["last_partner_id"])}
    partners = [
        p
        async for p in db.referral_partners.find(query, {"user_id": 1, "current_kyc_id": 1})
        .sort("_id", 1)
        .limit(100)
    ]
    submission_ids = [
        ObjectId(p["current_kyc_id"])
        for p in partners
        if ObjectId.is_valid(p.get("current_kyc_id"))
    ]
    submissions = {
        str(row["_id"]): row
        async for row in db.partner_kyc_submissions.find(
            {"_id": {"$in": submission_ids}}, {"accepted_agreement_ids": 1}
        )
    }
    count = 0
    async with await db.client.start_session() as session, session.start_transaction():
        for partner in partners:
            submission = submissions.get(partner.get("current_kyc_id"), {})
            if set(form["required_agreement_ids"]).issubset(
                submission.get("accepted_agreement_ids", [])
            ):
                continue
            notification = Notification(
                recipient_user_id=partner["user_id"],
                notification_type=NotificationType.PARTNER_PORTAL,
                category=NotificationCategory.SYSTEM,
                title="Partner agreement acceptance required",
                message="Required agreement versions changed. Open Complete KYC to read and accept the current versions before further referral activity.",
                entity_type="referral_partner",
                entity_id=str(partner["_id"]),
            )
            notification_id = ObjectId(
                hashlib.sha256(
                    (
                        "partner-agreements:"
                        + ",".join(sorted(form["required_agreement_ids"]))
                        + ":"
                        + partner["user_id"]
                    ).encode()
                ).hexdigest()[:24]
            )
            result = await db.notifications.update_one(
                {"_id": notification_id},
                {"$setOnInsert": notification.model_dump(exclude={"id"})},
                upsert=True,
                session=session,
            )
            count += int(result.upserted_id is not None)
        progress = {
            "last_processed_at": utc_now(),
            "completed_form_version": checkpoint.get("completed_form_version", 0),
            "current_form_version": form["version"],
            "last_partner_id": str(partners[-1]["_id"]) if partners else None,
        }
        if len(partners) < 100:
            progress.update(
                completed_form_version=form["version"],
                current_form_version=None,
                last_partner_id=None,
            )
        await db.notification_checkpoints.update_one(
            {"event_type": key}, {"$set": progress}, upsert=True, session=session
        )
    return {"notified": count, "processed": len(partners)}


async def notify_application_status(db: Any, case: Any, *, session: Any = None) -> None:
    """Only the attributed Partner receives a generic, idempotent status notice."""
    if not ObjectId.is_valid(case.application_id):
        return
    application = await db.applications.find_one(
        {"_id": ObjectId(case.application_id)},
        {"referral_attribution": 1, "lead_id": 1},
        session=session,
    )
    if not application:
        return
    attribution = application.get("referral_attribution") or {}
    partner_id = attribution.get("partner_id") if attribution.get("submitted_to_afs_at") else None
    if not partner_id and application.get("lead_id"):
        mapping = await db.referral_leads.find_one(
            {"lead_id": application["lead_id"], "is_deleted": False},
            {"partner_id": 1},
            session=session,
        )
        partner_id = mapping.get("partner_id") if mapping else None
    if not partner_id or not ObjectId.is_valid(partner_id):
        return
    partner = await db.referral_partners.find_one(
        {"_id": ObjectId(partner_id)}, {"user_id": 1}, session=session
    )
    if not partner:
        return
    notice_id = ObjectId(
        hashlib.sha256(
            (
                "partner-case-status:"
                + case.require_id()
                + ":"
                + str(case.version)
                + ":"
                + case.current_status
                + ":"
                + partner["user_id"]
            ).encode()
        ).hexdigest()[:24]
    )
    notice = Notification(
        recipient_user_id=partner["user_id"],
        notification_type=NotificationType.PARTNER_PORTAL,
        category=NotificationCategory.SYSTEM,
        title="Referral application updated",
        message="An attributed application has a status update. Open My Referrals to view its current customer-facing status.",
        entity_type="partner_referral",
        entity_id=case.application_id,
    )
    await db.notifications.update_one(
        {"_id": notice_id},
        {"$setOnInsert": notice.model_dump(exclude={"id"})},
        upsert=True,
        session=session,
    )
