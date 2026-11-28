"""Atomic payment reservations; no transfer is initiated against a bank provider."""

import hashlib
from datetime import date
from decimal import Decimal
from typing import Any

from bson import ObjectId
from pydantic import Field, model_validator
from pymongo.errors import DuplicateKeyError, OperationFailure

from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.features.referral_partner_management.finance import money
from app.features.referral_partner_management.kyc import event, oid, public
from app.features.referral_partner_management.portal_models import StrictInput
from app.utils.datetime import to_ist, utc_now


class Allocation(StrictInput):
    entry_id: str
    amount: float = Field(gt=0, allow_inf_nan=False)


class ReservePayment(StrictInput):
    request_id: str = Field(min_length=16, max_length=100)
    allocations: list[Allocation] = Field(min_length=1, max_length=100)
    remarks: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def unique_entries(self) -> "ReservePayment":
        if len({a.entry_id for a in self.allocations}) != len(self.allocations):
            raise ValueError("Select each commission only once.")
        return self


class ConfirmPayment(StrictInput):
    payment_reference: str = Field(min_length=1, max_length=150)
    payment_method: str = Field(min_length=1, max_length=80)
    payment_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    confirmed: bool


def paid_amount(entry: dict[str, Any]) -> Decimal:
    return money(
        entry.get("paid_amount", entry["commission_amount"] if entry["status"] == "paid" else 0)
    )


def outstanding(entry: dict[str, Any]) -> Decimal:
    return (
        money(entry["commission_amount"])
        + money(entry.get("additional_earned_amount", 0))
        + Decimal(str(entry.get("adjusted_amount", 0)))
        - paid_amount(entry)
    )


def require_owner(actor: Any) -> None:
    if actor.role != "owner":
        raise ForbiddenError("Only Owner can manage commission payments.")


def validate_confirmation(payload: ConfirmPayment) -> None:
    if not payload.confirmed:
        raise ValidationError("Confirm the actual payment before recording it.")
    try:
        if date.fromisoformat(payload.payment_date) > to_ist(utc_now()).date():
            raise ValueError
    except ValueError:
        raise ValidationError("Use a valid payment date no later than today.") from None


def payment_key(partner_id: str, method: str, reference: str) -> str:
    return hashlib.sha256(
        (partner_id + ":" + method.casefold().strip() + ":" + reference.casefold().strip()).encode()
    ).hexdigest()


async def _reserve(db: Any, payload: ReservePayment, actor: Any) -> dict[str, Any]:
    require_owner(actor)
    receipt = ObjectId(
        hashlib.sha256(
            ("commission-reservation:" + actor.require_id() + payload.request_id).encode()
        ).hexdigest()[:24]
    )
    fingerprint = hashlib.sha256(
        payload.model_dump_json(exclude={"request_id"}).encode()
    ).hexdigest()
    previous = await db.commission_payouts.find_one({"_id": receipt})
    if previous:
        if previous.get("fingerprint") != fingerprint:
            raise ConflictError("Payment request key already used for another allocation.")
        return public(previous)
    async with await db.client.start_session() as session, session.start_transaction():
        partner_id = None
        allocations = []
        for item in sorted(payload.allocations, key=lambda item: item.entry_id):
            amount = money(item.amount)
            entry = await db.commission_entries.find_one(
                {"_id": oid(item.entry_id), "is_deleted": False}, session=session
            )
            if not entry or entry["status"] != "approved":
                raise ConflictError("Only approved commissions can be reserved for payment.")
            if partner_id and partner_id != entry["partner_id"]:
                raise ValidationError("A grouped payment must belong to one Partner.")
            partner_id = entry["partner_id"]
            reserved = money(entry.get("reserved_amount", 0))
            if amount > outstanding(entry) - reserved:
                raise ValidationError(
                    "Payment exceeds the available approved balance after reservations."
                )
            result = await db.commission_entries.update_one(
                {"_id": entry["_id"], "version": entry["version"]},
                {"$set": {"reserved_amount": float(reserved + amount)}, "$inc": {"version": 1}},
                session=session,
            )
            if not result.matched_count:
                raise ConflictError(
                    "Commission changed; no payment was reserved. Refresh before retrying."
                )
            allocations.append(
                {
                    "entry_id": item.entry_id,
                    "product_id": entry.get("product_id"),
                    "amount": float(amount),
                }
            )
        assert partner_id is not None
        row = {
            "_id": receipt,
            "partner_id": partner_id,
            "allocations": allocations,
            "amount": float(sum((money(a["amount"]) for a in allocations), Decimal(0))),
            "status": "initiated",
            "created_at": utc_now(),
            "authorized_by": actor.require_id(),
            "remarks": payload.remarks,
            "fingerprint": fingerprint,
        }
        await db.commission_payouts.insert_one(row, session=session)
        await event(
            db,
            actor,
            "commission_payment_reserved",
            partner_id,
            session=session,
            detail={"payout_id": str(receipt), "entry_ids": [a["entry_id"] for a in allocations]},
        )
    return public(row)


async def finish(
    db: Any,
    payout_id: str,
    actor: Any,
    *,
    confirmation: ConfirmPayment | None = None,
    reason: str = "",
) -> dict[str, Any]:
    require_owner(actor)
    if confirmation:
        validate_confirmation(confirmation)
    elif len(reason.strip()) < 3:
        raise ValidationError("Record the reason for cancelling the reservation.")
    try:
        async with await db.client.start_session() as session, session.start_transaction():
            row = await db.commission_payouts.find_one({"_id": oid(payout_id)}, session=session)
            if not row:
                raise ValidationError("Payment reservation not found.")
            desired = "confirmed" if confirmation else "cancelled"
            if row.get("status") == desired:
                if confirmation and any(
                    row.get(key) != getattr(confirmation, key)
                    for key in ("payment_reference", "payment_method", "payment_date")
                ):
                    raise ConflictError(
                        "This payment was already confirmed with different details."
                    )
                return public(row)
            if row.get("status") != "initiated":
                raise ConflictError("Only an initiated reservation can be confirmed or cancelled.")
            if confirmation:
                await reject_recorded_reference(
                    db, row["partner_id"], confirmation.payment_reference, session
                )
            for allocation in row["allocations"]:
                entry = await db.commission_entries.find_one(
                    {"_id": oid(allocation["entry_id"])}, session=session
                )
                amount = money(allocation["amount"])
                if not entry or money(entry.get("reserved_amount", 0)) < amount:
                    raise ConflictError(
                        "Reservation balance requires review; no payment was recorded."
                    )
                changes: dict[str, Any] = {
                    "reserved_amount": float(money(entry["reserved_amount"]) - amount)
                }
                if confirmation:
                    if entry["status"] != "approved" or outstanding(entry) < amount:
                        raise ConflictError(
                            "Commission requires approval or review. Cancel the reservation to release it."
                        )
                    remaining = outstanding(entry) - amount
                    changes.update(
                        paid_amount=float(paid_amount(entry) + amount),
                        outstanding_amount=float(remaining),
                        status="paid" if remaining == 0 else "approved",
                        paid_at=utc_now(),
                        paid_by=actor.require_id(),
                        payment_reference=confirmation.payment_reference,
                    )
                result = await db.commission_entries.update_one(
                    {"_id": entry["_id"], "version": entry["version"]},
                    {"$set": changes, "$inc": {"version": 1}},
                    session=session,
                )
                if not result.matched_count:
                    raise ConflictError("Commission changed; refresh. No automatic retry.")
            changes = {
                "status": desired,
                "completed_by": actor.require_id(),
                "completed_at": utc_now(),
            }
            if confirmation:
                changes.update(confirmation.model_dump(exclude={"confirmed"}))
                changes.update(
                    confirmed_at=utc_now(),
                    payment_key=payment_key(
                        row["partner_id"],
                        confirmation.payment_method,
                        confirmation.payment_reference,
                    ),
                )
            else:
                changes["cancellation_reason"] = reason
            await db.commission_payouts.update_one(
                {"_id": row["_id"], "status": "initiated"}, {"$set": changes}, session=session
            )
            await event(
                db,
                actor,
                "commission_payout_" + desired,
                row["partner_id"],
                session=session,
                detail={"payout_id": payout_id, **({"reason": reason} if not confirmation else {})},
            )
    except DuplicateKeyError:
        raise ConflictError(
            "This Partner payment reference has already been recorded; no balances changed."
        ) from None
    except OperationFailure as exc:
        if exc.code == 112 or exc.has_error_label("TransientTransactionError"):
            raise ConflictError(
                "Payment or commission changed concurrently. Refresh; no automatic retry."
            ) from None
        raise
    return public({**row, **changes})


async def reject_recorded_reference(db: Any, partner_id: str, reference: str, session: Any) -> None:
    import re

    if await db.commission_entries.find_one(
        {
            "partner_id": partner_id,
            "payment_reference": {
                "$regex": "^" + re.escape(reference.strip()) + "$",
                "$options": "i",
            },
            "paid_at": {"$ne": None},
        },
        {"_id": 1},
        session=session,
    ):
        raise ConflictError(
            "This Partner payment reference is already recorded in the ledger. Review the existing payment before proceeding."
        )


async def reserve(db: Any, payload: ReservePayment, actor: Any) -> dict[str, Any]:
    try:
        return await _reserve(db, payload, actor)
    except DuplicateKeyError:
        raise ConflictError(
            "Payment reservation request already recorded; refresh before retrying."
        ) from None
    except OperationFailure as exc:
        if exc.code == 112 or exc.has_error_label("TransientTransactionError"):
            raise ConflictError(
                "Payment or commission changed concurrently. Refresh; no automatic retry."
            ) from None
        raise
