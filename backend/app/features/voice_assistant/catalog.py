from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.features.access_control.models import Permission
from app.features.dashboard.models import NavItem
from app.features.voice_assistant.campaign_service import ensure_campaign_indexes
from app.features.voice_assistant.recording_service import ensure_recording_indexes
from app.features.voice_assistant.repository import ensure_voice_indexes
from app.features.voice_assistant.smartflo_service import ensure_smartflo_indexes


async def initialize_voice_module(db: AsyncIOMotorDatabase[Any]) -> None:
    """Register shipped navigation on startup, preserving existing administrative choices."""
    await ensure_voice_indexes(db)
    await ensure_smartflo_indexes(db)
    await ensure_recording_indexes(db)
    await ensure_campaign_indexes(db)
    await seed_voice_catalog(db)


async def seed_voice_catalog(db: AsyncIOMotorDatabase[Any]) -> None:
    """Additive, idempotent catalog migration; grants are never assigned automatically."""
    for resource, actions, label in [
        ("calls", ["view", "create", "edit"], "AI Voice Calls"),
        ("knowledge", ["view", "create", "edit", "approve"], "AI Voice Knowledge"),
        ("recordings", ["view", "create", "edit", "download", "delete"], "AI Voice Recordings"),
        ("campaigns", ["view", "create", "edit", "import"], "AI Voice Campaigns"),
    ]:
        doc = Permission(module="voice_assistant", resource=resource, actions=actions, label=label)
        await db.permissions.update_one(
            {"module": "voice_assistant", "resource": resource},
            {"$setOnInsert": doc.model_dump(by_alias=True, exclude={"id"})},
            upsert=True,
        )
    nav = NavItem(
        key="voice_assistant",
        label="AI Voice Assistant",
        route="/voice-assistant",
        order=47,
        required_module="voice_assistant",
        required_resource="calls",
        required_action="view",
    )
    await db.nav_items.update_one(
        {"key": nav.key},
        {
            "$setOnInsert": nav.model_dump(by_alias=True, exclude={"id"}),
        },
        upsert=True,
    )
