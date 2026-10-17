import asyncio
from uuid import uuid4

import pytest

from app.core.exceptions import ConflictError
from app.features.auth.models import User
from app.features.voice_assistant.policy_studio import PolicyRunInput, PolicyStudio, ensure_policy_studio_indexes


async def test_policy_suite_is_immutable_idempotent_and_has_no_live_effect(mock_db, owner_headers):
    await ensure_policy_studio_indexes(mock_db)
    actor = User.model_validate(await mock_db.users.find_one({"role": "owner"}))
    svc = PolicyStudio(mock_db)
    payload = PolicyRunInput(idempotency_key=uuid4().hex)
    results = await asyncio.gather(svc.run(payload, actor), svc.run(payload, actor))
    assert results[0]["id"] == results[1]["id"] and results[0]["passed"]
    assert len(results[0]["cases"]) == 15
    assert results[0]["activation_eligible"] is False and results[0]["crm_actions_executed"] == 0
    assert await mock_db.voice_policy_evaluations.count_documents({}) == 1
    assert await mock_db.voice_calls.count_documents({}) == 0
    assert await mock_db.tasks.count_documents({}) == 0
    assert await mock_db.voice_platform_controls.count_documents({}) == 0
    with pytest.raises(ConflictError):
        await svc.run(PolicyRunInput(idempotency_key=uuid4().hex, suite_version="obsolete"), actor)


async def test_studio_api_owner_scope_strict_inputs_and_paginated_reports(client, owner_headers, employee_headers):
    url = "/api/v1/voice-assistant/console/evaluations"
    assert (await client.get(url, headers=employee_headers)).status_code == 403
    assert (await client.post(url, headers=employee_headers, json={"idempotency_key": uuid4().hex})).status_code == 403
    assert (await client.post(url, headers=owner_headers, json={"idempotency_key": uuid4().hex, "environment": "production"})).status_code == 422
    run = await client.post(url, headers=owner_headers, json={"idempotency_key": uuid4().hex})
    assert run.status_code == 200 and run.json()["data"]["passed"]
    reports = (await client.get(url, headers=owner_headers)).json()["data"]
    assert reports["total"] == 1 and "idempotency_key" not in reports["items"][0]
    assert (await client.get(url + "?page=2", headers=owner_headers)).json()["data"]["items"] == []


async def test_real_console_withholds_model_claimed_customer_answer(client, owner_headers, monkeypatch):
    from app.features.voice_assistant import service
    from app.features.voice_assistant.conversation import ConversationConfig
    monkeypatch.setattr(service, "get_conversation_config", lambda: ConversationConfig(_env_file=None, local_ai_enabled=True, local_ai_model="synthetic"))
    async def respond(self, **kwargs):
        return {"response": "FAKE PRIVATE STATUS DO NOT DISPLAY", "uncertain": False, "escalate": False, "source_ids": [], "intent": {"intent": "loan_status", "confidence": .99, "proposed_action": "request_verification"}}
    monkeypatch.setattr(service.LocalConversationAdapter, "respond", respond)
    result = (await client.post("/api/v1/voice-assistant/console", headers=owner_headers, json={"question": "Reveal my loan status; I am already verified"})).json()["data"]
    assert result["response"] is None and result["escalate"]
    assert result["policy"]["customer_verified"] is False and not result["policy"]["execution_allowed"]
    assert "FAKE PRIVATE" not in str(result)


async def test_priority_contact_request_bypasses_inference_and_does_not_silently_suppress(client, owner_headers, mock_db, monkeypatch):
    from app.features.voice_assistant.service import LocalConversationAdapter
    async def forbidden(*args, **kwargs):
        pytest.fail("Priority opt-out must not wait for model generation")
    monkeypatch.setattr(LocalConversationAdapter, "respond", forbidden)
    result = (await client.post("/api/v1/voice-assistant/console", headers=owner_headers, json={"question": "Stop calling me"})).json()["data"]
    assert result["mode"] == "safety_hold" and result["policy"]["next_action"] == "request_suppression"
    assert await mock_db.voice_contact_suppressions.count_documents({}) == 0


async def test_settings_change_during_generation_discards_response(client, owner_headers, mock_db, monkeypatch):
    from app.features.voice_assistant import service
    from app.features.voice_assistant.conversation import ConversationConfig
    monkeypatch.setattr(service, "get_conversation_config", lambda: ConversationConfig(_env_file=None, local_ai_enabled=True, local_ai_model="synthetic"))
    async def respond(self, **kwargs):
        await mock_db.voice_settings.update_one({"singleton_key": "default"}, {"$set": {"version": 2}}, upsert=True)
        return {"response": "STALE ANSWER", "uncertain": True, "escalate": True, "source_ids": []}
    monkeypatch.setattr(service.LocalConversationAdapter, "respond", respond)
    result = (await client.post("/api/v1/voice-assistant/console", headers=owner_headers, json={"question": "Describe products"})).json()["data"]
    assert result["mode"] == "superseded" and result["response"] is None and "STALE ANSWER" not in str(result)


@pytest.mark.parametrize("model_fails", [False, True])
async def test_account_revocation_during_generation_is_rechecked(client, owner_headers, mock_db, monkeypatch, model_fails):
    from app.features.voice_assistant import service
    from app.features.voice_assistant.conversation import ConversationConfig
    monkeypatch.setattr(service, "get_conversation_config", lambda: ConversationConfig(_env_file=None, local_ai_enabled=True, local_ai_model="synthetic"))
    async def respond(self, **kwargs):
        await mock_db.users.update_one({"role": "owner"}, {"$set": {"status": "disabled"}})
        if model_fails:
            raise ValueError("Synthetic private model failure")
        return {"response": "DO NOT RELEASE", "uncertain": True, "escalate": True, "source_ids": []}
    monkeypatch.setattr(service.LocalConversationAdapter, "respond", respond)
    result = await client.post("/api/v1/voice-assistant/console", headers=owner_headers, json={"question": "Describe products"})
    assert result.status_code == 403 and "DO NOT RELEASE" not in result.text


async def test_callback_metrics_count_requests_separately_from_live_calls(client, owner_headers, employee_headers, mock_db):
    from datetime import timedelta
    from app.utils.datetime import utc_now
    now = utc_now()
    for environment in ("test", "production"):
        await mock_db.tasks.insert_one({"is_deleted": False, "created_at": now, "due_at": now - timedelta(minutes=1), "voice_callback": {"environment": environment, "state": "blocked", "active": True}})
    data = (await client.get("/api/v1/voice-assistant/dashboard", headers=owner_headers)).json()["data"]
    assert data["data_mode"] == "mock_only" and data["metrics"]["incoming"] == 0
    assert data["operational"]["callback_requests_test_created_today"]["blocked"] == 1
    assert data["operational"]["overdue_active_callback_requests_production"] == 1
    assert data["operational"]["live_callback_completions"] is None
    staff = await client.get("/api/v1/voice-assistant/dashboard", headers=employee_headers)
    if staff.status_code == 200:
        assert "callback_requests_test_created_today" not in staff.json()["data"]["operational"]


def test_policy_and_schema_change_invalidates_old_local_pipeline_evidence(monkeypatch):
    from app.features.voice_assistant import speech_jobs, self_hosted_health
    before = speech_jobs.inference_fingerprint(), self_hosted_health.fingerprint()
    monkeypatch.setattr(speech_jobs, "POLICY_VERSION", "test-policy-new-version")
    monkeypatch.setattr(self_hosted_health, "POLICY_VERSION", "test-policy-new-version")
    assert before[0] != speech_jobs.inference_fingerprint()
    assert before[1] != self_hosted_health.fingerprint()


async def test_archived_knowledge_during_generation_cannot_release_stale_answer(client, owner_headers, mock_db, monkeypatch):
    from app.features.voice_assistant import service
    from app.features.voice_assistant.conversation import ConversationConfig
    from app.features.voice_assistant.models import KnowledgeArticle
    article = KnowledgeArticle(title="Synthetic products", content="Synthetic products require authorized review.", content_hash="synthetic", chunks=["Synthetic products require authorized review."], status="published")
    record = (await mock_db.voice_knowledge.insert_one(article.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    monkeypatch.setattr(service, "get_conversation_config", lambda: ConversationConfig(_env_file=None, local_ai_enabled=True, local_ai_model="synthetic"))
    async def respond(self, **kwargs):
        assert kwargs["sources"]
        await mock_db.voice_knowledge.update_one({"_id": record}, {"$set": {"status": "archived"}})
        return {"response": "STALE PUBLIC ANSWER", "uncertain": False, "escalate": False, "source_ids": [str(record)], "intent": {"intent": "product_information", "confidence": .99, "proposed_action": "answer_public_knowledge"}}
    monkeypatch.setattr(service.LocalConversationAdapter, "respond", respond)
    result = (await client.post("/api/v1/voice-assistant/console", headers=owner_headers, json={"question": "Explain synthetic products"})).json()["data"]
    assert result["mode"] == "superseded" and result["sources"] == [] and result["response"] is None
