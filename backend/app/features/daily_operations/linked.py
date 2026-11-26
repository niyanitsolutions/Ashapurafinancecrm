"""Explicit opt-in working records. No lead, application or case status mutations."""

from typing import Any, Literal

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config.redis import get_redis
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.features.access_control.permission_engine import PermissionEngine
from app.features.auth.models import User
from app.features.customer.service import CustomerService
from app.features.daily_operations.service import DailyOperationsService, public
from app.features.leads.service import LeadService
from app.shared.base_document import BaseDocument
from app.utils.datetime import ist_date_to_utc_midnight, to_ist, utc_now


class OpenLinkedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity: Literal["lead", "application"]
    record_id: str = Field(pattern=r"^[a-fA-F0-9]{24}$")

    @field_validator("record_id")
    @classmethod
    def canonical_id(cls, value: str) -> str:
        return value.lower()


async def open_linked(
    service: DailyOperationsService, payload: OpenLinkedRequest, actor: User
) -> dict[str, Any]:
    await service.authorize(actor, "follow-ups", "create")
    await service.authorize_lead_view(actor)
    db = service.db
    application = None
    lead = None
    if payload.entity == "lead":
        lead = await LeadService(db).get_lead_scoped(payload.record_id, actor)
    else:
        if not await PermissionEngine(db).has_permission(
            actor, module="customer", resource="customers", action="view"
        ):
            raise ForbiddenError("Customer viewing permission is required to link an application.")
        application = await CustomerService(db, get_redis()).get_application_for_staff(
            payload.record_id, actor
        )
        if application.lead_id:
            lead = await LeadService(db).get_lead_scoped(application.lead_id, actor)
    if application and application.customer_id:
        identity = await db.customers.find_one(
            {
                "_id": ObjectId(application.customer_id),
                "user_id": application.user_id,
                "is_deleted": False,
            },
            {"_id": 1},
        )
        if not identity:
            raise ConflictError(
                "Application ownership needs Owner review. No workspace was created."
            )
    key = f"{payload.entity}:{payload.record_id}"
    if lead and not application:
        # Prefer the exact application relationship; never infer a case by phone/name.
        apps = (
            await db.applications.find(
                {"lead_id": lead.require_id(), "is_deleted": False}, {"_id": 1}
            )
            .limit(2)
            .to_list(2)
        )
        if len(apps) == 1:
            return await open_linked(
                service,
                OpenLinkedRequest(entity="application", record_id=str(apps[0]["_id"])),
                actor,
            )
        if len(apps) > 1:
            raise ConflictError(
                "This lead has multiple applications. Open the intended application to start its Daily Follow-up."
            )
    if application:
        historical = (
            await db.daily_follow_ups.find(
                {"application_id": application.require_id(), "working_key": {"$ne": key}},
                {"_id": 1},
            )
            .limit(1)
            .to_list(1)
        )
        if historical:
            raise ConflictError(
                "Existing historical follow-up references this Application. Ask the Owner to review it before opening a new workspace; no duplicate was created."
            )
    existing = await db.daily_follow_ups.find_one({"working_key": key})
    if existing:
        if existing.get("is_deleted"):
            raise ConflictError(
                "The linked working record is archived. Ask the Owner to review its history."
            )
        return public(await service.get("follow-ups", str(existing["_id"]), actor))
    if application and lead:
        # Bind an earlier lead-only workspace to its first exact application, keeping
        # its ID and history. Further genuine applications get their own workspaces.
        from pymongo import ReturnDocument
        from pymongo.errors import DuplicateKeyError

        try:
            async with await db.client.start_session() as session, session.start_transaction():
                earlier = await db.daily_follow_ups.find_one_and_update(
                    {
                        "working_key": f"lead:{lead.require_id()}",
                        "application_id": None,
                        "is_deleted": False,
                    },
                    {
                        "$set": {
                            "working_key": key,
                            "application_id": application.require_id(),
                            "application_oid": ObjectId(application.require_id()),
                            "updated_at": utc_now(),
                            "updated_by": actor.require_id(),
                        },
                        "$push": {
                            "history": {
                                "source": "application_linked",
                                "actor_id": actor.require_id(),
                                "at": utc_now(),
                                "before": None,
                                "after": {"application_id": application.require_id()},
                            }
                        },
                        "$inc": {"version": 1},
                    },
                    return_document=ReturnDocument.AFTER,
                    session=session,
                )
                if earlier:
                    from app.shared.audit_log import AuditLog

                    audit = AuditLog(
                        event_type="daily_workspace_application_linked",
                        user_id=actor.require_id(),
                        metadata={
                            "application_id": application.require_id(),
                            "record_id": str(earlier["_id"]),
                        },
                    )
                    await db.audit_logs.insert_one(
                        audit.model_dump(by_alias=True, exclude={"id"}), session=session
                    )
        except DuplicateKeyError:
            earlier = await db.daily_follow_ups.find_one({"working_key": key})
        if earlier:
            return public(await service.get("follow-ups", str(earlier["_id"]), actor))
    assigned_to = application.assigned_to if application else lead.assigned_to if lead else None
    if not assigned_to:
        raise ConflictError("Assign this record before opening its Daily Follow-up workspace.")
    customer_id = application.customer_id if application else lead.customer_id if lead else None
    customer = (
        await db.customers.find_one({"_id": ObjectId(customer_id), "is_deleted": False})
        if customer_id
        else None
    )
    if not customer and not lead:
        raise NotFoundError("Customer profile not found.")
    if application and customer and customer.get("user_id") != application.user_id:
        raise ForbiddenError("The application customer relationship needs Owner review.")
    source = customer or (lead.model_dump() if lead else {})
    if application:
        from app.features.customer.identity_name import current_application_name
        source = {**source, "full_name": await current_application_name(db, application)}
    now = utc_now()
    day = ist_date_to_utc_midnight(to_ist(now).date())
    employee = await db.employees.find_one({"_id": ObjectId(assigned_to)}, {"display_name": 1})
    product_context = application or lead
    assert product_context is not None
    product = await db[
        "loan_products" if product_context.product_category == "loan" else "insurance_products"
    ].find_one({"_id": ObjectId(product_context.product_id)}, {"name": 1})
    doc = {
        **BaseDocument(created_by=actor.require_id()).model_dump(exclude={"id"}),
        "working_key": key,
        "import_key": f"linked:{key}",
        "source": "crm_linked",
        "lead_id": lead.require_id() if lead else None,
        "application_id": application.require_id() if application else None,
        "customer_id": customer_id,
        "case_id": None,
        "assigned_to": assigned_to,
        "customer_name": source.get("full_name", ""),
        "customer_number": source.get("mobile", ""),
        "employee_name": (employee or {}).get("display_name", "Owner"),
        "date": day,
        "remarks_date": day,
        "status": "FOLLOW UP PENDING",
        "remarks": "",
        "bank": "",
        "banks": [],
        "loan_type": (product or {}).get("name", ""),
        "next_action": "Review linked CRM record",
        "due_date": day,
        "reeligible_state": "inactive",
        "reeligible_date": None,
        "rejection_reason": "",
        "history": [
            {
                "source": "crm_linked",
                "actor_id": actor.require_id(),
                "at": now,
                "before": None,
                "after": {"working_key": key},
            }
        ],
    }
    if lead:
        doc["lead_oid"] = ObjectId(lead.require_id())
    if application:
        doc["application_oid"] = ObjectId(application.require_id())
    if customer_id:
        doc["customer_oid"] = ObjectId(customer_id)
    # Existing unique import_key also protects this upsert on deployments before the
    # additive working_key index is installed. A duplicate click never adds history.
    from pymongo.errors import DuplicateKeyError, OperationFailure

    from app.shared.audit_log import AuditLog

    audit = AuditLog(
        event_type="daily_follow_up_linked",
        user_id=actor.require_id(),
        metadata={
            "working_key": key,
            "application_id": doc["application_id"],
            "customer_id": customer_id,
        },
    )
    try:
        async with await db.client.start_session() as session, session.start_transaction():
            result = await db.daily_follow_ups.update_one(
                {"working_key": key}, {"$setOnInsert": doc}, upsert=True, session=session
            )
            if result.upserted_id:
                await db.audit_logs.insert_one(
                    audit.model_dump(by_alias=True, exclude={"id"}), session=session
                )
    except DuplicateKeyError:
        pass  # A committed concurrent creator owns this canonical workspace.
    except OperationFailure as exc:
        if exc.code != 112 and not exc.has_error_label("TransientTransactionError"):
            raise
        if not await db.daily_follow_ups.find_one({"working_key": key}):
            raise ConflictError("Concurrent workspace change. Reload before continuing.") from None
    row = await db.daily_follow_ups.find_one({"working_key": key})
    if not row:
        raise ConflictError("The linked record changed. Reload before continuing.")
    return public(await service.get("follow-ups", str(row["_id"]), actor))
