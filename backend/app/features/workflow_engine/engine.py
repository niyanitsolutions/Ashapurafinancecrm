"""The generic Workflow Engine: validates and executes a status transition for ANY case
type, driven entirely by `WorkflowDefinition` rows (data), never by per-product-type
branching in this file. A future case type (e.g. a future BNPL or Gold Loan pipeline)
is a new set of `WorkflowDefinition` rows, not new code here — the same "engine is code,
catalog is data" split as Access Control's `PermissionEngine`/`Permission` catalog.

Every transition, in one call: validates the move is allowed, updates the case's
`current_status`, writes an `ApplicationStatusHistory` entry (the Timeline's status
half), writes an `audit_logs` entry (reusing the shared, append-only writer every
module uses), and publishes an in-process event via `event_engine` (no subscriber is
registered for it yet in this module — see `event_engine/bus.py` — so this is a
forward-compatible hook for a future Notification/Reminder module, not a working
notification path; "Notification/Reminder Trigger" stay honest placeholders).
"""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.event_engine.bus import publish
from app.features.workflow_engine.constants import WorkflowAuditEvent
from app.features.workflow_engine.models import (
    ApplicationStatusHistory,
    ApplicationWorkflow,
    WorkflowDefinition,
)
from app.features.workflow_engine.repository import (
    ApplicationStatusHistoryRepository,
    ApplicationWorkflowRepository,
    WorkflowDefinitionRepository,
)
from app.shared.audit_log import write_audit_log

STATUS_CHANGED_EVENT = "workflow.status_changed"


class WorkflowEngine:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self._db = db
        self._definitions = WorkflowDefinitionRepository(db)
        self._workflows = ApplicationWorkflowRepository(db)
        self._history = ApplicationStatusHistoryRepository(db)

    @property
    def db(self) -> AsyncIOMotorDatabase[Any]:
        return self._db

    async def get_definition(self, case_type: str, status: str) -> WorkflowDefinition:
        definition = await self._definitions.find_by_case_type_status(case_type, status)
        if definition is None:
            raise NotFoundError(f"No workflow definition for {case_type}:{status} — seed data may be missing.")
        return definition

    async def assert_transition_allowed(self, case_type: str, from_status: str, to_status: str) -> WorkflowDefinition:
        current = await self.get_definition(case_type, from_status)
        if to_status not in current.allowed_next_statuses:
            raise ValidationError(f"Invalid status transition: {from_status} -> {to_status} is not allowed for {case_type} cases.")
        return current

    async def transition(
        self, workflow: ApplicationWorkflow, to_status: str, actor: User, *, updates: dict[str, Any] | None = None, remarks: str | None = None
    ) -> ApplicationWorkflow:
        from_status = workflow.current_status
        await self.assert_transition_allowed(workflow.case_type, from_status, to_status)
        target_definition = await self.get_definition(workflow.case_type, to_status)

        set_updates: dict[str, Any] = {**(updates or {}), "current_status": to_status}
        updated = await self._workflows.update(workflow.require_id(), set_updates, updated_by=actor.require_id())
        if updated is None:
            raise NotFoundError("Case not found.")

        await self._history.insert(
            ApplicationStatusHistory(
                application_workflow_id=workflow.require_id(), case_type=workflow.case_type,
                from_status=from_status, to_status=to_status, remarks=remarks, created_by=actor.require_id(),
            )
        )
        await write_audit_log(
            self._db, event_type=target_definition.audit_event, user_id=actor.require_id(),
            metadata={"application_workflow_id": workflow.require_id(), "from_status": from_status, "to_status": to_status},
        )
        await publish(
            STATUS_CHANGED_EVENT,
            {
                "application_workflow_id": workflow.require_id(), "case_type": workflow.case_type,
                "from_status": from_status, "to_status": to_status,
                "notification_trigger_key": target_definition.notification_trigger_key,
                "reminder_trigger_key": target_definition.reminder_trigger_key,
            },
        )
        return updated

    async def create_case(
        self, *, case_code: str, case_type: str, application_id: str, customer_id: str, product_id: str,
        product_category: str, assigned_to: str | None, actor_id: str | None, initial_status: str,
        loan_details: Any = None, insurance_details: Any = None,
    ) -> ApplicationWorkflow:
        workflow = ApplicationWorkflow(
            case_code=case_code, case_type=case_type, application_id=application_id, customer_id=customer_id,
            product_id=product_id, product_category=product_category, assigned_to=assigned_to,
            current_status=initial_status, loan_details=loan_details, insurance_details=insurance_details,
            created_by=actor_id,
        )
        workflow_id = await self._workflows.insert(workflow)
        created = await self._workflows.find_by_id(workflow_id)
        assert created is not None

        await self._history.insert(
            ApplicationStatusHistory(
                application_workflow_id=workflow_id, case_type=case_type, from_status=None,
                to_status=initial_status, created_by=actor_id,
            )
        )
        definition = await self.get_definition(case_type, initial_status)
        await write_audit_log(
            self._db, event_type=WorkflowAuditEvent.CASE_CREATED, user_id=actor_id,
            metadata={"application_workflow_id": workflow_id, "case_type": case_type, "application_id": application_id},
        )
        await publish(
            STATUS_CHANGED_EVENT,
            {
                "application_workflow_id": workflow_id, "case_type": case_type, "from_status": None,
                "to_status": initial_status, "notification_trigger_key": definition.notification_trigger_key,
                "reminder_trigger_key": definition.reminder_trigger_key,
            },
        )
        return created
