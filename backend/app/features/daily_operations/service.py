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
from app.features.daily_operations.schemas import FollowUpInput, IssueInput
from app.features.leads.service import LeadService
from app.features.loan_management.service import LoanCaseService
from app.shared.base_document import BaseDocument
from app.utils.datetime import ist_date_to_utc_midnight, to_ist, utc_now

COLLECTIONS = {"follow-ups": "daily_follow_ups", "issues": "operational_issues"}
OPEN_STATUSES = ["FOLLOW UP PENDING", "NEXT FOLLOW UP"]


def calendar_values(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: to_ist(value).date().isoformat()
        if key in {"date", "remarks_date", "due_date"} and isinstance(value, datetime)
        else value
        for key, value in values.items()
    }


def stored_values(payload: FollowUpInput | IssueInput) -> dict[str, Any]:
    return {
        key: ist_date_to_utc_midnight(value)
        if isinstance(value, date) and not isinstance(value, datetime)
        else value
        for key, value in payload.model_dump().items()
    }


def public(doc: dict[str, Any]) -> dict[str, Any]:
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
        **{k: v for k, v in doc.items() if k not in {"_id", "import_key", "lead_oid"}},
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
        if not await PermissionEngine(self.db).has_permission(
            actor, module="leads", resource="leads", action="view"
        ):
            raise ForbiddenError("Lead visibility permission is required.")
        lead = await LeadService(self.db).get_lead_scoped(payload.lead_id, actor)
        if lead.product_category != "loan":
            raise ValidationError("Daily loan follow-ups require a loan lead.")
        if not lead.assigned_to:
            raise ValidationError("Assign the lead in Leads before scheduling a follow-up.")
        case = None
        if payload.case_id:
            if not await PermissionEngine(self.db).has_permission(
                actor, module="loan_management", resource="applications", action="view"
            ):
                raise ForbiddenError("Loan visibility permission is required.")
            case = await LoanCaseService(self.db).get_case(payload.case_id, actor)
            application = await self.db.applications.find_one(
                {"_id": ObjectId(case.application_id), "is_deleted": False}
            )
            if not application or application.get("lead_id") != payload.lead_id:
                raise ValidationError("Loan case and lead do not belong to the same application.")
        if payload.status == "DISBURSE":
            details = case.loan_details if case else None
            if (
                not case
                or case.current_status != "disbursed"
                or not details
                or details.disbursed_amount is None
                or details.disbursed_amount < 0
                or details.disbursed_at is None
                or not details.disbursed_reference
            ):
                raise ValidationError("Record a verified disbursement in Loan Management first.")
        product = await self.db.loan_products.find_one({"_id": ObjectId(lead.product_id)})
        return {
            **stored_values(payload),
            "assigned_to": lead.assigned_to,
            "customer_name": lead.full_name,
            "customer_number": lead.mobile,
            "loan_type": product.get("name", "") if product else "",
            "lead_code": lead.lead_code,
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
        if payload.assigned_to != (old or {}).get("assigned_to"):
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
            "resolved_at": (old or {}).get("resolved_at") or utc_now()
            if payload.status == "RESOLVED"
            else None,
        }

    async def get(self, kind: str, record_id: str, actor: User) -> dict[str, Any]:
        await self.authorize(actor, kind)
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
            await self.validate_follow_up(
                FollowUpInput.model_validate(
                    {
                        k: value
                        for k, value in calendar_values(doc).items()
                        if k in FollowUpInput.model_fields
                    }
                ),
                actor,
            )
        return doc

    async def save(
        self,
        kind: str,
        payload: FollowUpInput | IssueInput,
        actor: User,
        record_id: str | None = None,
        version: int | None = None,
        import_key: str | None = None,
    ) -> dict[str, Any]:
        await self.authorize(actor, kind, "edit" if record_id else "create")
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
        event = {
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
        if kind == "follow-ups":
            doc["lead_oid"] = ObjectId(data["lead_id"])
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
        query = await self.scope(actor, kind)
        if date_from and date_to and date_from > date_to:
            raise ValidationError("Start date must be before end date.")
        if employee:
            query["$and"] = [{"assigned_to": employee}]
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
                        for key in ("customer_name", "lead_code", "bank", "inquiry", "next_action")
                    ]
                }
            )
        field = sort.lstrip("-")
        if field not in {"date", "status", "updated_at", "due_date", "bank", "priority"}:
            raise ValidationError("Unsupported sort column.")
        pipeline: list[dict[str, Any]] = [{"$project": {"history": 0}}]
        if kind == "follow-ups":
            await self.authorize_lead_view(actor)
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
                            "from": "leads",
                            "localField": "lead_oid",
                            "foreignField": "_id",
                            "as": "lead",
                        }
                    },
                    {"$unwind": "$lead"},
                    {"$match": {"lead.is_deleted": False}},
                    {
                        "$set": {
                            "assigned_to": "$lead.assigned_to",
                            "customer_name": "$lead.full_name",
                            "customer_number": "$lead.mobile",
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
                            {"$project": {"history": 0, "lead": 0, "lead_oid": 0}},
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
            item["employee_name"] = employees.get(
                item.get("employee_id") if kind == "issues" else item.get("assigned_to"),
                "Owner"
                if (item.get("employee_id") if kind == "issues" else item.get("assigned_to"))
                == actor.require_id()
                and actor.role == OWNER
                else "",
            )
        return {
            "items": [public(item) for item in result["items"]],
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
        if not await PermissionEngine(self.db).has_permission(
            actor, module="leads", resource="leads", action="view"
        ):
            raise ForbiddenError("Lead visibility permission is required.")


async def ensure_daily_operations_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    for name in COLLECTIONS.values():
        await db[name].create_index("import_key", unique=True)
        await db[name].create_index([("is_deleted", 1), ("assigned_to", 1), ("date", -1)])
        await db[name].create_index([("is_deleted", 1), ("status", 1), ("due_date", 1)])
    await db.daily_follow_ups.create_index("lead_oid")
    await db.daily_follow_ups.create_index([("case_id", 1), ("updated_at", -1)])
    await db.daily_follow_ups.create_index([("is_deleted", 1), ("bank", 1), ("date", -1)])
    await db.operational_issues.create_index([("created_by", 1), ("is_deleted", 1), ("date", -1)])
    await db.daily_imports.create_index("expires_at", expireAfterSeconds=0)
