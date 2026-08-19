"""Module 6C — Insurance Case processing pipeline routes. Same gating pattern as
`loan_management.router` (`require_permission("insurance_management", "applications",
action)`, no new authorization mechanism)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.core.pagination import PageParams, page_params
from app.core.response import ApiResponse, ResponseMeta
from app.features.access_control.permission_engine import require_permission
from app.features.auth.models import User
from app.features.geo_fencing.constants import GeoActivity
from app.features.geo_fencing.enforcement import enforce_geo_fence
from app.features.geo_fencing.schemas import GeoCoordinatesRequest
from app.features.insurance_management import mappers
from app.features.insurance_management.dependencies import (
    CurrentUserDep,
    CustomerDep,
    get_insurance_case_service,
)
from app.features.insurance_management.schemas import (
    GeneratePolicyRequest,
    InsuranceCaseDetailResponse,
    InsuranceCaseListItem,
    InsuranceStatusUpdateRequest,
    MedicalVerificationRequest,
    PremiumRequest,
    UnderwritingRequest,
)
from app.features.insurance_management.service import InsuranceCaseService
from app.features.workflow_engine.schemas import (
    AddCaseNoteRequest,
    AssignCaseRequest,
    CaseNoteResponse,
    CaseTimelineEntryResponse,
    HoldCaseRequest,
    RequestDocumentsRequest,
)

router = APIRouter(prefix="/insurance-cases", tags=["insurance-management"])

ServiceDep = Annotated[InsuranceCaseService, Depends(get_insurance_case_service)]
PageParamsDep = Annotated[PageParams, Depends(page_params)]
DbDep = Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]
_MODULE = "insurance_management"
_RESOURCE = "applications"


def _perm(action: str) -> Any:
    return require_permission(_MODULE, _RESOURCE, action)


async def _detail(service: InsuranceCaseService, case_id: str, actor: User, *, own: bool = False) -> ApiResponse[InsuranceCaseDetailResponse]:
    case = await (service.get_own_case(case_id, actor) if own else service.get_case(case_id, actor))
    customer_map, product_map, employee_map = await service.resolve_names([case])
    return ApiResponse[InsuranceCaseDetailResponse].ok(
        mappers.to_detail_response(case, customer_map.get(case.customer_id), product_map.get(case.product_id, ""), employee_map.get(case.assigned_to or ""))
    )


# ---------------------------------------------------------------------- Customer self-service ("mine")


@router.get("/mine")
async def list_own_cases(service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep) -> ApiResponse[list[InsuranceCaseListItem]]:
    cases = await service.list_own_cases(current_user)
    customer_map, product_map, employee_map = await service.resolve_names(cases)
    items = [
        mappers.to_list_item(c, customer_map.get(c.customer_id), product_map.get(c.product_id, ""), employee_map.get(c.assigned_to or ""))
        for c in cases
    ]
    return ApiResponse[list[InsuranceCaseListItem]].ok(items)


@router.get("/mine/{case_id}")
async def get_own_case(case_id: str, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep) -> ApiResponse[InsuranceCaseDetailResponse]:
    return await _detail(service, case_id, current_user, own=True)


@router.post("/{case_id}/premium/accept")
async def accept_premium(case_id: str, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.accept_premium(case_id, current_user)
    return await _detail(service, case_id, current_user, own=True)


@router.post("/{case_id}/premium/decline")
async def decline_premium(case_id: str, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.decline_premium(case_id, current_user)
    return await _detail(service, case_id, current_user, own=True)


# ---------------------------------------------------------------------- Staff (Owner/Employee)


@router.get("")
async def list_cases(
    service: ServiceDep, actor: Annotated[User, _perm("view")], page: PageParamsDep,
    customer_id: str | None = None, assigned_to: str | None = None, unassigned_only: bool = False, status: str | None = None,
) -> ApiResponse[list[InsuranceCaseListItem]]:
    cases, total = await service.list_cases(
        actor, search=page.search, customer_id=customer_id, assigned_to=assigned_to, unassigned_only=unassigned_only,
        status=status, skip=page.skip, limit=page.page_size, sort=page.sort,
    )
    customer_map, product_map, employee_map = await service.resolve_names(cases)
    items = [
        mappers.to_list_item(c, customer_map.get(c.customer_id), product_map.get(c.product_id, ""), employee_map.get(c.assigned_to or ""))
        for c in cases
    ]
    return ApiResponse[list[InsuranceCaseListItem]].ok(items, meta=ResponseMeta(pagination=page.build_meta(total)))


@router.get("/{case_id}")
async def get_case(case_id: str, service: ServiceDep, actor: Annotated[User, _perm("view")]) -> ApiResponse[InsuranceCaseDetailResponse]:
    return await _detail(service, case_id, actor)


@router.get("/{case_id}/timeline")
async def get_timeline(case_id: str, service: ServiceDep, actor: Annotated[User, _perm("view")]) -> ApiResponse[list[CaseTimelineEntryResponse]]:
    entries = await service.get_timeline(case_id, actor)
    return ApiResponse[list[CaseTimelineEntryResponse]].ok([mappers.timeline_entry_to_response(t, doc) for t, doc in entries])


@router.post("/{case_id}/notes")
async def add_note(case_id: str, payload: AddCaseNoteRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]) -> ApiResponse[CaseNoteResponse]:
    note = await service.add_note(case_id, payload.text, actor)
    return ApiResponse[CaseNoteResponse].ok(mappers.note_to_response(note))


@router.post("/{case_id}/assign")
async def assign_case(
    case_id: str, payload: AssignCaseRequest, service: ServiceDep, actor: Annotated[User, _perm("assign")]
) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.assign_case(case_id, payload.employee_id, actor)
    return await _detail(service, case_id, actor)


@router.patch("/{case_id}/status")
async def update_status(
    case_id: str, payload: InsuranceStatusUpdateRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.update_status(case_id, payload.status, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/hold")
async def hold_case(case_id: str, payload: HoldCaseRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.hold_case(case_id, payload.reason, actor, remarks=payload.remarks)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/resume")
async def resume_case(case_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")]) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.resume_case(case_id, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/documents/request")
async def request_documents(
    case_id: str, payload: RequestDocumentsRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.request_documents(case_id, payload.document_type_ids, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/documents/verify")
async def verify_documents(
    case_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")], db: DbDep, payload: GeoCoordinatesRequest | None = None
) -> ApiResponse[InsuranceCaseDetailResponse]:
    # Additive geo-fencing check (see app/features/geo_fencing/enforcement.py) — a no-op
    # unless an active Geo Fence is configured for document_collection, so existing
    # callers that send no body (or one with no coordinates) are unaffected.
    coords = payload or GeoCoordinatesRequest()
    await enforce_geo_fence(db, actor=actor, activity=GeoActivity.DOCUMENT_COLLECTION, latitude=coords.latitude, longitude=coords.longitude)
    await service.verify_documents(case_id, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/underwriting")
async def underwriting(
    case_id: str, payload: UnderwritingRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.underwriting(case_id, payload, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/medical-verification")
async def medical_verification(
    case_id: str, payload: MedicalVerificationRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.medical_verification(case_id, payload, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/premium")
async def record_premium(
    case_id: str, payload: PremiumRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.record_premium(case_id, payload, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/policy/generate")
async def generate_policy(
    case_id: str, payload: GeneratePolicyRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.generate_policy(case_id, payload, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/policy/issue")
async def issue_policy(case_id: str, service: ServiceDep, actor: Annotated[User, _perm("approve")]) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.issue_policy(case_id, actor)
    return await _detail(service, case_id, actor)
