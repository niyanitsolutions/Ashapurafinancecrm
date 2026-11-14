"""Index definitions for collections this module owns. Called once at app startup (see
main.py lifespan) — create_index is idempotent, safe to call every boot.
"""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_employee_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["employees"].create_index("user_id", unique=True)
    await db["employees"].create_index("employee_code", unique=True)
    await db["employees"].create_index("email", unique=True)
    await db["employees"].create_index("department_id")
    await db["employees"].create_index("designation_id")
    await db["employees"].create_index("branch_id")
    await db["employees"].create_index("status")

    await db["departments"].create_index("name", unique=True)
    await db["designations"].create_index("name", unique=True)
    await db["branches"].create_index("code", unique=True)

    await db["employee_documents"].create_index("employee_id")

    await db.employee_upload_intents.create_index("expires_at",expireAfterSeconds=0)
    await db.employee_upload_intents.create_index([("employee_id",1),("state",1)])

    await db.employee_leave_types.create_index([("company_id",1),("normalized_name",1)],unique=True,partialFilterExpression={"is_active":True})
    await db.employee_leave_types.create_index([("company_id",1),("is_active",1)])

    from app.features.access_control.models import Permission
    resources={"profiles":["view","create","edit","approve"],"documents":["view","create","edit","approve"],"attendance":["view","edit","export"],"leave":["view","create","approve","export"],"edits":["view","create","approve"],"reports":["view","export"],"settings":["view","edit"]}
    for resource,actions in resources.items():
        definition=Permission(module="employee_hr",resource=resource,actions=actions,label="Employee HR "+resource.replace("_"," ").title())
        await db.permissions.update_one({"module":"employee_hr","resource":resource},{"$setOnInsert":definition.model_dump(exclude={"id"})},upsert=True)

    await db.employees.create_index("hr_event_outbox.id")
    await db.audit_logs.create_index("metadata.hr_event_id",unique=True,partialFilterExpression={"metadata.hr_event_id":{"$exists":True}})
    await db.audit_logs.create_index([("metadata.hr_notification_delivered",1),("created_at",1)],partialFilterExpression={"metadata.hr_notification":{"$exists":True}})
