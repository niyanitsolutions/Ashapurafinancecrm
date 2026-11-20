"""Read-only company-database preflight. No automatic linking, merging or index writes.

Run from the repository root with the intended database environment already loaded:
  backend/.venv/Scripts/python.exe scripts/audit_unified_crm.py
Never pass connection strings as command-line arguments or publish environment files.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config.database import close_client, get_database
from app.features.leads.reconciliation import assess_relationships


async def main() -> None:
    try:
        print(
            json.dumps(
                await assess_relationships(get_database()), indent=2, sort_keys=True
            )
        )
    finally:
        await close_client()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:  # noqa: BLE001 -- connection/configuration errors can contain secrets
        print(
            "Read-only preflight failed. Review database access privately; no repair was attempted.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
