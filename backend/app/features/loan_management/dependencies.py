from typing import Annotated, Any

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.customer.dependencies import require_customer
from app.features.loan_management.service import LoanCaseService

__all__ = ["CurrentUserDep", "CustomerDep", "get_loan_case_service"]

CurrentUserDep = Annotated[User, Depends(get_current_active_user)]
CustomerDep = Annotated[User, Depends(require_customer)]


def get_loan_case_service(db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]) -> LoanCaseService:
    return LoanCaseService(db)
