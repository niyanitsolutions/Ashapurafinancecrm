"""Geo Fencing routes — gated with `Depends(require_permission("geo_fencing", "fences",
action))`, the same real RBAC engine `system_settings` already consumes (Owner bypasses it
entirely). No new authorization mechanism invented."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.core.pagination import PageParams, page_params
from app.core.response import ApiResponse, ResponseMeta
from app.features.access_control.permission_engine import require_permission
from app.features.auth.models import User
from app.features.geo_fencing import mappers
from app.features.geo_fencing.dependencies import get_geo_fencing_service
from app.features.geo_fencing.schemas import (
    CreateGeoFenceRequest,
    GeoFenceResponse,
    UpdateGeoFenceRequest,
)
from app.features.geo_fencing.service import GeoFencingService

router = APIRouter(prefix="/geo-fences", tags=["geo-fencing"])

ServiceDep = Annotated[GeoFencingService, Depends(get_geo_fencing_service)]
PageParamsDep = Annotated[PageParams, Depends(page_params)]
_MODULE = "geo_fencing"
_RESOURCE = "fences"


def _perm(action: str) -> Any:
    return require_permission(_MODULE, _RESOURCE, action)


@router.get("")
async def list_geo_fences(
    service: ServiceDep,
    actor: Annotated[User, _perm("view")],
    page: PageParamsDep,
    activity: str | None = None,
    status: str | None = None,
) -> ApiResponse[list[GeoFenceResponse]]:
    fences, total = await service.list_geo_fences(
        search=page.search, activity=activity, status=status, skip=page.skip, limit=page.page_size, sort=page.sort,
    )
    items = [mappers.geo_fence_to_response(f) for f in fences]
    return ApiResponse[list[GeoFenceResponse]].ok(items, meta=ResponseMeta(pagination=page.build_meta(total)))


@router.post("")
async def create_geo_fence(payload: CreateGeoFenceRequest, service: ServiceDep, actor: Annotated[User, _perm("create")]) -> ApiResponse[GeoFenceResponse]:
    fence, overlaps = await service.create_geo_fence(payload, actor)
    return ApiResponse[GeoFenceResponse].ok(mappers.geo_fence_to_response(fence, overlaps))


@router.get("/{fence_id}")
async def get_geo_fence(fence_id: str, service: ServiceDep, actor: Annotated[User, _perm("view")]) -> ApiResponse[GeoFenceResponse]:
    fence = await service.get_geo_fence(fence_id)
    return ApiResponse[GeoFenceResponse].ok(mappers.geo_fence_to_response(fence))


@router.patch("/{fence_id}")
async def update_geo_fence(
    fence_id: str, payload: UpdateGeoFenceRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[GeoFenceResponse]:
    fence, overlaps = await service.update_geo_fence(fence_id, payload, actor)
    return ApiResponse[GeoFenceResponse].ok(mappers.geo_fence_to_response(fence, overlaps))


@router.patch("/{fence_id}/activate")
async def activate_geo_fence(fence_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")]) -> ApiResponse[GeoFenceResponse]:
    fence = await service.activate_geo_fence(fence_id, actor)
    return ApiResponse[GeoFenceResponse].ok(mappers.geo_fence_to_response(fence))


@router.patch("/{fence_id}/deactivate")
async def deactivate_geo_fence(fence_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")]) -> ApiResponse[GeoFenceResponse]:
    fence = await service.deactivate_geo_fence(fence_id, actor)
    return ApiResponse[GeoFenceResponse].ok(mappers.geo_fence_to_response(fence))


@router.delete("/{fence_id}")
async def delete_geo_fence(fence_id: str, service: ServiceDep, actor: Annotated[User, _perm("delete")]) -> ApiResponse[None]:
    await service.delete_geo_fence(fence_id, actor)
    return ApiResponse[None].ok()
