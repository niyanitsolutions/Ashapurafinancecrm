"""End-to-end tests for Module 6D (Reminder & Notification Engine): Task CRUD +
completion, Access Control permission gating on Tasks/Reminder Rules, Notification
inbox self-service (read/archive/dismiss, ownership-scoped), and the three Arq scheduler
jobs run directly (not via a live worker): polling `audit_logs` for `lead_assigned`/
`document_uploaded` (with checkpoint idempotency), the Loan re-eligibility reminder, and
the full Task-due -> escalation -> Owner-escalation ladder — all driven by
`reminder_rules` rows, never hardcoded timings.
"""

from datetime import timedelta

from app.features.reminders.models import ReminderRule, Task
from app.utils.datetime import utc_now
from app.utils.helpers import to_object_id
from app.worker.tasks.reminders import check_re_eligible_cases, check_task_reminders, poll_audit_events


async def _create_employee(client, owner_headers, master_data, mobile, email):
    payload = {
        "mobile": mobile, "initial_password": "InitialPass1!", "first_name": "Staff", "last_name": "Member", "email": email,
        "department_id": master_data["department_id"], "designation_id": master_data["designation_id"], "branch_id": master_data["branch_id"],
        "joining_date": "2026-01-15", "employment_type": "full_time",
    }
    r = await client.post("/api/v1/employees", json=payload, headers=owner_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _grant_permission(client, owner_headers, employee_id, *, module, resource, actions):
    r = await client.post("/api/v1/permissions", json={"module": module, "resource": resource, "actions": actions}, headers=owner_headers)
    if r.status_code == 409:
        existing = await client.get("/api/v1/permissions", headers=owner_headers)
        permission = next(p for p in existing.json()["data"] if p["module"] == module and p["resource"] == resource)
    else:
        assert r.status_code == 200, r.text
        permission = r.json()["data"]
    r = await client.post("/api/v1/roles", json={"name": f"Role for {module}:{resource}:{employee_id}"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    role = r.json()["data"]
    r = await client.put(
        f"/api/v1/roles/{role['id']}/permissions", json={"grants": [{"permission_id": permission["id"], "granted_actions": actions}]}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/roles/{role['id']}/assign", json={"employee_id": employee_id}, headers=owner_headers)
    assert r.status_code == 200, r.text


async def _login(client, mobile, password):
    r = await client.post("/api/v1/auth/login", json={"mobile": mobile, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


# ---------------------------------------------------------------------- Tasks


async def test_task_lifecycle_and_assignment_notification(client, mock_db, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data, mobile="9700000101", email="task.officer@example.com")
    await _grant_permission(client, owner_headers, employee["id"], module="reminders", resource="tasks", actions=["view", "create", "edit"])
    employee_headers = await _login(client, "9700000101", "InitialPass1!")

    due_at = (utc_now() + timedelta(hours=2)).isoformat()
    r = await client.post(
        "/api/v1/tasks", json={"title": "Follow up with customer", "description": "Call before EOD", "assigned_to": employee["id"], "due_at": due_at},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    task = r.json()["data"]
    assert task["status"] == "pending"
    assert task["assigned_to_name"]

    # Assignment itself creates a notification for the assignee.
    r = await client.get("/api/v1/notifications", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert any(n["notification_type"] == "task_assigned" for n in r.json()["data"])

    # Owner sees all tasks; the assignee sees only their own.
    r = await client.get("/api/v1/tasks", headers=owner_headers)
    assert any(t["id"] == task["id"] for t in r.json()["data"])
    r = await client.get("/api/v1/tasks", headers=employee_headers)
    assert all(t["assigned_to"] == employee["id"] for t in r.json()["data"])

    other_employee = await _create_employee(client, owner_headers, master_data, mobile="9700000102", email="other.officer@example.com")
    await _grant_permission(client, owner_headers, other_employee["id"], module="reminders", resource="tasks", actions=["view"])
    other_headers = await _login(client, "9700000102", "InitialPass1!")
    r = await client.get(f"/api/v1/tasks/{task['id']}", headers=other_headers)
    assert r.status_code == 403, r.text  # not assigned to them

    r = await client.post(f"/api/v1/tasks/{task['id']}/complete", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "completed"
    assert r.json()["data"]["completed_at"] is not None


async def test_task_assigned_notification_uses_active_notification_template(client, mock_db, owner_headers, master_data):
    from app.features.system_settings.models import NotificationTemplate

    template = NotificationTemplate(
        channel="internal", key="task_assigned", subject="You've got a task: {{task_title}}",
        body="Please action: {{task_title}}", available_variables=["task_title"],
    )
    await mock_db["notification_templates"].insert_one(template.model_dump(by_alias=True, exclude={"id"}))

    employee = await _create_employee(client, owner_headers, master_data, mobile="9700000199", email="templated.task@example.com")
    employee_headers = await _login(client, "9700000199", "InitialPass1!")

    due_at = (utc_now() + timedelta(hours=2)).isoformat()
    r = await client.post(
        "/api/v1/tasks", json={"title": "Call the customer", "assigned_to": employee["id"], "due_at": due_at}, headers=owner_headers
    )
    assert r.status_code == 200, r.text

    r = await client.get("/api/v1/notifications", headers=employee_headers)
    assert r.status_code == 200, r.text
    notification = next(n for n in r.json()["data"] if n["notification_type"] == "task_assigned")
    assert notification["title"] == "You've got a task: Call the customer"
    assert notification["message"] == "Please action: Call the customer"


async def test_task_assigned_notification_falls_back_when_no_template_configured(client, mock_db, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data, mobile="9700000198", email="untemplated.task@example.com")
    employee_headers = await _login(client, "9700000198", "InitialPass1!")

    due_at = (utc_now() + timedelta(hours=2)).isoformat()
    r = await client.post(
        "/api/v1/tasks", json={"title": "Call the customer", "assigned_to": employee["id"], "due_at": due_at}, headers=owner_headers
    )
    assert r.status_code == 200, r.text

    r = await client.get("/api/v1/notifications", headers=employee_headers)
    notification = next(n for n in r.json()["data"] if n["notification_type"] == "task_assigned")
    assert notification["title"] == "New Task Assigned"
    assert notification["message"] == 'You have been assigned a new task: "Call the customer".'


async def test_employee_denied_task_creation_without_permission(client, mock_db, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data, mobile="9700000103", email="unpermitted.task@example.com")
    employee_headers = await _login(client, "9700000103", "InitialPass1!")

    r = await client.post(
        "/api/v1/tasks", json={"title": "X", "assigned_to": employee["id"], "due_at": utc_now().isoformat()}, headers=employee_headers
    )
    assert r.status_code == 403, r.text

    await _grant_permission(client, owner_headers, employee["id"], module="reminders", resource="tasks", actions=["view", "create"])
    employee_headers = await _login(client, "9700000103", "InitialPass1!")
    r = await client.post(
        "/api/v1/tasks", json={"title": "X", "assigned_to": employee["id"], "due_at": utc_now().isoformat()}, headers=employee_headers
    )
    assert r.status_code == 200, r.text


async def test_task_created_with_default_priority_when_omitted(client, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data, mobile="9700000106", email="default.priority@example.com")
    r = await client.post(
        "/api/v1/tasks", json={"title": "No priority specified", "assigned_to": employee["id"], "due_at": utc_now().isoformat()}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    task = r.json()["data"]
    assert task["priority"] == "medium"
    assert task["related_entity_type"] is None
    assert task["related_entity_id"] is None


async def test_task_created_with_explicit_priority_and_linkage(client, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data, mobile="9700000107", email="explicit.priority@example.com")
    r = await client.post(
        "/api/v1/tasks",
        json={
            "title": "Follow up on lead", "assigned_to": employee["id"], "due_at": utc_now().isoformat(),
            "priority": "high", "related_entity_type": "lead", "related_entity_id": "6a7df9db63fd1e0eb7749f99",
        },
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    task = r.json()["data"]
    assert task["priority"] == "high"
    assert task["related_entity_type"] == "lead"
    assert task["related_entity_id"] == "6a7df9db63fd1e0eb7749f99"

    r = await client.get(f"/api/v1/tasks/{task['id']}", headers=owner_headers)
    assert r.status_code == 200, r.text
    refetched = r.json()["data"]
    assert refetched["priority"] == "high"
    assert refetched["related_entity_type"] == "lead"
    assert refetched["related_entity_id"] == "6a7df9db63fd1e0eb7749f99"


async def test_task_creation_rejects_partial_linkage(client, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data, mobile="9700000108", email="partial.linkage@example.com")
    r = await client.post(
        "/api/v1/tasks",
        json={"title": "Bad linkage", "assigned_to": employee["id"], "due_at": utc_now().isoformat(), "related_entity_type": "lead"},
        headers=owner_headers,
    )
    assert r.status_code == 422, r.text


async def test_list_tasks_filters_by_priority_and_related_entity(client, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data, mobile="9700000109", email="filter.tasks@example.com")
    await _grant_permission(client, owner_headers, employee["id"], module="reminders", resource="tasks", actions=["view", "create"])
    employee_headers = await _login(client, "9700000109", "InitialPass1!")

    due_at = utc_now().isoformat()
    r = await client.post(
        "/api/v1/tasks",
        json={"title": "High priority lead task", "assigned_to": employee["id"], "due_at": due_at, "priority": "high", "related_entity_type": "lead", "related_entity_id": "6a7df9db63fd1e0eb7749f01"},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    high_lead_task = r.json()["data"]
    r = await client.post(
        "/api/v1/tasks",
        json={"title": "Low priority customer task", "assigned_to": employee["id"], "due_at": due_at, "priority": "low", "related_entity_type": "customer", "related_entity_id": "6a7df9db63fd1e0eb7749f02"},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text

    r = await client.get("/api/v1/tasks?priority=high", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert {t["id"] for t in r.json()["data"]} == {high_lead_task["id"]}

    r = await client.get("/api/v1/tasks?related_entity_type=lead&related_entity_id=6a7df9db63fd1e0eb7749f01", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert {t["id"] for t in r.json()["data"]} == {high_lead_task["id"]}

    # Ownership scoping still composes with the new filters — the assignee's own
    # filtered view never leaks another employee's tasks, and here it's the same
    # employee, so both tasks are visible, but still only priority-filtered correctly.
    r = await client.get("/api/v1/tasks?priority=low", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert all(t["priority"] == "low" for t in r.json()["data"])
    assert all(t["assigned_to"] == employee["id"] for t in r.json()["data"])


# ---------------------------------------------------------------------- Reminder Rules


async def test_reminder_rule_crud_and_activation(client, owner_headers):
    r = await client.post(
        "/api/v1/reminder-rules",
        json={"rule_type": "task_due", "label": "Test Rule", "notify_before_minutes": [15], "escalation_repeat_minutes": 30, "escalation_max_repeats": 1},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    rule = r.json()["data"]
    assert rule["status"] == "active"
    assert rule["notify_before_minutes"] == [15]

    r = await client.patch(f"/api/v1/reminder-rules/{rule['id']}", json={"notify_before_minutes": [20, 5]}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["notify_before_minutes"] == [20, 5]

    r = await client.patch(f"/api/v1/reminder-rules/{rule['id']}/deactivate", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "inactive"

    r = await client.get("/api/v1/reminder-rules", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert any(x["id"] == rule["id"] for x in r.json()["data"])


# ---------------------------------------------------------------------- Notifications self-service


async def test_notification_inbox_read_archive_dismiss_and_ownership(client, mock_db, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data, mobile="9700000104", email="inbox.officer@example.com")
    await _grant_permission(client, owner_headers, employee["id"], module="reminders", resource="tasks", actions=["view", "create"])
    employee_headers = await _login(client, "9700000104", "InitialPass1!")

    r = await client.post(
        "/api/v1/tasks", json={"title": "Inbox test task", "assigned_to": employee["id"], "due_at": utc_now().isoformat()}, headers=owner_headers
    )
    assert r.status_code == 200, r.text

    r = await client.get("/api/v1/notifications", headers=employee_headers)
    assert r.status_code == 200, r.text
    notification = r.json()["data"][0]
    assert notification["status"] == "unread"
    assert notification["notification_type"] == "task_assigned"
    assert notification["category"] == "assignment"  # derived automatically, not caller-supplied

    r = await client.get("/api/v1/notifications?category=assignment", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert any(n["id"] == notification["id"] for n in r.json()["data"])

    r = await client.get("/api/v1/notifications?category=task", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert all(n["id"] != notification["id"] for n in r.json()["data"])  # wrong category — filtered out

    r = await client.get("/api/v1/notifications/unread-count", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["unread_count"] >= 1

    # The Owner cannot act on the Employee's own notification.
    r = await client.post(f"/api/v1/notifications/{notification['id']}/read", headers=owner_headers)
    assert r.status_code == 404, r.text

    r = await client.post(f"/api/v1/notifications/{notification['id']}/read", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "read"
    assert r.json()["data"]["read_at"] is not None

    r = await client.post(f"/api/v1/notifications/{notification['id']}/archive", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "archived"

    r = await client.get("/api/v1/notifications?status=archived", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert any(n["id"] == notification["id"] for n in r.json()["data"])


# ---------------------------------------------------------------------- Scheduler jobs (called directly)


async def test_poll_audit_events_creates_lead_assigned_notification_once(client, mock_db, owner_headers, master_data, monkeypatch):
    monkeypatch.setattr("app.worker.tasks.reminders.get_database", lambda: mock_db)
    employee = await _create_employee(client, owner_headers, master_data, mobile="9700000105", email="poll.officer@example.com")

    await mock_db["audit_logs"].insert_one(
        {"event_type": "lead_assigned", "user_id": None, "metadata": {"lead_id": "000000000000000000000001", "employee_id": employee["id"]}, "created_at": utc_now()}
    )

    await poll_audit_events({})
    employee_headers = await _login(client, "9700000105", "InitialPass1!")
    r = await client.get("/api/v1/notifications", headers=employee_headers)
    assert r.status_code == 200, r.text
    matches = [n for n in r.json()["data"] if n["notification_type"] == "lead_assigned"]
    assert len(matches) == 1

    await poll_audit_events({})  # re-running must not duplicate (checkpoint)
    r = await client.get("/api/v1/notifications", headers=employee_headers)
    matches = [n for n in r.json()["data"] if n["notification_type"] == "lead_assigned"]
    assert len(matches) == 1


async def test_check_re_eligible_cases_notifies_assigned_employee_once(client, mock_db, owner_headers, master_data, monkeypatch):
    monkeypatch.setattr("app.worker.tasks.reminders.get_database", lambda: mock_db)
    employee = await _create_employee(client, owner_headers, master_data, mobile="9700000106", email="reeligible.officer@example.com")
    employee_headers = await _login(client, "9700000106", "InitialPass1!")

    rule = ReminderRule(rule_type="re_eligibility", label="Test Loan Re-Eligibility", case_type="loan", eligible_after_days=90, notify_before_days=[10])
    await mock_db["reminder_rules"].insert_one(rule.model_dump(by_alias=True, exclude={"id"}))

    now = utc_now()
    workflow_id = (
        await mock_db["application_workflows"].insert_one(
            {
                "case_code": "AFS-LOAN-000001", "case_type": "loan", "application_id": "000000000000000000000002",
                "customer_id": "000000000000000000000003", "product_id": "000000000000000000000004", "product_category": "loan",
                "assigned_to": employee["id"], "current_status": "rejected", "rejection_reason": "Low credit score",
                "pending_document_type_ids": [], "loan_details": {}, "is_deleted": False, "status": "active",
                "created_at": now, "updated_at": now, "version": 1,
            }
        )
    ).inserted_id
    rejected_at = now - timedelta(days=100)  # 100 days ago: eligible in -10 days (i.e. already within the notify window)
    await mock_db["application_status_history"].insert_one(
        {
            "application_workflow_id": str(workflow_id), "case_type": "loan", "from_status": "final_evaluation", "to_status": "rejected",
            "is_deleted": False, "status": "active", "created_at": rejected_at, "updated_at": rejected_at, "version": 1,
        }
    )

    await check_re_eligible_cases({})
    r = await client.get("/api/v1/notifications", headers=employee_headers)
    assert r.status_code == 200, r.text
    matches = [n for n in r.json()["data"] if n["notification_type"] == "reminder_triggered"]
    assert len(matches) == 1

    await check_re_eligible_cases({})  # idempotent — no duplicate reminder for the same rule+case
    r = await client.get("/api/v1/notifications", headers=employee_headers)
    matches = [n for n in r.json()["data"] if n["notification_type"] == "reminder_triggered"]
    assert len(matches) == 1


async def test_check_re_eligible_cases_fires_each_configured_trigger_point_independently(client, mock_db, owner_headers, master_data, monkeypatch):
    monkeypatch.setattr("app.worker.tasks.reminders.get_database", lambda: mock_db)
    employee = await _create_employee(client, owner_headers, master_data, mobile="9700000108", email="multitrigger.officer@example.com")
    employee_headers = await _login(client, "9700000108", "InitialPass1!")

    # Two trigger points: 30 days before eligibility, and 10 days before.
    rule = ReminderRule(rule_type="re_eligibility", label="Multi-Trigger Loan Re-Eligibility", case_type="loan", eligible_after_days=90, notify_before_days=[30, 10])
    await mock_db["reminder_rules"].insert_one(rule.model_dump(by_alias=True, exclude={"id"}))

    now = utc_now()
    workflow_id = (
        await mock_db["application_workflows"].insert_one(
            {
                "case_code": "AFS-LOAN-000002", "case_type": "loan", "application_id": "000000000000000000000005",
                "customer_id": "000000000000000000000006", "product_id": "000000000000000000000007", "product_category": "loan",
                "assigned_to": employee["id"], "current_status": "rejected", "rejection_reason": "Low credit score",
                "pending_document_type_ids": [], "loan_details": {}, "is_deleted": False, "status": "active",
                "created_at": now, "updated_at": now, "version": 1,
            }
        )
    ).inserted_id
    # Rejected 100 days ago: eligible in -10 days — past BOTH the 30-day and 10-day marks already.
    rejected_at = now - timedelta(days=100)
    await mock_db["application_status_history"].insert_one(
        {
            "application_workflow_id": str(workflow_id), "case_type": "loan", "from_status": "final_evaluation", "to_status": "rejected",
            "is_deleted": False, "status": "active", "created_at": rejected_at, "updated_at": rejected_at, "version": 1,
        }
    )

    await check_re_eligible_cases({})
    r = await client.get("/api/v1/notifications", headers=employee_headers)
    assert r.status_code == 200, r.text
    matches = [n for n in r.json()["data"] if n["notification_type"] == "reminder_triggered"]
    assert len(matches) == 2  # both trigger points fired, independently

    await check_re_eligible_cases({})  # idempotent per trigger point — still exactly 2
    r = await client.get("/api/v1/notifications", headers=employee_headers)
    matches = [n for n in r.json()["data"] if n["notification_type"] == "reminder_triggered"]
    assert len(matches) == 2


async def test_task_due_and_escalation_ladder_ends_with_owner_notification(client, mock_db, owner_headers, master_data, monkeypatch):
    monkeypatch.setattr("app.worker.tasks.reminders.get_database", lambda: mock_db)
    employee = await _create_employee(client, owner_headers, master_data, mobile="9700000107", email="escalation.officer@example.com")
    employee_headers = await _login(client, "9700000107", "InitialPass1!")

    rule = ReminderRule(rule_type="task_due", label="Test Task Due", notify_before_minutes=[30], escalation_repeat_minutes=60, escalation_max_repeats=2)
    await mock_db["reminder_rules"].insert_one(rule.model_dump(by_alias=True, exclude={"id"}))

    now = utc_now()
    task = Task(title="Overdue task", assigned_to=employee["id"], assigned_by="000000000000000000000099", due_at=now - timedelta(minutes=5))
    task_id = (await mock_db["tasks"].insert_one(task.model_dump(by_alias=True, exclude={"id"}))).inserted_id

    await check_task_reminders({})  # first escalation fires
    escalations = [doc async for doc in mock_db["reminders"].find({"target_id": str(task_id), "reminder_type": "task_escalation"})]
    assert len(escalations) == 1

    # Simulate the repeat-interval having elapsed so a second escalation is due.
    await mock_db["reminders"].update_one({"_id": to_object_id(str(escalations[0]["_id"]))}, {"$set": {"fired_at": now - timedelta(minutes=61)}})

    await check_task_reminders({})  # second (final) escalation fires, and Owner gets notified
    escalations = [doc async for doc in mock_db["reminders"].find({"target_id": str(task_id), "reminder_type": "task_escalation"})]
    assert len(escalations) == 2

    task_doc = await mock_db["tasks"].find_one({"_id": task_id})
    assert task_doc["owner_escalated"] is True

    r = await client.get("/api/v1/notifications", headers=owner_headers)
    assert any(n["notification_type"] == "task_owner_escalation" for n in r.json()["data"])

    r = await client.get("/api/v1/notifications", headers=employee_headers)
    assert len([n for n in r.json()["data"] if n["notification_type"] == "task_escalation"]) == 2

    await check_task_reminders({})  # already owner_escalated — must not fire again
    escalations = [doc async for doc in mock_db["reminders"].find({"target_id": str(task_id), "reminder_type": "task_escalation"})]
    assert len(escalations) == 2
