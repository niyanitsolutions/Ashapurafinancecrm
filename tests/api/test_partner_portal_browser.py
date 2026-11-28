# ruff: noqa: F811
"""Opt-in real Chrome, loopback API and disposable MongoDB; synthetic private storage."""

import asyncio
import base64
import io
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pymupdf
import pytest
import uvicorn
from app.config.database import get_database
from app.features.auth.models import User
from app.features.referral_partner_management.finance import save_rule
from app.features.referral_partner_management.indexes import (
    ensure_referral_partner_management_indexes,
)
from app.features.referral_partner_management.kyc import PartnerKyc
from app.features.referral_partner_management.portal_models import (
    ConfirmDocument,
    DocumentTicket,
    KycConfiguration,
)
from app.features.referral_partner_management.schemas import CreateCommissionRuleRequest
from app.security.password import hash_password
from app.security.pin import hash_pin
from app.utils.datetime import utc_now
from bson import ObjectId
from fastapi import Request, Response
from PIL import Image
from test_daily_handover_enhancement import (
    environment,  # noqa: F401
    loan,
)
from test_partner_portal_enhancement import (
    approved_partner,
    private_storage,  # noqa: F401
    product_form,
)
from test_pin_mongo_integration import pin_mongo  # noqa: F401


@pytest.mark.skipif(
    os.environ.get("AFS_PARTNER_BROWSER") != "1", reason="Opt-in local browser"
)
async def test_partner_owner_customer_responsive_journeys(
    environment, private_storage, client, monkeypatch
):
    db, owner, employees, _customer, application = environment
    await ensure_referral_partner_management_indexes(db)
    from app.features.dashboard.models import NavItem

    # Existing navigation keys, without granting an Employee any new capability.
    for key, label, route in (
        ("referral_partners", "Referral Partners", "/referral-partners"),
        ("commission_rules", "Commission Rules", "/commission-rules"),
        ("commission_ledger", "Commission Payouts", "/commission-ledger"),
    ):
        await db.nav_items.insert_one(
            NavItem(key=key, label=label, route=route, owner_only=True).model_dump(
                exclude={"id"}
            )
        )
    for actor in [owner, employees[0][1]]:
        await db.users.update_one(
            {"_id": ObjectId(actor.id)},
            {"$set": {"password_hash": hash_password("InitialPass1!")}},
        )
    with pymupdf.open() as pdf:
        pdf.new_page()
        pdf_bytes = pdf.tobytes()
    image_stream = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(image_stream, format="PNG")
    kyc = PartnerKyc(db)
    ticket = await kyc.upload(
        DocumentTicket(
            category="partner_agreement",
            content_type="application/pdf",
            size=len(pdf_bytes),
        ),
        owner,
        agreement=True,
    )
    private_storage.objects[
        ticket["upload_url"].removeprefix("https://synthetic-storage.invalid/")
    ] = pdf_bytes
    agreement = await kyc.confirm(
        ConfirmDocument(ticket=ticket["ticket"], consent=True), owner
    )
    config = KycConfiguration.model_validate(await kyc.configuration())
    config.required_agreement_ids = [agreement["id"]]
    await kyc.publish(config, owner)
    financial_partner, _partner_actor = await approved_partner(db, owner)
    await db.partner_kyc_submissions.update_one(
        {"partner_id": financial_partner.id},
        {"$set": {"accepted_agreement_ids": [agreement["id"]]}},
    )
    await db.applications.update_one(
        {"_id": ObjectId(application.id)},
        {
            "$set": {
                "referral_attribution": {
                    "partner_id": financial_partner.id,
                    "partner_name": financial_partner.full_name,
                    "referral_id": str(ObjectId()),
                    "submitted_to_afs_at": utc_now(),
                    "origin": "manual",
                    "submission_mode": "partner_review",
                }
            }
        },
    )
    case = await loan(environment)
    await save_rule(
        db,
        CreateCommissionRuleRequest(
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            label="Synthetic browser rate",
            calculation_type="percentage",
            rate_or_amount=2,
            trigger_event="loan_disbursed",
        ),
        owner,
    )
    product_id = await product_form(db)
    customer_user = User(
        mobile="9000000088",
        role="customer",
        pin_hash=hash_pin("7392"),
        pin_epoch=1,
        is_mobile_verified=True,
    )
    await db.users.insert_one(customer_user.model_dump(exclude={"id"}))
    app = client._transport.app
    app.dependency_overrides[get_database] = lambda: db
    from starlette.middleware.cors import CORSMiddleware

    # Only the disposable test app trusts the synthetic browser storage origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5176"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Test-only capability upload sink. Never registered by application source.
    @app.put("/synthetic-partner-storage/{key:path}")
    async def storage_put(key: str, request: Request):
        assert key.startswith("partner-kyc/staging/")
        private_storage.objects[key] = await request.body()
        return Response(
            status_code=200,
            headers={"Access-Control-Allow-Origin": "http://127.0.0.1:5176"},
        )

    @app.options("/synthetic-partner-storage/{key:path}")
    async def storage_options(key: str):
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "http://127.0.0.1:5176",
                "Access-Control-Allow-Methods": "PUT",
                "Access-Control-Allow-Headers": "content-type,x-amz-server-side-encryption",
            },
        )

    from app.features.referral_partner_management import kyc as kyc_module

    monkeypatch.setattr(
        kyc_module,
        "generate_presigned_upload_url",
        lambda key, **_kwargs: (
            "http://127.0.0.1:18774/synthetic-partner-storage/" + key
        ),
    )
    fixture = {
        "owner_mobile": owner.mobile,
        "employee_mobile": employees[0][1].mobile,
        "product_id": product_id,
        "case_id": case.id,
        "agreement_id": agreement["id"],
        "pdf": base64.b64encode(pdf_bytes).decode(),
        "image": base64.b64encode(image_stream.getvalue()).decode(),
    }
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=18774, log_level="error", lifespan="off"
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
            str(root / "scripts/partner-portal-ui-check.mjs"),
            cwd=root,
            env={**os.environ, "AFS_PARTNER_FIXTURE": json.dumps(fixture)},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await asyncio.wait_for(process.communicate(), 600)
        assert process.returncode == 0, output.decode(errors="replace")
        partner = await db.referral_partners.find_one({"mobile": "9000000077"})
        assert (
            partner["kyc_status"] == "approved"
            and partner["approval_status"] == "active"
        )
        assert (
            await db.partner_kyc_documents.count_documents(
                {
                    "partner_id": str(partner["_id"]),
                    "status": "approved",
                    "current": True,
                }
            )
            == 7
        )
        assert (
            await db.applications.count_documents(
                {
                    "referral_attribution.partner_id": str(partner["_id"]),
                    "referral_attribution.submitted_to_afs_at": {"$ne": None},
                }
            )
            == 1
        )
        entry = await db.commission_entries.find_one({"case_id": case.id})
        assert (
            entry["commission_amount"] == 1000
            and entry["paid_amount"] == 400
            and entry["reserved_amount"] == 0
        )
        assert await db.commission_payouts.count_documents({"status": "confirmed"}) == 1
        print(output.decode(errors="replace"))
    finally:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        server.should_exit = True
        await task
