"""Additional confirmed tranches on the existing Loan Case financial record."""

import hashlib
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError, OperationFailure

from app.core.exceptions import ConflictError, ValidationError
from app.features.referral_partner_management.finance import calculate, money
from app.shared.audit_log import AuditLog
from app.utils.datetime import ist_date_to_utc_midnight, to_ist, utc_now


async def record(service: Any, case_id: str, payload: Any, actor: Any) -> Any:
    case = await service.get_case(case_id, actor)
    receipt = ObjectId(
        hashlib.sha256(
            ("loan-tranche:" + actor.require_id() + payload.request_id).encode()
        ).hexdigest()[:24]
    )
    fingerprint = hashlib.sha256(
        (case_id + payload.model_dump_json(exclude={"request_id"})).encode()
    ).hexdigest()
    previous = await service._db.audit_logs.find_one({"_id": receipt})
    if previous:
        if previous["metadata"]["fingerprint"] != fingerprint:
            raise ConflictError("This disbursement request key was used for different data.")
        return case
    details = case.loan_details
    if case.current_status != "disbursed" or not details or details.disbursement_final:
        raise ConflictError("This loan has no explicitly pending disbursement tranche.")
    if len(details.disbursement_events) >= 100:
        raise ConflictError("Disbursement history limit reached; Owner review required.")
    amount = money(payload.amount)
    total = money(details.disbursed_amount) + amount
    if total > money(details.offered_amount) or (
        not payload.final_disbursement and total >= money(details.offered_amount)
    ):
        raise ValidationError(
            "Tranches cannot exceed the approved amount; a fully disbursed loan must be marked final."
        )
    last = details.last_disbursed_at or details.disbursed_at
    if not last or not to_ist(last).date() <= payload.disbursement_date <= to_ist(utc_now()).date():
        raise ValidationError("Use a date from the previous disbursement date through today.")
    reference = payload.reference.strip()
    if not reference or any(
        event["reference"].strip().casefold() == reference.casefold()
        for event in details.disbursement_events
    ):
        raise ValidationError(
            "This loan already contains that payment reference, or the reference is blank."
        )
    at = ist_date_to_utc_midnight(payload.disbursement_date)
    snapshot = {
        "id": str(receipt),
        "source": "audit_logs",
        "amount": float(amount),
        "at": at,
        "reference": reference,
        "remarks": payload.remarks,
        "actor_id": actor.require_id(),
        "final": payload.final_disbursement,
    }
    updated_details = details.model_copy(
        update={
            "disbursed_amount": float(total),
            "last_disbursed_at": at,
            "disbursement_final": payload.final_disbursement,
            "disbursement_events": [*details.disbursement_events, snapshot],
        }
    )
    audit = AuditLog(
        event_type="loan_additional_disbursement_confirmed",
        user_id=actor.require_id(),
        metadata={
            "case_id": case_id,
            "application_id": case.application_id,
            "amount": float(amount),
            "cumulative_disbursed_amount": float(total),
            "at": at,
            "reference": reference,
            "fingerprint": fingerprint,
        },
    )
    try:
        async with await service._db.client.start_session() as session, session.start_transaction():
            result = await service._db.application_workflows.update_one(
                {
                    "_id": ObjectId(case_id),
                    "version": case.version,
                    "current_status": "disbursed",
                    "assigned_to": case.assigned_to,
                    "is_deleted": False,
                    "loan_details.disbursement_final": False,
                },
                {
                    "$set": {
                        "loan_details": updated_details.model_dump(),
                        "updated_by": actor.require_id(),
                        "updated_at": utc_now(),
                    },
                    "$inc": {"version": 1},
                },
                session=session,
            )
            if not result.matched_count:
                raise ConflictError(
                    "Loan ownership or financial state changed; no tranche was recorded."
                )
            await service._db.audit_logs.insert_one(
                {**audit.model_dump(exclude={"id"}), "_id": receipt}, session=session
            )
            from app.features.workflow_engine.models import ApplicationNote

            note = ApplicationNote(
                application_workflow_id=case_id,
                text=f"Confirmed additional disbursement: {amount}; reference {reference}. {payload.remarks}",
                created_by=actor.require_id(),
            )
            await service._db.application_notes.insert_one(
                note.model_dump(exclude={"id"}), session=session
            )
            # The calculator receives this exact persisted financial event, never a cumulative base.
            financial_view = case.model_dump(by_alias=True)
            financial_view["loan_details"] = updated_details.model_copy(
                update={"disbursed_amount": float(amount), "disbursed_at": at}
            ).model_dump()
            await calculate(
                service._db,
                financial_view,
                actor,
                session,
                str(receipt),
                financial_event_source="audit_logs",
            )
            workspace = await service._db.daily_follow_ups.find_one(
                {
                    "application_id": case.application_id,
                    "working_key": "application:" + case.application_id,
                    "is_deleted": False,
                },
                session=session,
            )
            if workspace:
                if (
                    workspace.get("assigned_to") != case.assigned_to
                    or len(workspace.get("history", [])) >= 250
                ):
                    raise ConflictError(
                        "Follow-up ownership/history requires review before recording a tranche."
                    )
                history = {
                    "source": "loan_additional_disbursement",
                    "actor_id": actor.require_id(),
                    "at": utc_now(),
                    "before": {"status": workspace["status"]},
                    "after": {
                        "status": "DISBURSE",
                        "tranche_amount": float(amount),
                        "cumulative_disbursed_amount": float(total),
                    },
                    "case_id": case_id,
                    "financial_event_id": str(receipt),
                }
                result = await service._db.daily_follow_ups.update_one(
                    {
                        "_id": workspace["_id"],
                        "version": workspace["version"],
                        "assigned_to": case.assigned_to,
                    },
                    {
                        "$set": {
                            "status": "DISBURSE",
                            "due_date": None,
                            "updated_at": utc_now(),
                            "updated_by": actor.require_id(),
                        },
                        "$inc": {"version": 1},
                        "$push": {"history": history},
                    },
                    session=session,
                )
                if not result.matched_count:
                    raise ConflictError("Follow-up changed; nothing was disbursed.")
    except DuplicateKeyError:
        raise ConflictError(
            "This disbursement was already recorded. Refresh the case; no automatic retry."
        ) from None
    except OperationFailure as exc:
        if exc.code == 112 or exc.has_error_label("TransientTransactionError"):
            raise ConflictError(
                "Concurrent payment, commission approval or transfer. Refresh; no automatic retry."
            ) from None
        raise
    return await service.get_case(case_id, actor)
