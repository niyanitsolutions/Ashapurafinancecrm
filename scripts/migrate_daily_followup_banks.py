"""Run from backend with the approved target configuration. Dry-run unless --apply."""

import argparse
import asyncio

from app.config.database import close_client, get_database
from app.features.daily_operations.bank_migration import migrate
from app.features.daily_operations.bank_options import install


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        db = get_database()
        if args.apply:
            await install(db)
        print(await migrate(db, apply=args.apply))
    finally:
        await close_client()


if __name__ == "__main__":
    asyncio.run(main())
