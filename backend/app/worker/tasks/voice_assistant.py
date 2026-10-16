from typing import Any

from app.config.database import get_database
from app.config.redis import get_redis
from app.features.voice_assistant.campaign_service import CampaignService
from app.features.voice_assistant.recording_service import RecordingService
from app.features.voice_assistant.service import VoiceService
from app.features.voice_assistant.speech_jobs import SpeechJobs


async def verify_local_voice_speech(ctx: dict[str, Any]) -> int:
    """Explicit Owner-requested speech jobs only; never install, download or call."""
    db = ctx.get("voice_db")
    return await SpeechJobs(db if db is not None else get_database()).sweep()


async def reconcile_mock_voice_calls(ctx: dict[str, Any]) -> int:
    """Persistent deadlines recover on worker restart. This job never invokes telephony."""
    db = ctx.get("voice_db")
    return await VoiceService(db if db is not None else get_database()).sweep()


async def reconcile_voice_recordings(ctx: dict[str, Any]) -> dict[str, int]:
    """Recover interrupted imports and delete expired artifacts, never capture/call."""
    db = ctx.get("voice_db")
    return await RecordingService(db if db is not None else get_database()).reconcile()


async def process_voice_campaign_previews(ctx: dict[str, Any]) -> dict[str, int]:
    """Durable dry-run eligibility jobs only; no telephony or messaging invocation."""
    db = ctx.get("voice_db")
    redis = ctx.get("redis")
    return await CampaignService(
        db if db is not None else get_database(), redis if redis is not None else get_redis()
    ).sweep()
