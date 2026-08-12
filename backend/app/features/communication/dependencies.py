from typing import Annotated, Any

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.features.communication.service import CommunicationService

__all__ = ["get_communication_service"]


def get_communication_service(db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]) -> CommunicationService:
    return CommunicationService(db)
