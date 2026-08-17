"""Geo Fencing business logic: named-area CRUD plus enforcement. Overlap between two
active fences is flagged as a non-blocking warning (`overlaps_with` in the response)
rather than a `ConflictError`, since two legitimately close branches/work-areas are a
real business case, not a data-entry mistake.

A `GeoException` is a bypass of an employee's applicable fence(s), not a reference to
any one specific fence (see `app/features/access_control/models.py:GeoException` and
`enforcement.py`) — so deleting a `GeoFence` is never blocked by an active exception;
there is nothing for the exception to lose a reference to.
"""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import NotFoundError
from app.features.auth.models import User
from app.features.geo_fencing.constants import AuditEvent, GeoFenceStatus
from app.features.geo_fencing.geomath import haversine_distance_meters
from app.features.geo_fencing.models import GeoFence
from app.features.geo_fencing.repository import GeoFenceRepository
from app.features.geo_fencing.schemas import CreateGeoFenceRequest, UpdateGeoFenceRequest
from app.shared.audit_log import write_audit_log


class GeoFencingService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self._db = db
        self._fences = GeoFenceRepository(db)

    async def create_geo_fence(self, payload: CreateGeoFenceRequest, owner: User) -> tuple[GeoFence, list[str]]:
        fence = GeoFence(
            area_name=payload.area_name, address=payload.address, latitude=payload.latitude,
            longitude=payload.longitude, radius_meters=payload.radius_meters,
            allowed_activities=payload.allowed_activities, created_by=owner.require_id(),
        )
        overlaps = await self._overlapping_fence_names(fence, exclude_id=None)
        fence_id = await self._fences.insert(fence)
        await write_audit_log(self._db, event_type=AuditEvent.FENCE_CREATED, user_id=owner.require_id(), metadata={"geo_fence_id": fence_id})
        saved = await self._fences.find_by_id(fence_id)
        assert saved is not None
        return saved, overlaps

    async def update_geo_fence(self, fence_id: str, payload: UpdateGeoFenceRequest, owner: User) -> tuple[GeoFence, list[str]]:
        existing = await self._get_or_404(fence_id)
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return existing, await self._overlapping_fence_names(existing, exclude_id=fence_id)

        updated = await self._fences.update(fence_id, updates, updated_by=owner.require_id())
        assert updated is not None
        overlaps = await self._overlapping_fence_names(updated, exclude_id=fence_id)
        await write_audit_log(self._db, event_type=AuditEvent.FENCE_UPDATED, user_id=owner.require_id(), metadata={"geo_fence_id": fence_id})
        return updated, overlaps

    async def activate_geo_fence(self, fence_id: str, owner: User) -> GeoFence:
        await self._get_or_404(fence_id)
        updated = await self._fences.update(fence_id, {"status": GeoFenceStatus.ACTIVE}, updated_by=owner.require_id())
        assert updated is not None
        await write_audit_log(self._db, event_type=AuditEvent.FENCE_ACTIVATED, user_id=owner.require_id(), metadata={"geo_fence_id": fence_id})
        return updated

    async def deactivate_geo_fence(self, fence_id: str, owner: User) -> GeoFence:
        await self._get_or_404(fence_id)
        updated = await self._fences.update(fence_id, {"status": GeoFenceStatus.INACTIVE}, updated_by=owner.require_id())
        assert updated is not None
        await write_audit_log(self._db, event_type=AuditEvent.FENCE_DEACTIVATED, user_id=owner.require_id(), metadata={"geo_fence_id": fence_id})
        return updated

    async def delete_geo_fence(self, fence_id: str, owner: User) -> None:
        await self._get_or_404(fence_id)
        await self._fences.soft_delete(fence_id, deleted_by=owner.require_id())
        await write_audit_log(self._db, event_type=AuditEvent.FENCE_DELETED, user_id=owner.require_id(), metadata={"geo_fence_id": fence_id})

    async def get_geo_fence(self, fence_id: str) -> GeoFence:
        return await self._get_or_404(fence_id)

    async def list_geo_fences(
        self, *, search: str | None, activity: str | None, status: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None
    ) -> tuple[list[GeoFence], int]:
        return await self._fences.search_and_filter(search=search, activity=activity, status=status, skip=skip, limit=limit, sort=sort)

    async def _overlapping_fence_names(self, fence: GeoFence, *, exclude_id: str | None) -> list[str]:
        others = await self._fences.find_all_active()
        overlaps = []
        for other in others:
            if other.require_id() == exclude_id:
                continue
            distance = haversine_distance_meters(fence.latitude, fence.longitude, other.latitude, other.longitude)
            if distance <= (fence.radius_meters + other.radius_meters):
                overlaps.append(other.area_name)
        return overlaps

    async def _get_or_404(self, fence_id: str) -> GeoFence:
        fence = await self._fences.find_by_id(fence_id)
        if fence is None:
            raise NotFoundError("Geo Fence not found.")
        return fence
