import re
from typing import Any

from app.features.leads.models import Lead, LeadActivity, LeadNote
from app.shared.base_repository import BaseRepository

_SEARCH_FIELDS = ("lead_code", "full_name", "mobile", "email")

# Sentinel values for the `assigned_to` filter, additive to the existing exact-employee-id
# match — lets New Leads / Assigned Leads tabs filter by assignment presence server-side
# (needed for correct pagination) without adding a new query param or touching assign/
# unassign logic.
UNASSIGNED_SENTINEL = "__unassigned__"
ASSIGNED_SENTINEL = "__assigned__"
# Guaranteed to match zero leads — used by LeadService to force an empty result set for
# an Employee-role actor with no Employee record (defensive; shouldn't normally happen),
# rather than silently falling through to an unrestricted query.
NO_MATCH_SENTINEL = "__no_match__"


class LeadRepository(BaseRepository[Lead]):
    collection_name = "leads"
    model = Lead

    async def find_by_mobile(self, mobile: str, *, exclude_id: str | None = None) -> list[Lead]:
        query: dict[str, Any] = {"mobile": mobile, "is_deleted": False}
        if exclude_id:
            from app.utils.helpers import to_object_id

            query["_id"] = {"$ne": to_object_id(exclude_id)}
        cursor = self.collection.find(query)
        return [self.model.model_validate(doc) async for doc in cursor]

    async def search_and_filter(
        self,
        *,
        search: str | None,
        source_id: str | None,
        product_category: str | None,
        product_id: str | None,
        assigned_to: str | None,
        status: str | None,
        skip: int,
        limit: int,
        sort: list[tuple[str, int]] | None,
    ) -> tuple[list[Lead], int]:
        query: dict[str, Any] = {"is_deleted": False}
        if source_id:
            query["source_id"] = source_id
        if product_category:
            query["product_category"] = product_category
        if product_id:
            query["product_id"] = product_id
        if assigned_to == UNASSIGNED_SENTINEL:
            query["assigned_to"] = None
        elif assigned_to == ASSIGNED_SENTINEL:
            query["assigned_to"] = {"$ne": None}
        elif assigned_to:
            query["assigned_to"] = assigned_to
        if status:
            query["status"] = status
        if search:
            pattern = re.compile(re.escape(search), re.IGNORECASE)
            query["$or"] = [{field: pattern} for field in _SEARCH_FIELDS]

        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        items = [self.model.model_validate(doc) async for doc in cursor]
        return items, total


class LeadNoteRepository(BaseRepository[LeadNote]):
    collection_name = "lead_notes"
    model = LeadNote

    async def find_for_lead(self, lead_id: str) -> list[LeadNote]:
        return await self.find_many({"lead_id": lead_id}, limit=500, sort=[("created_at", -1)])


class LeadActivityRepository(BaseRepository[LeadActivity]):
    collection_name = "lead_activities"
    model = LeadActivity

    async def find_for_lead(self, lead_id: str) -> list[LeadActivity]:
        return await self.find_many({"lead_id": lead_id}, limit=500, sort=[("created_at", -1)])

    async def find_assigned_for_employees(self, employee_ids: list[str]) -> list[LeadActivity]:
        return await self.find_many({"event_type": "assigned", "metadata.employee_id": {"$in": employee_ids}}, limit=5000)
