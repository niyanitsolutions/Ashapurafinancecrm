"""Owner endpoints: public first-run registration (the Login page's "Create New Account"
button routes here first to decide whether an Owner still needs to be created at all —
see docs/decisions/DECISIONS.md), plus authenticated Owner Account Management (Primary
Owner creating/editing/deactivating Secondary Owners). Registration stays rate-limited
the same way the other public onboarding endpoints are (`app.middleware.rate_limit`),
reused directly; Account Management is Primary-Owner-only, enforced server-side via
`require_primary_owner` (see dependencies.py) — never by hiding buttons on the frontend.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.response import ApiResponse
from app.features.auth.dependencies import get_request_context
from app.features.auth.schemas import LoginResponse
from app.features.auth.service import RequestContext
from app.features.owner.dependencies import CurrentUserDep, get_owner_service, require_primary_owner
from app.features.owner.models import OwnerProfile
from app.features.owner.schemas import (
    CreateSecondaryOwnerRequest,
    OwnerAccountDetailResponse,
    OwnerAccountListItem,
    RegisterOwnerRequest,
    RegistrationStatusResponse,
    UpdateSecondaryOwnerRequest,
)
from app.features.owner.service import OwnerService
from app.middleware.rate_limit import rate_limited

router = APIRouter(prefix="/owner", tags=["owner"])

ServiceDep = Annotated[OwnerService, Depends(get_owner_service)]
RequestContextDep = Annotated[RequestContext, Depends(get_request_context)]


@router.get("/registration-status")
async def get_registration_status(service: ServiceDep) -> ApiResponse[RegistrationStatusResponse]:
    owner_exists = await service.registration_status()
    return ApiResponse[RegistrationStatusResponse].ok(RegistrationStatusResponse(owner_exists=owner_exists))


@router.post("/register", dependencies=[rate_limited(limit=5)])
async def register_owner(payload: RegisterOwnerRequest, service: ServiceDep, ctx: RequestContextDep) -> ApiResponse[LoginResponse]:
    session = await service.register_owner(payload, ctx)
    return ApiResponse[LoginResponse].ok(session)


# ---------------------------------------------------------------------- owner account management


@router.get("/me")
async def get_own_owner_account(service: ServiceDep, current_user: CurrentUserDep) -> ApiResponse[OwnerAccountDetailResponse]:
    """Any authenticated Owner (Primary or Secondary) reading their own record — used by
    the frontend to tell the two apart (e.g. to show/hide the Owner Management screen),
    since `role` alone is always just `"owner"` for both."""
    profile = await service.get_own_account(current_user)
    return ApiResponse[OwnerAccountDetailResponse].ok(_to_detail(profile))


@router.get("/accounts", dependencies=[Depends(require_primary_owner)])
async def list_owner_accounts(service: ServiceDep) -> ApiResponse[list[OwnerAccountListItem]]:
    profiles = await service.list_owner_accounts()
    return ApiResponse[list[OwnerAccountListItem]].ok([_to_list_item(p) for p in profiles])


@router.get("/accounts/{owner_profile_id}", dependencies=[Depends(require_primary_owner)])
async def get_owner_account(owner_profile_id: str, service: ServiceDep) -> ApiResponse[OwnerAccountDetailResponse]:
    profile = await service.get_owner_account(owner_profile_id)
    return ApiResponse[OwnerAccountDetailResponse].ok(_to_detail(profile))


@router.post("/accounts", dependencies=[Depends(require_primary_owner)])
async def create_secondary_owner(
    payload: CreateSecondaryOwnerRequest, service: ServiceDep, current_user: CurrentUserDep
) -> ApiResponse[OwnerAccountDetailResponse]:
    profile = await service.create_secondary_owner(payload, current_user)
    return ApiResponse[OwnerAccountDetailResponse].ok(_to_detail(profile))


@router.patch("/accounts/{owner_profile_id}", dependencies=[Depends(require_primary_owner)])
async def update_secondary_owner(
    owner_profile_id: str, payload: UpdateSecondaryOwnerRequest, service: ServiceDep, current_user: CurrentUserDep
) -> ApiResponse[OwnerAccountDetailResponse]:
    profile = await service.update_secondary_owner(owner_profile_id, payload, current_user)
    return ApiResponse[OwnerAccountDetailResponse].ok(_to_detail(profile))


@router.patch("/accounts/{owner_profile_id}/deactivate", dependencies=[Depends(require_primary_owner)])
async def deactivate_secondary_owner(
    owner_profile_id: str, service: ServiceDep, current_user: CurrentUserDep
) -> ApiResponse[OwnerAccountDetailResponse]:
    profile = await service.deactivate_secondary_owner(owner_profile_id, current_user)
    return ApiResponse[OwnerAccountDetailResponse].ok(_to_detail(profile))


@router.patch("/accounts/{owner_profile_id}/activate", dependencies=[Depends(require_primary_owner)])
async def activate_secondary_owner(
    owner_profile_id: str, service: ServiceDep, current_user: CurrentUserDep
) -> ApiResponse[OwnerAccountDetailResponse]:
    profile = await service.activate_secondary_owner(owner_profile_id, current_user)
    return ApiResponse[OwnerAccountDetailResponse].ok(_to_detail(profile))


def _to_list_item(profile: OwnerProfile) -> OwnerAccountListItem:
    return OwnerAccountListItem(
        id=profile.require_id(), full_name=profile.full_name, mobile=profile.mobile, email=profile.email,
        owner_type=profile.owner_type, status=profile.status, created_at=profile.created_at,
    )


def _to_detail(profile: OwnerProfile) -> OwnerAccountDetailResponse:
    return OwnerAccountDetailResponse(
        **_to_list_item(profile).model_dump(), user_id=profile.user_id, updated_at=profile.updated_at,
    )
