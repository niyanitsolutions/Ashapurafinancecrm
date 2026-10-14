from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.core.exceptions import AppError, ForbiddenError, ValidationError
from app.core.response import ApiResponse
from app.features.access_control.permission_engine import PermissionEngine, require_permission
from app.features.auth.models import User
from app.features.voice_assistant.recording_schemas import TranscriptInput
from app.features.voice_assistant.recording_service import RecordingService
from app.features.voice_assistant.recording_storage import MAX_RECORDING_BYTES
from app.middleware.rate_limit import rate_limited

router = APIRouter(prefix="/voice-assistant/recordings", tags=["voice-recordings"])


def service(db: AsyncIOMotorDatabase[Any] = Depends(get_database)) -> RecordingService:
    return RecordingService(db)


Service = Annotated[RecordingService, Depends(service)]
View = Annotated[User, require_permission("voice_assistant", "recordings", "view")]
Create = Annotated[User, require_permission("voice_assistant", "recordings", "create")]
Edit = Annotated[User, require_permission("voice_assistant", "recordings", "edit")]
Delete = Annotated[User, require_permission("voice_assistant", "recordings", "delete")]


class RangeError(AppError):
    code = "invalid_audio_range"
    http_status = 416


@router.get("")
async def recordings(
    svc: Service,
    actor: View,
    page: int = Query(1, ge=1),
    status: Literal["pending", "completed", "failed", "expired", "deleted", "deletion_pending"]
    | None = None,
    call_id: str | None = Query(None, max_length=24),
    since: datetime | None = None,
    until: datetime | None = None,
) -> ApiResponse[Any]:
    return ApiResponse.ok(
        await svc.list(actor, page=page, status=status, call_id=call_id, since=since, until=until)
    )


@router.post("/import", dependencies=[rate_limited(5)])
async def import_recording(
    svc: Service,
    actor: Create,
    file: Annotated[UploadFile, File()],
    call_id: str = Form(..., pattern=r"^[a-f0-9]{24}$"),
    idempotency_key: str = Form(..., min_length=16, max_length=100, pattern=r"^[A-Za-z0-9_-]+$"),
    consent_reference: str = Form(..., min_length=5, max_length=150),
    retention_days: int = Form(30, ge=1, le=365),
) -> ApiResponse[Any]:
    try:
        if not (file.filename or "").casefold().endswith(".wav") or file.content_type not in {
            None,
            "",
            "audio/wav",
            "audio/x-wav",
            "audio/wave",
            "application/octet-stream",
        }:
            raise ValidationError("Import a PCM WAV recording; other formats are not supported.")
        data = await file.read(MAX_RECORDING_BYTES + 1)
        if len(data) > MAX_RECORDING_BYTES:
            raise ValidationError("Recording exceeds the 20 MB limit.")
        return ApiResponse.ok(
            await svc.import_recording(
                actor,
                call_id=call_id,
                data=data,
                idempotency_key=idempotency_key,
                consent_reference=consent_reference,
                retention_days=retention_days,
            )
        )
    finally:
        await file.close()


@router.get("/{record_id}/audio", dependencies=[rate_limited(30)])
async def audio(
    record_id: str,
    request: Request,
    svc: Service,
    actor: View,
    download: bool = False,
) -> Response:
    if download and not await PermissionEngine(svc.db).has_permission(
        actor, module="voice_assistant", resource="recordings", action="download"
    ):
        raise ForbiddenError("Recording Download permission is required.")
    data = await svc.audio(record_id, actor, download=download)
    headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'{"attachment" if download else "inline"}; filename="recording-{record_id}.wav"',
    }
    range_header = request.headers.get("range")
    if range_header:
        import re

        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
        if len(range_header) > 128 or not match or (not match[1] and not match[2]):
            raise RangeError("Use one valid recording byte range.")
        size = len(data)
        if not match[1]:
            suffix = int(match[2])
            if suffix < 1:
                raise RangeError("Invalid recording suffix range.")
            start, end = max(0, size - suffix), size - 1
        else:
            start = int(match[1])
            end = min(int(match[2]) if match[2] else size - 1, size - 1)
        if start >= size or end < start:
            raise RangeError("Recording byte range is unavailable.")
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        return Response(
            data[start : end + 1], status_code=206, media_type="audio/wav", headers=headers
        )
    return Response(data, media_type="audio/wav", headers=headers)


@router.put("/{record_id}/transcript")
async def import_transcript(
    record_id: str, payload: TranscriptInput, svc: Service, actor: Edit
) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.save_transcript(record_id, payload, actor))


@router.get("/{record_id}/transcript", dependencies=[rate_limited(30)])
async def transcript(record_id: str, svc: Service, actor: View) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.transcript(record_id, actor))


@router.delete("/{record_id}")
async def delete_recording(
    record_id: str, svc: Service, actor: Delete, version: int = Query(..., ge=1)
) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.delete(record_id, actor, version))


@router.post("/{record_id}/recover", dependencies=[rate_limited(5)])
async def recover_recording(
    record_id: str, svc: Service, actor: Edit, version: int = Query(..., ge=1)
) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.recover(record_id, actor, version))
