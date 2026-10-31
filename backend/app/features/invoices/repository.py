from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.features.access_control.models import Permission
from app.features.dashboard.models import NavItem
from app.features.invoices.models import Invoice
from app.features.invoices.numbering import ACTIVE_NUMBER_FILTER, ACTIVE_NUMBER_INDEX
from app.shared.base_repository import BaseRepository

CORRECTION_INDEX = "replacement_for_reserved_unique"
CORRECTION_FILTER = {"replacement_for": {"$type": "string"}, "is_deleted": False}


class InvoiceRepository(BaseRepository[Invoice]):
    collection_name = "invoices"
    model = Invoice


async def ensure_invoice_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    # Add the stronger active-record guard before an explicitly reviewed migration
    # removes the legacy all-record index. Startup never drops an index.
    conflicts = await db.invoices.aggregate(
        [
            {"$match": ACTIVE_NUMBER_FILTER},
            {"$group": {"_id": "$invoice_number", "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
            {"$limit": 1},
        ]
    ).to_list(1)
    if conflicts:
        raise RuntimeError("Conflicting reserved invoice numbers; review invoice index migration.")
    await db.invoices.create_index(
        "invoice_number",
        unique=True,
        name=ACTIVE_NUMBER_INDEX,
        partialFilterExpression=ACTIVE_NUMBER_FILTER,
    )
    await db.invoices.create_index([("customer_id", 1), ("invoice_date", -1)])
    await db.invoices.create_index([("created_by", 1), ("created_at", -1)])
    await db.invoices.create_index(
        "request_key",
        unique=True,
        partialFilterExpression={"request_key": {"$type": "string"}},
    )
    correction_conflicts = await db.invoices.aggregate(
        [
            {"$match": CORRECTION_FILTER},
            {"$group": {"_id": "$replacement_for", "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
            {"$limit": 1},
        ]
    ).to_list(1)
    if correction_conflicts:
        raise RuntimeError("Conflicting correction workflows; review invoice index migration.")
    await db.invoices.create_index(
        "replacement_for",
        unique=True,
        name=CORRECTION_INDEX,
        partialFilterExpression=CORRECTION_FILTER,
    )
    # Catalog integration only: no grants, customer records or business seed data.
    permission = Permission(
        module="invoices", resource="invoices", label="Invoices", actions=["view", "create", "edit"]
    )
    await db.permissions.update_one(
        {"module": "invoices", "resource": "invoices"},
        {"$setOnInsert": permission.model_dump(by_alias=True, exclude={"id"})},
        upsert=True,
    )
    nav = NavItem(
        key="invoices",
        label="Invoices",
        route="/invoices",
        icon="reports",
        order=65,
        required_module="invoices",
        required_resource="invoices",
        required_action="view",
    )
    await db.nav_items.update_one(
        {"key": "invoices"},
        {"$setOnInsert": nav.model_dump(by_alias=True, exclude={"id"})},
        upsert=True,
    )
