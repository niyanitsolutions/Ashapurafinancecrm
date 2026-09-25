"""Backfill explicit routes for forms already connected before Meta Form Routing.

Only forms present in the active Meta connection at migration time are converted from
the preserved legacy capture-source default. New forms are never defaulted. Existing
`meta_lead_routings` rows are never overwritten. Idempotent.

Run before deploying the new backend:
    python scripts/migrate_meta_form_routing.py

Rollback rows created by this migration and never subsequently edited:
    python scripts/migrate_meta_form_routing.py --rollback
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config.database import get_database
from app.features.integrations import oauth as oauth_client
from app.security.encryption import decrypt
from app.utils.datetime import utc_now

_MIGRATION_KEY = "meta_form_routing_v1_legacy_selected_forms"


async def _rollback(db) -> None:
    result = await db["meta_lead_routings"].delete_many({
        "migration_key": _MIGRATION_KEY, "version": 1, "updated_by": None,
    })
    print(f"Removed {result.deleted_count} untouched routing rows created by this migration.")


async def _migrate(db) -> None:
    source = await db["capture_sources"].find_one({"key": "meta_lead_ads", "is_deleted": False})
    if not source or not source.get("default_product_category") or not source.get("default_product_id"):
        raise RuntimeError("Legacy Meta default Category/Product is incomplete; configure routes in the UI instead.")
    config = await db["integration_configs"].find_one({"integration_type": "meta", "is_active": True, "is_deleted": False})
    if not config:
        raise RuntimeError("No active Meta integration was found.")
    credentials = json.loads(decrypt(config["config_encrypted"])) if config.get("config_encrypted") else {}
    selected_ids = [value for value in credentials.get("selected_forms", "").split(",") if value]
    fetched = []
    if credentials.get("access_token") and credentials.get("page_id"):
        fetched = await oauth_client.fetch_lead_forms(
            page_access_token=credentials["access_token"], page_id=credentials["page_id"],
        )
    names = {str(form["id"]): str(form.get("name") or form["id"]) for form in fetched}
    form_ids = selected_ids or list(names)
    if not form_ids:
        raise RuntimeError("No existing Meta forms could be identified; no routing rows were written.")

    now = utc_now()
    category = source["default_product_category"]
    destination = "insurance_policy_leads" if category == "insurance" else "leads"
    inserted = 0
    for form_id in form_ids:
        result = await db["meta_lead_routings"].update_one(
            {"meta_form_id": form_id},
            {"$setOnInsert": {
                "meta_form_id": form_id, "form_name": names.get(form_id, form_id),
                "category": category, "product_mode": "default",
                "default_product_id": source["default_product_id"],
                "destination_module": destination,
                "destination_type": "fresh_lead" if category == "insurance" else "fresh_leads",
                "product_question_key": None, "product_question_label": None,
                "answer_mappings": {}, "discovered_questions": [], "priority": 0,
                "status": "active", "created_at": now, "updated_at": now,
                "created_by": None, "updated_by": None, "is_deleted": False,
                "deleted_at": None, "deleted_by": None, "version": 1,
                "migration_key": _MIGRATION_KEY,
            }},
            upsert=True,
        )
        inserted += int(result.upserted_id is not None)
    print(f"Created {inserted} explicit routes for {len(form_ids)} existing forms; existing routes were preserved.")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    db = get_database()
    await (_rollback(db) if args.rollback else _migrate(db))


if __name__ == "__main__":
    asyncio.run(main())
