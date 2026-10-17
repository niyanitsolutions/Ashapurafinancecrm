"""Known fixture aggregation, independent of provider delivery and synthetic counts."""

from datetime import UTC, datetime, timedelta

from app.features.auth.models import User
from app.features.voice_assistant import service


async def test_mock_metrics_exclude_other_sources_and_define_denominators(mock_db, owner_headers, monkeypatch):
    now = datetime(2026, 10, 17, 12, tzinfo=UTC)
    monkeypatch.setattr(service, "utc_now", lambda: now)
    actor = User.model_validate(await mock_db.users.find_one({"role": "owner"}))
    common = {"is_deleted": False, "provider": "mock", "created_at": now, "direction": "incoming", "status": "completed", "owner_user_id": actor.require_id(), "duration_seconds": 0, "timeline": [], "version": 1}
    await mock_db.voice_calls.insert_many([
        common | {"duration_seconds": 60, "answered_at": now - timedelta(minutes=1), "timeline": [{"state": "ai_active"}, {"state": "human_active"}]},
        common | {"status": "missed"},
        common | {"provider": "imported", "duration_seconds": 900},
        common | {"provider": "synthetic", "duration_seconds": 900},
        common | {"created_at": now + timedelta(days=1), "duration_seconds": 900},
        common | {"created_at": now - timedelta(days=1), "status": "ringing"},
    ])
    result = await service.VoiceService(mock_db).dashboard(actor)
    metrics = result["metrics"]
    assert metrics["incoming"] == 2 and metrics["answered"] == 1 and metrics["missed"] == 1
    assert metrics["total_seconds"] == 60 and metrics["average_seconds"] == 30
    assert metrics["average_answered_seconds"] == 60 and metrics["active"] == 1
    assert metrics["ai_handled"] == metrics["human_handled"] == 1
    assert result["metric_provenance"]["average_seconds_denominator"] == 2
    assert result["metric_provenance"]["as_of"] == now
    assert result["operational"]["live_callback_completions"] is None
    assert result["data_mode"] == "mock_only" and result["estimated_cost"] is None
    assert len(result["recent"]) == 3
    assert all(row["provider"] == "mock" and row["created_at"] <= now for row in result["recent"])
