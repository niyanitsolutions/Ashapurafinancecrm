"""Human-readable sequential business IDs (AFS-EMP-000001, AFS-LEAD-000001, ...).

Backed by a `counters` collection: one document per prefix, incremented atomically via
findOneAndUpdate so concurrent requests never collide. These IDs are for staff-facing
display/search only — Mongo's own _id (ObjectId) remains the actual primary key and the
target of every reference, so this scheme can be reformatted later without touching
relationships.
"""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument


class IdPrefix:
    EMPLOYEE = "EMP"
    CUSTOMER = "CUS"
    LEAD = "LEAD"
    APPLICATION = "APP"
    REFERRAL_PARTNER = "REF"
    LOAN_CASE = "LOAN"
    INSURANCE_CASE = "INS"
    INTEGRATION = "INTG"
    TICKET = "TICKET"


_PAD_WIDTH = 6
_CODE_FORMAT = "AFS-{prefix}-{seq:0{width}d}"


async def generate_id(db: AsyncIOMotorDatabase[Any], prefix: str) -> str:
    counters = db["counters"]
    doc = await counters.find_one_and_update(
        {"_id": prefix},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return _CODE_FORMAT.format(prefix=prefix, seq=doc["seq"], width=_PAD_WIDTH)
