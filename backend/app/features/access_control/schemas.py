from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.features.access_control.constants import PermissionAction
from app.features.geo_fencing.constants import GeoActivity

_TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


class CreateRoleRequest(BaseModel):
    name: str
    description: str | None = None


class UpdateRoleRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class RoleResponse(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class CreatePermissionRequest(BaseModel):
    module: str
    resource: str
    actions: list[str]
    label: str | None = None


class PermissionResponse(BaseModel):
    id: str
    module: str
    resource: str
    actions: list[str]
    label: str | None


class RolePermissionGrantInput(BaseModel):
    permission_id: str
    granted_actions: list[str] = Field(default_factory=list)
    department_ids: list[str] | None = None
    branch_ids: list[str] | None = None


class SetRolePermissionsRequest(BaseModel):
    grants: list[RolePermissionGrantInput]


class RolePermissionResponse(BaseModel):
    id: str
    role_id: str
    permission_id: str
    module: str
    resource: str
    granted_actions: list[str]
    department_ids: list[str] | None
    branch_ids: list[str] | None


class AssignRoleRequest(BaseModel):
    employee_id: str


class EmployeeRoleResponse(BaseModel):
    id: str
    employee_id: str
    role_id: str
    role_name: str


class TemporaryAccessGrantInput(BaseModel):
    permission_id: str
    actions: list[str] = Field(default_factory=list)


class CreateTemporaryAccessRequest(BaseModel):
    employee_id: str
    grants: list[TemporaryAccessGrantInput]
    start_date: date
    end_date: date
    start_time: str = Field(pattern=_TIME_PATTERN)
    end_time: str = Field(pattern=_TIME_PATTERN)
    reason: str


class TemporaryAccessGrantResponse(BaseModel):
    permission_id: str
    module: str
    resource: str
    actions: list[str]


class TemporaryAccessResponse(BaseModel):
    id: str
    employee_id: str
    grants: list[TemporaryAccessGrantResponse]
    start_date: date
    end_date: date
    start_time: str
    end_time: str
    reason: str
    status: str


class CreateGeoExceptionRequest(BaseModel):
    employee_id: str
    # Either geo_fence_id (prefills the 3 fields below from the named fence) or the 3
    # fields directly (freeform, pre-geo_fencing-module behavior) — at least one path
    # must fully resolve latitude/longitude/radius_meters, validated in the service.
    geo_fence_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    radius_meters: float | None = Field(default=None, gt=0)
    start_date: date
    end_date: date
    start_time: str = Field(pattern=_TIME_PATTERN)
    end_time: str = Field(pattern=_TIME_PATTERN)
    reason: str
    # None (default) = applies to every enforced activity, same as before this field
    # existed. A specific GeoActivity value (e.g. "login") scopes the exception to only
    # that one activity.
    activity: str | None = None

    @field_validator("activity")
    @classmethod
    def _check_activity(cls, value: str | None) -> str | None:
        if value is not None and value not in GeoActivity.ALL:
            raise ValueError(f"Unknown activity value: {value}")
        return value


class GeoExceptionResponse(BaseModel):
    id: str
    employee_id: str
    geo_fence_id: str | None
    latitude: float
    longitude: float
    radius_meters: float
    start_date: date
    end_date: date
    start_time: str
    end_time: str
    reason: str
    status: str
    activity: str | None


class AccessibleModulesResponse(BaseModel):
    modules: list[str]


class PermissionActionsResponse(BaseModel):
    actions: list[str] = Field(default_factory=lambda: list(PermissionAction.ALL))
