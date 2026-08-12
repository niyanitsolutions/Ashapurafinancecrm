from typing import Annotated, Any

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.customer.dependencies import require_staff
from app.features.reminders.service import RemindersService

__all__ = ["CurrentUserDep", "StaffDep", "get_reminders_service"]

CurrentUserDep = Annotated[User, Depends(get_current_active_user)]
StaffDep = Annotated[User, Depends(require_staff)]


def get_reminders_service(db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]) -> RemindersService:
    return RemindersService(db)
