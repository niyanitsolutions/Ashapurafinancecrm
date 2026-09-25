from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.core.pagination import PageParams, page_params
from app.core.response import ApiResponse, ResponseMeta
from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.insurance_management.analytics_schemas import (
    AdvisorAnalyticsRow,
    AdvisorWorkAnalytics,
    InsuranceAnalyticsOverview,
    ProductAnalyticsRow,
    ProductWorkAnalytics,
)
from app.features.insurance_management.analytics_service import InsuranceAnalyticsService

router = APIRouter(prefix="/insurance-analytics", tags=["insurance-management"])


def get_analytics_service(
    db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)],
) -> InsuranceAnalyticsService:
    return InsuranceAnalyticsService(db)


ServiceDep = Annotated[InsuranceAnalyticsService, Depends(get_analytics_service)]
ActorDep = Annotated[User, Depends(get_current_active_user)]
PageDep = Annotated[PageParams, Depends(page_params)]


@router.get("/overview")
async def overview(
    service: ServiceDep,
    actor: ActorDep,
    date_from: date | None = None,
    date_to: date | None = None,
    advisor_id: str | None = None,
    product_id: str | None = None,
    stage: str | None = None,
) -> ApiResponse[InsuranceAnalyticsOverview]:
    return ApiResponse[InsuranceAnalyticsOverview].ok(
        await service.overview(
            actor,
            date_from=date_from,
            date_to=date_to,
            advisor_id=advisor_id,
            product_id=product_id,
            stage=stage,
        )
    )


@router.get("/advisors")
async def advisors(
    service: ServiceDep,
    actor: ActorDep,
    page: PageDep,
    date_from: date | None = None,
    date_to: date | None = None,
    advisor_id: str | None = None,
) -> ApiResponse[list[AdvisorAnalyticsRow]]:
    items, total = await service.advisors(
        actor,
        date_from=date_from,
        date_to=date_to,
        advisor_id=advisor_id,
        skip=page.skip,
        limit=page.page_size,
    )
    return ApiResponse[list[AdvisorAnalyticsRow]].ok(
        items, meta=ResponseMeta(pagination=page.build_meta(total))
    )


@router.get("/advisors/{advisor_id}")
async def advisor_work(
    advisor_id: str,
    service: ServiceDep,
    actor: ActorDep,
    page: PageDep,
    date_from: date | None = None,
    date_to: date | None = None,
) -> ApiResponse[AdvisorWorkAnalytics]:
    item, total = await service.advisor_work(
        actor,
        advisor_id,
        date_from=date_from,
        date_to=date_to,
        skip=page.skip,
        limit=page.page_size,
    )
    return ApiResponse[AdvisorWorkAnalytics].ok(
        item, meta=ResponseMeta(pagination=page.build_meta(total))
    )


@router.get("/products")
async def products(
    service: ServiceDep,
    actor: ActorDep,
    page: PageDep,
    date_from: date | None = None,
    date_to: date | None = None,
    advisor_id: str | None = None,
    product_id: str | None = None,
    stage: str | None = None,
) -> ApiResponse[list[ProductAnalyticsRow]]:
    items, total = await service.products(
        actor,
        date_from=date_from,
        date_to=date_to,
        advisor_id=advisor_id,
        product_id=product_id,
        stage=stage,
        skip=page.skip,
        limit=page.page_size,
    )
    return ApiResponse[list[ProductAnalyticsRow]].ok(
        items, meta=ResponseMeta(pagination=page.build_meta(total))
    )


@router.get("/products/{product_id}")
async def product_work(
    product_id: str,
    service: ServiceDep,
    actor: ActorDep,
    page: PageDep,
    date_from: date | None = None,
    date_to: date | None = None,
    advisor_id: str | None = None,
    stage: str | None = None,
) -> ApiResponse[ProductWorkAnalytics]:
    item, total = await service.product_work(
        actor,
        product_id,
        date_from=date_from,
        date_to=date_to,
        advisor_id=advisor_id,
        stage=stage,
        skip=page.skip,
        limit=page.page_size,
    )
    return ApiResponse[ProductWorkAnalytics].ok(
        item, meta=ResponseMeta(pagination=page.build_meta(total))
    )
