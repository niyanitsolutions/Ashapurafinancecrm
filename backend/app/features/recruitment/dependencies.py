from typing import Annotated, Any

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.features.recruitment.advisor_service import AdvisorService
from app.features.recruitment.service import RecruitmentService


def get_recruitment_service(db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]) -> RecruitmentService:
    return RecruitmentService(db)


def get_advisor_service(db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]) -> AdvisorService:
    return AdvisorService(db)
