# ruff: noqa: F811
"""Real local portal/API journeys; storage transport is mocked, no SMS is sent."""
import asyncio
import json
import os
from pathlib import Path

import pytest
import uvicorn
from app.features.auth.models import User
from app.features.customer.service import CustomerService
from app.security.pin import hash_pin
from bson import ObjectId
from test_customer import _create_lead_doc
from test_portal_modernisation import portal  # noqa: F401


@pytest.mark.skipif(os.environ.get("AFS_PORTAL_BROWSER_CHECK") != "1", reason="Opt-in local portal browser")
async def test_portal_responsive_and_unified_journey(portal, mock_redis):
    client, db, owner_headers, _, product = portal
    user = await db.users.find_one({"mobile": "9000000098"})
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"pin_hash": hash_pin("0472"), "is_mobile_verified": True}})
    lead_id = await _create_lead_doc(db, product, mobile=user["mobile"], full_name="Portal Customer")
    link = await client.post(f"/api/v1/leads/{lead_id}/secure-links", headers=owner_headers, json={})
    assert link.status_code == 200, link.text
    from datetime import timedelta

    from app.features.customer.models import SecureLink
    from app.utils.datetime import utc_now

    for code, status, expires in [("EXPIREDPORTAL", "active", utc_now() - timedelta(minutes=1)),
                                  ("DISABLEDPORTAL", "revoked", utc_now() + timedelta(days=1))]:
        record = SecureLink(lead_id=lead_id, secure_code=code, status=status, expires_at=expires)
        await db.secure_links.insert_one(record.model_dump(by_alias=True, exclude={"id"}))
    owner = User.model_validate(await db.users.find_one({"role": "owner"}))
    customer = await db.customers.find_one({"user_id": str(user["_id"])})
    staff = await CustomerService(db, mock_redis).create_application_for_customer(
        customer_id=str(customer["_id"]), product_category="loan", product_id=product["product_id"], actor=owner)
    # The independent journey uses a different product so it never consumes staff's draft.
    from test_customer import _seed_product_and_form
    independent = await _seed_product_and_form(db, product_name="Portal Personal Loan")
    server = uvicorn.Server(uvicorn.Config(client._transport.app, host="127.0.0.1", port=18771, log_level="error", lifespan="off"))
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
            str(root / "scripts/customer-portal-ui-check.mjs"), cwd=root,
            env={**os.environ, "AFS_PORTAL_FIXTURE": json.dumps({"secure_code": link.json()["data"]["secure_code"],
                "staff_id": staff.require_id(), "product_id": independent["product_id"]})},
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await asyncio.wait_for(process.communicate(), 240)
        assert process.returncode == 0, output.decode(errors="replace")
        assert await db.applications.count_documents({"submission_source": "secure_link", "lead_id": lead_id}) == 1
        assert await db.applications.count_documents({"submission_source": "customer_portal", "status": "submitted"}) == 1
        assert (await db.applications.find_one({"_id": ObjectId(staff.require_id())}))["status"] == "draft"
        print(output.decode(errors="replace"))
    finally:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        server.should_exit = True
        await task
