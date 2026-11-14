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
from test_employee_hr import identity
from test_invoice_mongo_integration import real_invoice_db  # noqa: F401


@pytest.mark.skipif(
    os.environ.get("AFS_HR_BROWSER_CHECK") != "1",
    reason="Opt-in local browser check",
)
async def test_employee_hr_browser_journey(
    client, mock_db, master_data, real_invoice_db, owner_headers
):
    _employee, headers = await identity(client, owner_headers, master_data)
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
            app, host="127.0.0.1", port=18766, log_level="error", lifespan="off"
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
                    headers["Authorization"],
                    owner_headers["Authorization"],
                ]
            ),
        }
        process = await asyncio.create_subprocess_exec(
            str(root / "frontend/node_modules/.cache/voice-node22/node.exe"),
            str(root / "scripts/employee-hr-ui-check.mjs"),
            cwd=root,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await asyncio.wait_for(process.communicate(), 180)
        assert process.returncode == 0, output.decode(errors="replace")
        print(output.decode())
    finally:
        server.should_exit = True
        await task
        app.dependency_overrides[get_database] = lambda: mock_db
