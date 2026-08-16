"""Access Control business logic. Reads Module 2's `EmployeeRepository` to validate
`employee_id` references and resolve display names — read-only, no Module 2 file is
touched (per the Module 2 freeze).
"""

import logging
from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.constants.roles import OWNER
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.features.access_control.constants import (
    AccessGrantStatus,
    AuditEvent,
    PermissionAction,
    RoleStatus,
)
from app.features.access_control.models import (
    AllowedLocation,
    EmployeeRole,
    GeoException,
    Permission,
    Role,
    RolePermission,
    TemporaryAccess,
    TemporaryAccessGrant,
)
from app.features.access_control.permission_engine import PermissionEngine
from app.features.access_control.repository import (
    EmployeeRoleRepository,
    GeoExceptionRepository,
    PermissionRepository,
    RolePermissionRepository,
    RoleRepository,
    TemporaryAccessRepository,
)
from app.features.access_control.schemas import (
    CreateGeoExceptionRequest,
    CreatePermissionRequest,
    CreateRoleRequest,
    CreateTemporaryAccessRequest,
    SetRolePermissionsRequest,
    UpdateRoleRequest,
)
from app.features.auth.models import User
from app.features.employee.repository import EmployeeRepository
from app.features.geo_fencing.repository import GeoFenceRepository
from app.shared.audit_log import write_audit_log

logger = logging.getLogger(__name__)


def _date_to_datetime(value: Any) -> datetime:
    return datetime(value.year, value.month, value.day, tzinfo=UTC)


def _combine_date_time(value: Any, time_str: str) -> datetime:
    # `time_str` is already validated against `_TIME_PATTERN` ("HH:MM") at the schema
    # layer, so this parse can't fail here.
    hour, minute = (int(part) for part in time_str.split(":"))
    return datetime(value.year, value.month, value.day, hour, minute, tzinfo=UTC)


# UI-support curation only — NOT a re-hardcoding of the permission system itself
# (module/resource stay free-text/data-driven in the catalog, per this file's own
# constants.py docstring). This is just the fixed set of (module, resource, actions)
# pairs the main app's UI currently has buttons/routes for, so `get_my_permissions`
# knows what to check. Adding a ninth module to the UI later means adding one row here,
# not touching PermissionEngine or the catalog schema.
_MY_PERMISSIONS_CATALOG: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("leads", "leads", ("view", "create", "edit", "assign", "export")),
    ("customer", "customers", ("view", "create", "edit")),
    ("reminders", "tasks", ("view", "create", "edit")),
    ("reminders", "reminder_rules", ("view", "create", "edit")),
    ("loan_management", "applications", ("view", "edit", "assign", "approve")),
    ("insurance_management", "applications", ("view", "edit", "assign", "approve")),
    ("referral_partner_management", "partners", ("view", "create")),
    ("reporting", "reports", ("view", "export")),
    ("reporting", "scheduled_reports", ("view", "create", "edit", "delete")),
    ("communication", "templates", ("view", "create", "edit")),
    ("communication", "queue", ("view", "edit")),
    ("communication", "send", ("view", "create")),
    ("communication", "bulk", ("view", "create", "edit")),
)


class AccessControlService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self._db = db
        self._roles = RoleRepository(db)
        self._permissions = PermissionRepository(db)
        self._role_permissions = RolePermissionRepository(db)
        self._employee_roles = EmployeeRoleRepository(db)
        self._temporary_access = TemporaryAccessRepository(db)
        self._geo_exceptions = GeoExceptionRepository(db)
        self._geo_fences = GeoFenceRepository(db)
        self._employees = EmployeeRepository(db)
        self._engine = PermissionEngine(db)

    # ---------------------------------------------------------------- roles

    async def create_role(self, payload: CreateRoleRequest, owner: User) -> Role:
        if await self._roles.find_by_name(payload.name):
            raise ConflictError(f"Role '{payload.name}' already exists.")
        role = Role(name=payload.name, description=payload.description, created_by=owner.require_id())
        role_id = await self._roles.insert(role)
        await write_audit_log(self._db, event_type=AuditEvent.ROLE_CREATED, user_id=owner.require_id(), metadata={"role_id": role_id})
        return await self._roles.find_by_id(role_id) or role

    async def update_role(self, role_id: str, payload: UpdateRoleRequest, owner: User) -> Role:
        role = await self._get_role_or_404(role_id)
        updates: dict[str, Any] = {}
        if payload.name is not None and payload.name != role.name:
            if await self._roles.find_by_name(payload.name, exclude_id=role_id):
                raise ConflictError(f"Role '{payload.name}' already exists.")
            updates["name"] = payload.name
        if payload.description is not None:
            updates["description"] = payload.description
        if not updates:
            return role
        updated = await self._roles.update(role_id, updates, updated_by=owner.require_id())
        await write_audit_log(self._db, event_type=AuditEvent.ROLE_UPDATED, user_id=owner.require_id(), metadata={"role_id": role_id})
        return updated or role

    async def activate_role(self, role_id: str, owner: User) -> Role:
        await self._get_role_or_404(role_id)
        updated = await self._roles.update(role_id, {"status": RoleStatus.ACTIVE}, updated_by=owner.require_id())
        await write_audit_log(self._db, event_type=AuditEvent.ROLE_ACTIVATED, user_id=owner.require_id(), metadata={"role_id": role_id})
        assert updated is not None
        return updated

    async def deactivate_role(self, role_id: str, owner: User) -> Role:
        await self._get_role_or_404(role_id)
        updated = await self._roles.update(role_id, {"status": RoleStatus.INACTIVE}, updated_by=owner.require_id())
        await write_audit_log(self._db, event_type=AuditEvent.ROLE_DEACTIVATED, user_id=owner.require_id(), metadata={"role_id": role_id})
        assert updated is not None
        return updated

    async def duplicate_role(self, role_id: str, new_name: str, owner: User) -> Role:
        source = await self._get_role_or_404(role_id)
        if await self._roles.find_by_name(new_name):
            raise ConflictError(f"Role '{new_name}' already exists.")

        new_role = Role(name=new_name, description=source.description, created_by=owner.require_id())
        new_role_id = await self._roles.insert(new_role)

        source_grants = await self._role_permissions.find_for_role(role_id)
        for grant in source_grants:
            copy = RolePermission(
                role_id=new_role_id,
                permission_id=grant.permission_id,
                granted_actions=list(grant.granted_actions),
                department_ids=list(grant.department_ids) if grant.department_ids else None,
                branch_ids=list(grant.branch_ids) if grant.branch_ids else None,
                created_by=owner.require_id(),
            )
            await self._role_permissions.insert(copy)

        await write_audit_log(
            self._db, event_type=AuditEvent.ROLE_DUPLICATED, user_id=owner.require_id(),
            metadata={"source_role_id": role_id, "new_role_id": new_role_id},
        )
        return await self._roles.find_by_id(new_role_id) or new_role

    async def list_roles(self) -> list[Role]:
        return await self._roles.find_many({}, limit=500, sort=[("name", 1)])

    async def get_role(self, role_id: str) -> Role:
        return await self._get_role_or_404(role_id)

    # ---------------------------------------------------------------- permission catalog

    async def create_permission(self, payload: CreatePermissionRequest, owner: User) -> Permission:
        invalid = [a for a in payload.actions if a not in PermissionAction.ALL]
        if invalid:
            raise ValidationError(f"Unknown action(s): {', '.join(invalid)}")
        if await self._permissions.find_by_module_resource(payload.module, payload.resource):
            raise ConflictError(f"Permission for '{payload.module}:{payload.resource}' already exists.")
        permission = Permission(
            module=payload.module, resource=payload.resource, actions=payload.actions,
            label=payload.label, created_by=owner.require_id(),
        )
        permission_id = await self._permissions.insert(permission)
        await write_audit_log(
            self._db, event_type=AuditEvent.PERMISSION_CREATED, user_id=owner.require_id(),
            metadata={"permission_id": permission_id, "module": payload.module, "resource": payload.resource},
        )
        return await self._permissions.find_by_id(permission_id) or permission

    async def list_permissions(self) -> list[Permission]:
        return await self._permissions.find_many({}, limit=1000, sort=[("module", 1), ("resource", 1)])

    # ---------------------------------------------------------------- permission matrix

    async def get_role_permissions(self, role_id: str) -> list[RolePermission]:
        await self._get_role_or_404(role_id)
        return await self._role_permissions.find_for_role(role_id)

    async def _log_permission_validation_failure(self, role_id: str, reason: str, **details: Any) -> None:
        # Best-effort — a failure to resolve employee_ids for the log line must never
        # itself break the validation-error response being returned to the caller.
        try:
            employee_ids = [er.employee_id for er in await self._employee_roles.find_for_roles([role_id])]
        except Exception:  # noqa: BLE001 - logging-only, deliberately never propagates
            employee_ids = []
        logger.warning(
            "set_role_permissions rejected: %s | role_id=%s employee_ids=%s %s",
            reason, role_id, employee_ids, details,
        )

    async def set_role_permissions(self, role_id: str, payload: SetRolePermissionsRequest, owner: User) -> list[RolePermission]:
        """Bulk replace — the Permission Matrix save action (also what Employee Create/
        Edit's Business Modules section writes through, see
        frontend/src/features/employee/businessModules.ts). Validates every
        `granted_actions` entry against both the fixed action vocabulary and the
        referenced catalog entry's own `actions` (can't grant an action the resource
        doesn't support), and rejects a payload naming the same permission twice —
        anticipated client mistakes, always a 422 (this codebase's `ValidationError`),
        never an unhandled exception.

        Soft-deletes the role's current grants and inserts the new set. See
        indexes.py's `ensure_access_control_indexes` for why the underlying
        (role_id, permission_id) unique index had to become partial (scoped to
        is_deleted=False): re-saving a role's grants a second time — the normal case,
        not an edge case — re-inserts the same (role_id, permission_id) pair a
        soft-deleted row still holds; a full unique index doesn't know that row is
        deleted and raises DuplicateKeyError. The try/except below is a defensive
        second layer (e.g. two saves racing on the same role), not the fix itself.
        """
        await self._get_role_or_404(role_id)

        seen_permission_ids: set[str] = set()
        resolved: list[RolePermission] = []
        for grant in payload.grants:
            if grant.permission_id in seen_permission_ids:
                await self._log_permission_validation_failure(
                    role_id, "duplicate permission_id in payload", permission_id=grant.permission_id
                )
                raise ValidationError(f"Duplicate permission_id '{grant.permission_id}' in request.")
            seen_permission_ids.add(grant.permission_id)

            permission = await self._permissions.find_by_id(grant.permission_id)
            if permission is None:
                await self._log_permission_validation_failure(
                    role_id, "unknown permission_id", permission_id=grant.permission_id
                )
                raise ValidationError(f"Unknown permission_id '{grant.permission_id}'.")
            invalid = [a for a in grant.granted_actions if a not in permission.actions]
            if invalid:
                await self._log_permission_validation_failure(
                    role_id, "action(s) not available for resource", permission_id=grant.permission_id,
                    module=permission.module, resource=permission.resource, invalid_actions=invalid,
                )
                raise ValidationError(f"Action(s) {invalid} not available for '{permission.module}:{permission.resource}'.")
            resolved.append(
                RolePermission(
                    role_id=role_id, permission_id=grant.permission_id, granted_actions=grant.granted_actions,
                    department_ids=grant.department_ids, branch_ids=grant.branch_ids, created_by=owner.require_id(),
                )
            )

        existing = await self._role_permissions.find_for_role(role_id)
        for old in existing:
            await self._role_permissions.soft_delete(old.require_id(), deleted_by=owner.require_id())
        try:
            for new_grant in resolved:
                await self._role_permissions.insert(new_grant)
        except DuplicateKeyError as exc:
            await self._log_permission_validation_failure(
                role_id, "duplicate key on insert despite pre-checks (concurrent save?)",
                permission_ids=[g.permission_id for g in resolved],
            )
            raise ConflictError("This role's permissions were just changed elsewhere — please retry.") from exc

        await write_audit_log(
            self._db, event_type=AuditEvent.ROLE_PERMISSIONS_UPDATED, user_id=owner.require_id(),
            metadata={"role_id": role_id, "grant_count": len(resolved)},
        )
        return await self._role_permissions.find_for_role(role_id)

    # ---------------------------------------------------------------- employee <-> role assignment

    async def assign_role(self, role_id: str, employee_id: str, owner: User) -> EmployeeRole:
        await self._get_role_or_404(role_id)
        if await self._employees.find_by_id(employee_id) is None:
            raise ValidationError("Unknown employee_id.")
        if await self._employee_roles.find_one(employee_id, role_id) is not None:
            raise ConflictError("Employee already has this role.")

        assignment = EmployeeRole(employee_id=employee_id, role_id=role_id, created_by=owner.require_id())
        assignment_id = await self._employee_roles.insert(assignment)
        await write_audit_log(
            self._db, event_type=AuditEvent.ROLE_ASSIGNED, user_id=owner.require_id(),
            metadata={"role_id": role_id, "employee_id": employee_id},
        )
        return await self._employee_roles.find_by_id(assignment_id) or assignment

    async def remove_role(self, role_id: str, employee_id: str, owner: User) -> None:
        assignment = await self._employee_roles.find_one(employee_id, role_id)
        if assignment is None:
            raise NotFoundError("Employee does not have this role.")
        await self._employee_roles.soft_delete(assignment.require_id(), deleted_by=owner.require_id())
        await write_audit_log(
            self._db, event_type=AuditEvent.ROLE_REMOVED, user_id=owner.require_id(),
            metadata={"role_id": role_id, "employee_id": employee_id},
        )

    async def list_employee_roles(self, employee_id: str) -> list[EmployeeRole]:
        if await self._employees.find_by_id(employee_id) is None:
            raise NotFoundError("Employee not found.")
        return await self._employee_roles.find_for_employee(employee_id)

    async def get_accessible_modules(self, user: User) -> list[str]:
        return await self._engine.get_accessible_modules(user)

    # ---------------------------------------------------------------- temporary access

    async def create_temporary_access(self, payload: CreateTemporaryAccessRequest, owner: User) -> TemporaryAccess:
        if await self._employees.find_by_id(payload.employee_id) is None:
            raise ValidationError("Unknown employee_id.")
        for grant in payload.grants:
            permission = await self._permissions.find_by_id(grant.permission_id)
            if permission is None:
                raise ValidationError(f"Unknown permission_id '{grant.permission_id}'.")
            invalid = [a for a in grant.actions if a not in permission.actions]
            if invalid:
                raise ValidationError(f"Action(s) {invalid} not available for '{permission.module}:{permission.resource}'.")
        if payload.end_date < payload.start_date:
            raise ValidationError("end_date must not be before start_date.")

        temp_access = TemporaryAccess(
            employee_id=payload.employee_id,
            grants=[TemporaryAccessGrant(permission_id=g.permission_id, actions=g.actions) for g in payload.grants],
            start_date=_date_to_datetime(payload.start_date),
            end_date=_date_to_datetime(payload.end_date),
            start_time=payload.start_time,
            end_time=payload.end_time,
            reason=payload.reason,
            status=AccessGrantStatus.ACTIVE,
            created_by=owner.require_id(),
        )
        temp_access_id = await self._temporary_access.insert(temp_access)
        await write_audit_log(
            self._db, event_type=AuditEvent.TEMPORARY_ACCESS_GRANTED, user_id=owner.require_id(),
            metadata={"employee_id": payload.employee_id, "temporary_access_id": temp_access_id},
        )
        return await self._temporary_access.find_by_id(temp_access_id) or temp_access

    async def revoke_temporary_access(self, temp_access_id: str, owner: User) -> TemporaryAccess:
        existing = await self._temporary_access.find_by_id(temp_access_id)
        if existing is None:
            raise NotFoundError("Temporary access grant not found.")
        updated = await self._temporary_access.update(temp_access_id, {"status": AccessGrantStatus.REVOKED}, updated_by=owner.require_id())
        await write_audit_log(
            self._db, event_type=AuditEvent.TEMPORARY_ACCESS_REVOKED, user_id=owner.require_id(),
            metadata={"temporary_access_id": temp_access_id},
        )
        return updated or existing

    async def list_temporary_access(self, employee_id: str | None) -> list[TemporaryAccess]:
        filters = {"employee_id": employee_id} if employee_id else {}
        return await self._temporary_access.find_many(filters, limit=500, sort=[("start_date", -1)])

    # ---------------------------------------------------------------- geo exceptions

    async def create_geo_exception(self, payload: CreateGeoExceptionRequest, owner: User) -> GeoException:
        if await self._employees.find_by_id(payload.employee_id) is None:
            raise ValidationError("Unknown employee_id.")
        # Full datetime comparison, not just dates — a same-day window with
        # end_time <= start_time (e.g. 09:00-09:00 or 18:00-09:00 same day) must be
        # rejected too, not just an outright end_date < start_date. The old date-only
        # check let an invalid same-day period through.
        start_at = _combine_date_time(payload.start_date, payload.start_time)
        end_at = _combine_date_time(payload.end_date, payload.end_time)
        if end_at <= start_at:
            raise ValidationError("The exception's valid-until date/time must be after its valid-from date/time.")

        latitude, longitude, radius_meters = payload.latitude, payload.longitude, payload.radius_meters
        if payload.geo_fence_id:
            fence = await self._geo_fences.find_by_id(payload.geo_fence_id)
            if fence is None:
                raise ValidationError("Unknown geo_fence_id.")
            latitude = latitude if latitude is not None else fence.latitude
            longitude = longitude if longitude is not None else fence.longitude
            radius_meters = radius_meters if radius_meters is not None else fence.radius_meters
        if latitude is None or longitude is None or radius_meters is None:
            raise ValidationError("latitude, longitude, and radius_meters are required when geo_fence_id is not provided.")

        geo_exception = GeoException(
            employee_id=payload.employee_id,
            geo_fence_id=payload.geo_fence_id,
            allowed_location=AllowedLocation(latitude=latitude, longitude=longitude),
            radius_meters=radius_meters,
            start_date=_date_to_datetime(payload.start_date),
            end_date=_date_to_datetime(payload.end_date),
            start_time=payload.start_time,
            end_time=payload.end_time,
            reason=payload.reason,
            activity=payload.activity,
            status=AccessGrantStatus.ACTIVE,
            created_by=owner.require_id(),
        )
        geo_exception_id = await self._geo_exceptions.insert(geo_exception)
        await write_audit_log(
            self._db, event_type=AuditEvent.GEO_EXCEPTION_GRANTED, user_id=owner.require_id(),
            metadata={"employee_id": payload.employee_id, "geo_exception_id": geo_exception_id},
        )
        return await self._geo_exceptions.find_by_id(geo_exception_id) or geo_exception

    async def revoke_geo_exception(self, geo_exception_id: str, owner: User) -> GeoException:
        existing = await self._geo_exceptions.find_by_id(geo_exception_id)
        if existing is None:
            raise NotFoundError("Geo exception not found.")
        updated = await self._geo_exceptions.update(geo_exception_id, {"status": AccessGrantStatus.REVOKED}, updated_by=owner.require_id())
        await write_audit_log(
            self._db, event_type=AuditEvent.GEO_EXCEPTION_REVOKED, user_id=owner.require_id(),
            metadata={"geo_exception_id": geo_exception_id},
        )
        return updated or existing

    async def list_geo_exceptions(
        self, employee_id: str | None, *, skip: int = 0, limit: int = 500, sort: list[tuple[str, int]] | None = None
    ) -> tuple[list[GeoException], int]:
        filters = {"employee_id": employee_id} if employee_id else {}
        items = await self._geo_exceptions.find_many(filters, skip=skip, limit=limit, sort=sort or [("start_date", -1)])
        total = await self._geo_exceptions.count(filters)
        return items, total

    # ---------------------------------------------------------------- my-permissions (UI support)

    async def get_my_permissions(self, user: User) -> dict[str, list[str]]:
        """Tells the frontend which buttons/routes to show for the CURRENTLY
        authenticated user — e.g. `{"leads:leads": ["view", "create"]}` means this user
        can see and create Leads but not edit them. Reuses `PermissionEngine.has_permission`
        for every single check (the exact function every real write already goes
        through), so this can never drift from what's actually enforced — it is purely
        additive read-only UI support, never itself an authorization boundary. Owner
        gets an empty result on purpose: the frontend treats Owner as unrestricted and
        should never consult this for an Owner session."""
        if user.role == OWNER:
            return {}
        result: dict[str, list[str]] = {}
        for module, resource, actions in _MY_PERMISSIONS_CATALOG:
            granted = [a for a in actions if await self._engine.has_permission(user, module=module, resource=resource, action=a)]
            if granted:
                result[f"{module}:{resource}"] = granted
        return result

    # ---------------------------------------------------------------- internals

    async def _get_role_or_404(self, role_id: str) -> Role:
        role = await self._roles.find_by_id(role_id)
        if role is None:
            raise NotFoundError("Role not found.")
        return role
