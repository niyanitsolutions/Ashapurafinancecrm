from typing import Annotated, Any

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.features.leads.service import LeadService


def get_lead_service(db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]) -> LeadService:
    return LeadService(db)
