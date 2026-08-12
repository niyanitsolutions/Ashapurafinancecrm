from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_workflow_engine_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["workflow_definitions"].create_index([("case_type", 1), ("status", 1)], unique=True)

    await db["application_workflows"].create_index("case_code", unique=True)
    await db["application_workflows"].create_index("application_id", unique=True)
    await db["application_workflows"].create_index("customer_id")
    await db["application_workflows"].create_index("assigned_to")
    await db["application_workflows"].create_index([("case_type", 1), ("current_status", 1)])

    await db["application_status_history"].create_index("application_workflow_id")
    await db["application_notes"].create_index("application_workflow_id")
    await db["application_decisions"].create_index("application_workflow_id")
