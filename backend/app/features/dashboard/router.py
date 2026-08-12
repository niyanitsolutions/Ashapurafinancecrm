from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.response import ApiResponse
from app.features.dashboard import mappers
from app.features.dashboard.dependencies import CurrentUserDep, get_dashboard_service
from app.features.dashboard.schemas import (
    NavItemResponse,
    NotificationsResponse,
    SearchResponse,
    SearchResultItem,
    UpdateLayoutRequest,
    WidgetResponse,
)
from app.features.dashboard.service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

ServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]


@router.get("/nav")
async def get_nav(service: ServiceDep, current_user: CurrentUserDep) -> ApiResponse[list[NavItemResponse]]:
    items = await service.get_nav(current_user)
    return ApiResponse[list[NavItemResponse]].ok([mappers.nav_item_to_response(i) for i in items])


@router.get("/layout")
async def get_layout(service: ServiceDep, current_user: CurrentUserDep) -> ApiResponse[list[WidgetResponse]]:
    resolved = await service.get_resolved_layout(current_user)
    return ApiResponse[list[WidgetResponse]].ok([mappers.resolved_widget_to_response(r) for r in resolved])


@router.put("/layout")
async def update_layout(payload: UpdateLayoutRequest, service: ServiceDep, current_user: CurrentUserDep) -> ApiResponse[list[WidgetResponse]]:
    resolved = await service.update_layout(current_user, payload.widgets)
    return ApiResponse[list[WidgetResponse]].ok([mappers.resolved_widget_to_response(r) for r in resolved])


@router.get("")
async def get_dashboard(service: ServiceDep, current_user: CurrentUserDep) -> ApiResponse[list[WidgetResponse]]:
    widgets_with_data = await service.get_dashboard(current_user)
    return ApiResponse[list[WidgetResponse]].ok([mappers.resolved_widget_to_response(r, data) for r, data in widgets_with_data])


@router.get("/notifications")
async def get_notifications(service: ServiceDep, current_user: CurrentUserDep) -> ApiResponse[NotificationsResponse]:
    data = await service.get_notifications(current_user)
    return ApiResponse[NotificationsResponse].ok(NotificationsResponse(**data))


@router.get("/search")
async def search(
    service: ServiceDep, current_user: CurrentUserDep, q: Annotated[str, Query(min_length=1)]
) -> ApiResponse[SearchResponse]:
    results = await service.search(current_user, q)
    return ApiResponse[SearchResponse].ok(SearchResponse(results=[SearchResultItem(**r) for r in results]))
