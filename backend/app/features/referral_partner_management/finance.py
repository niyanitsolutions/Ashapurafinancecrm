"""One existing commission ledger, tied to committed canonical Loan disbursements."""

import hashlib
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from bson import ObjectId
from pydantic import Field

from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.features.referral_partner_management.kyc import event, oid, public
from app.features.referral_partner_management.models import CommissionEntry, CommissionRule
from app.features.referral_partner_management.portal_models import StrictInput
from app.utils.datetime import ensure_utc, utc_now


def money(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
        if (
            not result.is_finite()
            or result < 0
            or result != result.quantize(Decimal("0.01"))
            or result * 100 > 9007199254740991
        ):
            raise ValueError
        return result
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(
            "Use a finite non-negative amount with at most two decimal places."
        ) from None


class PayoutInput(StrictInput):
    request_id: str = Field(min_length=16, max_length=100)
    amount: float = Field(gt=0, allow_inf_nan=False)
    payment_reference: str = Field(min_length=1, max_length=150)
    payment_method: str = Field(min_length=1, max_length=80)
    payment_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    remarks: str = Field(default="", max_length=1000)
    confirmed: bool


class CommissionDecision(StrictInput):
    version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)
    action: str = Field(pattern=r"^(hold|resume)$")


class AdjustmentInput(StrictInput):
    request_id: str = Field(min_length=16, max_length=100)
    amount: float = Field(allow_inf_nan=False)
    reason: str = Field(min_length=1, max_length=1000)
    kind: str = Field(pattern=r"^(adjustment|reversal)$")
    financial_audit_id: str | None = None


async def calculate(
    db: Any,
    case: dict[str, Any],
    actor: Any,
    session: Any,
    financial_event_id: str,
    *,
    financial_event_source: str = "application_status_history",
) -> None:
    """Caller owns the disbursement transaction; absence of a rule creates an exception."""
    application = await db.applications.find_one(
        {"_id": oid(case["application_id"]), "is_deleted": False}, session=session
    )
    if not application:
        return
    attribution = application.get("referral_attribution")
    if attribution and attribution.get("submitted_to_afs_at"):
        partner_id, referral_id = attribution["partner_id"], attribution["referral_id"]
    elif application.get("lead_id"):
        mapping = await db.referral_leads.find_one(
            {"lead_id": application["lead_id"], "is_deleted": False}, session=session
        )
        if not mapping:
            return
        partner_id, referral_id = mapping["partner_id"], str(mapping["_id"])
    else:
        return
    case_id = str(case["_id"])
    existing_entry = await db.commission_entries.find_one({"case_id": case_id}, session=session)
    if (
        existing_entry
        and existing_entry.get("disbursement_event_id") == financial_event_id
        and existing_entry.get("disbursement_event_source", "application_status_history")
        == financial_event_source
    ):
        return
    event_key = hashlib.sha256(
        (financial_event_source + ":" + financial_event_id).encode()
    ).hexdigest()
    if await db.commission_entry_events.find_one(
        {"financial_event_key": event_key}, session=session
    ):
        return
    loan = case.get("case_type") == "loan"
    details = case.get("loan_details" if loan else "insurance_details") or {}
    amount_field, date_field = (
        ("disbursed_amount", "disbursed_at") if loan else ("premium_amount", "policy_issued_at")
    )
    if (
        case.get("current_status") != ("disbursed" if loan else "policy_issued")
        or not details.get(amount_field)
        or not details.get(date_field)
    ):
        return
    base = money(details[amount_field])
    if base <= 0:
        return
    at = ensure_utc(details[date_field])
    await db.counters.update_one(
        {"_id": "commission-rule-config"}, {"$inc": {"epoch": 1}}, upsert=True, session=session
    )
    rules = [
        r
        async for r in db.commission_rules.find(
            {
                "is_deleted": False,
                "status": "active",
                "trigger_event": "loan_disbursed" if loan else "insurance_policy_issued",
                "partner_id": {"$in": [None, partner_id]},
                "product_category": {"$in": [None, "loan" if loan else "insurance"]},
                "$or": [{"product_id": None}, {"product_id": application["product_id"]}],
            },
            session=session,
        ).limit(200)
    ]
    rules = [
        r
        for r in rules
        if (not r.get("effective_from") or ensure_utc(r["effective_from"]) <= at)
        and (not r.get("effective_until") or at < ensure_utc(r["effective_until"]))
    ]
    rules.sort(
        key=lambda r: (
            r.get("partner_id") is None,
            r.get("product_id") is None,
            r.get("product_category") is None,
        )
    )
    ambiguous = len(rules) > 1 and tuple(
        rules[0].get(k) for k in ("partner_id", "product_id", "product_category")
    ) == tuple(rules[1].get(k) for k in ("partner_id", "product_id", "product_category"))

    async def record_exception(reason: str) -> None:
        result = await db.commission_exceptions.update_one(
            {
                "disbursement_event_id": financial_event_id,
                "disbursement_event_source": financial_event_source,
            },
            {
                "$setOnInsert": {
                    "case_id": case_id,
                    "application_id": case["application_id"],
                    "partner_id": partner_id,
                    "disbursement_event_id": financial_event_id,
                    "disbursement_event_source": financial_event_source,
                    "reason": reason,
                    "created_at": utc_now(),
                    "status": "open",
                    "eligible_base_amount": float(base),
                    "disbursed_at": details[date_field],
                    "product_id": application["product_id"],
                }
            },
            upsert=True,
            session=session,
        )
        if result.upserted_id:
            await event(
                db,
                actor,
                "partner_commission_exception",
                partner_id,
                session=session,
                detail={"case_id": case_id, "financial_event_id": financial_event_id},
            )

    valid_partner = ObjectId.is_valid(partner_id) and await db.referral_partners.find_one(
        {"_id": oid(partner_id), "is_deleted": False}, session=session
    )
    if not valid_partner:
        await record_exception("invalid_partner_attribution")
        return
    if not rules or ambiguous:
        await record_exception("conflicting_rules" if ambiguous else "missing_rule")
        return
    rule = rules[0]
    rate = Decimal(str(rule["rate_or_amount"]))
    if (
        not rate.is_finite()
        or rate < 0
        or (rule["calculation_type"] == "percentage" and rate > 100)
        or (rule["calculation_type"] == "flat" and not rule.get("fixed_contract_confirmed"))
    ):
        await record_exception("invalid_rule")
        return
    if rule["calculation_type"] == "flat" and rule.get("fixed_event_policy") not in {
        "per_case",
        "per_event",
    }:
        await record_exception("fixed_amount_event_policy_unconfirmed")
        return
    earned = (base * rate / 100 if rule["calculation_type"] == "percentage" else rate).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    money(earned)
    if existing_entry:
        if existing_entry["partner_id"] != partner_id:
            await record_exception("attribution_conflicts_with_existing_earning")
            return
        if rule["calculation_type"] == "flat" and rule.get("fixed_event_policy") == "per_case":
            previously_fixed = existing_entry[
                "calculation_type"
            ] == "flat" or await db.commission_entry_events.find_one(
                {
                    "entry_id": str(existing_entry["_id"]),
                    "kind": "disbursement_earning",
                    "calculation_type": "flat",
                },
                session=session,
            )
            if previously_fixed:
                earned = Decimal(0)
        additional = money(money(existing_entry.get("additional_earned_amount", 0)) + earned)
        paid_before = money(
            existing_entry.get("paid_amount")
            or (existing_entry["commission_amount"] if existing_entry["status"] == "paid" else 0)
        )
        balance = (
            money(existing_entry["commission_amount"])
            + additional
            + Decimal(str(existing_entry.get("adjusted_amount", 0)))
            - paid_before
        )
        line = {
            "entry_id": str(existing_entry["_id"]),
            "partner_id": partner_id,
            "case_id": case_id,
            "kind": "disbursement_earning",
            "amount": float(earned),
            "base_amount": float(base),
            "financial_at": at,
            "rule_id": str(rule["_id"]),
            "rule_version": rule.get("rule_version", 1),
            "calculation_type": rule["calculation_type"],
            "fixed_event_policy": rule.get("fixed_event_policy"),
            "rate_or_amount": float(rate),
            "disbursement_event_id": financial_event_id,
            "disbursement_event_source": financial_event_source,
            "financial_event_key": event_key,
            "created_at": utc_now(),
            "authorized_by": actor.require_id(),
        }
        await db.commission_entry_events.insert_one(line, session=session)
        if earned == 0:
            await event(
                db,
                actor,
                "commission_fixed_case_event_recorded",
                partner_id,
                session=session,
                detail={
                    "entry_id": str(existing_entry["_id"]),
                    "line_id": str(line["_id"]),
                    "financial_event_id": financial_event_id,
                },
            )
            return
        result = await db.commission_entries.update_one(
            {"_id": existing_entry["_id"], "version": existing_entry["version"]},
            {
                "$set": {
                    "additional_earned_amount": float(additional),
                    "paid_amount": float(paid_before),
                    "outstanding_amount": float(max(Decimal(0), balance)),
                    "recovery_due_amount": float(max(Decimal(0), -balance)),
                    "held_from_status": "pending",
                    "pending_additional_earning": True,
                    "status": "on_hold" if existing_entry["status"] == "on_hold" else "pending",
                },
                "$inc": {"version": 1},
            },
            session=session,
        )
        if not result.matched_count:
            raise ConflictError(
                "Commission approval or payment changed; no financial event was committed."
            )
        await event(
            db,
            actor,
            "commission_additional_earning_calculated",
            partner_id,
            session=session,
            detail={
                "entry_id": str(existing_entry["_id"]),
                "line_id": str(line["_id"]),
                "financial_event_id": financial_event_id,
            },
        )
        return
    entry = CommissionEntry(
        partner_id=partner_id,
        lead_id=application.get("lead_id") or "",
        case_type=case["case_type"],
        case_id=case_id,
        application_id=case["application_id"],
        customer_id=application.get("customer_id"),
        referral_id=referral_id,
        product_id=application["product_id"],
        financial_at=at,
        disbursement_event_id=financial_event_id,
        disbursement_event_source=financial_event_source,
        rule_id=str(rule["_id"]),
        rule_version=rule.get("rule_version", 1),
        calculation_type=rule["calculation_type"],
        fixed_event_policy=rule.get("fixed_event_policy"),
        rate_or_amount=float(rate),
        base_amount=float(base),
        commission_amount=float(earned),
        outstanding_amount=float(earned),
        created_by=actor.require_id(),
    )
    await db.commission_entries.insert_one(entry.model_dump(exclude={"id"}), session=session)
    await event(
        db,
        actor,
        "commission_entry_created",
        partner_id,
        session=session,
        detail={
            "case_id": case_id,
            "disbursement_event_id": financial_event_id,
            "rule_id": str(rule["_id"]),
            "rule_version": rule.get("rule_version", 1),
        },
    )


async def _payout(db: Any, entry_id: str, payload: PayoutInput, actor: Any) -> dict[str, Any]:
    from app.features.referral_partner_management.payouts import (
        payment_key,
        reject_recorded_reference,
    )

    if actor.role != "owner":
        raise ForbiddenError("Only Owner can confirm payouts.")
    if not payload.confirmed:
        raise ValidationError("Confirm the actual payment before recording a payout.")
    from datetime import date

    from app.utils.datetime import to_ist

    try:
        if date.fromisoformat(payload.payment_date) > to_ist(utc_now()).date():
            raise ValueError
    except ValueError:
        raise ValidationError("Use a valid payment date no later than today.") from None
    paid = money(payload.amount)
    receipt = ObjectId(
        hashlib.sha256(
            ("commission-payment:" + actor.require_id() + payload.request_id).encode()
        ).hexdigest()[:24]
    )
    previous = await db.commission_payouts.find_one({"_id": receipt})
    fingerprint = hashlib.sha256(
        (entry_id + payload.model_dump_json(exclude={"request_id"})).encode()
    ).hexdigest()
    if previous:
        if previous["fingerprint"] != fingerprint:
            raise ConflictError("Payout request key already used for another payment.")
        return public(previous)
    async with await db.client.start_session() as session, session.start_transaction():
        entry = await db.commission_entries.find_one(
            {"_id": oid(entry_id), "is_deleted": False}, session=session
        )
        if not entry or entry["status"] != "approved":
            raise ConflictError("Only an approved outstanding commission can be paid.")
        outstanding = (
            money(entry["commission_amount"])
            + money(entry.get("additional_earned_amount", 0))
            + Decimal(str(entry.get("adjusted_amount", 0)))
            - money(entry.get("paid_amount", 0))
        )
        available = outstanding - money(entry.get("reserved_amount", 0))
        if paid > available:
            raise ValidationError("Payment exceeds the approved outstanding balance.")
        await reject_recorded_reference(db, entry["partner_id"], payload.payment_reference, session)
        remaining = outstanding - paid
        result = await db.commission_entries.update_one(
            {"_id": entry["_id"], "version": entry["version"], "status": "approved"},
            {
                "$set": {
                    "paid_amount": float(money(entry.get("paid_amount", 0)) + paid),
                    "outstanding_amount": float(remaining),
                    "status": "paid" if remaining == 0 else "approved",
                    "payment_reference": payload.payment_reference,
                    "paid_at": utc_now(),
                    "paid_by": actor.require_id(),
                },
                "$inc": {"version": 1},
            },
            session=session,
        )
        if not result.matched_count:
            raise ConflictError("Commission balance changed; refresh. No automatic retry.")
        row = {
            "_id": receipt,
            "entry_id": entry_id,
            "product_id": entry.get("product_id"),
            "partner_id": entry["partner_id"],
            "amount": float(paid),
            "status": "confirmed",
            "payment_key": payment_key(
                entry["partner_id"], payload.payment_method, payload.payment_reference
            ),
            "payment_reference": payload.payment_reference,
            "payment_method": payload.payment_method,
            "payment_date": payload.payment_date,
            "remarks": payload.remarks,
            "authorized_by": actor.require_id(),
            "created_at": utc_now(),
            "confirmed_at": utc_now(),
            "fingerprint": fingerprint,
        }
        await db.commission_payouts.insert_one(row, session=session)
        await event(
            db,
            actor,
            "commission_payout_confirmed",
            entry["partner_id"],
            session=session,
            detail={"entry_id": entry_id, "payout_id": str(receipt)},
        )
    return public(row)


async def save_rule(
    db: Any, payload: Any, actor: Any, previous: CommissionRule | None = None
) -> CommissionRule:
    from app.features.referral_partner_management.models import CommissionRule

    if actor.role != "owner":
        raise ForbiddenError("Only Owner can configure commission rules.")
    values = {
        **(previous.model_dump(exclude={"id"}) if previous else {}),
        **payload.model_dump(exclude_unset=True),
    }
    rule = CommissionRule(**values)
    if rule.partner_id and not await db.referral_partners.find_one(
        {"_id": oid(rule.partner_id), "is_deleted": False}
    ):
        raise ValidationError("Applicable Partner not found.")
    if rule.product_id and (
        rule.product_category not in {None, "loan"} or rule.trigger_event != "loan_disbursed"
    ):
        raise ValidationError("A Loan Product requires the Loan disbursement trigger and category.")
    if rule.product_id and not await db.loan_products.find_one(
        {"_id": oid(rule.product_id), "is_deleted": False}
    ):
        raise ValidationError("Loan Product not found.")
    if rule.status == "active" and not rule.effective_from:
        raise ValidationError("Set the confirmed effective start date for an active rule version.")
    if rule.effective_from:
        rule.effective_from = ensure_utc(rule.effective_from)
    if rule.effective_until:
        rule.effective_until = ensure_utc(rule.effective_until)
    if rule.calculation_type not in {"percentage", "flat"} or rule.trigger_event not in {
        "loan_disbursed",
        "insurance_policy_issued",
    }:
        raise ValidationError("Unsupported calculation or trigger.")
    if (rule.trigger_event == "loan_disbursed" and rule.product_category == "insurance") or (
        rule.trigger_event == "insurance_policy_issued" and rule.product_category == "loan"
    ):
        raise ValidationError("The product category must match the confirmed financial trigger.")
    rate = Decimal(str(rule.rate_or_amount))
    if not rate.is_finite() or rate < 0 or (rule.calculation_type == "percentage" and rate > 100):
        raise ValidationError("Commission percentage must be between zero and 100.")
    if rule.calculation_type == "flat" and not rule.fixed_contract_confirmed:
        raise ValidationError("Fixed amount requires an explicitly confirmed commission contract.")
    if rule.calculation_type == "flat":
        money(rule.rate_or_amount)
        if rule.fixed_event_policy not in {"per_case", "per_event"}:
            raise ValidationError(
                "Confirm whether the fixed contract pays once per case or per eligible disbursement event."
            )
    if rule.effective_from and rule.effective_until and rule.effective_until <= rule.effective_from:
        raise ValidationError("Effective Until must be after Effective From.")
    rule.rule_version = previous.rule_version + 1 if previous else 1
    rule.previous_rule_id = previous.require_id() if previous else None
    rule.created_at, rule.created_by = utc_now(), actor.require_id()
    rule.updated_at, rule.updated_by = rule.created_at, actor.require_id()
    async with await db.client.start_session() as session, session.start_transaction():
        await db.counters.update_one(
            {"_id": "commission-rule-config"}, {"$inc": {"epoch": 1}}, upsert=True, session=session
        )
        if previous and await db.commission_rules.find_one(
            {"previous_rule_id": previous.require_id()}, session=session
        ):
            raise ConflictError("Edit the latest rule version, not a superseded version.")
        query = {
            "is_deleted": False,
            "status": "active",
            "partner_id": rule.partner_id,
            "product_id": rule.product_id,
            "product_category": rule.product_category,
            "trigger_event": rule.trigger_event,
        }
        if previous:
            query["_id"] = {"$ne": oid(previous.require_id())}
        async for other in db.commission_rules.find(query, session=session):
            if rule.status != "active":
                break
            if (
                not rule.effective_until
                or not other.get("effective_from")
                or ensure_utc(other["effective_from"]) < ensure_utc(rule.effective_until)
            ) and (
                not rule.effective_from
                or not other.get("effective_until")
                or ensure_utc(rule.effective_from) < ensure_utc(other["effective_until"])
            ):
                raise ConflictError(
                    "An active rule already overlaps this Partner/product/effective period."
                )
        if previous:
            result = await db.commission_rules.update_one(
                {"_id": oid(previous.require_id()), "version": previous.version},
                {"$set": {"status": "inactive"}, "$inc": {"version": 1}},
                session=session,
            )
            if not result.matched_count:
                raise ConflictError("Rule changed; reload.")
        result = await db.commission_rules.insert_one(
            rule.model_dump(exclude={"id"}), session=session
        )
        rule.id = str(result.inserted_id)
        await event(
            db,
            actor,
            "commission_rule_version_created",
            rule.partner_id or "default",
            session=session,
            detail={"rule_id": rule.id, "rule_version": rule.rule_version},
        )
    return rule


async def commission_decision(
    db: Any, entry_id: str, payload: CommissionDecision, actor: Any
) -> dict[str, Any]:
    if actor.role != "owner":
        raise ForbiddenError("Only Owner can hold or resume commissions.")
    async with await db.client.start_session() as session, session.start_transaction():
        row = await db.commission_entries.find_one(
            {"_id": oid(entry_id), "version": payload.version, "is_deleted": False}, session=session
        )
        if not row:
            raise ConflictError("Commission changed; reload.")
        if payload.action == "hold" and row["status"] in {"pending", "approved"}:
            changes = {
                "status": "on_hold",
                "hold_reason": payload.reason,
                "held_from_status": row["status"],
            }
        elif (
            payload.action == "resume"
            and row["status"] == "on_hold"
            and not row.get("recovery_due_amount")
        ):
            changes = {"status": row.get("held_from_status", "pending"), "hold_reason": None}
        else:
            raise ValidationError("This commission cannot make the selected transition.")
        await db.commission_entries.update_one(
            {"_id": row["_id"], "version": payload.version},
            {"$set": changes, "$inc": {"version": 1}},
            session=session,
        )
        await event(
            db,
            actor,
            "commission_" + payload.action,
            row["partner_id"],
            session=session,
            detail={"entry_id": entry_id, "reason": payload.reason},
        )
    return {"id": entry_id, **changes, "version": payload.version + 1}


async def adjust(db: Any, entry_id: str, payload: AdjustmentInput, actor: Any) -> dict[str, Any]:
    if actor.role != "owner":
        raise ForbiddenError("Only Owner can authorize commission adjustments.")
    amount = money(abs(payload.amount)) * (-1 if payload.amount < 0 else 1)
    if amount == 0:
        raise ValidationError("Use a non-zero adjustment with at most two decimal places.")
    receipt = ObjectId(
        hashlib.sha256(
            ("commission-adjustment:" + actor.require_id() + payload.request_id).encode()
        ).hexdigest()[:24]
    )
    fingerprint = hashlib.sha256(
        (entry_id + payload.model_dump_json(exclude={"request_id"})).encode()
    ).hexdigest()
    prior = await db.commission_entry_events.find_one({"_id": receipt})
    if prior:
        if prior["fingerprint"] != fingerprint:
            raise ConflictError("Adjustment request key already used.")
        return public(prior)
    async with await db.client.start_session() as session, session.start_transaction():
        row = await db.commission_entries.find_one(
            {"_id": oid(entry_id), "is_deleted": False}, session=session
        )
        if not row:
            raise ValidationError("Commission entry not found.")
        if payload.kind == "reversal":
            financial = await db.audit_logs.find_one(
                {
                    "_id": oid(payload.financial_audit_id or ""),
                    "event_type": {
                        "$in": ["loan_disbursement_reversed", "loan_disbursement_adjusted"]
                    },
                    "metadata.case_id": row["case_id"],
                },
                session=session,
            )
            if not financial or amount >= 0:
                raise ValidationError(
                    "A reversal requires a real authorized financial reversal event for this Loan Case and a negative amount."
                )
        adjusted = Decimal(str(row.get("adjusted_amount", 0))) + amount
        paid_before = money(
            row.get("paid_amount", row["commission_amount"] if row["status"] == "paid" else 0)
        )
        balance = (
            money(row["commission_amount"])
            + money(row.get("additional_earned_amount", 0))
            + adjusted
            - paid_before
        )
        changes = {
            "paid_amount": float(paid_before),
            "adjusted_amount": float(adjusted),
            "outstanding_amount": float(max(Decimal(0), balance)),
            "recovery_due_amount": float(max(Decimal(0), -balance)),
            "status": "on_hold",
            "held_from_status": "pending",
            "hold_reason": "Owner adjustment requires review before further payment",
        }
        result = await db.commission_entries.update_one(
            {"_id": row["_id"], "version": row["version"]},
            {"$set": changes, "$inc": {"version": 1}},
            session=session,
        )
        if not result.matched_count:
            raise ConflictError("Commission changed; no adjustment recorded.")
        record = {
            "_id": receipt,
            "entry_id": entry_id,
            "partner_id": row["partner_id"],
            "case_id": row["case_id"],
            "amount": float(amount),
            "reason": payload.reason,
            "kind": payload.kind,
            "financial_audit_id": payload.financial_audit_id,
            "created_at": utc_now(),
            "authorized_by": actor.require_id(),
            "fingerprint": fingerprint,
        }
        await db.commission_entry_events.insert_one(record, session=session)
        await event(
            db,
            actor,
            "commission_" + payload.kind + "_recorded",
            row["partner_id"],
            session=session,
            detail={"entry_id": entry_id, "adjustment_id": str(receipt), "reason": payload.reason},
        )
    return public(record)


async def resolve_exception(db: Any, exception_id: str, reason: str, actor: Any) -> dict[str, Any]:
    if actor.role != "owner":
        raise ForbiddenError("Only Owner can authorize commission exception resolution.")
    if len(reason.strip()) < 3:
        raise ValidationError("Record the reason for resolving this financial exception.")
    async with await db.client.start_session() as session, session.start_transaction():
        exception = await db.commission_exceptions.find_one(
            {"_id": oid(exception_id)}, session=session
        )
        if not exception:
            raise ValidationError("Commission exception not found.")
        if exception["status"] == "resolved":
            return public(exception)
        case = await db.application_workflows.find_one(
            {"_id": oid(exception["case_id"]), "is_deleted": False}, session=session
        )
        if not case or case["application_id"] != exception["application_id"]:
            raise ConflictError("Original Loan Case relationship requires Owner review.")
        source = exception.get("disbursement_event_source", "application_status_history")
        financial_id = exception["disbursement_event_id"]
        if source == "application_status_history":
            verified = await db.application_status_history.find_one(
                {
                    "_id": oid(financial_id),
                    "application_workflow_id": exception["case_id"],
                    "to_status": "disbursed",
                },
                session=session,
            )
        elif source == "audit_logs":
            verified = await db.audit_logs.find_one(
                {
                    "_id": oid(financial_id),
                    "event_type": "loan_additional_disbursement_confirmed",
                    "metadata.case_id": exception["case_id"],
                },
                session=session,
            )
        else:
            verified = None
        snapshot = next(
            (
                item
                for item in case.get("loan_details", {}).get("disbursement_events", [])
                if item["id"] == financial_id
                and item.get("source", "application_status_history") == source
            ),
            None,
        )
        if (
            not verified
            or not snapshot
            or money(snapshot["amount"]) != money(exception["eligible_base_amount"])
        ):
            raise ConflictError(
                "The original confirmed financial event cannot be verified; no earning was created."
            )
        financial_view = {
            **case,
            "current_status": "disbursed",
            "loan_details": {
                **case["loan_details"],
                "disbursed_amount": exception["eligible_base_amount"],
                "disbursed_at": exception["disbursed_at"],
            },
        }
        await calculate(
            db, financial_view, actor, session, financial_id, financial_event_source=source
        )
        entry = await db.commission_entries.find_one(
            {"case_id": exception["case_id"]}, session=session
        )
        event_key = hashlib.sha256((source + ":" + financial_id).encode()).hexdigest()
        line = await db.commission_entry_events.find_one(
            {"financial_event_key": event_key}, session=session
        )
        if not entry or (
            (
                entry.get("disbursement_event_id") != financial_id
                or entry.get("disbursement_event_source", "application_status_history") != source
            )
            and not line
        ):
            raise ValidationError(
                "No eligible unambiguous rule applies to the original financial event date, or its attribution still needs review."
            )
        result = await db.commission_exceptions.update_one(
            {"_id": exception["_id"], "status": "open"},
            {
                "$set": {
                    "status": "resolved",
                    "resolved_at": utc_now(),
                    "resolved_by": actor.require_id(),
                    "resolution_reason": reason,
                    "resolved_entry_id": str(entry["_id"]),
                    "resolved_partner_id": entry["partner_id"],
                }
            },
            session=session,
        )
        if not result.matched_count:
            raise ConflictError("Exception was resolved by another request; refresh.")
        await event(
            db,
            actor,
            "commission_exception_resolved",
            entry["partner_id"],
            session=session,
            detail={"exception_id": exception_id, "entry_id": str(entry["_id"]), "reason": reason},
        )
    return {"id": exception_id, "status": "resolved", "entry_id": str(entry["_id"])}


async def payout(db: Any, entry_id: str, payload: PayoutInput, actor: Any) -> dict[str, Any]:
    from pymongo.errors import DuplicateKeyError, OperationFailure

    try:
        return await _payout(db, entry_id, payload, actor)
    except DuplicateKeyError:
        raise ConflictError(
            "Payment reference or request already recorded; no balances changed. Refresh before retrying."
        ) from None
    except OperationFailure as exc:
        if exc.code == 112 or exc.has_error_label("TransientTransactionError"):
            raise ConflictError(
                "Payment or commission changed concurrently. Refresh; no automatic retry."
            ) from None
        raise
