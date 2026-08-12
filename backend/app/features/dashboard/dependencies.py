"""Dashboard dependencies. Reuses Auth's `get_current_active_user` directly — every
endpoint here just needs "an authenticated Owner or Employee," same as Module 2's
self-service routes; per-widget/per-nav-item visibility is resolved inside the service,
not at the route-dependency level (unlike Settings, Module 4, where every action maps
to one fixed permission)."""

from typing import Annotated, Any

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.constants.roles import EMPLOYEE, OWNER
from app.core.exceptions import ForbiddenError
from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.dashboard.service import DashboardService


def require_staff(current_user: Annotated[User, Depends(get_current_active_user)]) -> User:
    # The docstring above already asserts "Owner or Employee" for every route in this
    # module, but `CurrentUserDep` alone never enforced it — a logged-in Customer or
    # Referral Partner could reach `/dashboard`, `/dashboard/nav`, etc. No actual
    # cross-tenant data escaped (every widget's `_scope_to_employee` returns a
    # sentinel for non-Employees, so values come back as 0), but it exposed internal
    # nav/route structure to roles that should never see it.
    if current_user.role not in (OWNER, EMPLOYEE):
        raise ForbiddenError("This action is restricted to Owner/Employee.")
    return current_user


CurrentUserDep = Annotated[User, Depends(require_staff)]


def get_dashboard_service(db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]) -> DashboardService:
    return DashboardService(db)
