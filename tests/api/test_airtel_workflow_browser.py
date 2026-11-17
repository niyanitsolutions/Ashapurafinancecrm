from test_airtel_transport import confirmed_auth_stub  # noqa: F401

# ruff: noqa: F811
"""Opt-in local browser + real API/MongoDB, with Airtel completely mocked."""

import asyncio
import json
import os
from pathlib import Path

import pytest
import uvicorn
from app.config.database import get_database
from app.features.communication import airtel_iq
from app.features.integrations.indexes import ensure_integrations_indexes
from test_airtel_configuration import create
from test_airtel_transport import CONFIG
from test_invoice_mongo_integration import real_invoice_db  # noqa: F401


@pytest.mark.skipif(
    os.environ.get("AFS_AIRTEL_BROWSER_CHECK") != "1",
    reason="Opt-in local browser check",
)
async def test_airtel_owner_workflow_browser(
    client, mock_db, owner_headers, real_invoice_db, monkeypatch
):
    ids = []
    for _ in range(2):
        row = await create(
            client, mock_db, owner_headers, CONFIG | {"contract_confirmed": "false"}
        )
        ids.append(row["id"])
    db = real_invoice_db
    for name in await mock_db.list_collection_names():
        rows = await mock_db[name].find({}).to_list(None)
        if rows:
            await db[name].insert_many(rows)
    await ensure_integrations_indexes(db)
    received = []

    async def gateway(body, authorization):
        received.append(body["message"].split(" is ")[1].split(".")[0])
        return 200, None

    monkeypatch.setattr(airtel_iq, "request", gateway)
    app = client._transport.app
    app.dependency_overrides[get_database] = lambda: db
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=18769, log_level="error", lifespan="off"
        )
    )
    task = asyncio.create_task(server.serve())
    process = None
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.05)
        assert server.started
        root = Path(__file__).resolve().parents[2]
        process = await asyncio.create_subprocess_exec(
            str(root / "frontend/node_modules/.cache/voice-node22/node.exe"),
            str(root / "scripts/airtel-workflow-ui-check.mjs"),
            cwd=root,
            env={
                **os.environ,
                "AFS_TEST_AUTH": owner_headers["Authorization"],
                "AFS_TEST_CONFIGS": json.dumps(ids),
            },
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        async def journey():
            output = []
            while line := await process.stdout.readline():
                output.append(line.decode(errors="replace"))
                if line.startswith(b"NEED_MOCK_OTP"):
                    assert received
                    process.stdin.write((received[-1] + "\n").encode())
                    await process.stdin.drain()
            await process.wait()
            return "".join(output)

        output = await asyncio.wait_for(journey(), 180)
        assert process.returncode == 0, output
        assert len(received) == 2
        assert (
            await db.integration_configs.count_documents(
                {"airtel_test_verified_at": {"$ne": None}}
            )
            == 2
        )
        print(output)
    finally:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        server.should_exit = True
        await task
        app.dependency_overrides[get_database] = lambda: mock_db
