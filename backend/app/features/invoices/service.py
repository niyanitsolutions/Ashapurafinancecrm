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
from app.features.invoices.repository import InvoiceRepository
from app.features.invoices.schemas import InvoiceConfig, InvoiceInput, StatusInput
from app.features.system_settings.repository import CompanySettingsRepository
from app.shared.audit_log import write_audit_log
from app.utils.datetime import now_ist, utc_now
from app.utils.id_generator import generate_id


def public(doc: dict[str, Any]) -> dict[str, Any]:
    data = {
        ("id" if k == "_id" else k): str(v) if isinstance(v, ObjectId) else v
        for k, v in doc.items()
    }
    data["total_quantity"] = str(
        sum((Decimal(item["quantity"]) for item in doc["items"]), Decimal(0))
    )
    return data


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
        return public(doc)

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
    ) -> dict[str, Any]:
        query = await self.scope(actor)
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
            payload.model_dump(mode="json")
            | calculate(payload.items, payload.tax_type)
            | {
                "company": await self.snapshot(),
                "invoice_number": "PREVIEW",
                "status": "draft",
                "qr_value": "",
            }
        )

    async def create(
        self, payload: InvoiceInput, actor: User, *, duplicated_from: str | None = None
    ) -> dict[str, Any]:
        doc = await self.preview(payload, actor)
        # Existing atomic counter utility; $max raises the initial floor without resets.
        company = doc["company"]
        await self.db.counters.update_one(
            {"_id": "INV"}, {"$max": {"seq": company["starting_number"] - 1}}, upsert=True
        )
        code = await generate_id(self.db, "INV")
        doc["invoice_number"] = company["prefix"] + code.rsplit("-", 1)[-1]
        now = utc_now()
        doc.update(
            created_by=actor.require_id(),
            updated_by=actor.require_id(),
            created_at=now,
            updated_at=now,
            version=1,
            duplicated_from=duplicated_from,
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
            raise ConflictError("Invoice number already exists. Please retry.") from exc
        await self.audit(
            actor,
            "duplicated" if duplicated_from else "created",
            invoice_id,
            source=duplicated_from,
        )
        return await self.get(invoice_id, actor)

    async def update(self, invoice_id: str, payload: InvoiceInput, actor: User) -> dict[str, Any]:
        current = await self.get(invoice_id, actor)
        if current["status"] != "draft":
            raise ConflictError("Only draft invoices can be edited.")
        doc = await self.preview(payload, actor)
        for field in ("invoice_number", "status", "version"):
            doc.pop(field, None)
        return await self.replace(invoice_id, current, payload.version, doc, actor, "edited")

    async def replace(
        self,
        invoice_id: str,
        current: dict[str, Any],
        version: int,
        updates: dict[str, Any],
        actor: User,
        action: str,
    ) -> dict[str, Any]:
        updates.update(updated_by=actor.require_id(), updated_at=utc_now())
        doc = await self.db.invoices.find_one_and_update(
            {
                "_id": ObjectId(invoice_id),
                "version": version,
                "status": current["status"],
                "is_deleted": False,
            },
            {"$set": updates, "$inc": {"version": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if not doc:
            raise ConflictError("Invoice changed. Reload before saving.")
        await self.audit(actor, action, invoice_id)
        return public(doc)

    async def status(self, invoice_id: str, payload: StatusInput, actor: User) -> dict[str, Any]:
        current = await self.get(invoice_id, actor)
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
        if payload.status == "cancelled":
            if not payload.reason.strip():
                raise ValidationError("Cancellation reason is required.")
            updates.update(
                cancelled_by=actor.require_id(),
                cancelled_at=utc_now(),
                cancellation_reason=payload.reason.strip(),
            )
        if payload.status == "issued":
            company = current["company"]  # stored snapshot; settings changes never rewrite history
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
            qr = company["qr_type"]
            updates["qr_value"] = (
                "upi://pay?"
                + urlencode(
                    {
                        "pa": company["upi_id"],
                        "pn": company["account_holder"] or company["name"],
                        "am": current["grand_total"],
                        "cu": "INR",
                        "tn": current["invoice_number"],
                    }
                )
                if qr == "upi"
                else "Invoice:" + current["invoice_number"]
                if qr == "identifier"
                else ""
            )
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
            invoice_id, current, payload.version, updates, actor, payload.status
        )

    async def duplicate(self, invoice_id: str, actor: User) -> dict[str, Any]:
        old = await self.get(invoice_id, actor)
        fields = {key: old[key] for key in InvoiceInput.model_fields if key in old}
        fields.update(
            invoice_date=now_ist().date().isoformat(),
            due_date=now_ist().date().isoformat(),
            version=1,
        )
        fields["items"] = [
            {k: row[k] for k in ("description", "hsn", "quantity", "unit", "rate", "gst_rate")}
            for row in old["items"]
        ]
        return await self.create(
            InvoiceInput.model_validate(fields), actor, duplicated_from=invoice_id
        )
