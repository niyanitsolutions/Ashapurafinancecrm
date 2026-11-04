# ruff: noqa: F811
import asyncio

from app.features.auth.models import User
from app.features.daily_operations.service import DailyOperationsService
from app.features.daily_operations.status_options import StatusOptions, install
from bson import ObjectId
from test_invoice_mongo_integration import real_invoice_db  # noqa: F401


async def test_real_mongo_status_uniqueness_archive_restart_and_database_isolation(
    real_invoice_db,
):
    db = real_invoice_db
    await install(db)
    service = StatusOptions(DailyOperationsService(db))
    actor = User(id=str(ObjectId()), mobile="9000000001", role="owner")
    outcomes = await asyncio.gather(
        *(service.change(actor, name="Concurrent") for _ in range(12)),
        return_exceptions=True,
    )
    assert sum(isinstance(row, dict) for row in outcomes) == 1
    first = next(row for row in outcomes if isinstance(row, dict))
    await service.change(actor, option_id=first["id"], version=1, active=False)
    await service.change(actor, name="concurrent")
    await install(db)  # real partial index remains idempotent with archived duplicates
    seed = (await service.list(actor))[0]
    await service.change(
        actor, option_id=seed["id"], version=seed["version"], color="#010203"
    )
    await install(db)
    assert (
        next(r for r in await service.list(actor) if r["id"] == seed["id"])["color"]
        == "#010203"
    )
    # A separate company database cannot resolve or mutate the first database's options.
    other_name = db.name + "_other"
    other = db.client[other_name]
    try:
        await install(other)
        other_service = StatusOptions(DailyOperationsService(other))
        assert first["id"] not in {
            r["id"] for r in await other_service.list(actor, True)
        }
        import pytest
        from app.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            await other_service.change(
                actor, option_id=first["id"], version=2, name="Foreign"
            )
    finally:
        assert other.name.startswith("afs_invoice_test_") and other.name.endswith(
            "_other"
        )
        await db.client.drop_database(other_name)
