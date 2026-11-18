
"""Airtel configuration-stage tests. Network is forbidden; PIN runtime is pending."""

import json

import pytest
from app.features.integrations.airtel_iq import BLOCKED, DEFAULTS, ensure_provider
from app.security.encryption import decrypt
from bson import ObjectId

BASE = "/api/v1/integration-configs"
SECRETS = {"customer_id": "cust-test-secret", "username": "u", "password": "p"}


async def test_explicit_sms_confirmation_success_activation_and_edit_reset(
    client, mock_db, owner_headers, monkeypatch
):
    from app.features.communication import airtel_iq
    from test_airtel_transport import CONFIG

    calls = []

    async def request(*args):
        calls.append(True)
        return 200, {"result": {"accepted": True}}

    monkeypatch.setattr(airtel_iq, "request", request)
    row = await create(client, mock_db, owner_headers, CONFIG)
    url = BASE + "/" + row["id"]
    payload = {"mobile": "9000000088", "request_id": "a" * 32, "confirm_send": False}
    assert (
        await client.post(url + "/airtel-test-sms", headers=owner_headers, json=payload)
    ).status_code == 422
    assert not calls
    assert (
        await client.patch(url + "/enable", headers=owner_headers)
    ).status_code == 200
    assert (
        await client.post(url + "/activate", headers=owner_headers)
    ).status_code == 422
    result = await client.post(
        url + "/airtel-test-sms",
        headers=owner_headers,
        json=payload | {"confirm_send": True},
    )
    assert result.status_code == 200 and result.json()["data"]["success"], result.text
    assert len(calls) == 1
    assert (
        await client.post(url + "/activate", headers=owner_headers)
    ).status_code == 422
    updated = await client.patch(
        url,
        headers=owner_headers,
        json={"config": {"customer_id": "rotated dummy customer"}},
    )
    assert (
        updated.status_code == 200 and updated.json()["data"]["last_success_at"] is None
    )
    assert not updated.json()["data"]["is_active"]


async def create(client, db, headers, config=None):
    await ensure_provider(db)
    response = await client.post(
        BASE,
        headers=headers,
        json={
            "integration_type": "sms",
            "provider": "airtel_iq",
            "name": "Airtel draft",
            "config": SECRETS
            if config is None
            else config | {"contract_confirmed": "false"},
        },
    )
    assert response.status_code == 200, response.text
    row = response.json()["data"]
    if config and config.get("contract_confirmed") == "true":
        validated = await client.post(
            BASE + "/" + row["id"] + "/test", headers=headers, json={}
        )
        assert validated.status_code == 200, validated.text
        confirmed = await client.patch(
            BASE + "/" + row["id"],
            headers=headers,
            json={"config": {"contract_confirmed": "true"}},
        )
        assert confirmed.status_code == 200, confirmed.text
        row = confirmed.json()["data"]
    return row


async def test_encryption_full_masking_edit_preserves_credentials(
    client, mock_db, owner_headers
):
    row = await create(client, mock_db, owner_headers)
    for key in SECRETS:
        assert row["config"][key] == "********"
    raw = await mock_db.integration_configs.find_one({"_id": ObjectId(row["id"])})
    assert all(
        secret not in raw["config_encrypted"] for secret in ("cust-test-secret",)
    )
    saved = json.loads(decrypt(raw["config_encrypted"]))
    assert all(saved[key] == value for key, value in SECRETS.items())
    assert all(saved[key] == value for key, value in DEFAULTS.items())
    response = await client.patch(
        BASE + "/" + row["id"],
        headers=owner_headers,
        json={"config": {key: "********" for key in SECRETS}},
    )
    assert response.status_code == 200
    raw = await mock_db.integration_configs.find_one({"_id": ObjectId(row["id"])})
    assert json.loads(decrypt(raw["config_encrypted"])) == saved
    updated = await client.patch(
        BASE + "/" + row["id"],
        headers=owner_headers,
        json={"config": {"password": "rotated-test-secret"}},
    )
    assert updated.json()["data"]["config"]["password"] == "********"
    audit = await mock_db.audit_logs.find({"metadata.config_id": row["id"]}).to_list(
        None
    )
    assert "cust-test-secret" not in str(audit) and "rotated-test-secret" not in str(
        audit
    )


@pytest.mark.parametrize(
    "config",
    [
        {"api_url": "http://127.0.0.1/internal"},
        {"sender_id": "WRONG"},
        {"dlt_template_id": "other"},
        {"entity_id": "other"},
        {"authorization": "guessed"},
        {"username": "newline\nnot-allowed"},
        {"message_type": "transactional"},
        {"password": "newline\nsecret"},
    ],
)
async def test_invalid_airtel_settings_rejected(client, mock_db, owner_headers, config):
    await ensure_provider(mock_db)
    response = await client.post(
        BASE,
        headers=owner_headers,
        json={
            "integration_type": "sms",
            "provider": "airtel_iq",
            "name": "Bad",
            "config": config,
        },
    )
    assert response.status_code == 422


async def test_test_connection_never_sends_or_claims_success(
    client, mock_db, owner_headers, monkeypatch, caplog
):
    from app.features.communication import adapters
    from app.features.integrations import testers

    async def forbidden(*args, **kwargs):
        raise AssertionError("Network access is forbidden")

    monkeypatch.setattr(testers, "_timed_get", forbidden)
    monkeypatch.setattr(adapters, "_timed_post", forbidden)
    row = await create(client, mock_db, owner_headers)
    result = await client.post(
        BASE + "/" + row["id"] + "/test", headers=owner_headers, json={}
    )
    assert result.status_code == 200 and result.json()["data"]["success"] is True
    assert "customer_id" not in result.json()["data"]["error_message"]
    assert "No SMS was sent" in result.json()["data"]["error_message"]
    raw = await mock_db.integration_configs.find_one({"_id": ObjectId(row["id"])})
    assert raw["last_success_at"] is None and raw["last_failure_at"] is None
    assert (
        await mock_db.integration_test_logs.count_documents(
            {"config_id": row["id"], "success": True}
        )
        == 1
    )
    for value in ("cust-test-secret", "rotated-test-secret"):
        assert value not in caplog.text
    await client.patch(
        BASE + "/" + row["id"] + "/enable", headers=owner_headers, json={}
    )
    result = await client.post(
        BASE + "/" + row["id"] + "/activate", headers=owner_headers, json={}
    )
    assert result.status_code == 422
    assert not (
        await mock_db.integration_configs.find_one({"_id": ObjectId(row["id"])})
    )["is_active"]
    draft = await client.post(
        BASE + "/test-draft",
        headers=owner_headers,
        json={"integration_type": "sms", "provider": "airtel_iq", "config": SECRETS},
    )
    assert draft.json()["data"]["success"] is False


async def test_unauthorized_and_anonymous_config_access(
    client, mock_db, owner_headers, employee_headers
):
    row = await create(client, mock_db, owner_headers)
    assert (await client.get(BASE + "/" + row["id"])).status_code == 401
    assert (
        await client.get(BASE + "/" + row["id"], headers=employee_headers)
    ).status_code == 403
    assert (
        await client.patch(
            BASE + "/" + row["id"],
            headers=employee_headers,
            json={"name": "Unauthorized"},
        )
    ).status_code == 403


async def test_provider_catalog_idempotence_and_no_generic_sms_fallback(
    mock_db, monkeypatch
):
    from app.features.communication import adapters

    await ensure_provider(mock_db)
    await ensure_provider(mock_db)
    assert (
        await mock_db.integration_providers.count_documents({"provider": "airtel_iq"})
        == 1
    )

    async def forbidden(*args, **kwargs):
        raise AssertionError("Generic SMS fallback was used")

    monkeypatch.setattr(adapters, "_timed_post", forbidden)
    result = await adapters.send_sms(
        recipient="9000000000",
        subject=None,
        body="sensitive",
        config={
            "_provider": "airtel_iq",
            "api_url": DEFAULTS["api_url"],
            "api_key": "must-not-be-used",
        },
    )
    assert not result.success and not result.is_transient and result.error == BLOCKED


async def test_no_sms_validation_and_confirmation_gate(
    client, mock_db, owner_headers, monkeypatch
):
    from app.features.communication import airtel_iq
    from test_airtel_transport import CONFIG

    async def forbidden(*args, **kwargs):
        raise AssertionError("No SMS allowed")

    monkeypatch.setattr(airtel_iq, "request", forbidden)
    await ensure_provider(mock_db)
    premature = await client.post(
        BASE,
        headers=owner_headers,
        json={
            "integration_type": "sms",
            "provider": "airtel_iq",
            "name": "Premature",
            "config": CONFIG,
        },
    )
    assert premature.status_code == 422
    row = await create(
        client, mock_db, owner_headers, CONFIG | {"contract_confirmed": "false"}
    )
    url = BASE + "/" + row["id"]
    assert (
        row["config"]["customer_id"] == "********"
        and row["config"]["password"] == "********"
    )
    assert (
        await client.patch(
            url, headers=owner_headers, json={"config": {"contract_confirmed": "true"}}
        )
    ).status_code == 422
    checked = await client.post(url + "/test", headers=owner_headers, json={})
    assert (
        checked.status_code == 200
        and "No SMS was sent" in checked.json()["data"]["error_message"]
    )
    confirmed = await client.patch(
        url, headers=owner_headers, json={"config": {"contract_confirmed": "true"}}
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["data"]["last_success_at"] is None
    changed = await client.patch(
        url,
        headers=owner_headers,
        json={"config": {"customer_id": "updated-owner-value"}},
    )
    assert (
        changed.status_code == 200
        and changed.json()["data"]["config"]["contract_confirmed"] == "false"
    )
    assert changed.json()["data"]["last_tested_at"] is None


async def test_unconfirmed_entity_is_not_silently_accepted(
    client, mock_db, owner_headers
):
    from test_airtel_transport import CONFIG

    await ensure_provider(mock_db)
    result = await client.post(
        BASE,
        headers=owner_headers,
        json={
            "integration_type": "sms",
            "provider": "airtel_iq",
            "name": "Wrong entity",
            "config": CONFIG
            | {"contract_confirmed": "false", "entity_id": "wrong-api-entity"},
        },
    )
    assert result.status_code == 422


def test_delegated_permissions_do_not_authorize_airtel_owner_action():
    from types import SimpleNamespace

    from app.core.exceptions import ForbiddenError
    from app.features.integrations.airtel_iq import require_owner

    with pytest.raises(ForbiddenError):
        require_owner(SimpleNamespace(role="employee"))
