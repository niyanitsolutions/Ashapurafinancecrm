"""End-to-end tests for Module 5 (Dashboard Framework): nav filtering (owner_only vs.
permission-gated), widget layout resolution/customization (defaults, visibility,
ordering), real widget data (Employee/Department Summary, Recent Activities), honest
placeholders for not-yet-built modules, and Quick Search permission gating.
"""

from app.features.dashboard.constants import WidgetType
from app.features.dashboard.models import DashboardWidget, NavItem


async def _seed_widget(mock_db, **overrides):
    defaults = {
        "key": "test_widget",
        "label": "Test Widget",
        "category": "test",
        "widget_type": WidgetType.METRIC,
        "required_module": None,
        "required_resource": None,
        "required_action": None,
        "default_order": 0,
    }
    defaults.update(overrides)
    widget = DashboardWidget(**defaults)
    await mock_db["dashboard_widgets"].insert_one(widget.model_dump(by_alias=True, exclude={"id"}))
    return widget


async def _seed_nav_item(mock_db, **overrides):
    defaults = {"key": "test_nav", "label": "Test Nav", "route": "/test", "order": 0}
    defaults.update(overrides)
    item = NavItem(**defaults)
    await mock_db["nav_items"].insert_one(item.model_dump(by_alias=True, exclude={"id"}))
    return item


async def _create_employee(client, owner_headers, master_data, mobile="9411111111", email="dashboard.test@example.com"):
    payload = {
        "mobile": mobile,
        "initial_password": "InitialPass1!",
        "first_name": "Dash",
        "last_name": "Tester",
        "email": email,
        "department_id": master_data["department_id"],
        "designation_id": master_data["designation_id"],
        "branch_id": master_data["branch_id"],
        "joining_date": "2026-01-15",
        "employment_type": "full_time",
    }
    r = await client.post("/api/v1/employees", json=payload, headers=owner_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _login(client, mobile, password="InitialPass1!"):
    r = await client.post("/api/v1/auth/login", json={"mobile": mobile, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


# ---------------------------------------------------------------------- nav


async def test_nav_filters_owner_only_and_ungated_items(client, mock_db, owner_headers, employee_headers):
    await _seed_nav_item(mock_db, key="dashboard", label="Dashboard", route="/", order=0)
    await _seed_nav_item(mock_db, key="employees", label="Employees", route="/employees", order=10, owner_only=True)

    r = await client.get("/api/v1/dashboard/nav", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert {i["key"] for i in r.json()["data"]} == {"dashboard", "employees"}

    r = await client.get("/api/v1/dashboard/nav", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert {i["key"] for i in r.json()["data"]} == {"dashboard"}


async def test_nav_permission_gated_item_requires_grant(client, mock_db, owner_headers, master_data):
    await _seed_nav_item(
        mock_db, key="settings", label="Settings", route="/settings", order=30,
        required_module="system_settings", required_resource="company_settings", required_action="view",
    )
    employee = await _create_employee(client, owner_headers, master_data)
    own_headers = await _login(client, "9411111111")

    r = await client.get("/api/v1/dashboard/nav", headers=own_headers)
    assert r.json()["data"] == []

    permission = await client.post(
        "/api/v1/permissions", json={"module": "system_settings", "resource": "company_settings", "actions": ["view"]}, headers=owner_headers
    )
    role = await client.post("/api/v1/roles", json={"name": "Settings Viewer"}, headers=owner_headers)
    role_id = role.json()["data"]["id"]
    await client.put(
        f"/api/v1/roles/{role_id}/permissions",
        json={"grants": [{"permission_id": permission.json()["data"]["id"], "granted_actions": ["view"]}]},
        headers=owner_headers,
    )
    await client.post(f"/api/v1/roles/{role_id}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)

    r = await client.get("/api/v1/dashboard/nav", headers=own_headers)
    assert {i["key"] for i in r.json()["data"]} == {"settings"}


async def test_customers_nav_items_require_customer_view_permission(client, mock_db, owner_headers, master_data):
    # Regression test for the Employee Permission Matrix redesign gap: `customer/router.py`
    # gates GET /customers and GET /applications behind `CustomerViewDep`
    # (require_permission("customer", "customers", "view")), but the "customers"/
    # "applications" nav_items rows (scripts/seed.py's seed_ui_navigation_nav_items) were
    # never updated to match, so the sidebar link stayed visible to every employee
    # regardless of grant. Mirrors exactly what seed.py now seeds for these two keys —
    # see scripts/migrate_gate_customer_nav_items.py for the already-provisioned-database
    # backfill.
    await _seed_nav_item(
        mock_db, key="customers", label="Customers", route="/customers", order=40,
        required_module="customer", required_resource="customers", required_action="view",
    )
    await _seed_nav_item(
        mock_db, key="applications", label="Applications", route="/applications", order=41,
        required_module="customer", required_resource="customers", required_action="view",
    )
    employee = await _create_employee(client, owner_headers, master_data, mobile="9422222222", email="navcustomer.test@example.com")
    own_headers = await _login(client, "9422222222")

    r = await client.get("/api/v1/dashboard/nav", headers=own_headers)
    assert r.json()["data"] == []

    permission = await client.post(
        "/api/v1/permissions", json={"module": "customer", "resource": "customers", "actions": ["view", "create", "edit"]}, headers=owner_headers
    )
    role = await client.post("/api/v1/roles", json={"name": "Customer Nav Viewer"}, headers=owner_headers)
    role_id = role.json()["data"]["id"]
    await client.put(
        f"/api/v1/roles/{role_id}/permissions",
        json={"grants": [{"permission_id": permission.json()["data"]["id"], "granted_actions": ["view"]}]},
        headers=owner_headers,
    )
    await client.post(f"/api/v1/roles/{role_id}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)

    r = await client.get("/api/v1/dashboard/nav", headers=own_headers)
    assert {i["key"] for i in r.json()["data"]} == {"customers", "applications"}

    # Owner is unaffected by the gate — unconditional PermissionEngine bypass.
    r = await client.get("/api/v1/dashboard/nav", headers=owner_headers)
    assert {i["key"] for i in r.json()["data"]} == {"customers", "applications"}


# ---------------------------------------------------------------------- layout


async def test_layout_defaults_then_customize(client, mock_db, owner_headers):
    await _seed_widget(mock_db, key="employee_summary", label="Employee Summary", default_order=0, default_visible=True)
    await _seed_widget(mock_db, key="today_leads", label="Today's Leads", default_order=1, default_visible=True)

    r = await client.get("/api/v1/dashboard/layout", headers=owner_headers)
    assert r.status_code == 200, r.text
    layout = r.json()["data"]
    assert [w["key"] for w in layout] == ["employee_summary", "today_leads"]
    assert all(w["is_visible"] for w in layout)
    assert all(w["data"] is None for w in layout)

    r = await client.put(
        "/api/v1/dashboard/layout",
        json={"widgets": [
            {"widget_key": "employee_summary", "is_visible": False, "order": 1, "refresh_interval_seconds": 60},
            {"widget_key": "today_leads", "is_visible": True, "order": 0, "refresh_interval_seconds": 120},
        ]},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    updated = r.json()["data"]
    assert [w["key"] for w in updated] == ["today_leads", "employee_summary"]
    assert updated[1]["is_visible"] is False
    assert updated[0]["refresh_interval_seconds"] == 120

    # persisted — a second GET reflects the same customization, not the catalog defaults
    r = await client.get("/api/v1/dashboard/layout", headers=owner_headers)
    layout = r.json()["data"]
    assert [w["key"] for w in layout] == ["today_leads", "employee_summary"]


async def test_update_layout_rejects_unknown_widget_key(client, mock_db, owner_headers):
    await _seed_widget(mock_db, key="employee_summary")
    r = await client.put(
        "/api/v1/dashboard/layout",
        json={"widgets": [{"widget_key": "does_not_exist", "is_visible": True, "order": 0, "refresh_interval_seconds": 60}]},
        headers=owner_headers,
    )
    assert r.status_code == 422, r.text


async def test_dashboard_excludes_hidden_widgets(client, mock_db, owner_headers):
    await _seed_widget(mock_db, key="employee_summary", default_order=0)
    await _seed_widget(mock_db, key="today_leads", default_order=1)

    await client.put(
        "/api/v1/dashboard/layout",
        json={"widgets": [{"widget_key": "today_leads", "is_visible": False, "order": 1, "refresh_interval_seconds": 300}]},
        headers=owner_headers,
    )

    r = await client.get("/api/v1/dashboard", headers=owner_headers)
    assert r.status_code == 200, r.text
    keys = [w["key"] for w in r.json()["data"]]
    assert keys == ["employee_summary"]
    assert all(w["data"] is not None for w in r.json()["data"])


# ---------------------------------------------------------------------- widget data


async def test_employee_summary_widget_reflects_real_counts(client, mock_db, owner_headers, master_data):
    await _seed_widget(mock_db, key="employee_summary", label="Employee Summary")
    await _create_employee(client, owner_headers, master_data)

    r = await client.get("/api/v1/dashboard", headers=owner_headers)
    assert r.status_code == 200, r.text
    widget = next(w for w in r.json()["data"] if w["key"] == "employee_summary")
    assert widget["data"]["available"] is True
    assert widget["data"]["total"] >= 1
    assert widget["data"]["active"] >= 1


async def test_department_summary_widget_groups_by_department(client, mock_db, owner_headers, master_data):
    await _seed_widget(mock_db, key="department_summary", label="Department Summary", widget_type=WidgetType.LIST)
    await _create_employee(client, owner_headers, master_data)

    r = await client.get("/api/v1/dashboard", headers=owner_headers)
    widget = next(w for w in r.json()["data"] if w["key"] == "department_summary")
    assert widget["data"]["available"] is True
    assert any(row["employee_count"] >= 1 for row in widget["data"]["items"])


async def test_not_yet_available_widget_returns_honest_placeholder(client, mock_db, owner_headers):
    # "today_leads" is deliberately NOT used here — Module 6A (Lead Foundation) wired it
    # to real data (decision 039); "revenue" still has no owning module (Loan/Insurance
    # Management, Module 6C) and stays a placeholder.
    await _seed_widget(mock_db, key="revenue", label="Revenue")

    r = await client.get("/api/v1/dashboard", headers=owner_headers)
    widget = next(w for w in r.json()["data"] if w["key"] == "revenue")
    assert widget["data"] == {"available": False, "value": 0}


async def test_recent_activities_scoped_to_self_for_employee(client, mock_db, owner_headers, employee_headers):
    await _seed_widget(mock_db, key="recent_activities", label="Recent Activities", widget_type=WidgetType.LIST)

    r = await client.get("/api/v1/dashboard", headers=employee_headers)
    widget = next(w for w in r.json()["data"] if w["key"] == "recent_activities")
    assert widget["data"]["available"] is True
    # employee_headers's own login is the only audit event attributable to them
    assert all(item["event_type"] in ("login",) for item in widget["data"]["items"])


# ---------------------------------------------------------------------- widgets forward-compatible with future modules


async def test_widget_for_unbuilt_module_becomes_grantable_once_catalog_entry_exists(client, mock_db, owner_headers, master_data):
    await _seed_widget(mock_db, key="today_leads", label="Today's Leads", required_module="leads", required_resource="leads", required_action="view")
    employee = await _create_employee(client, owner_headers, master_data)
    own_headers = await _login(client, "9411111111")

    r = await client.get("/api/v1/dashboard/layout", headers=own_headers)
    assert r.json()["data"] == []  # no catalog entry for "leads" yet — correctly invisible

    permission = await client.post("/api/v1/permissions", json={"module": "leads", "resource": "leads", "actions": ["view"]}, headers=owner_headers)
    role = await client.post("/api/v1/roles", json={"name": "Lead Viewer"}, headers=owner_headers)
    role_id = role.json()["data"]["id"]
    await client.put(
        f"/api/v1/roles/{role_id}/permissions",
        json={"grants": [{"permission_id": permission.json()["data"]["id"], "granted_actions": ["view"]}]},
        headers=owner_headers,
    )
    await client.post(f"/api/v1/roles/{role_id}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)

    r = await client.get("/api/v1/dashboard/layout", headers=own_headers)
    assert [w["key"] for w in r.json()["data"]] == ["today_leads"]


# ---------------------------------------------------------------------- quick search


async def test_search_requires_permission_for_employee_results(client, mock_db, owner_headers, employee_headers, master_data):
    await _create_employee(client, owner_headers, master_data, mobile="9422222222", email="findme@example.com")

    r = await client.get("/api/v1/dashboard/search?q=Dash", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]["results"]) >= 1

    r = await client.get("/api/v1/dashboard/search?q=Dash", headers=employee_headers)
    assert r.json()["data"]["results"] == []
