"""Attendance-only dry run by default. Explicit isolated target required."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.features.daily_operations.reconciliation import reconcile_attendance
from motor.motor_asyncio import AsyncIOMotorClient


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    client: AsyncIOMotorClient[Any] = AsyncIOMotorClient(args.uri, tz_aware=True)
    try:
        report = await reconcile_attendance(client[args.database], apply=args.apply)
        print(json.dumps(report, indent=2))
        if report["status"] == "BLOCKED":
            raise SystemExit(2)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
