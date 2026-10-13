from typing import Any

from app.config.database import get_database
from app.features.voice_assistant.service import VoiceService


async def reconcile_mock_voice_calls(ctx: dict[str, Any]) -> int:
    """Persistent deadlines recover on worker restart. This job never invokes telephony."""
    db = ctx.get("voice_db")
    return await VoiceService(db if db is not None else get_database()).sweep()
