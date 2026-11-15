# ruff: noqa: F811
"""Opt-in Playwright + actual API + isolated loopback MongoDB browser check."""

import asyncio
import json
import os
from pathlib import Path

import pytest
import uvicorn
from app.config.database import get_database
from app.features.daily_operations.catalog import install_catalog
from test_daily_simple_entry import staff  # noqa: F401
from test_invoice_mongo_integration import real_invoice_db  # noqa: F401


@pytest.mark.skipif(
    os.environ.get("AFS_REELIGIBLE_BROWSER_CHECK") != "1",
    reason="Opt-in local browser check",
)
async def test_reeligible_worker_browser_journey(
    client, mock_db, staff, real_invoice_db, owner_headers
):
    db = real_invoice_db
    for name in await mock_db.list_collection_names():
        docs = await mock_db[name].find({}).to_list(None)
        if docs:
            await db[name].insert_many(docs)
    await install_catalog(db)
    # Synthetic users represent employees who completed their first-login setup.
    await db.users.update_many(
        {"role": "employee"}, {"$set": {"must_change_password": False}}
    )
    app = client._transport.app
    app.dependency_overrides[get_database] = lambda: db
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=18767, log_level="error", lifespan="off"
        )
    )
    task = asyncio.create_task(server.serve())
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.05)
        assert server.started
        root = Path(__file__).resolve().parents[2]
        env = {
            **os.environ,
            "AFS_TEST_ACTORS": json.dumps(
                [
                    staff[1]["Authorization"],
                    staff[3]["Authorization"],
                    owner_headers["Authorization"],
                ]
            ),
        }
        from datetime import datetime, timezone
        from unittest.mock import patch

        from app.features.daily_operations import reeligible
        from app.worker.tasks import daily_operations as worker

        process = await asyncio.create_subprocess_exec(
            str(root / "frontend/node_modules/.cache/voice-node22/node.exe"),
            str(root / "scripts/daily-reeligible-ui-check.mjs"),
            cwd=root,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        async def journey():
            output = []
            while line := await process.stdout.readline():
                output.append(line.decode(errors="replace"))
                if line.startswith(b"READY_FOR_WORKER"):
                    with (
                        patch.object(worker, "get_database", lambda: db),
                        patch.object(
                            reeligible,
                            "utc_now",
                            lambda: datetime(2026, 11, 19, 18, 30, tzinfo=timezone.utc),
                        ),
                    ):
                        await worker.check_daily_operations_notifications({})
                        await worker.check_daily_operations_notifications({})
                    process.stdin.write(b"processed\n")
                    await process.stdin.drain()
            await process.wait()
            return "".join(output)

        output = await asyncio.wait_for(journey(), 180)
        assert process.returncode == 0, output
        print(output)
        assert await db.daily_follow_ups.count_documents({}) == 2
        async for record in db.daily_follow_ups.find({}):
            assert (
                sum(event.get("automatic", False) for event in record["history"]) == 1
            )
    finally:
        server.should_exit = True
        await task
        app.dependency_overrides[get_database] = lambda: mock_db


@pytest.mark.skipif(
    os.environ.get("AFS_REELIGIBLE_BROWSER_CHECK") != "1",
    reason="Opt-in isolated MongoDB check",
)
async def test_real_mongo_concurrent_eligibility_transition(real_invoice_db):
    from datetime import datetime, timezone
    from unittest.mock import patch

    from app.features.daily_operations import reeligible
    from bson import ObjectId

    db = real_invoice_db
    await db.daily_follow_ups.create_index(
        [("is_deleted", 1), ("reeligible_state", 1), ("reeligible_date", 1)]
    )
    oid = ObjectId()
    await db.daily_follow_ups.insert_one(
        {
            "_id": oid,
            "is_deleted": False,
            "version": 1,
            "status": "custom:" + str(ObjectId()),
            "status_label": "Re-Eligible",
            "reeligible_state": "waiting",
            "reeligible_date": datetime(2026, 11, 19, 18, 30, tzinfo=timezone.utc),
            "history": [],
        }
    )
    with patch.object(
        reeligible, "utc_now", lambda: datetime(2026, 11, 20, tzinfo=timezone.utc)
    ):
        counts = await asyncio.gather(
            reeligible.reconcile_reeligible(db), reeligible.reconcile_reeligible(db)
        )
        assert sum(counts) == 1
    row = await db.daily_follow_ups.find_one({"_id": oid})
    assert (
        row["version"] == 2
        and len(row["history"]) == 1
        and row["reeligible_state"] == "ready"
    )
