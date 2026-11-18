# ruff: noqa: F811
"""Opt-in standalone/replica MongoDB concurrency; disposable loopback database only."""
import asyncio
from uuid import uuid4

from app.features.auth.models import User
from app.features.customer.indexes import ensure_customer_indexes
from app.features.customer.models import Customer
from app.features.customer.schemas import (
    StartApplicationRequest,
    SubmitApplicationRequest,
)
from app.features.customer.service import CustomerService
from app.features.workflow_engine.indexes import ensure_workflow_engine_indexes
from test_customer import _seed_product_and_form
from test_invoice_mongo_integration import real_invoice_db  # noqa: F401
from test_workflow import _seed_workflow_definitions


async def test_real_mongo_concurrent_creation_and_submission_without_transactions(real_invoice_db, mock_redis):
    db = real_invoice_db
    # Observe the actual test topology rather than assume transactions are present.
    assert (await db.client.admin.command("hello"))["ok"] == 1
    await ensure_customer_indexes(db)
    await ensure_workflow_engine_indexes(db)
    product = await _seed_product_and_form(db)
    await db.application_form_definitions.update_many({}, {"$set": {"fields": [], "required_documents": []}})
    await _seed_workflow_definitions(db)
    raw = User(mobile="9000000096", role="customer", status="active")
    uid = (await db.users.insert_one(raw.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    actor = User.model_validate(await db.users.find_one({"_id": uid}))
    customer = Customer(customer_code="AFS-CUS-FIXTURE", user_id=actor.require_id(), full_name="Test Customer", mobile=actor.mobile)
    await db.customers.insert_one(customer.model_dump(by_alias=True, exclude={"id"}))
    service = CustomerService(db, mock_redis)
    request = StartApplicationRequest(product_category="loan", product_id=product["product_id"], request_key=str(uuid4()))
    applications = await asyncio.gather(*(service.start_application(request, actor) for _ in range(8)))
    assert len({app.require_id() for app in applications}) == 1
    aid = applications[0].require_id()
    submitted = await asyncio.gather(*(service.submit_application(aid, SubmitApplicationRequest(), actor) for _ in range(5)))
    assert len({app.submitted_at for app in submitted}) == 1
    assert await db.applications.count_documents({}) == 1
    assert await db.application_workflows.count_documents({"application_id": aid}) == 1
    assert await db.audit_logs.count_documents({"event_type": "application_submitted"}) == 1
