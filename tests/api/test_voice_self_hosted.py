import json
from datetime import timedelta

import httpx
import pytest

from app.features.auth.models import User
from app.features.voice_assistant import conversation, self_hosted_health
from app.features.voice_assistant.conversation import ConversationConfig, LocalConversationAdapter
from app.features.voice_assistant.self_hosted_health import SelfHostedHealthService, ensure_ai_health_indexes
from app.utils.datetime import utc_now


@pytest.fixture
async def health_context(mock_db, owner_headers, monkeypatch):
    await ensure_ai_health_indexes(mock_db)
    config = ConversationConfig(local_ai_enabled=True, local_ai_model="test-only-local-model")
    monkeypatch.setattr(self_hosted_health, "get_conversation_config", lambda: config)
    actor = User.model_validate(await mock_db.users.find_one({"role": "owner"}))
    return SelfHostedHealthService(mock_db), actor, config


def model_http(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(conversation.httpx, "AsyncClient", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))


def answer_response():
    return httpx.Response(200, json={"message": {"content": json.dumps({"response": "Readiness check acknowledged.", "uncertain": True, "escalate": True, "source_ids": []})}})


def test_private_inference_requires_explicit_server_allowlist():
    with pytest.raises(ValueError):
        ConversationConfig(local_ai_url="https://inference.example.internal")
    config = ConversationConfig(local_ai_url="https://inference.example.internal/", local_ai_allowed_origins=["https://inference.example.internal"])
    assert config.local_ai_url == "https://inference.example.internal"
    with pytest.raises(ValueError):
        ConversationConfig(local_ai_url="http://inference.example.internal", local_ai_allowed_origins=["http://inference.example.internal"])


async def test_functional_request_evidence_is_not_speech_readiness(health_context, monkeypatch, mock_db):
    svc, actor, _ = health_context
    bodies = []
    def handler(request):
        assert request.method == "POST" and request.url.path == "/api/chat"
        bodies.append(json.loads(request.content))
        return answer_response()
    model_http(monkeypatch, handler)
    assert (await svc.status(actor))["text_inference"] == "unverified_or_unavailable"
    result = await svc.test(actor)
    assert result["text_inference"] == "functional_request_passed"
    assert result["live_calling"] is False and result["language_quality_verified"] is False
    assert result["speech_to_text"] == "not_installed"
    assert bodies[0]["model"] == "test-only-local-model" and bodies[0]["stream"] is False
    assert "tools" not in bodies[0]
    assert "Readiness check acknowledged" not in str(await mock_db.voice_ai_health.find({}).to_list(None))


async def test_unavailable_inference_is_honestly_degraded(health_context, monkeypatch):
    svc, actor, _ = health_context
    model_http(monkeypatch, lambda request: httpx.Response(503, text="private-error-do-not-echo"))
    status = await svc.test(actor)
    assert status["text_inference"] == "unverified_or_unavailable"
    assert status["last_test"]["status"] == "functional_request_failed"
    assert "private-error" not in str(status)


async def test_disabled_model_never_issues_requests(health_context, monkeypatch, mock_db):
    svc, actor, _ = health_context
    monkeypatch.setattr(self_hosted_health, "get_conversation_config", lambda: ConversationConfig())
    def forbidden(request):
        pytest.fail("Disabled models must not receive HTTP requests")
    model_http(monkeypatch, forbidden)
    result = await svc.test(actor)
    assert result["text_inference"] == "disabled"
    assert await mock_db.voice_ai_health.count_documents({}) == 0


async def test_health_evidence_expires_and_is_bound_to_model(health_context, monkeypatch, mock_db):
    svc, actor, _ = health_context
    model_http(monkeypatch, lambda request: answer_response())
    assert (await svc.test(actor))["evidence_fresh"] is True
    await mock_db.voice_ai_health.update_one({}, {"$set": {"checked_at": utc_now() - timedelta(minutes=16)}})
    assert (await svc.status(actor))["text_inference"] == "unverified_or_unavailable"
    monkeypatch.setattr(self_hosted_health, "get_conversation_config", lambda: ConversationConfig(local_ai_enabled=True, local_ai_model="different-model"))
    assert (await svc.status(actor))["last_test"] is None


@pytest.mark.parametrize("response", [httpx.Response(200, content=b"x" * 65537, headers={"content-type": "application/json"}), httpx.Response(200, text="not-json", headers={"content-type": "application/json"}), httpx.Response(200, text="<html>error</html>", headers={"content-type": "text/html"})])
async def test_inference_response_bounds_and_content_type(health_context, monkeypatch, response):
    svc, actor, _ = health_context
    model_http(monkeypatch, lambda request: response)
    assert (await svc.test(actor))["last_test"]["status"] == "functional_request_failed"


async def test_self_hosted_routes_owner_only(client, owner_headers, employee_headers, health_context):
    assert (await client.get("/api/v1/voice-assistant/self-hosted/status", headers=employee_headers)).status_code == 403
    result = await client.get("/api/v1/voice-assistant/self-hosted/status", headers=owner_headers)
    assert result.status_code == 200 and result.json()["data"]["live_calling"] is False
