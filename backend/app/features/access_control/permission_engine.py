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

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.constants.roles import EMPLOYEE, OWNER
from app.core.exceptions import ForbiddenError, UnauthorizedError
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
from app.utils.datetime import utc_now, within_daily_window


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
        if await self._check_role_grants(employee_id, permission_id, action, department_id, branch_id):
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

        employee_roles = await self._employee_roles.find_for_employee(employee.require_id())
        role_ids = [er.role_id for er in employee_roles]
        if not role_ids:
            return []
        grants = await self._role_permissions.find_for_roles(role_ids)
        permission_ids = {g.permission_id for g in grants if g.granted_actions}
        modules: set[str] = set()
        for permission_id in permission_ids:
            permission = await self._permissions.find_by_id(permission_id)
            if permission is not None:
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

    async def _check_temporary_access(self, employee_id: str, permission_id: str, action: str) -> bool:
        now = utc_now()
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
