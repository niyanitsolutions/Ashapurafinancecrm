"""The actual RBAC engine: resolves whether an authenticated user may perform `action` on
`resource` within `module`. This is new, reusable infrastructure for FUTURE modules to
adopt (e.g. `Depends(require_permission("loan_management", "leads", "view"))`) — Module 2's
existing endpoints are deliberately NOT retrofitted to use this, per the Module 2 freeze.

Owner bypasses this engine entirely (superuser, matching the rest of the system's
convention). Customer/Referral Partner are never covered by it — this system is
staff-only (Owner/Employee), consistent with the whole Module 3 brief being about
Employee ↔ Role assignment, departments, branches.
"""

from typing import Annotated, Any

from fastapi import Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.constants.roles import EMPLOYEE, OWNER
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.features.access_control.constants import PermissionAction
from app.features.access_control.repository import (
    EmployeeRoleRepository,
    PermissionRepository,
    RolePermissionRepository,
    TemporaryAccessRepository,
)
from app.features.auth.models import ACCOUNT_STATUS_ACTIVE, User
from app.features.auth.repository import UserRepository
from app.features.employee.repository import EmployeeRepository
from app.middleware.auth import get_current_subject
from app.utils.datetime import now_ist, within_daily_window
from app.utils.helpers import is_valid_object_id, to_object_id


class PermissionEngine:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self._employees = EmployeeRepository(db)
        self._employee_roles = EmployeeRoleRepository(db)
        self._role_permissions = RolePermissionRepository(db)
        self._permissions = PermissionRepository(db)
        self._temporary_access = TemporaryAccessRepository(db)

    async def has_permission(
        self,
        user: User,
        *,
        module: str,
        resource: str,
        action: str,
        department_id: str | None = None,
        branch_id: str | None = None,
    ) -> bool:
        if user.role == OWNER:
            return True
        if user.role != EMPLOYEE:
            return False

        employee = await self._employees.find_by_user_id(user.require_id())
        if employee is None:
            return False
        employee_id = employee.require_id()

        permission = await self._permissions.find_by_module_resource(module, resource)
        if permission is None or action not in permission.actions:
            return False

        permission_id = permission.require_id()

        # Create/Edit must never independently grant access without View (the CRM's
        # required permission hierarchy) — checked here, once, so every caller of
        # has_permission/require_permission gets it for free, rather than relying on
        # the frontend hiding Create/Edit buttons.
        if action in (PermissionAction.CREATE, PermissionAction.EDIT) and PermissionAction.VIEW in permission.actions:
            has_view = await self._check_effective_role_grants(
                employee_id, permission, PermissionAction.VIEW, department_id, branch_id
            ) or await self._check_temporary_access(employee_id, permission_id, PermissionAction.VIEW)
            if not has_view:
                return False

        if await self._check_effective_role_grants(employee_id, permission, action, department_id, branch_id):
            return True
        return await self._check_temporary_access(employee_id, permission_id, action)

    async def get_accessible_modules(self, user: User) -> list[str]:
        """Derived, not stored — the set of modules an employee has any granted action
        in, via their roles. Used for future nav/menu filtering."""
        if user.role == OWNER:
            return ["*"]
        if user.role != EMPLOYEE:
            return []

        employee = await self._employees.find_by_user_id(user.require_id())
        if employee is None:
            return []

        modules: set[str] = set()
        for permission in await self._permissions.find_many({}, limit=1000):
            if permission.module in modules or PermissionAction.VIEW not in permission.actions:
                continue
            if await self.has_permission(
                user,
                module=permission.module,
                resource=permission.resource,
                action=PermissionAction.VIEW,
            ):
                modules.add(permission.module)
        return sorted(modules)

    async def _check_role_grants(
        self, employee_id: str, permission_id: str, action: str, department_id: str | None, branch_id: str | None
    ) -> bool:
        employee_roles = await self._employee_roles.find_for_employee(employee_id)
        if not employee_roles:
            return False
        role_ids = [er.role_id for er in employee_roles]
        grants = await self._role_permissions.find_for_roles(role_ids)
        for grant in grants:
            if grant.permission_id != permission_id or action not in grant.granted_actions:
                continue
            if grant.department_ids is not None and (department_id is None or department_id not in grant.department_ids):
                continue
            if grant.branch_ids is not None and (branch_id is None or branch_id not in grant.branch_ids):
                continue
            return True
        return False

    async def _check_effective_role_grants(
        self, employee_id: str, permission: Any, action: str,
        department_id: str | None, branch_id: str | None,
    ) -> bool:
        """Resolve child override -> parent default independently for each role."""
        assignments = await self._employee_roles.find_for_employee(employee_id)
        if not assignments:
            return False
        role_ids = [assignment.role_id for assignment in assignments]
        grants = await self._role_permissions.find_for_roles(role_ids)
        grants_by_role: dict[str, dict[str, Any]] = {}
        for grant in grants:
            grants_by_role.setdefault(grant.role_id, {})[grant.permission_id] = grant

        catalog = await self._permissions.find_by_module(permission.module)
        by_resource = {item.resource: item for item in catalog}

        def applies(grant: Any) -> bool:
            if grant.department_ids is not None and (
                department_id is None or department_id not in grant.department_ids
            ):
                return False
            return not (
                grant.branch_ids is not None
                and (branch_id is None or branch_id not in grant.branch_ids)
            )

        def root_for(node: Any) -> Any:
            seen: set[str] = set()
            current = node
            while current.parent_resource and current.resource not in seen:
                seen.add(current.resource)
                parent = by_resource.get(current.parent_resource)
                if parent is None:
                    break
                current = parent
            return current

        def decision(node: Any, role_grants: dict[str, Any], seen: set[str] | None = None) -> bool:
            visited = set() if seen is None else seen
            node_id = node.require_id()
            if node_id in visited:
                return False
            visited.add(node_id)
            grant = role_grants.get(node_id)
            if grant is not None and applies(grant):
                if action in grant.denied_actions:
                    return False
                if action in grant.granted_actions:
                    return True
            if node.parent_resource:
                parent = by_resource.get(node.parent_resource)
                if parent is not None:
                    return decision(parent, role_grants, visited)
            return False

        root = root_for(permission)
        for role_id in role_ids:
            role_grants = grants_by_role.get(role_id, {})
            root_grant = role_grants.get(root.require_id())
            if root_grant is not None and applies(root_grant) and root_grant.module_enabled is False:
                continue
            if decision(permission, role_grants):
                return True
        return False

    async def _check_temporary_access(self, employee_id: str, permission_id: str, action: str) -> bool:
        # A Temporary Access grant's daily window is an IST business-hours window (the
        # Owner enters "09:00"-"18:00" meaning India time) — must be evaluated against
        # IST "now", not UTC. See app/utils/datetime.py's within_daily_window docstring.
        now = now_ist()
        active = await self._temporary_access.find_active_for_employee(employee_id)
        for grant_set in active:
            if not within_daily_window(grant_set.start_date, grant_set.end_date, grant_set.start_time, grant_set.end_time, now):
                continue
            for grant in grant_set.grants:
                if grant.permission_id == permission_id and action in grant.actions:
                    return True
        return False


def require_permission(module: str, resource: str, action: str) -> Any:
    async def dependency(
        subject: Annotated[str, Depends(get_current_subject)],
        db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)],
    ) -> User:
        user = await UserRepository(db).find_by_id(subject)
        if user is None:
            raise ForbiddenError("Account no longer exists.")
        # `get_current_active_user` (the plain-auth dependency) already enforces this —
        # this is the parallel permission-gated dependency, which read the user straight
        # from the repository and never re-checked status. A deactivated/disabled
        # Employee's outstanding access token (up to 15 min old) would otherwise keep
        # working on every `require_permission`-gated route — loans, insurance, leads,
        # reports, settings — even though `/employees/me` and friends already reject them.
        if user.status != ACCOUNT_STATUS_ACTIVE:
            raise UnauthorizedError("Account is not active.")

        engine = PermissionEngine(db)
        if not await engine.has_permission(user, module=module, resource=resource, action=action):
            raise ForbiddenError(f"Missing permission: {module}:{resource}:{action}")
        return user

    return Depends(dependency)


def require_any_permission(module: str, resource: str, actions: tuple[str, ...]) -> Any:
    """Same contract as `require_permission`, satisfied if the caller holds ANY ONE of
    `actions` on `module:resource` — e.g. Leads' Reject Lead action is authorized by
    either the dedicated `reject` grant or the general `edit` grant already used to
    manage a lead, so an employee who can already move/update a lead doesn't need a
    second, separate permission just to reject it. Not a new permission of its own —
    just an alternate authorization dependency over the existing action set."""

    async def dependency(
        subject: Annotated[str, Depends(get_current_subject)],
        db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)],
    ) -> User:
        user = await UserRepository(db).find_by_id(subject)
        if user is None:
            raise ForbiddenError("Account no longer exists.")
        if user.status != ACCOUNT_STATUS_ACTIVE:
            raise UnauthorizedError("Account is not active.")

        engine = PermissionEngine(db)
        for action in actions:
            if await engine.has_permission(user, module=module, resource=resource, action=action):
                return user
        raise ForbiddenError(f"Missing permission: {module}:{resource}:{' or '.join(actions)}")

    return Depends(dependency)


def require_stage_permission(
    module: str,
    parent_resource: str,
    action: str,
    *,
    collection: str,
    path_id: str,
    status_field: str,
    query_status: str | None = None,
    discriminator: tuple[str, str] | None = None,
    default_stage: str | None = None,
    require_all_children_without_stage: bool = False,
    legacy_parent_resources: tuple[str, ...] = (),
    legacy_parent_action: str | None = None,
) -> Any:
    """Authorize a workflow request against its current tab/stage.

    During rollout, a missing child catalog row deliberately falls back to the existing
    parent permission. Once the idempotent hierarchy migration creates the child row,
    inheritance and explicit overrides are enforced for list, detail, and mutation
    requests alike.
    """

    async def dependency(
        request: Request,
        subject: Annotated[str, Depends(get_current_subject)],
        db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)],
    ) -> User:
        user = await UserRepository(db).find_by_id(subject)
        if user is None:
            raise ForbiddenError("Account no longer exists.")
        if user.status != ACCOUNT_STATUS_ACTIVE:
            raise UnauthorizedError("Account is not active.")

        stage = request.query_params.get(query_status) if query_status else None
        record_id = request.path_params.get(path_id)
        if stage is None and record_id and is_valid_object_id(record_id):
            query: dict[str, Any] = {"_id": to_object_id(record_id), "is_deleted": False}
            if discriminator:
                query[discriminator[0]] = discriminator[1]
            document = await db[collection].find_one(query, {status_field: 1})
            if document is not None:
                stage = document.get(status_field)
        stage = stage or default_stage

        engine = PermissionEngine(db)
        if stage is None and require_all_children_without_stage:
            children = [
                permission for permission in await PermissionRepository(db).find_by_module(module)
                if permission.parent_resource == parent_resource and action in permission.actions
            ]
            if children:
                for child_permission in children:
                    if not await engine.has_permission(
                        user, module=module, resource=child_permission.resource, action=action
                    ):
                        raise ForbiddenError(
                            f"Missing permission: {module}:{child_permission.resource}:{action}"
                        )
                return user

        resource = parent_resource
        if stage:
            child_resource = f"{parent_resource}.{stage}"
            stage_permission = await PermissionRepository(db).find_by_module_resource(module, child_resource)
            if stage_permission is not None and action in stage_permission.actions:
                resource = child_resource

        if await engine.has_permission(user, module=module, resource=resource, action=action):
            return user

        # Before the hierarchy migration, some workflows deliberately shared a broader
        # entry permission or used Edit for creation. Keep those exact legacy contracts
        # only while no stage child exists; migrated/new hierarchical grants remain strict.
        if resource == parent_resource:
            for legacy_resource in legacy_parent_resources:
                if await engine.has_permission(
                    user, module=module, resource=legacy_resource, action=action
                ):
                    return user
            if legacy_parent_action and await engine.has_permission(
                user, module=module, resource=parent_resource, action=legacy_parent_action
            ):
                return user

        raise ForbiddenError(f"Missing permission: {module}:{resource}:{action}")

    return Depends(dependency)


def require_any_stage_permission(
    module: str,
    parent_resource: str,
    actions: tuple[str, ...],
    **stage_options: Any,
) -> Any:
    """Stage-aware counterpart to :func:`require_any_permission`."""

    async def dependency(
        request: Request,
        subject: Annotated[str, Depends(get_current_subject)],
        db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)],
    ) -> User:
        user = await UserRepository(db).find_by_id(subject)
        if user is None:
            raise ForbiddenError("Account no longer exists.")
        if user.status != ACCOUNT_STATUS_ACTIVE:
            raise UnauthorizedError("Account is not active.")

        query_status = stage_options.get("query_status")
        stage = request.query_params.get(query_status) if query_status else None
        record_id = request.path_params.get(stage_options["path_id"])
        if stage is None and record_id and is_valid_object_id(record_id):
            query: dict[str, Any] = {"_id": to_object_id(record_id), "is_deleted": False}
            discriminator = stage_options.get("discriminator")
            if discriminator:
                query[discriminator[0]] = discriminator[1]
            document = await db[stage_options["collection"]].find_one(
                query, {stage_options["status_field"]: 1}
            )
            if document is not None:
                stage = document.get(stage_options["status_field"])
        stage = stage or stage_options.get("default_stage")

        child_resource: str | None = None
        child: Any | None = None
        if stage:
            child_resource = f"{parent_resource}.{stage}"
            child = await PermissionRepository(db).find_by_module_resource(module, child_resource)

        engine = PermissionEngine(db)
        for action in actions:
            resource = (
                child_resource
                if child is not None and child_resource is not None and action in child.actions
                else parent_resource
            )
            if await engine.has_permission(user, module=module, resource=resource, action=action):
                return user
        raise ForbiddenError(f"Missing permission: {module}:{resource}:{' or '.join(actions)}")

    return Depends(dependency)
