import asyncio
import csv
import io
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError as SchemaError
from redis.asyncio import Redis

from app.config.database import get_database
from app.config.redis import get_redis
from app.core.exceptions import ValidationError
from app.core.response import ApiResponse
from app.features.access_control.permission_engine import require_permission
from app.features.auth.models import User
from app.features.employee.dependencies import require_owner
from app.features.voice_assistant.campaign_schemas import (
    AudienceInput,
    CampaignAction,
    CampaignInput,
    ContactConsentInput,
    EmergencyInput,
    RecipientInput,
    SuppressionInput,
)
from app.features.voice_assistant.campaign_service import CampaignService
from app.features.voice_assistant.knowledge_import import MAX_IMPORT_BYTES, decode_text
from app.middleware.rate_limit import rate_limited

router = APIRouter(prefix="/voice-assistant", tags=["voice-campaigns"])


def service(
    db: AsyncIOMotorDatabase[Any] = Depends(get_database), redis: Redis = Depends(get_redis)
) -> CampaignService:
    return CampaignService(db, redis)


Service = Annotated[CampaignService, Depends(service)]
View = Annotated[User, require_permission("voice_assistant", "campaigns", "view")]
Create = Annotated[User, require_permission("voice_assistant", "campaigns", "create")]
Edit = Annotated[User, require_permission("voice_assistant", "campaigns", "edit")]
Import = Annotated[User, require_permission("voice_assistant", "campaigns", "import")]
Owner = Annotated[User, Depends(require_owner)]


@router.get("/campaigns")
async def campaigns(svc: Service, actor: View, page: int = Query(1, ge=1)) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.list(actor, page))


@router.post("/campaigns", dependencies=[rate_limited(10)])
async def create_campaign(payload: CampaignInput, svc: Service, actor: Create) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.save(payload, actor))


@router.put("/campaigns/{record_id}")
async def edit_campaign(
    record_id: str, payload: CampaignInput, svc: Service, actor: Edit
) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.save(payload, actor, record_id))


@router.post("/campaigns/{record_id}/actions")
async def campaign_action(
    record_id: str, payload: CampaignAction, svc: Service, actor: Edit
) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.action(record_id, payload, actor))


@router.get("/campaigns/{record_id}/recipients")
async def recipients(
    record_id: str, svc: Service, actor: View, page: int = Query(1, ge=1)
) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.recipients(record_id, actor, page))


@router.post("/campaigns/{record_id}/recipients", dependencies=[rate_limited(10)])
async def add_recipients(
    record_id: str, payload: AudienceInput, svc: Service, actor: Import
) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.audience(record_id, payload, actor))


def parse_audience_csv(data: bytes) -> list[RecipientInput]:
    try:
        if not data or len(data) > MAX_IMPORT_BYTES:
            raise ValueError("size")
        reader = csv.DictReader(io.StringIO(decode_text(data)), strict=True)
        if reader.fieldnames not in (["customer_id"], ["customer_id", "timezone"]):
            raise ValueError("columns")
        recipients: list[RecipientInput] = []
        for row in reader:
            if len(recipients) >= 500 or None in row:
                raise ValueError("rows")
            recipients.append(
                RecipientInput(
                    customer_id=row["customer_id"].strip(),
                    timezone=row.get("timezone", "").strip() or None,
                )
            )
        if not recipients:
            raise ValueError("empty")
        return recipients
    except (ValueError, UnicodeError, csv.Error, SchemaError, TypeError, AttributeError):
        raise ValidationError(
            "Use CSV columns customer_id,timezone (timezone optional), at most 500 rows/5 MB, valid CRM customer IDs and IANA timezones. No phone numbers, formulas or new customers are imported."
        ) from None


@router.post("/campaigns/{record_id}/recipients/import", dependencies=[rate_limited(5)])
async def import_recipients(
    record_id: str,
    svc: Service,
    actor: Import,
    file: Annotated[UploadFile, File()],
    version: int = Form(..., ge=1),
    idempotency_key: str = Form(..., min_length=16, max_length=100, pattern=r"^[A-Za-z0-9_-]+$"),
) -> ApiResponse[Any]:
    try:
        if not (file.filename or "").casefold().endswith(".csv") or file.content_type not in {
            "text/csv",
            "text/plain",
            "application/octet-stream",
        }:
            raise ValidationError("Import a CSV referencing existing customers only.")
        data = await file.read(MAX_IMPORT_BYTES + 1)
        recipients = await asyncio.to_thread(parse_audience_csv, data)
        return ApiResponse.ok(
            await svc.audience(
                record_id,
                AudienceInput(
                    version=version, idempotency_key=idempotency_key, recipients=recipients
                ),
                actor,
            )
        )
    finally:
        await file.close()


@router.post("/campaigns/{record_id}/preview", dependencies=[rate_limited(10)])
async def preview(
    record_id: str, svc: Service, actor: View, page: int = Query(1, ge=1)
) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.preview(record_id, actor, page))


@router.get("/contact-policies/{customer_id}")
async def contact_policies(customer_id: str, svc: Service, actor: Owner) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.contact_policies(customer_id, actor))


@router.put("/contact-policies/consent")
async def consent(payload: ContactConsentInput, svc: Service, actor: Owner) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.save_contact_policy(payload, actor))


@router.put("/contact-policies/suppression")
async def suppression(payload: SuppressionInput, svc: Service, actor: Owner) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.save_contact_policy(payload, actor))


@router.post("/campaign-controls/emergency")
async def emergency(payload: EmergencyInput, svc: Service, actor: Owner) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.emergency(payload.stopped, payload.reason, actor))
