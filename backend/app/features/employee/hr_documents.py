"""Private immutable employee document versions, tied to canonical employees."""

import io
import secrets
from datetime import timedelta
from typing import Any, Literal

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field

from app.config.storage import get_storage_config
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.features.employee.hr_notifications import record_event as write_audit_log
from app.features.employee.hr_profile import HrProfiles
from app.services.storage.client import (
    generate_presigned_download_url,
    generate_presigned_upload_url,
    get_s3_client,
)
from app.utils.datetime import utc_now

Category = Literal[
    "aadhaar",
    "pan",
    "bank_passbook",
    "rental_agreement",
    "pvc_certificate",
    "offer_letter",
    "joining_letter",
    "photo",
    "relieving_letter",
    "experience_letter",
    "experience_certificate",
    "other",
]
REQUIRED = {
    "aadhaar",
    "pan",
    "bank_passbook",
    "rental_agreement",
    "pvc_certificate",
    "offer_letter",
    "joining_letter",
    "photo",
}
MIME = {"application/pdf", "image/jpeg", "image/png"}
MAX_SIZE = 10 * 1024 * 1024


class UploadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Category
    part: Literal["file", "front", "back"] = "file"
    file_name: str = Field(min_length=1, max_length=200, pattern=r"^[^\x00-\x1f\x7f/\\]+$")
    content_type: Literal["application/pdf", "image/jpeg", "image/png"]
    size: int = Field(gt=0, le=MAX_SIZE)


class ConfirmInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Category
    version: int = Field(ge=0)
    tickets: list[str] = Field(min_length=1, max_length=2)
    pdf_password: str | None = Field(default=None, max_length=200, repr=False)


class DocumentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    decision: Literal["approved", "rejected", "reupload_required"]
    reason: str = Field(default="", max_length=2000)


def materialize(key: str, mime: str, password: str | None) -> tuple[bytes, str]:
    """Read bounded private input and validate bytes. Password never leaves this call."""
    client = get_s3_client()
    bucket = get_storage_config().bucket_name
    head = client.head_object(Bucket=bucket, Key=key)
    if not 0 < int(head["ContentLength"]) <= MAX_SIZE:
        raise ValidationError("Document must be between 1 byte and 10 MB.")
    response = client.get_object(Bucket=bucket, Key=key)
    try:
        data = response["Body"].read(MAX_SIZE + 1)
    finally:
        response["Body"].close()
    if len(data) > MAX_SIZE:
        raise ValidationError("Document exceeds 10 MB.")
    if mime == "application/pdf":
        try:
            import fitz  # type: ignore[import-untyped]
        except ImportError:
            raise ValidationError(
                "PDF document processing is not configured on this server."
            ) from None
        try:
            with fitz.open(stream=data, filetype="pdf") as document:
                if document.needs_pass and (not password or not document.authenticate(password)):
                    raise ValueError("Password required")
                if not document.page_count:
                    raise ValueError("Empty PDF")
                # Decrypt transiently into the private immutable final object.
                data = document.tobytes(encryption=fitz.PDF_ENCRYPT_NONE)
        except Exception:  # noqa: BLE001 - sanitize parser errors; never expose password/file contents
            raise ValidationError(
                "PDF could not be processed. Check the file and its password."
            ) from None
    else:
        try:
            from PIL import Image

            with Image.open(io.BytesIO(data)) as image:
                if image.format != ("JPEG" if mime == "image/jpeg" else "PNG"):
                    raise ValueError("Wrong type")
                image.verify()
        except Exception:  # noqa: BLE001 - sanitize parser errors; never expose password/file contents
            raise ValidationError(
                "The image does not match its declared type or is invalid."
            ) from None
    if len(data) > MAX_SIZE:
        raise ValidationError("Processed document exceeds 10 MB.")
    return data, mime


class HrDocuments:
    def __init__(self, service: Any):
        self.service = service
        self.db = service._db
        self.profiles = HrProfiles(service)

    async def upload(self, employee_id: str, payload: UploadInput, actor: Any) -> dict[str, Any]:
        employee = await self.profiles.employee(employee_id, actor)
        if payload.category != "aadhaar" and payload.part != "file":
            raise ValidationError("Only Aadhaar uses front/back parts.")
        if payload.category == "aadhaar" and (
            (payload.part == "file") != (payload.content_type == "application/pdf")
        ):
            raise ValidationError("Use one Aadhaar PDF or front/back images.")
        if payload.category == "photo" and payload.content_type == "application/pdf":
            raise ValidationError("The photograph must be an image.")
        ticket = secrets.token_urlsafe(32)
        key = f"employee-upload-staging/{employee['_id']}/{secrets.token_hex(24)}"
        await self.db.employee_upload_intents.insert_one(
            {
                "_id": ticket,
                "employee_id": str(employee["_id"]),
                "actor_id": actor.require_id(),
                "key": key,
                "category": payload.category,
                "part": payload.part,
                "file_name": payload.file_name,
                "content_type": payload.content_type,
                "expires_at": utc_now() + timedelta(minutes=10),
                "state": "pending",
            }
        )
        return {
            "ticket": ticket,
            "upload_url": generate_presigned_upload_url(
                key, expires_in=300, content_type=payload.content_type
            ),
            "expires_in": 300,
        }

    async def confirm(self, employee_id: str, payload: ConfirmInput, actor: Any) -> dict[str, Any]:
        employee = await self.profiles.employee(employee_id, actor)
        previous = employee.get("hr_documents", {}).get(payload.category, {})
        if previous.get("version", 0) != payload.version:
            raise ConflictError("Document changed. Refresh before uploading a replacement.")
        intents = []
        for ticket in payload.tickets:
            intent = await self.db.employee_upload_intents.find_one(
                {
                    "_id": ticket,
                    "employee_id": str(employee["_id"]),
                    "actor_id": actor.require_id(),
                    "category": payload.category,
                    "state": "pending",
                    "expires_at": {"$gt": utc_now()},
                }
            )
            if not intent:
                raise ValidationError("Upload ticket is invalid, expired or already consumed.")
            intents.append(intent)
        parts = {intent["part"] for intent in intents}
        if (
            len(set(payload.tickets)) != len(payload.tickets)
            or (payload.category == "aadhaar" and parts not in ({"file"}, {"front", "back"}))
            or (payload.category != "aadhaar" and (len(intents) != 1 or parts != {"file"}))
        ):
            raise ValidationError("Aadhaar needs one PDF or both front and back images.")
        # Claim each bounded upload ticket before reading or writing private objects.
        for intent in intents:
            claimed = await self.db.employee_upload_intents.update_one(
                {"_id": intent["_id"], "state": "pending", "expires_at": {"$gt": utc_now()}},
                {"$set": {"state": "processing"}},
            )
            if not claimed.modified_count:
                raise ConflictError("Upload already consumed. Request a new upload URL.")
        files = []
        for intent in intents:
            from starlette.concurrency import run_in_threadpool

            data, mime = await run_in_threadpool(
                materialize,
                intent["key"],
                intent["content_type"],
                payload.pdf_password if payload.category == "aadhaar" else None,
            )
            final = f"employee-documents/{employee['employee_code']}/{payload.category}/{secrets.token_hex(24)}"
            await run_in_threadpool(
                get_s3_client().put_object,
                Bucket=get_storage_config().bucket_name,
                Key=final,
                Body=data,
                ContentType=mime,
            )
            files.append(
                {
                    "s3_key": final,
                    "file_name": intent["file_name"],
                    "content_type": mime,
                    "part": intent["part"],
                    "size": len(data),
                }
            )
        now = utc_now()
        oid = ObjectId()
        version = {
            "id": str(oid),
            "version": payload.version + 1,
            "status": "pending_verification",
            "files": files,
            "uploaded_by": actor.require_id(),
            "uploaded_at": now,
            "malware_scan": "not_configured",
            "history": [],
        }
        # The pointer/version history and profile state change atomically in one employee.
        changed = await self.profiles.commit(
            {
                "_id": employee["_id"],
                "is_deleted": False,
                "hr_documents": employee.get("hr_documents"),
            },
            {
                "$set": {
                    f"hr_documents.{payload.category}": {
                        **version,
                        "versions": previous.get("versions", [])
                        + (
                            [{key: value for key, value in previous.items() if key != "versions"}]
                            if previous
                            else []
                        ),
                    },
                    "onboarding.status": "changes_required",
                },
                "$inc": {"onboarding.version": 1},
            },
            actor,
            "employee_document_version_uploaded",
            {
                "employee_id": str(employee["_id"]),
                "category": payload.category,
                "version": payload.version + 1,
            },
        )
        if not changed:
            raise ConflictError("Documents changed. Refresh before confirming.")
        await self.db.employee_documents.update_one(
            {"_id": oid},
            {
                "$setOnInsert": {
                    "_id": oid,
                    "employee_id": str(employee["_id"]),
                    "document_type": payload.category,
                    "file_name": files[0]["file_name"],
                    "s3_key": files[0]["s3_key"],
                    "content_type": files[0]["content_type"],
                    "files": files,
                    "created_at": now,
                    "updated_at": now,
                    "created_by": actor.require_id(),
                    "is_deleted": False,
                    "status": "pending_verification",
                }
            },
            upsert=True,
        )
        await self.db.employee_upload_intents.update_many(
            {"_id": {"$in": payload.tickets}}, {"$set": {"state": "consumed"}}
        )
        await write_audit_log(
            self.db,
            event_type="employee_document_version_uploaded",
            user_id=actor.require_id(),
            metadata={
                "employee_id": str(employee["_id"]),
                "category": payload.category,
                "version": payload.version + 1,
            },
        )
        return self.public(changed)

    @staticmethod
    def public(employee: dict[str, Any]) -> dict[str, Any]:
        def clean(value: Any) -> Any:
            if isinstance(value, dict):
                return {key: clean(item) for key, item in value.items() if key != "s3_key"}
            if isinstance(value, list):
                return [clean(item) for item in value]
            return value

        return dict(clean(employee.get("hr_documents", {})))

    async def review(
        self, employee_id: str, category: Category, payload: DocumentDecision, actor: Any
    ) -> dict[str, Any]:
        employee = await self.profiles.employee(employee_id, actor, review=True)
        previous = employee.get("hr_documents", {}).get(category)
        if not previous or previous.get("status") != "pending_verification":
            raise ConflictError("Only the current pending document can be reviewed.")
        if payload.decision != "approved" and not payload.reason.strip():
            raise ValidationError("A rejection or reupload reason is required.")
        now = utc_now()
        changed = await self.profiles.commit(
            {
                "_id": employee["_id"],
                f"hr_documents.{category}.version": payload.version,
                f"hr_documents.{category}.status": "pending_verification",
            },
            {
                "$set": {f"hr_documents.{category}.status": payload.decision},
                "$push": {
                    f"hr_documents.{category}.history": {
                        "status": payload.decision,
                        "reason": payload.reason.strip(),
                        "reviewed_by": actor.require_id(),
                        "at": now,
                    }
                },
                "$inc": {"onboarding.version": 1},
            },
            actor,
            "employee_document_" + payload.decision,
            {"employee_id": str(employee["_id"]), "category": category, "version": payload.version},
        )
        if not changed:
            raise ConflictError("Document changed. Refresh before reviewing.")
        await write_audit_log(
            self.db,
            event_type="employee_document_" + payload.decision,
            user_id=actor.require_id(),
            metadata={
                "employee_id": str(employee["_id"]),
                "category": category,
                "version": payload.version,
            },
        )
        return self.public(changed)

    async def download(
        self, employee_id: str, category: Category, version: int, part: str, actor: Any
    ) -> str:
        employee = await self.profiles.employee(employee_id, actor)
        current = employee.get("hr_documents", {}).get(category, {})
        document = next(
            (
                row
                for row in [current] + current.get("versions", [])
                if row.get("version") == version
            ),
            None,
        )
        file = next((row for row in (document or {}).get("files", []) if row["part"] == part), None)
        if not file:
            raise NotFoundError("Document version not found.")
        await write_audit_log(
            self.db,
            event_type="employee_document_viewed",
            user_id=actor.require_id(),
            metadata={
                "employee_id": str(employee["_id"]),
                "category": category,
                "version": version,
            },
        )
        return generate_presigned_download_url(file["s3_key"], expires_in=120)

    async def require_approved(self, employee: dict[str, Any]) -> None:
        required = REQUIRED.copy()
        if not employee.get("onboarding", {}).get("profile", {}).get("fresher", True):
            required |= {"relieving_letter", "experience_letter"}
        missing = [
            name
            for name in required
            if employee.get("hr_documents", {}).get(name, {}).get("status") != "approved"
        ]
        if missing:
            raise ValidationError(
                "Approve all required documents first: " + ", ".join(sorted(missing))
            )
