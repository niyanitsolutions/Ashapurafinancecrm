"""Apply only the voice catalog migration, avoiding unrelated full seed operations.

From backend: .venv/bin/python ../scripts/voice_catalog.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config.database import close_client, get_database
from app.features.voice_assistant.catalog import seed_voice_catalog
from app.features.voice_assistant.repository import ensure_voice_indexes


async def main() -> None:
    try:
        db = get_database()
        await ensure_voice_indexes(db)
        await seed_voice_catalog(db)
        print("Voice indexes, permission catalog and navigation ensured. No grants or live calls enabled.")
    finally:
        await close_client()


if __name__ == "__main__":
    asyncio.run(main())
