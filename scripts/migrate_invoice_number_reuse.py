"""Reviewed invoice-only index migration. Dry-run by default; stop invoice writers for --apply.

Never modifies invoice documents or counters. Requires explicit target database name.
Rollback refuses after tail reuse has produced duplicate historical tombstone numbers.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config.database import get_database
from app.features.invoices.numbering import ACTIVE_NUMBER_FILTER, ACTIVE_NUMBER_INDEX
from app.features.invoices.repository import CORRECTION_FILTER, CORRECTION_INDEX
from motor.motor_asyncio import AsyncIOMotorDatabase


async def preflight(db: AsyncIOMotorDatabase[Any], *, rollback: bool = False) -> None:
    # Missing/invalid lifecycle fields must be reviewed, never silently backfilled.
    async for doc in db.invoices.find(
        {}, {"is_deleted": 1, "status": 1, "issued_at": 1, "is_archived": 1}
    ):
        if not isinstance(doc.get("is_deleted"), bool):
            raise TypeError(
                "Invoice lifecycle metadata requires owner review; no indexes changed."
            )
        if doc["is_deleted"] and (
            doc.get("status") != "draft"
            or doc.get("issued_at")
            or doc.get("is_archived")
        ):
            raise RuntimeError(
                "A protected invoice is soft-deleted. Review before enabling reuse."
            )
    matches = {} if rollback else ACTIVE_NUMBER_FILTER
    conflicts = await db.invoices.aggregate(
        [
            {"$match": matches},
            {"$group": {"_id": "$invoice_number", "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
            {"$limit": 1},
        ]
    ).to_list(1)
    if conflicts:
        raise RuntimeError(
            "Duplicate invoice numbers in target index scope; no data was modified. Roll forward after reuse; never remove tombstones to force rollback."
        )
    correction_scope = (
        {"replacement_for": {"$type": "string"}} if rollback else CORRECTION_FILTER
    )
    corrections = await db.invoices.aggregate(
        [
            {"$match": correction_scope},
            {"$group": {"_id": "$replacement_for", "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
            {"$limit": 1},
        ]
    ).to_list(1)
    if corrections:
        raise RuntimeError(
            "Duplicate correction sources in target index scope; no data modified."
        )
    indexes = await db.invoices.index_information()
    active = indexes.get(ACTIVE_NUMBER_INDEX)
    if active and (
        not active.get("unique")
        or active.get("partialFilterExpression") != ACTIVE_NUMBER_FILTER
    ):
        raise RuntimeError("Unexpected invoice index options. Review manually.")
    correction = indexes.get(CORRECTION_INDEX)
    if correction and (
        not correction.get("unique")
        or correction.get("partialFilterExpression") != CORRECTION_FILTER
    ):
        raise RuntimeError("Unexpected correction index options. Review manually.")
    legacy_correction = indexes.get("replacement_for_1")
    if legacy_correction and (
        not legacy_correction.get("unique")
        or legacy_correction.get("key") != [("replacement_for", 1)]
        or legacy_correction.get("partialFilterExpression")
        != {"replacement_for": {"$type": "string"}}
    ):
        raise RuntimeError(
            "Unexpected legacy correction index options. Review manually."
        )
    legacy = indexes.get("invoice_number_1")
    if legacy and (
        not legacy.get("unique")
        or legacy.get("key") != [("invoice_number", 1)]
        or legacy.get("partialFilterExpression")
    ):
        raise RuntimeError("Unexpected legacy invoice index options. Review manually.")


async def migrate(
    db: AsyncIOMotorDatabase[Any], *, apply: bool = False, rollback: bool = False
) -> None:
    await preflight(db, rollback=rollback)
    if not apply:
        return
    if rollback:
        # Reestablish the old guard before removing the new one.
        await db.invoices.create_index("invoice_number", unique=True)
        await db.invoices.create_index(
            "replacement_for",
            unique=True,
            partialFilterExpression={"replacement_for": {"$type": "string"}},
        )
        if CORRECTION_INDEX in await db.invoices.index_information():
            await db.invoices.drop_index(CORRECTION_INDEX)
        if ACTIVE_NUMBER_INDEX in await db.invoices.index_information():
            await db.invoices.drop_index(ACTIVE_NUMBER_INDEX)
    else:
        await db.invoices.create_index(
            "invoice_number",
            unique=True,
            name=ACTIVE_NUMBER_INDEX,
            partialFilterExpression=ACTIVE_NUMBER_FILTER,
        )
        await db.invoices.create_index(
            "replacement_for",
            unique=True,
            name=CORRECTION_INDEX,
            partialFilterExpression=CORRECTION_FILTER,
        )
        if "replacement_for_1" in await db.invoices.index_information():
            await db.invoices.drop_index("replacement_for_1")
        if "invoice_number_1" in await db.invoices.index_information():
            await db.invoices.drop_index("invoice_number_1")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", required=True, help="Must match configured MONGO_DB_NAME"
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    db = get_database()
    if db.name != args.database:
        raise RuntimeError("Explicit database name does not match configured target.")
    print(
        f"Invoice index target: {db.name}; mode: {'apply' if args.apply else 'dry-run'}"
    )
    await migrate(db, apply=args.apply, rollback=args.rollback)
    print(
        "Invoice index preflight/migration completed. No invoice records or counters changed."
    )


if __name__ == "__main__":
    asyncio.run(main())
