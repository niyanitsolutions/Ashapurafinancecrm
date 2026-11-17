from test_airtel_transport import confirmed_auth_stub  # noqa: F401

"""Untrusted provider replies must never leak echoed SMS/PII or trigger retries."""

import json

import httpx
import pytest
from app.features.communication import airtel_iq as adapter
from test_airtel_transport import CONFIG


@pytest.mark.parametrize(
    "code,payload,category,fmt",
    [
        (200, b"", "http_200", "empty"),
        (200, b"{broken", "http_200", "malformed_json"),
        (200, b"accepted", "http_200", "text"),
        (
            401,
            b'{"message":"Invalid authorization credentials"}',
            "http_non_200",
            "json",
        ),
        (400, b'{"message":"Invalid request"}', "http_non_200", "json"),
        (403, b"Forbidden account access", "http_non_200", "text"),
        (429, b'{"error":"Rate limit exceeded"}', "http_non_200", "json"),
        (500, b"{broken", "http_non_200", "malformed_json"),
        (302, b"redirect", "http_non_200", "text"),
        (None, b"bad", "unexpected_response", "unavailable"),
    ],
)
async def test_actual_transport_reply_classified_safely(
    mock_db, monkeypatch, code, payload, category, fmt
):
    calls = []

    async def request(*args):
        calls.append(True)
        return code, payload

    monkeypatch.setattr(adapter, "request", request)
    result = await adapter.submit(mock_db, CONFIG, "9000000001", "0472", "diagnostic")
    assert result["success"] == (code == 200)
    assert result["diagnostics"]["outcome_type"] == category
    assert result["diagnostics"]["response_format"] == fmt
    again = await adapter.submit(mock_db, CONFIG, "9000000001", "0472", "diagnostic")
    assert len(calls) == 1 and again["diagnostics"] == result["diagnostics"]
    if code == 401:
        assert "HTTP 401" in result["error"]


@pytest.mark.parametrize(
    "exc,category",
    [
        (httpx.ReadTimeout, "timeout"),
        (httpx.ConnectTimeout, "timeout"),
        (httpx.ConnectError, "connection_error"),
        (httpx.RemoteProtocolError, "unexpected_response"),
    ],
)
async def test_exceptions_are_distinct_without_exception_text_or_retry(
    mock_db, monkeypatch, exc, category
):
    calls = []

    async def request(*args):
        calls.append(True)
        raise exc("private fixture-customer 0472 9000000001")

    monkeypatch.setattr(adapter, "request", request)
    result = await adapter.submit(
        mock_db, CONFIG, "9000000001", "0472", "transport-failure"
    )
    assert (
        result["status"] == "unknown"
        and result["diagnostics"]["outcome_type"] == category
    )
    assert result["diagnostics"]["http_status"] is None
    await adapter.submit(mock_db, CONFIG, "9000000001", "0472", "transport-failure")
    assert len(calls) == 1
    assert "private" not in str(result)


async def test_actual_http_status_body_projection_and_redaction(
    mock_db, monkeypatch, caplog
):
    async def post(self, url, **kwargs):
        return httpx.Response(
            401,
            json={
                "error": {
                    "code": "AUTHENTICATION_FAILED",
                    "message": "Invalid customer id fixture-customer; authorization ASHFNS for Jane Doe jane@example.test at 123 Private Road; mobile 9000000001 OTP 0472",
                    "request": kwargs["json"],
                },
                "9000000001": "Jane Doe",
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    result = await adapter.submit(mock_db, CONFIG, "9000000001", "0472", "redaction")
    record = await mock_db.sms_submissions.find_one({})
    safe = json.dumps(
        {
            "response": result,
            "stored_diagnostics": record["diagnostics"],
            "logs": caplog.text,
        }
    )
    for secret in [
        "ASHFNS",
        "fixture-customer",
        "9000000001",
        "0472",
        "Jane",
        "Doe",
        "jane@example.test",
        "Private Road",
    ]:
        assert secret not in safe
    assert "Invalid customer id" in result["diagnostics"]["response_excerpt"]
    assert result["diagnostics"]["http_status"] == 401
    assert "[redacted]" in safe


async def test_oversized_reply_is_bounded(mock_db, monkeypatch):
    async def post(self, *args, **kwargs):
        return httpx.Response(502, text="PrivateName " * 5000)

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    result = await adapter.submit(mock_db, CONFIG, "9000000001", "0472", "large-body")
    assert result["diagnostics"]["response_format"] == "truncated"
    assert len(result["diagnostics"]["response_excerpt"]) <= 2000
    assert "PrivateName" not in str(result)


async def test_declared_json_malformed_body_does_not_override_http_200(
    mock_db, monkeypatch
):
    async def post(*args, **kwargs):
        return httpx.Response(
            200, content=b"not json", headers={"content-type": "application/json"}
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    result = await adapter.submit(
        mock_db, CONFIG, "9000000001", "0472", "declared-json"
    )
    assert result["success"] and result["diagnostics"]["http_status"] == 200
    assert result["diagnostics"]["response_format"] == "malformed_json"


async def test_excessive_json_nesting_cannot_hide_http_200(mock_db, monkeypatch):
    async def request(*args):
        return 200, b"[" * 2000 + b"]" * 2000

    monkeypatch.setattr(adapter, "request", request)
    result = await adapter.submit(mock_db, CONFIG, "9000000001", "0472", "deep-json")
    assert result["success"] and result["diagnostics"]["http_status"] == 200
    assert result["diagnostics"]["response_format"] == "malformed_json"
