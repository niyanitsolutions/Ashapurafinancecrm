from typing import Annotated, Any

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.features.bin.service import BinService


def get_bin_service(db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]) -> BinService:
    return BinService(db)
