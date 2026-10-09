from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.features.access_control.models import Permission
from app.features.dashboard.models import NavItem
from app.features.invoices.models import Invoice
from app.shared.base_repository import BaseRepository


class InvoiceRepository(BaseRepository[Invoice]):
    collection_name = "invoices"
    model = Invoice


async def ensure_invoice_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db.invoices.create_index("invoice_number", unique=True)
    await db.invoices.create_index([("customer_id", 1), ("invoice_date", -1)])
    await db.invoices.create_index([("created_by", 1), ("created_at", -1)])
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
