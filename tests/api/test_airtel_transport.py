"""Mocked confirmed HTTP Basic transport tests; never send real SMS."""

import asyncio
import json

import httpx
import pytest
from app.features.communication import airtel_iq as adapter
from app.features.integrations.airtel_iq import DEFAULTS, ENDPOINT

CONFIG = DEFAULTS | {
    "customer_id": "fixture-customer",
    "username": "fixture-username",
    "password": "fixture-password",
    "message_type": "TRANSACTIONAL",
    "destination_template": "[]",
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
        '["91{{mobile}}"]',
    ],
)
async def test_invalid_destination_shape_never_sends(mock_db, monkeypatch, destination):
    async def forbidden(*args):
        raise AssertionError("Invalid destination must not reach Airtel")

    monkeypatch.setattr(adapter, "request", forbidden)
    from app.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        await adapter.submit(
            mock_db,
            CONFIG
            | {"destination_template": destination, "contract_confirmed": "false"},
            "9000000001",
            "0472",
            "invalid-destination",
        )
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
    }
    import base64

    assert isinstance(call["auth"], httpx.BasicAuth)
    authenticated = next(call["auth"].auth_flow(httpx.Request("POST", url)))
    assert (
        authenticated.headers["authorization"]
        == "Basic "
        + base64.b64encode(
            (CONFIG["username"] + ":" + CONFIG["password"]).encode()
        ).decode()
    )
    assert call["json"] == {
        "customerId": "fixture-customer",
        "destinationAddress": ["9000000001"],
        "dltTemplateId": DEFAULTS["dlt_template_id"],
        "entityId": DEFAULTS["entity_id"],
        "message": "Your OTP for mobile verification with Ashapura Financial Services is 0472. It is valid for 10 minutes. Do not share this OTP with anyone.",
        "messageType": "TRANSACTIONAL",
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
        (201, None, "rejected"),
        (204, {}, "rejected"),
        (302, {}, "rejected"),
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
        "username",
        "password",
        "contract_confirmed",
    ],
)
async def test_missing_contract_rule_fails_closed(mock_db, monkeypatch, key):
    async def forbidden(*args):
        raise AssertionError("Network is forbidden for incomplete contract")

    monkeypatch.setattr(adapter, "request", forbidden)
    result = await adapter.submit(
        mock_db,
        CONFIG | {key: "", "contract_confirmed": "false"},
        "9000000001",
        "0472",
        "missing",
    )
    assert result["status"] == "unconfigured"
    assert await mock_db.sms_submissions.count_documents({}) == 0


@pytest.mark.parametrize(
    "payload", [None, {}, "unexpected", {"error": "unconfirmed provider text"}]
)
async def test_http_200_is_submission_without_json_rule_or_delivery_claim(
    mock_db, monkeypatch, payload, caplog
):
    async def request(*args):
        return 200, payload

    monkeypatch.setattr(adapter, "request", request)
    config = {
        k: v for k, v in CONFIG.items() if k not in {"success_field", "success_value"}
    }
    result = await adapter.submit(mock_db, config, "9000000001", "0472", "http-only")
    assert {key: result[key] for key in ("success", "status", "error")} == {
        "success": True,
        "status": "accepted",
        "error": None,
    }
    assert result["diagnostics"]["http_status"] == 200
    assert "delivered" not in str(result)
    assert all(
        secret not in caplog.text for secret in ["0472", "fixture-customer", "ASHFNS"]
    )


async def test_timeout_remains_deduplicated_after_config_edit(mock_db, monkeypatch):
    calls = []

    async def request(*args):
        calls.append(True)
        raise httpx.ReadTimeout("sensitive exception")

    monkeypatch.setattr(adapter, "request", request)
    await adapter.submit(mock_db, CONFIG, "9000000001", "0472", "stable-id")
    result = await adapter.submit(
        mock_db,
        CONFIG | {"customer_id": "rotated-account"},
        "9000000001",
        "0472",
        "stable-id",
    )
    assert result["status"] == "unknown" and len(calls) == 1


async def test_connection_failure_unknown_without_provider_schema(mock_db, monkeypatch):
    async def request(*args):
        raise httpx.ConnectError("private details")

    monkeypatch.setattr(adapter, "request", request)
    result = await adapter.submit(
        mock_db, CONFIG, "9000000001", "0472", "connection-failure"
    )
    assert result["status"] == "unknown" and not result["success"]
    assert "private details" not in str(result)


async def test_each_recipient_is_runtime_array_without_saved_number(
    mock_db, monkeypatch
):
    bodies = []

    async def request(body, username, password):
        bodies.append(body)
        return 200, None

    monkeypatch.setattr(adapter, "request", request)
    for index, mobile in enumerate(["9000000011", "9000000022"]):
        result = await adapter.submit(
            mock_db, CONFIG, mobile, "0472", "recipient-" + str(index)
        )
        assert result["success"]
        assert bodies[index]["destinationAddress"] == [mobile]
    assert CONFIG["destination_template"] == "[]"
    assert all("{{" not in json.dumps(body) for body in bodies)


async def test_httpx_applies_basic_auth_on_wire_and_redacts_echo(
    mock_db, monkeypatch, caplog
):
    import base64

    client_class = httpx.AsyncClient
    expected = (
        "Basic "
        + base64.b64encode(
            (CONFIG["username"] + ":" + CONFIG["password"]).encode()
        ).decode()
    )
    calls = []

    def handler(request):
        calls.append(True)
        assert request.method == "POST" and str(request.url) == ENDPOINT
        assert request.headers["authorization"] == expected
        payload = json.loads(request.content)
        assert payload["customerId"] == CONFIG["customer_id"]
        assert "username" not in payload and "password" not in payload
        return httpx.Response(
            401,
            json={
                "message": "Invalid credentials "
                + expected
                + " "
                + CONFIG["username"]
                + " "
                + CONFIG["password"],
                "authorization": expected,
            },
        )

    def client(**kwargs):
        return client_class(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "AsyncClient", client)
    outcome = await adapter.submit(
        mock_db, CONFIG, "9000000001", "0472", "real-httpx-mock-wire"
    )
    assert not outcome["success"] and outcome["diagnostics"]["http_status"] == 401
    safe = (
        json.dumps(outcome)
        + caplog.text
        + str((await mock_db.sms_submissions.find_one({}))["diagnostics"])
    )
    for secret in (CONFIG["username"], CONFIG["password"], expected):
        assert secret not in safe
    await adapter.submit(mock_db, CONFIG, "9000000001", "0472", "real-httpx-mock-wire")
    assert len(calls) == 1
