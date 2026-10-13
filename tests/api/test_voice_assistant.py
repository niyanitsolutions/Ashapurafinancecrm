from datetime import timedelta
from uuid import uuid4

import pytest
from bson import ObjectId

from app.features.auth.models import User
from app.features.voice_assistant.catalog import seed_voice_catalog
from app.features.voice_assistant.conversation import ConversationConfig
from app.features.voice_assistant.repository import ensure_voice_indexes
from app.features.voice_assistant.service import VoiceService
from app.utils.datetime import utc_now

BASE = "/api/v1/voice-assistant"


async def enable(client, headers, **updates):
    result = await client.get(f"{BASE}/settings", headers=headers)
    cfg = result.json()["data"]
    cfg.update({"mode": "mock", **updates})
    result = await client.put(f"{BASE}/settings", headers=headers, json=cfg)
    assert result.status_code == 200, result.text
    return result.json()["data"]


async def create(client, headers, **updates):
    return await client.post(
        f"{BASE}/mock/calls",
        headers=headers,
        json={
            "direction": "incoming",
            "contact_label": "Test caller",
            "idempotency_key": uuid4().hex,
            **updates,
        },
    )


async def action(client, headers, call, name):
    return await client.post(
        f"{BASE}/mock/calls/{call['id']}/actions",
        headers=headers,
        json={"action": name, "version": call["version"]},
    )


async def test_default_disabled_and_live_gates(client, owner_headers):
    assert (await create(client, owner_headers)).status_code == 403
    for feature in ("inbound", "outbound", "recording", "cloning"):
        assert (
            await client.post(f"{BASE}/live/{feature}", headers=owner_headers)
        ).status_code == 403
    cfg = (await client.get(f"{BASE}/settings", headers=owner_headers)).json()["data"]
    assert cfg["ring_seconds"] == 10
    cfg["mode"] = "live"
    assert (
        await client.put(f"{BASE}/settings", headers=owner_headers, json=cfg)
    ).status_code == 422
    provider = (await client.get(f"{BASE}/providers", headers=owner_headers)).json()["data"]
    assert provider["validated_languages"] == []
    assert provider["live_outbound"] is False


async def test_permissions_and_unknown_fields(client, employee_headers, owner_headers):
    for route in ("dashboard", "settings", "calls", "knowledge", "providers"):
        assert (await client.get(f"{BASE}/{route}", headers=employee_headers)).status_code == 403
        assert (await client.get(f"{BASE}/{route}")).status_code in (401, 403)
    cfg = (await client.get(f"{BASE}/settings", headers=owner_headers)).json()["data"]
    cfg["outbound_enabled"] = True
    assert (
        await client.put(f"{BASE}/settings", headers=owner_headers, json=cfg)
    ).status_code == 422


async def test_settings_version_and_invalid_windows(client, owner_headers, mock_db):
    await ensure_voice_indexes(mock_db)
    original = (await client.get(f"{BASE}/settings", headers=owner_headers)).json()["data"]
    await enable(client, owner_headers)
    assert (
        await client.put(f"{BASE}/settings", headers=owner_headers, json=original)
    ).status_code == 409
    cfg = (await client.get(f"{BASE}/settings", headers=owner_headers)).json()["data"]
    for changes in (
        {"timezone": "Mars/Test"},
        {"calling_start": "22:00", "calling_end": "08:00"},
        {"ring_seconds": 0},
    ):
        assert (
            await client.put(f"{BASE}/settings", headers=owner_headers, json={**cfg, **changes})
        ).status_code == 422


async def test_idempotency_and_transfer_confirmation(client, owner_headers, mock_db):
    await ensure_voice_indexes(mock_db)
    await enable(client, owner_headers)
    key = uuid4().hex
    call = (await create(client, owner_headers, idempotency_key=key)).json()["data"]
    duplicate = (await create(client, owner_headers, idempotency_key=key)).json()["data"]
    assert duplicate["id"] == call["id"]
    assert await mock_db.voice_calls.count_documents({}) == 1
    assert (
        await create(client, owner_headers, idempotency_key=key, direction="outgoing")
    ).status_code == 409
    assert (await action(client, owner_headers, call, "transfer")).status_code == 409
    active = (await action(client, owner_headers, call, "reject")).json()["data"]
    assert active["status"] == "ai_active"
    assert (await action(client, owner_headers, call, "answer")).status_code == 409
    transfer = (await action(client, owner_headers, active, "transfer")).json()["data"]
    assert transfer["status"] == "transferring" and transfer["transfer_outcome"] == "pending"
    human = (await action(client, owner_headers, transfer, "transfer_confirmed")).json()["data"]
    assert human["status"] == "human_active" and human["transfer_outcome"] == "confirmed"
    ended = (await action(client, owner_headers, human, "end")).json()["data"]
    assert ended["status"] == "completed" and ended["recording_status"] == "disabled"
    assert (await action(client, owner_headers, ended, "answer")).status_code == 409
    dashboard = (await client.get(f"{BASE}/dashboard", headers=owner_headers)).json()["data"]
    assert dashboard["metrics"]["successful_transfers"] == 1
    assert dashboard["estimated_cost"] is None


async def test_limits_and_consent(client, owner_headers, mock_db):
    await ensure_voice_indexes(mock_db)
    await enable(client, owner_headers, max_concurrent_calls=1)
    assert (await create(client, owner_headers, direction="outgoing")).status_code == 403
    assert (await create(client, owner_headers)).status_code == 200
    assert (await create(client, owner_headers)).status_code == 409


async def test_worker_recovery_deadline_and_no_duplicate(client, owner_headers, mock_db):
    await ensure_voice_indexes(mock_db)
    await enable(client, owner_headers)
    call = (await create(client, owner_headers)).json()["data"]
    await mock_db.voice_calls.update_one(
        {"_id": ObjectId(call["id"])},
        {
            "$set": {
                "deadline_at": utc_now() - timedelta(seconds=5),
            }
        },
    )
    assert await VoiceService(mock_db).sweep() == 1
    assert await VoiceService(mock_db).sweep() == 0
    active = await mock_db.voice_calls.find_one({"_id": ObjectId(call["id"])})
    assert active["status"] == "ai_active"
    await mock_db.voice_calls.update_one(
        {"_id": active["_id"]},
        {
            "$set": {
                "deadline_at": utc_now() - timedelta(seconds=1),
                "answered_at": utc_now() - timedelta(seconds=400),
            }
        },
    )
    assert await VoiceService(mock_db).sweep() == 1
    ended = await mock_db.voice_calls.find_one({"_id": active["_id"]})
    assert ended["status"] == "completed"
    assert await mock_db.voice_calls.count_documents({}) == 1


async def test_record_scope(mock_db):
    from app.core.exceptions import ForbiddenError
    from app.features.voice_assistant.models import CallSession

    actor = User(_id=str(ObjectId()), mobile="9000000022", role="employee")
    other = User(_id=str(ObjectId()), mobile="9000000023", role="employee")
    call = CallSession(
        direction="incoming",
        contact_label="Private",
        idempotency_key=uuid4().hex,
        owner_user_id=other.require_id(),
        deadline_at=utc_now(),
    )
    result = await mock_db.voice_calls.insert_one(call.model_dump(by_alias=True, exclude={"id"}))
    service = VoiceService(mock_db)
    assert (await service.list_calls(actor))["total"] == 0
    with pytest.raises(ForbiddenError):
        await service.call(str(result.inserted_id), actor)


async def test_knowledge_review_retrieval_expiry_and_rollback(client, owner_headers, mock_db):
    data = {
        "title": "Document policy",
        "content": "Personal loan applications require identity documents and proof of income.",
        "language": "en",
    }
    response = await client.post(f"{BASE}/knowledge", headers=owner_headers, json=data)
    assert response.status_code == 200, response.text
    article = response.json()["data"]
    assert (
        await client.post(f"{BASE}/knowledge", headers=owner_headers, json=data)
    ).status_code == 409
    question = {"question": "Which documents for a loan?", "language": "en"}
    assert not (await client.post(f"{BASE}/console", headers=owner_headers, json=question)).json()[
        "data"
    ]["sources"]

    async def advance(article, operation):
        return await client.post(
            f"{BASE}/knowledge/{article['id']}/actions",
            headers=owner_headers,
            json={"action": operation, "version": article["version"]},
        )

    assert (await advance(article, "publish")).status_code == 409
    review = (await advance(article, "review")).json()["data"]
    published = (await advance(review, "publish")).json()["data"]
    answer = (await client.post(f"{BASE}/console", headers=owner_headers, json=question)).json()[
        "data"
    ]
    assert answer["sources"] and answer["response"] is None and answer["mode"] == "retrieval_only"
    edited = (
        await client.put(
            f"{BASE}/knowledge/{article['id']}",
            headers=owner_headers,
            json={
                **data,
                "content": "Loan documents are reviewed by authorized staff before processing.",
                "version": published["version"],
            },
        )
    ).json()["data"]
    assert edited["status"] == "draft"
    restored = await client.post(
        f"{BASE}/knowledge/{article['id']}/actions",
        headers=owner_headers,
        json={
            "action": "rollback",
            "version": edited["version"],
            "target_version": published["version"],
        },
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["data"]["content"] == data["content"]
    await mock_db.voice_knowledge.update_one(
        {"_id": ObjectId(article["id"])},
        {"$set": {"status": "published", "expires_on": "2000-01-01"}},
    )
    assert not (await VoiceService(mock_db).retrieve("loan", "en"))


async def test_local_dynamic_console_with_context(client, owner_headers, monkeypatch):
    from app.features.voice_assistant import service

    captured = {}

    async def respond(self, **kwargs):
        captured.update(kwargs)
        return {
            "response": "Which service would you like help with?",
            "uncertain": True,
            "escalate": False,
            "source_ids": [],
        }

    monkeypatch.setattr(
        service,
        "get_conversation_config",
        lambda: ConversationConfig(
            local_ai_enabled=True,
            local_ai_model="test-model",
        ),
    )
    monkeypatch.setattr(service.LocalConversationAdapter, "respond", respond)
    answer = await client.post(
        f"{BASE}/console",
        headers=owner_headers,
        json={
            "question": "And the process?",
            "history": [{"role": "user", "content": "I need a loan"}],
        },
    )
    assert answer.status_code == 200
    assert answer.json()["data"]["mode"] == "local_dynamic_text"
    assert captured["history"][0]["content"] == "I need a loan"
    assert "instructions" in captured and "operational_rules" in captured


def test_local_model_url_rejects_external_and_credentials():
    for endpoint in (
        "https://external.example",
        "http://127.0.0.1@evil.test",
        "http://localhost/api",
        "http://user:pass@localhost",
    ):
        with pytest.raises(ValueError):
            ConversationConfig(local_ai_url=endpoint)


async def test_catalog_additive_and_no_grants(mock_db):
    await seed_voice_catalog(mock_db)
    await seed_voice_catalog(mock_db)
    assert await mock_db.permissions.count_documents({"module": "voice_assistant"}) == 2
    assert await mock_db.nav_items.count_documents({"key": "voice_assistant"}) == 1
    assert await mock_db.role_permissions.count_documents({}) == 0


async def test_outgoing_windows_and_monthly_reservation(client, owner_headers, mock_db):
    await ensure_voice_indexes(mock_db)
    await enable(
        client,
        owner_headers,
        holidays=[
            utc_now().astimezone(__import__("zoneinfo").ZoneInfo("Asia/Kolkata")).date().isoformat()
        ],
    )
    assert (
        await create(client, owner_headers, direction="outgoing", consent_reference="test-consent")
    ).status_code == 403
    await enable(
        client, owner_headers, holidays=[], monthly_minute_limit=1, max_duration_seconds=120
    )
    assert (await create(client, owner_headers)).status_code == 409


async def test_daily_and_rate_limits(client, owner_headers, mock_db):
    await ensure_voice_indexes(mock_db)
    await enable(client, owner_headers, daily_call_limit=1)
    call = (await create(client, owner_headers)).json()["data"]
    await action(client, owner_headers, call, "end")
    assert (await create(client, owner_headers)).status_code == 409
    await enable(client, owner_headers, daily_call_limit=50, calls_per_minute=1)
    assert (await create(client, owner_headers)).status_code == 409


async def test_local_model_protocol_and_invalid_sources(monkeypatch):
    import json

    import httpx

    from app.features.voice_assistant import conversation
    from app.features.voice_assistant.conversation import LocalConversationAdapter

    original_client = httpx.AsyncClient
    requests = []
    source_id = "approved-source"

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {
                            "response": "Please clarify which service you mean.",
                            "uncertain": True,
                            "escalate": False,
                            "source_ids": [source_id],
                        }
                    )
                }
            },
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        conversation.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )
    adapter = LocalConversationAdapter(
        ConversationConfig(local_ai_enabled=True, local_ai_model="test-model")
    )
    params = {
        "question": "What about my unusual situation?",
        "history": [{"role": "user", "content": "I need document guidance"}],
        "sources": [{"id": "approved-source", "excerpt": "Approved content"}],
        "instructions": "Be concise.",
        "operational_rules": "No financial decisions.",
        "language": "en",
    }
    answer = await adapter.respond(**params)
    assert answer["uncertain"]
    body = requests[0]
    assert body["stream"] is False and body["format"]["type"] == "object"
    assert body["messages"][-1]["content"] == params["question"]
    assert "untrusted" in body["messages"][0]["content"]
    assert any(turn["content"] == "I need document guidance" for turn in body["messages"])
    source_id = "invented-source"
    with pytest.raises(ValueError):
        await adapter.respond(**params)


async def test_console_rate_limit(client, owner_headers):
    for _ in range(10):
        assert (
            await client.post(
                f"{BASE}/console", headers=owner_headers, json={"question": "Help with documents"}
            )
        ).status_code == 200
    assert (
        await client.post(
            f"{BASE}/console", headers=owner_headers, json={"question": "Help with documents"}
        )
    ).status_code == 429


async def test_disable_finalizes_calls_and_transfer_respects_fallback(
    client, owner_headers, mock_db
):
    await ensure_voice_indexes(mock_db)
    await enable(client, owner_headers)
    call = (await create(client, owner_headers)).json()["data"]
    active = (await action(client, owner_headers, call, "reject")).json()["data"]
    transfer = (await action(client, owner_headers, active, "transfer")).json()["data"]
    await enable(client, owner_headers, ai_fallback=False)
    failed = (await action(client, owner_headers, transfer, "transfer_failed")).json()["data"]
    assert failed["status"] == "completed"
    call = (await create(client, owner_headers)).json()["data"]
    await enable(client, owner_headers, mode="disabled")
    assert (await action(client, owner_headers, call, "answer")).status_code == 403
    assert await VoiceService(mock_db).sweep() == 1
    call = (await client.get(f"{BASE}/calls/{call['id']}", headers=owner_headers)).json()["data"]
    assert call["status"] == "missed"


async def test_view_only_http_and_other_call_scope(
    client, owner_headers, employee_headers, mock_db, master_data
):
    from app.features.access_control.models import EmployeeRole, Role, RolePermission
    from app.features.employee.models import Employee

    await ensure_voice_indexes(mock_db)
    await seed_voice_catalog(mock_db)
    user = await mock_db.users.find_one({"mobile": "9000000002"})
    employee = Employee(
        user_id=str(user["_id"]),
        employee_code="VOICE-TEST",
        first_name="Test",
        last_name="Viewer",
        display_name="Test Viewer",
        mobile=user["mobile"],
        email="voice-viewer@example.test",
        joining_date=utc_now(),
        employment_type="full_time",
        **master_data,
    )
    employee_id = (
        await mock_db.employees.insert_one(employee.model_dump(by_alias=True, exclude={"id"}))
    ).inserted_id
    role_id = (
        await mock_db.roles.insert_one(
            Role(name="Voice Viewer").model_dump(by_alias=True, exclude={"id"})
        )
    ).inserted_id
    permission = await mock_db.permissions.find_one(
        {"module": "voice_assistant", "resource": "calls"}
    )
    grant = RolePermission(
        role_id=str(role_id), permission_id=str(permission["_id"]), granted_actions=["view"]
    )
    await mock_db.role_permissions.insert_one(grant.model_dump(by_alias=True, exclude={"id"}))
    link = EmployeeRole(employee_id=str(employee_id), role_id=str(role_id))
    await mock_db.employee_roles.insert_one(link.model_dump(by_alias=True, exclude={"id"}))
    await enable(client, owner_headers)
    call = (await create(client, owner_headers)).json()["data"]
    assert (await client.get(f"{BASE}/calls", headers=employee_headers)).json()["data"][
        "total"
    ] == 0
    assert (
        await client.get(f"{BASE}/calls/{call['id']}", headers=employee_headers)
    ).status_code == 403
    assert (await create(client, employee_headers)).status_code == 403
    assert (await action(client, employee_headers, call, "answer")).status_code == 403
