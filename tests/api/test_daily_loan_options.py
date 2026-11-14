# ruff: noqa: F811
import copy

from bson import ObjectId
from test_daily_operations import create
from test_daily_simple_entry import follow, staff  # noqa: F401

BASE = "/api/v1/daily-operations"


async def test_shared_loan_types_duplicate_archive_history(client, mock_db, staff):
    from app.features.daily_operations.loan_options import install

    await install(mock_db)
    url = BASE + "/loan-type-options"
    created = await client.post(
        url, headers=staff[1], json={"name": "Secured Business Loan"}
    )
    assert created.status_code == 200, created.text
    option = created.json()["data"]
    assert (
        await client.post(
            url, headers=staff[3], json={"name": " secured  business loan "}
        )
    ).status_code == 409
    assert option["id"] in {
        row["id"] for row in (await client.get(url, headers=staff[3])).json()["data"]
    }
    record = await create(
        client, staff[1], "follow-ups", follow(loan_type=option["name"])
    )
    assert (
        await client.patch(
            url + "/" + option["id"],
            headers=staff[3],
            json={"name": "Renamed Loan", "version": 1},
        )
    ).status_code == 200
    assert (
        await client.post(
            url + "/" + option["id"] + "/archive", headers=staff[1], json={"version": 2}
        )
    ).status_code == 200
    assert not (await client.get(url, headers=staff[1])).json()["data"]
    retained = await client.get(BASE + "/follow-ups/" + record["id"], headers=staff[1])
    assert retained.json()["data"]["loan_type"] == "Secured Business Loan"
    assert (
        await client.post(
            url + "/" + option["id"] + "/restore", headers=staff[1], json={"version": 3}
        )
    ).status_code == 200


async def test_daily_default_200_bounded_backend_pages(client, mock_db, staff):
    record = await create(client, staff[1], "follow-ups", follow())
    raw = await mock_db.daily_follow_ups.find_one({"_id": ObjectId(record["id"])})
    clones = []
    for _ in range(204):
        row = copy.deepcopy(raw)
        row["_id"] = ObjectId()
        row["import_key"] = str(row["_id"])
        clones.append(row)
    await mock_db.daily_follow_ups.insert_many(clones)
    first = await client.get(BASE + "/follow-ups", headers=staff[1])
    assert first.status_code == 200, first.text
    assert (
        first.json()["data"]["total"] == 205
        and len(first.json()["data"]["items"]) == 200
    )
    second = await client.get(
        BASE + "/follow-ups", headers=staff[1], params={"page": 2, "page_size": 200}
    )
    assert len(second.json()["data"]["items"]) == 5
    assert (
        await client.get(
            BASE + "/follow-ups", headers=staff[1], params={"page_size": 201}
        )
    ).status_code == 422
