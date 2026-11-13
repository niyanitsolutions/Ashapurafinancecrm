"""Fixtures below are synthetic contract rules, not Airtel account defaults."""

import asyncio
import json

import httpx
import pytest
from app.features.communication import airtel_iq as adapter
from app.features.integrations.airtel_iq import DEFAULTS, ENDPOINT

CONFIG = DEFAULTS | {
    "customer_id": "fixture-customer",
    "authorization_value": "Fixture account secret",
    "message_type": "fixture-type",
    "destination_template": '["{{mobile}}"]',
    "success_field": "result.accepted",
    "success_value": "true",
    "contract_confirmed": "true",
}


@pytest.mark.parametrize(
    "destination",
    [
        "[1234567890]",
        '[{"mobile":"{{mobile}}"}]',
        '["{{mobile}}","other"]',
        '["literal-mobile"]',
    ],
)
async def test_invalid_destination_shape_never_sends(mock_db, monkeypatch, destination):
    async def forbidden(*args):
        raise AssertionError("Invalid destination must not reach Airtel")

    monkeypatch.setattr(adapter, "request", forbidden)
    result = await adapter.submit(
        mock_db,
        CONFIG | {"destination_template": destination},
        "9000000001",
        "0472",
        "invalid-destination",
    )
    assert not result["success"]
    assert await mock_db.sms_submissions.count_documents({}) == 0


@pytest.mark.parametrize("otp", ["12345", "{#numeric#}", "abcd", "１２３４"])
async def test_invalid_otp_never_sends(mock_db, monkeypatch, otp):
    from app.core.exceptions import ValidationError

    async def forbidden(*args):
        raise AssertionError("Invalid OTP must not reach Airtel")

    monkeypatch.setattr(adapter, "request", forbidden)
    with pytest.raises(ValidationError):
        await adapter.submit(mock_db, CONFIG, "9000000001", otp, "invalid-otp")
    assert await mock_db.sms_submissions.count_documents({}) == 0


async def test_exact_post_headers_body_and_no_secret_persistence(mock_db, monkeypatch):
    captured = []

    async def post(self, url, **kwargs):
        captured.append((url, kwargs))
        return httpx.Response(200, json={"result": {"accepted": True}})

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    result = await adapter.submit(
        mock_db, CONFIG, "9000000001", "0472", "unique-reference"
    )
    assert result["success"]
    url, call = captured[0]
    assert url == ENDPOINT
    assert call["headers"] == {
        "accept": "application/json",
        "content-type": "application/json",
        "Authorization": "Fixture account secret",
    }
    assert call["json"] == {
        "customerId": "fixture-customer",
        "destinationAddress": ["9000000001"],
        "dltTemplateId": DEFAULTS["dlt_template_id"],
        "entityId": DEFAULTS["entity_id"],
        "message": "Your OTP for mobile verification with Ashapura Financial Services is 0472. It is valid for 10 minutes. Do not share this OTP with anyone.",
        "messageType": "fixture-type",
        "sourceAddress": "ASHFNS",
    }
    assert (
        await adapter.submit(mock_db, CONFIG, "9000000001", "0472", "unique-reference")
    )["success"]
    assert len(captured) == 1
    records = str(await mock_db.sms_submissions.find().to_list(None))
    assert all(
        value not in records
        for value in [
            "0472",
            "Fixture account secret",
            "fixture-customer",
            "9000000001",
        ]
    )


@pytest.mark.parametrize(
    "code,payload,status",
    [
        (401, {"error": "secret failure"}, "rejected"),
        (429, {}, "rejected"),
        (500, {}, "rejected"),
        (200, None, "unknown"),
        (200, {"result": {"accepted": "true"}}, "unknown"),
        (302, {}, "unknown"),
    ],
)
async def test_unconfirmed_success_never_accepted_or_retried(
    mock_db, monkeypatch, code, payload, status
):
    calls = []

    async def request(*args):
        calls.append(True)
        return code, payload

    monkeypatch.setattr(adapter, "request", request)
    outcome = await adapter.submit(mock_db, CONFIG, "9000000001", "0472", "failure")
    assert not outcome["success"] and outcome["status"] == status
    assert "secret failure" not in json.dumps(outcome)
    await adapter.submit(mock_db, CONFIG, "9000000001", "0472", "failure")
    assert len(calls) == 1


async def test_timeout_and_concurrent_duplicate_no_retry(mock_db, monkeypatch):
    calls = []

    async def request(*args):
        calls.append(True)
        await asyncio.sleep(0)
        raise httpx.ReadTimeout("request could contain credentials")

    monkeypatch.setattr(adapter, "request", request)
    results = await asyncio.gather(
        *(
            adapter.submit(mock_db, CONFIG, "9000000001", "0472", "same")
            for _ in range(2)
        )
    )
    assert len(calls) == 1 and all(not r["success"] for r in results)
    assert "credentials" not in str(results)


@pytest.mark.parametrize(
    "key",
    [
        "customer_id",
        "authorization_value",
        "message_type",
        "destination_template",
        "success_field",
        "success_value",
        "contract_confirmed",
    ],
)
async def test_missing_contract_rule_fails_closed(mock_db, monkeypatch, key):
    async def forbidden(*args):
        raise AssertionError("Network is forbidden for incomplete contract")

    monkeypatch.setattr(adapter, "request", forbidden)
    result = await adapter.submit(
        mock_db, CONFIG | {key: ""}, "9000000001", "0472", "missing"
    )
    assert result["status"] == "unconfigured"
    assert await mock_db.sms_submissions.count_documents({}) == 0
