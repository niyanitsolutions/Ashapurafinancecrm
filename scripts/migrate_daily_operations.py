"""Additive daily-operations catalog/index migration; select an isolated environment first.

Run from backend: .venv/Scripts/python.exe ../scripts/migrate_daily_operations.py
No records are backfilled and no access is granted. Production execution needs owner approval.
"""

import asyncio

from app.config.database import close_client, get_database
from app.features.daily_operations.catalog import install_catalog


async def main() -> None:
    try:
        await install_catalog(get_database())
        print(
            "Daily operations catalog and indexes installed; employee grants unchanged."
        )
    finally:
        await close_client()


if __name__ == "__main__":
    asyncio.run(main())
