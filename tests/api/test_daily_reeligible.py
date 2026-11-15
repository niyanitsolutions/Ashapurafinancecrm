# ruff: noqa: F811
"""Controlled business-date and actual worker-entry regression coverage."""

import asyncio
from datetime import datetime, timezone

from app.features.daily_operations import reeligible
from bson import ObjectId
from test_daily_simple_entry import follow, staff  # noqa: F401

BASE = "/api/v1/daily-operations"
NOW = datetime(2026, 11, 19, 18, 30, tzinfo=timezone.utc)  # 20 November in India.


async def create(client, headers, **changes):
    response = await client.post(
        BASE + "/follow-ups",
        headers=headers,
        json=follow(
            status="Re-Eligible", due_date=None, reeligible_date="2026-11-20", **changes
        ),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def test_required_date_custom_label_and_legacy_records(client, mock_db, staff):
    headers = staff[1]
    response = await client.post(
        BASE + "/follow-ups",
        headers=headers,
        json=follow(status="Re-Eligible", due_date=None),
    )
    assert response.status_code == 422
    option = await client.post(
        BASE + "/follow-up-status-options",
        headers=headers,
        json={"name": "Re Eligible"},
    )
    assert option.status_code == 200, option.text
    custom = option.json()["data"]["value"]
    response = await client.post(
        BASE + "/follow-ups", headers=headers, json=follow(status=custom, due_date=None)
    )
    assert response.status_code == 422
    row = await create(client, headers)
    await mock_db.daily_follow_ups.update_one(
        {"_id": ObjectId(row["id"])},
        {"$unset": {"reeligible_date": "", "reeligible_state": ""}},
    )
    assert (await client.get(BASE + "/follow-ups", headers=headers)).json()["data"][
        "total"
    ] == 1
    assert (
        await client.get(BASE + "/follow-ups?workflow=reeligible", headers=headers)
    ).json()["data"]["total"] == 0


async def test_actual_worker_midnight_overdue_idempotence_and_resume(
    client, mock_db, staff, monkeypatch
):
    headers = staff[1]
    row = await create(client, headers)
    from app.worker.tasks import daily_operations as worker

    monkeypatch.setattr(worker, "get_database", lambda: mock_db)
    monkeypatch.setattr(reeligible, "utc_now", lambda: NOW)
    # The scheduled callback executes without an authenticated request or open page.
    await worker.check_daily_operations_notifications({})
    await worker.check_daily_operations_notifications({})
    raw = await mock_db.daily_follow_ups.find_one({"_id": ObjectId(row["id"])})
    assert raw["reeligible_state"] == "ready"
    automatic = [event for event in raw["history"] if event.get("automatic")]
    assert len(automatic) == 1 and automatic[0]["business_date"] == "2026-11-20"
    assert (
        raw["customer_name"] == row["customer_name"]
        and raw["assigned_to"] == row["assigned_to"]
    )
    assert (await client.get(BASE + "/follow-ups", headers=headers)).json()["data"][
        "total"
    ] == 0
    ready = (
        await client.get(BASE + "/follow-ups?workflow=reeligible", headers=headers)
    ).json()["data"]
    assert [item["id"] for item in ready["items"]] == [row["id"]]
    changed = await client.patch(
        BASE + "/follow-ups/" + row["id"],
        headers=headers,
        json=follow(status="DISBURSE", due_date=None, version=raw["version"]),
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["data"]["reeligible_date"] == "2026-11-20"
    assert (
        await client.get(BASE + "/follow-ups?workflow=reeligible", headers=headers)
    ).json()["data"]["total"] == 0
    await create(client, headers)
    monkeypatch.setattr(
        reeligible, "utc_now", lambda: datetime(2026, 12, 1, tzinfo=timezone.utc)
    )
    await worker.check_daily_operations_notifications({})
    assert (
        await client.get(BASE + "/follow-ups?workflow=reeligible", headers=headers)
    ).json()["data"]["total"] == 1


async def test_future_boundary_concurrent_transition_and_stale_edit(
    client, mock_db, staff, monkeypatch
):
    row = await create(client, staff[1])
    monkeypatch.setattr(
        reeligible,
        "utc_now",
        lambda: datetime(2026, 11, 19, 18, 29, 59, tzinfo=timezone.utc),
    )
    assert await reeligible.reconcile_reeligible(mock_db) == 0
    monkeypatch.setattr(reeligible, "utc_now", lambda: NOW)
    counts = await asyncio.gather(
        reeligible.reconcile_reeligible(mock_db),
        reeligible.reconcile_reeligible(mock_db),
    )
    assert sum(counts) == 1
    changed = await client.patch(
        BASE + "/follow-ups/" + row["id"],
        headers=staff[1],
        json=follow(status="DISBURSE", due_date=None, version=row["version"]),
    )
    assert changed.status_code == 409


async def test_status_priority_precedes_pagination_and_search(
    client, mock_db, staff, owner_headers
):
    # Seed historical records directly, including a custom status ID with its saved label.
    statuses = [
        "REJECTED WITH REASON",
        "Re-Eligible",
        "DISBURSE",
        "CASE ON HOLD WITH REASON",
        "NEXT FOLLOW UP",
        "FOLLOW UP PENDING",
    ]
    rows = []
    for index, status in enumerate(statuses):
        rows.append(
            {
                "_id": ObjectId(),
                "import_key": str(ObjectId()),
                "is_deleted": False,
                "version": 1,
                "status": status,
                "status_label": None,
                "date": NOW,
                "due_date": None,
                "customer_name": "Priority sample",
                "customer_number": "9000000000",
                "assigned_to": staff[0]["id"],
                "history": [],
                "reeligible_date": datetime(2026, 12, 1, tzinfo=timezone.utc),
                "reeligible_state": "waiting"
                if status == "Re-Eligible"
                else "inactive",
            }
        )
    await mock_db.daily_follow_ups.insert_many(rows)
    result = []
    for page in range(1, 4):
        response = await client.get(
            BASE + f"/follow-ups?page_size=2&page={page}&search=Priority",
            headers=owner_headers,
        )
        assert response.status_code == 200, response.text
        result.extend(item["status"] for item in response.json()["data"]["items"])
    assert result == list(reversed(statuses))
    foreign = await client.get(
        BASE + "/follow-ups?workflow=reeligible", headers=staff[3]
    )
    assert foreign.json()["data"]["total"] == 0


async def test_ready_edits_reschedule_new_cycle_and_private_access(
    client, mock_db, staff, monkeypatch
):
    row = await create(client, staff[1])
    monkeypatch.setattr(reeligible, "utc_now", lambda: NOW)
    await reeligible.reconcile_reeligible(mock_db)
    record = (
        await client.get(BASE + "/follow-ups/" + row["id"], headers=staff[1])
    ).json()["data"]
    assert (
        await client.get(BASE + "/follow-ups/" + row["id"], headers=staff[3])
    ).status_code in {403, 404}
    payload = follow(
        status="Re-Eligible",
        due_date=None,
        reeligible_date="2026-11-20",
        remarks="Updated remarks",
        version=record["version"],
    )
    edited = await client.patch(
        BASE + "/follow-ups/" + row["id"], headers=staff[1], json=payload
    )
    assert edited.status_code == 200, edited.text
    current = edited.json()["data"]
    assert current["reeligible_state"] == "ready"
    payload.update(reeligible_date="2026-12-01", version=current["version"])
    edited = await client.patch(
        BASE + "/follow-ups/" + row["id"], headers=staff[1], json=payload
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["data"]["reeligible_state"] == "waiting"
    assert await reeligible.reconcile_reeligible(mock_db) == 0
    assert (
        await client.get(BASE + "/follow-ups?workflow=reeligible", headers=staff[1])
    ).json()["data"]["total"] == 0
    assert (
        await client.request(
            "DELETE",
            BASE + "/follow-ups/" + row["id"],
            headers=staff[1],
            json={"version": edited.json()["data"]["version"]},
        )
    ).status_code == 403


async def test_priority_uses_effective_business_date_status_before_pagination(
    client, mock_db, staff, owner_headers
):
    from datetime import timedelta

    from app.utils.datetime import utc_now

    now = utc_now()
    ids = [ObjectId(), ObjectId()]
    await mock_db.daily_follow_ups.insert_many(
        [
            {
                "_id": ids[0],
                "import_key": str(ids[0]),
                "is_deleted": False,
                "version": 1,
                "status": "NEXT FOLLOW UP",
                "date": now,
                "due_date": now - timedelta(days=1),
                "customer_name": "Effective status",
                "customer_number": "9000000000",
                "history": [],
            },
            {
                "_id": ids[1],
                "import_key": str(ids[1]),
                "is_deleted": False,
                "version": 1,
                "status": "FOLLOW UP PENDING",
                "date": now + timedelta(days=1),
                "due_date": now + timedelta(days=2),
                "customer_name": "Effective status",
                "customer_number": "9000000000",
                "history": [],
            },
        ]
    )
    response = await client.get(
        BASE + "/follow-ups?page_size=1&search=Effective", headers=owner_headers
    )
    assert response.status_code == 200, response.text
    first = response.json()["data"]["items"][0]
    assert first["id"] == str(ids[0]) and first["status"] == "FOLLOW UP PENDING"
