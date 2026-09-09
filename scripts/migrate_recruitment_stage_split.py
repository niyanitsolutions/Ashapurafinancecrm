"""Insurance Advisor Recruitment — 2026 stage split.

The old recruitment pipeline had one umbrella "Doc Collection" stage spanning two values:

    doc_collection_examination      (collecting docs / awaiting first exam)
    doc_collection_re_examination   (awaiting a re-exam)

The redesign flattens this into real stages, one per recruitment tab:

    doc_collection -> exam_fee_status -> examination -> (re_examination)

`RecruitmentLead.stage` carries a `Field(pattern=...)` regex; once the app's
`RecruitmentStage.ALL` no longer contains the two legacy values, an un-migrated row
still LOADS (the model keeps a lenient `ALL_INCLUDING_LEGACY` pattern) but never appears
under any tab. This migration remaps every such row so it lands in the right new tab.

Remap:
    doc_collection_examination + all required documents present -> examination
    doc_collection_examination + documents incomplete            -> doc_collection
    doc_collection_re_examination                                -> re_examination

**Only `recruitment_leads` (+ its `recruitment_activities` log) are touched. Loan and
Insurance are never read or written.** Idempotent: a row already on a new stage is
skipped; re-running is a no-op.

Run from repo root:  python scripts/migrate_recruitment_stage_split.py
Run from backend/:    python ../scripts/migrate_recruitment_stage_split.py
"""

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config.database import get_database

_LEGACY_EXAMINATION = "doc_collection_examination"
_LEGACY_RE_EXAMINATION = "doc_collection_re_examination"


def _documents_ready(docs: dict | None) -> bool:
    """Mirror of `RecruitmentService._documents_ready` on the raw stored shape: the four
    required documents + a photo + a signature, and — for a cheque bank proof — the
    printed-name attestation."""
    if not docs:
        return False
    if not (docs.get("pan") and docs.get("aadhaar") and docs.get("bank_proof") and docs.get("qualification")):
        return False
    if not (docs.get("photo") and docs.get("signature")):
        return False
    return not (docs.get("bank_proof_type") == "cheque" and not docs.get("cheque_name_confirmed"))


async def _remap(db) -> None:
    leads = db["recruitment_leads"]
    activities = db["recruitment_activities"]
    rows = await leads.find({"stage": {"$in": [_LEGACY_EXAMINATION, _LEGACY_RE_EXAMINATION]}}).to_list(length=100_000)

    remapped = 0
    for row in rows:
        old = row["stage"]
        if old == _LEGACY_RE_EXAMINATION:
            new = "re_examination"
        else:
            new = "examination" if _documents_ready(row.get("documents")) else "doc_collection"

        await leads.update_one({"_id": row["_id"]}, {"$set": {"stage": new, "updated_at": datetime.now(UTC)}})
        await activities.insert_one({
            "recruitment_lead_id": str(row["_id"]),
            "event_type": "stage_changed",
            "metadata": {"from": old, "to": new, "reason": "Recruitment stage split migration."},
            "created_by": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "is_deleted": False,
            "version": 1,
        })
        remapped += 1
        print(f"  {row.get('recruitment_code', row['_id'])}: {old} -> {new}")

    print(f"\nrecruitment_leads: remapped {remapped} of {len(rows)} legacy row(s). Loan / Insurance untouched.")


async def main() -> None:
    db = get_database()
    print(f"Connected to database: {db.name!r}")
    await _remap(db)


if __name__ == "__main__":
    asyncio.run(main())
