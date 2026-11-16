"""Owner-only integration OTP receipt proof; no customer login/session side effects."""

import hmac
import json
import secrets
from datetime import timedelta
from time import perf_counter
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import ConflictError, ValidationError
from app.features.auth.pin_service import digest, limit, otp_digest
from app.features.communication.airtel_iq import submit
from app.features.integrations.airtel_iq import config_fingerprint, require_owner, require_validated
from app.features.integrations.models import IntegrationTestLog
from app.security.encryption import decrypt
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now


async def send_test(service: Any, config_id: str, payload: Any, actor: Any) -> dict[str, Any]:
    require_owner(actor)
    config = await service.get_config(config_id)
    if config.provider != "airtel_iq":
        raise ValidationError("Select an Airtel SMS configuration.")
    values = json.loads(decrypt(config.config_encrypted))
    require_validated(config, values)
    if not config.is_enabled:
        raise ValidationError("Enable this integration before sending a test SMS.")
    if not payload.confirm_send:
        raise ValidationError("Explicitly authorize the test SMS first.")
    await limit(service._db, "airtel-test-send:" + actor.require_id(), 5, 600)
    challenge = digest("airtel-test:" + config_id + ":" + payload.request_id)
    now = utc_now()
    otp = str(secrets.randbelow(10000)).zfill(4)
    row = {
        "_id": challenge,
        "config_id": config_id,
        "actor_id": actor.require_id(),
        "mobile_digest": otp_digest(challenge, payload.mobile),
        "otp_hash": otp_digest(challenge, otp),
        "fingerprint": config_fingerprint(values),
        "expires_at": now + timedelta(minutes=10),
        "used": False,
        "attempts": 0,
        "status": "sending",
        "created_at": now,
    }
    try:
        await service._db.integration_airtel_test_otps.insert_one(row)
    except DuplicateKeyError:
        raise ConflictError(
            "This test submission is already recorded. Check its result; it was not sent again."
        ) from None
    claimed = await service._db.integration_configs.update_one(
        {
            "_id": ObjectId(config_id),
            "config_encrypted": config.config_encrypted,
            "is_enabled": True,
            "is_deleted": False,
        },
        {
            "$set": {
                "airtel_test_challenge_id": challenge,
                "airtel_test_verified_at": None,
                "airtel_last_submission_status": "sending",
                "is_active": False,
            }
        },
    )
    if not claimed.matched_count:
        raise ConflictError("Configuration changed. Reload before sending.")
    started = perf_counter()
    outcome = await submit(
        service._db,
        values,
        payload.mobile,
        otp,
        "admin-test:" + config_id + ":" + payload.request_id,
    )
    elapsed = round((perf_counter() - started) * 1000)
    await service._db.integration_airtel_test_otps.update_one(
        {"_id": challenge}, {"$set": {"status": outcome["status"]}}
    )
    now = utc_now()
    await service._db.integration_configs.update_one(
        {
            "_id": ObjectId(config_id),
            "config_encrypted": config.config_encrypted,
            "airtel_test_challenge_id": challenge,
            "is_enabled": True,
            "is_deleted": False,
        },
        {
            "$set": {
                "airtel_last_submission_status": outcome["status"],
                "last_tested_at": now,
                "last_success_at": now if outcome["success"] else None,
                "last_failure_at": None if outcome["success"] else now,
                "last_error_message": outcome["error"],
                "health_status": "warning" if outcome["success"] else "error",
                "updated_at": now,
                "updated_by": actor.require_id(),
            }
        },
    )
    await service._test_logs.insert(
        IntegrationTestLog(
            kind="sms_submission",
            submission_status=outcome["status"],
            diagnostics=outcome.get("diagnostics"),
            config_id=config_id,
            integration_type="sms",
            provider="airtel_iq",
            success=outcome["success"],
            response_time_ms=elapsed,
            error_message=outcome["error"],
            tested_at=now,
            created_by=actor.require_id(),
        )
    )
    await write_audit_log(
        service._db,
        event_type="airtel_test_submission",
        user_id=actor.require_id(),
        metadata={"config_id": config_id, "status": outcome["status"]},
    )
    return outcome | {
        "challenge_id": challenge if outcome["success"] else None,
        "expires_in": 600 if outcome["success"] else None,
        "response_time_ms": elapsed,
    }


async def verify_test(service: Any, config_id: str, payload: Any, actor: Any) -> dict[str, bool]:
    require_owner(actor)
    config = await service.get_config(config_id)
    if config.provider != "airtel_iq" or not config.is_enabled:
        raise ValidationError("Enable the Airtel integration first.")
    values = json.loads(decrypt(config.config_encrypted))
    require_validated(config, values)
    await limit(service._db, "airtel-test-verify:" + actor.require_id(), 30, 600)
    row = await service._db.integration_airtel_test_otps.find_one_and_update(
        {
            "_id": payload.challenge_id,
            "config_id": config_id,
            "actor_id": actor.require_id(),
            "used": False,
            "status": "accepted",
            "attempts": {"$lt": 5},
            "expires_at": {"$gt": utc_now()},
        },
        {"$inc": {"attempts": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if (
        not row
        or not hmac.compare_digest(
            row["mobile_digest"], otp_digest(payload.challenge_id, payload.mobile)
        )
        or not hmac.compare_digest(row["otp_hash"], otp_digest(payload.challenge_id, payload.otp))
    ):
        raise ValidationError(
            "Invalid, expired or already-used test OTP. Check the requested test mobile and code."
        )
    if (
        row["fingerprint"] != config_fingerprint(values)
        or config.airtel_test_challenge_id != payload.challenge_id
    ):
        raise ConflictError("The settings or latest test changed. Verify the current test only.")
    consumed = await service._db.integration_airtel_test_otps.update_one(
        {
            "_id": row["_id"],
            "used": False,
            "attempts": row["attempts"],
            "expires_at": {"$gt": utc_now()},
        },
        {"$set": {"used": True, "verified_at": utc_now()}},
    )
    if not consumed.modified_count:
        raise ConflictError("This test OTP was already used or changed.")
    now = utc_now()
    updated = await service._db.integration_configs.update_one(
        {
            "_id": ObjectId(config_id),
            "config_encrypted": config.config_encrypted,
            "airtel_test_challenge_id": payload.challenge_id,
            "is_enabled": True,
            "is_deleted": False,
        },
        {
            "$set": {
                "airtel_test_verified_at": now,
                "health_status": "healthy",
                "updated_at": now,
                "updated_by": actor.require_id(),
            }
        },
    )
    if not updated.matched_count:
        raise ConflictError("Configuration changed. Verification did not activate it.")
    await service._test_logs.insert(
        IntegrationTestLog(
            kind="otp_verification",
            config_id=config_id,
            integration_type="sms",
            provider="airtel_iq",
            success=True,
            response_time_ms=0,
            tested_at=now,
            created_by=actor.require_id(),
        )
    )
    await write_audit_log(
        service._db,
        event_type="airtel_test_otp_verified",
        user_id=actor.require_id(),
        metadata={"config_id": config_id},
    )
    return {"verified": True}
