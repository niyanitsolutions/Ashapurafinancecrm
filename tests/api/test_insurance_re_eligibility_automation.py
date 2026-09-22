"""Exercise the registered Arq cron through its queue/worker, then read the public APIs.

MongoDB and Redis are isolated in-memory test implementations. No local/production
database, network listener, or external notification provider is used.
"""

import asyncio
import signal
from copy import copy
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
from arq.connections import ArqRedis
from arq.worker import Worker
from bson import ObjectId
from redis.asyncio import ConnectionPool
from test_insurance_manual_lead import _create
from test_insurance_policy_leads import _insurance_product_with_schema
from test_reminders import _insert_rejected_case, _insert_rejected_insurance_case
from test_workflow import _seed_workflow_definitions

from app.core.exceptions import ConflictError
from app.features.auth.models import User
from app.features.insurance_management.service import InsuranceCaseService
from app.features.workflow_engine.engine import WorkflowEngine
from app.features.workflow_engine.repository import (
    ApplicationStatusHistoryRepository,
    ApplicationWorkflowRepository,
)
from app.utils.datetime import add_calendar_months
from app.worker.tasks import reminders
from app.worker.worker_settings import WorkerSettings

NOW = datetime(2026, 1, 31, 10, tzinfo=UTC)


async def run_scheduled_worker(monkeypatch, mock_db, now, *, timeout=10):
    """Use the *registered* production cron, not a direct service/job call."""
    monkeypatch.setattr(reminders, "get_database", lambda: mock_db)
    monkeypatch.setattr(reminders, "utc_now", lambda: now)
    # fakeredis doesn't implement INFO. Only that diagnostic is bypassed; Arq's
    # startup cron, enqueue, Redis queue, dispatch, completion and health check are real.
    monkeypatch.setattr("arq.worker.log_redis_info", AsyncMock())
    # Arq close() uses this POSIX signal even when signal handlers are disabled.
    if not hasattr(signal, "SIGUSR1"):
        monkeypatch.setattr(signal, "SIGUSR1", signal.SIGTERM, raising=False)
    registered = next(job for job in WorkerSettings.cron_jobs if job.coroutine is reminders.auto_transition_re_eligible_cases)
    job = copy(registered)
    job.next_run = None
    pool = ConnectionPool(connection_class=fakeredis.FakeAsyncRedisConnection, server=fakeredis.FakeServer())
    redis = ArqRedis(connection_pool=pool)
    worker = Worker(
        functions=[], cron_jobs=[job], redis_pool=redis, burst=True, max_burst_jobs=1,
        poll_delay=0.01, handle_signals=False,
    )
    try:
        await asyncio.wait_for(worker.async_run(), timeout=timeout)
        assert worker.jobs_complete == 1
        assert worker.jobs_failed == 0
        assert await redis.get(worker.health_check_key) is not None
    finally:
        await worker.close()
        await pool.disconnect()


@pytest.mark.parametrize("stage", ["fresh_lead", "policy_document", "policy_login", "payment", "re_eligible"])
@pytest.mark.parametrize(("choice", "months"), [("3_months", 3), ("6_months", 6), ("12_months", 12), ("custom", None)])
async def test_every_rejectable_stage_and_schedule_runs_automatically(
    client, mock_db, owner_headers, monkeypatch, stage, choice, months,
):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name="Automation Plan", docs=["PAN"])
    response = await _create(client, owner_headers, product)
    assert response.status_code == 200, response.text
    case_id = response.json()["data"]["id"]
    # Start at each supported rejection stage without testing unrelated payment/docs gates.
    await mock_db.application_workflows.update_one({"_id": ObjectId(case_id)}, {"$set": {"current_status": stage}})
    before = await mock_db.application_workflows.find_one({"_id": ObjectId(case_id)})
    application_before = await mock_db.applications.find_one({"_id": ObjectId(before["application_id"])})
    monkeypatch.setattr("app.features.insurance_management.service.utc_now", lambda: NOW)
    payload = {"reason": "Reapply later", "re_eligibility": choice}
    if choice == "custom":
        payload["re_eligible_date"] = "2026-02-02"
    response = await client.post(f"/api/v1/insurance-cases/{case_id}/reject", json=payload, headers=owner_headers)
    assert response.status_code == 200, response.text
    case = await mock_db.application_workflows.find_one({"_id": ObjectId(case_id)})
    # Independent expected instants: Jan 31 + 3 months clamps to Apr 30, while
    # 6/12 months retain day 31; IST midnight is 18:30 UTC on the preceding day.
    due = {
        3: datetime(2026, 4, 29, 18, 30, tzinfo=UTC),
        6: datetime(2026, 7, 30, 18, 30, tzinfo=UTC),
        12: datetime(2027, 1, 30, 18, 30, tzinfo=UTC),
        None: datetime(2026, 2, 1, 18, 30, tzinfo=UTC),
    }[months]
    assert case["current_status"] == "rejected"
    assert case["insurance_details"]["re_eligible_date"] == due
    assert case["insurance_details"]["re_eligibility_choice"] == choice
    counts = (await client.get("/api/v1/insurance-cases/counts", headers=owner_headers)).json()["data"]
    assert counts["rejected"] == 1 and counts["re_eligible"] == 0
    notes_before = await mock_db.application_notes.count_documents({"application_workflow_id": case_id})
    notifications_before = await mock_db.notifications.count_documents({})

    await run_scheduled_worker(monkeypatch, mock_db, due - timedelta(milliseconds=1))
    assert (await mock_db.application_workflows.find_one({"_id": ObjectId(case_id)}))["current_status"] == "rejected"
    await run_scheduled_worker(monkeypatch, mock_db, due)
    await run_scheduled_worker(monkeypatch, mock_db, due + timedelta(days=1))

    counts = (await client.get("/api/v1/insurance-cases/counts", headers=owner_headers)).json()["data"]
    assert counts["rejected"] == 0 and counts["re_eligible"] == 1
    rejected = await client.get("/api/v1/insurance-cases", params={"status": "rejected"}, headers=owner_headers)
    eligible = await client.get("/api/v1/insurance-cases", params={"status": "re_eligible"}, headers=owner_headers)
    assert rejected.status_code == eligible.status_code == 200
    assert rejected.json()["data"] == []
    assert [case["id"] for case in eligible.json()["data"]] == [case_id]
    detail = await client.get(f"/api/v1/insurance-cases/{case_id}", headers=owner_headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["current_status"] == "re_eligible"
    assert detail.json()["data"]["insurance_details"]["re_eligibility_auto_transitioned"] is True
    history_query = {"application_workflow_id": case_id, "from_status": "rejected", "to_status": "re_eligible"}
    assert await mock_db.application_status_history.count_documents(history_query) == 1
    history = await mock_db.application_status_history.find_one(history_query)
    assert history["created_by"] is None
    assert "Automatically" in history["remarks"]
    audit_query = {"event_type": "insurance_case_re_eligibility_auto_transitioned", "metadata.application_workflow_id": case_id}
    assert await mock_db.audit_logs.count_documents(audit_query) == 1
    assert (await mock_db.audit_logs.find_one(audit_query))["metadata"]["actor_type"] == "system"
    assert await mock_db.application_notes.count_documents({"application_workflow_id": case_id}) == notes_before
    assert await mock_db.notifications.count_documents({}) == notifications_before
    after = await mock_db.application_workflows.find_one({"_id": ObjectId(case_id)})
    assert after["created_by"] == before["created_by"]
    assert after["assigned_to"] == before["assigned_to"]
    assert await mock_db.applications.find_one({"_id": ObjectId(before["application_id"])}) == application_before


def test_registered_cron_polls_every_minute_and_catches_up_at_startup():
    job = copy(next(job for job in WorkerSettings.cron_jobs if job.coroutine is reminders.auto_transition_re_eligible_cases))
    assert job.run_at_startup is True
    assert job.hour is None
    assert job.minute == set(range(60))
    job.calculate_next(NOW)
    assert timedelta(0) < job.next_run - NOW < timedelta(seconds=61)
    first = job.next_run
    job.calculate_next(first)
    assert job.next_run - first == timedelta(minutes=1)


@pytest.mark.parametrize("case_type", ["loan", "insurance"])
async def test_already_expired_cases_run_without_owner_and_no_remains_rejected(mock_db, monkeypatch, case_type):
    await _seed_workflow_definitions(mock_db)
    insert = _insert_rejected_case if case_type == "loan" else _insert_rejected_insurance_case
    due_id = await insert(mock_db, case_code="OLD-DUE", re_eligible_date=NOW - timedelta(days=365))
    no_id = await insert(mock_db, case_code="NO", re_eligible_date=None, choice="no")
    corrupt_no_id = await insert(mock_db, case_code="NO-WITH-DATE", re_eligible_date=NOW - timedelta(days=1), choice="no")
    assert await mock_db.users.count_documents({}) == 0
    await run_scheduled_worker(monkeypatch, mock_db, NOW)
    await run_scheduled_worker(monkeypatch, mock_db, NOW + timedelta(days=800))
    assert (await mock_db.application_workflows.find_one({"_id": ObjectId(due_id)}))["current_status"] == "re_eligible"
    for case_id in (no_id, corrupt_no_id):
        assert (await mock_db.application_workflows.find_one({"_id": ObjectId(case_id)}))["current_status"] == "rejected"
        assert await mock_db.application_status_history.count_documents({"application_workflow_id": case_id}) == 0
    assert await mock_db.application_status_history.count_documents({"application_workflow_id": due_id}) == 1


@pytest.mark.parametrize("case_type", ["loan", "insurance"])
async def test_overlapping_workers_only_record_one_transition(mock_db, monkeypatch, case_type):
    await _seed_workflow_definitions(mock_db)
    insert = _insert_rejected_case if case_type == "loan" else _insert_rejected_insurance_case
    case_id = await insert(mock_db, case_code="CONCURRENT", re_eligible_date=NOW)
    monkeypatch.setattr(reminders, "get_database", lambda: mock_db)
    monkeypatch.setattr(reminders, "utc_now", lambda: NOW)
    original = ApplicationWorkflowRepository.update_if_current
    barrier = asyncio.Event()
    arrivals = 0

    async def synchronized(repo, *args, **kwargs):
        nonlocal arrivals
        arrivals += 1
        if arrivals == 2:
            barrier.set()
        await asyncio.wait_for(barrier.wait(), timeout=2)
        return await original(repo, *args, **kwargs)

    monkeypatch.setattr(ApplicationWorkflowRepository, "update_if_current", synchronized)
    results = await asyncio.gather(reminders.auto_transition_re_eligible_cases({}), reminders.auto_transition_re_eligible_cases({}))
    assert sum(result["processed"] for result in results) == 1
    assert sum(result["skipped"] for result in results) == 1
    assert await mock_db.application_status_history.count_documents({"application_workflow_id": case_id}) == 1
    assert await mock_db.audit_logs.count_documents({"event_type": f"{case_type}_case_re_eligibility_auto_transitioned"}) == 1


@pytest.mark.parametrize("change", ["no", "future", "deleted", "status"])
async def test_schedule_changed_after_scan_is_not_transitioned(mock_db, monkeypatch, change):
    await _seed_workflow_definitions(mock_db)
    case_id = await _insert_rejected_insurance_case(mock_db, case_code="CHANGED", re_eligible_date=NOW)
    monkeypatch.setattr(reminders, "get_database", lambda: mock_db)
    monkeypatch.setattr(reminders, "utc_now", lambda: NOW)
    original = ApplicationWorkflowRepository.update_if_current
    changes = {
        "no": {"insurance_details.re_eligibility_choice": "no"},
        "future": {"insurance_details.re_eligible_date": NOW + timedelta(days=30)},
        "deleted": {"is_deleted": True}, "status": {"current_status": "fresh_lead"},
    }

    async def changed(repo, *args, **kwargs):
        await mock_db.application_workflows.update_one({"_id": ObjectId(case_id)}, {"$set": changes[change]})
        return await original(repo, *args, **kwargs)

    monkeypatch.setattr(ApplicationWorkflowRepository, "update_if_current", changed)
    assert (await reminders.auto_transition_re_eligible_cases({}))["processed"] == 0
    assert await mock_db.application_status_history.count_documents({}) == 0


async def test_invalid_loan_does_not_block_due_insurance(mock_db, monkeypatch):
    await _seed_workflow_definitions(mock_db)
    await _insert_rejected_case(mock_db, case_code="BAD-LOAN", re_eligible_date=NOW)
    case_id = await _insert_rejected_insurance_case(mock_db, case_code="GOOD-INSURANCE", re_eligible_date=NOW)
    await mock_db.workflow_definitions.delete_one({"case_type": "loan", "status": "rejected"})
    monkeypatch.setattr(reminders, "get_database", lambda: mock_db)
    monkeypatch.setattr(reminders, "utc_now", lambda: NOW)
    with pytest.raises(RuntimeError, match="failed for 1 case"):
        await reminders.auto_transition_re_eligible_cases({})
    assert (await mock_db.application_workflows.find_one({"_id": ObjectId(case_id)}))["current_status"] == "re_eligible"


async def test_rejection_stores_schedule_with_status_even_if_history_write_fails(client, mock_db, owner_headers, monkeypatch):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name="Atomic Rejection", docs=["PAN"])
    response = await _create(client, owner_headers, product)
    case_id = response.json()["data"]["id"]
    actor = User.model_validate(await mock_db.users.find_one({"role": "owner"}))
    monkeypatch.setattr("app.features.insurance_management.service.utc_now", lambda: NOW)
    original_insert = ApplicationStatusHistoryRepository.insert
    monkeypatch.setattr(ApplicationStatusHistoryRepository, "insert", AsyncMock(side_effect=RuntimeError("history unavailable")))
    with pytest.raises(RuntimeError, match="history unavailable"):
        await InsuranceCaseService(mock_db).reject_case(case_id, "Later", "3_months", None, actor)
    case = await mock_db.application_workflows.find_one({"_id": ObjectId(case_id)})
    assert case["current_status"] == "rejected"
    assert case["insurance_details"]["re_eligible_date"] == add_calendar_months(NOW, 3)
    monkeypatch.setattr(ApplicationStatusHistoryRepository, "insert", original_insert)
    await run_scheduled_worker(monkeypatch, mock_db, add_calendar_months(NOW, 3))
    assert (await mock_db.application_workflows.find_one({"_id": ObjectId(case_id)}))["current_status"] == "re_eligible"


async def test_stale_manual_mark_does_not_duplicate_worker_history(mock_db, monkeypatch):
    await _seed_workflow_definitions(mock_db)
    case_id = await _insert_rejected_insurance_case(mock_db, case_code="MANUAL-RACE", re_eligible_date=NOW)
    stale = await ApplicationWorkflowRepository(mock_db).find_by_id(case_id)
    await run_scheduled_worker(monkeypatch, mock_db, NOW)
    with pytest.raises(ConflictError):
        await WorkflowEngine(mock_db).transition(stale, "re_eligible", User(id=str(ObjectId()), mobile="9000000000", role="owner"))
    assert await mock_db.application_status_history.count_documents({"application_workflow_id": case_id}) == 1


@pytest.mark.parametrize("stage", ["fresh_lead", "policy_document", "policy_login", "payment", "re_eligible"])
async def test_no_re_eligibility_from_every_stage_is_never_scheduled(client, mock_db, owner_headers, monkeypatch, stage):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name="No Reapply", docs=["PAN"])
    response = await _create(client, owner_headers, product)
    case_id = response.json()["data"]["id"]
    await mock_db.application_workflows.update_one({"_id": ObjectId(case_id)}, {"$set": {"current_status": stage}})
    response = await client.post(
        f"/api/v1/insurance-cases/{case_id}/reject",
        json={"reason": "Do not reapply", "re_eligibility": "no"}, headers=owner_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["insurance_details"]["re_eligible_date"] is None
    await run_scheduled_worker(monkeypatch, mock_db, NOW + timedelta(days=3650))
    assert (await mock_db.application_workflows.find_one({"_id": ObjectId(case_id)}))["current_status"] == "rejected"


@pytest.mark.parametrize("stage", ["policy_issued", "on_hold", "rejected"])
async def test_unsupported_rejection_stages_keep_existing_rules(client, mock_db, owner_headers, stage):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name="Closed or Paused", docs=["PAN"])
    response = await _create(client, owner_headers, product)
    case_id = response.json()["data"]["id"]
    await mock_db.application_workflows.update_one({"_id": ObjectId(case_id)}, {"$set": {"current_status": stage}})
    response = await client.post(
        f"/api/v1/insurance-cases/{case_id}/reject",
        json={"reason": "Reject", "re_eligibility": "3_months"}, headers=owner_headers,
    )
    assert response.status_code == 409
    assert (await mock_db.application_workflows.find_one({"_id": ObjectId(case_id)}))["current_status"] == stage


async def test_scheduled_worker_drains_more_than_one_thousand_overdue_cases(mock_db, monkeypatch):
    await _seed_workflow_definitions(mock_db)
    template_id = await _insert_rejected_insurance_case(mock_db, case_code="BACKLOG-0", re_eligible_date=NOW)
    template = await mock_db.application_workflows.find_one({"_id": ObjectId(template_id)})
    await mock_db.application_workflows.insert_many([
        {**template, "_id": ObjectId(), "case_code": f"BACKLOG-{index}", "application_id": f"app-{index}"}
        for index in range(1, 1001)
    ])
    await run_scheduled_worker(monkeypatch, mock_db, NOW, timeout=60)
    assert await mock_db.application_workflows.count_documents({"current_status": "re_eligible"}) == 1001
    assert await mock_db.application_status_history.count_documents({"to_status": "re_eligible"}) == 1001
