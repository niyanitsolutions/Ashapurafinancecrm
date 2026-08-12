"""Module 5 — Dashboard Framework domain models.

`DashboardWidget`/`NavItem` are a *catalog*, not Owner-CRUD-able data like Access
Control's Permission catalog — each entry needs actual backend code (a data provider /
a real route) to mean anything, so they're seeded once via `scripts/seed.py`, not
created through the API. What IS user-editable is `DashboardLayoutPreference` — per-user
visibility/order/refresh-interval, the actual "configurable" part of the brief.
"""

from pydantic import Field

from app.features.dashboard.constants import WidgetType
from app.shared.base_document import BaseDocument


class DashboardWidget(BaseDocument):
    key: str  # unique, e.g. "today_leads" — also the WIDGET_PROVIDERS registry key
    label: str
    category: str  # free text grouping for UI, e.g. "leads", "loans", "team", "system"
    widget_type: str = Field(pattern=f"^({'|'.join(WidgetType.ALL)})$")
    # Permission gate — if required_module is None, any authenticated Owner/Employee sees
    # it. If set, resolved via PermissionEngine.has_permission (Owner always bypasses).
    required_module: str | None = None
    required_resource: str | None = None
    required_action: str | None = None
    default_order: int = 0
    default_visible: bool = True
    default_refresh_interval_seconds: int = 300
    # BaseDocument.status: "active"/"inactive" — an inactive widget is hidden system-wide
    # regardless of any user's layout preference (e.g. to retire one without deleting it).


class DashboardLayoutPreference(BaseDocument):
    user_id: str
    widget_key: str
    is_visible: bool = True
    order: int = 0
    refresh_interval_seconds: int = 300
    # Phase 4.1 — "pin to top", purely a per-user display preference like everything
    # else on this model; never touches permissions/visibility eligibility (that's
    # still decided by `required_module`/`resource`/`action` on the catalog row).
    is_pinned: bool = False


class NavItem(BaseDocument):
    key: str  # unique
    label: str
    route: str
    icon: str | None = None  # opaque identifier string — frontend owns the icon mapping
    order: int = 0
    # Gate must mirror how the target route is ACTUALLY protected (require_owner vs.
    # require_permission) — see decision 033. Both may be set: owner_only=True bypasses
    # the module/resource/action check entirely (Owner always passes it anyway).
    owner_only: bool = False
    required_module: str | None = None
    required_resource: str | None = None
    required_action: str | None = None
