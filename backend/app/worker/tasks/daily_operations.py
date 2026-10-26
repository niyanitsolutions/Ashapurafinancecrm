from typing import Any

from app.config.database import get_database
from app.features.daily_operations.notifications import deliver_notifications


async def check_daily_operations_notifications(_ctx: dict[Any, Any]) -> dict[str, int]:
    from app.features.auth.session_lifecycle import expire_sessions
    from app.features.daily_operations.follow_status import reconcile_statuses

    db = get_database()
    await reconcile_statuses(db)
    await expire_sessions(db)
    return await deliver_notifications(db)
