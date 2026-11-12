# ruff: noqa: F811
import asyncio

import pytest
from app.core.exceptions import ValidationError
from app.features.auth.models import User
from app.features.daily_operations.bank_migration import migrate
from app.features.daily_operations.bank_options import BankChoice, BankOptions, install
from app.features.daily_operations.service import DailyOperationsService
from bson import ObjectId
from test_invoice_mongo_integration import real_invoice_db  # noqa: F401


async def test_real_bank_concurrency_migration_restart_and_database_isolation(
    real_invoice_db,
):
    db = real_invoice_db
    await install(db)
    service = BankOptions(DailyOperationsService(db))
    actor = User(id=str(ObjectId()), mobile="9000000001", role="owner")
    outcomes = await asyncio.gather(
        *(service.change(actor, name="Concurrent bank") for _ in range(12)),
        return_exceptions=True,
    )
    assert sum(isinstance(row, dict) for row in outcomes) == 1
    first = next(row for row in outcomes if isinstance(row, dict))
    originals = []
    for _ in range(2):
        doc = {
            "_id": ObjectId(),
            "bank": " Legacy, literal bank ",
            "version": 1,
            "is_deleted": False,
            "history": [{"original": True}],
        }
        await db.daily_follow_ups.insert_one(doc)
        originals.append(doc)
    assert (await migrate(db))["eligible"] == 2
    for doc in originals:
        assert await db.daily_follow_ups.find_one({"_id": doc["_id"]}) == doc
    assert (await migrate(db, True))["converted"] == 2
    for doc in originals:
        changed = await db.daily_follow_ups.find_one({"_id": doc["_id"]})
        assert changed["banks"][0]["name"] == doc["bank"]
        assert {key: value for key, value in changed.items() if key != "banks"} == doc
    assert (
        await db.daily_followup_bank_options.count_documents(
            {"normalized_name": "legacy, literal bank"}
        )
        == 1
    )
    assert (await migrate(db, True))["converted"] == 0
    await service.change(actor, option_id=first["id"], version=1, active=False)
    await install(db)
    assert first["id"] not in {row["id"] for row in await service.list(actor)}
    other_name = db.name + "_bank_other"
    other = db.client[other_name]
    try:
        await install(other)
        isolated = BankOptions(DailyOperationsService(other))
        with pytest.raises(ValidationError):
            await isolated.selections([BankChoice(option_id=first["id"])], "", None)
    finally:
        assert other_name.startswith("afs_invoice_test_") and other_name.endswith(
            "_bank_other"
        )
        await db.client.drop_database(other_name)
