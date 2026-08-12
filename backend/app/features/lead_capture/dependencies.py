from typing import Annotated, Any

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.features.lead_capture.service import LeadCaptureService

__all__ = ["get_lead_capture_service"]


def get_lead_capture_service(db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]) -> LeadCaptureService:
    return LeadCaptureService(db)
