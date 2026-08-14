from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.features.geo_fencing.constants import MAX_RADIUS_METERS, MIN_RADIUS_METERS, GeoActivity


def _validate_activities(value: list[str]) -> list[str]:
    invalid = [a for a in value if a not in GeoActivity.ALL]
    if invalid:
        raise ValueError(f"Unknown allowed_activities value(s): {', '.join(invalid)}")
    return value


class CreateGeoFenceRequest(BaseModel):
    area_name: str = Field(min_length=1)
    address: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_meters: float = Field(ge=MIN_RADIUS_METERS, le=MAX_RADIUS_METERS)
    allowed_activities: list[str] = Field(default_factory=list)

    @field_validator("allowed_activities")
    @classmethod
    def _check_activities(cls, value: list[str]) -> list[str]:
        return _validate_activities(value)


class UpdateGeoFenceRequest(BaseModel):
    area_name: str | None = Field(default=None, min_length=1)
    address: str | None = Field(default=None, min_length=1)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_meters: float | None = Field(default=None, ge=MIN_RADIUS_METERS, le=MAX_RADIUS_METERS)
    allowed_activities: list[str] | None = None

    @field_validator("allowed_activities")
    @classmethod
    def _check_activities(cls, value: list[str] | None) -> list[str] | None:
        return _validate_activities(value) if value is not None else value


class GeoCoordinatesRequest(BaseModel):
    """Reused as the optional request body for the handful of existing endpoints that
    gained a geo-fencing check (e.g. loan/insurance case "Verify Documents", which
    previously took no body at all) — kept here rather than duplicated per-feature since
    it's purely a geo_fencing concern, not a loan/insurance one."""

    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class GeoFenceResponse(BaseModel):
    id: str
    area_name: str
    address: str
    latitude: float
    longitude: float
    radius_meters: float
    allowed_activities: list[str]
    status: str
    created_at: datetime
    updated_at: datetime
    overlaps_with: list[str] = Field(default_factory=list)  # area_names of nearby active fences — a warning, not a block
