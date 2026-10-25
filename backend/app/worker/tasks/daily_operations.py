from typing import Any

from app.config.database import get_database
from app.features.daily_operations.notifications import deliver_notifications


async def check_daily_operations_notifications(_ctx: dict[Any, Any]) -> dict[str, int]:
    return await deliver_notifications(get_database())
