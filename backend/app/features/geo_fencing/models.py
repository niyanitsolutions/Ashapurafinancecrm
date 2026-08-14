"""Geo Fencing domain model. `geo_fencing` was a reserved-but-empty module in this
codebase ("no defined use case yet" — see docs/KNOWN_LIMITATIONS.md's general section);
this is its first real use case: a named work-area an Owner defines, with a radius and the
activities it's meant to gate.
"""

from pydantic import Field

from app.features.geo_fencing.constants import MAX_RADIUS_METERS, MIN_RADIUS_METERS, GeoActivity
from app.shared.base_document import BaseDocument


class GeoFence(BaseDocument):
    area_name: str
    address: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_meters: float = Field(ge=MIN_RADIUS_METERS, le=MAX_RADIUS_METERS)
    allowed_activities: list[str] = Field(default_factory=list)
    # status (BaseDocument): active/inactive — no hard delete anywhere in this codebase;
    # a real DELETE is only offered by the service when zero GeoExceptions reference it.

    def activity_is_valid(self) -> bool:
        return all(a in GeoActivity.ALL for a in self.allowed_activities)
