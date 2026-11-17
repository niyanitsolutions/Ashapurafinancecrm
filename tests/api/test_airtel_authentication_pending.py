"""Default runtime is fail-closed. No confirmed_auth_stub is imported here."""

import json

from app.features.communication import airtel_iq as adapter
from app.features.integrations import airtel_iq
from app.security.encryption import decrypt
from bson import ObjectId
from test_airtel_configuration import BASE, create

CREDENTIALS = {
    "customer_id": "synthetic-customer-secret",
    "username": "synthetic-username-secret",
    "password": "synthetic-password-secret",
    "contract_confirmed": "false",
}


async def test_three_credentials_encrypted_masked_blank_preserved_and_rotatable(
    client, mock_db, owner_headers, caplog
):
    row = await create(client, mock_db, owner_headers, CREDENTIALS)
    url = BASE + "/" + row["id"]
    for key in ("customer_id", "username", "password"):
        assert row["config"][key] == "********"
    raw = await mock_db.integration_configs.find_one({"_id": ObjectId(row["id"])})
    stored = json.loads(decrypt(raw["config_encrypted"]))
    for key in ("customer_id", "username", "password"):
        assert (
            stored[key] == CREDENTIALS[key]
            and CREDENTIALS[key] not in raw["config_encrypted"]
        )
    result = await client.patch(
        url,
        headers=owner_headers,
        json={"config": {"customer_id": "", "username": " ", "password": ""}},
    )
    assert result.status_code == 200, result.text
    reread = await client.get(url, headers=owner_headers)
    assert all(
        reread.json()["data"]["config"][key] == "********"
        for key in ("customer_id", "username", "password")
    )
    raw = await mock_db.integration_configs.find_one({"_id": ObjectId(row["id"])})
    assert json.loads(decrypt(raw["config_encrypted"])) == stored
    changed = await client.patch(
        url, headers=owner_headers, json={"config": {"password": "replacement-secret"}}
    )
    assert (
        changed.status_code == 200
        and changed.json()["data"]["config"]["password"] == "********"
    )
    raw = await mock_db.integration_configs.find_one({"_id": ObjectId(row["id"])})
    assert (
        json.loads(decrypt(raw["config_encrypted"]))["password"] == "replacement-secret"
    )
    assert "replacement-secret" not in caplog.text
    assert "replacement-secret" not in str(
        await mock_db.audit_logs.find({}).to_list(None)
    )


async def test_default_authentication_blocks_send_and_activation_after_local_validation(
    client, mock_db, owner_headers, monkeypatch
):
    assert airtel_iq.authentication_ready(CREDENTIALS) is False

    async def forbidden(*args, **kwargs):
        raise AssertionError("Authentication is unknown; network must not run")

    monkeypatch.setattr(adapter, "request", forbidden)
    row = await create(client, mock_db, owner_headers, CREDENTIALS)
    url = BASE + "/" + row["id"]
    validated = await client.post(url + "/test", headers=owner_headers, json={})
    assert validated.status_code == 200 and validated.json()["data"]["success"]
    assert "authentication" in validated.json()["data"]["error_message"].lower()
    assert (
        await client.patch(
            url, headers=owner_headers, json={"config": {"contract_confirmed": "true"}}
        )
    ).status_code == 200
    assert (
        await client.patch(url + "/enable", headers=owner_headers)
    ).status_code == 200
    sent = await client.post(
        url + "/airtel-test-sms",
        headers=owner_headers,
        json={"mobile": "9000000088", "request_id": "a" * 32, "confirm_send": True},
    )
    assert (
        sent.status_code == 422
        and "authentication" in sent.json()["error"]["message"].lower()
    )
    assert (
        await client.post(url + "/activate", headers=owner_headers)
    ).status_code == 422
    outcome = await adapter.submit(
        mock_db,
        airtel_iq.DEFAULTS
        | CREDENTIALS
        | {"authorization_value": "ASHFNS", "contract_confirmed": "true"},
        "9000000088",
        "0472",
        "blocked",
    )
    assert not outcome["success"] and outcome["status"] == "unconfigured"
    assert await mock_db.sms_submissions.count_documents({}) == 0
    assert await mock_db.integration_airtel_test_otps.count_documents({}) == 0
    assert await mock_db.auth_login_policy.count_documents({}) == 0
    public = (await client.get(url, headers=owner_headers)).json()["data"]
    assert public["airtel_workflow"]["authentication_ready"] is False
    assert public["last_success_at"] is None and public["is_active"] is False


async def test_secondary_owner_cannot_update_credentials(
    client, mock_db, owner_headers
):
    row = await create(client, mock_db, owner_headers, CREDENTIALS)
    owner = await mock_db.users.find_one({"role": "owner"})
    await mock_db.owner_profiles.update_one(
        {"user_id": str(owner["_id"])},
        {
            "$set": {
                "owner_type": "secondary",
                "is_deleted": False,
                "full_name": "Synthetic Secondary",
                "mobile": "9000000011",
                "email": "secondary@example.test",
            }
        },
        upsert=True,
    )
    denied = await client.patch(
        BASE + "/" + row["id"],
        headers=owner_headers,
        json={"config": {"password": "denied-change"}},
    )
    assert denied.status_code == 403
    raw = await mock_db.integration_configs.find_one({"_id": ObjectId(row["id"])})
    assert (
        json.loads(decrypt(raw["config_encrypted"]))["password"]
        == CREDENTIALS["password"]
    )


async def test_legacy_saved_header_cannot_bypass_unknown_three_credential_auth(
    mock_db, monkeypatch
):
    async def forbidden(*args, **kwargs):
        raise AssertionError("No legacy fallback is authorized")

    monkeypatch.setattr(adapter, "request", forbidden)
    legacy = airtel_iq.DEFAULTS | {
        "customer_id": "old-customer",
        "authorization_value": "ASHFNS",
        "contract_confirmed": "true",
    }
    result = await adapter.submit(
        mock_db, legacy, "9000000088", "0472", "legacy-blocked"
    )
    assert not result["success"] and result["error"] == airtel_iq.AUTHENTICATION_PENDING
    assert await mock_db.sms_submissions.count_documents({}) == 0
