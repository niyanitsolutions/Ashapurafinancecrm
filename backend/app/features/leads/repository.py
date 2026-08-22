import re
from typing import Any

from app.features.leads.models import Lead, LeadActivity, LeadNote
from app.shared.base_repository import BaseRepository
from app.utils.datetime import end_of_day_ist, start_of_day_ist

_SEARCH_FIELDS = ("lead_code", "full_name", "mobile", "email")

# Sentinel values for the `assigned_to` filter, additive to the existing exact-employee-id
# match — lets New Leads / Assigned Leads tabs filter by assignment presence server-side
# (needed for correct pagination) without adding a new query param or touching assign/
# unassign logic.
UNASSIGNED_SENTINEL = "__unassigned__"
ASSIGNED_SENTINEL = "__assigned__"
# "The acting employee themselves" — resolved server-side by LeadService._scope_query,
# never trusted as a literal employee id from the client. Backs the "My Leads" tab and
# Create/Edit Lead's "Assign To: Self" option (decision 125) with one shared mechanism.
SELF_SENTINEL = "__self__"
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

    def _build_query(
        self,
        *,
        search: str | None,
        source_id: str | None,
        product_category: str | None,
        product_id: str | None,
        assigned_to: str | None,
        created_by: str | None,
        status: str | None,
        stage: str | None,
        exclude_stage: str | None,
    ) -> dict[str, Any]:
        query: dict[str, Any] = {"is_deleted": False}
        if source_id:
            query["source_id"] = source_id
        if product_category:
            query["product_category"] = product_category
        if product_id:
            query["product_id"] = product_id
        if assigned_to == UNASSIGNED_SENTINEL:
            query["assigned_to"] = None
            # `created_by` is only ever passed alongside UNASSIGNED_SENTINEL, by a
            # non-Owner actor — see LeadService._scope_query. It narrows the query with
            # AND (not OR): "unassigned AND created by me," i.e. my own not-yet-assigned
            # drafts only, never every employee's unassigned pool.
            if created_by:
                query["created_by"] = created_by
        elif assigned_to == ASSIGNED_SENTINEL:
            query["assigned_to"] = {"$ne": None}
        elif assigned_to:
            query["assigned_to"] = assigned_to
        if status:
            query["status"] = status
        # `stage`/`exclude_stage` are mutually exclusive by caller convention (see
        # LeadService's tab-scoped list/count methods) — never both passed for the same
        # call, so no precedence rule between them is needed here.
        if stage:
            query["stage"] = stage
        if exclude_stage:
            query["stage"] = {"$ne": exclude_stage}
        if search:
            pattern = re.compile(re.escape(search), re.IGNORECASE)
            query["$or"] = [{field: pattern} for field in _SEARCH_FIELDS]
        return query

    async def search_and_filter(
        self,
        *,
        search: str | None,
        source_id: str | None,
        product_category: str | None,
        product_id: str | None,
        assigned_to: str | None,
        created_by: str | None = None,
        status: str | None,
        stage: str | None = None,
        exclude_stage: str | None = None,
        skip: int,
        limit: int,
        sort: list[tuple[str, int]] | None,
    ) -> tuple[list[Lead], int]:
        query = self._build_query(
            search=search, source_id=source_id, product_category=product_category, product_id=product_id,
            assigned_to=assigned_to, created_by=created_by, status=status, stage=stage, exclude_stage=exclude_stage,
        )
        total = await self.collection.count_documents(query)
        if sort:
            # An explicit sort was requested (e.g. CSV export's created_at desc) — unchanged.
            cursor = self.collection.find(query).skip(skip).limit(limit).sort(sort)
            items = [self.model.model_validate(doc) async for doc in cursor]
        else:
            items = await self._find_with_follow_up_priority(query, skip=skip, limit=limit)
        return items, total

    async def _find_with_follow_up_priority(self, query: dict[str, Any], *, skip: int, limit: int) -> list[Lead]:
        """Default ordering for every Leads list view with no explicit sort requested
        (production bug fix): Past follow-ups, then Today's, then Future, then leads
        with no follow-up date at all — chronological within each group. Previously the
        list had no explicit sort at all here, so it fell back to MongoDB's natural
        (roughly insertion) order, which is neither this priority ordering nor a plain
        chronological one. Computed once, server-side, entirely BEFORE `$skip`/`$limit`
        — pagination can never see a partially-sorted page. Bucket boundaries use the
        same business-timezone (IST) "today" the rest of the app already computes
        follow-up colors from (`start_of_day_ist`/`end_of_day_ist`), so a lead's bucket
        here always agrees with the red/blue/green it renders as on the frontend."""
        today_start = start_of_day_ist()
        today_end = end_of_day_ist()
        pipeline: list[dict[str, Any]] = [
            {"$match": query},
            {
                "$addFields": {
                    "_follow_up_rank": {
                        "$switch": {
                            "branches": [
                                {"case": {"$eq": ["$next_follow_up_date", None]}, "then": 3},
                                {"case": {"$lt": ["$next_follow_up_date", today_start]}, "then": 0},
                                {"case": {"$lt": ["$next_follow_up_date", today_end]}, "then": 1},
                            ],
                            "default": 2,
                        }
                    }
                }
            },
            {"$sort": {"_follow_up_rank": 1, "next_follow_up_date": 1, "created_at": -1}},
            {"$skip": skip},
            {"$limit": limit},
        ]
        docs = await self.collection.aggregate(pipeline).to_list(length=limit)
        return [self.model.model_validate(doc) for doc in docs]

    async def count_filtered(
        self,
        *,
        assigned_to: str | None = None,
        created_by: str | None = None,
        stage: str | None = None,
        exclude_stage: str | None = None,
    ) -> int:
        """Same query-building as `search_and_filter`, without paginating — backs the
        tab count badges (`LeadService.get_tab_counts`) so a count can never disagree
        with what its matching list call actually returns."""
        query = self._build_query(
            search=None, source_id=None, product_category=None, product_id=None,
            assigned_to=assigned_to, created_by=created_by, status=None, stage=stage, exclude_stage=exclude_stage,
        )
        return await self.collection.count_documents(query)


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
