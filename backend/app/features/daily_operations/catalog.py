from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.features.access_control.models import Permission
from app.features.daily_operations.service import ensure_daily_operations_indexes
from app.features.dashboard.models import NavItem

AREAS = {
    "follow-ups": "Daily Follow-up Data",
    "progress": "Loan Progress Tracking",
    "sessions": "Employee Login & Logout",
    "issues": "Inquiry or Issue",
}


async def install_catalog(db: AsyncIOMotorDatabase[Any]) -> None:
    """Additive catalog only: never grant employees new permissions implicitly."""
    await ensure_daily_operations_indexes(db)
    for order, (resource, label) in enumerate(AREAS.items(), 70):
        actions = ["view", "create", "edit", "import", "export"]
        if resource == "progress":
            actions = ["view", "import", "export"]
        elif resource == "sessions":
            actions = ["view", "edit", "import", "export"]
        if resource == "issues":
            actions += ["assign", "approve"]
        permission = Permission(
            module="daily_operations", resource=resource, actions=actions, label=label
        )
        await db.permissions.update_one(
            {"module": "daily_operations", "resource": resource},
            {"$setOnInsert": permission.model_dump(exclude={"id"})},
            upsert=True,
        )
        item = NavItem(
            key=f"daily_{resource}",
            label=label,
            route=f"/daily-operations/{resource}",
            order=order,
            required_module="daily_operations",
            required_resource=resource,
            required_action="view",
        )
        await db.nav_items.update_one(
            {"key": item.key}, {"$setOnInsert": item.model_dump(exclude={"id"})}, upsert=True
        )
