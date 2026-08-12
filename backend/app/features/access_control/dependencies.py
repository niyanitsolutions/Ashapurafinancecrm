"""Access Control auth dependencies. Reuses Auth's `get_current_active_user` and
Module 2's `require_owner` (a generic role gate, not employee business logic) —
read-only imports, no file under app/features/{auth,employee}/ is touched.
"""

from typing import Annotated, Any

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.features.access_control.service import AccessControlService
from app.features.auth.models import User
from app.features.employee.dependencies import (
    require_owner,
)

CurrentUserDep = Annotated[User, Depends(require_owner)]


def get_access_control_service(db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]) -> AccessControlService:
    return AccessControlService(db)
