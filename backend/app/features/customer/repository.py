import re
from typing import Any

from app.features.customer.constants import ApplicationStatus
from app.features.customer.models import (
    Application,
    ApplicationDocument,
    ApplicationFormDefinition,
    Customer,
    FormTemplateMaster,
    SecureLink,
)
from app.shared.base_repository import BaseRepository

_SEARCH_FIELDS = ("customer_code", "full_name", "mobile", "email")


class CustomerRepository(BaseRepository[Customer]):
    collection_name = "customers"
    model = Customer

    async def find_by_user_id(self, user_id: str) -> Customer | None:
        doc = await self.collection.find_one({"user_id": user_id, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None

    async def find_by_lead_id(self, lead_id: str) -> Customer | None:
        doc = await self.collection.find_one({"converted_from_lead_id": lead_id, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None

    async def search_and_filter(
        self, *, search: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None
    ) -> tuple[list[Customer], int]:
        query: dict[str, Any] = {"is_deleted": False}
        if search:
            pattern = re.compile(re.escape(search), re.IGNORECASE)
            query["$or"] = [{field: pattern} for field in _SEARCH_FIELDS]
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        items = [self.model.model_validate(doc) async for doc in cursor]
        return items, total


class ApplicationFormDefinitionRepository(BaseRepository[ApplicationFormDefinition]):
    collection_name = "application_form_definitions"
    model = ApplicationFormDefinition

    async def find_by_product(self, product_category: str, product_id: str) -> ApplicationFormDefinition | None:
        """The shared read every portal's dynamic form uses — only ever returns an
        ACTIVE schema, so an Owner can build/edit a DRAFT without it going live, and
        ARCHIVED retires one without deleting it. Admin lookups (list/edit) use
        `find_by_id`/`find_many` directly and see every status."""
        doc = await self.collection.find_one(
            {"product_category": product_category, "product_id": product_id, "status": "active", "is_deleted": False}
        )
        return self.model.model_validate(doc) if doc else None

    async def find_any_by_product(self, product_category: str, product_id: str) -> ApplicationFormDefinition | None:
        """Status-agnostic — used for the "one schema per product" uniqueness check on
        create, so a DRAFT doesn't let a second schema be created for the same product."""
        doc = await self.collection.find_one({"product_category": product_category, "product_id": product_id, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None

    async def find_all_versions_by_product(self, product_category: str, product_id: str) -> list[ApplicationFormDefinition]:
        """Governance round — every version (active + draft + archived) of a product's
        schema, newest first. Used by Compare (§7) and to resolve one specific
        `version` number for it."""
        return await self.find_many(
            {"product_category": product_category, "product_id": product_id}, limit=500, sort=[("version", -1)]
        )


class FormTemplateMasterRepository(BaseRepository[FormTemplateMaster]):
    """Governance round — the client's official spec per product, written only by
    `scripts/apply_product_schema.py`. No service method here ever creates/updates one
    through an API request; this repository exists so the migration script (which does
    run inside the app's own Motor connection) can reuse the same model validation as
    everything else, not to back a CRUD endpoint."""

    collection_name = "form_template_masters"
    model = FormTemplateMaster

    async def find_by_product(self, product_category: str, product_id: str) -> FormTemplateMaster | None:
        doc = await self.collection.find_one({"product_category": product_category, "product_id": product_id, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None


class ApplicationRepository(BaseRepository[Application]):
    collection_name = "applications"
    model = Application

    async def find_for_user(self, user_id: str, *, status: str | None = None) -> list[Application]:
        query: dict[str, Any] = {"user_id": user_id, "is_deleted": False}
        if status:
            query["status"] = status
        return await self.find_many(query, limit=200, sort=[("created_at", -1)])

    async def find_pending_conversion_for_user(self, user_id: str) -> Application | None:
        """Unified onboarding — a Flow-1 (secure-link) application this user has already
        started but not yet converted to a real `Customer`. Used by
        `CustomerService.complete_profile` to link the two the moment the customer
        finishes their one profile step, instead of waiting for submission."""
        doc = await self.collection.find_one(
            {"user_id": user_id, "customer_id": None, "lead_id": {"$ne": None}, "status": ApplicationStatus.DRAFT, "is_deleted": False}
        )
        return self.model.model_validate(doc) if doc else None

    async def search_and_filter(
        self,
        *,
        search: str | None,
        customer_id: str | None,
        assigned_to: str | None,
        unassigned_only: bool = False,
        status: str | None,
        product_category: str | None,
        skip: int,
        limit: int,
        sort: list[tuple[str, int]] | None,
    ) -> tuple[list[Application], int]:
        query: dict[str, Any] = {"is_deleted": False}
        if customer_id:
            query["customer_id"] = customer_id
        if unassigned_only:
            # The "Unassigned Applications" queue — deliberately takes precedence over
            # `assigned_to` (the two are mutually exclusive filters).
            query["assigned_to"] = None
        elif assigned_to:
            query["assigned_to"] = assigned_to
        if status:
            query["status"] = status
        if product_category:
            query["product_category"] = product_category
        if search:
            pattern = re.compile(re.escape(search), re.IGNORECASE)
            query["$or"] = [{"application_code": pattern}]

        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        items = [self.model.model_validate(doc) async for doc in cursor]
        return items, total


class ApplicationDocumentRepository(BaseRepository[ApplicationDocument]):
    collection_name = "application_documents"
    model = ApplicationDocument

    async def find_for_application(self, application_id: str) -> list[ApplicationDocument]:
        return await self.find_many({"application_id": application_id}, limit=100)


class SecureLinkRepository(BaseRepository[SecureLink]):
    collection_name = "secure_links"
    model = SecureLink

    async def find_by_code(self, secure_code: str) -> SecureLink | None:
        doc = await self.collection.find_one({"secure_code": secure_code, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None

    async def code_exists(self, secure_code: str) -> bool:
        return await self.collection.count_documents({"secure_code": secure_code}, limit=1) > 0

    async def find_active_for_lead(self, lead_id: str) -> list[SecureLink]:
        return await self.find_many({"lead_id": lead_id, "status": "active"}, limit=50)

    async def find_latest_for_lead(self, lead_id: str) -> SecureLink | None:
        # `_id` as a tiebreaker: BSON datetimes truncate to millisecond precision, so two
        # links generated in rapid succession (e.g. "Regenerate" clicked twice quickly,
        # or in a fast test) can share an identical stored `created_at` — `_id` embeds a
        # monotonic counter that still orders them correctly when that happens.
        results = await self.find_many({"lead_id": lead_id}, limit=1, sort=[("created_at", -1), ("_id", -1)])
        return results[0] if results else None
