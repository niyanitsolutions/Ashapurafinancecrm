import asyncio
import csv
import io
from datetime import UTC, date, datetime, timedelta

import pytest
from app.core.exceptions import ValidationError
from app.features.auth.models import User
from app.features.auth.session_lifecycle import (
    ensure_summary,
    ensure_summary_range,
    expire_sessions,
)
from app.features.daily_operations import attendance, reconciliation
from app.features.daily_operations.calendar import day_segments, month_bounds
from app.features.daily_operations.catalog import install_catalog
from app.features.daily_operations.service import DailyOperationsService
from bson import ObjectId
from openpyxl import load_workbook

NOW = datetime(2026, 10, 27, 0, tzinfo=UTC)
BOUNDARY = datetime(2026, 10, 26, 18, 30, tzinfo=UTC)


async def employee(db, user_id=None, name="Synthetic Employee"):
    user_id = user_id or str(ObjectId())
    if not await db.users.find_one({"_id": ObjectId(user_id)}):
        await db.users.insert_one(
            {"_id": ObjectId(user_id), "mobile": str(ObjectId()), "role": "employee"}
        )
    result = await db.employees.insert_one(
        {
            "user_id": user_id,
            "display_name": name,
            "first_name": "Synthetic",
            "last_name": name,
            "mobile": "9000000000",
            "department_id": str(ObjectId()),
            "designation_id": str(ObjectId()),
            "branch_id": str(ObjectId()),
            "joining_date": NOW,
            "employment_type": "full_time",
            "employee_code": f"test-{ObjectId()}",
            "email": f"test-{ObjectId()}@example.invalid",
            "status": "active",
            "is_deleted": False,
        }
    )
    return user_id, str(result.inserted_id)


async def session(
    db, user_id, login, end=None, *, activity=None, family=None, reason="manual_logout"
):
    family = family or str(ObjectId())
    await db.sessions.insert_one(
        {
            "token_id": str(ObjectId()),
            "family_id": family,
            "user_id": user_id,
            "login_at": login,
            "logout_at": end,
            "last_activity_at": activity or end or login,
            "status": "logged_out" if end else "active",
            "end_reason": reason if end else None,
            "updated_at": end or activity or login,
            "is_deleted": False,
            "version": 1,
        }
    )
    await ensure_summary_range(db, user_id, login, end or activity or login)
    await ensure_summary(db, user_id, login)
    return family


def owner():
    return User(id=str(ObjectId()), role="owner", mobile="9000000001")


@pytest.mark.parametrize(
    "month,start,end",
    [
        ("2026-10", date(2026, 10, 1), date(2026, 11, 1)),
        ("2026-12", date(2026, 12, 1), date(2027, 1, 1)),
        ("2024-02", date(2024, 2, 1), date(2024, 3, 1)),
        ("2026-02", date(2026, 2, 1), date(2026, 3, 1)),
    ],
)
def test_month_half_open_boundaries(month, start, end):
    assert month_bounds(month, NOW) == (month, start, end)


@pytest.mark.parametrize(
    "month", ["", "2026-13", "2026-00", "2026-2", "0000-01", "9999-12", "invalid"]
)
def test_invalid_month(month):
    with pytest.raises(ValidationError):
        month_bounds(month, NOW)


def test_default_month_uses_business_midnight():
    instant = datetime(2026, 10, 31, 18, 30, tzinfo=UTC)
    assert month_bounds(None, instant)[0] == "2026-11"
    assert month_bounds(None, instant - timedelta(microseconds=1))[0] == "2026-10"


async def test_continuous_midnight_session_retains_original_but_splits_summary(
    mock_db, monkeypatch
):
    monkeypatch.setattr(attendance, "utc_now", lambda: NOW)
    user_id, _ = await employee(mock_db)
    login, end = BOUNDARY - timedelta(minutes=30), BOUNDARY + timedelta(minutes=30)
    family = await session(mock_db, user_id, login, end)
    result = await attendance.daily_sessions(
        DailyOperationsService(mock_db), owner(), month="2026-10"
    )
    current, previous = result["items"]
    assert result["total"] == 2
    assert current["date"] == "2026-10-27" and previous["date"] == "2026-10-26"
    assert current["login_at"] == BOUNDARY and previous["login_at"] == login
    assert current["logout_at"] == end and previous["logout_at"] is None
    assert current["recorded_seconds"] == previous["recorded_seconds"] == 1800
    assert current["sessions"][0]["login_at"] == login
    assert previous["sessions"][0]["segment_end_at"] == BOUNDARY
    assert previous["sessions"][0]["segment_status"] == "day_boundary"
    assert previous["status"] == "day_completed"
    assert await mock_db.sessions.count_documents({"family_id": family}) == 1


def test_exact_midnight_end_never_creates_an_extra_day_or_loses_seconds():
    segments = list(day_segments(BOUNDARY - timedelta(seconds=1), BOUNDARY))
    assert len(segments) == 1
    assert segments[0][0] == date(2026, 10, 26)
    assert (segments[0][2] - segments[0][1]).total_seconds() == 1


async def test_timeout_crosses_midnight_without_browser_and_is_idempotent(
    mock_db, monkeypatch
):
    from app.features.auth import session_lifecycle

    monkeypatch.setattr(
        session_lifecycle, "utc_now", lambda: BOUNDARY + timedelta(minutes=6)
    )
    monkeypatch.setattr(attendance, "utc_now", lambda: BOUNDARY + timedelta(minutes=6))
    user_id, _ = await employee(mock_db)
    login, last_activity = (
        BOUNDARY - timedelta(minutes=30),
        BOUNDARY - timedelta(minutes=5),
    )
    family = await session(mock_db, user_id, login, activity=last_activity)
    assert await mock_db.attendance_days.count_documents({"user_id": user_id}) == 1
    assert await expire_sessions(mock_db) == 1
    assert await expire_sessions(mock_db) == 0
    result = await attendance.daily_sessions(
        DailyOperationsService(mock_db), owner(), month="2026-10"
    )
    current, previous = result["items"]
    assert current["recorded_seconds"] == 300 and previous["recorded_seconds"] == 1800
    assert current["login_at"] == BOUNDARY and current["status"] == "timed_out"
    stored = await mock_db.sessions.find_one({"family_id": family})
    assert stored["login_at"] == login and stored["logout_at"] == BOUNDARY + timedelta(
        minutes=5
    )
    assert len(stored["lifecycle_history"]) == 1


async def test_repeated_sessions_and_overlap_preserve_first_login_and_last_logout(
    mock_db, monkeypatch
):
    monkeypatch.setattr(attendance, "utc_now", lambda: NOW)
    user_id, _ = await employee(mock_db)
    for start, end in [(0, 60), (90, 120), (180, 240), (190, 230)]:
        await session(
            mock_db,
            user_id,
            BOUNDARY - timedelta(hours=12) + timedelta(minutes=start),
            BOUNDARY - timedelta(hours=12) + timedelta(minutes=end),
        )
    await asyncio.gather(
        *(
            ensure_summary(mock_db, user_id, BOUNDARY - timedelta(hours=1))
            for _ in range(20)
        )
    )
    result = await attendance.daily_sessions(
        DailyOperationsService(mock_db), owner(), month="2026-10"
    )
    assert result["total"] == 1
    row = result["items"][0]
    assert row["recorded_seconds"] == 9000 and len(row["sessions"]) == 4
    assert row["login_at"] == BOUNDARY - timedelta(hours=12)
    assert row["logout_at"] == BOUNDARY - timedelta(hours=8)


@pytest.mark.parametrize("format", ["csv", "xlsx"])
async def test_month_employee_pagination_and_export_are_scoped(
    client, mock_db, owner_headers, employee_headers, monkeypatch, format
):
    await install_catalog(mock_db)
    monkeypatch.setattr(attendance, "utc_now", lambda: NOW)
    own = await mock_db.users.find_one({"role": "employee"})
    user_a, employee_a = await employee(mock_db, str(own["_id"]), "Synthetic A")
    user_b, employee_b = await employee(mock_db, name="Synthetic B")
    # The authenticated employee fixture already has a real login-day summary.
    expected_october_dates = {"2026-10-01", "2026-10-31"} | {
        row["date"]
        async for row in mock_db.attendance_days.find({"user_id": user_a})
        if row["date"].startswith("2026-10-")
    }
    for user_id in (user_a, user_b):
        for day in (
            datetime(2026, 9, 30, 5, tzinfo=UTC),
            datetime(2026, 10, 1, 5, tzinfo=UTC),
            datetime(2026, 10, 31, 5, tzinfo=UTC),
            datetime(2026, 11, 1, 5, tzinfo=UTC),
        ):
            await session(mock_db, user_id, day, day + timedelta(minutes=30))
    url = "/api/v1/daily-operations/sessions"
    response = await client.get(
        f"{url}?month=2026-10&employee={employee_a}&page_size=1", headers=owner_headers
    )
    data = response.json()["data"]
    assert response.status_code == 200, response.text
    assert data["total"] == len(expected_october_dates) and len(data["items"]) == 1
    assert data["items"][0]["date"] == "2026-10-31"
    response = await client.get(
        f"{url}?month=2026-09&employee_name=Synthetic+B", headers=owner_headers
    )
    assert response.json()["data"]["total"] == 1
    response = await client.get(url, headers=owner_headers)
    assert response.json()["data"]["month"] == "2026-10"
    response = await client.get(f"{url}?month=2024-02", headers=owner_headers)
    assert response.json()["data"]["items"] == []
    response = await client.get(
        f"{url}?month=2026-10&employee={employee_b}", headers=employee_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["total"] == 0
    response = await client.get(
        f"{url}/export?month=2026-10&format={format}", headers=employee_headers
    )
    assert response.status_code == 200, response.text
    if format == "csv":
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    else:
        workbook = load_workbook(io.BytesIO(response.content))
        rows = list(workbook.active.values)
        workbook.close()
    assert len(rows) == len(expected_october_dates) + 1
    assert {row[0] for row in rows[1:]} == expected_october_dates
    assert {row[1] for row in rows[1:]} == {"Synthetic A"}


async def test_reconciliation_dry_run_apply_repeat_and_manual_correction_preservation(
    mock_db,
):
    user_id, _ = await employee(mock_db)
    login, end = BOUNDARY - timedelta(minutes=30), BOUNDARY + timedelta(minutes=30)
    family = await session(mock_db, user_id, login, end)
    # Simulate interrupted legacy materialization in this isolated fixture only.
    await mock_db.attendance_days.delete_many({})
    correction = {
        "_id": family,
        "user_id": user_id,
        "login_at": login,
        "logout_at": end,
        "reason": "Verified owner correction",
        "version": 1,
        "history": [{"reason": "kept"}],
    }
    await mock_db.session_corrections.insert_one(correction.copy())
    raw = await mock_db.sessions.find_one({"family_id": family})
    dry = await reconciliation.reconcile_attendance(mock_db, now=NOW)
    assert dry["status"] == "PASS" and dry["planned_inserts"] == 2
    assert dry["before"] == dry["after"] and dry["cross_midnight_families"] == 1
    applied = await reconciliation.reconcile_attendance(mock_db, now=NOW, apply=True)
    assert applied["created"] == 2 and applied["after"]["attendance_days"] == 2
    again = await reconciliation.reconcile_attendance(mock_db, now=NOW, apply=True)
    assert again["created"] == 0
    assert await mock_db.sessions.find_one({"family_id": family}) == raw
    assert await mock_db.session_corrections.find_one({"_id": family}) == correction


async def test_reconciliation_blocks_ambiguous_sources_and_retains_wrong_summary_metadata(
    mock_db,
):
    user_id, _ = await employee(mock_db)
    await session(
        mock_db,
        user_id,
        BOUNDARY - timedelta(minutes=30),
        BOUNDARY + timedelta(minutes=30),
    )
    await mock_db.attendance_days.update_one(
        {"_id": f"{user_id}:2026-10-27"},
        {
            "$set": {
                "login_at": BOUNDARY - timedelta(minutes=30),
                "recorded_seconds": 999999,
            }
        },
    )
    await mock_db.sessions.insert_one(
        {
            "family_id": "ambiguous",
            "user_id": user_id,
            "login_at": BOUNDARY,
            "last_activity_at": BOUNDARY,
            "status": "revoked",
            "is_deleted": False,
        }
    )
    report = await reconciliation.reconcile_attendance(mock_db, now=NOW, apply=True)
    assert report["status"] == "BLOCKED" and report["created"] == 0
    assert report["wrong_stored_login_dates"] == report["wrong_stored_durations"] == 1
    assert report["before"] == report["after"]
    assert any(
        issue["kind"] == "ended_family_missing_logout" for issue in report["issues"]
    )


def test_fractional_seconds_are_not_lost_between_calendar_dates():
    segments = list(
        day_segments(
            BOUNDARY - timedelta(milliseconds=500),
            BOUNDARY + timedelta(milliseconds=500),
        )
    )
    durations = [attendance.union_seconds([(start, end)]) for _, start, end in segments]
    assert durations == [0.5, 0.5] and sum(durations) == 1


def test_segments_honor_configured_dst_zone(monkeypatch):
    from zoneinfo import ZoneInfo

    from app.utils import datetime as dates

    monkeypatch.setattr(dates, "_business_zone", lambda: ZoneInfo("America/New_York"))
    login = datetime(2026, 3, 8, 5, tzinfo=UTC)
    end = datetime(2026, 3, 9, 4, tzinfo=UTC)
    segments = list(day_segments(login, end))
    assert len(segments) == 1 and segments[0][0] == date(2026, 3, 8)
    assert attendance.union_seconds([(segments[0][1], segments[0][2])]) == 23 * 3600


async def test_reconciliation_does_not_choose_or_delete_duplicate_summaries(mock_db):
    user_id, _ = await employee(mock_db)
    await session(mock_db, user_id, BOUNDARY - timedelta(minutes=30), BOUNDARY)
    await mock_db.attendance_days.insert_one(
        {"user_id": user_id, "date": "2026-10-26", "legacy_note": "retain"}
    )
    before = await mock_db.attendance_days.find({}).to_list(10)
    report = await reconciliation.reconcile_attendance(mock_db, now=NOW, apply=True)
    assert report["status"] == "BLOCKED"
    assert any(
        issue["kind"] == "duplicate_employee_date_summary" for issue in report["issues"]
    )
    assert await mock_db.attendance_days.find({}).to_list(10) == before


@pytest.mark.parametrize("month", ["2026-13", "2026-2", "0000-01", "9999-12"])
async def test_month_api_rejects_invalid_dates(client, owner_headers, month):
    response = await client.get(
        f"/api/v1/daily-operations/sessions?month={month}", headers=owner_headers
    )
    assert response.status_code == 422


async def test_reconciliation_reports_duplicate_session_events_without_rewriting(
    mock_db,
):
    user_id, _ = await employee(mock_db)
    family = await session(mock_db, user_id, BOUNDARY - timedelta(minutes=30), BOUNDARY)
    original = await mock_db.sessions.find_one({"family_id": family})
    await mock_db.sessions.insert_one({**original, "_id": ObjectId()})
    report = await reconciliation.reconcile_attendance(mock_db, now=NOW, apply=True)
    assert report["status"] == "BLOCKED" and report["duplicate_token_events"] == 1
    assert report["before"] == report["after"]
    assert original["token_id"] not in str(report["issues"])


async def test_concurrent_timeout_creates_only_one_terminal_event(mock_db, monkeypatch):
    from app.features.auth import session_lifecycle

    monkeypatch.setattr(
        session_lifecycle, "utc_now", lambda: BOUNDARY + timedelta(minutes=6)
    )
    user_id, _ = await employee(mock_db)
    family = await session(
        mock_db,
        user_id,
        BOUNDARY - timedelta(minutes=30),
        activity=BOUNDARY - timedelta(minutes=5),
    )
    counts = await asyncio.gather(expire_sessions(mock_db), expire_sessions(mock_db))
    assert sum(counts) == 1
    stored = await mock_db.sessions.find_one({"family_id": family})
    assert len(stored["lifecycle_history"]) == 1
    assert await mock_db.attendance_days.count_documents({"user_id": user_id}) == 2


async def test_zero_elapsed_login_at_midnight_has_its_own_date(mock_db, monkeypatch):
    monkeypatch.setattr(attendance, "utc_now", lambda: BOUNDARY)
    user_id, _ = await employee(mock_db)
    await session(mock_db, user_id, BOUNDARY, BOUNDARY)
    result = await attendance.daily_sessions(
        DailyOperationsService(mock_db), owner(), month="2026-10"
    )
    assert result["total"] == 1
    assert result["items"][0]["login_at"] == BOUNDARY
    assert result["items"][0]["date"] == "2026-10-27"
    assert result["items"][0]["recorded_seconds"] == 0


async def test_reconciliation_creation_timestamp_is_actual_write_time(
    mock_db, monkeypatch
):
    from app.features.auth import session_lifecycle

    monkeypatch.setattr(session_lifecycle, "utc_now", lambda: NOW)
    user_id, _ = await employee(mock_db)
    await ensure_summary(mock_db, user_id, BOUNDARY - timedelta(days=1))
    summary = await mock_db.attendance_days.find_one({"user_id": user_id})
    assert summary["created_at"] == NOW
    assert summary["date"] == "2026-10-26"


async def test_reconciliation_fills_only_missing_correction_binding_and_audits_once(
    mock_db,
):
    user_id, _ = await employee(mock_db)
    family = await session(mock_db, user_id, BOUNDARY - timedelta(minutes=30), BOUNDARY)
    original = {
        "_id": family,
        "login_at": BOUNDARY + timedelta(minutes=10),
        "logout_at": BOUNDARY + timedelta(minutes=20),
        "version": 1,
        "reason": "Verified legacy correction",
        "history": [{"reason": "keep"}],
    }
    await mock_db.session_corrections.insert_one(original.copy())
    report = await reconciliation.reconcile_attendance(mock_db, now=NOW, apply=True)
    assert report["status"] == "PASS" and report["correction_bindings_created"] == 1
    stored = await mock_db.session_corrections.find_one({"_id": family})
    assert stored["user_id"] == user_id and len(stored["reconciliation_history"]) == 1
    assert {key: stored[key] for key in original} == original
    again = await reconciliation.reconcile_attendance(mock_db, now=NOW, apply=True)
    assert again["correction_bindings_created"] == 0
    assert (
        len(
            (await mock_db.session_corrections.find_one({"_id": family}))[
                "reconciliation_history"
            ]
        )
        == 1
    )


async def test_reconciliation_preserves_hidden_session_visibility(mock_db):
    user_id, _ = await employee(mock_db)
    family = await session(mock_db, user_id, BOUNDARY - timedelta(minutes=30), BOUNDARY)
    await mock_db.daily_session_visibility.insert_one(
        {"_id": family, "is_deleted": True}
    )
    report = await reconciliation.reconcile_attendance(mock_db, now=NOW, apply=True)
    assert report["status"] == "PASS" and report["expected_source_days"] == 0
    assert report["planned_inserts"] == 0 and report["unattributed_summaries"] == 1
    assert await mock_db.sessions.count_documents({"family_id": family}) == 1
