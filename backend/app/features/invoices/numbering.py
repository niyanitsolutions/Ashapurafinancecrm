"""Invoice-only tail reuse. The shared counter never decreases.

One atomic counter operation consumes a reusable tail or allocates the next sequence.
A claimed number stays consumed if an insertion fails: crashes create gaps, not duplicates.
The partial unique index is the final guard; tombstone documents retain their original ID,
number, contents and audit evidence. No scan of older gaps is performed.
"""

from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

ACTIVE_NUMBER_INDEX = "invoice_number_reserved_unique"
ACTIVE_NUMBER_FILTER = {"is_deleted": False}


async def reuse_ready(db: AsyncIOMotorDatabase[Any]) -> bool:
    indexes = await db.invoices.index_information()
    target = indexes.get(ACTIVE_NUMBER_INDEX, {})
    return bool(
        target.get("unique")
        and target.get("partialFilterExpression") == ACTIVE_NUMBER_FILTER
        and not any(
            item.get("unique")
            and item.get("key") == [("invoice_number", 1)]
            and not item.get("partialFilterExpression")
            for item in indexes.values()
        )
    )


def sequence_of(invoice: dict[str, Any]) -> int | None:
    prefix = invoice["company"].get("prefix", "INV-")
    number = invoice["invoice_number"]
    suffix = number[len(prefix) :] if number.startswith(prefix) else ""
    return int(suffix) if suffix.isdigit() and number == f"{prefix}{int(suffix):06d}" else None


def never_issued_draft(invoice: dict[str, Any]) -> bool:
    protected = {"issued", "paid", "partially_paid", "cancelled"}
    return bool(
        invoice["status"] == "draft"
        and not any(invoice.get(field) for field in ("issued_at", "cancelled_at", "is_archived"))
        and not any(
            event.get("new_status") in protected
            or event.get("action") in {"issued", "cancelled", "correction_finalized"}
            for event in invoice.get("history", [])
        )
    )


async def deletion_eligibility(
    db: AsyncIOMotorDatabase[Any], invoice: dict[str, Any]
) -> dict[str, Any]:
    eligible = False
    reason = "Only the latest never-issued draft can make its number available for reuse."
    seq = sequence_of(invoice)
    if never_issued_draft(invoice):
        if not await reuse_ready(db):
            reason = (
                "Number retained: the reviewed invoice index migration is required before reuse."
            )
        else:
            counter = await db.counters.find_one({"_id": "INV"})
            eligible = seq is not None and counter is not None and counter.get("seq") == seq
            if eligible:
                reason = "Eligible only if it is still the latest allocation when deletion completes. Allocation is decided by the server; this is not a reservation."
    return {"eligible": eligible, "explanation": reason}


async def publish_deleted_tail(db: AsyncIOMotorDatabase[Any], invoice: dict[str, Any]) -> bool:
    if not (await deletion_eligibility(db, invoice))["eligible"]:
        return False
    seq = sequence_of(invoice)
    result = await db.counters.update_one(
        {"_id": "INV", "seq": seq},
        {
            "$set": {
                "reusable_invoice": {
                    "seq": seq,
                    "prefix": invoice["company"].get("prefix", "INV-"),
                    "invoice_id": invoice["id"],
                    "invoice_number": invoice["invoice_number"],
                }
            }
        },
    )
    return bool(result.matched_count)


async def allocate(
    db: AsyncIOMotorDatabase[Any], company: dict[str, Any]
) -> tuple[str, str | None]:
    await db.counters.update_one(
        {"_id": "INV"},
        {"$max": {"seq": company["starting_number"] - 1}},
        upsert=True,
    )
    if await reuse_ready(db):
        claimed = await db.counters.find_one_and_update(
            {
                "_id": "INV",
                "reusable_invoice": {"$exists": True},
                "reusable_invoice.prefix": company["prefix"],
                "$expr": {"$eq": ["$seq", "$reusable_invoice.seq"]},
            },
            {"$unset": {"reusable_invoice": ""}},
            return_document=ReturnDocument.BEFORE,
        )
        if claimed:
            candidate = claimed["reusable_invoice"]
            tombstone = await db.invoices.find_one(
                {
                    "_id": ObjectId(candidate["invoice_id"]),
                    "is_deleted": True,
                    "status": "draft",
                    "issued_at": None,
                    "is_archived": {"$ne": True},
                    "invoice_number": candidate["invoice_number"],
                }
            )
            protected = await db.invoices.find_one(
                {
                    "invoice_number": candidate["invoice_number"],
                    "$or": [
                        {"is_deleted": False},
                        {"status": {"$ne": "draft"}},
                        {"issued_at": {"$ne": None}},
                        {"is_archived": True},
                    ],
                }
            )
            if tombstone and never_issued_draft(tombstone) and not protected:
                return candidate["invoice_number"], candidate["invoice_id"]
    allocated = await db.counters.find_one_and_update(
        {"_id": "INV"},
        {"$inc": {"seq": 1}, "$unset": {"reusable_invoice": ""}},
        return_document=ReturnDocument.AFTER,
    )
    return f"{company['prefix']}{allocated['seq']:06d}", None
