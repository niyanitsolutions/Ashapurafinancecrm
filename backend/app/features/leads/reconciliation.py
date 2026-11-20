"""Read-only preflight. Reports stable IDs and counts, never contact data or secrets."""

from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


async def assess_relationships(db: AsyncIOMotorDatabase[Any]) -> dict[str, Any]:
    report: dict[str, Any] = {
        "mode": "read_only",
        "issue_count": 0,
        "issues": [],
        "counts": {},
        "duplicate_keys": {},
    }
    for name in ("leads", "customers", "applications", "daily_follow_ups"):
        report["counts"][name] = await db[name].count_documents({"is_deleted": False})
    report["counts"]["placeholder_profiles"] = await db.customers.count_documents(
        {"is_deleted": False, "full_name": {"$regex": r"^\s*(customer)?\s*$", "$options": "i"}}
    )
    for collection, key in (
        ("leads", "intake_key"),
        ("daily_follow_ups", "working_key"),
        ("applications", "creation_key"),
    ):
        duplicates = (
            await db[collection]
            .aggregate(
                [
                    {"$match": {key: {"$type": "string"}}},
                    {"$group": {"_id": f"${key}", "count": {"$sum": 1}}},
                    {"$match": {"count": {"$gt": 1}}},
                    {"$count": "value"},
                ]
            )
            .to_list(1)
        )
        report["duplicate_keys"][f"{collection}.{key}"] = (
            duplicates[0]["value"] if duplicates else 0
        )

    def issue(kind: str, record_id: Any) -> None:
        report["issue_count"] += 1
        if len(report["issues"]) < 200:
            report["issues"].append({"kind": kind, "record_id": str(record_id)})

    async def inspect_batch(rows: list[dict[str, Any]]) -> None:
        maps = {}
        for field, collection in (
            ("user_id", "users"),
            ("customer_id", "customers"),
            ("lead_id", "leads"),
        ):
            ids = {row.get(field) for row in rows if ObjectId.is_valid(row.get(field))}
            maps[field] = {
                str(r["_id"]): r
                async for r in db[collection].find(
                    {"_id": {"$in": [ObjectId(value) for value in ids]}, "is_deleted": False},
                    {"user_id": 1},
                )
            }
        for row in rows:
            for field, records in maps.items():
                if row.get(field) and row[field] not in records:
                    issue(f"application_missing_{field}", row["_id"])
            customer = maps["customer_id"].get(row.get("customer_id") or "")
            if customer and customer.get("user_id") != row.get("user_id"):
                issue("application_customer_account_mismatch", row["_id"])

    batch = []
    async for row in db.applications.find(
        {"is_deleted": False}, {"user_id": 1, "customer_id": 1, "lead_id": 1}
    ).batch_size(200):
        batch.append(row)
        if len(batch) == 200:
            await inspect_batch(batch)
            batch.clear()
    if batch:
        await inspect_batch(batch)
    report["counts"][
        "legacy_daily_links_for_manual_review"
    ] = await db.daily_follow_ups.count_documents(
        {
            "is_deleted": False,
            "working_key": {"$exists": False},
            "$or": [{"lead_id": {"$type": "string"}}, {"case_id": {"$type": "string"}}],
        }
    )
    report["changes_applied"] = 0
    return report
