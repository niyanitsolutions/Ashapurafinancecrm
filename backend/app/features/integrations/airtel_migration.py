"""Explicit, CAS-protected Airtel mapping upgrade. Never sends or changes secrets."""

import json
from typing import Any

from app.features.integrations.airtel_iq import corrected_values
from app.security.encryption import decrypt, encrypt
from app.utils.datetime import utc_now


async def migrate(db: Any, *, apply: bool = False) -> dict[str, int | bool]:
    result = {"scanned": 0, "changed": 0, "conflicts": 0, "apply": apply}
    async for row in db.integration_configs.find(
        {"provider": "airtel_iq", "integration_type": "sms", "is_deleted": False}
    ):
        result["scanned"] += 1
        original = json.loads(decrypt(row["config_encrypted"]))
        corrected = corrected_values(original)
        if corrected == original:
            continue
        corrected["contract_confirmed"] = "false"
        if not apply:
            result["changed"] += 1
            continue
        updated = await db.integration_configs.update_one(
            {"_id": row["_id"], "config_encrypted": row["config_encrypted"], "is_deleted": False},
            {
                "$set": {
                    "config_encrypted": encrypt(json.dumps(corrected)),
                    "is_active": False,
                    "last_tested_at": None,
                    "last_success_at": None,
                    "health_status": None,
                    "airtel_config_validated_at": None,
                    "airtel_validated_fingerprint": None,
                    "airtel_test_verified_at": None,
                    "airtel_test_challenge_id": None,
                    "airtel_last_submission_status": None,
                    "updated_at": utc_now(),
                }
            },
        )
        result["changed"] += updated.modified_count
        result["conflicts"] += int(not updated.matched_count)
    return result
