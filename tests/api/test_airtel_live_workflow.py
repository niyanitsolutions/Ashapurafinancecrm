from test_airtel_transport import confirmed_auth_stub  # noqa: F401

"""All provider calls are mocked; no production SMS or deployment."""

import json
from datetime import timedelta

import pytest
from app.features.communication import airtel_iq
from app.security.encryption import decrypt
from app.utils.datetime import utc_now
from bson import ObjectId
from test_airtel_configuration import BASE, create
from test_airtel_transport import CONFIG


async def setup(client, mock_db, owner_headers, monkeypatch):
    calls = []

    async def request(body, authorization):
        calls.append(body)
        return 200, None

    monkeypatch.setattr(airtel_iq, "request", request)
    row = await create(client, mock_db, owner_headers, CONFIG)
    url = BASE + "/" + row["id"]
    assert (
        await client.patch(url + "/enable", headers=owner_headers)
    ).status_code == 200
    return row, url, calls


async def send(client, url, headers, request_id="a" * 32):
    result = await client.post(
        url + "/airtel-test-sms",
        headers=headers,
        json={"mobile": "9000000088", "confirm_send": True, "request_id": request_id},
    )
    assert result.status_code == 200, result.text
    return result.json()["data"]


async def test_saved_validated_submitted_verified_active_separate_states(
    client, mock_db, owner_headers, monkeypatch, caplog
):
    _row, url, calls = await setup(client, mock_db, owner_headers, monkeypatch)
    assert not calls
    data = (await client.get(url, headers=owner_headers)).json()["data"]
    assert (
        data["airtel_workflow"]["validated_at"]
        and not data["airtel_workflow"]["verified_at"]
    )
    assert data["last_success_at"] is None
    assert (
        await client.post(url + "/activate", headers=owner_headers)
    ).status_code == 422
    sent = await send(client, url, owner_headers)
    assert sent["success"] and sent["challenge_id"] and len(calls) == 1
    otp = calls[0]["message"].split(" is ")[1].split(".")[0]
    assert "otp" not in sent and "message" not in sent
    assert all(value != otp for value in sent.values())
    assert (
        await client.post(url + "/activate", headers=owner_headers)
    ).status_code == 422
    payload = {"mobile": "9000000088", "challenge_id": sent["challenge_id"], "otp": otp}
    verify = url + "/airtel-verify-test-otp"
    assert (
        await client.post(
            verify, headers=owner_headers, json=payload | {"mobile": "9000000099"}
        )
    ).status_code == 422
    assert (
        await client.post(
            verify,
            headers=owner_headers,
            json=payload | {"otp": "9999" if otp != "9999" else "9998"},
        )
    ).status_code == 422
    correct = await client.post(verify, headers=owner_headers, json=payload)
    assert correct.status_code == 200, correct.text
    assert (
        await client.post(verify, headers=owner_headers, json=payload)
    ).status_code in {409, 422}
    assert (
        await client.post(url + "/activate", headers=owner_headers)
    ).status_code == 200
    stored = await mock_db.integration_airtel_test_otps.find_one(
        {"_id": sent["challenge_id"]}
    )
    assert stored["used"] and stored["otp_hash"] != otp
    assert "otp" not in stored and "mobile" not in stored
    assert otp not in caplog.text and "fixture-customer" not in caplog.text
    logs = (await client.get(url + "/test-logs", headers=owner_headers)).json()["data"]
    assert {"configuration_validation", "sms_submission", "otp_verification"} <= {
        log["kind"] for log in logs
    }


async def test_endpoint_customer_id_round_trip_and_numeric_rejected(
    client, mock_db, owner_headers, monkeypatch
):
    row, url, calls = await setup(client, mock_db, owner_headers, monkeypatch)
    endpoint = CONFIG["api_url"]
    for _ in range(2):
        read = (await client.get(url, headers=owner_headers)).json()["data"]
        assert read["config"]["api_url"] == endpoint
        assert read["config"]["customer_id"] == "********"
        result = await client.patch(
            url,
            headers=owner_headers,
            json={"config": {"customer_id": "********"}, "name": "Updated name"},
        )
        assert result.status_code == 200, result.text
    assert (
        await client.patch(
            url, headers=owner_headers, json={"config": {"api_url": "1234567890"}}
        )
    ).status_code == 422
    raw = await mock_db.integration_configs.find_one({"_id": ObjectId(row["id"])})
    values = json.loads(decrypt(raw["config_encrypted"]))
    assert (
        values["api_url"] == endpoint and values["customer_id"] == CONFIG["customer_id"]
    )
    assert not calls


async def test_expired_otp_and_changed_configuration_cannot_verify(
    client, mock_db, owner_headers, monkeypatch
):
    _row, url, calls = await setup(client, mock_db, owner_headers, monkeypatch)
    sent = await send(client, url, owner_headers)
    otp = calls[0]["message"].split(" is ")[1].split(".")[0]
    await mock_db.integration_airtel_test_otps.update_one(
        {"_id": sent["challenge_id"]},
        {"$set": {"expires_at": utc_now() - timedelta(seconds=1)}},
    )
    verify = url + "/airtel-verify-test-otp"
    payload = {"mobile": "9000000088", "challenge_id": sent["challenge_id"], "otp": otp}
    assert (
        await client.post(verify, headers=owner_headers, json=payload)
    ).status_code == 422
    await client.patch(
        url, headers=owner_headers, json={"config": {"customer_id": "changed-owner-id"}}
    )
    read = (await client.get(url, headers=owner_headers)).json()["data"]
    assert (
        read["airtel_workflow"]["validated_at"] is None
        and read["airtel_workflow"]["verified_at"] is None
    )
    assert (
        await client.post(verify, headers=owner_headers, json=payload)
    ).status_code == 422


async def test_test_otp_attempt_limit_and_duplicate_send(
    client, mock_db, owner_headers, monkeypatch
):
    _row, url, calls = await setup(client, mock_db, owner_headers, monkeypatch)
    sent = await send(client, url, owner_headers)
    duplicate = await client.post(
        url + "/airtel-test-sms",
        headers=owner_headers,
        json={"mobile": "9000000088", "confirm_send": True, "request_id": "a" * 32},
    )
    assert duplicate.status_code == 409 and len(calls) == 1
    otp = calls[0]["message"].split(" is ")[1].split(".")[0]
    bad = "9999" if otp != "9999" else "9998"
    for _ in range(5):
        result = await client.post(
            url + "/airtel-verify-test-otp",
            headers=owner_headers,
            json={
                "mobile": "9000000088",
                "challenge_id": sent["challenge_id"],
                "otp": bad,
            },
        )
        assert result.status_code == 422
    correct = await client.post(
        url + "/airtel-verify-test-otp",
        headers=owner_headers,
        json={"mobile": "9000000088", "challenge_id": sent["challenge_id"], "otp": otp},
    )
    assert correct.status_code == 422


@pytest.mark.parametrize("mode", ["rejected", "unknown"])
async def test_failed_or_ambiguous_send_records_failure_without_retry(
    client, mock_db, owner_headers, monkeypatch, mode
):
    import httpx

    _row, url, calls = await setup(client, mock_db, owner_headers, monkeypatch)

    async def request(body, auth):
        calls.append(True)
        if mode == "unknown":
            raise httpx.ReadTimeout("private credential details")
        return 401, {"unknown-schema": "private"}

    monkeypatch.setattr(airtel_iq, "request", request)
    sent = await send(client, url, owner_headers)
    assert not sent["success"] and sent["status"] == mode and not sent["challenge_id"]
    read = (await client.get(url, headers=owner_headers)).json()["data"]
    assert read["last_failure_at"] and not read["airtel_workflow"]["verified_at"]
    duplicate = await client.post(
        url + "/airtel-test-sms",
        headers=owner_headers,
        json={"mobile": "9000000088", "confirm_send": True, "request_id": "a" * 32},
    )
    assert duplicate.status_code == 409 and len(calls) == 1
    assert "private" not in str(sent)
    assert sent["diagnostics"]["outcome_type"] == ("timeout" if mode == "unknown" else "http_non_200")
    logs=(await client.get(url+"/test-logs",headers=owner_headers)).json()["data"]
    submission=next(log for log in logs if log["kind"]=="sms_submission")
    assert submission["diagnostics"]["http_status"] == (None if mode=="unknown" else 401)
    assert "private" not in str(submission)



async def test_explicit_repair_of_legacy_bad_endpoint_retains_customer_id(
    client, mock_db, owner_headers, monkeypatch
):
    from app.security.encryption import encrypt

    row, url, _calls = await setup(client, mock_db, owner_headers, monkeypatch)
    old = CONFIG | {"api_url": "1234567890"}
    await mock_db.integration_configs.update_one(
        {"_id": ObjectId(row["id"])},
        {"$set": {"config_encrypted": encrypt(json.dumps(old))}},
    )
    read = (await client.get(url, headers=owner_headers)).json()["data"]
    assert read["airtel_workflow"]["expected_endpoint"] == CONFIG["api_url"]
    fixed = await client.patch(
        url, headers=owner_headers, json={"config": {"api_url": CONFIG["api_url"]}}
    )
    assert fixed.status_code == 200, fixed.text
    raw = await mock_db.integration_configs.find_one({"_id": ObjectId(row["id"])})
    values = json.loads(decrypt(raw["config_encrypted"]))
    assert (
        values["api_url"] == CONFIG["api_url"]
        and values["customer_id"] == CONFIG["customer_id"]
    )


async def test_concurrent_verification_consumes_test_otp_once(
    client, mock_db, owner_headers, monkeypatch
):
    import asyncio

    _row, url, calls = await setup(client, mock_db, owner_headers, monkeypatch)
    sent = await send(client, url, owner_headers)
    otp = calls[0]["message"].split(" is ")[1].split(".")[0]
    payload = {"mobile": "9000000088", "challenge_id": sent["challenge_id"], "otp": otp}
    responses = await asyncio.gather(
        *(
            client.post(
                url + "/airtel-verify-test-otp", headers=owner_headers, json=payload
            )
            for _ in range(2)
        )
    )
    assert sum(response.status_code == 200 for response in responses) == 1
    assert (
        await mock_db.integration_test_logs.count_documents(
            {"kind": "otp_verification"}
        )
        == 1
    )
    assert await mock_db.auth_login_policy.count_documents({}) == 0


async def test_legacy_active_without_receipt_proof_cannot_cut_over(
    client, mock_db, owner_headers, monkeypatch
):
    row, _url, _calls = await setup(client, mock_db, owner_headers, monkeypatch)
    await mock_db.integration_configs.update_one(
        {"_id": ObjectId(row["id"])},
        {
            "$set": {
                "is_active": True,
                "last_success_at": utc_now(),
                "airtel_test_verified_at": None,
            }
        },
    )
    response = await client.post("/api/v1/auth/pin/cutover", headers=owner_headers)
    assert response.status_code == 409
    assert await mock_db.auth_login_policy.count_documents({}) == 0
