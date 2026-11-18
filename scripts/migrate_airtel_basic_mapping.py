"""Approved target only. Dry-run by default; --apply updates mappings, never sends SMS."""

import argparse
import asyncio

from app.config.database import close_client, get_database
from app.features.integrations.airtel_migration import migrate


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        print(await migrate(get_database(), apply=args.apply))
    finally:
        await close_client()


if __name__ == "__main__":
    asyncio.run(main())
