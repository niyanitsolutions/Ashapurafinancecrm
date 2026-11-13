"""Airtel prepaid transport. Unknown account-specific rules are explicit configuration.

No Basic/Bearer scheme, destination structure, message type or success code is assumed.
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
    BLOCKED,
    ENDPOINT,
    confirmed_contract,
    validate_config,
)
from app.utils.datetime import utc_now


def field(payload: Any, path: str) -> Any:
    for key in path.split("."):
        if isinstance(payload, dict):
            payload = payload.get(key)
        elif (
            isinstance(payload, list)
            and key.isascii()
            and key.isdigit()
            and int(key) < len(payload)
        ):
            payload = payload[int(key)]
        else:
            return None
    return payload


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
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, None


async def submit(
    db: Any, config: dict[str, str], mobile: str, otp: str, reference: str
) -> dict[str, Any]:
    if len(otp) != 4 or not otp.isascii() or not otp.isdigit():
        raise ValidationError("Airtel OTP must contain exactly four numeric digits.")
    if len(mobile) != 10 or not mobile.isascii() or not mobile.isdigit():
        raise ValidationError("Use the registered ten-digit mobile number.")
    config = validate_config(
        {k: v for k, v in config.items() if k not in {"provider", "_provider"}}
    )
    if not confirmed_contract(config):
        return {"success": False, "status": "unconfigured", "error": BLOCKED}
    key = hashlib.sha256(
        (reference + ":" + json.dumps(config, sort_keys=True)).encode()
    ).hexdigest()
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
        }
    body = {
        "customerId": config.get("customer_id", ""),
        "destinationAddress": json.loads(
            config["destination_template"].replace("{{mobile}}", mobile)
        ),
        "dltTemplateId": config["dlt_template_id"],
        "entityId": config["entity_id"],
        "message": APPROVED_MESSAGE.replace("{#numeric#}", otp),
        "messageType": config["message_type"],
        "sourceAddress": config["sender_id"],
    }
    status = "unknown"
    code = None
    started = perf_counter()
    try:
        code, payload = await request(body, config["authorization_value"])
        expected = json.loads(config["success_value"])
        actual = field(payload, config["success_field"])
        accepted = 200 <= code < 300 and type(actual) is type(expected) and actual == expected
        status = "accepted" if accepted else "rejected" if code >= 400 else "unknown"
    except httpx.HTTPError:
        # Never persist exception text, request body, authentication or provider payload.
        status = "unknown"
    await db.sms_submissions.update_one(
        {"_id": key},
        {
            "$set": {
                "status": status,
                "http_status": code,
                "response_time_ms": round((perf_counter() - started) * 1000),
                "updated_at": utc_now(),
            }
        },
    )
    return {
        "success": status == "accepted",
        "status": status,
        "error": None
        if status == "accepted"
        else "SMS submission was not confirmed. No automatic retry was performed.",
    }
