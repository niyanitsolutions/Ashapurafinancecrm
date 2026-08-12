"""Public (unauthenticated) endpoints for Owner first-run registration — the Login page's
"Create New Account" button routes here first to decide whether an Owner still needs to
be created at all (see docs/decisions/DECISIONS.md). Rate-limited the same way the other
public onboarding endpoints are (`app.middleware.rate_limit`), reused directly.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.response import ApiResponse
from app.features.auth.dependencies import get_request_context
from app.features.auth.schemas import LoginResponse
from app.features.auth.service import RequestContext
from app.features.owner.dependencies import get_owner_service
from app.features.owner.schemas import RegisterOwnerRequest, RegistrationStatusResponse
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
