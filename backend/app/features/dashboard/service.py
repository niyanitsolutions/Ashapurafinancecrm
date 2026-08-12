"""Module 5 — Dashboard Framework business logic: resolving a user's nav + widget layout
(catalog defaults merged with their own `DashboardLayoutPreference` rows), computing
widget data on demand, and Quick Search. No permission CRUD here — visibility is
resolved per-item via `PermissionEngine.has_permission`, reused read-only from Access
Control (Module 3), the same composition pattern every module since has used.
"""

from dataclasses import dataclass
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.constants.roles import OWNER
from app.core.exceptions import ValidationError
from app.features.access_control.permission_engine import PermissionEngine
from app.features.auth.models import User
from app.features.dashboard.models import DashboardLayoutPreference, DashboardWidget, NavItem
from app.features.dashboard.repository import (
    DashboardLayoutPreferenceRepository,
    DashboardWidgetRepository,
    NavItemRepository,
)
from app.features.dashboard.schemas import UpdateLayoutItem
from app.features.dashboard.widget_providers import compute_widget_data
from app.features.employee.repository import EmployeeRepository

_SEARCH_LIMIT = 10


@dataclass
class ResolvedWidget:
    widget: DashboardWidget
    is_visible: bool
    order: int
    refresh_interval_seconds: int
    is_pinned: bool = False


class DashboardService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self._db = db
        self._widgets = DashboardWidgetRepository(db)
        self._layout = DashboardLayoutPreferenceRepository(db)
        self._nav_items = NavItemRepository(db)
        self._employees = EmployeeRepository(db)
        self._engine = PermissionEngine(db)

    async def _is_permitted(self, user: User, *, required_module: str | None, required_resource: str | None, required_action: str | None) -> bool:
        if required_module is None:
            return True
        assert required_resource is not None and required_action is not None
        return await self._engine.has_permission(user, module=required_module, resource=required_resource, action=required_action)

    # ---------------------------------------------------------------- nav

    async def get_nav(self, user: User) -> list[NavItem]:
        items = await self._nav_items.find_many({}, limit=100, sort=[("order", 1)])
        visible = []
        for item in items:
            if item.owner_only and user.role != OWNER:
                continue
            if not await self._is_permitted(
                user, required_module=item.required_module, required_resource=item.required_resource, required_action=item.required_action
            ):
                continue
            visible.append(item)
        return visible

    # ---------------------------------------------------------------- layout

    async def get_resolved_layout(self, user: User) -> list[ResolvedWidget]:
        catalog = await self._widgets.find_many({}, limit=200, sort=[("default_order", 1)])
        prefs = {p.widget_key: p for p in await self._layout.find_for_user(user.require_id())}

        resolved: list[ResolvedWidget] = []
        for widget in catalog:
            if not await self._is_permitted(
                user, required_module=widget.required_module, required_resource=widget.required_resource, required_action=widget.required_action
            ):
                continue
            pref = prefs.get(widget.key)
            resolved.append(
                ResolvedWidget(
                    widget=widget,
                    is_visible=pref.is_visible if pref else widget.default_visible,
                    order=pref.order if pref else widget.default_order,
                    refresh_interval_seconds=pref.refresh_interval_seconds if pref else widget.default_refresh_interval_seconds,
                    is_pinned=pref.is_pinned if pref else False,
                )
            )
        resolved.sort(key=lambda r: r.order)
        return resolved

    async def update_layout(self, user: User, items: list[UpdateLayoutItem]) -> list[ResolvedWidget]:
        catalog_keys = {w.key for w in await self._widgets.find_many({}, limit=200)}
        for item in items:
            if item.widget_key not in catalog_keys:
                raise ValidationError(f"Unknown widget_key '{item.widget_key}'.")

            existing = await self._layout.find_one_for_user_widget(user.require_id(), item.widget_key)
            if existing:
                await self._layout.update(
                    existing.require_id(),
                    {
                        "is_visible": item.is_visible, "order": item.order,
                        "refresh_interval_seconds": item.refresh_interval_seconds, "is_pinned": item.is_pinned,
                    },
                    updated_by=user.require_id(),
                )
            else:
                pref = DashboardLayoutPreference(
                    user_id=user.require_id(),
                    widget_key=item.widget_key,
                    is_visible=item.is_visible,
                    order=item.order,
                    refresh_interval_seconds=item.refresh_interval_seconds,
                    is_pinned=item.is_pinned,
                    created_by=user.require_id(),
                )
                await self._layout.insert(pref)
        return await self.get_resolved_layout(user)

    async def get_dashboard(self, user: User) -> list[tuple[ResolvedWidget, dict[str, Any]]]:
        resolved = await self.get_resolved_layout(user)
        result = []
        for entry in resolved:
            if not entry.is_visible:
                continue
            data = await compute_widget_data(self._db, user, entry.widget.key)
            result.append((entry, data))
        return result

    # ---------------------------------------------------------------- notifications (framework-ready, no owning module yet)

    async def get_notifications(self, user: User, limit: int = 10) -> dict[str, Any]:
        del limit  # accepted for API shape/forward-compat; nothing to page through yet
        return await compute_widget_data(self._db, user, "notifications")

    # ---------------------------------------------------------------- quick search

    async def search(self, user: User, query: str) -> list[dict[str, Any]]:
        query = query.strip()
        if not query:
            return []

        results: list[dict[str, Any]] = []
        # Employees: only surfaced if the searcher can see employee_management:employee_records
        # (Owner always can; an Employee needs it granted — Module 2's own list/get API
        # stays require_owner-only regardless, this is Dashboard's own read path).
        if await self._is_permitted(user, required_module="employee_management", required_resource="employee_records", required_action="view"):
            employees, _ = await self._employees.search_and_filter(
                search=query, department_id=None, designation_id=None, branch_id=None, status=None,
                skip=0, limit=_SEARCH_LIMIT, sort=None,
            )
            results.extend(
                {
                    "type": "employee",
                    "id": e.require_id(),
                    "label": e.display_name,
                    "subtitle": e.employee_code,
                    "route": f"/employees/{e.require_id()}",
                }
                for e in employees
            )
        return results
