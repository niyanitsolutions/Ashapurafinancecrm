from typing import Any

from pydantic import BaseModel, Field


class WidgetResponse(BaseModel):
    key: str
    label: str
    category: str
    widget_type: str
    is_visible: bool
    order: int
    refresh_interval_seconds: int
    is_pinned: bool = False
    data: dict[str, Any] | None = None  # populated on /dashboard, omitted on /dashboard/layout


class UpdateLayoutItem(BaseModel):
    widget_key: str
    is_visible: bool = True
    order: int = 0
    refresh_interval_seconds: int = Field(default=300, ge=10, le=3600)
    is_pinned: bool = False


class UpdateLayoutRequest(BaseModel):
    widgets: list[UpdateLayoutItem]


class NavItemResponse(BaseModel):
    key: str
    label: str
    route: str
    icon: str | None
    order: int


class NotificationsResponse(BaseModel):
    available: bool
    items: list[dict[str, Any]]
    unread_count: int = 0


class SearchResultItem(BaseModel):
    customer_code: str | None = None
    customer_name: str | None = None
    mobile: str | None = None
    product_name: str | None = None
    status: str | None = None
    assigned_to_name: str | None = None
    employee_code: str | None = None
    designation: str | None = None
    type: str
    id: str
    label: str
    subtitle: str | None
    route: str


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
