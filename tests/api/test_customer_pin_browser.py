# ruff: noqa: F811
"""Opt-in real local API/database browser journey; Airtel HTTP is mocked."""
import asyncio
import json
import os
from pathlib import Path

import pytest
import uvicorn
from app.features.auth import pin_service
from test_customer_pin_registration import registration  # noqa: F401
from test_pin_mongo_integration import pin_mongo  # noqa: F401


@pytest.mark.skipif(os.environ.get("AFS_CUSTOMER_PIN_BROWSER_CHECK") != "1", reason="Opt-in local browser")
async def test_customer_registration_login_forgot_pin_browser(registration, monkeypatch):
    client, db, sent = registration
    monkeypatch.setattr(pin_service.secrets, "randbelow", lambda n: 8621)
    server = uvicorn.Server(uvicorn.Config(client._transport.app, host="127.0.0.1", port=18770, log_level="error", lifespan="off"))
    task = asyncio.create_task(server.serve())
    process = None
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(.05)
        assert server.started
        root = Path(__file__).resolve().parents[2]
        process = await asyncio.create_subprocess_exec(
            str(root / "frontend/node_modules/.cache/voice-node22/node.exe"),
            str(root / "scripts/customer-pin-ui-check.mjs"), cwd=root,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )

        async def journey():
            output = []
            while line := await process.stdout.readline():
                if line.startswith(b"NEED_MOCK_OTP"):
                    code = sent[-1]["message"].split(" is ")[1].split(".")[0]
                    process.stdin.write((code + "\n").encode())
                    await process.stdin.drain()
                else:
                    output.append(line.decode(errors="replace"))
            await process.wait()
            return "".join(output)

        output = await asyncio.wait_for(journey(), 180)
        assert process.returncode == 0, output
        widths = json.loads(os.environ.get("AFS_PIN_BROWSER_WIDTHS", "[1440,390]"))
        assert len(sent) == 2 * len(widths)
        assert await db.users.count_documents({"role": "customer"}) == len(widths)
        assert await db.customers.count_documents({}) == len(widths)
        print(output)
    finally:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        server.should_exit = True
        await task
