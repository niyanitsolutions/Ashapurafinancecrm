import re
from typing import Any

from app.features.referral_partner_management.constants import CommissionEntryStatus
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
        self, *, search: str | None, approval_status: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None
    ) -> tuple[list[ReferralPartner], int]:
        query: dict[str, Any] = {"is_deleted": False}
        if approval_status:
            query["approval_status"] = approval_status
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
        pending = await self._sum(partner_id, CommissionEntryStatus.PENDING)
        approved = await self._sum(partner_id, CommissionEntryStatus.APPROVED)
        paid = await self._sum(partner_id, CommissionEntryStatus.PAID)
        return {"pending": pending, "approved": approved, "paid": paid, "balance": pending + approved}

    async def _sum(self, partner_id: str, status: str) -> float:
        cursor = self.collection.aggregate(
            [
                {"$match": {"partner_id": partner_id, "status": status, "is_deleted": False}},
                {"$group": {"_id": None, "total": {"$sum": "$commission_amount"}}},
            ]
        )
        async for doc in cursor:
            return float(doc["total"])
        return 0.0
