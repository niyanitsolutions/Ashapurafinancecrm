import re
from typing import Any

from app.features.workflow_engine.models import (
    ApplicationDecision,
    ApplicationNote,
    ApplicationStatusHistory,
    ApplicationWorkflow,
    WorkflowDefinition,
)
from app.shared.base_repository import BaseRepository

_SEARCH_FIELDS = ("case_code",)


class WorkflowDefinitionRepository(BaseRepository[WorkflowDefinition]):
    collection_name = "workflow_definitions"
    model = WorkflowDefinition

    async def find_by_case_type_status(self, case_type: str, status: str) -> WorkflowDefinition | None:
        doc = await self.collection.find_one({"case_type": case_type, "status": status, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None

    async def find_for_case_type(self, case_type: str) -> list[WorkflowDefinition]:
        return await self.find_many({"case_type": case_type}, limit=50, sort=[("sequence", 1)])


class ApplicationWorkflowRepository(BaseRepository[ApplicationWorkflow]):
    collection_name = "application_workflows"
    model = ApplicationWorkflow

    async def find_by_application_id(self, application_id: str) -> ApplicationWorkflow | None:
        doc = await self.collection.find_one({"application_id": application_id, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None

    async def find_existing_application_ids(self, case_type: str) -> set[str]:
        cursor = self.collection.find({"case_type": case_type, "is_deleted": False}, {"application_id": 1})
        return {doc["application_id"] async for doc in cursor}

    async def search_and_filter(
        self,
        *,
        case_type: str,
        search: str | None,
        customer_id: str | None,
        assigned_to: str | None,
        unassigned_only: bool = False,
        status: str | None,
        skip: int,
        limit: int,
        sort: list[tuple[str, int]] | None,
        extra_filter: dict[str, Any] | None = None,
    ) -> tuple[list[ApplicationWorkflow], int]:
        query: dict[str, Any] = {"is_deleted": False, "case_type": case_type}
        if unassigned_only:
            query["assigned_to"] = None
        elif assigned_to:
            query["assigned_to"] = assigned_to
        if status:
            query["current_status"] = status
        if customer_id:
            query["customer_id"] = customer_id
        if search:
            pattern = re.compile(re.escape(search), re.IGNORECASE)
            query["$or"] = [{field: pattern} for field in _SEARCH_FIELDS]
        if extra_filter:
            query.update(extra_filter)

        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        items = [self.model.model_validate(doc) async for doc in cursor]
        return items, total

    async def find_for_customer(self, customer_id: str, case_type: str) -> list[ApplicationWorkflow]:
        return await self.find_many({"customer_id": customer_id, "case_type": case_type}, limit=200, sort=[("created_at", -1)])

    async def count_filtered(
        self, *, case_type: str, status: str, assigned_to: str | None = None, unassigned_only: bool = False,
        extra_filter: dict[str, Any] | None = None,
    ) -> int:
        """Same query-building as `search_and_filter`'s status/assigned_to branch,
        without paginating — backs a status-tab count badge (e.g.
        `LoanCaseService.get_counts`) so a count can never disagree with what its
        matching list call actually returns."""
        query: dict[str, Any] = {"is_deleted": False, "case_type": case_type, "current_status": status}
        if unassigned_only:
            query["assigned_to"] = None
        elif assigned_to:
            query["assigned_to"] = assigned_to
        if extra_filter:
            query.update(extra_filter)
        return await self.collection.count_documents(query)


class ApplicationStatusHistoryRepository(BaseRepository[ApplicationStatusHistory]):
    collection_name = "application_status_history"
    model = ApplicationStatusHistory

    async def find_for_workflow(self, application_workflow_id: str) -> list[ApplicationStatusHistory]:
        return await self.find_many({"application_workflow_id": application_workflow_id}, limit=200, sort=[("created_at", -1)])


class ApplicationNoteRepository(BaseRepository[ApplicationNote]):
    collection_name = "application_notes"
    model = ApplicationNote

    async def find_for_workflow(self, application_workflow_id: str) -> list[ApplicationNote]:
        return await self.find_many({"application_workflow_id": application_workflow_id}, limit=200, sort=[("created_at", -1)])


class ApplicationDecisionRepository(BaseRepository[ApplicationDecision]):
    collection_name = "application_decisions"
    model = ApplicationDecision

    async def find_for_workflow(self, application_workflow_id: str) -> list[ApplicationDecision]:
        return await self.find_many({"application_workflow_id": application_workflow_id}, limit=200, sort=[("created_at", -1)])
