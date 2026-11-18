"""Confirmed Basic credentials, encryption and authorization regression coverage."""

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


async def test_confirmed_basic_credentials_allow_authorized_test_not_early_activation(client,mock_db,owner_headers,monkeypatch):
    assert airtel_iq.authentication_ready(CREDENTIALS) is True
    calls=[]
    async def request(body,username,password):
        calls.append((body,username,password))
        return 200,None
    monkeypatch.setattr(adapter,"request",request)
    row=await create(client,mock_db,owner_headers,CREDENTIALS)
    url=BASE+"/"+row["id"]
    assert (await client.post(url+"/test",headers=owner_headers,json={})).json()["data"]["success"]
    assert (await client.patch(url,headers=owner_headers,json={"config":{"contract_confirmed":"true"}})).status_code==200
    assert (await client.patch(url+"/enable",headers=owner_headers)).status_code==200
    assert (await client.post(url+"/activate",headers=owner_headers)).status_code==422
    result=await client.post(url+"/airtel-test-sms",headers=owner_headers,json={"mobile":"9000000088","request_id":"a"*32,"confirm_send":True})
    assert result.status_code==200 and result.json()["data"]["success"],result.text
    assert len(calls)==1 and calls[0][1:]==(CREDENTIALS["username"],CREDENTIALS["password"])
    assert calls[0][0]["customerId"]==CREDENTIALS["customer_id"]
    assert calls[0][0]["entityId"]=="1001474305342749488"
    assert calls[0][0]["destinationAddress"]==["9000000088"]
    assert (await client.post(url+"/activate",headers=owner_headers)).status_code==422
    assert await mock_db.auth_login_policy.count_documents({})==0


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


async def test_legacy_header_cannot_replace_basic_credentials(
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
    assert not result["success"] and "Username" in result["error"]
    assert await mock_db.sms_submissions.count_documents({}) == 0
