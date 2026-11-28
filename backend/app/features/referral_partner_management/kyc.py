"""Private, versioned Partner KYC using existing encryption, S3 and audit primitives."""

import hashlib
import json
import math
import re
import secrets
from datetime import date, timedelta
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument

from app.config.storage import get_storage_config
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.features.referral_partner_management.portal_models import (
    PROTECTED_FIELDS,
    KycConfiguration,
)
from app.security.encryption import decrypt, decrypt_bytes, encrypt, encrypt_bytes
from app.services.storage.client import generate_presigned_upload_url, get_s3_client
from app.shared.audit_log import AuditLog
from app.utils.datetime import to_ist, utc_now

FILE_KINDS = {"file", "image", "pdf", "signature"}


def oid(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise NotFoundError("Record not found.")
    return ObjectId(value)


def public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        ("id" if k == "_id" else k): str(v) if k == "_id" else v
        for k, v in row.items()
        if not k.endswith("_cipher")
        and k not in {"s3_key", "ticket_hash", "token_hash", "fingerprint"}
    }


async def event(
    db: Any,
    actor: Any,
    name: str,
    partner_id: str,
    *,
    session: Any,
    detail: dict[str, Any] | None = None,
) -> None:
    audit = AuditLog(
        event_type=name,
        user_id=actor.require_id(),
        metadata={"partner_id": partner_id, **(detail or {})},
    )
    await db.audit_logs.insert_one(audit.model_dump(exclude={"id"}), session=session)
    from app.features.referral_partner_management.notifications import notify

    await notify(db, actor, name, partner_id, session)


class PartnerKyc:
    def __init__(self, db: Any):
        self.db = db

    async def partner(self, actor: Any, partner_id: str | None = None) -> dict[str, Any]:
        if actor.role == "owner" and partner_id:
            query = {"_id": oid(partner_id)}
        elif actor.role == "referral_partner" and not actor.must_change_password:
            query = {"user_id": actor.require_id()}
        else:
            raise ForbiddenError(
                "Partner or Owner access required. Complete any required password change first."
            )
        row = await self.db.referral_partners.find_one({**query, "is_deleted": False})
        if not row or (actor.role != "owner" and partner_id and str(row["_id"]) != partner_id):
            raise NotFoundError("Partner not found.")
        return dict(row)

    async def guard(self, partner: dict[str, Any], session: Any) -> None:
        result = await self.db.referral_partners.update_one(
            {"_id": partner["_id"], "version": partner["version"]},
            {"$inc": {"kyc_guard": 1, "version": 1}},
            session=session,
        )
        if not result.matched_count:
            raise ConflictError("Partner changed; reload before continuing.")

    async def configuration(self, version: int | None = None) -> dict[str, Any]:
        query = {"version": version} if version else {}
        row = await self.db.partner_kyc_forms.find_one(query, sort=[("version", -1)])
        if row:
            return {k: row[k] for k in KycConfiguration.model_fields}
        if version and version != 1:
            raise NotFoundError("KYC form version not found.")
        initial = {
            "version": 1,
            "fields": [f.model_dump() for f in PROTECTED_FIELDS],
            "aadhaar_format": "either",
            "required_agreement_ids": [],
            "retention_days": 365,
        }
        stored = await self.db.partner_kyc_forms.find_one_and_update(
            {"_id": ObjectId("000000000000000000000101")},
            {"$setOnInsert": initial},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return {k: stored[k] for k in KycConfiguration.model_fields}

    async def publish(self, payload: Any, actor: Any) -> dict[str, Any]:
        if actor.role != "owner":
            raise ForbiddenError("Only Owner can publish KYC configuration.")
        current = await self.configuration()
        if payload.version != current["version"]:
            raise ConflictError("KYC configuration changed; reload.")
        fields = {f.key: f for f in payload.fields}
        if len(fields) != len(payload.fields):
            raise ValidationError("Field keys must be unique.")
        for protected in PROTECTED_FIELDS:
            f = fields.get(protected.key)
            if (
                not f
                or not f.required
                or f.hidden
                or f.kind != protected.kind
                or (f.condition_key, f.condition_value)
                != (protected.condition_key, protected.condition_value)
                or f.options != protected.options
            ):
                raise ValidationError(
                    "Protected identity, financial and conditional controls cannot be removed, hidden or weakened."
                )
        for f in payload.fields:
            if f.condition_key and f.condition_key not in fields:
                raise ValidationError("Conditional field references an unknown field.")
        if not payload.required_agreement_ids:
            raise ValidationError(
                "At least one required Partner agreement version must remain enabled."
            )
        for agreement_id in payload.required_agreement_ids:
            if not await self.db.partner_kyc_documents.find_one(
                {"_id": oid(agreement_id), "partner_id": "agreement", "status": "available"}
            ):
                raise ValidationError("Required agreement version is unavailable.")
        row = {
            **payload.model_dump(),
            "version": payload.version + 1,
            "created_at": utc_now(),
            "created_by": actor.require_id(),
        }
        async with await self.db.client.start_session() as session, session.start_transaction():
            # Shared singleton guard makes concurrent publishes conflict without retries.
            await self.db.counters.update_one(
                {"_id": "partner_kyc_publish"}, {"$inc": {"epoch": 1}}, upsert=True, session=session
            )
            latest = await self.db.partner_kyc_forms.find_one(
                {}, sort=[("version", -1)], session=session
            )
            if latest and latest["version"] != payload.version:
                raise ConflictError("KYC configuration changed; reload.")
            await self.db.partner_kyc_forms.insert_one(row, session=session)
            await event(
                self.db,
                actor,
                "partner_kyc_form_published",
                "configuration",
                session=session,
                detail={"form_version": row["version"]},
            )
        return {k: row[k] for k in KycConfiguration.model_fields}

    async def state(
        self, actor: Any, partner_id: str | None = None, *, document_page: int = 1
    ) -> dict[str, Any]:
        if document_page < 1 or document_page > 100000:
            raise ValidationError("Invalid document history page.")
        partner = await self.partner(actor, partner_id)
        pid = str(partner["_id"])
        latest = await self.db.partner_kyc_submissions.find_one(
            {"partner_id": pid}, sort=[("created_at", -1)]
        )
        documents = [
            public(d)
            async for d in self.db.partner_kyc_documents.find({"partner_id": pid})
            .sort("created_at", -1)
            .skip((document_page - 1) * 20)
            .limit(20)
        ]
        values = json.loads(decrypt(latest["values_cipher"])) if latest else {}
        for key in ("pan_number", "account_number"):
            if values.get(key):
                values[key] = "*" * max(0, len(values[key]) - 4) + values[key][-4:]
        current_config = await self.configuration()
        new_terms = bool(
            latest
            and latest["status"] in {"approved", "reupload_required", "rejected"}
            and not set(current_config["required_agreement_ids"]).issubset(
                latest.get("accepted_agreement_ids", [])
            )
        )
        config = await self.configuration(
            latest["form_version"] if latest and not new_terms else None
        )
        present_documents = {
            (d["category"], d["part"])
            async for d in self.db.partner_kyc_documents.find(
                {"partner_id": pid, "current": True, "status": {"$in": ["pending", "approved"]}},
                {"category": 1, "part": 1},
            )
        }
        required, completed = 0, 0
        for field in config["fields"]:
            if (
                not field["required"]
                or field["hidden"]
                or (
                    field.get("condition_key")
                    and values.get(field["condition_key"]) != field["condition_value"]
                )
            ):
                continue
            if field["kind"] in FILE_KINDS:
                parts = (
                    ["front", "back"]
                    if field["key"] == "aadhaar" and values.get("aadhaar_type") == "images"
                    else ["file"]
                )
                required += len(parts)
                completed += sum((field["key"], part) in present_documents for part in parts)
            else:
                required += 1
                completed += bool(values.get(field["key"]))
        required += 1 + len(config["required_agreement_ids"])
        completed += int(bool(latest and latest.get("consent"))) + len(
            set(config["required_agreement_ids"])
            & set(latest.get("accepted_agreement_ids", []) if latest else [])
        )
        return {
            "completion": {
                "completed": completed,
                "required": required,
                "percent": int(completed * 100 / required) if required else 0,
            },
            "document_page": document_page,
            "documents_total": await self.db.partner_kyc_documents.count_documents(
                {"partner_id": pid}
            ),
            "requires_agreement_acceptance": new_terms,
            "partner": {
                "account_active": True,
                "kyc_status": "pending",
                "submission_mode": "partner_review",
                "applicable_product_ids": [],
                "restrictions": "",
                **public(partner),
            },
            "submission": public(latest) if latest else None,
            "values": values,
            "documents": documents,
            "configuration": config,
        }

    async def draft(self, payload: Any, actor: Any) -> dict[str, Any]:
        partner = await self.partner(actor)
        if not partner.get("account_active", True):
            raise ForbiddenError("Partner account suspended.")
        pid = str(partner["_id"])
        config = await self.configuration(payload.form_version)
        latest = await self.db.partner_kyc_submissions.find_one(
            {"partner_id": pid}, sort=[("created_at", -1)]
        )
        if latest and latest["status"] in {"submitted", "under_review"}:
            raise ConflictError("Submitted KYC is locked for review.")
        if latest and latest["status"] == "draft" and latest["version"] != payload.version:
            raise ConflictError("KYC draft changed; reload.")
        if latest and latest["status"] == "approved":
            current = await self.configuration()
            if set(current["required_agreement_ids"]).issubset(
                latest.get("accepted_agreement_ids", [])
            ):
                raise ConflictError(
                    "Approved KYC is locked. Owner must request a reviewed correction."
                )
            if payload.form_version != current["version"]:
                raise ConflictError("Accept the current agreement and form version.")
        values = dict(payload.values)
        if len(json.dumps(values).encode()) > 100000:
            raise ValidationError("KYC field data exceeds the supported draft size.")
        if any(
            value is not None
            and (
                not isinstance(value, (str, int, float, bool))
                or isinstance(value, float)
                and not math.isfinite(value)
            )
            for value in values.values()
        ):
            raise ValidationError("Use scalar values for KYC fields.")
        if "aadhaar_number" in values:
            raise ValidationError("Do not collect a full Aadhaar number.")
        allowed = {f["key"] for f in config["fields"]} | {"email", "gender", "same_address"}
        if set(values) - allowed:
            raise ValidationError("Unknown KYC field.")
        previous = json.loads(decrypt(latest["values_cipher"])) if latest else {}
        for key in ("pan_number", "account_number"):
            if str(values.get(key, "")).startswith("*"):
                values[key] = previous.get(key, "")
        if (
            values.get("account_number")
            and values.get("account_number") != previous.get("account_number")
            and values.get("account_number") != payload.confirm_account_number
        ):
            raise ValidationError("Bank account confirmation does not match.")
        if values.get("same_address"):
            values["permanent_address"] = values.get("current_address", "")
        row = {
            "partner_id": pid,
            "identity_snapshot": {"full_name": partner["full_name"], "mobile": partner["mobile"]},
            "form_version": payload.form_version,
            "values_cipher": encrypt(json.dumps(values)),
            "consent": payload.consent,
            "accepted_agreement_ids": payload.accepted_agreement_ids,
            "status": "draft",
            "version": payload.version + 1,
            "updated_at": utc_now(),
        }
        async with await self.db.client.start_session() as session, session.start_transaction():
            await self.guard(partner, session)
            if latest and latest["status"] == "draft":
                result = await self.db.partner_kyc_submissions.update_one(
                    {"_id": latest["_id"], "version": payload.version, "status": "draft"},
                    {"$set": row},
                    session=session,
                )
                if not result.matched_count:
                    raise ConflictError("Draft changed; reload.")
            else:
                row.update(
                    {"version": 1, "created_at": utc_now(), "created_by": actor.require_id()}
                )
                await self.db.partner_kyc_submissions.insert_one(row, session=session)
                if latest and latest["status"] == "approved":
                    await self.db.referral_partners.update_one(
                        {"_id": partner["_id"]},
                        {"$set": {"kyc_status": "pending"}},
                        session=session,
                    )
                    await event(
                        self.db,
                        actor,
                        "partner_kyc_revision_started",
                        pid,
                        session=session,
                        detail={
                            "form_version": payload.form_version,
                            "previous_submission_id": str(latest["_id"]),
                        },
                    )
        return await self.state(actor)

    async def submit(self, version: int, actor: Any) -> dict[str, Any]:
        partner = await self.partner(actor)
        if not partner.get("account_active", True):
            raise ForbiddenError("Partner account suspended.")
        pid = str(partner["_id"])
        row = await self.db.partner_kyc_submissions.find_one(
            {"partner_id": pid}, sort=[("created_at", -1)]
        )
        if not row or row["status"] != "draft" or row["version"] != version:
            raise ConflictError("Save and reload the current KYC draft before submission.")
        config = await self.configuration(row["form_version"])
        values = json.loads(decrypt(row["values_cipher"]))
        errors = []
        file_keys = [
            field["key"]
            for field in config["fields"]
            if field["kind"] in FILE_KINDS
            and not field["hidden"]
            and (
                not field.get("condition_key")
                or values.get(field["condition_key"]) == field["condition_value"]
            )
        ]
        current_files = [
            document
            async for document in self.db.partner_kyc_documents.find(
                {
                    "partner_id": pid,
                    "category": {"$in": file_keys},
                    "current": True,
                    "status": {"$in": ["pending", "approved"]},
                }
            ).limit(301)
        ]
        if len(current_files) > 300:
            raise ValidationError("Current document versions require Owner review.")
        file_map = {
            (document["category"], document["part"]): document for document in current_files
        }
        if len(file_map) != len(current_files):
            raise ValidationError("Duplicate current document versions require Owner review.")
        selected_documents: set[str] = set()
        for f in config["fields"]:
            if f["hidden"] or (
                f.get("condition_key") and values.get(f["condition_key"]) != f["condition_value"]
            ):
                continue
            if f["kind"] in FILE_KINDS:
                parts = (
                    ["front", "back"]
                    if f["key"] == "aadhaar" and values.get("aadhaar_type") == "images"
                    else ["file"]
                )
                for part in parts:
                    document = file_map.get((f["key"], part))
                    if f["required"] and not document:
                        errors.append(f["label"] + " upload required")
                    if document:
                        size = document.get("size")
                        if (
                            document.get("content_type") not in f["mime_types"]
                            or not isinstance(size, int)
                            or not 0 < size <= f["max_size_mb"] * 1024 * 1024
                        ):
                            errors.append(
                                f["label"]
                                + " must meet this form version's accepted file format and size"
                            )
                        selected_documents.add(str(document["_id"]))
            else:
                v = values.get(f["key"])
                if f["required"] and (v is None or v == "" or v is False):
                    errors.append(f["label"] + " required")
                if isinstance(v, str) and len(v) > f["max_length"]:
                    errors.append(f["label"] + " too long")
                if f["options"] and v and v not in f["options"]:
                    errors.append(f["label"] + " invalid option")
        from app.features.customer.field_validation import validate_form_data
        from app.features.customer.models import FieldValidation, FormFieldDefinition

        scalar_fields = []
        for f in config["fields"]:
            if (
                f["hidden"]
                or f["kind"] in FILE_KINDS
                or (
                    f.get("condition_key")
                    and values.get(f["condition_key"]) != f["condition_value"]
                )
            ):
                continue
            checks = dict(f.get("validation") or {})
            if f["kind"] in {"email", "mobile"}:
                checks["format"] = f["kind"]
            scalar_fields.append(
                FormFieldDefinition(
                    key=f["key"],
                    label=f["label"],
                    field_type={
                        "dropdown": "select",
                        "radio": "select",
                        "address": "textarea",
                        "email": "text",
                        "mobile": "text",
                    }.get(f["kind"], f["kind"]),
                    required=f["required"],
                    options=f["options"],
                    validation=FieldValidation(**checks),
                )
            )
        errors.extend(validate_form_data(scalar_fields, values))
        if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", str(values.get("pan_number", ""))):
            errors.append("Valid PAN required")
        if not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", str(values.get("ifsc", ""))):
            errors.append("Valid IFSC required")
        if not re.fullmatch(r"[0-9]{6,24}", str(values.get("account_number", ""))):
            errors.append("Valid bank account required")
        if not re.fullmatch(r"[6-9][0-9]{9}", str(values.get("bank_mobile", ""))):
            errors.append("Valid bank mobile required")
        try:
            if date.fromisoformat(values.get("date_of_birth", "")) >= to_ist(utc_now()).date():
                errors.append("Date of birth must be in the past")
        except (TypeError, ValueError):
            errors.append("Valid date of birth required")
        if (
            config["aadhaar_format"] != "either"
            and values.get("aadhaar_type") != config["aadhaar_format"]
        ):
            errors.append("Use the configured Aadhaar format")
        if not config["required_agreement_ids"]:
            errors.append("Owner must publish the required Partner agreement before KYC submission")
        if not row["consent"] or not set(config["required_agreement_ids"]).issubset(
            row["accepted_agreement_ids"]
        ):
            errors.append("Consent and current agreement acceptance required")
        for agreement_id in config["required_agreement_ids"]:
            if not await self.db.audit_logs.find_one(
                {
                    "event_type": "partner_kyc_document_viewed",
                    "user_id": actor.require_id(),
                    "metadata.document_id": agreement_id,
                }
            ):
                errors.append("Open every required agreement before acceptance")
        if values.get("email"):
            from pydantic import EmailStr, TypeAdapter

            try:
                TypeAdapter(EmailStr).validate_python(values["email"])
            except ValueError:
                errors.append("Valid email address required")
        if errors:
            raise ValidationError("; ".join(errors))
        documents = sorted(selected_documents)
        async with await self.db.client.start_session() as session, session.start_transaction():
            await self.guard(partner, session)
            result = await self.db.partner_kyc_submissions.update_one(
                {"_id": row["_id"], "version": version, "status": "draft"},
                {
                    "$set": {
                        "status": "submitted",
                        "submitted_at": utc_now(),
                        "document_ids": documents,
                        "accepted_at": utc_now(),
                    },
                    "$inc": {"version": 1},
                },
                session=session,
            )
            if not result.matched_count:
                raise ConflictError("KYC changed; reload.")
            await self.db.referral_partners.update_one(
                {"_id": partner["_id"], "account_active": {"$ne": False}},
                {
                    "$set": {"kyc_status": "submitted", "current_kyc_id": str(row["_id"])},
                    "$inc": {"version": 1},
                },
                session=session,
            )
            await event(
                self.db,
                actor,
                "partner_kyc_submitted",
                pid,
                session=session,
                detail={"submission_id": str(row["_id"]), "form_version": row["form_version"]},
            )
        return await self.state(actor)

    async def review(self, partner_id: str, payload: Any, actor: Any) -> dict[str, Any]:
        if actor.role != "owner":
            raise ForbiddenError("Only Owner can review KYC.")
        partner = await self.partner(actor, partner_id)
        row = await self.db.partner_kyc_submissions.find_one(
            {"partner_id": partner_id}, sort=[("created_at", -1)]
        )
        if (
            not row
            or row["status"] not in {"submitted", "under_review"}
            or row["version"] != payload.version
        ):
            raise ConflictError("KYC submission is not reviewable; reload.")
        if payload.decision in {"rejected", "reupload_required"} and not payload.reason.strip():
            raise ValidationError("A review reason is required.")
        if payload.decision == "approved":
            current_config = await self.configuration()
            if not set(current_config["required_agreement_ids"]).issubset(
                row.get("accepted_agreement_ids", [])
            ):
                raise ValidationError(
                    "Required agreement versions changed. Request re-upload and acceptance of the current terms before approval."
                )
            if not payload.fields_verified:
                raise ValidationError("Confirm that all required KYC fields have been reviewed.")
            for did in row["document_ids"]:
                if not await self.db.partner_kyc_documents.find_one(
                    {"_id": oid(did), "partner_id": partner_id, "status": "approved"}
                ):
                    raise ValidationError("All submitted documents must be approved first.")
        history = {
            "at": utc_now(),
            "actor_id": actor.require_id(),
            "decision": payload.decision,
            "reason": payload.reason,
        }
        async with await self.db.client.start_session() as session, session.start_transaction():
            await self.guard(partner, session)
            if payload.decision == "approved":
                for document_id in row["document_ids"]:
                    if not await self.db.partner_kyc_documents.find_one(
                        {
                            "_id": oid(document_id),
                            "partner_id": partner_id,
                            "status": "approved",
                            "current": True,
                        },
                        session=session,
                    ):
                        raise ConflictError("A submitted document changed; reload the KYC review.")
            result = await self.db.partner_kyc_submissions.update_one(
                {"_id": row["_id"], "version": payload.version},
                {
                    "$set": {"status": payload.decision},
                    "$inc": {"version": 1},
                    "$push": {"review_history": history},
                },
                session=session,
            )
            if not result.matched_count:
                raise ConflictError("Review changed; reload.")
            await self.db.referral_partners.update_one(
                {"_id": partner["_id"]},
                {"$set": {"kyc_status": payload.decision}, "$inc": {"version": 1}},
                session=session,
            )
            await event(
                self.db,
                actor,
                "partner_kyc_" + payload.decision,
                partner_id,
                session=session,
                detail={"submission_id": str(row["_id"])},
            )
        return await self.state(actor, partner_id)

    async def upload(self, payload: Any, actor: Any, *, agreement: bool = False) -> dict[str, Any]:
        field = None
        if agreement:
            if actor.role != "owner" or payload.content_type != "application/pdf":
                raise ForbiddenError("Owner agreement PDF required.")
            pid = "agreement"
        else:
            partner = await self.partner(actor)
            if not partner.get("account_active", True):
                raise ForbiddenError("Partner account suspended.")
            pid = str(partner["_id"])
            current = await self.db.partner_kyc_submissions.find_one(
                {"partner_id": pid}, sort=[("created_at", -1)]
            )
            if current and current["status"] in {"submitted", "under_review", "approved"}:
                raise ConflictError("KYC is locked. Save an authorized revision before uploading.")
            config = await self.configuration(
                current["form_version"]
                if current and current["status"] in {"draft", "reupload_required", "rejected"}
                else None
            )
            field = next(
                (
                    f
                    for f in config["fields"]
                    if f["key"] == payload.category and f["kind"] in FILE_KINDS and not f["hidden"]
                ),
                None,
            )
            if (
                not field
                or payload.content_type not in field["mime_types"]
                or payload.size > field["max_size_mb"] * 1024 * 1024
            ):
                raise ValidationError("File does not match the configured field limits.")
            if payload.category != "aadhaar" and payload.part != "file":
                raise ValidationError("Only Aadhaar has front/back parts.")
            if payload.category == "aadhaar" and (
                (payload.part == "file") != (payload.content_type == "application/pdf")
            ):
                raise ValidationError("Use a PDF or front/back images.")
        token = secrets.token_urlsafe(32)
        key = "partner-kyc/staging/" + secrets.token_hex(24)
        row = {
            "ticket_hash": hashlib.sha256(token.encode()).hexdigest(),
            "partner_id": pid,
            "user_id": actor.require_id(),
            "category": payload.category,
            "part": payload.part,
            "content_type": payload.content_type,
            "size": payload.size,
            "processed_limit": (field["max_size_mb"] if field is not None else 10) * 1024 * 1024,
            "form_version": config["version"] if not agreement else None,
            "retention_days": config["retention_days"] if not agreement else None,
            "s3_key": key,
            "expires_at": utc_now() + timedelta(minutes=10),
            "used": False,
        }
        await self.db.partner_kyc_uploads.insert_one(row)
        return {
            "ticket": token,
            "upload_url": generate_presigned_upload_url(
                key, content_type=payload.content_type, server_side_encryption="AES256"
            ),
            "expires_in": 300,
            "upload_headers": {"x-amz-server-side-encryption": "AES256"},
        }

    async def confirm(self, payload: Any, actor: Any) -> dict[str, Any]:
        ticket = await self.db.partner_kyc_uploads.find_one(
            {
                "ticket_hash": hashlib.sha256(payload.ticket.encode()).hexdigest(),
                "user_id": actor.require_id(),
                "used": False,
                "expires_at": {"$gt": utc_now()},
            }
        )
        if not ticket or not payload.consent:
            raise ValidationError("Valid upload ticket and informed document consent required.")
        if ticket["partner_id"] != "agreement":
            partner = await self.partner(actor)
            if str(partner["_id"]) != ticket["partner_id"] or not partner.get(
                "account_active", True
            ):
                raise ForbiddenError("Partner upload no longer permitted.")
            current = await self.db.partner_kyc_submissions.find_one(
                {"partner_id": ticket["partner_id"]}, sort=[("created_at", -1)]
            )
            if current and current["status"] in {"submitted", "under_review", "approved"}:
                raise ConflictError(
                    "Submitted or approved KYC is locked. Save an authorized new revision before replacing documents."
                )
        # Reuse the existing bounded PDF/image parser; password only lives in this call.
        from app.features.employee.hr_documents import materialize

        head = get_s3_client().head_object(
            Bucket=get_storage_config().bucket_name, Key=ticket["s3_key"]
        )
        if int(head["ContentLength"]) != ticket["size"]:
            raise ValidationError("Uploaded file size does not match the private upload ticket.")
        data, mime = materialize(ticket["s3_key"], ticket["content_type"], payload.pdf_password)
        from app.features.referral_partner_management.artifacts import harden

        data = harden(data, mime)
        if len(data) > ticket.get("processed_limit", 10 * 1024 * 1024):
            raise ValidationError("Processed file exceeds the upload allowance.")
        key = "partner-kyc/encrypted/" + secrets.token_hex(32)
        storage, bucket = get_s3_client(), get_storage_config().bucket_name
        storage.put_object(
            Bucket=bucket,
            Key=key,
            Body=encrypt_bytes(data),
            ContentType="application/octet-stream",
            ServerSideEncryption="AES256",
        )
        document = {
            "partner_id": ticket["partner_id"],
            "category": ticket["category"],
            "part": ticket["part"],
            "content_type": mime,
            "s3_key": key,
            "size": len(data),
            "current": True,
            "status": "available" if ticket["partner_id"] == "agreement" else "pending",
            "created_at": utc_now(),
            "created_by": actor.require_id(),
            "version": 1,
            "review_history": [],
            "consent_at": utc_now(),
            "form_version": ticket.get("form_version"),
            "retention_review_after": utc_now() + timedelta(days=ticket["retention_days"])
            if ticket.get("retention_days")
            else None,
        }
        try:
            async with await self.db.client.start_session() as session, session.start_transaction():
                if ticket["partner_id"] != "agreement":
                    await self.guard(partner, session)
                    locked = await self.db.partner_kyc_submissions.find_one(
                        {"partner_id": ticket["partner_id"]},
                        sort=[("created_at", -1)],
                        session=session,
                    )
                    if locked and locked["status"] in {"submitted", "under_review", "approved"}:
                        raise ConflictError(
                            "KYC is locked. Save an authorized revision before uploading."
                        )
                result = await self.db.partner_kyc_uploads.update_one(
                    {"_id": ticket["_id"], "used": False}, {"$set": {"used": True}}, session=session
                )
                if not result.matched_count:
                    raise ConflictError("Upload already confirmed.")
                await self.db.partner_kyc_documents.update_many(
                    {
                        "partner_id": ticket["partner_id"],
                        "category": ticket["category"],
                        "part": ticket["part"],
                        "current": True,
                    },
                    {"$set": {"current": False}},
                    session=session,
                )
                await self.db.partner_kyc_documents.insert_one(document, session=session)
                await event(
                    self.db,
                    actor,
                    "partner_kyc_document_uploaded",
                    ticket["partner_id"],
                    session=session,
                    detail={"document_id": str(document["_id"]), "category": ticket["category"]},
                )
        except Exception:
            storage.delete_object(Bucket=bucket, Key=key)
            raise
        finally:
            storage.delete_object(Bucket=bucket, Key=ticket["s3_key"])
        return public(document)

    async def document(self, document_id: str, actor: Any) -> tuple[bytes, str]:
        if actor.role == "referral_partner":
            await self.partner(actor)
        row = await self.db.partner_kyc_documents.find_one({"_id": oid(document_id)})
        if not row:
            raise NotFoundError("Document unavailable.")
        if row["partner_id"] != "agreement":
            await self.partner(actor, row["partner_id"])
        elif actor.role not in {"owner", "referral_partner"}:
            raise ForbiddenError("Partner agreement access required.")
        async with await self.db.client.start_session() as session, session.start_transaction():
            await event(
                self.db,
                actor,
                "partner_kyc_document_viewed",
                row["partner_id"],
                session=session,
                detail={"document_id": document_id},
            )
        response = get_s3_client().get_object(
            Bucket=get_storage_config().bucket_name, Key=row["s3_key"]
        )
        try:
            data = response["Body"].read(16 * 1024 * 1024)
        finally:
            response["Body"].close()
        return decrypt_bytes(data), row["content_type"]

    async def document_review(self, document_id: str, payload: Any, actor: Any) -> dict[str, Any]:
        if actor.role != "owner" or payload.decision == "under_review":
            raise ForbiddenError("Owner document decision required.")
        if payload.decision != "approved" and not payload.reason.strip():
            raise ValidationError("A rejection or re-upload reason is required.")
        history = {
            "at": utc_now(),
            "actor_id": actor.require_id(),
            "decision": payload.decision,
            "reason": payload.reason,
        }
        async with await self.db.client.start_session() as session, session.start_transaction():
            row = await self.db.partner_kyc_documents.find_one_and_update(
                {
                    "_id": oid(document_id),
                    "version": payload.version,
                    "partner_id": {"$ne": "agreement"},
                    "current": True,
                },
                {
                    "$set": {"status": payload.decision},
                    "$inc": {"version": 1},
                    "$push": {"review_history": history},
                },
                return_document=ReturnDocument.AFTER,
                session=session,
            )
            if not row:
                raise ConflictError("Document changed or is historical; reload.")
            await self.db.referral_partners.update_one(
                {"_id": oid(row["partner_id"])}, {"$inc": {"version": 1}}, session=session
            )
            if payload.decision != "approved":
                await self.db.referral_partners.update_one(
                    {"_id": oid(row["partner_id"])},
                    {"$set": {"kyc_status": "reupload_required"}, "$inc": {"version": 1}},
                    session=session,
                )
                await self.db.partner_kyc_submissions.update_one(
                    {
                        "partner_id": row["partner_id"],
                        "status": {"$in": ["submitted", "under_review", "approved"]},
                    },
                    {
                        "$set": {"status": "reupload_required"},
                        "$inc": {"version": 1},
                        "$push": {"review_history": history},
                    },
                    session=session,
                )
            await event(
                self.db,
                actor,
                "partner_kyc_document_" + payload.decision,
                row["partner_id"],
                session=session,
                detail={"document_id": document_id},
            )
        return public(row)
