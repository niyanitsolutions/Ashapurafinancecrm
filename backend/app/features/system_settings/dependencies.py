"""Settings module dependencies. Authorization is handled per-route in router.py via
`Depends(require_permission("system_settings", resource, action))` (Access Control,
Module 3) — there's no single `CurrentUserDep` here the way Modules 2/3 had, since
different actions on different resources need different permission checks."""

from typing import Annotated, Any

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.features.system_settings.service import SystemSettingsService


def get_system_settings_service(db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]) -> SystemSettingsService:
    return SystemSettingsService(db)
