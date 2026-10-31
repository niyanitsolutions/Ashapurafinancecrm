from __future__ import annotations

import builtins
import re
from datetime import date
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from redis.asyncio import Redis
from starlette.concurrency import run_in_threadpool

from app.constants.roles import EMPLOYEE, OWNER
from app.core.exceptions import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.features.auth.models import User
from app.features.customer.models import Customer
from app.features.customer.repository import CustomerRepository
from app.features.customer.service import CustomerService
from app.features.employee.repository import EmployeeRepository
from app.features.invoices.assets import snapshot_image
from app.features.invoices.calculations import calculate
from app.features.invoices.models import Invoice
from app.features.invoices.numbering import (
    allocate,
    deletion_eligibility,
    never_issued_draft,
    publish_deleted_tail,
)
from app.features.invoices.repository import InvoiceRepository
from app.features.invoices.schemas import InvoiceConfig, InvoiceInput, StatusInput
from app.features.system_settings.repository import CompanySettingsRepository
from app.shared.audit_log import write_audit_log
from app.utils.datetime import now_ist, utc_now


def public(doc: dict[str, Any]) -> dict[str, Any]:
    data = {
        ("id" if k == "_id" else k): str(v) if isinstance(v, ObjectId) else v
        for k, v in doc.items()
    }
    data["total_quantity"] = str(
        sum((Decimal(item["quantity"]) for item in doc["items"]), Decimal(0))
    )
    return data


def payment_qr(company: dict[str, Any], invoice: dict[str, Any]) -> str:
    config = InvoiceConfig.model_validate(
        {key: company[key] for key in InvoiceConfig.model_fields if key in company}
    )
    if config.qr_type == "upi":
        return "upi://pay?" + urlencode(
            {
                "pa": config.upi_id,
                "pn": config.account_holder or company["name"],
                "am": invoice["grand_total"],
                "cu": "INR",
                "tn": invoice["invoice_number"],
            }
        )
    return "Invoice:" + invoice["invoice_number"] if config.qr_type == "identifier" else ""


class InvoiceService:
    def __init__(self, db: AsyncIOMotorDatabase[Any], redis: Redis) -> None:
        self.db, self.redis = db, redis
        self.company = CompanySettingsRepository(db)
        self.invoices = InvoiceRepository(db)

    async def audit(
        self, actor: User, action: str, invoice_id: str | None = None, **metadata: Any
    ) -> None:
        await write_audit_log(
            self.db,
            event_type="invoice_" + action,
            user_id=actor.require_id(),
            metadata={"invoice_id": invoice_id, **metadata},
        )

    async def scope(self, actor: User) -> dict[str, Any]:
        if actor.role == OWNER:
            return {"is_deleted": False}
        if actor.role != EMPLOYEE:
            raise ForbiddenError("Staff access required.")
        customer_ids = await self.assigned_customer_ids(actor)
        return {
            "is_deleted": False,
            "$or": [
                {"customer_id": {"$in": customer_ids}},
                {"customer_id": None, "created_by": actor.require_id()},
            ],
        }

    async def assigned_customer_ids(self, actor: User) -> list[str]:
        employee = await EmployeeRepository(self.db).find_by_user_id(actor.require_id())
        if not employee:
            raise ForbiddenError("Employee profile required.")
        customer_ids = await self.db.applications.distinct(
            "customer_id", {"assigned_to": employee.require_id(), "is_deleted": False}
        )
        # Unsubmitted applications may have no customer yet. Null must never match
        # every manually billed company invoice through the assignment branch.
        return [value for value in customer_ids if value]

    async def customer_options(self, actor: User, search: str) -> list[Customer]:
        query: dict[str, Any] = {}
        if actor.role != OWNER:
            ids = await self.assigned_customer_ids(actor)
            query["_id"] = {"$in": [ObjectId(value) for value in ids if ObjectId.is_valid(value)]}
        if search:
            query["full_name"] = {"$regex": re.escape(search), "$options": "i"}
        # Apply assignment and search before the limit, including large customer lists.
        return await CustomerRepository(self.db).find_many(
            query, limit=100, sort=[("full_name", 1)]
        )

    async def get(self, invoice_id: str, actor: User) -> dict[str, Any]:
        if not ObjectId.is_valid(invoice_id):
            raise NotFoundError("Invoice not found.")
        doc = await self.db.invoices.find_one(
            {"_id": ObjectId(invoice_id), **await self.scope(actor)}
        )
        if doc is None:
            raise NotFoundError("Invoice not found.")
        result = public(doc)
        if doc.get("replacement_for"):
            original = await self.db.invoices.find_one(
                {"_id": ObjectId(doc["replacement_for"]), **await self.scope(actor)}
            )
            result["source_status"] = original["status"] if original else "unavailable"
        return result

    async def list(
        self,
        actor: User,
        *,
        search: str = "",
        status: str = "",
        from_date: date | None = None,
        to_date: date | None = None,
        page: int = 1,
        page_size: int = 25,
        sort: str = "created_at",
        direction: int = -1,
        archived: bool = False,
    ) -> dict[str, Any]:
        query = await self.scope(actor)
        query["is_archived"] = True if archived else {"$ne": True}
        if search:
            query = {
                "$and": [
                    query,
                    {
                        "$or": [
                            {"invoice_number": {"$regex": re.escape(search), "$options": "i"}},
                            {"customer.name": {"$regex": re.escape(search), "$options": "i"}},
                        ]
                    },
                ]
            }
        if status:
            query["status"] = status
        if from_date or to_date:
            query["invoice_date"] = {}
            if from_date:
                query["invoice_date"]["$gte"] = from_date.isoformat()
            if to_date:
                query["invoice_date"]["$lte"] = to_date.isoformat()
        count = await self.db.invoices.count_documents(query)
        docs = (
            await self.db.invoices.find(query)
            .sort([(sort, direction), ("_id", direction)])
            .skip((page - 1) * page_size)
            .limit(page_size)
            .to_list(page_size)
        )
        return {
            "items": [public(d) for d in docs],
            "total": count,
            "page": page,
            "page_size": page_size,
            "total_pages": (count + page_size - 1) // page_size,
        }

    async def snapshot(self) -> dict[str, Any]:
        company = await self.company.get_or_create()
        config = InvoiceConfig.model_validate(company.invoice_config)
        return dict(
            name=company.company_name,
            address=company.address.model_dump() if company.address else {},
            phone=company.contact_phone or "",
            email=company.contact_email or "",
            logo_s3_key=company.logo_s3_key,
            **config.model_dump(mode="json"),
        )

    async def draft_company(self, doc: dict[str, Any]) -> dict[str, Any]:
        latest = await self.snapshot()
        company = dict(doc["company"])
        for field in (
            "signature_s3_key",
            "show_signature",
            "signatory",
            "designation",
            "qr_type",
            "upi_id",
            "account_holder",
        ):
            company[field] = latest[field]
        return company

    async def customer_validate(self, payload: InvoiceInput, actor: User) -> None:
        if payload.customer_id:
            if not ObjectId.is_valid(payload.customer_id):
                raise ValidationError("Invalid customer.")
            await CustomerService(self.db, self.redis).get_customer_for_staff(
                payload.customer_id, actor
            )

    async def preview(self, payload: InvoiceInput, actor: User) -> dict[str, Any]:
        await self.customer_validate(payload, actor)
        return (
            payload.model_dump(mode="json", exclude={"request_key"})
            | calculate(payload.items, payload.tax_type)
            | {
                "company": await self.snapshot(),
                "invoice_number": "PREVIEW",
                "status": "draft",
                "qr_value": "",
            }
        )

    async def create(
        self,
        payload: InvoiceInput,
        actor: User,
        *,
        duplicated_from: str | None = None,
        replacement_for: str | None = None,
        source_invoice_number: str | None = None,
        correction_reason: str | None = None,
        request_key: str | None = None,
    ) -> dict[str, Any]:
        request_key = request_key or payload.request_key
        if request_key:
            existing = await self.db.invoices.find_one({"request_key": request_key})
            if existing:
                if (
                    existing.get("created_by") != actor.require_id()
                    or existing.get("duplicated_from") != duplicated_from
                    or existing.get("replacement_for") != replacement_for
                ):
                    raise ConflictError("Request key already used for another operation.")
                return await self.get(str(existing["_id"]), actor)
        doc = await self.preview(payload, actor)
        doc["invoice_number"], reused_from = await allocate(self.db, doc["company"])
        now = utc_now()
        doc.update(
            created_by=actor.require_id(),
            updated_by=actor.require_id(),
            created_at=now,
            updated_at=now,
            version=1,
            duplicated_from=duplicated_from,
            replacement_for=replacement_for,
            source_invoice_number=source_invoice_number,
            correction_reason=correction_reason,
            request_key=request_key,
            number_reused_from=reused_from,
            history=[
                self.event(
                    actor,
                    "replacement_draft_created"
                    if replacement_for
                    else "duplicated"
                    if duplicated_from
                    else "created",
                    None,
                    "draft",
                    related_invoice_number=source_invoice_number,
                    reason=correction_reason,
                )
            ],
        )
        if reused_from:
            doc["history"].append(
                self.event(actor, "number_reused", None, "draft", related_invoice_id=reused_from)
            )
        profile = await self.db["owner_profiles" if actor.role == OWNER else "employees"].find_one(
            {"user_id": actor.require_id()}
        )
        doc["created_by_name"] = (
            (profile.get("full_name") or profile.get("display_name") or actor.mobile)
            if profile
            else actor.mobile
        )
        try:
            invoice_id = await self.invoices.insert(Invoice.model_validate(doc))
        except DuplicateKeyError as exc:
            if request_key:
                existing = await self.db.invoices.find_one({"request_key": request_key})
                if (
                    existing
                    and existing.get("created_by") == actor.require_id()
                    and existing.get("duplicated_from") == duplicated_from
                    and existing.get("replacement_for") == replacement_for
                ):
                    return await self.get(str(existing["_id"]), actor)
            if replacement_for and await self.db.invoices.find_one(
                {"replacement_for": replacement_for}
            ):
                existing = await self.correction_draft(replacement_for, actor)
                if existing:
                    return existing | {"correction_resumed": True}
                raise ConflictError(
                    "The correction was finalized or deleted; review its history."
                ) from exc
            raise ConflictError("Invoice number already exists. Please retry.") from exc
        if reused_from:
            await self.audit(
                actor,
                "number_reused",
                invoice_id,
                deleted_draft_id=reused_from,
                invoice_number=doc["invoice_number"],
            )
            await self.db.invoices.update_one(
                {"_id": ObjectId(reused_from), "is_deleted": True},
                {
                    "$push": {
                        "history": self.event(
                            actor, "number_reused", "draft", "draft", related_invoice_id=invoice_id
                        )
                    }
                },
            )
        await self.audit(
            actor,
            "replacement_draft_created"
            if replacement_for
            else "duplicated"
            if duplicated_from
            else "created",
            invoice_id,
            source=duplicated_from,
        )
        return await self.get(invoice_id, actor)

    async def update(self, invoice_id: str, payload: InvoiceInput, actor: User) -> dict[str, Any]:
        current = await self.get(invoice_id, actor)
        if current["status"] != "draft" or current.get("is_archived"):
            raise ConflictError("Only active draft invoices can be edited.")
        doc = await self.preview(payload, actor)
        for field in ("invoice_number", "status", "version"):
            doc.pop(field, None)
        return await self.replace(
            invoice_id,
            current,
            payload.version,
            doc,
            actor,
            "correction_draft_updated" if current.get("replacement_for") else "edited",
        )

    async def replace(
        self,
        invoice_id: str,
        current: dict[str, Any],
        version: int,
        updates: dict[str, Any],
        actor: User,
        action: str,
    ) -> dict[str, Any]:
        if version != current["version"]:
            raise ConflictError("Invoice changed. Reload before saving.")
        updates.update(updated_by=actor.require_id(), updated_at=utc_now())
        doc = await self.db.invoices.find_one_and_update(
            {
                "_id": ObjectId(invoice_id),
                "version": version,
                "status": current["status"],
                "is_archived": True if current.get("is_archived") else {"$ne": True},
                "is_deleted": False,
            },
            {
                "$set": updates,
                "$inc": {"version": 1},
                "$push": {
                    "history": self.event(
                        actor,
                        action,
                        current["status"],
                        updates.get("status", current["status"]),
                        reason=updates.get("cancellation_reason")
                        or updates.get("archive_reason")
                        or updates.get("deletion_reason"),
                    )
                },
            },
            return_document=ReturnDocument.AFTER,
        )
        if not doc:
            raise ConflictError("Invoice changed. Reload before saving.")
        await self.audit(
            actor,
            action,
            invoice_id,
            previous_status=current["status"],
            new_status=updates.get("status", current["status"]),
            reason=updates.get("cancellation_reason")
            or updates.get("archive_reason")
            or updates.get("deletion_reason"),
        )
        return public(doc)

    async def status(self, invoice_id: str, payload: StatusInput, actor: User) -> dict[str, Any]:
        current = await self.get(invoice_id, actor)
        if current.get("is_archived"):
            raise ConflictError("Archived invoices cannot change financial status.")
        allowed = {
            "draft": {"issued", "cancelled"},
            "issued": {"paid", "partially_paid", "cancelled"},
            "partially_paid": {"paid", "cancelled"},
            "paid": set(),
            "cancelled": set(),
        }
        if payload.status not in allowed[current["status"]]:
            raise ConflictError("This status transition is not allowed.")
        updates: dict[str, Any] = {"status": payload.status}
        if payload.status == "cancelled" and current["status"] == "partially_paid":
            raise ConflictError(
                "Settled invoices require an accounting adjustment; credit notes are not supported."
            )
        if payload.status == "cancelled":
            if not payload.reason.strip():
                raise ValidationError("Cancellation reason is required.")
            updates.update(
                cancelled_by=actor.require_id(),
                cancelled_at=utc_now(),
                cancellation_reason=payload.reason.strip(),
            )
        if payload.status == "issued":
            if current.get("replacement_for"):
                original = await self.get(current["replacement_for"], actor)
                if original["status"] != "cancelled":
                    raise ConflictError(
                        "Cancel the original through an accounting-approved process before issuing its replacement. Credit notes are not supported."
                    )
            company = await self.draft_company(current)
            if not all(
                [
                    company["name"],
                    company["address"],
                    company["gstin"],
                    company["bank_name"],
                    company["account_number"],
                    company["ifsc"],
                ]
            ):
                raise ValidationError(
                    "Complete company address, GSTIN and bank details before issuing."
                )
            updates["qr_value"] = payment_qr(company, current)
            updates["issued_at"] = utc_now()
            # Even an old logo uploaded through the shared Settings flow might later
            # be replaced at its source key. Issued invoices own immutable copies.
            frozen_company = dict(company)
            try:
                for field in ("logo_s3_key", "signature_s3_key"):
                    if company.get(field):
                        frozen_company[field] = await run_in_threadpool(
                            snapshot_image, company[field], invoice_id
                        )
            except Exception as exc:
                raise AppError(
                    "Company images could not be saved. The invoice remains a draft."
                ) from exc
            updates["company"] = frozen_company
        return await self.replace(
            invoice_id,
            current,
            payload.version,
            updates,
            actor,
            "correction_finalized"
            if current.get("replacement_for") and payload.status == "issued"
            else payload.status,
        )

    async def duplicate(
        self,
        invoice_id: str,
        actor: User,
        *,
        request_key: str | None = None,
        reason: str = "",
        replacement: bool = False,
    ) -> dict[str, Any]:
        old = await self.get(invoice_id, actor)
        if old["status"] in {"paid", "partially_paid"}:
            raise ConflictError(
                "Settled invoices require an accounting adjustment; credit notes are not supported."
            )
        if replacement:
            existing = await self.correction_draft(invoice_id, actor)
            if existing:
                return existing | {"correction_resumed": True}
        if replacement and (old["status"] not in {"issued", "cancelled"} or not reason.strip()):
            raise ValidationError(
                "A replacement requires an issued or cancelled invoice and a correction reason."
            )
        fields = {
            key: old[key]
            for key in InvoiceInput.model_fields
            if key in old and key != "request_key"
        }
        fields.update(
            invoice_date=old["invoice_date"] if replacement else now_ist().date().isoformat(),
            due_date=old["due_date"] if replacement else now_ist().date().isoformat(),
            version=1,
        )
        fields["items"] = [
            {k: row[k] for k in ("description", "hsn", "quantity", "unit", "rate", "gst_rate")}
            for row in old["items"]
        ]
        return await self.create(
            InvoiceInput.model_validate(fields),
            actor,
            duplicated_from=None if replacement else invoice_id,
            replacement_for=invoice_id if replacement else None,
            source_invoice_number=old["invoice_number"],
            correction_reason=reason.strip() if replacement else None,
            request_key=request_key,
        )

    @staticmethod
    def event(
        actor: User, action: str, previous_status: str | None, new_status: str, **extra: Any
    ) -> dict[str, Any]:
        return dict(
            action=action,
            timestamp=utc_now(),
            user_id=actor.require_id(),
            previous_status=previous_status,
            new_status=new_status,
            **extra,
        )

    async def delete_draft(
        self, invoice_id: str, version: int, actor: User, reason: str = ""
    ) -> dict[str, Any]:
        current = await self.get(invoice_id, actor)
        if not never_issued_draft(current):
            raise ConflictError("Only never-issued active draft invoices can be deleted.")
        # No payment/posting collections reference invoices in the current application.
        # Keep referenced source drafts available, including references from deleted copies.
        if await self.db.invoices.find_one(
            {"$or": [{"duplicated_from": invoice_id}, {"replacement_for": invoice_id}]}
        ):
            raise ConflictError("This invoice has dependent invoices and cannot be deleted.")
        await self.replace(
            invoice_id,
            current,
            version,
            {
                "is_deleted": True,
                "deleted_by": actor.require_id(),
                "deleted_at": utc_now(),
                "deletion_reason": reason.strip(),
            },
            actor,
            "deleted",
        )
        reusable = await publish_deleted_tail(self.db, current)
        return {
            "deleted": True,
            "number_reusable": reusable,
            "message": "Draft deleted. Its number is available only while it remains the latest allocation."
            if reusable
            else "Draft deleted. Its number is retained and will not be reused.",
        }

    async def correction_draft(self, invoice_id: str, actor: User) -> dict[str, Any] | None:
        await self.get(invoice_id, actor)
        doc = await self.db.invoices.find_one({"replacement_for": invoice_id, "is_deleted": False})
        if not doc:
            return None
        # Do not reveal a correction assigned outside this user's record scope.
        result = await self.get(str(doc["_id"]), actor)
        if result["status"] != "draft" or result.get("is_archived"):
            raise ConflictError(
                "This correction has already been finalized or archived. Review its history."
            )
        return result

    async def delete_options(self, invoice_id: str, actor: User) -> dict[str, Any]:
        return await deletion_eligibility(self.db, await self.get(invoice_id, actor))

    async def archive(
        self, invoice_id: str, version: int, reason: str, actor: User
    ) -> dict[str, Any]:
        current = await self.get(invoice_id, actor)
        if current["status"] not in {"issued", "cancelled", "paid", "partially_paid"}:
            raise ConflictError("Drafts must use the draft deletion workflow.")
        if not reason.strip():
            raise ValidationError("Archive reason is required.")
        if current.get("is_archived"):
            raise ConflictError("Invoice is already archived.")
        return await self.replace(
            invoice_id,
            current,
            version,
            {
                "is_archived": True,
                "archived_at": utc_now(),
                "archived_by": actor.require_id(),
                "archive_reason": reason.strip(),
            },
            actor,
            "archived",
        )

    async def history(self, invoice_id: str, actor: User) -> builtins.list[dict[str, Any]]:
        if actor.role == OWNER and ObjectId.is_valid(invoice_id):
            doc = await self.db.invoices.find_one({"_id": ObjectId(invoice_id)})
            if doc is None:
                raise NotFoundError("Invoice not found.")
            current = public(doc)
        else:
            current = await self.get(invoice_id, actor)
        events = list(current.get("history", []))
        # Existing audit events are real history; never synthesize missing legacy events.
        logs = (
            await self.db.audit_logs.find({"metadata.invoice_id": invoice_id})
            .sort("created_at", 1)
            .to_list(None)
        )
        for log in logs:
            action = log["event_type"].removeprefix("invoice_")
            embedded = current.get("history", [])
            first_recorded = min((e["timestamp"] for e in embedded), default=None)
            if action not in {e["action"] for e in embedded} or (
                first_recorded and log["created_at"] < first_recorded
            ):
                events.append(
                    {
                        "action": action,
                        "timestamp": log["created_at"],
                        "user_id": log.get("user_id"),
                    }
                )
        related_scope = await self.scope(actor)
        if actor.role == OWNER:
            related_scope.pop("is_deleted", None)
        related = await self.db.invoices.find(
            {
                "$and": [
                    {"$or": [{"replacement_for": invoice_id}, {"duplicated_from": invoice_id}]},
                    related_scope,
                ]
            }
        ).to_list(None)
        for doc in related:
            events.append(
                {
                    "action": "replacement_draft_created"
                    if doc.get("replacement_for")
                    else "duplicate_created",
                    "timestamp": doc["created_at"],
                    "user_id": doc["created_by"],
                    "related_invoice_number": doc["invoice_number"],
                    "related_invoice_id": str(doc["_id"]),
                    "reason": doc.get("correction_reason"),
                }
            )
            if doc.get("replacement_for"):
                for event in doc.get("history", []):
                    if event["action"] in {"correction_draft_updated", "deleted", "archived"}:
                        events.append(
                            event
                            | {
                                "related_invoice_number": doc["invoice_number"],
                                "related_invoice_id": str(doc["_id"]),
                            }
                        )
            if doc.get("issued_at") and doc.get("replacement_for"):
                events.append(
                    {
                        "action": "replacement_invoice_issued",
                        "timestamp": doc["issued_at"],
                        "related_invoice_number": doc["invoice_number"],
                        "related_invoice_id": str(doc["_id"]),
                    }
                )
        return sorted(events, key=lambda event: event["timestamp"].isoformat())
