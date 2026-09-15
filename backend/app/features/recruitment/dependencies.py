from typing import Annotated, Any

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.features.access_control.permission_engine import PermissionEngine
from app.features.auth.models import ACCOUNT_STATUS_ACTIVE, User
from app.features.auth.repository import UserRepository
from app.features.recruitment.advisor_service import AdvisorService
from app.features.recruitment.service import RecruitmentService
from app.middleware.auth import get_current_subject


def get_recruitment_service(db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]) -> RecruitmentService:
    return RecruitmentService(db)


def get_advisor_service(db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]) -> AdvisorService:
    return AdvisorService(db)


async def require_insurance_management_read_access(
    subject: Annotated[str, Depends(get_current_subject)],
    db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)],
) -> User:
    """Authorize read-only Insurance Management workflow access.

    ``applications:view`` is the existing module-entry permission.  ``recruitment:view``
    remains valid as the more specific legacy grant.  This is deliberately read-only:
    Recruitment creation, updates, assignment and approval still use their existing
    action-level ``recruitment`` permissions.
    """
    user = await UserRepository(db).find_by_id(subject)
    if user is None:
        raise ForbiddenError("Account no longer exists.")
    if user.status != ACCOUNT_STATUS_ACTIVE:
        raise UnauthorizedError("Account is not active.")

    engine = PermissionEngine(db)
    for resource in ("applications", "recruitment"):
        if await engine.has_permission(user, module="insurance_management", resource=resource, action="view"):
            return user
    raise ForbiddenError("Missing Insurance Management view permission.")


InsuranceManagementReadDep = Annotated[User, Depends(require_insurance_management_read_access)]
