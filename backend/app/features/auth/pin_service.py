"""PIN authentication composes AuthService sessions; durable single-use OTP state."""

import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from typing import Any, Literal, Self

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.config.settings import get_settings
from app.core.exceptions import (
    ConflictError,
    RateLimitedError,
    UnauthorizedError,
    ValidationError,
)
from app.features.auth.models import User
from app.features.communication.airtel_iq import submit
from app.features.geo_fencing.constants import GeoActivity
from app.features.geo_fencing.enforcement import enforce_geo_fence
from app.security.encryption import decrypt
from app.security.pin import hash_pin, verify_pin
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now

Purpose = Literal["FIRST_TIME_LOGIN", "FORGOT_PIN", "REGISTRATION"]


class Start(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mobile: str = Field(pattern=r"^[0-9]{10}$")
    purpose: Purpose


class Verify(Start):
    challenge_id: str = Field(min_length=32, max_length=100)
    otp: str = Field(pattern=r"^[0-9]{4}$", repr=False)


class Complete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    authorization: str = Field(min_length=32, max_length=100, repr=False)
    pin: str = Field(pattern=r"^[0-9]{4}$", repr=False)
    confirm_pin: str = Field(pattern=r"^[0-9]{4}$", repr=False)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def matching(self) -> Self:
        if self.pin != self.confirm_pin:
            raise ValueError("PIN confirmation does not match.")
        return self


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mobile: str = Field(pattern=r"^[0-9]{10}$")
    pin: str = Field(pattern=r"^[0-9]{4}$", repr=False)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


async def policy(db: Any) -> str:
    doc = await db.auth_login_policy.find_one({"_id": "default"})
    return str((doc or {}).get("mode", "enrollment"))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def otp_digest(challenge: str, otp: str) -> str:
    return hmac.new(
        get_settings().jwt_secret_key.encode(), (challenge + ":" + otp).encode(), hashlib.sha256
    ).hexdigest()


async def limit(db: Any, key: str, maximum: int, seconds: int) -> None:
    now = utc_now()
    slot = digest(key + ":" + str(int(now.timestamp()) // seconds))
    update = {
        "$inc": {"count": 1},
        "$setOnInsert": {"expires_at": now + timedelta(seconds=seconds * 2)},
    }
    try:
        row = await db.auth_pin_limits.find_one_and_update(
            {"_id": slot}, update, upsert=True, return_document=ReturnDocument.AFTER
        )
    except DuplicateKeyError:
        # Another worker inserted this time bucket first. Count this attempt too.
        row = await db.auth_pin_limits.find_one_and_update(
            {"_id": slot}, update, return_document=ReturnDocument.AFTER
        )
    if row is None:
        raise RateLimitedError("Please wait before trying again.")
    if row["count"] > maximum:
        raise RateLimitedError("Too many attempts. Please wait before trying again.")


class PinService:
    def __init__(self, auth: Any):
        self.auth = auth
        self.db = auth._db

    async def account(self, mobile: str) -> dict[str, Any] | None:
        row = await self.db.users.find_one(
            {
                "role": "customer",
                "mobile": mobile,
                "is_deleted": False,
                "status": {"$in": ["active", "pending_password"]},
            }
        )

        return dict(row) if row else None

    async def start(self, body: Start, ctx: Any) -> dict[str, Any]:
        await limit(self.db, "pin-otp-ip:" + str(ctx.ip_address), 10, 600)
        await limit(self.db, "pin-otp-mobile:" + body.mobile, 5, 3600)
        user = await self.account(body.mobile)
        eligible = bool(
            user
            and (
                (body.purpose == "FIRST_TIME_LOGIN" and not user.get("pin_hash"))
                or (body.purpose == "FORGOT_PIN" and user.get("pin_hash"))
            )
        )
        if body.purpose == "REGISTRATION":
            # Registration creates no User until the OTP is verified and completed.
            existing = await self.db.users.find_one({"mobile": body.mobile})
            if existing:
                raise ConflictError("This mobile is already registered. Log in or use Create PIN.")
            eligible = True
        if user:
            await limit(self.db, "pin-otp-account:" + str(user["_id"]), 5, 3600)
        now = utc_now()
        challenge = secrets.token_urlsafe(32)
        otp = str(secrets.randbelow(10000)).zfill(4)
        slot = digest(body.mobile + ":" + body.purpose)
        data = {
            "challenge_id": challenge,
            "mobile": body.mobile,
            "purpose": body.purpose,
            "user_id": str(user["_id"]) if eligible and user else None,
            "base_epoch": (user or {}).get("pin_epoch", 0),
            "otp_hash": otp_digest(challenge, otp),
            "attempts": 0,
            "state": "sending",
            "expires_at": now + timedelta(minutes=10),
            "next_send_at": now + timedelta(seconds=60),
            "created_at": now,
        }
        claimed = await self.db.auth_pin_challenges.find_one_and_update(
            {"_id": slot, "next_send_at": {"$lte": now}},
            {
                "$set": data,
                "$unset": {
                    "authorization_hash": "",
                    "authorization_expires_at": "",
                    "verified_at": "",
                    "used_otp_hash": "",
                },
            },
            return_document=ReturnDocument.AFTER,
        )
        if not claimed:
            try:
                await self.db.auth_pin_challenges.insert_one({"_id": slot, **data})
            except DuplicateKeyError:
                raise RateLimitedError("Wait 60 seconds before requesting another code.") from None
        delivered = False
        if eligible:
            config = await self.db.integration_configs.find_one(
                {
                    "integration_type": "sms",
                    "provider": "airtel_iq",
                    "is_enabled": True,
                    "is_active": True,
                    "is_deleted": False,
                }
            )
            if config:
                values = json.loads(decrypt(config["config_encrypted"]))
                result = await submit(self.db, values, body.mobile, otp, "otp:" + challenge)
                delivered = result["success"]
        await self.db.auth_pin_challenges.update_one(
            {"_id": slot, "challenge_id": challenge},
            {"$set": {"state": "issued" if delivered else "failed"}},
        )
        if body.purpose == "REGISTRATION" and not delivered:
            raise ValidationError("OTP submission was not confirmed. Wait before trying again; contact support if no code arrives.")
        # Same shape for unknown/ineligible/undelivered requests. No account enumeration.
        return {
            "challenge_id": challenge,
            "masked_mobile": "******" + body.mobile[-4:],
            "expires_in": 600,
            "resend_after": 60,
            "message": "OTP submitted. Check your mobile for the code." if body.purpose == "REGISTRATION" else "If the account is eligible and SMS is configured, a code will arrive. If none arrives, contact your administrator.",
        }

    async def verify(self, body: Verify, ctx: Any) -> dict[str, str]:
        await limit(self.db, "pin-verify-ip:" + str(ctx.ip_address), 30, 600)
        now = utc_now()
        slot = digest(body.mobile + ":" + body.purpose)
        doc = await self.db.auth_pin_challenges.find_one_and_update(
            {
                "_id": slot,
                "challenge_id": body.challenge_id,
                "purpose": body.purpose,
                "state": "issued",
                "expires_at": {"$gt": now},
                "attempts": {"$lt": 5},
            },
            {"$inc": {"attempts": 1}},
            return_document=ReturnDocument.AFTER,
        )
        account = await self.account(body.mobile)
        registration = body.purpose == "REGISTRATION"
        if (
            not doc
            or (not registration and (not account or str(account["_id"]) != doc.get("user_id")))
            or not hmac.compare_digest(doc["otp_hash"], otp_digest(body.challenge_id, body.otp))
        ):
            raise ValidationError(
                "Invalid, expired or exhausted OTP. Request a new code if needed."
            )
        token = secrets.token_urlsafe(32)
        used = await self.db.auth_pin_challenges.update_one(
            {
                "_id": slot,
                "challenge_id": body.challenge_id,
                "state": "issued",
                "expires_at": {"$gt": now},
            },
            {
                "$set": {
                    "state": "verified",
                    "authorization_hash": digest(token),
                    "authorization_expires_at": now + timedelta(minutes=5),
                    "verified_at": now,
                    "used_otp_hash": doc["otp_hash"],
                },
                "$unset": {"otp_hash": ""},
            },
        )
        if not used.modified_count:
            raise ValidationError("This code was already used. Request another code.")
        return {"authorization": token, "purpose": body.purpose}

    async def complete(self, body: Complete, ctx: Any) -> Any:
        await limit(self.db, "pin-complete-ip:" + str(ctx.ip_address), 20, 600)
        now = utc_now()
        proof = await self.db.auth_pin_challenges.find_one(
            {
                "authorization_hash": digest(body.authorization),
                "state": "verified",
                "authorization_expires_at": {"$gt": now},
            }
        )
        user = (
            await self.db.users.find_one(
                {
                    "_id": ObjectId(proof["user_id"]),
                    "role": "customer",
                    "is_deleted": False,
                    "status": {"$in": ["active", "pending_password"]},
                }
            )
            if proof and proof.get("user_id")
            else None
        )
        if not proof or not user or user.get("pin_epoch", 0) != proof["base_epoch"]:
            raise UnauthorizedError("PIN authorization is invalid or expired.")
        if hmac.compare_digest(
            proof.get("used_otp_hash", ""), otp_digest(proof["challenge_id"], body.pin)
        ):
            raise ValidationError("Choose a PIN different from the verification code.")
        if user.get("pin_hash") and verify_pin(body.pin, user["pin_hash"]):
            raise ValidationError("Choose a PIN different from your previous PIN.")
        initial = proof["purpose"] == "FIRST_TIME_LOGIN"
        if initial:
            await enforce_geo_fence(
                self.db,
                actor=User.model_validate(user),
                activity=GeoActivity.LOGIN,
                latitude=body.latitude,
                longitude=body.longitude,
            )
        if bool(user.get("pin_hash")) == initial:
            raise ConflictError("Account setup changed. Request a new verification.")
        claimed = await self.db.auth_pin_challenges.update_one(
            {
                "_id": proof["_id"],
                "authorization_hash": digest(body.authorization),
                "state": "verified",
                "authorization_expires_at": {"$gt": now},
            },
            {"$set": {"state": "consumed"}, "$unset": {"authorization_hash": ""}},
        )
        if not claimed.modified_count:
            raise UnauthorizedError("PIN authorization was already used.")
        hashed = hash_pin(body.pin)
        changed = await self.db.users.find_one_and_update(
            {
                "_id": user["_id"],
                "role": "customer",
                "pin_hash": user.get("pin_hash"),
                "status": user["status"],
                "is_deleted": False,
                "$or": [{"pin_epoch": proof["base_epoch"]}, {"pin_epoch": {"$exists": False}}],
            },
            {
                "$set": {
                    "pin_hash": hashed,
                    "pin_updated_at": now,
                    "mobile_verified_at": now,
                    "is_mobile_verified": True,
                    "must_change_password": False,
                    "status": "active",
                    "failed_pin_attempts": 0,
                    "pin_locked_until": None,
                },
                "$inc": {"pin_epoch": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        if not changed:
            raise ConflictError("Account changed. Request a new verification.")
        await self.auth.revoke_all_sessions_for_user(str(user["_id"]))
        await write_audit_log(
            self.db,
            event_type="pin_configured" if initial else "pin_reset",
            user_id=str(user["_id"]),
        )
        if initial:
            return await self.auth.issue_session(
                user=User.model_validate(changed), ctx=ctx, login_method="pin"
            )
        return {"message": "PIN reset. Return to login and use your new PIN."}

    async def login(self, body: Login, ctx: Any) -> Any:
        await limit(self.db, "pin-login-ip:" + str(ctx.ip_address), 20, 60)
        await limit(self.db, "pin-login-mobile:" + body.mobile, 10, 900)
        now = utc_now()
        await self.db.users.update_one(
            {"mobile": body.mobile, "role": "customer", "pin_locked_until": {"$lte": now}},
            {"$set": {"failed_pin_attempts": 0, "pin_locked_until": None}},
        )
        user = await self.db.users.find_one_and_update(
            {
                "mobile": body.mobile,
                "role": "customer",
                "status": "active",
                "is_deleted": False,
                "pin_hash": {"$type": "string"},
                "$and": [
                    {"$or": [{"pin_locked_until": None}, {"pin_locked_until": {"$lte": now}}]},
                    {
                        "$or": [
                            {"failed_pin_attempts": {"$lt": 5}},
                            {"pin_locked_until": {"$lte": now}},
                        ]
                    },
                ],
            },
            [
                {
                    "$set": {
                        "failed_pin_attempts": {
                            "$add": [{"$ifNull": ["$failed_pin_attempts", 0]}, 1]
                        }
                    }
                },
                {
                    "$set": {
                        "pin_locked_until": {
                            "$cond": [
                                {"$gte": ["$failed_pin_attempts", 5]},
                                now + timedelta(minutes=15),
                                None,
                            ]
                        }
                    }
                },
            ],
            return_document=ReturnDocument.AFTER,
        )
        if not user or not verify_pin(body.pin, user["pin_hash"]):
            await write_audit_log(
                self.db,
                event_type="pin_login_failed",
                metadata={"mobile_hash": digest(body.mobile)},
            )
            raise UnauthorizedError(
                "Invalid mobile/PIN, unavailable PIN or temporary lock. Try later or use PIN recovery."
            )
        fresh = await self.db.users.find_one_and_update(
            {
                "_id": user["_id"],
                "role": "customer",
                "pin_hash": user["pin_hash"],
                "status": "active",
                "is_deleted": False,
            },
            {"$set": {
                "failed_pin_attempts": 0, "pin_locked_until": None,
                "pin_hash": hash_pin(body.pin) if user["pin_hash"].startswith("$2") else user["pin_hash"],
            }},
            return_document=ReturnDocument.AFTER,
        )
        if not fresh:
            raise UnauthorizedError("Account changed. Please log in again.")
        await enforce_geo_fence(
            self.db,
            actor=User.model_validate(fresh),
            activity=GeoActivity.LOGIN,
            latitude=body.latitude,
            longitude=body.longitude,
        )
        return await self.auth.issue_session(
            user=User.model_validate(fresh), ctx=ctx, login_method="pin"
        )
