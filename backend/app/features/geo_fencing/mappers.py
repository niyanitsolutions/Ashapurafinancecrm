from app.features.geo_fencing.models import GeoFence
from app.features.geo_fencing.schemas import GeoFenceResponse


def geo_fence_to_response(fence: GeoFence, overlaps_with: list[str] | None = None) -> GeoFenceResponse:
    return GeoFenceResponse(
        id=fence.require_id(), area_name=fence.area_name, address=fence.address,
        latitude=fence.latitude, longitude=fence.longitude, radius_meters=fence.radius_meters,
        allowed_activities=fence.allowed_activities, status=fence.status,
        created_at=fence.created_at, updated_at=fence.updated_at,
        overlaps_with=overlaps_with or [],
    )
