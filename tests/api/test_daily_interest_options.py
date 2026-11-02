# ruff: noqa: F811
import asyncio

import pytest
from bson import ObjectId
from test_daily_operations import create
from test_daily_simple_entry import follow, staff  # noqa: F401

BASE = "/api/v1/daily-operations"
OPTIONS = BASE + "/interest-options"


async def option(client, headers, name="Custom interest"):
    response = await client.post(OPTIONS, headers=headers, json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def test_shared_employee_options_and_audit(client, mock_db, staff, owner_headers):
    _, a, _, b = staff
    first = await option(client, a, "  Need   documents  ")
    second = await option(client, b, "Ready tomorrow")
    assert first["name"] == "Need documents"
    for headers in (a, b, owner_headers):
        rows = (await client.get(OPTIONS, headers=headers)).json()["data"]
        assert {first["id"], second["id"]} <= {r["id"] for r in rows}
    assert (
        await mock_db.audit_logs.count_documents(
            {
                "event_type": "customer_interest_option_created",
                "metadata.company_id": "default",
            }
        )
        == 2
    )
    assert (await client.get(OPTIONS)).status_code == 401
    for payload in (
        {"name": "", "company_id": "other"},
        {"name": "x", "created_by": "spoof"},
    ):
        assert (await client.post(OPTIONS, headers=a, json=payload)).status_code == 422


@pytest.mark.parametrize("name", ["", "   ", "x" * 61])
async def test_option_validation(client, staff, name):
    assert (
        await client.post(OPTIONS, headers=staff[1], json={"name": name})
    ).status_code == 422


async def test_duplicates_unicode_concurrency_and_stale_updates(client, staff):
    headers = staff[1]
    doc = await option(client, headers, "Urgent   CALL")
    for name in (
        "urgent call",
        "  URGENT CALL  ",
        "\uff35\uff32\uff27\uff25\uff2e\uff34 CALL",
    ):
        assert (
            await client.post(OPTIONS, headers=headers, json={"name": name})
        ).status_code == 409
    responses = await asyncio.gather(
        *(
            client.post(OPTIONS, headers=headers, json={"name": "Concurrent option"})
            for _ in range(8)
        )
    )
    assert sum(r.status_code == 200 for r in responses) == 1
    renamed = await client.patch(
        OPTIONS + "/" + doc["id"],
        headers=headers,
        json={"name": "Renamed", "version": 1},
    )
    assert renamed.status_code == 200
    assert (
        await client.patch(
            OPTIONS + "/" + doc["id"],
            headers=headers,
            json={"name": "Stale", "version": 1},
        )
    ).status_code == 409


async def test_snapshots_archive_restore_filter_and_exports(
    client, mock_db, staff, owner_headers
):
    headers = staff[1]
    doc = await option(client, headers, "Original label")
    record = await create(
        client, headers, "follow-ups", follow(customer_interest_option_id=doc["id"])
    )
    assert record["customer_interest_status_snapshot"] == "Original label"
    renamed = (
        await client.patch(
            OPTIONS + "/" + doc["id"],
            headers=staff[3],
            json={"name": "New label", "version": 1},
        )
    ).json()["data"]
    archived = (
        await client.post(
            OPTIONS + "/" + doc["id"] + "/archive",
            headers=headers,
            json={"version": renamed["version"]},
        )
    ).json()["data"]
    assert doc["id"] not in {
        r["id"] for r in (await client.get(OPTIONS, headers=headers)).json()["data"]
    }
    # Existing value can be retained; unrelated fields and labels survive.
    saved = await client.patch(
        BASE + "/follow-ups/" + record["id"],
        headers=headers,
        json=follow(
            version=record["version"],
            customer_interest_option_id=doc["id"],
            remarks="Other edits",
        ),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["customer_interest_status_snapshot"] == "Original label"
    assert (
        await client.post(
            BASE + "/follow-ups",
            headers=headers,
            json=follow(customer_interest_option_id=doc["id"]),
        )
    ).status_code == 422
    # Older clients omitting the new optional field must not clear it.
    again = await client.patch(
        BASE + "/follow-ups/" + record["id"],
        headers=headers,
        json=follow(version=saved.json()["data"]["version"]),
    )
    assert again.json()["data"]["customer_interest_status_snapshot"] == "Original label"
    listed = await client.get(
        BASE + "/follow-ups",
        headers=headers,
        params={"customer_interest_option_id": doc["id"]},
    )
    assert listed.json()["data"]["total"] == 1
    for fmt in ("csv", "xlsx"):
        export = await client.get(
            BASE + "/follow-ups/export",
            headers=headers,
            params={"format": fmt, "customer_interest_option_id": doc["id"]},
        )
        assert export.status_code == 200, export.text
        if fmt == "csv":
            assert (
                "CUSTOMER INTEREST STATUS" in export.text
                and "Original label" in export.text
            )
    restored = await client.post(
        OPTIONS + "/" + doc["id"] + "/restore",
        headers=owner_headers,
        json={"version": archived["version"]},
    )
    assert restored.status_code == 200
    events = await mock_db.audit_logs.find({"metadata.option_id": doc["id"]}).to_list(
        None
    )
    assert {e["event_type"] for e in events} == {
        "customer_interest_option_created",
        "customer_interest_option_renamed",
        "customer_interest_option_archived",
        "customer_interest_option_restored",
    }


async def test_archived_restore_conflict_and_foreign_scope(client, mock_db, staff):
    headers = staff[1]
    doc = await option(client, headers, "Recoverable")
    await client.post(
        OPTIONS + "/" + doc["id"] + "/archive", headers=headers, json={"version": 1}
    )
    await option(client, headers, "recoverable")
    assert (
        await client.post(
            OPTIONS + "/" + doc["id"] + "/restore", headers=headers, json={"version": 2}
        )
    ).status_code == 409
    foreign = str(ObjectId())
    await mock_db.daily_interest_options.insert_one(
        {
            "_id": ObjectId(foreign),
            "company_id": "foreign",
            "name": "Private",
            "is_active": True,
            "version": 1,
        }
    )
    assert foreign not in {
        r["id"]
        for r in (
            await client.get(
                OPTIONS, headers=headers, params={"include_archived": True}
            )
        ).json()["data"]
    }
    assert (
        await client.patch(
            OPTIONS + "/" + foreign,
            headers=headers,
            json={"name": "Hack", "version": 1},
        )
    ).status_code == 404
    assert (
        await client.post(
            BASE + "/follow-ups",
            headers=headers,
            json=follow(customer_interest_option_id=foreign),
        )
    ).status_code == 422
    assert (
        await mock_db.daily_interest_options.find_one({"_id": ObjectId(doc["id"])})
    )["is_active"] is False


async def test_inactive_employee_and_profileless_user_cannot_manage_options(
    client, mock_db, staff, employee_headers
):
    employee, headers, _, _ = staff
    await mock_db.employees.update_one(
        {"_id": ObjectId(employee["id"])}, {"$set": {"status": "inactive"}}
    )
    for actor in (headers, employee_headers):
        assert (await client.get(OPTIONS, headers=actor)).status_code == 403
        assert (
            await client.post(OPTIONS, headers=actor, json={"name": "Forbidden"})
        ).status_code == 403


async def test_snapshot_is_server_owned_and_active_renames_apply_only_to_new_selections(
    client, staff
):
    headers = staff[1]
    doc = await option(client, headers, "Old display")
    response = await client.post(
        BASE + "/follow-ups",
        headers=headers,
        json=follow(
            customer_interest_option_id=doc["id"],
            customer_interest_status_snapshot="Forged",
        ),
    )
    assert response.status_code == 422
    await client.patch(
        OPTIONS + "/" + doc["id"],
        headers=headers,
        json={"name": "New display", "version": 1},
    )
    saved = await create(
        client, headers, "follow-ups", follow(customer_interest_option_id=doc["id"])
    )
    assert saved["customer_interest_status_snapshot"] == "New display"


async def test_legacy_import_update_preserves_saved_interest(client, staff):
    import csv
    import io

    headers = staff[1]
    doc = await option(client, headers, "Keep through import")
    record = await create(
        client, headers, "follow-ups", follow(customer_interest_option_id=doc["id"])
    )
    row = follow(
        record_id=record["id"], version=record["version"], remarks="Imported note"
    )
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(row))
    writer.writeheader()
    writer.writerow(row)
    response = await client.post(
        BASE + "/transfers/follow-ups/preview",
        headers=headers,
        data={"allow_updates": "true"},
        files={"file": ("legacy.csv", stream.getvalue().encode(), "text/csv")},
    )
    assert response.status_code == 200, response.text
    batch = response.json()["data"]
    assert not batch["rows"][0]["errors"]
    committed = await client.post(
        BASE + "/transfers/" + batch["id"] + "/confirm",
        headers=headers,
        json={"confirmed": True},
    )
    assert committed.json()["data"]["updated"] == 1, committed.text
    saved = (
        await client.get(BASE + "/follow-ups/" + record["id"], headers=headers)
    ).json()["data"]
    assert saved["customer_interest_status_snapshot"] == "Keep through import"
    assert saved["remarks"] == "Imported note"
