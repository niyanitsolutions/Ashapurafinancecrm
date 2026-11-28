"""Shared Loan Management disbursement; Daily Update contributes no second ledger."""

from decimal import Decimal, InvalidOperation
from typing import Any

from bson import ObjectId
from pymongo.errors import OperationFailure

from app.core.exceptions import ConflictError, ValidationError
from app.features.workflow_engine.constants import LoanStatus
from app.features.workflow_engine.models import ApplicationWorkflow
from app.shared.audit_log import AuditLog
from app.utils.datetime import ist_date_to_utc_midnight, to_ist, utc_now


async def disburse(
    service: Any, case_id: str, payload: Any, actor: Any, *, followup: Any = None
) -> ApplicationWorkflow:
    case = await service.get_case(case_id, actor)
    if case.current_status != LoanStatus.SEND_FOR_DISBURSEMENT:
        raise ConflictError(
            "This case is not ready for disbursement; use the existing Loan Management lifecycle."
        )
    details = case.loan_details
    if not details:
        raise ConflictError("Loan details are unavailable.")
    approved = (
        payload.approved_amount if payload.approved_amount is not None else details.offered_amount
    )
    if approved is None or approved <= 0 or payload.disbursed_amount > approved:
        raise ValidationError(
            "A positive approved amount is required; disbursed amount cannot exceed it."
        )
    try:
        for amount in (approved, payload.disbursed_amount):
            if Decimal(str(amount)).quantize(Decimal("0.01")) != Decimal(str(amount)):
                raise ValidationError("Monetary amounts support at most two decimal places.")
    except InvalidOperation:
        raise ValidationError("Monetary amount is too large to process safely.") from None
    if details.offered_amount is not None and Decimal(str(details.offered_amount)) != Decimal(
        str(approved)
    ):
        raise ConflictError("Approved amount must match the existing approved loan offer.")
    date = payload.disbursement_date
    if date and date > to_ist(utc_now()).date():
        raise ValidationError("Disbursement date cannot be in the future.")
    if not payload.final_disbursement and payload.disbursed_amount >= approved:
        raise ValidationError("No further disbursement can be expected when the approved amount is fully disbursed.")
    updated_details = details.model_copy(
        update={
            "offered_amount": approved,
            "disbursement_final": payload.final_disbursement,
            "last_disbursed_at": ist_date_to_utc_midnight(date) if date else utc_now(),
            "disbursed_amount": payload.disbursed_amount,
            "disbursed_reference": payload.disbursed_reference,
            "disbursed_at": ist_date_to_utc_midnight(date) if date else utc_now(),
            "disbursement_remarks": payload.remarks,
        }
    )
    try:
        async with await service._db.client.start_session() as session, session.start_transaction():
            updated = await service._engine.transition(
                case,
                LoanStatus.DISBURSED,
                actor,
                updates={"loan_details": updated_details.model_dump()},
                remarks=payload.remarks,
                session=session,
            )
            from app.features.referral_partner_management.finance import calculate

            financial_event = await service._db.application_status_history.find_one(
                {"application_workflow_id": case_id, "to_status": LoanStatus.DISBURSED},
                sort=[("created_at", -1)], session=session)
            if not financial_event:
                raise ConflictError("Disbursement history is required for commission traceability.")
            financial_snapshot = {"id": str(financial_event["_id"]), "source": "application_status_history", "amount": payload.disbursed_amount, "at": updated_details.disbursed_at, "reference": payload.disbursed_reference, "remarks": payload.remarks, "actor_id": actor.require_id(), "final": payload.final_disbursement}
            await service._db.application_workflows.update_one({"_id": ObjectId(case_id)}, {"$push": {"loan_details.disbursement_events": financial_snapshot}}, session=session)
            updated = updated.model_copy(update={"loan_details": updated_details.model_copy(update={"disbursement_events": [financial_snapshot]})})
            await calculate(service._db, updated.model_dump(by_alias=True), actor, session, str(financial_event["_id"]))
            workspace = await service._db.daily_follow_ups.find_one(
                {
                    "application_id": case.application_id,
                    "is_deleted": False,
                    "working_key": "application:" + case.application_id,
                },
                session=session,
            )
            if followup and (not workspace or str(workspace["_id"]) != str(followup[0]["_id"])):
                raise ConflictError("The selected Application workspace changed.")
            if workspace:
                if len(workspace.get("history", [])) >= 250:
                    raise ConflictError(
                        "Follow-up history limit reached; Owner review required before disbursement."
                    )
                before = followup[0] if followup else workspace
                values = {
                    **(followup[1] if followup else {}),
                    "status": "DISBURSE",
                    "due_date": None,
                    "case_id": case_id,
                    "case_oid": ObjectId(case_id),
                    "updated_at": utc_now(),
                    "updated_by": actor.require_id(),
                }
                event = {
                    "source": "loan_disbursement",
                    "actor_id": actor.require_id(),
                    "at": utc_now(),
                    "before": {k: workspace.get(k) for k in values if not k.endswith("_oid")},
                    "after": {k: v for k, v in values.items() if not k.endswith("_oid")},
                    "case_id": case_id,
                }
                result = await service._db.daily_follow_ups.update_one(
                    {
                        "_id": workspace["_id"],
                        "version": before["version"],
                        "assigned_to": case.assigned_to,
                        "is_deleted": False,
                    },
                    {"$set": values, "$inc": {"version": 1}, "$push": {"history": event}},
                    session=session,
                )
                if not result.matched_count:
                    raise ConflictError(
                        "Follow-up ownership or version changed; nothing was disbursed."
                    )
                audit = AuditLog(
                    event_type="daily_followup_disbursed",
                    user_id=actor.require_id(),
                    metadata={"record_id": str(workspace["_id"]), "case_id": case_id},
                )
                await service._db.audit_logs.insert_one(
                    audit.model_dump(by_alias=True, exclude={"id"}), session=session
                )
    except OperationFailure as exc:
        if exc.code == 112 or exc.has_error_label("TransientTransactionError"):
            raise ConflictError(
                "Concurrent disbursement or transfer. Refresh; no automatic retry."
            ) from None
        raise
    from app.features.event_engine.bus import publish
    from app.features.workflow_engine.engine import STATUS_CHANGED_EVENT

    definition = await service._engine.get_definition(case.case_type, LoanStatus.DISBURSED)
    await publish(
        STATUS_CHANGED_EVENT,
        {
            "application_workflow_id": case_id,
            "case_type": case.case_type,
            "from_status": case.current_status,
            "to_status": LoanStatus.DISBURSED,
            "notification_trigger_key": definition.notification_trigger_key,
            "reminder_trigger_key": definition.reminder_trigger_key,
        },
    )
    return ApplicationWorkflow.model_validate(updated)


async def schedule_top_up(
    service: Any, case: Any, details: Any, payload: Any, actor: Any
) -> ApplicationWorkflow:
    import hashlib
    import json

    from pymongo import ReturnDocument
    from pymongo.errors import DuplicateKeyError

    from app.features.workflow_engine.constants import LoanAuditEvent
    from app.features.workflow_engine.models import ApplicationNote, ApplicationWorkflow

    fingerprint = hashlib.sha256(
        json.dumps(
            [case.require_id(), payload.period, str(payload.custom_date), payload.remarks],
            sort_keys=True,
        ).encode()
    ).hexdigest()
    receipt_id = (
        ObjectId(
            hashlib.sha256(
                ("topup:" + actor.require_id() + payload.request_id).encode()
            ).hexdigest()[:24]
        )
        if payload.request_id
        else ObjectId()
    )
    old = await service._db.audit_logs.find_one({"_id": receipt_id})
    if old:
        if old.get("metadata", {}).get("fingerprint") != fingerprint:
            raise ConflictError("Top-up request key already belongs to another action.")
        return ApplicationWorkflow.model_validate(case)
    audit = AuditLog(
        event_type=LoanAuditEvent.TOP_UP_SCHEDULED,
        user_id=actor.require_id(),
        metadata={
            "application_workflow_id": case.require_id(),
            "period": payload.period,
            "eligibility_date": details.top_up_eligibility_date.isoformat()
            if details.top_up_eligibility_date
            else None,
            "fingerprint": fingerprint,
        },
    )
    note = ApplicationNote(
        application_workflow_id=case.require_id(),
        created_by=actor.require_id(),
        text=service._top_up_note_text(
            payload.period, details.top_up_eligibility_date, payload.remarks
        ),
    )
    try:
        async with await service._db.client.start_session() as session, session.start_transaction():
            row = await service._db.application_workflows.find_one_and_update(
                {
                    "_id": ObjectId(case.require_id()),
                    "current_status": "disbursed",
                    "version": case.version,
                    "assigned_to": case.assigned_to,
                    "is_deleted": False,
                },
                {
                    "$set": {
                        "loan_details": details.model_dump(),
                        "updated_by": actor.require_id(),
                        "updated_at": utc_now(),
                    },
                    "$inc": {"version": 1},
                },
                return_document=ReturnDocument.AFTER,
                session=session,
            )
            if not row:
                raise ConflictError("Case changed. No Top-up decision was saved.")
            await service._db.audit_logs.insert_one(
                {**audit.model_dump(by_alias=True, exclude={"id"}), "_id": receipt_id},
                session=session,
            )
            await service._db.application_notes.insert_one(
                note.model_dump(by_alias=True, exclude={"id"}), session=session
            )
    except DuplicateKeyError:
        old = await service._db.audit_logs.find_one({"_id": receipt_id})
        if old and old.get("metadata", {}).get("fingerprint") == fingerprint:
            return ApplicationWorkflow.model_validate(
                await service.get_case(case.require_id(), actor)
            )
        raise ConflictError("Concurrent Top-up action. Refresh before continuing.") from None
    except OperationFailure as exc:
        if exc.code == 112 or exc.has_error_label("TransientTransactionError"):
            raise ConflictError(
                "Concurrent Top-up or transfer. Refresh; no automatic retry."
            ) from None
        raise
    return ApplicationWorkflow.model_validate(row)
