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
    """No latitude/longitude/radius — a GeoException is a bypass of the employee's
    applicable Geo Fence(s), not a second, competing location restriction (see
    `app/features/geo_fencing/enforcement.py`)."""

    employee_id: str
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
    start_date: date
    end_date: date
    start_time: str
    end_time: str
    reason: str
    status: str
    activity: str | None


class AccessibleModulesResponse(BaseModel):
    modules: list[str]


class MyPermissionsResponse(BaseModel):
    # "module:resource" -> granted actions, for the CURRENTLY authenticated user only —
    # UI support for showing/hiding buttons, never itself an authorization boundary
    # (every write still goes through require_permission independently). Empty for
    # Owner — the frontend treats Owner as unrestricted and never consults this.
    grants: dict[str, list[str]]


class PermissionActionsResponse(BaseModel):
    actions: list[str] = Field(default_factory=lambda: list(PermissionAction.ALL))
