"""Only internal inbox delivery; no SMS, email or financial retries."""

from typing import Any

from app.config.database import get_database
from app.features.referral_partner_management.notifications import notify_updated_agreements


async def notify_partner_agreements(
    ctx: dict[Any, Any], *args: Any, **kwargs: Any
) -> dict[str, int]:
    return await notify_updated_agreements(get_database())
