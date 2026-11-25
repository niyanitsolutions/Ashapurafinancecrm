"""Exact identity checks; snapshots remain unchanged. No fuzzy or mobile-only linking."""

import hashlib
import hmac
import json
import re
from typing import Any

from bson import ObjectId

from app.config.settings import get_settings
from app.constants.roles import OWNER
from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.shared.audit_log import write_audit_log
from app.shared.customer_identity import mobile_match_pattern, normalize_mobile


def name_key(value: str) -> str:
    return " ".join(value.split()).casefold() if isinstance(value, str) else ""


def fingerprint(value: Any) -> str:
    settings = get_settings()
    return hmac.new(
        (settings.encryption_key or settings.jwt_secret_key).encode(),
        b"daily-identity-v1:" + json.dumps(value, sort_keys=True, default=str).encode(),
        hashlib.sha256,
    ).hexdigest()


def name_pattern(value: str) -> str:
    return r"^\s*" + r"\s+".join(re.escape(part) for part in value.split()) + r"\s*$"


mobile_pattern = mobile_match_pattern


async def candidates(db: Any, name: str, mobile: str) -> dict[str, Any]:
    number = normalize_mobile(mobile or "")
    query = {
        "is_deleted": False,
        "$or": [
            {"full_name": {"$regex": name_pattern(name), "$options": "i"}},
            {"mobile": {"$regex": mobile_pattern(number)}},
        ],
    }
    rows = (
        await db.customers.find(query, {"full_name": 1, "mobile": 1, "user_id": 1})
        .limit(201)
        .to_list(201)
    )
    exact: list[str] = []
    partial: list[str] = []
    for row in rows[:200]:
        try:
            same_number = normalize_mobile(row.get("mobile") or "") == number
        except ValueError:
            same_number = False
        same_name = name_key(row.get("full_name", "")) == name_key(name)
        target = exact if same_number and same_name else partial
        target.append(str(row["_id"]))
    return {"exact": exact, "partial": partial, "truncated": len(rows) > 200}


async def prepare(service: Any, payload: Any, actor: Any) -> dict[str, Any]:
    try:
        mobile = normalize_mobile(payload.customer_number)
    except ValueError:
        raise ValidationError("Enter a valid Indian customer mobile number.") from None
    matches = await candidates(service.db, payload.customer_name, mobile)
    reason = payload.identity_review_reason.strip()
    chosen = payload.review_customer_id
    ambiguous = (
        matches["truncated"]
        or len(matches["exact"]) > 1
        or (not matches["exact"] and matches["partial"])
    )
    if chosen or (ambiguous and reason):
        if actor.role != OWNER or not reason:
            raise ForbiddenError("Owner identity review and a reason are required.")
        if chosen and chosen not in matches["exact"] + matches["partial"]:
            raise ValidationError("Choose a customer from the identity review candidates.")
        await write_audit_log(
            service.db,
            event_type="daily_identity_review",
            user_id=actor.require_id(),
            metadata={
                "customer_id": chosen,
                "decision": "verified_link" if chosen else "distinct_identity",
                "reason": reason,
            },
        )
    elif ambiguous:
        raise ConflictError(
            "Possible duplicate identity: name-only, mobile-only or ambiguous match. Ask the Owner to verify the identity; enter an Owner review reason to record a distinct customer decision."
        )
    elif len(matches["exact"]) == 1:
        chosen = matches["exact"][0]
        # Employees may reuse only a customer reachable through their current assignments.
        if actor.role != OWNER:
            assignment = await service.employee_id(actor)
            linked = await service.db.applications.find_one(
                {"customer_id": chosen, "assigned_to": assignment, "is_deleted": False}, {"_id": 1}
            )
            if not linked:
                raise ConflictError("This identity requires Owner review before linking.")
    data: dict[str, Any] = {
        "identity_state": "reviewed_distinct"
        if ambiguous and not chosen
        else "exact_match"
        if chosen
        else "independent"
    }
    if chosen:
        customer = await service.db.customers.find_one(
            {"_id": ObjectId(chosen), "is_deleted": False}
        )
        uid = (customer or {}).get("user_id")
        user = (
            await service.db.users.find_one(
                {"_id": ObjectId(uid), "role": "customer", "is_deleted": False}
            )
            if ObjectId.is_valid(uid)
            else None
        )
        if not user:
            raise ConflictError("Customer ownership relationship needs Owner review.")
        data.update(customer_id=chosen, user_id=uid)
    activity = payload.separate_activity_reason.strip()
    if not activity:
        from app.utils.datetime import ist_date_to_utc_midnight

        identities: list[dict[str, Any]] = [
            {
                "customer_name": {"$regex": name_pattern(payload.customer_name), "$options": "i"},
                "customer_number": {"$regex": mobile_pattern(mobile)},
            }
        ]
        if chosen:
            identities.append({"customer_id": chosen})
            for collection, field in (
                ("applications", "application_id"),
                ("application_workflows", "case_id"),
                ("leads", "lead_id"),
            ):
                linked = (
                    await service.db[collection]
                    .find({"customer_id": chosen, "is_deleted": False}, {"_id": 1})
                    .limit(201)
                    .to_list(201)
                )
                if len(linked) > 200:
                    raise ConflictError(
                        "Review this customer's historical activities before recording a separate activity with an explicit reason."
                    )
                if linked:
                    identities.append({field: {"$in": [str(item["_id"]) for item in linked]}})
        existing = await service.db.daily_follow_ups.find_one(
            {
                "is_deleted": False,
                "date": ist_date_to_utc_midnight(payload.date),
                "$or": identities,
            },
            {"_id": 1},
        )
        if existing:
            raise ConflictError(
                "An activity for this customer and date already exists. Edit it, or explicitly record a separate activity with a reason."
            )
    if activity and not payload.idempotency_key:
        raise ValidationError("A stable submission key is required for a separate activity.")
    data["activity_slot"] = payload.idempotency_key if activity else "primary"
    data["activity_key"] = fingerprint(
        [
            chosen or [name_key(payload.customer_name), mobile],
            payload.date.isoformat(),
            payload.idempotency_key if activity else "primary",
        ]
    )
    if activity:
        data["separate_activity_reason"] = activity
    return data


async def resolve_rows(db: Any, rows: list[dict[str, Any]]) -> None:
    """Bounded page batch, exact references only; never infer a relationship from PII."""
    maps = {}
    for field, collection in (
        ("application_id", "applications"),
        ("lead_id", "leads"),
        ("case_id", "application_workflows"),
    ):
        ids = [ObjectId(r[field]) for r in rows if ObjectId.is_valid(r.get(field))]
        maps[field] = (
            {
                str(r["_id"]): r
                for r in await db[collection]
                .find({"_id": {"$in": ids}, "is_deleted": False})
                .to_list(len(ids))
            }
            if ids
            else {}
        )
    cids = {r.get("customer_id") for r in rows}
    for records in maps.values():
        cids.update(r.get("customer_id") for r in records.values())
    ids = [ObjectId(cid) for cid in cids if ObjectId.is_valid(cid)]
    customers = (
        {
            str(c["_id"]): c
            for c in await db.customers.find({"_id": {"$in": ids}, "is_deleted": False}).to_list(
                len(ids)
            )
        }
        if ids
        else {}
    )
    uids = [
        ObjectId(c["user_id"]) for c in customers.values() if ObjectId.is_valid(c.get("user_id"))
    ]
    users = (
        {
            str(u["_id"]): u
            for u in await db.users.find(
                {"_id": {"$in": uids}, "role": "customer", "is_deleted": False}, {"_id": 1}
            ).to_list(len(uids))
        }
        if uids
        else {}
    )
    from app.features.customer.identity_name import actual_name, batch_application_names

    application_names = await batch_application_names(db, list(maps["application_id"]))
    for row in rows:
        if "_identity_original_name" in row:
            row["customer_name"] = row.pop("_identity_original_name")
        refs = [maps[field].get(row[field]) for field in maps if row.get(field)]
        linked_ids = {ref["customer_id"] for ref in refs if ref and ref.get("customer_id")}
        if row.get("customer_id"):
            linked_ids.add(row["customer_id"])
        customers_for_row = [customers[cid] for cid in linked_ids if cid in customers]
        broken = (
            any(ref is None for ref in refs)
            or len(linked_ids) > 1
            or len(customers_for_row) != len(linked_ids)
        )
        customer = customers_for_row[0] if len(customers_for_row) == 1 else None
        users_for_row = {ref["user_id"] for ref in refs if ref and ref.get("user_id")}
        if row.get("user_id"):
            users_for_row.add(row["user_id"])
        application = maps["application_id"].get(row.get("application_id") or "")
        case = maps["case_id"].get(row.get("case_id") or "")
        if len(users_for_row) > 1 or (
            application and row.get("lead_id") and application.get("lead_id") != row["lead_id"]
        ):
            broken = True
        if (
            case
            and row.get("application_id")
            and case.get("application_id")
            and case["application_id"] != row["application_id"]
        ):
            broken = True
        if customer and customer.get("user_id") not in users:
            broken = True
        if customer and any(
            ref.get("user_id") and ref["user_id"] != customer.get("user_id") for ref in refs if ref
        ):
            broken = True
        if customer and row.get("user_id") and row["user_id"] != customer.get("user_id"):
            broken = True
        if broken:
            row["identity_state"] = "manual_review"
            row["identity_warning"] = (
                "Linked customer relationships need Owner review. Historical values are retained."
            )
            continue
        if customer and actual_name(customer.get("full_name")):
            row["identity_snapshot"] = {
                "customer_name": row.get("customer_name", ""),
                "customer_number": row.get("customer_number", ""),
            }
            row["customer_name"] = customer["full_name"]
            row["customer_number"] = customer.get("mobile") or row.get("customer_number", "")
            row["identity_state"] = "linked_current"
        elif not actual_name(row.get("customer_name")):
            row["identity_snapshot"] = {
                "customer_name": row.get("customer_name", ""),
                "customer_number": row.get("customer_number", ""),
            }
            lead = maps["lead_id"].get(row.get("lead_id") or "")
            application_name = actual_name(application_names.get(row.get("application_id") or ""))
            if application_name:
                row["customer_name"] = application_name
            elif lead and actual_name(lead.get("full_name")):
                row["customer_name"] = lead["full_name"]
            else:
                row["identity_state"] = "manual_review"
                row["identity_warning"] = "Customer name is missing; verify the linked identity."


async def preview(db: Any, actor: Any, after: str | None = None, limit: int = 50) -> dict[str, Any]:
    if actor.role != OWNER:
        raise ForbiddenError("Owner review is required.")
    query: dict[str, Any] = {"is_deleted": False}
    if after:
        if not ObjectId.is_valid(after):
            raise ValidationError("Invalid preview cursor.")
        query["_id"] = {"$gt": ObjectId(after)}
    rows = await db.daily_follow_ups.find(query).sort("_id", 1).limit(limit + 1).to_list(limit + 1)
    output = []
    counts = {
        "missing_names": 0,
        "valid_linked": 0,
        "safe_candidates": 0,
        "manual_review": 0,
        "possible_duplicates": 0,
    }
    for row in rows[:limit]:
        resolved = dict(row)
        await resolve_rows(db, [resolved])
        missing = name_key(row.get("customer_name", "")) in {"", "customer", "name unavailable"}
        counts["missing_names"] += int(missing)
        matches: dict[str, Any]
        try:
            matches = (
                await candidates(db, row.get("customer_name", ""), row.get("customer_number", ""))
                if not missing
                else {"exact": [], "partial": [], "truncated": False}
            )
        except ValueError:
            matches = {"exact": [], "partial": [], "truncated": False}
        state = resolved.get("identity_state", "independent")
        safe = len(matches["exact"]) == 1 and not matches["truncated"] and state != "manual_review"
        counts["valid_linked"] += int(state == "linked_current")
        counts["safe_candidates"] += int(safe and not row.get("customer_id"))
        counts["manual_review"] += int(
            state == "manual_review"
            or bool(matches["partial"])
            or len(matches["exact"]) > 1
            or missing
        )
        counts["possible_duplicates"] += int(bool(matches["exact"] or matches["partial"]))
        token = fingerprint(
            [
                str(row["_id"]),
                row.get("version", 1),
                row.get("customer_id"),
                row.get("customer_name"),
                row.get("customer_number"),
                matches,
            ]
        )
        output.append(
            {
                "id": str(row["_id"]),
                "version": row.get("version", 1),
                "missing_name": missing,
                "identity_state": state,
                "matches": matches,
                "preview_fingerprint": token,
            }
        )
    return {
        "mode": "read_only",
        "items": output,
        "counts": counts,
        "has_more": len(rows) > limit,
        "next_cursor": str(rows[limit - 1]["_id"]) if len(rows) > limit else None,
    }


async def apply_link(db: Any, actor: Any, record_id: str, body: Any) -> dict[str, Any]:
    if actor.role != OWNER:
        raise ForbiddenError("Owner review is required.")
    row = await db.daily_follow_ups.find_one(
        {"_id": ObjectId(record_id), "is_deleted": False, "version": body.version}
    )
    if not row:
        raise ConflictError("Record changed. Generate a fresh preview.")
    matches = await candidates(db, row.get("customer_name", ""), row.get("customer_number", ""))
    expected = fingerprint(
        [
            str(row["_id"]),
            row.get("version", 1),
            row.get("customer_id"),
            row.get("customer_name"),
            row.get("customer_number"),
            matches,
        ]
    )
    if not hmac.compare_digest(body.preview_fingerprint, expected):
        raise ConflictError("Preview is stale. Generate a fresh preview.")
    if body.customer_id not in matches["exact"] + matches["partial"] or matches["truncated"]:
        raise ValidationError("Review a bounded candidate set before linking.")
    customer = await db.customers.find_one({"_id": ObjectId(body.customer_id), "is_deleted": False})
    uid = (customer or {}).get("user_id")
    if not ObjectId.is_valid(uid) or not await db.users.find_one(
        {"_id": ObjectId(uid), "role": "customer", "is_deleted": False}
    ):
        raise ConflictError("Customer account ownership must be repaired separately.")
    checked = dict(row)
    await resolve_rows(db, [checked])
    if checked.get("identity_state") == "manual_review" or (
        row.get("customer_id") and row["customer_id"] != body.customer_id
    ):
        raise ConflictError(
            "Repair inconsistent source relationships first. This action cannot merge customers."
        )
    for field, coll in (
        ("application_id", "applications"),
        ("lead_id", "leads"),
        ("case_id", "application_workflows"),
    ):
        if row.get(field):
            source = await db[coll].find_one({"_id": ObjectId(row[field]), "is_deleted": False})
            if (
                not source
                or source.get("customer_id") != body.customer_id
                or (source.get("user_id") and source["user_id"] != uid)
            ):
                raise ConflictError(
                    "Choose the authoritative source customer; source records are never rewritten here."
                )
    before = {field: row[field] for field in ("customer_id", "user_id") if field in row}
    after = {"customer_id": body.customer_id, "user_id": uid}
    return await correction(db, actor, row, before, after, body.reason, "identity_link")


async def correction(
    db: Any,
    actor: Any,
    row: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
    reason: str,
    source: str,
) -> dict[str, Any]:
    from app.shared.audit_log import AuditLog
    from app.utils.datetime import utc_now

    if len(row.get("history", [])) >= 250:
        raise ConflictError("History limit reached; archive with Owner review.")
    event_id = str(ObjectId())
    event = {
        "id": event_id,
        "source": source,
        "actor_id": actor.require_id(),
        "at": utc_now(),
        "reason": reason,
        "before": before,
        "after": after,
    }
    changes = {**after, "updated_by": actor.require_id(), "updated_at": utc_now()}
    if "customer_id" in after:
        changes["customer_oid"] = (
            ObjectId(after["customer_id"]) if after.get("customer_id") else None
        )
    update = {"$set": changes, "$inc": {"version": 1}, "$push": {"history": event}}
    absent = {key: "" for key in ("customer_id", "user_id") if key not in after}
    if "customer_id" not in after:
        absent["customer_oid"] = ""
    if absent:
        update["$unset"] = absent
    audit = AuditLog(
        event_type="daily_" + source,
        user_id=actor.require_id(),
        metadata={"record_id": str(row["_id"]), "event_id": event_id, "reason": reason},
    )
    # A supported replica-set transaction is mandatory; there is no partial-write fallback.
    async with await db.client.start_session() as session, session.start_transaction():
        updated = await db.daily_follow_ups.update_one(
            {"_id": row["_id"], "version": row["version"], "is_deleted": False},
            update,
            session=session,
        )
        if not updated.modified_count:
            raise ConflictError("Record changed. Generate a fresh preview.")
        await db.audit_logs.insert_one(
            audit.model_dump(by_alias=True, exclude={"id"}), session=session
        )
    return {"id": str(row["_id"]), "version": row["version"] + 1, "event_id": event_id}


async def rollback_link(db: Any, actor: Any, record_id: str, body: Any) -> dict[str, Any]:
    if actor.role != OWNER:
        raise ForbiddenError("Owner review is required.")
    row = await db.daily_follow_ups.find_one(
        {"_id": ObjectId(record_id), "version": body.version, "is_deleted": False}
    )
    last = (row or {}).get("history", [])[-1:]
    if (
        not row
        or not last
        or last[0].get("id") != body.event_id
        or last[0].get("source") != "identity_link"
    ):
        raise ConflictError(
            "Only the latest unchanged identity link can be rolled back. Review newer history separately."
        )
    event = last[0]
    if any(row.get(k) != v for k, v in event["after"].items()):
        raise ConflictError("Identity changed after linking; review manually.")
    return await correction(
        db, actor, row, event["after"], event["before"], body.reason, "identity_link_rollback"
    )
