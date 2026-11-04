# ruff: noqa: F811
import asyncio

import pytest
from bson import ObjectId
from test_daily_operations import create
from test_daily_simple_entry import follow, staff  # noqa: F401

BASE = "/api/v1/daily-operations"
OPTIONS = BASE + "/follow-up-status-options"


async def option(client, headers, name="Custom status", color="#EDE3FF"):
    response = await client.post(
        OPTIONS,
        headers=headers,
        json={"name": name, "color": color, "display_order": 10},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def test_defaults_colors_shared_and_removal_of_interest(
    client, mock_db, staff, owner_headers
):
    rows = (await client.get(OPTIONS, headers=owner_headers)).json()["data"]
    assert [(r["name"], r["color"]) for r in rows] == [
        ("FOLLOW UP PENDING", "#FFF0C2"),
        ("NEXT FOLLOW UP", "#DCEBFF"),
        ("DISBURSE", "#D9F5E3"),
        ("REJECTED WITH REASON", "#FFE0E0"),
    ]
    a = await option(client, staff[1], "  Need   documents  ", "#abcdef")
    b = await option(client, staff[3], "Ready tomorrow")
    assert a["name"] == "Need documents" and a["color"] == "#ABCDEF"
    for headers in (staff[1], staff[3], owner_headers):
        shared = (await client.get(OPTIONS, headers=headers)).json()["data"]
        assert {a["id"], b["id"]} <= {r["id"] for r in shared}
    assert (await client.get(OPTIONS)).status_code == 401
    assert (
        await client.post(
            BASE + "/interest-options", headers=staff[1], json={"name": "Removed"}
        )
    ).status_code == 405
    assert (
        await client.post(
            BASE + "/follow-ups",
            headers=staff[1],
            json=follow(customer_interest_option_id=a["id"]),
        )
    ).status_code == 422
    assert (
        await mock_db.audit_logs.count_documents(
            {"event_type": "followup_status_option_created"}
        )
        == 2
    )


@pytest.mark.parametrize(
    "color", ["red", "#FFF", "#1234567", "123456", "#GGGGGG", "#000000;background:red"]
)
async def test_hex_validation(client, staff, color):
    assert (
        await client.post(
            OPTIONS, headers=staff[1], json={"name": "Bad color", "color": color}
        )
    ).status_code == 422


@pytest.mark.parametrize("name", ["", "   ", "x" * 61])
async def test_name_validation(client, staff, name):
    assert (
        await client.post(OPTIONS, headers=staff[1], json={"name": name})
    ).status_code == 422


async def test_duplicate_concurrent_create_and_stale_edits(client, staff):
    a = await option(client, staff[1], "Urgent CALL")
    for name in (
        "urgent call",
        "  URGENT   CALL  ",
        "\uff35\uff32\uff27\uff25\uff2e\uff34 CALL",
    ):
        assert (
            await client.post(OPTIONS, headers=staff[1], json={"name": name})
        ).status_code == 409
    responses = await asyncio.gather(
        *(
            client.post(OPTIONS, headers=staff[1], json={"name": "Concurrent"})
            for _ in range(8)
        )
    )
    assert sum(r.status_code == 200 for r in responses) == 1
    renamed = await client.patch(
        OPTIONS + "/" + a["id"],
        headers=staff[3],
        json={"name": "Renamed", "color": "#123456", "version": 1},
    )
    assert renamed.status_code == 200
    assert renamed.json()["data"]["value"] == a["value"]
    assert (
        await client.patch(
            OPTIONS + "/" + a["id"],
            headers=staff[1],
            json={"name": "Stale", "version": 1},
        )
    ).status_code == 409


async def test_defaults_protect_names_but_allow_recolor(client, staff):
    row = (await client.get(OPTIONS, headers=staff[1])).json()["data"][0]
    assert (
        await client.patch(
            OPTIONS + "/" + row["id"],
            headers=staff[1],
            json={"name": "Renamed default", "version": 1},
        )
    ).status_code == 422
    assert (
        await client.post(
            OPTIONS + "/" + row["id"] + "/archive",
            headers=staff[1],
            json={"version": 1},
        )
    ).status_code == 422
    saved = await client.patch(
        OPTIONS + "/" + row["id"],
        headers=staff[3],
        json={"name": row["name"], "color": "#000000", "version": 1},
    )
    assert saved.status_code == 200 and saved.json()["data"]["color"] == "#000000"


async def test_history_archive_filters_exports_and_legacy_data_preserved(
    client, mock_db, staff
):
    headers = staff[1]
    status = await option(client, headers, "Original label")
    row = await create(client, headers, "follow-ups", follow(status=status["value"]))
    assert row["status_display"] == "Original label"
    # Historical interest payload stays in storage but never surfaces in active API/export.
    await mock_db.daily_follow_ups.update_one(
        {"_id": ObjectId(row["id"])},
        {
            "$set": {
                "customer_interest_option_id": "old",
                "customer_interest_status_snapshot": "Historical interest",
            }
        },
    )
    await client.patch(
        OPTIONS + "/" + status["id"],
        headers=staff[3],
        json={"name": "New label", "color": "#123456", "version": 1},
    )
    await client.post(
        OPTIONS + "/" + status["id"] + "/archive", headers=staff[3], json={"version": 2}
    )
    assert status["id"] not in {
        r["id"] for r in (await client.get(OPTIONS, headers=headers)).json()["data"]
    }
    saved = await client.patch(
        BASE + "/follow-ups/" + row["id"],
        headers=headers,
        json=follow(
            status=status["value"], version=row["version"], remarks="Other edits"
        ),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["status_display"] == "Original label"
    assert "customer_interest" not in saved.text
    raw = await mock_db.daily_follow_ups.find_one({"_id": ObjectId(row["id"])})
    assert raw["customer_interest_status_snapshot"] == "Historical interest"
    assert len(raw["history"]) == 2 and raw["status"] == status["value"]
    assert (
        await client.post(
            BASE + "/follow-ups", headers=headers, json=follow(status=status["value"])
        )
    ).status_code == 422
    listed = (
        await client.get(
            BASE + "/follow-ups", headers=headers, params={"status": status["value"]}
        )
    ).json()["data"]
    assert listed["total"] == 1
    for fmt in ("csv", "xlsx"):
        export = await client.get(
            BASE + "/follow-ups/export",
            headers=headers,
            params={"format": fmt, "status": status["value"]},
        )
        assert export.status_code == 200, export.text
        if fmt == "csv":
            assert (
                "Original label" in export.text
                and "CUSTOMER INTEREST" not in export.text
            )
    assert (
        await client.post(
            OPTIONS + "/" + status["id"] + "/restore",
            headers=headers,
            json={"version": 3},
        )
    ).status_code == 200
    events = await mock_db.audit_logs.find(
        {"metadata.option_id": status["id"]}
    ).to_list(None)
    assert {e["event_type"] for e in events} == {
        "followup_status_option_created",
        "followup_status_option_updated",
        "followup_status_option_archived",
        "followup_status_option_restored",
    }


async def test_scope_and_inactive_employee(client, mock_db, staff, employee_headers):
    headers = staff[1]
    foreign = str(ObjectId())
    await mock_db.daily_followup_status_options.insert_one(
        {
            "_id": ObjectId(foreign),
            "company_id": "foreign",
            "value": "custom:foreign",
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
            BASE + "/follow-ups", headers=headers, json=follow(status="custom:foreign")
        )
    ).status_code == 422
    assert (
        await client.post(
            OPTIONS, headers=headers, json={"name": "Spoof", "company_id": "foreign"}
        )
    ).status_code == 422
    await mock_db.employees.update_one(
        {"_id": ObjectId(staff[0]["id"])}, {"$set": {"status": "inactive"}}
    )
    for actor in (headers, employee_headers):
        assert (await client.get(OPTIONS, headers=actor)).status_code == 403
        assert (
            await client.post(OPTIONS, headers=actor, json={"name": "Forbidden"})
        ).status_code == 403


async def test_status_changes_preserve_history_and_default_rules(client, staff):
    headers = staff[1]
    status = await option(client, headers)
    row = await create(client, headers, "follow-ups", follow(status=status["value"]))
    saved = await client.patch(
        BASE + "/follow-ups/" + row["id"],
        headers=headers,
        json=follow(
            version=row["version"],
            status="REJECTED WITH REASON",
            due_date=None,
            rejection_reason="Not eligible",
        ),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["status_display"] == "REJECTED WITH REASON"
    assert saved.json()["data"]["history"][-1]["before"]["status"] == status["value"]
    for status_name in ("DISBURSE", "REJECTED WITH REASON"):
        assert (
            await client.post(
                BASE + "/follow-ups",
                headers=headers,
                json=follow(status=status_name, due_date=None),
            )
        ).status_code == 422


async def test_unknown_legacy_status_can_be_retained_but_not_created(
    client, mock_db, staff
):
    headers = staff[1]
    row = await create(client, headers, "follow-ups", follow())
    await mock_db.daily_follow_ups.update_one(
        {"_id": ObjectId(row["id"])}, {"$set": {"status": "Legacy imported status"}}
    )
    assert (
        await client.patch(
            BASE + "/follow-ups/" + row["id"],
            headers=headers,
            json=follow(status="Legacy imported status", version=row["version"]),
        )
    ).status_code == 200
    assert (
        await client.post(
            BASE + "/follow-ups",
            headers=headers,
            json=follow(status="Legacy imported status"),
        )
    ).status_code == 422
