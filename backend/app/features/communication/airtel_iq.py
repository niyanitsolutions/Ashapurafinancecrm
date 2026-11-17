"""Airtel prepaid transport. Unknown account-specific rules are explicit configuration.

The payload uses a ten-digit recipient and HTTP 200 submission success.
Authentication is unconfirmed; default submission is blocked before provider I/O.
Timeout/ambiguous responses are never automatically retried (provider idempotency unknown).
"""

import hashlib
import json
from time import perf_counter
from typing import Any

import httpx
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import ValidationError
from app.features.integrations.airtel_iq import (
    APPROVED_MESSAGE,
    AUTHENTICATION_PENDING,
    BLOCKED,
    ENDPOINT,
    authentication_ready,
    confirmed_contract,
    validate_config,
)
from app.utils.datetime import utc_now


async def request(body: dict[str, Any], authorization: str) -> tuple[int, Any]:
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(15, connect=5, write=10, pool=5), follow_redirects=False
    ) as client:
        response = await client.post(
            ENDPOINT,
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "Authorization": authorization,
            },
            json=body,
        )
    from app.features.communication.airtel_diagnostics import MAX_BODY, ProviderBody

    return response.status_code, ProviderBody(
        response.content[: MAX_BODY + 1],
        response.headers.get("content-type", "").lower().startswith("application/json"),
    )


async def submit(
    db: Any, config: dict[str, str], mobile: str, otp: str, reference: str
) -> dict[str, Any]:
    if len(otp) != 4 or not otp.isascii() or not otp.isdigit():
        raise ValidationError("Airtel OTP must contain exactly four numeric digits.")
    if len(mobile) != 10 or not mobile.isascii() or not mobile.isdigit():
        raise ValidationError("Use the registered ten-digit mobile number.")
    if not authentication_ready(config):
        return {"success": False, "status": "unconfigured", "error": AUTHENTICATION_PENDING}
    config = validate_config(
        {k: v for k, v in config.items() if k not in {"provider", "_provider"}}
    )
    if not confirmed_contract(config):
        return {"success": False, "status": "unconfigured", "error": BLOCKED}
    from app.features.communication.airtel_diagnostics import failure_message, response_details

    key = hashlib.sha256(("airtel_iq:" + reference).encode()).hexdigest()
    stamp = utc_now()
    try:
        await db.sms_submissions.insert_one(
            {
                "_id": key,
                "provider": "airtel_iq",
                "destination": "******" + mobile[-4:],
                "status": "sending",
                "created_at": stamp,
            }
        )
    except DuplicateKeyError:
        prior = await db.sms_submissions.find_one({"_id": key})
        return {
            "success": bool(prior and prior["status"] == "accepted"),
            "status": (prior or {}).get("status", "unknown"),
            "error": "Submission already recorded; it was not sent again.",
            "diagnostics": (prior or {}).get(
                "diagnostics",
                {
                    "http_status": (prior or {}).get("http_status"),
                    "outcome_type": "previous_submission",
                    "response_format": "unavailable",
                    "response_excerpt": None,
                },
            ),
        }
    body = {
        "customerId": config.get("customer_id", ""),
        "destinationAddress": json.loads(
            config["destination_template"].replace("{{mobile}}", mobile)
        ),
        "dltTemplateId": config["dlt_template_id"],
        "entityId": config["entity_id"],
        "message": APPROVED_MESSAGE.replace("{OTP}", otp),
        "messageType": config["message_type"],
        "sourceAddress": config["sender_id"],
    }
    status = "unknown"
    code = None
    started = perf_counter()
    category = "unexpected_response"
    details = {"response_format": "unavailable", "response_excerpt": None}
    try:
        code, payload = await request(body, config["authorization_value"])
        if type(code) is not int or not 100 <= code <= 599:
            code = None
        else:
            # HTTP 200 is submission regardless of body shape or JSON validity.
            status = "accepted" if code == 200 else "rejected"
            category = "http_200" if code == 200 else "http_non_200"
            try:
                details = response_details(
                    payload, [mobile, otp, *config.values(), body["message"]]
                )
            except (TypeError, ValueError, RecursionError):
                details = {"response_format": "unreadable", "response_excerpt": None}
    except httpx.TimeoutException:
        category = "timeout"
    except httpx.NetworkError:
        category = "connection_error"
    except (httpx.ProtocolError, httpx.DecodingError):
        category = "unexpected_response"
    except httpx.HTTPError:
        category = "transport_error"
    except (TypeError, ValueError):
        category = "unexpected_response"
    diagnostics = {"http_status": code, "outcome_type": category, **details}
    await db.sms_submissions.update_one(
        {"_id": key},
        {
            "$set": {
                "status": status,
                "diagnostics": diagnostics,
                "http_status": code,
                "response_time_ms": round((perf_counter() - started) * 1000),
                "updated_at": utc_now(),
            }
        },
    )
    return {
        "success": status == "accepted",
        "status": status,
        "diagnostics": diagnostics,
        "error": None if status == "accepted" else failure_message(code, category),
    }
