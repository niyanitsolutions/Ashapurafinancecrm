# ruff: noqa: F811
"""Real local API/MongoDB browser coverage with default auth blocking, no auth stub."""

import asyncio
import os
from pathlib import Path

import pytest
import uvicorn
from app.config.database import get_database
from app.features.communication import airtel_iq
from app.features.integrations.indexes import ensure_integrations_indexes
from test_airtel_authentication_pending import CREDENTIALS
from test_airtel_configuration import create
from test_invoice_mongo_integration import real_invoice_db  # noqa: F401


@pytest.mark.skipif(
    os.environ.get("AFS_AIRTEL_CREDENTIALS_BROWSER") != "1",
    reason="Opt-in isolated local browser",
)
async def test_secure_credentials_browser(
    client, mock_db, owner_headers, real_invoice_db, monkeypatch
):
    row = await create(client, mock_db, owner_headers, CREDENTIALS)
    db = real_invoice_db
    for name in await mock_db.list_collection_names():
        docs = await mock_db[name].find({}).to_list(None)
        if docs:
            await db[name].insert_many(docs)
    await ensure_integrations_indexes(db)

    async def forbidden(*args):
        raise AssertionError("No SMS request is allowed")

    monkeypatch.setattr(airtel_iq, "request", forbidden)
    app = client._transport.app
    app.dependency_overrides[get_database] = lambda: db
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=18770, log_level="error", lifespan="off"
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
            str(root / "scripts/airtel-credentials-ui-check.mjs"),
            cwd=root,
            env={
                **os.environ,
                "AFS_TEST_AUTH": owner_headers["Authorization"],
                "AFS_TEST_CONFIG_ID": row["id"],
            },
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await asyncio.wait_for(process.communicate(), 180)
        assert process.returncode == 0, output.decode(errors="replace")
        assert await db.sms_submissions.count_documents({}) == 0
        assert await db.integration_airtel_test_otps.count_documents({}) == 0
        print(output.decode())
    finally:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        server.should_exit = True
        await task
        app.dependency_overrides[get_database] = lambda: mock_db
