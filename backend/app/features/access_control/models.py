"""Access Control domain models.

Time windows on TemporaryAccess/GeoException are a *daily recurring* window (date range +
time-of-day range), not one continuous span — see docs/decisions/DECISIONS.md. BSON has
no bare `date` or `time` type (see the date/datetime note in docs/database/DATABASE.md,
discovered in Module 2): dates are stored as `datetime` at midnight UTC, times are stored
as "HH:MM" strings and compared as such — never `datetime.time` directly.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.features.access_control.constants import PermissionAction
from app.shared.base_document import BaseDocument

_TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"  # "HH:MM", 24-hour


class Role(BaseDocument):
    name: str
    description: str | None = None
    # status (BaseDocument): active/inactive


class Permission(BaseDocument):
    """Catalog entry: describes a (module, resource) pair and which actions are
    conceptually applicable to it. Not a grant — see RolePermission for that.
    `module`/`resource` are free text by design (data-driven, not hardcoded).
    """

    module: str
    resource: str
    actions: list[str] = Field(default_factory=list)
    label: str | None = None


class RolePermission(BaseDocument):
    """A grant: `role_id` may perform `granted_actions` (subset of the referenced
    Permission's `actions`) on that (module, resource), optionally scoped to specific
    departments/branches. `None` scope = unrestricted (applies everywhere).
    """

    role_id: str
    permission_id: str
    granted_actions: list[str] = Field(default_factory=list)
    department_ids: list[str] | None = None
    branch_ids: list[str] | None = None


class EmployeeRole(BaseDocument):
    employee_id: str
    role_id: str


class TemporaryAccessGrant(BaseModel):
    permission_id: str
    actions: list[str] = Field(default_factory=list)


class TemporaryAccess(BaseDocument):
    employee_id: str
    grants: list[TemporaryAccessGrant]
    start_date: datetime
    end_date: datetime
    start_time: str = Field(pattern=_TIME_PATTERN)
    end_time: str = Field(pattern=_TIME_PATTERN)
    reason: str
    # status (BaseDocument): active/revoked — "expired" is never stored, only ever
    # evaluated lazily at permission-check time (see decision log for Module 3).


class AllowedLocation(BaseModel):
    latitude: float
    longitude: float


class GeoException(BaseDocument):
    employee_id: str
    allowed_location: AllowedLocation
    radius_meters: float
    start_date: datetime
    end_date: datetime
    start_time: str = Field(pattern=_TIME_PATTERN)
    end_time: str = Field(pattern=_TIME_PATTERN)
    reason: str
    # status (BaseDocument): active/revoked


def is_valid_action(action: str) -> bool:
    return action in PermissionAction.ALL
