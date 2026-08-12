"""Support module dependencies. Reuses Module 6B's `require_customer` role check directly
rather than duplicating it — a Support Ticket is always self-service for whoever's logged
in as a Customer, the same authorization shape Module 6B already defined.
"""

from typing import Annotated, Any

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.config.database import get_database
from app.config.redis import get_redis
from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.customer.dependencies import require_customer
from app.features.support.service import SupportTicketService

__all__ = ["CurrentUserDep", "get_support_ticket_service", "require_customer"]

CurrentUserDep = Annotated[User, Depends(get_current_active_user)]


def get_support_ticket_service(
    db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> SupportTicketService:
    return SupportTicketService(db, redis)
