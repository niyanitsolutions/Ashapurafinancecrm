"""Synthetic encrypted records only; never connects to Airtel."""

import json

from app.features.integrations.airtel_migration import migrate
from app.security.encryption import decrypt, encrypt
from bson import ObjectId


async def test_upgrade_dry_run_apply_idempotence_and_credentials(mock_db):
    credentials = {
        "customer_id": "synthetic-customer",
        "username": "synthetic-user",
        "password": "synthetic-password",
    }
    old = credentials | {
        "entity_id": "AIR7316372024",
        "destination_template": '["{{mobile}}"]',
        "authorization_value": "obsolete-header",
        "contract_confirmed": "true",
    }
    oid = ObjectId()
    encrypted = encrypt(json.dumps(old))
    await mock_db.integration_configs.insert_one(
        {
            "_id": oid,
            "provider": "airtel_iq",
            "integration_type": "sms",
            "is_deleted": False,
            "is_active": True,
            "config_encrypted": encrypted,
        }
    )
    await mock_db.integration_configs.insert_one(
        {
            "_id": ObjectId(),
            "provider": "other",
            "integration_type": "sms",
            "is_deleted": False,
            "config_encrypted": encrypted,
        }
    )
    dry = await migrate(mock_db)
    assert (
        dry["changed"] == 1
        and (await mock_db.integration_configs.find_one({"_id": oid}))[
            "config_encrypted"
        ]
        == encrypted
    )
    assert (await migrate(mock_db, apply=True))["changed"] == 1
    row = await mock_db.integration_configs.find_one({"_id": oid})
    values = json.loads(decrypt(row["config_encrypted"]))
    assert (
        values["entity_id"] == "1001474305342749488"
        and values["destination_template"] == "[]"
    )
    assert "authorization_value" not in values
    assert all(values[key] == value for key, value in credentials.items())
    assert not row["is_active"] and values["contract_confirmed"] == "false"
    assert (await migrate(mock_db, apply=True))["changed"] == 0
    assert await mock_db.sms_submissions.count_documents({}) == 0
