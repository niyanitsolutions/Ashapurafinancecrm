"""Atomic ownership handovers. Existing assigned_to fields remain authoritative."""

import hashlib
import json
from typing import Any, Literal

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import DuplicateKeyError, OperationFailure

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.features.access_control.permission_engine import PermissionEngine
from app.features.auth.models import User
from app.features.auth.role_context import effective_user
from app.shared.audit_log import AuditLog
from app.utils.datetime import utc_now

RecordType = Literal[
    "leads", "applications", "application_workflows", "daily_follow_ups", "operational_issues"
]
RULES = {
    "leads": ("leads", "leads"),
    "applications": ("customer", "customers"),
    "application_workflows": ("loan_management", "applications"),
    "daily_follow_ups": ("daily_operations", "follow-ups"),
    "operational_issues": ("daily_operations", "issues"),
}


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    collection: RecordType
    id: str = Field(pattern=r"^[a-f0-9]{24}$")
    version: int = Field(ge=1)


class TransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    records: list[Reference] = Field(min_length=1, max_length=50)
    employee_id: str = Field(pattern=r"^[a-f0-9]{24}$")
    remarks: str = Field(default="", max_length=1000)
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,100}$")


async def employee_id(db: Any, actor: User) -> str:
    if actor.role == "owner":
        return actor.require_id()  # Existing Owner assignment representation.
    row = await db.employees.find_one(
        {"user_id": actor.require_id(), "status": "active", "is_deleted": False}, {"_id": 1}
    )
    if actor.role != "employee" or not row:
        raise ForbiddenError("An active staff identity is required.")
    return str(row["_id"])


async def permit(
    db: Any,
    actor: User,
    collection: str,
    row: dict[str, Any],
    action: str,
    cache: dict[Any, Any] | None = None,
) -> None:
    module, resource = RULES[collection]
    if collection == "application_workflows" and row.get("case_type") != "loan":
        raise ValidationError("Only loan cases support this transfer operation.")
    key = (
        actor.require_id(),
        actor.role,
        module,
        resource,
        action,
        row.get("branch_id"),
        row.get("department_id"),
        row.get("stage"),
        row.get("current_status"),
    )
    if cache is not None and key in cache:
        return
    stage = (
        row.get("stage")
        if collection == "leads"
        else row.get("current_status")
        if collection == "application_workflows"
        else None
    )
    if stage:
        child = await db.permissions.find_one(
            {"module": module, "resource": resource + "." + stage, "is_deleted": False},
            {"actions": 1},
        )
        if child and action in child.get("actions", []):
            resource += "." + stage
    engine = PermissionEngine(db)
    if not await engine.has_permission(
        actor,
        module=module,
        resource=resource,
        action=action,
        branch_id=row.get("branch_id"),
        department_id=row.get("department_id"),
    ):
        raise ForbiddenError("Required transfer or record permission is missing.")
    if cache is not None:
        cache[key] = True


async def receiver(db: Any, eid: str, actor: User) -> tuple[User, str]:
    row = await db.employees.find_one(
        {"_id": ObjectId(eid), "status": "active", "is_deleted": False}
    )
    if row:
        user = await db.users.find_one(
            {"_id": ObjectId(row["user_id"]), "status": "active", "is_deleted": False}
        )
        if user:
            return await effective_user(db, User.model_validate(user), "employee"), row[
                "display_name"
            ]
    if actor.role == "owner" and eid == actor.require_id():
        return actor, "Owner"
    raise ValidationError("Receiving employee is inactive, invalid or has no active login access.")


async def batch_graph(db: Any, records: list[Reference]) -> dict[tuple[str, str], dict[str, Any]]:
    projection = {
        "assigned_to": 1,
        "version": 1,
        "application_id": 1,
        "lead_id": 1,
        "case_id": 1,
        "customer_id": 1,
        "case_type": 1,
        "stage": 1,
        "current_status": 1,
        "branch_id": 1,
        "department_id": 1,
        "lead_code": 1,
        "application_code": 1,
        "case_code": 1,
        "last_transfer": 1,
    }
    graph: dict[tuple[str, str], dict[str, Any]] = {}
    for collection in RULES:
        ids = [ObjectId(r.id) for r in records if r.collection == collection]
        if ids:
            async for row in db[collection].find(
                {"_id": {"$in": ids}, "is_deleted": False}, projection
            ):
                graph[(collection, str(row["_id"]))] = row
    if any((r.collection, r.id) not in graph for r in records):
        raise NotFoundError("A selected record is unavailable; nothing was transferred.")
    lead_ids = {r.id for r in records if r.collection == "leads"}
    app_ids = {r.id for r in records if r.collection == "applications"}
    case_ids = set()
    for row in graph.values():
        if row.get("application_id"):
            app_ids.add(row["application_id"])
        if row.get("lead_id"):
            lead_ids.add(row["lead_id"])
        if row.get("case_id"):
            case_ids.add(row["case_id"])
    if any(not ObjectId.is_valid(i) for i in app_ids | lead_ids | case_ids):
        raise ConflictError("A source reference requires Owner review.")
    if case_ids:
        async for row in db.application_workflows.find(
            {"_id": {"$in": [ObjectId(i) for i in case_ids]}, "is_deleted": False}, projection
        ):
            graph[("application_workflows", str(row["_id"]))] = row
            app_ids.add(row["application_id"])
    if app_ids or lead_ids:
        async for row in db.applications.find(
            {
                "is_deleted": False,
                "$or": [
                    {"_id": {"$in": [ObjectId(i) for i in app_ids]}},
                    {"lead_id": {"$in": list(lead_ids)}},
                ],
            },
            projection,
        ).limit(201):
            graph[("applications", str(row["_id"]))] = row
            app_ids.add(str(row["_id"]))
            if row.get("lead_id"):
                lead_ids.add(row["lead_id"])
    if lead_ids:
        if any(not ObjectId.is_valid(i) for i in lead_ids):
            raise ConflictError("A Lead reference requires Owner review.")
        apps = (
            await db.applications.find(
                {"lead_id": {"$in": list(lead_ids)}, "is_deleted": False}, {"lead_id": 1}
            )
            .limit(201)
            .to_list(201)
        )
        if any(sum(a["lead_id"] == lid for a in apps) > 1 for lid in lead_ids) or len(apps) > 200:
            raise ConflictError(
                "A shared Lead has multiple Applications; Owner relationship review is required. No siblings were reassigned."
            )
        async for row in db.leads.find(
            {"_id": {"$in": [ObjectId(i) for i in lead_ids]}, "is_deleted": False}, projection
        ):
            graph[("leads", str(row["_id"]))] = row
    for collection in ("application_workflows", "daily_follow_ups"):
        query: dict[str, Any] = {"application_id": {"$in": list(app_ids)}}
        if collection == "daily_follow_ups":
            query = {"$or": [query, {"lead_id": {"$in": list(lead_ids)}}]}
        if app_ids or lead_ids:
            async for row in (
                db[collection].find({**query, "is_deleted": False}, projection).limit(201)
            ):
                graph[(collection, str(row["_id"]))] = row
    if len(graph) > 200:
        raise ValidationError(
            "Related records exceed the atomic batch limit. Select fewer records."
        )
    for (collection, rid), row in graph.items():
        if row.get("case_id") and ("application_workflows", row["case_id"]) not in graph:
            raise ConflictError("Loan case relationship requires Owner review.")
        if row.get("application_id"):
            app = graph.get(("applications", row["application_id"]))
            if not app or (row.get("customer_id") and row["customer_id"] != app.get("customer_id")):
                raise ConflictError("Application identity relationship requires Owner review.")
        if row.get("lead_id") and ("leads", row["lead_id"]) not in graph:
            raise ConflictError("Lead relationship requires Owner review.")
    return graph


async def transfer(db: Any, actor: User, body: TransferRequest) -> dict[str, Any]:
    own = await employee_id(db, actor)
    refs = [(r.collection, r.id) for r in body.records]
    if len(set(refs)) != len(refs):
        raise ValidationError("Select each record only once.")
    digest = hashlib.sha256(json.dumps(body.model_dump(), sort_keys=True).encode()).hexdigest()
    receipt_id = ObjectId(
        hashlib.sha256((actor.require_id() + body.request_id).encode()).hexdigest()[:24]
    )
    old = await db.audit_logs.find_one({"_id": receipt_id})
    if old:
        if old.get("metadata", {}).get("fingerprint") != digest:
            raise ConflictError("Request key already belongs to a different transfer.")
        return dict(old["metadata"]["result"])
    target, target_name = await receiver(db, body.employee_id, actor)
    changes = await batch_graph(db, body.records)
    cache: dict[Any, Any] = {}
    for ref in body.records:
        if changes[(ref.collection, ref.id)].get("version", 1) != ref.version:
            raise ConflictError(f"Record {ref.id} changed. Refresh the selection.")
    for (collection, rid), row in changes.items():
        await permit(
            db, actor, collection, row, "assign" if (collection, rid) in refs else "edit", cache
        )
        if actor.role != "owner" and row.get("assigned_to") != own:
            raise ForbiddenError("You can transfer only records currently assigned to you.")
        await permit(db, target, collection, row, "view", cache)
        await permit(db, target, collection, row, "edit", cache)
        if row.get("assigned_to") == body.employee_id:
            raise ConflictError("A selected record is already assigned to the receiving employee.")
    prior = (
        await db.audit_logs.find(
            {
                "event_type": "crm_record_transferred",
                "metadata.from_employee_id": body.employee_id,
                "$or": [
                    {"metadata.collection": c, "metadata.record_id": rid} for c, rid in changes
                ],
            },
            {"metadata.collection": 1, "metadata.record_id": 1},
        )
        .limit(201)
        .to_list(201)
    )
    returned = {(r["metadata"]["collection"], r["metadata"]["record_id"]) for r in prior}
    applications_by_lead = {
        r.get("lead_id"): rid
        for (c, rid), r in changes.items()
        if c == "applications" and r.get("lead_id")
    }
    applications_by_case = {
        rid: r.get("application_id")
        for (c, rid), r in changes.items()
        if c == "application_workflows"
    }
    now = utc_now()
    result = {"bulk_reference": str(receipt_id), "selected": len(refs), "updated": len(changes)}
    receipt = AuditLog(
        event_type="crm_transfer_batch",
        user_id=actor.require_id(),
        metadata={"fingerprint": digest, "result": result},
    )
    try:
        async with await db.client.start_session() as session, session.start_transaction():
            await db.audit_logs.insert_one(
                {**receipt.model_dump(by_alias=True, exclude={"id"}), "_id": receipt_id},
                session=session,
            )
            if actor.role == "employee":
                active = await db.employees.update_one(
                    {"_id": ObjectId(own), "status": "active", "is_deleted": False},
                    {"$inc": {"transfer_epoch": 1}},
                    session=session,
                )
                login = await db.users.update_one(
                    {
                        "_id": ObjectId(actor.require_id()),
                        "status": "active",
                        "is_deleted": False,
                        **({"employee_access.enabled": True} if actor.employee_access else {}),
                    },
                    {"$inc": {"transfer_epoch": 1}},
                    session=session,
                )
                if not active.matched_count or not login.matched_count:
                    raise ConflictError("Sending employee access changed. Nothing was transferred.")
            # Receiver eligibility changes contend with this guarded write, not a stale preflight read.
            if target.role == "employee":
                check = await db.employees.update_one(
                    {"_id": ObjectId(body.employee_id), "status": "active", "is_deleted": False},
                    {"$inc": {"transfer_epoch": 1}},
                    session=session,
                )
                if not check.matched_count:
                    raise ConflictError("Receiving employee changed. Refresh and review.")
                check = await db.users.update_one(
                    {
                        "_id": ObjectId(target.require_id()),
                        "status": "active",
                        "is_deleted": False,
                        **({"employee_access.enabled": True} if target.employee_access else {}),
                    },
                    {"$inc": {"transfer_epoch": 1}},
                    session=session,
                )
                if not check.matched_count:
                    raise ConflictError("Receiving login access changed. Refresh and review.")
            for (collection, rid), row in changes.items():
                event_id = ObjectId()
                app_id = (
                    rid
                    if collection == "applications"
                    else row.get("application_id")
                    or applications_by_case.get(str(row.get("case_id")))
                    or applications_by_lead.get(
                        rid if collection == "leads" else str(row.get("lead_id"))
                    )
                )
                work_key = (
                    "application:" + app_id
                    if app_id
                    else "lead:" + (rid if collection == "leads" else row["lead_id"])
                    if collection == "leads" or row.get("lead_id")
                    else collection + ":" + rid
                )
                event = {
                    "status": "Transferred Back"
                    if (collection, rid) in returned
                    else "Transferred Again"
                    if row.get("last_transfer")
                    else "Transferred",
                    "primary": (collection, rid) in refs,
                    "work_key": work_key,
                    "transfer_id": str(event_id),
                    "source_module": collection,
                    "collection": collection,
                    "record_id": rid,
                    "application_id": app_id,
                    "record_code": row.get("lead_code")
                    or row.get("application_code")
                    or row.get("case_code")
                    or changes.get(("applications", str(app_id)), {}).get("application_code")
                    or rid,
                    "from_employee_id": row.get("assigned_to"),
                    "to_employee_id": body.employee_id,
                    "initiated_by": actor.require_id(),
                    "at": now,
                    "remarks": body.remarks,
                    "bulk_reference": str(receipt_id),
                    "scope": "single_company_database",
                }
                audit = AuditLog(
                    event_type="crm_record_transferred", user_id=actor.require_id(), metadata=event
                )
                updated = await db[collection].update_one(
                    {
                        "_id": row["_id"],
                        "is_deleted": False,
                        "assigned_to": row.get("assigned_to"),
                        "version": row.get("version", 1),
                    },
                    {
                        "$set": {
                            "assigned_to": body.employee_id,
                            "updated_by": actor.require_id(),
                            "updated_at": now,
                            "last_transfer": event,
                            **(
                                {"employee_name": target_name}
                                if collection in {"daily_follow_ups", "operational_issues"}
                                else {}
                            ),
                        },
                        "$inc": {"version": 1},
                    },
                    session=session,
                )
                if not updated.matched_count:
                    raise ConflictError(f"Record {rid} changed; no records were transferred.")
                await db.audit_logs.insert_one(
                    {**audit.model_dump(by_alias=True, exclude={"id"}), "_id": event_id},
                    session=session,
                )
    except DuplicateKeyError:
        saved = await db.audit_logs.find_one({"_id": receipt_id})
        if saved and saved.get("metadata", {}).get("fingerprint") == digest:
            return dict(saved["metadata"]["result"])
        raise ConflictError(
            "Concurrent transfer. Refresh before continuing; no automatic retry."
        ) from None
    except OperationFailure as exc:
        if exc.code == 112 or exc.has_error_label("TransientTransactionError"):
            raise ConflictError("Concurrent ownership change; no automatic retry.") from None
        raise
    return result


async def history(db: Any, actor: User, collection: str, rid: str) -> dict[str, Any]:
    own = await employee_id(db, actor)
    query = {
        "event_type": "crm_record_transferred",
        "metadata.collection": collection,
        "metadata.record_id": rid,
    }
    row = await db[collection].find_one({"_id":ObjectId(rid)}, {"assigned_to":1,"case_type":1,"stage":1,"current_status":1,"branch_id":1,"department_id":1})
    await permit(db,actor,collection,row or {"case_type":"loan"},"view")
    if actor.role != "owner" and (not row or row.get("assigned_to") != own):
        participant = await db.audit_logs.find_one(
            {
                **query,
                "$or": [{"metadata.from_employee_id": own}, {"metadata.to_employee_id": own}],
            },
            {"_id": 1},
        )
        if not participant:
            raise ForbiddenError("Transfer history is unavailable.")
    elif row:
        await permit(db, actor, collection, row, "view")
    rows = (
        await db.audit_logs.find(query, {"metadata": 1})
        .sort("created_at", 1)
        .limit(501)
        .to_list(501)
    )
    if not rows and actor.role != "owner" and (not row or row.get("assigned_to") != own):
        raise ForbiddenError("Transfer history is unavailable.")
    return {
        "items": [r["metadata"] for r in rows[:500]],
        "has_more": len(rows) > 500,
        "current_owner": (row or {}).get("assigned_to"),
    }


async def queue(
    db: Any,
    actor: User,
    *,
    page: int = 1,
    search: str = "",
    direction: str = "all",
    collection: str = "",
    date_from: Any = None,
    date_to: Any = None,
    sort: str = "newest",
) -> dict[str, Any]:
    if sort not in {"newest", "oldest"}:
        raise ValidationError("Choose newest or oldest transfer order.")
    own = await employee_id(db, actor)
    query: dict[str, Any] = {"event_type": "crm_record_transferred", "metadata.primary": True}
    if actor.role != "owner":
        query["$or"] = [{"metadata.from_employee_id": own}, {"metadata.to_employee_id": own}]
    if direction in {"sent", "received"}:
        query["metadata.from_employee_id" if direction == "sent" else "metadata.to_employee_id"] = (
            own
        )
    if collection:
        if collection not in RULES:
            raise ValidationError("Invalid transfer module.")
        query["metadata.source_module"] = collection
    if date_from or date_to:
        from datetime import timedelta

        from app.utils.datetime import ist_date_to_utc_midnight

        query["created_at"] = {}
        if date_from:
            query["created_at"]["$gte"] = ist_date_to_utc_midnight(date_from)
        if date_to:
            query["created_at"]["$lt"] = ist_date_to_utc_midnight(date_to + timedelta(days=1))
    if search:
        import re

        pattern = {"$regex": re.escape(search), "$options": "i"}
        ids = [
            str(e["_id"])
            async for e in db.employees.find({"display_name": pattern}, {"_id": 1}).limit(200)
        ]
        query["$and"] = [
            {
                "$or": [
                    {"metadata.record_id": pattern},
                    {"metadata.record_code": pattern},
                    {"metadata.from_employee_id": {"$in": ids}},
                    {"metadata.to_employee_id": {"$in": ids}},
                ]
            }
        ]
    data = await db.audit_logs.aggregate(
        [
            {"$match": query},
            {"$sort": {"created_at": -1, "_id": -1}},
            {
                "$group": {
                    "_id": "$metadata.work_key",
                    "event": {"$first": "$metadata"},
                    "at": {"$first": "$created_at"},
                }
            },
            {"$set": {"_id": {"collection": "$event.source_module", "id": "$event.record_id"}}},
            {"$sort": {"at": -1 if sort == "newest" else 1, "_id.id": 1}},
            {
                "$facet": {
                    "items": [{"$skip": (page - 1) * 20}, {"$limit": 20}],
                    "total": [{"$count": "value"}],
                }
            },
        ]
    ).to_list(1)
    data = data[0] if data else {"items": [], "total": []}
    current = {}
    for source in RULES:
        record_ids = [
            ObjectId(r["_id"]["id"]) for r in data["items"] if r["_id"]["collection"] == source
        ]
        if record_ids:
            async for r in db[source].find(
                {"_id": {"$in": record_ids}, "is_deleted": False},
                {
                    "assigned_to": 1,
                    "last_transfer": 1,
                    "version": 1,
                    "lead_code": 1,
                    "application_code": 1,
                    "case_code": 1,
                },
            ):
                current[(source, str(r["_id"]))] = r
    items = []
    for r in data["items"]:
        source, rid = r["_id"]["collection"], r["_id"]["id"]
        row = current.get((source, rid), {})
        latest = row.get("last_transfer", r["event"])
        items.append(
            {
                "collection": source,
                "id": rid,
                "version": row.get("version", 1),
                "code": row.get("lead_code")
                or row.get("application_code")
                or row.get("case_code")
                or r["event"].get("record_code")
                or rid,
                "current_owner": row.get("assigned_to"),
                "can_work": bool(row) and (actor.role == "owner" or row.get("assigned_to") == own),
                "transfer": latest,
                "status": ("Received - " + latest.get("status", "Transferred"))
                if row.get("assigned_to") == own
                else latest.get("status", "Transferred"),
            }
        )
    names = {
        i
        for r in items
        for i in [
            r["current_owner"],
            r["transfer"].get("from_employee_id"),
            r["transfer"].get("to_employee_id"),
        ]
        if i and ObjectId.is_valid(i)
    }
    employees = (
        {
            str(e["_id"]): e["display_name"]
            async for e in db.employees.find(
                {"_id": {"$in": [ObjectId(i) for i in names]}}, {"display_name": 1}
            )
        }
        if names
        else {}
    )
    for r in items:
        for k in ("from_employee_id", "to_employee_id"):
            r["transfer"][k.replace("_id", "_name")] = employees.get(
                r["transfer"].get(k), "Owner / unassigned"
            )
        r["current_owner_name"] = employees.get(r["current_owner"], "Owner / unavailable")
    return {
        "items": items,
        "total": data["total"][0]["value"] if data["total"] else 0,
        "page": page,
        "page_size": 20,
    }


class ContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    collection: RecordType
    ids: list[str] = Field(min_length=1, max_length=200)


async def contexts(db: Any, actor: User, body: ContextRequest) -> dict[str, Any]:
    own = await employee_id(db, actor)
    if any(not ObjectId.is_valid(i) for i in body.ids):
        raise ValidationError("Invalid record ID.")
    query = {"_id": {"$in": [ObjectId(i) for i in body.ids]}, "is_deleted": False}
    if actor.role != "owner":
        query["assigned_to"] = own
    rows = (
        await db[body.collection]
        .find(
            query,
            {
                "assigned_to": 1,
                "version": 1,
                "last_transfer": 1,
                "case_type": 1,
                "stage": 1,
                "current_status": 1,
                "branch_id": 1,
                "department_id": 1,
            },
        )
        .to_list(200)
    )
    cache: dict[Any, Any] = {}
    result = []
    for row in rows:
        await permit(db, actor, body.collection, row, "view", cache)
        result.append(
            {
                "id": str(row["_id"]),
                "version": row.get("version", 1),
                "assigned_to": row.get("assigned_to"),
                "transfer": row.get("last_transfer"),
            }
        )
    ids = {
        i
        for r in result
        for i in [
            r.get("assigned_to"),
            (r.get("transfer") or {}).get("from_employee_id"),
            (r.get("transfer") or {}).get("to_employee_id"),
        ]
        if ObjectId.is_valid(i)
    }
    names = (
        {
            str(e["_id"]): e["display_name"]
            async for e in db.employees.find(
                {"_id": {"$in": [ObjectId(i) for i in ids]}}, {"display_name": 1}
            )
        }
        if ids
        else {}
    )
    for r in result:
        r["assigned_to_name"] = names.get(r["assigned_to"], "Owner / unavailable")
        if r.get("transfer"):
            for k in ("from_employee_id", "to_employee_id"):
                r["transfer"][k.replace("_id", "_name")] = names.get(
                    r["transfer"].get(k), "Owner / unassigned"
                )
    return {"items": result}


class ReceiverQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    records: list[Reference] = Field(min_length=1, max_length=50)
    search: str = Field(default="", max_length=100)


async def eligible_receivers(db: Any, actor: User, body: ReceiverQuery) -> dict[str, Any]:
    import re

    own = await employee_id(db, actor)
    graph = await batch_graph(db, body.records)
    cache: dict[Any, Any] = {}
    for ref in body.records:
        row = graph[(ref.collection, ref.id)]
        await permit(db, actor, ref.collection, row, "assign", cache)
        if actor.role != "owner" and row.get("assigned_to") != own:
            raise ForbiddenError("Only current assigned work can be transferred.")
    query = {"status": "active", "is_deleted": False}
    if body.search:
        query["display_name"] = {"$regex": re.escape(body.search), "$options": "i"}
    employees = (
        await db.employees.find(query, {"display_name": 1, "user_id": 1})
        .sort("display_name", 1)
        .limit(51)
        .to_list(51)
    )
    uids = [ObjectId(e["user_id"]) for e in employees if ObjectId.is_valid(e.get("user_id"))]
    users = {
        str(u["_id"]): u
        async for u in db.users.find(
            {"_id": {"$in": uids}, "status": "active", "is_deleted": False},
            {"role": 1, "mobile": 1, "status": 1, "employee_access.enabled": 1},
        )
    }
    items = []
    for employee in employees[:50]:
        user = users.get(employee["user_id"])
        eid = str(employee["_id"])
        if not user or any(row.get("assigned_to") == eid for row in graph.values()):
            continue
        if user.get("role") != "employee" and not (
            user.get("role") in {"customer", "referral_partner"}
            and user.get("employee_access", {}).get("enabled")
        ):
            continue
        # Context is evaluated only against a verified active Employee profile/login.
        # Membership adds one role context, never a union of primary-role permissions.
        target = User.model_validate(user).model_copy(update={"role": "employee"})
        try:
            for (collection, _rid), row in graph.items():
                await permit(db, target, collection, row, "view", cache)
                await permit(db, target, collection, row, "edit", cache)
        except ForbiddenError:
            continue
        items.append({"id": eid, "name": employee["display_name"]})
    if actor.role == "owner" and not any(r.get("assigned_to") == own for r in graph.values()):
        items.insert(0, {"id": own, "name": "Owner (myself)"})
    return {"items": items, "has_more": len(employees) > 50}
