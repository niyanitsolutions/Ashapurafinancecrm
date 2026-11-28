import re
from typing import Any

from app.features.referral_partner_management.models import (
    CommissionEntry,
    CommissionRule,
    ReferralLead,
    ReferralPartner,
)
from app.shared.base_repository import BaseRepository

_PARTNER_SEARCH_FIELDS = ("partner_code", "full_name", "mobile", "email", "business_name")


class ReferralPartnerRepository(BaseRepository[ReferralPartner]):
    collection_name = "referral_partners"
    model = ReferralPartner

    async def find_by_user_id(self, user_id: str) -> ReferralPartner | None:
        doc = await self.collection.find_one({"user_id": user_id, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None

    async def search_and_filter(
        self, *, search: str | None, approval_status: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None, kyc_status: str | None = None
    ) -> tuple[list[ReferralPartner], int]:
        query: dict[str, Any] = {"is_deleted": False}
        if approval_status:
            query["approval_status"] = approval_status
        if kyc_status == "pending":
            query["kyc_status"] = {"$in": [None, "pending"]}
        elif kyc_status == "suspended":
            query["account_active"] = False
        elif kyc_status:
            query["kyc_status"] = kyc_status
        if search:
            pattern = re.compile(re.escape(search), re.IGNORECASE)
            query["$or"] = [{field: pattern} for field in _PARTNER_SEARCH_FIELDS]
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        items = [self.model.model_validate(doc) async for doc in cursor]
        return items, total


class ReferralLeadRepository(BaseRepository[ReferralLead]):
    collection_name = "referral_leads"
    model = ReferralLead

    async def find_by_lead_id(self, lead_id: str) -> ReferralLead | None:
        doc = await self.collection.find_one({"lead_id": lead_id, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None

    async def find_for_partner(self, partner_id: str, *, skip: int = 0, limit: int = 200) -> tuple[list[ReferralLead], int]:
        query = {"partner_id": partner_id, "is_deleted": False}
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        items = [self.model.model_validate(doc) async for doc in cursor]
        return items, total

    async def find_all_for_partner(self, partner_id: str) -> list[ReferralLead]:
        return await self.find_many({"partner_id": partner_id}, limit=10000)


class CommissionRuleRepository(BaseRepository[CommissionRule]):
    collection_name = "commission_rules"
    model = CommissionRule

    async def find_candidates(self, *, product_category: str, partner_id: str) -> list[CommissionRule]:
        """Every active rule that could apply to this (partner, product_category) pair —
        partner-specific or default, this-product or all-products. The service picks the
        most specific match; this just narrows the candidate set."""
        query = {
            "status": "active",
            "is_deleted": False,
            "partner_id": {"$in": [partner_id, None]},
            "product_category": {"$in": [product_category, None]},
        }
        return await self.find_many(query, limit=50)


class CommissionEntryRepository(BaseRepository[CommissionEntry]):
    collection_name = "commission_entries"
    model = CommissionEntry

    async def find_existing_for_case(self, case_id: str) -> CommissionEntry | None:
        doc = await self.collection.find_one({"case_id": case_id, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None

    async def search_and_filter(
        self, *, partner_id: str | None, status: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None
    ) -> tuple[list[CommissionEntry], int]:
        query: dict[str, Any] = {"is_deleted": False}
        if partner_id:
            query["partner_id"] = partner_id
        if status:
            query["status"] = status
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        items = [self.model.model_validate(doc) async for doc in cursor]
        return items, total

    async def summary_for_partner(self, partner_id: str) -> dict[str, float]:
        rows = [row async for row in self.collection.aggregate([
            {"$match": {"partner_id": partner_id, "is_deleted": False}},
            {"$set": {"actual_paid": {"$ifNull": ["$paid_amount", {"$cond": [{"$eq": ["$status", "paid"]}, "$commission_amount", 0]}]}, "gross": {"$add": ["$commission_amount", {"$ifNull": ["$additional_earned_amount", 0]}, {"$ifNull": ["$adjusted_amount", 0]}]}}},
            {"$group": {"_id": "$status", "balance": {"$sum": {"$max": [0, {"$subtract": ["$gross", "$actual_paid"]}]}}, "paid": {"$sum": "$actual_paid"}}},
        ])]
        totals = {row["_id"]: round(row["balance"], 2) for row in rows}
        return {"pending": totals.get("pending", 0), "approved": totals.get("approved", 0), "paid": round(sum(row["paid"] for row in rows), 2), "balance": round(sum(totals.values()), 2)}
