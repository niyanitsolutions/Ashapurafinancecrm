"""Advisor Management (Phase 2) routes.

Prefix `/advisors`. Reuses the Phase 1 permission resource
(`require_permission("insurance_management", "recruitment", action)`) — no new
permission. `view` for reads, `edit` for the agency-code / status update and for adding
a business record.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.core.pagination import PageParams, page_params
from app.core.response import ApiResponse, ResponseMeta
from app.features.access_control.permission_engine import require_permission
from app.features.auth.models import User
from app.features.recruitment import mappers
from app.features.recruitment.advisor_service import AdvisorService
from app.features.recruitment.dependencies import get_advisor_service
from app.features.recruitment.schemas import (
    AddAdvisorBusinessRequest,
    AdvisorBusinessResponse,
    AdvisorDetailResponse,
    AdvisorListItem,
    AdvisorPasswordResponse,
    UpdateAdvisorRequest,
)

router = APIRouter(prefix="/advisors", tags=["insurance-management"])

ServiceDep = Annotated[AdvisorService, Depends(get_advisor_service)]
PageParamsDep = Annotated[PageParams, Depends(page_params)]
_MODULE = "insurance_management"
_RESOURCE = "recruitment"


def _perm(action: str) -> Any:
    return require_permission(_MODULE, _RESOURCE, action)


async def _detail(service: AdvisorService, advisor_id: str) -> ApiResponse[AdvisorDetailResponse]:
    advisor, is_employee, count, premium, businesses = await service.get_advisor_detail(advisor_id)
    linked = await service.get_linked_recruitment(advisor)
    recruitment = (
        mappers.to_detail(linked[0], linked[1], linked[2], linked[3]) if linked is not None else None
    )
    return ApiResponse[AdvisorDetailResponse].ok(
        mappers.advisor_to_detail(advisor, is_employee, count, premium, businesses, recruitment)
    )


@router.get("")
async def list_advisors(
    service: ServiceDep, actor: Annotated[User, _perm("view")], page: PageParamsDep,
    channel: str | None = None, profession: str | None = None, status: str | None = None,
) -> ApiResponse[list[AdvisorListItem]]:
    """`channel` (QR / Non-QR "Type"), `profession` and `status` are independent optional
    filters — any combination is allowed; omitting one means "All"."""
    rows, total = await service.list_advisors(
        actor, channel=channel, profession=profession, status=status,
        search=page.search, skip=page.skip, limit=page.page_size, sort=page.sort,
    )
    items = [mappers.advisor_to_list_item(a, is_emp, count, premium) for a, is_emp, count, premium in rows]
    return ApiResponse[list[AdvisorListItem]].ok(items, meta=ResponseMeta(pagination=page.build_meta(total)))


@router.get("/{advisor_id}")
async def get_advisor(advisor_id: str, service: ServiceDep, _actor: Annotated[User, _perm("view")]) -> ApiResponse[AdvisorDetailResponse]:
    return await _detail(service, advisor_id)


@router.get("/{advisor_id}/password")
async def reveal_advisor_password(
    advisor_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[AdvisorPasswordResponse]:
    # `edit` (not `view`) — same, stricter-than-read gate the bank-statement document
    # password reveal uses (`CustomerService.reveal_document_password`): a view-only
    # staff member can see the masked Advisor Details page but cannot reveal a secret.
    # Never returned from `list_advisors`/`get_advisor`; every call is audited.
    password = await service.reveal_password(advisor_id, actor)
    return ApiResponse[AdvisorPasswordResponse].ok(AdvisorPasswordResponse(password=password))


@router.patch("/{advisor_id}")
async def update_advisor(
    advisor_id: str, payload: UpdateAdvisorRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[AdvisorDetailResponse]:
    await service.update_advisor(advisor_id, payload, actor)
    return await _detail(service, advisor_id)


@router.get("/{advisor_id}/business")
async def list_advisor_business(
    advisor_id: str, service: ServiceDep, _actor: Annotated[User, _perm("view")]
) -> ApiResponse[list[AdvisorBusinessResponse]]:
    businesses = await service.list_business(advisor_id)
    return ApiResponse[list[AdvisorBusinessResponse]].ok([mappers.business_to_response(b) for b in businesses])


@router.post("/{advisor_id}/business")
async def add_advisor_business(
    advisor_id: str, payload: AddAdvisorBusinessRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[AdvisorBusinessResponse]:
    business = await service.add_business(advisor_id, payload, actor)
    return ApiResponse[AdvisorBusinessResponse].ok(mappers.business_to_response(business))
