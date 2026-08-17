"""Public (unauthenticated) endpoints for both onboarding flows — see
docs/decisions/DECISIONS.md #046-#049. Rate-limited the same way Auth's own public
endpoints are (`app.middleware.rate_limit`), reused directly.

Authentication itself never happens here — there is exactly one login/registration
experience in this app (Auth's own /auth/login, /auth/send-otp+/auth/verify-otp+
/auth/reset-password chain, fronted by the single shared LoginPage/RegisterPage on the
frontend). A Secure Application Link only ever resolves its own status; claiming it
(linking the authenticated customer to the Lead's Application) happens via the
authenticated `claim_secure_link` endpoint in customer/router.py, not here.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.response import ApiResponse
from app.features.customer.dependencies import get_customer_service
from app.features.customer.schemas import (
    BypassVerifyMobileResponse,
    CompleteDirectRegistrationRequest,
    DirectRegisterRequest,
    OtpKickoffResponse,
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
async def start_direct_registration(payload: DirectRegisterRequest, service: ServiceDep) -> ApiResponse[OtpKickoffResponse]:
    dev_otp, bypass_available = await service.start_direct_registration(payload.mobile)
    return ApiResponse[OtpKickoffResponse].ok(OtpKickoffResponse(dev_otp=dev_otp, bypass_available=bypass_available))


# TEMPORARY — MSG91 DLT Sender ID/template approval testing bypass, customer
# self-registration only. See CustomerService.bypass_verify_registration_mobile. Remove
# this endpoint (and Settings.registration_otp_bypass) once DLT approval lands.
@router.post("/customer-registration/bypass-verify", dependencies=[rate_limited(limit=5)])
async def bypass_verify_registration_mobile(payload: DirectRegisterRequest, service: ServiceDep) -> ApiResponse[BypassVerifyMobileResponse]:
    token = await service.bypass_verify_registration_mobile(payload.mobile)
    return ApiResponse[BypassVerifyMobileResponse].ok(BypassVerifyMobileResponse(otp_verified_token=token))


@router.post("/customer-registration/complete", dependencies=[rate_limited(limit=5)])
async def complete_direct_registration(payload: CompleteDirectRegistrationRequest, service: ServiceDep) -> ApiResponse[None]:
    await service.complete_direct_registration(payload)
    return ApiResponse[None].ok()
