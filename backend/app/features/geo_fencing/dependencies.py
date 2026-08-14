from typing import Annotated, Any

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.features.geo_fencing.service import GeoFencingService


def get_geo_fencing_service(db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]) -> GeoFencingService:
    return GeoFencingService(db)
