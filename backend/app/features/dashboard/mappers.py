from typing import Any

from app.features.dashboard.models import NavItem
from app.features.dashboard.schemas import NavItemResponse, WidgetResponse
from app.features.dashboard.service import ResolvedWidget


def resolved_widget_to_response(resolved: ResolvedWidget, data: dict[str, Any] | None = None) -> WidgetResponse:
    return WidgetResponse(
        key=resolved.widget.key,
        label=resolved.widget.label,
        category=resolved.widget.category,
        widget_type=resolved.widget.widget_type,
        is_visible=resolved.is_visible,
        order=resolved.order,
        refresh_interval_seconds=resolved.refresh_interval_seconds,
        is_pinned=resolved.is_pinned,
        data=data,
    )


def nav_item_to_response(item: NavItem) -> NavItemResponse:
    return NavItemResponse(key=item.key, label=item.label, route=item.route, icon=item.icon, order=item.order)
