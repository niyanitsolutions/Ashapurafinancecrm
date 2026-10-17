"""Read-only by default. Never loads CRM .env or accepts a production database."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError

from app.core.exceptions import AppError
from app.features.voice_assistant.staging_migration import apply_indexes, inspect_indexes


async def run(args: argparse.Namespace) -> int:
    if not args.database.startswith("voice_staging_"):
        raise ValueError("Only an isolated voice_staging_ database is allowed.")
    uri = os.environ.get("VOICE_STAGING_MONGO_URI")
    if not uri:
        raise ValueError("Set VOICE_STAGING_MONGO_URI in the secure process environment.")
    client = AsyncIOMotorClient(uri, tz_aware=True, serverSelectionTimeoutMS=5000)
    try:
        db = client[args.database]
        result = await apply_indexes(db, args.backup_reference or "") if args.apply else await inspect_indexes(db)
        print(json.dumps(result, default=str, indent=2))
        return 0 if result["passed"] else 1
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--apply", action="store_true", help="Explicitly apply additive staging indexes; never deletes data")
    parser.add_argument("--backup-reference")
    try:
        raise SystemExit(asyncio.run(run(parser.parse_args())))
    except (AppError, PyMongoError, ValueError, OSError):
        # Driver exceptions can contain connection details. Do not print URI,
        # credentials, duplicate keys/customer IDs or raw database diagnostics.
        print("Staging index check failed. Verify isolated database, secure connection, backup evidence and index conflicts with the operator.", file=sys.stderr)
        raise SystemExit(1) from None
