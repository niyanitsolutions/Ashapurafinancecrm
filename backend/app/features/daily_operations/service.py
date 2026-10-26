import re
from datetime import date, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.constants.roles import EMPLOYEE, OWNER
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.features.access_control.permission_engine import PermissionEngine
from app.features.auth.models import User
from app.features.daily_operations.schemas import FollowUpInput, IssueInput, ProgressInput
from app.features.leads.service import LeadService
from app.shared.base_document import BaseDocument
from app.utils.datetime import ist_date_to_utc_midnight, to_ist, utc_now

COLLECTIONS = {
    "follow-ups": "daily_follow_ups",
    "issues": "operational_issues",
    "progress": "daily_progress_entries",
}
OPEN_STATUSES = ["FOLLOW UP PENDING", "NEXT FOLLOW UP"]


def calendar_values(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: to_ist(value).date().isoformat()
        if key in {"date", "remarks_date", "due_date"} and isinstance(value, datetime)
        else value
        for key, value in values.items()
    }


def stored_values(payload: FollowUpInput | IssueInput | ProgressInput) -> dict[str, Any]:
    return {
        key: ist_date_to_utc_midnight(value)
        if isinstance(value, date) and not isinstance(value, datetime)
        else value
        for key, value in payload.model_dump().items()
    }


def public(doc: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    from app.features.daily_operations.follow_status import effective_status

    if "due_date" in doc and "customer_number" in doc:
        doc = {**doc, "status": effective_status(doc["status"], doc.get("due_date"), now or utc_now())}
    doc = calendar_values(doc)
    if "history" in doc:
        doc["history"] = [
            {
                **event,
                "before": calendar_values(event["before"]) if event.get("before") else None,
                "after": calendar_values(event["after"]) if event.get("after") else None,
            }
            for event in doc["history"]
        ]
    return {
        **{k: v for k, v in doc.items() if k not in {"_id", "import_key", "lead_oid", "case_oid"}},
        "id": str(doc["_id"]),
    }


class DailyOperationsService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db

    async def authorize(self, actor: User, resource: str, action: str = "view") -> None:
        if not await PermissionEngine(self.db).has_permission(
            actor, module="daily_operations", resource=resource, action=action
        ):
            raise ForbiddenError("You do not have permission for this daily operations action.")

    async def employee_id(self, actor: User) -> str:
        if actor.role == OWNER:
            return actor.require_id()
        employee = await self.db.employees.find_one(
            {"user_id": actor.require_id(), "is_deleted": False, "status": "active"}, {"_id": 1}
        )
        if actor.role != EMPLOYEE or not employee:
            raise ForbiddenError("An active employee profile is required.")
        return str(employee["_id"])

    async def scope(self, actor: User, kind: str) -> dict[str, Any]:
        query: dict[str, Any] = {"is_deleted": False}
        if actor.role != OWNER:
            employee_id = await self.employee_id(actor)
            if kind == "issues":
                query["$or"] = [{"assigned_to": employee_id}, {"created_by": actor.require_id()}]
            else:
                # Scope against CURRENT lead ownership, not a stale assignment snapshot.
                # A lookup-based list query below enforces this without an unbounded ID list.
                query["assigned_to"] = employee_id
        return query

    async def validate_follow_up(self, payload: FollowUpInput, actor: User) -> dict[str, Any]:
        await self.authorize(actor, "follow-ups")
        from app.features.daily_operations.entries import assignee, case_row

        if payload.case_id:
            from math import isfinite

            linked = await case_row(self, actor, payload.case_id)
            application = await self.db.applications.find_one(
                {"_id": ObjectId(linked["application_id"]), "is_deleted": False}
            )
            if payload.lead_id and (
                not application or application.get("lead_id") != payload.lead_id
            ):
                raise ValidationError("Loan case and lead do not belong to the same application.")
            if payload.status == "DISBURSE" and (
                linked["canonical_status"] != "disbursed"
                or linked["disbursed_amount"] is None
                or not isfinite(linked["disbursed_amount"])
                or linked["disbursed_amount"] < 0
                or linked["disbursed_at"] is None
                or not linked["disbursed_reference"]
            ):
                raise ValidationError(
                    "Choose a loan with a verified disbursement before marking DISBURSE."
                )
            data = stored_values(payload)
            data.update(
                {
                    key: linked[key]
                    for key in ("customer_name", "customer_number", "loan_type", "bank")
                }
            )
            data.update(await assignee(self, actor, linked.get("assigned_to"), ""))
            data["source"] = "crm"
            return data
        if not payload.lead_id:
            from app.shared.customer_identity import normalize_mobile, normalized_name

            try:
                mobile = normalize_mobile(payload.customer_number)
            except ValueError:
                mobile = payload.customer_number  # Preserve manual international numbers.
            matches = (
                await LeadService(self.db).check_duplicate(mobile, actor)
                if mobile.isdigit() and len(mobile) == 10 and mobile[0] in "6789"
                else []
            )
            if matches:
                matching = matches[0]
                if normalized_name(matching.full_name) != normalized_name(payload.customer_name):
                    raise ValidationError(
                        "This mobile belongs to a different customer name. Review the linked lead before continuing."
                    )
                return await self.validate_follow_up(
                    payload.model_copy(update={"lead_id": matching.require_id()}), actor
                )
            customer = await self.db.customers.find_one(
                {"mobile": mobile, "is_deleted": False}, {"_id": 1}
            )
            if customer:
                raise ValidationError(
                    "Use Link existing CRM record to choose the existing customer's loan. This daily entry does not create a new customer."
                )
            data = stored_values(payload)
            data.update(await assignee(self, actor, payload.assigned_to, payload.employee_name))
            data["source"] = "manual"
            return data
        lead = await LeadService(self.db).get_lead_scoped(payload.lead_id, actor)
        if lead.product_category != "loan":
            raise ValidationError("Daily loan follow-ups require a loan lead.")
        if not lead.assigned_to:
            raise ValidationError("Assign the lead in Leads before scheduling a follow-up.")
        product = await self.db.loan_products.find_one({"_id": ObjectId(lead.product_id)})
        assigned_employee = await self.db.employees.find_one(
            {"_id": ObjectId(lead.assigned_to), "is_deleted": False}, {"display_name": 1}
        )
        return {
            **stored_values(payload),
            "assigned_to": lead.assigned_to,
            "customer_name": lead.full_name,
            "customer_number": lead.mobile,
            "loan_type": product.get("name", "") if product else "",
            "lead_code": lead.lead_code,
            "employee_name": assigned_employee["display_name"] if assigned_employee else "Owner",
        }

    async def validate_issue(
        self, payload: IssueInput, actor: User, old: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if old is None and payload.status != "OPEN":
            raise ValidationError("New issues must start OPEN.")
        if old:
            transitions = {
                "OPEN": {"OPEN", "IN PROGRESS", "RESOLVED"},
                "IN PROGRESS": {"IN PROGRESS", "RESOLVED"},
                "RESOLVED": {"RESOLVED", "REOPENED"},
                "REOPENED": {"REOPENED", "IN PROGRESS", "RESOLVED"},
            }
            if payload.status not in transitions[old["status"]]:
                raise ValidationError("Unsupported issue status transition.")
        own_id = await self.employee_id(actor)
        if "assigned_to" not in payload.model_fields_set or (
            actor.role != OWNER and payload.assigned_to is None and old
        ):
            payload = payload.model_copy(
                update={
                    "assigned_to": (old or {}).get("assigned_to")
                    or (own_id if actor.role != OWNER else None)
                }
            )
        if payload.assigned_to != (old or {}).get("assigned_to") and not (
            payload.assigned_to == own_id and not (old or {}).get("assigned_to")
        ):
            await self.authorize(actor, "issues", "assign")
        if payload.assigned_to:
            employee = await self.db.employees.find_one(
                {"_id": ObjectId(payload.assigned_to), "is_deleted": False, "status": "active"}
            )
            if not employee:
                raise ValidationError("Assigned To must identify an active employee.")
        if payload.status == "RESOLVED":
            await self.authorize(actor, "issues", "approve")
        return {
            **stored_values(payload),
            "assigned_to": payload.assigned_to or (own_id if actor.role != OWNER else None),
            "resolved_at": (old or {}).get("resolved_at") or utc_now()
            if payload.status == "RESOLVED"
            else None,
        }

    async def get(self, kind: str, record_id: str, actor: User) -> dict[str, Any]:
        await self.authorize(actor, kind)
        if kind == "progress":
            from app.features.daily_operations.entries import get_progress

            return await get_progress(self, actor, record_id)
        if not ObjectId.is_valid(record_id):
            raise NotFoundError("Record not found.")
        query = await self.scope(actor, kind)
        # Follow-up ownership can move with its lead since the last edit.
        if kind == "follow-ups":
            query.pop("assigned_to", None)
        doc: dict[str, Any] | None = await self.db[COLLECTIONS[kind]].find_one(
            {**query, "_id": ObjectId(record_id)}
        )
        if not doc:
            raise NotFoundError("Record not found.")
        if kind == "follow-ups":
            if (
                not doc.get("lead_id")
                and not doc.get("case_id")
                and actor.role != OWNER
                and doc.get("assigned_to") != await self.employee_id(actor)
            ):
                raise ForbiddenError("This daily entry is not assigned to you.")
            current = await self.validate_follow_up(
                FollowUpInput.model_validate(
                    {
                        k: value
                        for k, value in calendar_values(doc).items()
                        if k in FollowUpInput.model_fields
                    }
                ),
                actor,
            )
            if doc.get("lead_id") or doc.get("case_id"):
                doc = {
                    **doc,
                    **{
                        key: current[key]
                        for key in (
                            "assigned_to",
                            "employee_name",
                            "customer_name",
                            "customer_number",
                            "loan_type",
                        )
                    },
                }
        return doc

    async def save(
        self,
        kind: str,
        payload: FollowUpInput | IssueInput | ProgressInput,
        actor: User,
        record_id: str | None = None,
        version: int | None = None,
        import_key: str | None = None,
    ) -> dict[str, Any]:
        await self.authorize(actor, kind, "edit" if record_id else "create")
        if isinstance(payload, ProgressInput):
            from app.features.daily_operations.entries import save_progress

            return await save_progress(self, actor, payload, record_id, version, import_key)
        old = await self.get(kind, record_id, actor) if record_id else None
        if (
            old
            and kind == "follow-ups"
            and (
                payload.lead_id != old["lead_id"]  # type: ignore[union-attr]
                or (old.get("case_id") and payload.case_id != old.get("case_id"))  # type: ignore[union-attr]
            )
        ):
            raise ValidationError(
                "Linked lead and loan case cannot be changed; create a new record."
            )
        if isinstance(payload, FollowUpInput):
            data = await self.validate_follow_up(payload, actor)
        else:
            data = await self.validate_issue(payload, actor, old)
        now = utc_now()
        if isinstance(payload, FollowUpInput):
            from app.features.daily_operations.follow_status import effective_status

            data["status"] = effective_status(data["status"], data.get("due_date"), now)
        event = {
            "source": "manual",
            "actor_id": actor.require_id(),
            "at": now,
            "before": {k: old.get(k) for k in data} if old else None,
            "after": data,
            "import_key": import_key,
        }
        collection = self.db[COLLECTIONS[kind]]
        if old:
            if len(old.get("history", [])) >= 250:
                raise ConflictError(
                    "History limit reached; ask an administrator to archive this case."
                )
            updates = {**data, "updated_by": actor.require_id(), "updated_at": now}
            if kind == "follow-ups" and data.get("case_id"):
                updates["case_oid"] = ObjectId(data["case_id"])
            if kind == "issues" and old.get("assigned_to") != data.get("assigned_to"):
                updates["assignment_notification_pending"] = (
                    str(ObjectId()) if data.get("assigned_to") else None
                )
            updated = await collection.find_one_and_update(
                {"_id": old["_id"], "version": version, "is_deleted": False},
                {
                    "$set": updates,
                    "$inc": {"version": 1},
                    "$push": {"history": event},
                },
                return_document=ReturnDocument.AFTER,
            )
            if not updated:
                raise ConflictError("This record changed. Reload it before saving again.")
            return public(updated)
        doc = {
            **BaseDocument(created_by=actor.require_id()).model_dump(exclude={"id"}),
            **data,
            "history": [event],
            "import_key": import_key or str(ObjectId()),
        }
        if kind == "follow-ups" and data.get("lead_id"):
            doc["lead_oid"] = ObjectId(data["lead_id"])
        if kind == "follow-ups" and data.get("case_id"):
            doc["case_oid"] = ObjectId(data["case_id"])
        if kind == "issues":
            doc["employee_id"] = await self.employee_id(actor)
            doc["assignment_notification_pending"] = (
                str(ObjectId()) if data.get("assigned_to") else None
            )
        try:
            inserted = await collection.insert_one(doc)
        except DuplicateKeyError:
            raise ConflictError("This import row has already been processed.") from None
        doc["_id"] = inserted.inserted_id
        return public(doc)

    async def list_records(
        self,
        kind: str,
        actor: User,
        *,
        search: str = "",
        status: str = "",
        employee: str = "",
        employee_name: str = "",
        bank: str = "",
        loan_type: str = "",
        date_from: date | None = None,
        date_to: date | None = None,
        overdue: bool = False,
        page: int = 1,
        page_size: int = 20,
        sort: str = "-date",
    ) -> dict[str, Any]:
        await self.authorize(actor, kind)
        now = utc_now()
        query = await self.scope(actor, kind)
        if kind == "progress":
            query["case_id"] = None  # Linked annotations are already merged with CRM cases.
        if date_from and date_to and date_from > date_to:
            raise ValidationError("Start date must be before end date.")
        if employee:
            query["$and"] = [{"assigned_to": employee}]
        if employee_name:
            matching = (
                await self.db.employees.find(
                    {
                        "display_name": {"$regex": re.escape(employee_name), "$options": "i"},
                        "is_deleted": False,
                    },
                    {"_id": 1},
                )
                .limit(100)
                .to_list(100)
            )
            query.setdefault("$and", []).append(
                {
                    "$or": [
                        {"assigned_to": {"$in": [str(e["_id"]) for e in matching]}},
                        {"employee_name": {"$regex": re.escape(employee_name), "$options": "i"}},
                    ]
                }
            )
        for key, value in (("status", status), ("bank", bank), ("loan_type", loan_type)):
            if value:
                query[key] = value
        if date_from or date_to:
            query["date"] = {}
            if date_from:
                query["date"]["$gte"] = ist_date_to_utc_midnight(date_from)
            if date_to:
                query["date"]["$lte"] = ist_date_to_utc_midnight(date_to)
        if overdue:
            query["due_date"] = {
                "$lt": ist_date_to_utc_midnight(to_ist(utc_now()).date()),
                "$ne": None,
            }
            query.setdefault("$and", []).append({"status": {"$in": OPEN_STATUSES}})
        if search:
            pattern = re.escape(search[:200])
            query.setdefault("$and", []).append(
                {
                    "$or": [
                        {key: {"$regex": pattern, "$options": "i"}}
                        for key in (
                            "customer_name",
                            "customer_number",
                            "lead_code",
                            "bank",
                            "inquiry",
                            "next_action",
                        )
                    ]
                }
            )
        field = sort.lstrip("-")
        if field not in {
            "date",
            "created_at",
            "status",
            "updated_at",
            "due_date",
            "bank",
            "priority",
        }:
            raise ValidationError("Unsupported sort column.")
        pipeline: list[dict[str, Any]] = [{"$project": {"history": 0}}]
        if kind == "follow-ups":
            from app.features.daily_operations.follow_status import status_stage

            pipeline.append(status_stage(now))
            await self.authorize_lead_view(actor)
            if actor.role != OWNER:
                # Old linked rows predate case_oid. Fail closed on their case ownership;
                # new rows use the live indexed case lookup below, including reassignment.
                case_ids = (
                    await self.db.application_workflows.find(
                        {
                            "case_type": "loan",
                            "is_deleted": False,
                            "assigned_to": await self.employee_id(actor),
                            "moved_to_loan_management_at": {"$ne": None},
                        },
                        {"_id": 1},
                    )
                    .limit(2001)
                    .to_list(2001)
                )
                if len(case_ids) > 2000:
                    raise ValidationError(
                        "Ask the Owner to archive older cases before browsing more than 2,000 assigned loans."
                    )
                query.setdefault("$and", []).append(
                    {
                        "$or": [
                            {"case_id": None},
                            {"case_oid": {"$exists": True}},
                            {"case_id": {"$in": [str(c["_id"]) for c in case_ids]}},
                        ]
                    }
                )
            pipeline.append(
                {
                    "$match": {
                        key: value
                        for key, value in query.items()
                        if key in {"is_deleted", "date", "bank", "loan_type", "status", "due_date"}
                    }
                }
            )
            pipeline.extend(
                [
                    {
                        "$lookup": {
                            "from": "application_workflows",
                            "localField": "case_oid",
                            "foreignField": "_id",
                            "as": "linked_case",
                        }
                    },
                    {"$unwind": {"path": "$linked_case", "preserveNullAndEmptyArrays": True}},
                    {
                        "$match": {
                            "$or": [
                                {"case_oid": {"$exists": False}},
                                {"linked_case.is_deleted": False},
                            ]
                        }
                    },
                    {
                        "$lookup": {
                            "from": "leads",
                            "localField": "lead_oid",
                            "foreignField": "_id",
                            "as": "lead",
                        }
                    },
                    {"$unwind": {"path": "$lead", "preserveNullAndEmptyArrays": True}},
                    {"$match": {"$or": [{"lead_id": None}, {"lead.is_deleted": False}]}},
                    {
                        "$set": {
                            "assigned_to": {
                                "$cond": [
                                    {"$ne": [{"$ifNull": ["$case_oid", None]}, None]},
                                    "$linked_case.assigned_to",
                                    {"$ifNull": ["$lead.assigned_to", "$assigned_to"]},
                                ]
                            },
                            "customer_name": {"$ifNull": ["$lead.full_name", "$customer_name"]},
                            "customer_number": {"$ifNull": ["$lead.mobile", "$customer_number"]},
                        }
                    },
                ]
            )
        pipeline.extend(
            [
                {"$match": query},
                {
                    "$facet": {
                        "items": [
                            {"$sort": {field: -1 if sort.startswith("-") else 1, "_id": 1}},
                            {"$skip": (page - 1) * page_size},
                            {"$limit": page_size},
                            {
                                "$project": {
                                    "history": 0,
                                    "lead": 0,
                                    "lead_oid": 0,
                                    "case_oid": 0,
                                    "linked_case": 0,
                                }
                            },
                        ],
                        "total": [{"$count": "value"}],
                        "statuses": [{"$group": {"_id": "$status", "count": {"$sum": 1}}}],
                        "by_employee": [
                            {"$group": {"_id": "$assigned_to", "count": {"$sum": 1}}},
                            {"$sort": {"count": -1, "_id": 1}},
                            {"$limit": 100},
                        ],
                        "by_bank": [
                            {"$group": {"_id": "$bank", "count": {"$sum": 1}}},
                            {"$sort": {"count": -1, "_id": 1}},
                            {"$limit": 100},
                        ],
                        "by_loan_type": [
                            {"$group": {"_id": "$loan_type", "count": {"$sum": 1}}},
                            {"$sort": {"count": -1, "_id": 1}},
                            {"$limit": 100},
                        ],
                    }
                },
            ]
        )
        result = (await self.db[COLLECTIONS[kind]].aggregate(pipeline).to_list(1))[0]
        ids = {item.get("assigned_to") for item in result["items"]} | {
            item.get("employee_id") for item in result["items"]
        }
        employees = {
            str(e["_id"]): e["display_name"]
            for e in await self.db.employees.find(
                {
                    "_id": {
                        "$in": [
                            ObjectId(value) for value in ids if value and ObjectId.is_valid(value)
                        ]
                    },
                    "is_deleted": False,
                },
                {"display_name": 1},
            ).to_list(page_size * 2)
        }
        for item in result["items"]:
            item["employee_name"] = (
                item.get("employee_name")
                if not item.get("case_id") and not item.get("lead_id")
                else ""
            ) or employees.get(
                item.get("employee_id") if kind == "issues" else item.get("assigned_to"),
                "Owner"
                if (item.get("employee_id") if kind == "issues" else item.get("assigned_to"))
                == actor.require_id()
                and actor.role == OWNER
                else "",
            )
            item["assigned_to_name"] = employees.get(
                item.get("assigned_to"),
                "Owner"
                if item.get("assigned_to") == actor.require_id() and actor.role == OWNER
                else "Unassigned",
            )
        return {
            "items": [public(item, now) for item in result["items"]],
            "total": result["total"][0]["value"] if result["total"] else 0,
            "statuses": {item["_id"]: item["count"] for item in result["statuses"]},
            "breakdowns": {
                key: [
                    {"label": str(entry["_id"] or "Unassigned"), "count": entry["count"]}
                    for entry in result[key]
                ]
                for key in ("by_employee", "by_bank", "by_loan_type")
            },
        }

    async def authorize_lead_view(self, actor: User) -> None:
        await self.authorize(actor, "follow-ups")


async def ensure_daily_operations_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    for name in COLLECTIONS.values():
        if name == "daily_progress_entries":
            await db[name].create_index("import_key", unique=True, sparse=True)
        else:
            await db[name].create_index("import_key", unique=True)
        await db[name].create_index([("is_deleted", 1), ("assigned_to", 1), ("date", -1)])
        await db[name].create_index([("is_deleted", 1), ("status", 1), ("due_date", 1)])
    await db.daily_follow_ups.create_index("lead_oid")
    await db.daily_follow_ups.create_index([("case_id", 1), ("updated_at", -1)])
    await db.daily_follow_ups.create_index([("is_deleted", 1), ("bank", 1), ("date", -1)])
    await db.operational_issues.create_index([("created_by", 1), ("is_deleted", 1), ("date", -1)])
    await db.daily_imports.create_index("expires_at", expireAfterSeconds=0)
