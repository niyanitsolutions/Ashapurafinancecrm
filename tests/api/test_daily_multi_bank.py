# ruff: noqa: F811
import asyncio

import pytest
from app.features.daily_operations.bank_migration import migrate
from bson import ObjectId
from test_daily_operations import create
from test_daily_simple_entry import follow, staff  # noqa: F401

BASE = "/api/v1/daily-operations"
OPTIONS = BASE + "/bank-options"


async def bank(client, headers, name):
    response = await client.post(OPTIONS, headers=headers, json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def test_multiple_banks_shared_and_snapshots(
    client, mock_db, staff, owner_headers
):
    a = await bank(client, staff[1], "WERIZE FINANCE")
    b = await bank(client, staff[3], "FINNABLE FINANCE")
    c = await bank(client, staff[1], "INCRED FINANCE")
    for headers in (owner_headers, staff[1], staff[3]):
        assert {a["id"], b["id"], c["id"]} <= {
            r["id"] for r in (await client.get(OPTIONS, headers=headers)).json()["data"]
        }
    choices = [
        {"option_id": r["id"], "name": "Ignored client label"} for r in (a, b, c)
    ]
    record = await create(
        client, staff[1], "follow-ups", follow(bank="", banks=choices)
    )
    assert [r["name"] for r in record["banks"]] == [a["name"], b["name"], c["name"]]
    for name in (a["name"], b["name"], c["name"]):
        result = await client.get(
            BASE + "/follow-ups", headers=staff[1], params={"bank": name}
        )
        assert result.json()["data"]["total"] == 1
    assert (await client.get(BASE + "/follow-ups", headers=staff[3])).json()["data"][
        "total"
    ] == 0
    await client.patch(
        OPTIONS + "/" + a["id"],
        headers=staff[3],
        json={"name": "Renamed bank", "version": 1},
    )
    await client.post(
        OPTIONS + "/" + a["id"] + "/archive", headers=staff[3], json={"version": 2}
    )
    saved = await client.patch(
        BASE + "/follow-ups/" + record["id"],
        headers=staff[1],
        json=follow(
            bank="", banks=record["banks"], version=1, remarks="Retained archived bank"
        ),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["banks"][0]["name"] == a["name"]
    assert (
        await client.post(
            BASE + "/follow-ups",
            headers=staff[1],
            json=follow(bank="", banks=[{"option_id": a["id"]}]),
        )
    ).status_code == 422
    changed = await client.patch(
        BASE + "/follow-ups/" + record["id"],
        headers=staff[1],
        json=follow(
            bank="", banks=[{"option_id": b["id"]}, {"option_id": c["id"]}], version=2
        ),
    )
    assert changed.status_code == 200
    assert len(changed.json()["data"]["history"][-1]["before"]["banks"]) == 3
    for fmt in ("csv", "xlsx"):
        export = await client.get(
            BASE + "/follow-ups/export", headers=staff[1], params={"format": fmt}
        )
        assert export.status_code == 200
        if fmt == "csv":
            assert b["name"] in export.text and c["name"] in export.text
    assert (
        await mock_db.audit_logs.count_documents(
            {"event_type": "followup_bank_option_created"}
        )
        == 3
    )
    assert (
        await mock_db.audit_logs.count_documents(
            {"event_type": "followup_bank_option_updated"}
        )
        == 1
    )
    assert (
        await mock_db.audit_logs.count_documents(
            {"event_type": "followup_bank_option_archived"}
        )
        == 1
    )


@pytest.mark.parametrize(
    "choices",
    [
        [],
        [{"option_id": "not-an-id"}],
        [{"option_id": "aaaaaaaaaaaaaaaaaaaaaaaa"}],
        [{"option_id": None, "name": "Forged bank"}],
    ],
)
async def test_bank_validation(client, staff, choices):
    assert (
        await client.post(
            BASE + "/follow-ups", headers=staff[1], json=follow(bank="", banks=choices)
        )
    ).status_code == 422


async def test_duplicates_concurrency_and_restore(client, mock_db, staff):
    a = await bank(client, staff[1], "  Custom   bank  ")
    assert a["name"] == "Custom bank"
    assert (
        await client.post(OPTIONS, headers=staff[3], json={"name": "custom bank"})
    ).status_code == 409
    assert (
        await client.post(
            BASE + "/follow-ups",
            headers=staff[1],
            json=follow(bank="", banks=[{"option_id": a["id"]}] * 2),
        )
    ).status_code == 422
    responses = await asyncio.gather(
        *(
            client.post(OPTIONS, headers=staff[1], json={"name": "Concurrent bank"})
            for _ in range(6)
        )
    )
    assert sum(r.status_code == 200 for r in responses) == 1
    assert (
        await client.post(
            OPTIONS + "/" + a["id"] + "/archive", headers=staff[3], json={"version": 1}
        )
    ).status_code == 200
    assert (
        await client.patch(
            OPTIONS + "/" + a["id"],
            headers=staff[1],
            json={"name": "Stale", "version": 1},
        )
    ).status_code == 409
    assert (
        await client.post(
            OPTIONS + "/" + a["id"] + "/restore", headers=staff[1], json={"version": 2}
        )
    ).status_code == 200
    for name in ("", " ", "x" * 201):
        assert (
            await client.post(OPTIONS, headers=staff[1], json={"name": name})
        ).status_code == 422


async def test_foreign_options_permissions(client, mock_db, staff, employee_headers):
    foreign = str(ObjectId())
    await mock_db.daily_followup_bank_options.insert_one(
        {
            "_id": ObjectId(foreign),
            "company_id": "foreign",
            "name": "Other company",
            "normalized_name": "other company",
            "is_active": True,
            "version": 1,
        }
    )
    assert (
        await client.post(
            BASE + "/follow-ups",
            headers=staff[1],
            json=follow(bank="", banks=[{"option_id": foreign}]),
        )
    ).status_code == 422
    assert (
        await client.patch(
            OPTIONS + "/" + foreign,
            headers=staff[1],
            json={"name": "Spoof", "version": 1},
        )
    ).status_code == 404
    assert foreign not in {
        r["id"] for r in (await client.get(OPTIONS, headers=staff[1])).json()["data"]
    }
    assert (
        await client.post(
            OPTIONS, headers=staff[1], json={"name": "Spoof", "company_id": "foreign"}
        )
    ).status_code == 422
    assert (await client.get(OPTIONS)).status_code == 401
    assert (
        await client.post(
            OPTIONS, headers=employee_headers, json={"name": "Unauthorized"}
        )
    ).status_code == 403


async def test_disburse_no_automatic_links_or_financial_side_effects(
    client, mock_db, staff, monkeypatch
):
    from app.features.leads.service import LeadService

    async def forbidden(*args, **kwargs):
        raise AssertionError("Follow-up save queried CRM matching")

    monkeypatch.setattr(LeadService, "check_duplicate", forbidden)
    mobile = "9000000000"
    await mock_db.customers.insert_one(
        {"mobile": mobile, "full_name": "Other name", "is_deleted": False}
    )
    await mock_db.leads.insert_one(
        {"mobile": mobile, "full_name": "Other name", "is_deleted": False}
    )
    collections = (
        "leads",
        "customers",
        "applications",
        "application_workflows",
        "application_status_history",
        "counters",
    )
    before = {name: await mock_db[name].find({}).to_list(None) for name in collections}
    a = await bank(client, staff[1], "Independent Bank")
    record = await create(
        client,
        staff[1],
        "follow-ups",
        follow(
            banks=[{"option_id": a["id"]}], bank="", status="DISBURSE", due_date=None
        ),
    )
    assert (
        record["lead_id"] is None
        and record["case_id"] is None
        and record["status"] == "DISBURSE"
    )
    saved = await client.patch(
        BASE + "/follow-ups/" + record["id"],
        headers=staff[1],
        json=follow(
            banks=record["banks"],
            bank="",
            status="DISBURSE",
            due_date=None,
            version=1,
            remarks="Independent edit",
        ),
    )
    assert saved.status_code == 200
    assert {
        name: await mock_db[name].find({}).to_list(None) for name in collections
    } == before
    lookup = (await client.get(BASE + "/lookups", headers=staff[1])).json()["data"]
    assert lookup["leads"] == [] and lookup["cases"] == []
    assert (
        await client.post(
            BASE + "/follow-ups", headers=staff[1], json=follow(lead_id=str(ObjectId()))
        )
    ).status_code == 422


async def test_legacy_projection_migration_and_repeat_saves(client, mock_db, staff):
    row = await create(
        client, staff[1], "follow-ups", follow(bank="WERIZE, legacy literal")
    )
    await mock_db.daily_follow_ups.update_one(
        {"_id": ObjectId(row["id"])}, {"$unset": {"banks": ""}}
    )
    raw = await mock_db.daily_follow_ups.find_one({"_id": ObjectId(row["id"])})
    projected = (
        await client.get(BASE + "/follow-ups/" + row["id"], headers=staff[1])
    ).json()["data"]
    assert projected["banks"] == [{"option_id": None, "name": "WERIZE, legacy literal"}]
    preview = await migrate(mock_db)
    assert preview["eligible"] == 1 and preview["converted"] == 0
    assert await mock_db.daily_follow_ups.find_one({"_id": raw["_id"]}) == raw
    result = await migrate(mock_db, True)
    assert result["converted"] == 1
    migrated = await mock_db.daily_follow_ups.find_one({"_id": raw["_id"]})
    for key, value in raw.items():
        assert migrated[key] == value
    assert migrated["banks"][0]["name"] == raw["bank"]
    assert (await migrate(mock_db, True))["converted"] == 0
    saved = await client.patch(
        BASE + "/follow-ups/" + row["id"],
        headers=staff[1],
        json=follow(bank="", banks=migrated["banks"], version=1),
    )
    assert saved.status_code == 200, saved.text
