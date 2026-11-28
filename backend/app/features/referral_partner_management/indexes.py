from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_referral_partner_management_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["referral_partners"].create_index("user_id", unique=True)
    await db["referral_partners"].create_index("approval_status")

    await db["referral_leads"].create_index("lead_id", unique=True)
    await db["referral_leads"].create_index("partner_id")

    await db["commission_rules"].create_index([("product_category", 1), ("partner_id", 1)])

    await db["commission_entries"].create_index("case_id", unique=True)
    await db["commission_entries"].create_index([("partner_id", 1), ("status", 1)])

    await db.partner_kyc_forms.create_index("version", unique=True)
    await db.partner_kyc_submissions.create_index([("partner_id", 1), ("created_at", -1)])
    await db.partner_kyc_documents.create_index([("partner_id", 1), ("category", 1), ("current", 1)])
    await db.partner_kyc_uploads.create_index("ticket_hash", unique=True)
    # Staging object cleanup is operationally required; Mongo TTL removes only tickets.
    await db.partner_kyc_uploads.create_index("expires_at", expireAfterSeconds=86400)

    await db.commission_payouts.create_index([("entry_id", 1), ("confirmed_at", -1)])
    await db.commission_payouts.create_index([("partner_id", 1), ("confirmed_at", -1)])
    await db.commission_exceptions.create_index([("disbursement_event_source", 1), ("disbursement_event_id", 1)], unique=True)

    await db.partner_referral_links.create_index("token_hash", unique=True)
    await db.partner_referral_links.create_index([("partner_id", 1), ("created_at", -1)])
    await db.partner_referral_links.create_index([("partner_id", 1), ("request_id", 1)], unique=True)
    await db.applications.create_index("referral_attribution.request_key", unique=True, partialFilterExpression={"referral_attribution.request_key": {"$type": "string"}})
    await db.applications.create_index([("referral_attribution.partner_id", 1), ("created_at", -1)])

    await db.commission_entry_events.create_index("financial_event_key", unique=True, partialFilterExpression={"financial_event_key": {"$type": "string"}})
    await db.commission_entry_events.create_index([("entry_id", 1), ("created_at", -1)])

    await db.commission_exceptions.create_index([("status", 1), ("created_at", -1)])

    await db.commission_payouts.create_index("payment_key", unique=True, partialFilterExpression={"payment_key": {"$type": "string"}})
    await db.commission_payouts.create_index([("status", 1), ("created_at", -1)])
