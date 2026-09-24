from typing import Annotated, Any

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.features.access_control.permission_engine import PermissionEngine
from app.features.access_control.repository import PermissionRepository
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
    resources = ["advisors"]
    advisor_permission = await PermissionRepository(db).find_by_module_resource(
        "insurance_management", "advisors"
    )
    if advisor_permission is None:
        resources.append("applications")
    agency_child = await PermissionRepository(db).find_by_module_resource(
        "insurance_management", "recruitment.agency_code"
    )
    resources.append("recruitment.agency_code" if agency_child is not None else "recruitment")
    for resource in resources:
        if await engine.has_permission(user, module="insurance_management", resource=resource, action="view"):
            return user
    raise ForbiddenError("Missing Insurance Management view permission.")


InsuranceManagementReadDep = Annotated[User, Depends(require_insurance_management_read_access)]


async def require_advisor_edit(
    actor: InsuranceManagementReadDep,
    db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)],
) -> User:
    engine = PermissionEngine(db)
    resources = ["advisors"]
    advisor_permission = await PermissionRepository(db).find_by_module_resource(
        "insurance_management", "advisors"
    )
    if advisor_permission is None:
        resources.append("applications")
    agency_child = await PermissionRepository(db).find_by_module_resource(
        "insurance_management", "recruitment.agency_code"
    )
    resources.append("recruitment.agency_code" if agency_child is not None else "recruitment")
    for resource in resources:
        if await engine.has_permission(actor, module="insurance_management", resource=resource, action="edit"):
            return actor
    raise ForbiddenError("Missing Advisor edit permission.")


AdvisorEditDep = Annotated[User, Depends(require_advisor_edit)]


async def require_advisor_business_edit(
    actor: InsuranceManagementReadDep,
    db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)],
) -> User:
    engine = PermissionEngine(db)
    resources = ["applications", "advisors"]
    agency_child = await PermissionRepository(db).find_by_module_resource(
        "insurance_management", "recruitment.agency_code"
    )
    resources.append("recruitment.agency_code" if agency_child is not None else "recruitment")
    for resource in resources:
        if await engine.has_permission(actor, module="insurance_management", resource=resource, action="edit"):
            return actor
    raise ForbiddenError("Missing Insurance business edit permission.")


AdvisorBusinessEditDep = Annotated[User, Depends(require_advisor_business_edit)]
