import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from app.core.exceptions import UnauthorizedError
from app.features.auth.session_lifecycle import (
    ensure_summary,
    expire_sessions,
    validate_family,
)
from app.features.daily_operations.attendance import union_seconds
from app.features.daily_operations.follow_status import (
    effective_status,
    reconcile_statuses,
)
from app.shared.customer_identity import normalize_mobile, normalized_name
from bson import ObjectId

NOW = datetime(2026, 10, 26, 9, tzinfo=UTC)


@pytest.mark.parametrize(
    "offset,expected",
    [(-1, "FOLLOW UP PENDING"), (0, "FOLLOW UP PENDING"), (1, "NEXT FOLLOW UP")],
)
def test_effective_dates(offset, expected):
    assert (
        effective_status("NEXT FOLLOW UP", NOW + timedelta(days=offset), NOW)
        == expected
    )


@pytest.mark.parametrize("status", ["DISBURSE", "REJECTED WITH REASON"])
def test_terminal_and_missing_date(status):
    assert effective_status(status, NOW - timedelta(days=1), NOW) == status
    assert effective_status("NEXT FOLLOW UP", None, NOW) == "NEXT FOLLOW UP"


def test_business_midnight():
    due = datetime(2026, 10, 26, 18, 30, tzinfo=UTC)
    assert (
        effective_status("NEXT FOLLOW UP", due, due - timedelta(seconds=1))
        == "NEXT FOLLOW UP"
    )
    assert effective_status("NEXT FOLLOW UP", due, due) == "FOLLOW UP PENDING"


async def test_worker_transitions_without_page_and_idempotency(mock_db, monkeypatch):
    from app.features.daily_operations import follow_status

    monkeypatch.setattr(follow_status, "utc_now", lambda: NOW)
    await mock_db.daily_follow_ups.insert_one(
        {
            "status": "NEXT FOLLOW UP",
            "due_date": NOW,
            "is_deleted": False,
            "version": 1,
            "history": [],
        }
    )
    counts = await asyncio.gather(
        reconcile_statuses(mock_db), reconcile_statuses(mock_db)
    )
    assert sum(counts) == 1
    record = await mock_db.daily_follow_ups.find_one({})
    assert record["status"] == "FOLLOW UP PENDING"
    assert record["version"] == 2
    assert len(record["history"]) == 1
    assert record["history"][0]["source"] == "automatic"


@pytest.mark.parametrize(
    "mobile", ["9663589524", "+91 9663589524", "0091-9663589524", "91 (96635) 89524"]
)
def test_mobile_variations(mobile):
    assert normalize_mobile(mobile) == "9663589524"
    assert normalized_name("Surag R.") == normalized_name(" SURAG   R ")


@pytest.mark.parametrize(
    "mobile", ["", "abc9663589524", "+1 9663589524", "96635895240", None]
)
def test_invalid_mobile(mobile):
    with pytest.raises(ValueError):
        normalize_mobile(mobile)


def test_duration_gaps_and_overlap():
    def at(hour, minute=0):
        return NOW.replace(hour=hour, minute=minute)

    assert (
        union_seconds([(at(9), at(10)), (at(10, 30), at(11)), (at(12), at(13))]) == 9000
    )
    assert (
        union_seconds([(at(9), at(10)), (at(9, 30), at(11)), (at(12), at(11))]) == 7200
    )


async def test_daily_key_concurrent_and_next_day(mock_db):
    keys = await asyncio.gather(
        *(ensure_summary(mock_db, "employee", NOW) for _ in range(20))
    )
    assert len(set(keys)) == 1
    assert await mock_db.attendance_days.count_documents({}) == 1
    assert await ensure_summary(mock_db, "employee", NOW + timedelta(days=1)) != keys[0]


async def test_timeout_no_browser_and_cannot_resurrect(mock_db, monkeypatch):
    from app.features.auth import session_lifecycle

    monkeypatch.setattr(session_lifecycle, "utc_now", lambda: NOW)
    await mock_db.sessions.insert_one(
        {
            "family_id": "idle",
            "user_id": "employee",
            "status": "active",
            "is_deleted": False,
            "last_activity_at": NOW - timedelta(minutes=10),
            "version": 1,
        }
    )
    with pytest.raises(UnauthorizedError):
        await validate_family(mock_db, "employee", "idle", activity=True)
    session = await mock_db.sessions.find_one({})
    assert session["logout_at"] == NOW
    assert session["end_reason"] == "inactivity_timeout"
    assert await expire_sessions(mock_db) == 0


async def test_activity_isolated_by_family(mock_db, monkeypatch):
    from app.features.auth import session_lifecycle

    monkeypatch.setattr(session_lifecycle, "utc_now", lambda: NOW)
    for family in ("tab1", "device2"):
        await mock_db.sessions.insert_one(
            {
                "family_id": family,
                "user_id": "employee",
                "status": "active",
                "is_deleted": False,
                "last_activity_at": NOW - timedelta(minutes=9),
                "version": 1,
            }
        )
    await validate_family(mock_db, "employee", "tab1", activity=True)
    other = await mock_db.sessions.find_one({"family_id": "device2"})
    assert other["last_activity_at"] == NOW - timedelta(minutes=9)


async def test_expired_access_and_refresh_denied(client, mock_db, owner_headers):
    await mock_db.sessions.update_many(
        {}, {"$set": {"last_activity_at": datetime.now(UTC) - timedelta(minutes=11)}}
    )
    assert (
        await client.get("/api/v1/auth/profile", headers=owner_headers)
    ).status_code == 401
    assert (
        await client.post("/api/v1/auth/activity", headers=owner_headers)
    ).status_code == 401


async def test_stronger_unique_index_and_report(mock_db):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "hardening_migration",
        Path(__file__).resolve().parents[2]
        / "scripts/migrate_daily_attendance_identity.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for phone in ("9663589524", "+91 9663589524"):
        await mock_db.leads.insert_one(
            {"_id": ObjectId(), "mobile": phone, "is_deleted": False}
        )
    report = await module.inspect(mock_db)
    assert len(report["identity_conflicts"]) == 1
    assert len(report["noncanonical_mobile"]) == 1
    with pytest.raises(ValueError):
        await module.apply(mock_db, report)
    assert await mock_db.leads.count_documents({}) == 2


async def test_daily_summary_accumulates_history_and_active_overlap(
    mock_db, monkeypatch
):
    from app.features.auth.models import User
    from app.features.daily_operations import attendance
    from app.features.daily_operations.service import DailyOperationsService

    monkeypatch.setattr(attendance, "utc_now", lambda: NOW.replace(hour=13))
    user_id = str(ObjectId())
    actor = User(id=str(ObjectId()), mobile="9000000001", role="owner")
    await mock_db.employees.insert_one(
        {"user_id": user_id, "display_name": "Synthetic Employee", "is_deleted": False}
    )
    await ensure_summary(mock_db, user_id, NOW)
    for i, (start, finish) in enumerate([(9, 10), (10.5, 11), (12, 13)]):
        login = NOW.replace(hour=int(start), minute=30 if start == 10.5 else 0)
        end = NOW.replace(hour=finish)
        await mock_db.sessions.insert_one(
            {
                "family_id": f"family{i}",
                "user_id": user_id,
                "login_at": login,
                "logout_at": end,
                "last_activity_at": end,
                "status": "logged_out",
                "end_reason": "manual_logout",
                "updated_at": end,
                "is_deleted": False,
            }
        )
    result = await attendance.daily_sessions(DailyOperationsService(mock_db), actor)
    assert result["total"] == 1
    row = result["items"][0]
    assert row["recorded_seconds"] == 9000
    assert len(row["sessions"]) == 3
    assert row["status"] == "logged_out"
    await mock_db.sessions.insert_one(
        {
            "family_id": "active-device",
            "user_id": user_id,
            "login_at": NOW.replace(hour=12, minute=30),
            "logout_at": None,
            "last_activity_at": NOW.replace(hour=12, minute=59),
            "status": "active",
            "updated_at": NOW.replace(hour=12, minute=59),
            "is_deleted": False,
        }
    )
    result = await attendance.daily_sessions(DailyOperationsService(mock_db), actor)
    assert result["items"][0]["status"] == "active"
    assert result["items"][0]["recorded_seconds"] == 9000  # overlap counted once


async def test_followup_filter_export_and_reopen_agree(
    client, mock_db, owner_headers, monkeypatch
):
    from app.features.daily_operations import service
    from app.features.daily_operations.catalog import install_catalog

    await install_catalog(mock_db)
    monkeypatch.setattr(service, "utc_now", lambda: NOW)
    payload = {
        "date": "2026-10-25",
        "remarks_date": "2026-10-25",
        "customer_name": "Synthetic Customer",
        "customer_number": "+91 9663589524",
        "bank": "Synthetic Bank",
        "status": "NEXT FOLLOW UP",
        "due_date": "2026-10-26",
        "next_action": "Call customer",
    }
    response = await client.post(
        "/api/v1/daily-operations/follow-ups", json=payload, headers=owner_headers
    )
    assert response.status_code == 200, response.text
    record = response.json()["data"]
    assert record["status"] == "FOLLOW UP PENDING"
    response = await client.get(
        "/api/v1/daily-operations/follow-ups?status=FOLLOW+UP+PENDING",
        headers=owner_headers,
    )
    assert response.json()["data"]["total"] == 1
    response = await client.get(
        "/api/v1/daily-operations/follow-ups/export", headers=owner_headers
    )
    assert "FOLLOW UP PENDING" in response.text
    terminal = {
        **payload,
        "version": record["version"],
        "status": "REJECTED WITH REASON",
        "due_date": None,
        "rejection_reason": "Not eligible",
    }
    url = f"/api/v1/daily-operations/follow-ups/{record['id']}"
    response = await client.patch(url, json=terminal, headers=owner_headers)
    assert response.status_code == 200, response.text
    reopened = {
        **payload,
        "version": response.json()["data"]["version"],
        "due_date": "2026-10-27",
    }
    response = await client.patch(url, json=reopened, headers=owner_headers)
    assert response.json()["data"]["status"] == "NEXT FOLLOW UP"
    stored = await mock_db.daily_follow_ups.find_one({"_id": ObjectId(record["id"])})
    assert len(stored["history"]) == 3


async def test_family_revocation_rejects_racing_refresh_child(mock_db):
    for status in ("revoked", "active"):
        await mock_db.sessions.insert_one(
            {
                "family_id": "same-family",
                "user_id": "employee",
                "status": status,
                "is_deleted": False,
                "last_activity_at": datetime.now(UTC),
            }
        )
    with pytest.raises(UnauthorizedError):
        await validate_family(mock_db, "employee", "same-family", activity=True)


async def test_login_request_retry_is_one_session(client, mock_db, owner_headers):
    from uuid import uuid4

    key = str(uuid4())
    payload = {"mobile": "9000000001", "password": "OwnerPass1!"}
    responses = await asyncio.gather(
        *(
            client.post(
                "/api/v1/auth/login", json=payload, headers={"Idempotency-Key": key}
            )
            for _ in range(2)
        )
    )
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert responses[0].json()["data"] == responses[1].json()["data"]
    assert (
        await mock_db.sessions.count_documents({"login_request_key": {"$exists": True}})
        == 1
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={**payload, "password": "wrong"},
        headers={"Idempotency-Key": key},
    )
    assert (
        response.status_code == 401
    )  # A receipt never bypasses credential validation.


async def test_correction_moved_to_another_business_day_remains_visible(
    mock_db, monkeypatch
):
    from app.features.auth.models import User
    from app.features.daily_operations import attendance
    from app.features.daily_operations.service import DailyOperationsService
    from app.features.daily_operations.views import SessionCorrection, correct_session
    from app.utils.datetime import to_ist

    monkeypatch.setattr(attendance, "utc_now", lambda: NOW)
    user_id = str(ObjectId())
    actor = User(id=str(ObjectId()), mobile="9000000001", role="owner")
    await mock_db.employees.insert_one(
        {"user_id": user_id, "display_name": "Synthetic", "is_deleted": False}
    )
    await ensure_summary(mock_db, user_id, NOW)
    await mock_db.sessions.insert_one(
        {
            "family_id": "corrected",
            "user_id": user_id,
            "login_at": NOW - timedelta(hours=2),
            "logout_at": NOW - timedelta(hours=1),
            "last_activity_at": NOW - timedelta(hours=1),
            "status": "logged_out",
            "is_deleted": False,
            "updated_at": NOW,
        }
    )
    service = DailyOperationsService(mock_db)
    await correct_session(
        service,
        actor,
        "corrected",
        SessionCorrection(
            login_at=NOW - timedelta(days=1, hours=2),
            logout_at=NOW - timedelta(days=1, hours=1),
            reason="Corrected wrong business date",
        ),
    )
    day = to_ist(NOW - timedelta(days=1)).date()
    result = await attendance.daily_sessions(service, actor, date_from=day, date_to=day, month=day.isoformat()[:7])
    assert result["total"] == 1
    assert result["items"][0]["recorded_seconds"] == 3600
    assert (
        result["items"][0]["sessions"][0]["end_reason"] == "administrative_correction"
    )
    original = await mock_db.sessions.find_one({"family_id": "corrected"})
    assert original["login_at"] == NOW - timedelta(hours=2)


async def test_identity_unique_migration_concurrent_create_and_name_warning(
    client, mock_db, owner_headers
):
    import importlib.util
    from pathlib import Path

    from test_leads import _lead_master_data, _lead_payload

    spec = importlib.util.spec_from_file_location(
        "identity_migration",
        Path(__file__).resolve().parents[2]
        / "scripts/migrate_daily_attendance_identity.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = await module.inspect(mock_db)
    await module.apply(mock_db, report)
    master = await _lead_master_data(mock_db)
    payload = {**_lead_payload(master, mobile="9663589524"), "full_name": "Surag R."}
    responses = await asyncio.gather(
        *(
            client.post("/api/v1/leads", json=payload, headers=owner_headers)
            for _ in range(2)
        )
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    response = await client.post(
        "/api/v1/leads",
        json={**payload, "mobile": "+91 9663589524", "full_name": "Different Person"},
        headers=owner_headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["details"]["identity_conflict"] is True
    response = await client.post(
        "/api/v1/leads",
        json={**payload, "mobile": "9663589525", "full_name": " SURAG R "},
        headers=owner_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["is_potential_duplicate"] is True
    assert await mock_db.leads.count_documents({}) == 2


def test_duration_uses_instants_across_daylight_saving():
    from zoneinfo import ZoneInfo

    zone = ZoneInfo("America/New_York")
    start = datetime(2026, 3, 8, 1, 30, tzinfo=zone)
    finish = datetime(2026, 3, 8, 3, 30, tzinfo=zone)
    assert union_seconds([(start, finish)]) == 3600


async def test_cross_midnight_time_is_clipped_to_each_day(mock_db, monkeypatch):
    from app.features.auth.models import User
    from app.features.daily_operations import attendance
    from app.features.daily_operations.service import DailyOperationsService

    boundary = NOW.replace(hour=18, minute=30) - timedelta(days=1)
    monkeypatch.setattr(attendance, "utc_now", lambda: boundary + timedelta(minutes=5))
    user_id = str(ObjectId())
    actor = User(id=str(ObjectId()), mobile="9000000001", role="owner")
    await mock_db.employees.insert_one(
        {"user_id": user_id, "display_name": "Synthetic", "is_deleted": False}
    )
    for instant in (boundary - timedelta(minutes=5), boundary):
        await ensure_summary(mock_db, user_id, instant)
    await mock_db.sessions.insert_one(
        {
            "family_id": "overnight",
            "user_id": user_id,
            "login_at": boundary - timedelta(minutes=5),
            "logout_at": None,
            "last_activity_at": boundary + timedelta(minutes=4),
            "status": "active",
            "updated_at": boundary + timedelta(minutes=4),
            "is_deleted": False,
        }
    )
    result = await attendance.daily_sessions(DailyOperationsService(mock_db), actor)
    assert result["total"] == 2
    current, previous = result["items"]
    assert current["recorded_seconds"] == previous["recorded_seconds"] == 300
    assert current["status"] == "active" and previous["status"] == "day_completed"
    assert current["logout_at"] is None and previous["logout_at"] is None
