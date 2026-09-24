import base64
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, UploadFile
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from starlette.concurrency import run_in_threadpool

from app.config.database import get_database
from app.config.redis import get_redis
from app.core.exceptions import ForbiddenError, ValidationError
from app.core.response import ApiResponse
from app.features.access_control.permission_engine import PermissionEngine
from app.features.access_control.repository import PermissionRepository
from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.bulk_import.files import MAX_BYTES, parse_file, sample_file
from app.features.bulk_import.service import BulkImportService
from app.features.geo_fencing.constants import GeoActivity
from app.features.geo_fencing.enforcement import enforce_geo_fence

router = APIRouter(prefix="/bulk-import", tags=["bulk-import"])
Kind = Literal["leads", "insurance"]
DbDep = Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]
RedisDep = Annotated[Redis, Depends(get_redis)]


async def authorize(
    kind: Kind, actor: Annotated[User, Depends(get_current_active_user)], db: DbDep
) -> User:
    module, resource, action = ("leads", "leads", "create")
    if kind == "insurance":
        module, resource, action = "insurance_management", "applications", "create"
        repository = PermissionRepository(db)
        if await repository.find_by_module_resource(module, "applications.fresh_lead") is not None:
            resource = "applications.fresh_lead"
        else:
            legacy = await repository.find_by_module_resource(module, resource)
            if legacy is not None and action not in legacy.actions:
                action = "edit"
    if not await PermissionEngine(db).has_permission(
        actor, module=module, resource=resource, action=action
    ):
        raise ForbiddenError("You do not have permission to import these leads.")
    return actor


ActorDep = Annotated[User, Depends(authorize)]


class ConfirmRequest(BaseModel):
    batch_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


@router.get("/{kind}/sample")
async def sample(
    kind: Kind, actor: ActorDep, db: DbDep, redis: RedisDep
) -> ApiResponse[dict[str, str]]:
    lookups = await BulkImportService(db, redis).lookups(kind)
    content = await run_in_threadpool(sample_file, kind, lookups)
    return ApiResponse[dict[str, str]].ok(
        {"filename": f"{kind}-sample.xlsx", "content": base64.b64encode(content).decode("ascii")}
    )


@router.post("/{kind}/preview")
async def preview(
    kind: Kind, actor: ActorDep, db: DbDep, redis: RedisDep, file: UploadFile
) -> ApiResponse[dict[str, Any]]:
    try:
        content = await file.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise ValidationError("Choose a file no larger than 5 MB.")
        rows = await run_in_threadpool(
            parse_file, content, file.filename or "", file.content_type, kind
        )
        result = await BulkImportService(db, redis).preview(kind, rows, actor)
        return ApiResponse[dict[str, Any]].ok(result)
    finally:
        await file.close()


@router.post("/{kind}/confirm")
async def confirm(
    kind: Kind, payload: ConfirmRequest, actor: ActorDep, db: DbDep, redis: RedisDep
) -> ApiResponse[dict[str, Any]]:
    if kind == "leads":
        await enforce_geo_fence(
            db,
            actor=actor,
            activity=GeoActivity.LEAD_CREATION,
            latitude=payload.latitude,
            longitude=payload.longitude,
        )
    result = await BulkImportService(db, redis).confirm(kind, payload.batch_id, actor)
    return ApiResponse[dict[str, Any]].ok(result)
