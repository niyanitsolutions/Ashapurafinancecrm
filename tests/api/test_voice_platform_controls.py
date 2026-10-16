"""Local control-plane tests; no real PBX, model, speech process or calls."""

import asyncio
from datetime import timedelta

import pytest

from app.core.exceptions import ConflictError, ForbiddenError
from app.features.auth.models import User
from app.features.voice_assistant.platform_schemas import ActivationChange, ComponentChange
from app.features.voice_assistant.platform_service import PlatformService, ensure_platform_indexes
from app.utils.datetime import utc_now


@pytest.fixture
async def controls(mock_db, owner_headers):
    await ensure_platform_indexes(mock_db)
    actor = User.model_validate(await mock_db.users.find_one({"role": "owner"}))
    return PlatformService(mock_db), actor


async def test_platform_defaults_and_environment_separation(controls):
    svc, actor = controls
    state = await svc.status("test", actor)
    assert state["emergency_stopped"] and not state["inbound"] and not state["production_eligible"]
    changed = await svc.component("test", "workers", ComponentChange(version=1, enabled=True, reason="Local testing only"), actor)
    assert changed["version"] == 2 and changed["components"]["workers"]["enabled"]
    production = await svc.status("production", actor)
    assert production["version"] == 1 and not production["components"]["workers"]["enabled"]
    assert state["evidence_token"] != production["evidence_token"]


async def test_platform_optimistic_race_only_one_change_wins(controls):
    svc, actor = controls
    await svc.status("test", actor)
    payload = ComponentChange(version=1, enabled=True, reason="Race condition test")
    outcomes = await asyncio.gather(svc.component("test", "workers", payload, actor), svc.component("test", "inference", payload, actor), return_exceptions=True)
    assert sum(isinstance(value, ConflictError) for value in outcomes) == 1


async def test_emergency_wins_without_ui_version_and_preserves_profiles(controls, mock_db):
    svc, actor = controls
    await svc.record("test")
    await mock_db.voice_platform_controls.update_one({"environment": "test"}, {"$set": {"inbound": True, "outbound": True, "processing": True, "components.stt.profile_id": "preserve-profile"}})
    result = await svc.emergency("test", actor, "Emergency stop test")
    assert not any(result[key] for key in ("inbound", "outbound", "processing"))
    assert result["emergency_stopped"] and result["components"]["stt"]["profile_id"] == "preserve-profile"
    assert result["history"][-1]["actor_id"] == actor.require_id()
    with pytest.raises(ConflictError):
        await svc.component("test", "media", ComponentChange(version=1, enabled=True, reason="Old browser state"), actor)


@pytest.mark.parametrize("direction", ["inbound", "outbound", "processing"])
async def test_activation_never_accepts_forged_or_mock_health(controls, mock_db, direction):
    svc, actor = controls
    state = await svc.status("production", actor)
    await mock_db.voice_platform_controls.update_one({"environment": "production"}, {"$set": {"production_eligible": True, "live_implementation_available": True}})
    with pytest.raises(ForbiddenError):
        await svc.activation("production", ActivationChange(version=state["version"], direction=direction, enabled=True, confirmation="ENABLE LIVE CALLING", evidence_token=state["evidence_token"], reason="Explicit activation test"), actor)
    with pytest.raises(ForbiddenError):
        await svc.require_live("production", direction)
    assert not (await svc.status("production", actor))[direction]


async def test_worker_evidence_expires_but_never_proves_media(controls, mock_db):
    svc, actor = controls
    await mock_db.voice_worker_health.insert_one({"singleton_key": "default", "heartbeat_at": utc_now()})
    gates = {item["key"]: item["passed"] for item in (await svc.status("test", actor))["gates"]}
    assert gates["worker_heartbeat"] and not gates["native_control_media"]
    await mock_db.voice_worker_health.update_one({}, {"$set": {"heartbeat_at": utc_now() - timedelta(minutes=1)}})
    assert not next(item["passed"] for item in (await svc.status("test", actor))["gates"] if item["key"] == "worker_heartbeat")


async def test_controls_http_permissions_validation_and_disable(client, owner_headers, employee_headers):
    base = "/api/v1/voice-assistant/platform"
    assert (await client.get(f"{base}/test", headers=employee_headers)).status_code == 403
    assert (await client.post(f"{base}/test/emergency", headers=employee_headers, json={"reason": "Forbidden owner action"})).status_code == 403
    assert (await client.get(f"{base}/other", headers=owner_headers)).status_code == 422
    state = (await client.get(f"{base}/test", headers=owner_headers)).json()["data"]
    assert (await client.post(f"{base}/test/activation", headers=owner_headers, json={"version": state["version"], "direction": "inbound", "enabled": False, "reason": "Explicit disable test"})).status_code == 200
    assert (await client.put(f"{base}/test/components/unknown", headers=owner_headers, json={"version": 2, "enabled": True, "reason": "Invalid component name"})).status_code == 422


async def test_component_configuration_invalidates_all_live_flags(controls, mock_db):
    svc, actor = controls
    await svc.record("test")
    await mock_db.voice_platform_controls.update_one({"environment": "test"}, {"$set": {"inbound": True, "outbound": True, "processing": True}})
    state = await svc.component("test", "media", ComponentChange(version=1, enabled=False, reason="Disable for maintenance"), actor)
    assert not any(state[key] for key in ("inbound", "outbound", "processing"))
    assert state["history"][-1]["event"] == "component.media.disabled"


async def test_unimplemented_runtime_cannot_be_enabled(controls):
    svc, actor = controls
    with pytest.raises(ForbiddenError):
        await svc.component("test", "media", ComponentChange(version=1, enabled=True, reason="Unavailable media test"), actor)


async def test_central_disable_prevents_existing_text_tests(controls, monkeypatch):
    from app.features.voice_assistant.self_hosted_health import SelfHostedHealthService
    svc, actor = controls
    await svc.status("test", actor)
    with pytest.raises(ForbiddenError, match="disabled"):
        await SelfHostedHealthService(svc.db).test(actor)


async def test_disabling_inference_preserves_lexical_knowledge_lookup(controls, monkeypatch):
    from app.features.voice_assistant import service
    from app.features.voice_assistant.conversation import ConversationConfig
    from app.features.voice_assistant.schemas import ConsoleInput
    svc, actor = controls
    await svc.status("test", actor)
    monkeypatch.setattr(service, "get_conversation_config", lambda: ConversationConfig(_env_file=None))
    result = await service.VoiceService(svc.db).console(ConsoleInput(question="Synthetic knowledge test", language="en", history=[]), actor)
    assert result["mode"] == "retrieval_only" and result["response"] is None


async def test_append_only_audit_retains_control_and_emergency_events(controls):
    svc, actor = controls
    await svc.record("test")
    await svc.component("test", "workers", ComponentChange(version=1, enabled=True, reason="Local audit verification"), actor)
    await svc.emergency("test", actor, "Emergency audit verification")
    events = await svc.db.audit_logs.find({"event_type": {"$in": ["voice_assistant.platform_control_changed", "voice_assistant.platform_emergency_disabled"]}}).to_list(None)
    assert len(events) == 2 and all(event["user_id"] == actor.require_id() for event in events)
