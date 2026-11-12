"""Additive single-bank conversion. Dry-run is default; no CRM collections are touched."""

import hashlib
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.features.daily_operations.status_options import COMPANY, normalized
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now


async def migrate(db: Any, apply: bool = False) -> dict[str, int]:
    counts = {"eligible": 0, "converted": 0, "empty": 0, "conflicts": 0}
    async for doc in db.daily_follow_ups.find(
        {"$or": [{"banks": {"$exists": False}}, {"banks": None}]}
    ):
        name = doc.get("bank")
        if not isinstance(name, str) or not name.strip():
            counts["empty"] += 1
            continue
        counts["eligible"] += 1
        if not apply:
            continue
        norm = normalized(name)
        option = await db.daily_followup_bank_options.find_one(
            {"company_id": COMPANY, "normalized_name": norm}
        )
        if not option:
            oid = ObjectId(
                hashlib.sha256((COMPANY + ":daily-bank:" + norm).encode()).hexdigest()[:24]
            )
            now = utc_now()
            try:
                await db.daily_followup_bank_options.update_one(
                    {"_id": oid},
                    {
                        "$setOnInsert": {
                            "company_id": COMPANY,
                            "name": name,
                            "normalized_name": norm,
                            "value": "bank:" + str(oid),
                            "is_active": True,
                            "is_system": False,
                            "version": 1,
                            "created_by": None,
                            "created_by_name": "Legacy bank migration",
                            "created_at": now,
                            "updated_at": now,
                            "updated_by": None,
                            "deleted_at": None,
                        }
                    },
                    upsert=True,
                )
            except DuplicateKeyError:
                pass
            option = await db.daily_followup_bank_options.find_one(
                {"company_id": COMPANY, "normalized_name": norm}
            )
        if not option:
            counts["conflicts"] += 1
            continue
        result = await db.daily_follow_ups.update_one(
            {
                "_id": doc["_id"],
                "version": doc.get("version"),
                "bank": name,
                "$or": [{"banks": {"$exists": False}}, {"banks": None}],
            },
            {"$set": {"banks": [{"option_id": str(option["_id"]), "name": name}]}},
        )
        counts["converted" if result.modified_count else "conflicts"] += 1
    if apply and counts["converted"]:
        await write_audit_log(
            db,
            event_type="daily_followup_banks_migrated",
            metadata={"company_id": COMPANY, **counts},
        )
    return counts
