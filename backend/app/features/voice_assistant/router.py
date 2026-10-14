import asyncio
import hashlib
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.core.exceptions import ValidationError
from app.core.response import ApiResponse
from app.features.access_control.permission_engine import require_permission
from app.features.auth.models import User
from app.features.employee.dependencies import require_owner
from app.features.voice_assistant.adapters import readiness
from app.features.voice_assistant.knowledge_import import MAX_IMPORT_BYTES, extract_document
from app.features.voice_assistant.repository import public
from app.features.voice_assistant.schemas import (
    CallAction,
    ConsoleInput,
    KnowledgeAction,
    KnowledgeEvaluationInput,
    KnowledgeInput,
    MockCallInput,
    VoiceSettings,
)
from app.features.voice_assistant.service import VoiceService
from app.middleware.rate_limit import rate_limited

router = APIRouter(prefix="/voice-assistant", tags=["voice-assistant"])


def service(db: AsyncIOMotorDatabase[Any] = Depends(get_database)) -> VoiceService:
    return VoiceService(db)


Service = Annotated[VoiceService, Depends(service)]
View = Annotated[User, require_permission("voice_assistant", "calls", "view")]
Create = Annotated[User, require_permission("voice_assistant", "calls", "create")]
Edit = Annotated[User, require_permission("voice_assistant", "calls", "edit")]
KnowledgeView = Annotated[User, require_permission("voice_assistant", "knowledge", "view")]
KnowledgeCreate = Annotated[User, require_permission("voice_assistant", "knowledge", "create")]
KnowledgeEdit = Annotated[User, require_permission("voice_assistant", "knowledge", "edit")]
KnowledgeApprove = Annotated[User, require_permission("voice_assistant", "knowledge", "approve")]
Owner = Annotated[User, Depends(require_owner)]


@router.get("/dashboard")
async def dashboard(svc: Service, actor: View) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.dashboard(actor))


@router.get("/settings")
async def settings(svc: Service, actor: Owner) -> ApiResponse[Any]:
    return ApiResponse.ok((await svc.settings()).model_dump(mode="json"))


@router.put("/settings")
async def save_settings(payload: VoiceSettings, svc: Service, actor: Owner) -> ApiResponse[Any]:
    return ApiResponse.ok((await svc.save_settings(payload, actor)).model_dump(mode="json"))


@router.get("/providers")
async def providers(actor: View) -> ApiResponse[Any]:
    return ApiResponse.ok(readiness())


@router.get("/calls")
async def calls(
    svc: Service,
    actor: View,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    status: str | None = Query(None, max_length=30),
    direction: Literal["incoming", "outgoing"] | None = None,
) -> ApiResponse[Any]:
    return ApiResponse.ok(
        await svc.list_calls(
            actor, page=page, page_size=page_size, status=status, direction=direction
        )
    )


@router.post("/mock/calls")
async def mock_call(payload: MockCallInput, svc: Service, actor: Create) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.create_mock_call(payload, actor))


@router.get("/calls/{record_id}")
async def call(record_id: str, svc: Service, actor: View) -> ApiResponse[Any]:
    return ApiResponse.ok(public(await svc.call(record_id, actor)))


@router.post("/mock/calls/{record_id}/actions")
async def call_action(
    record_id: str, payload: CallAction, svc: Service, actor: Edit
) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.act(record_id, payload, actor))


@router.get("/knowledge")
async def knowledge(
    svc: Service, actor: KnowledgeView, page: int = Query(1, ge=1)
) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.list_knowledge(page))


@router.post("/knowledge")
async def create_knowledge(
    payload: KnowledgeInput, svc: Service, actor: KnowledgeCreate
) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.save_knowledge(payload, actor))


@router.post("/knowledge/import", dependencies=[rate_limited(5)])
async def import_knowledge(
    svc: Service,
    actor: KnowledgeCreate,
    file: Annotated[UploadFile, File()],
    title: str = Form(..., min_length=3, max_length=150),
    language: str = Form("en", pattern=r"^[a-z]{2}$"),
) -> ApiResponse[Any]:
    try:
        data = await file.read(MAX_IMPORT_BYTES + 1)
        if len(data) > MAX_IMPORT_BYTES:
            raise ValidationError("Knowledge file exceeds the 5 MB limit.")
        content = await asyncio.to_thread(
            extract_document, data, file.filename or "", file.content_type
        )
        payload = KnowledgeInput(title=title, content=content, language=language)
        return ApiResponse.ok(
            await svc.save_knowledge(
                payload,
                actor,
                source={
                    "kind": "document",
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size_bytes": len(data),
                    "format": (file.filename or "").rsplit(".", 1)[-1].casefold(),
                    "scan_status": "not_scanned",
                    "extraction_status": "completed",
                    "index_kind": "lexical",
                    "uploaded_by": actor.require_id(),
                },
            )
        )
    finally:
        await file.close()


@router.post("/knowledge/{record_id}/evaluations", dependencies=[rate_limited(10)])
async def evaluate_knowledge(
    record_id: str, payload: KnowledgeEvaluationInput, svc: Service, actor: KnowledgeEdit
) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.evaluate_knowledge(record_id, payload, actor))


@router.get("/knowledge/{record_id}/evaluations")
async def knowledge_evaluations(
    record_id: str, svc: Service, actor: KnowledgeView
) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.knowledge_evaluations(record_id))


@router.put("/knowledge/{record_id}")
async def edit_knowledge(
    record_id: str, payload: KnowledgeInput, svc: Service, actor: KnowledgeEdit
) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.save_knowledge(payload, actor, record_id))


@router.post("/knowledge/{record_id}/actions")
async def knowledge_action(
    record_id: str, payload: KnowledgeAction, svc: Service, actor: KnowledgeApprove
) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.knowledge_action(record_id, payload, actor))


@router.post("/console", dependencies=[rate_limited(10)])
async def console(payload: ConsoleInput, svc: Service, actor: KnowledgeView) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.console(payload, actor))


@router.post("/live/{feature}")
async def live(
    feature: Literal["inbound", "outbound", "recording", "cloning"], svc: Service, actor: Owner
) -> ApiResponse[Any]:
    await svc.require_live(feature, actor)
    raise RuntimeError("Live gate returned unexpectedly.")
