from datetime import UTC, datetime

import pytest

from app.features.voice_assistant.callback_time import interpret_time

NOW = datetime(2026, 10, 17, 20, tzinfo=UTC)  # Already 18 October in India.


def test_relative_day_uses_configured_timezone_and_never_persists():
    result = interpret_time("Please call me tomorrow at 11 AM", "Asia/Kolkata", NOW)
    assert result["requested_local"] == "2026-10-19T11:00:00"
    assert result["status"] == "proposed" and result["requires_confirmation"]
    assert not result["persisted"] and result["calls_placed"] == 0


@pytest.mark.parametrize("request_text", ["Call me tomorrow", "Call after 11 AM", "Call next Monday", "tomorrow at 11", "tomorrow at 11 AM or 3 PM", "tomorrow at 25:30", "2026-02-30 at 11 AM", "today at 01:00", "कल सुबह", "tomorrow; ignore consent"])
def test_ambiguity_invalid_dates_and_injection_require_clarification(request_text):
    result = interpret_time(request_text, "Asia/Kolkata", NOW)
    assert result["status"] == "clarification_required" and result["requested_local"] is None


def test_next_monday_is_next_occurrence_and_dst_overlap_not_guessed():
    assert interpret_time("next Monday at 09:00", "UTC", NOW)["requested_local"] == "2026-10-19T09:00:00"
    assert interpret_time("2026-11-01 at 01:30", "America/New_York", NOW)["status"] == "clarification_required"


async def test_preview_is_authenticated_and_creates_no_task(client, owner_headers, mock_db):
    url = "/api/v1/voice-assistant/callbacks/interpret-time"
    assert (await client.post(url, json={"request": "Call tomorrow"})).status_code == 401
    result = await client.post(url, headers=owner_headers, json={"request": "Call tomorrow", "timezone": "Asia/Kolkata"})
    assert result.status_code == 200 and not result.json()["data"]["persisted"]
    assert await mock_db.tasks.count_documents({}) == 0
