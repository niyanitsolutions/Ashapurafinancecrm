"""On Hold / Resume — a generic capability of the Workflow Engine, usable by any case
type via its own `WorkflowDefinition` rows (an "Optional Status" every non-terminal
status can transition into and back out of), not a hardcoded branch per pipeline.

`put_on_hold` records the case's current status before moving it to the shared
`on_hold` status; `resume` reads that recorded status back out and transitions there —
both are just the existing generic `WorkflowEngine.transition()`, so no new engine
validation logic is needed: `on_hold`'s own `allowed_next_statuses` (seeded per case
type) is what actually constrains which statuses a resume can land on.
"""

from app.core.exceptions import ConflictError, ValidationError
from app.features.auth.models import User
from app.features.workflow_engine.constants import ON_HOLD_STATUS, WorkflowAuditEvent
from app.features.workflow_engine.engine import WorkflowEngine
from app.features.workflow_engine.models import ApplicationWorkflow
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now


async def put_on_hold(engine: WorkflowEngine, case: ApplicationWorkflow, reason: str, actor: User, *, remarks: str | None = None) -> ApplicationWorkflow:
    if case.current_status == ON_HOLD_STATUS:
        raise ConflictError("This case is already on hold.")
    return await engine.transition(
        case, ON_HOLD_STATUS, actor,
        updates={"on_hold_previous_status": case.current_status, "on_hold_reason": reason, "on_hold_since": utc_now()},
        remarks=remarks,
    )


async def resume_case(engine: WorkflowEngine, case: ApplicationWorkflow, actor: User) -> ApplicationWorkflow:
    if case.current_status != ON_HOLD_STATUS:
        raise ConflictError("This case is not on hold.")
    previous_status = case.on_hold_previous_status
    if not previous_status:
        raise ValidationError("No previous status was recorded to resume into.")
    resumed = await engine.transition(
        case, previous_status, actor,
        updates={"on_hold_previous_status": None, "on_hold_reason": None, "on_hold_since": None},
    )
    await write_audit_log(
        engine.db, event_type=WorkflowAuditEvent.CASE_RESUMED, user_id=actor.require_id(),
        metadata={"application_workflow_id": case.require_id(), "resumed_to": previous_status},
    )
    return resumed
