"""Public customer registration and secure-link resolution.

Registration composes Auth's shared purpose-bound PIN OTP challenges and creates
no account until verified completion. Secure links retain their existing flow.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.core.response import ApiResponse
from app.features.auth.dependencies import get_request_context
from app.features.auth.service import RequestContext
from app.features.customer.dependencies import get_customer_service
from app.features.customer.schemas import (
    CompleteDirectRegistrationRequest,
    DirectRegisterRequest,
    ResolveSecureLinkResponse,
)
from app.features.customer.service import CustomerService
from app.middleware.rate_limit import rate_limited

router = APIRouter(tags=["customer-onboarding-public"])

ServiceDep = Annotated[CustomerService, Depends(get_customer_service)]


@router.get("/secure-links/{secure_code}", dependencies=[rate_limited(limit=20)])
async def resolve_secure_link(secure_code: str, service: ServiceDep) -> ApiResponse[ResolveSecureLinkResponse]:
    status = await service.get_secure_link_public_status(secure_code)
    return ApiResponse[ResolveSecureLinkResponse].ok(ResolveSecureLinkResponse(**status))


@router.post("/customer-registration/start", dependencies=[rate_limited(limit=5)])
async def start_direct_registration(
    payload: DirectRegisterRequest, service: ServiceDep,
    ctx: Annotated[RequestContext, Depends(get_request_context)],
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse.ok(await service.start_direct_registration(payload, ctx))


@router.post("/customer-registration/complete", dependencies=[rate_limited(limit=5)])
async def complete_direct_registration(payload: CompleteDirectRegistrationRequest, service: ServiceDep) -> ApiResponse[None]:
    await service.complete_direct_registration(payload)
    return ApiResponse[None].ok()
