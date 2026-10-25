from unittest.mock import AsyncMock

import pytest
from app.features.daily_operations.catalog import AREAS, install_catalog
from app.features.dashboard.models import NavItem
from test_daily_operations import grant
from test_leads import _create_employee
from test_workflow import _login


async def test_normal_startup_recovers_missing_navigation_without_employee_grants(
    client, mock_db, owner_headers, monkeypatch
):
    # Reproduce the old release path: existing app indexes/auth work, but the
    # environment has never run the optional daily-operations seed/migration.
    await mock_db.nav_items.insert_one(
        NavItem(key="leads", label="Leads", route="/leads").model_dump(exclude={"id"})
    )
    before = (await client.get("/api/v1/dashboard/nav", headers=owner_headers)).json()[
        "data"
    ]
    assert [item["key"] for item in before] == ["leads"]

    from app import main

    for name in vars(main):
        if name.startswith("ensure_") or name in {
            "initialize_voice_module",
            "close_client",
            "close_redis",
        }:
            monkeypatch.setattr(main, name, AsyncMock())
    monkeypatch.setattr(main, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(main, "get_database", lambda: mock_db)

    for _ in range(2):
        async with main.lifespan(main.create_app()):
            after = (
                await client.get("/api/v1/dashboard/nav", headers=owner_headers)
            ).json()["data"]
            assert {f"daily_{area}" for area in AREAS} <= {
                item["key"] for item in after
            }
            assert "leads" in {item["key"] for item in after}
    assert (
        await mock_db.permissions.count_documents({"module": "daily_operations"}) == 4
    )
    assert await mock_db.role_permissions.count_documents({}) == 0


async def test_employee_navigation_is_available_by_default(
    client, mock_db, owner_headers, master_data
):
    await install_catalog(mock_db)
    employee = await _create_employee(client, owner_headers, master_data)
    headers = await _login(client, "9511111111", "InitialPass1!")
    response = await client.get("/api/v1/dashboard/nav", headers=headers)
    assert {
        item["key"]
        for item in response.json()["data"]
        if item["key"].startswith("daily_")
    } == {f"daily_{area}" for area in AREAS}
    await grant(mock_db, employee, "issues", ["view"])
    response = await client.get("/api/v1/dashboard/nav", headers=headers)
    assert {
        item["key"]
        for item in response.json()["data"]
        if item["key"].startswith("daily_")
    } == {f"daily_{area}" for area in AREAS}


@pytest.mark.parametrize("area", ["follow-ups", "progress", "sessions", "issues"])
async def test_owner_can_read_all_work_areas_and_exports(
    client, mock_db, owner_headers, area
):
    await install_catalog(mock_db)
    for suffix in ("", "/export?format=csv"):
        response = await client.get(
            f"/api/v1/daily-operations/{area}{suffix}", headers=owner_headers
        )
        assert response.status_code == 200, response.text


@pytest.mark.parametrize("area", ["follow-ups", "progress", "sessions", "issues"])
async def test_employee_can_read_own_empty_views_but_uploads_are_still_validated(
    client, mock_db, owner_headers, master_data, area
):
    await install_catalog(mock_db)
    await _create_employee(client, owner_headers, master_data)
    headers = await _login(client, "9511111111", "InitialPass1!")
    for suffix in ("", "/export?format=csv"):
        response = await client.get(
            f"/api/v1/daily-operations/{area}{suffix}", headers=headers
        )
        assert response.status_code == 200, response.text
    response = await client.post(
        f"/api/v1/daily-operations/transfers/{area}/preview",
        headers=headers,
        files={"file": ("invalid.csv", b"\x00", "text/csv")},
    )
    assert response.status_code == (403 if area == "sessions" else 422), response.text
