"""Module 6C — Insurance "Policy Leads" pipeline routes.

Same gating as `loan_management.router` (`require_permission("insurance_management",
"applications", action)`). Every workflow transition is backend-validated in the service.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.core.pagination import PageParams, page_params
from app.core.response import ApiResponse, ResponseMeta
from app.features.access_control.permission_engine import require_any_permission, require_permission
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
    AddOtherDocumentRequest,
    AssignInsuranceCaseRequest,
    ChangeProductRequest,
    ConfirmOtherDocumentRequest,
    CreateManualInsuranceCaseRequest,
    HoldInsuranceCaseRequest,
    InsuranceCaseCountsResponse,
    InsuranceCaseDetailResponse,
    InsuranceCaseDocumentResponse,
    InsuranceCaseListItem,
    InsuranceLookupItem,
    InsuranceStatusUpdateRequest,
    MoveBackRequest,
    MoveToStageRequest,
    OtherDocumentResponse,
    OtherDocumentUploadUrlRequest,
    OtherDocumentUploadUrlResponse,
    PaymentHistoryResponse,
    PaymentUpdateRequest,
    PolicyLoginUpdateRequest,
    RejectCaseDocumentRequest,
    RejectInsuranceCaseRequest,
    RejectOtherDocumentRequest,
    RestartFromReEligibleRequest,
)
from app.features.insurance_management.service import InsuranceCaseService
from app.features.workflow_engine.schemas import (
    AddCaseNoteRequest,
    CaseNoteResponse,
    CaseTimelineEntryResponse,
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
    customer_map, product_map, assignee_map, assignee_channel_map = await service.resolve_names([case])
    summary = await service.required_documents_summary(case)
    applicant = await service.applicant_details(case)
    return ApiResponse[InsuranceCaseDetailResponse].ok(
        mappers.to_detail_response(
            case, customer_map.get(case.customer_id), product_map.get(case.product_id, ""),
            assignee_map.get(case.assigned_to or ""), summary, applicant,
            assignee_channel_map.get(case.assigned_to or ""),
        )
    )


# ---------------------------------------------------------------------- Customer self-service ("mine")


@router.get("/mine")
async def list_own_cases(service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep) -> ApiResponse[list[InsuranceCaseListItem]]:
    cases = await service.list_own_cases(current_user)
    customer_map, product_map, employee_map, _channel_map = await service.resolve_names(cases)
    items = [
        mappers.to_list_item(c, customer_map.get(c.customer_id), product_map.get(c.product_id, ""), employee_map.get(c.assigned_to or ""))
        for c in cases
    ]
    return ApiResponse[list[InsuranceCaseListItem]].ok(items)


@router.get("/mine/{case_id}")
async def get_own_case(case_id: str, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep) -> ApiResponse[InsuranceCaseDetailResponse]:
    return await _detail(service, case_id, current_user, own=True)


@router.get("/mine/{case_id}/other-documents")
async def list_own_other_documents(
    case_id: str, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[list[OtherDocumentResponse]]:
    docs = await service.list_other_documents_own(case_id, current_user)
    return ApiResponse[list[OtherDocumentResponse]].ok([mappers.other_document_to_response(d) for d in docs])


@router.post("/mine/{case_id}/other-documents/{doc_id}/upload-url")
async def mint_own_other_document_upload_url(
    case_id: str, doc_id: str, payload: OtherDocumentUploadUrlRequest, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[OtherDocumentUploadUrlResponse]:
    upload_url, s3_key = await service.mint_other_document_upload_url(case_id, doc_id, payload, current_user)
    return ApiResponse[OtherDocumentUploadUrlResponse].ok(OtherDocumentUploadUrlResponse(upload_url=upload_url, s3_key=s3_key))


@router.post("/mine/{case_id}/other-documents/{doc_id}/confirm")
async def confirm_own_other_document_upload(
    case_id: str, doc_id: str, payload: ConfirmOtherDocumentRequest, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[OtherDocumentResponse]:
    doc = await service.confirm_other_document_upload(case_id, doc_id, payload, current_user)
    return ApiResponse[OtherDocumentResponse].ok(mappers.other_document_to_response(doc))


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
    customer_map, product_map, employee_map, _channel_map = await service.resolve_names(cases)
    items = [
        mappers.to_list_item(c, customer_map.get(c.customer_id), product_map.get(c.product_id, ""), employee_map.get(c.assigned_to or ""))
        for c in cases
    ]
    return ApiResponse[list[InsuranceCaseListItem]].ok(items, meta=ResponseMeta(pagination=page.build_meta(total)))


@router.post("/manual")
async def create_manual_case(
    payload: CreateManualInsuranceCaseRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[InsuranceCaseDetailResponse]:
    case = await service.create_manual_case(payload, actor)
    return await _detail(service, case.require_id(), actor)


# Registered before "/{case_id}" so "counts" is never captured as a case id.
@router.get("/counts")
async def get_counts(service: ServiceDep, actor: Annotated[User, _perm("view")]) -> ApiResponse[InsuranceCaseCountsResponse]:
    return ApiResponse[InsuranceCaseCountsResponse].ok(InsuranceCaseCountsResponse(**await service.get_counts(actor)))


# "Add Insurance Lead" form pickers — staff-facing (the Customer Portal's own
# /customer/portal-* category/product reads are Customer-only). Registered before
# "/{case_id}" so "lookup" is never captured as a case id.
@router.get("/lookup/categories")
async def lookup_categories(
    service: ServiceDep, actor: Annotated[User, _perm("view")]
) -> ApiResponse[list[InsuranceLookupItem]]:
    categories = await service.lookup_insurance_categories()
    return ApiResponse[list[InsuranceLookupItem]].ok([InsuranceLookupItem(id=c.require_id(), name=c.name) for c in categories])


@router.get("/lookup/products")
async def lookup_products(
    service: ServiceDep, actor: Annotated[User, _perm("view")], insurance_category_id: str | None = None
) -> ApiResponse[list[InsuranceLookupItem]]:
    products = await service.lookup_insurance_products(insurance_category_id)
    return ApiResponse[list[InsuranceLookupItem]].ok([InsuranceLookupItem(id=p.require_id(), name=p.name) for p in products])


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
    case_id: str, payload: AssignInsuranceCaseRequest, service: ServiceDep, actor: Annotated[User, _perm("assign")]
) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.assign_case(case_id, payload.advisor_id, actor)
    return await _detail(service, case_id, actor)


@router.patch("/{case_id}/status")
async def update_status(
    case_id: str, payload: InsuranceStatusUpdateRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.update_status(case_id, payload.status, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/hold")
async def hold_case(
    case_id: str, payload: HoldInsuranceCaseRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.hold_case(case_id, payload.reason, actor, other_reason=payload.other_reason, remarks=payload.remarks)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/resume")
async def resume_case(case_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")]) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.resume_case(case_id, actor)
    return await _detail(service, case_id, actor)


# ---------------------------------------------------------------------- pipeline transitions


@router.post("/{case_id}/move-to-policy-document")
async def move_to_policy_document(
    case_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.move_to_policy_document(case_id, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/move-to-policy-login")
async def move_to_policy_login(
    case_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")], db: DbDep,
    payload: GeoCoordinatesRequest | None = None,
) -> ApiResponse[InsuranceCaseDetailResponse]:
    coords = payload or GeoCoordinatesRequest()
    await enforce_geo_fence(db, actor=actor, activity=GeoActivity.DOCUMENT_COLLECTION, latitude=coords.latitude, longitude=coords.longitude)
    await service.move_to_policy_login(case_id, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/move-to-payment")
async def move_to_payment(
    case_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.move_to_payment(case_id, actor)
    return await _detail(service, case_id, actor)


@router.patch("/{case_id}/payment")
async def update_payment(
    case_id: str, payload: PaymentUpdateRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.update_payment(case_id, payload, actor)
    return await _detail(service, case_id, actor)


@router.get("/{case_id}/payment-history")
async def get_payment_history(
    case_id: str, service: ServiceDep, actor: Annotated[User, _perm("view")]
) -> ApiResponse[PaymentHistoryResponse]:
    transactions, unrecorded = await service.payment_history(case_id, actor)
    creator_names = await service.resolve_payment_creator_names(transactions)
    return ApiResponse[PaymentHistoryResponse].ok(mappers.payment_history_to_response(transactions, creator_names, unrecorded))


@router.post("/{case_id}/move-to-policy-issued")
async def move_to_policy_issued(
    case_id: str, service: ServiceDep, actor: Annotated[User, _perm("approve")]
) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.move_to_policy_issued(case_id, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/move-back")
async def move_back(
    case_id: str, payload: MoveBackRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.move_back(case_id, payload.target, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/restart")
async def restart_from_re_eligible(
    case_id: str, payload: RestartFromReEligibleRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.restart_from_re_eligible(case_id, payload.target, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/reject")
async def reject_case(
    case_id: str, payload: RejectInsuranceCaseRequest, service: ServiceDep,
    actor: Annotated[User, require_any_permission(_MODULE, _RESOURCE, ("edit", "reject"))],
) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.reject_case(case_id, payload.reason, payload.re_eligibility, payload.re_eligible_date, actor)
    return await _detail(service, case_id, actor)


@router.patch("/{case_id}/policy-login")
async def update_policy_login(
    case_id: str, payload: PolicyLoginUpdateRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.update_policy_login(case_id, payload, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/change-product")
async def change_product(
    case_id: str, payload: ChangeProductRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.change_product(case_id, payload.product_id, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/move-to-stage")
async def move_case_to_stage(
    case_id: str, payload: MoveToStageRequest, service: ServiceDep,
    actor: Annotated[User, require_any_permission(_MODULE, _RESOURCE, ("edit", "reject"))],
) -> ApiResponse[InsuranceCaseDetailResponse]:
    await service.move_case_to_stage(
        case_id, payload.target, actor,
        reason=payload.reason, re_eligibility=payload.re_eligibility, re_eligible_date=payload.re_eligible_date,
    )
    return await _detail(service, case_id, actor)


# ---------------------------------------------------------------------- per-document actions (schema documents)


async def _document_response(
    service: InsuranceCaseService, document: Any, schema_type_ids: set[str]
) -> InsuranceCaseDocumentResponse:
    type_names = await service.resolve_document_type_names([document])
    verifier_names = await service.resolve_verifier_names([document])
    return mappers.case_document_to_response(
        document, type_names.get(document.document_type_id, ""), service.document_download_url(document),
        verifier_names.get(document.verified_by or ""), attachment_url=service.document_attachment_url(document),
        is_in_schema=document.document_type_id in schema_type_ids,
    )


@router.get("/{case_id}/documents")
async def list_case_documents(
    case_id: str, service: ServiceDep, actor: Annotated[User, _perm("view")]
) -> ApiResponse[list[InsuranceCaseDocumentResponse]]:
    documents, schema_type_ids = await service.list_case_documents(case_id, actor)
    type_names = await service.resolve_document_type_names(documents)
    verifier_names = await service.resolve_verifier_names(documents)
    items = [
        mappers.case_document_to_response(
            d, type_names.get(d.document_type_id, ""), service.document_download_url(d),
            verifier_names.get(d.verified_by or ""), attachment_url=service.document_attachment_url(d),
            is_in_schema=d.document_type_id in schema_type_ids,
        )
        for d in documents
    ]
    return ApiResponse[list[InsuranceCaseDocumentResponse]].ok(items)


@router.get("/{case_id}/documents/{document_type_id}/history")
async def case_document_history(
    case_id: str, document_type_id: str, service: ServiceDep, actor: Annotated[User, _perm("view")]
) -> ApiResponse[list[InsuranceCaseDocumentResponse]]:
    documents = await service.case_document_history(case_id, document_type_id, actor)
    type_names = await service.resolve_document_type_names(documents)
    verifier_names = await service.resolve_verifier_names(documents)
    items = [
        mappers.case_document_to_response(
            d, type_names.get(d.document_type_id, ""), service.document_download_url(d),
            verifier_names.get(d.verified_by or ""), attachment_url=service.document_attachment_url(d),
        )
        for d in documents
    ]
    return ApiResponse[list[InsuranceCaseDocumentResponse]].ok(items)


@router.post("/{case_id}/documents/{document_id}/verify")
async def verify_case_document(
    case_id: str, document_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[InsuranceCaseDocumentResponse]:
    document, schema_type_ids = await service.verify_case_document(case_id, document_id, actor)
    return ApiResponse[InsuranceCaseDocumentResponse].ok(await _document_response(service, document, schema_type_ids))


@router.post("/{case_id}/documents/{document_id}/reject")
async def reject_case_document(
    case_id: str, document_id: str, payload: RejectCaseDocumentRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[InsuranceCaseDocumentResponse]:
    document, schema_type_ids = await service.reject_case_document(case_id, document_id, payload.reason, actor)
    return ApiResponse[InsuranceCaseDocumentResponse].ok(await _document_response(service, document, schema_type_ids))


# ---------------------------------------------------------------------- "Add Other Document" (ad-hoc, per-case)


@router.get("/{case_id}/other-documents")
async def list_other_documents(
    case_id: str, service: ServiceDep, actor: Annotated[User, _perm("view")]
) -> ApiResponse[list[OtherDocumentResponse]]:
    docs = await service.list_other_documents(case_id, actor)
    return ApiResponse[list[OtherDocumentResponse]].ok(
        [
            mappers.other_document_to_response(d, service.other_document_download_url(d), service.other_document_attachment_url(d))
            for d in docs
        ]
    )


@router.post("/{case_id}/other-documents")
async def add_other_document(
    case_id: str, payload: AddOtherDocumentRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[OtherDocumentResponse]:
    doc = await service.add_other_document(case_id, payload.name, actor)
    return ApiResponse[OtherDocumentResponse].ok(mappers.other_document_to_response(doc))


@router.post("/{case_id}/other-documents/{doc_id}/upload-url")
async def staff_mint_other_document_upload_url(
    case_id: str, doc_id: str, payload: OtherDocumentUploadUrlRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[OtherDocumentUploadUrlResponse]:
    upload_url, s3_key = await service.staff_mint_other_document_upload_url(case_id, doc_id, payload, actor)
    return ApiResponse[OtherDocumentUploadUrlResponse].ok(OtherDocumentUploadUrlResponse(upload_url=upload_url, s3_key=s3_key))


@router.post("/{case_id}/other-documents/{doc_id}/confirm")
async def staff_confirm_other_document_upload(
    case_id: str, doc_id: str, payload: ConfirmOtherDocumentRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[OtherDocumentResponse]:
    doc = await service.staff_confirm_other_document_upload(case_id, doc_id, payload, actor)
    return ApiResponse[OtherDocumentResponse].ok(
        mappers.other_document_to_response(doc, service.other_document_download_url(doc), service.other_document_attachment_url(doc))
    )


@router.get("/{case_id}/other-documents/{doc_id}/history")
async def other_document_history(
    case_id: str, doc_id: str, service: ServiceDep, actor: Annotated[User, _perm("view")]
) -> ApiResponse[list[OtherDocumentResponse]]:
    docs = await service.other_document_history(case_id, doc_id, actor)
    return ApiResponse[list[OtherDocumentResponse]].ok(
        [
            mappers.other_document_to_response(d, service.other_document_download_url(d), service.other_document_attachment_url(d))
            for d in docs
        ]
    )


@router.post("/{case_id}/other-documents/{doc_id}/verify")
async def verify_other_document(
    case_id: str, doc_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[OtherDocumentResponse]:
    doc = await service.verify_other_document(case_id, doc_id, actor)
    return ApiResponse[OtherDocumentResponse].ok(
        mappers.other_document_to_response(doc, service.other_document_download_url(doc), service.other_document_attachment_url(doc))
    )


@router.post("/{case_id}/other-documents/{doc_id}/reject")
async def reject_other_document(
    case_id: str, doc_id: str, payload: RejectOtherDocumentRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[OtherDocumentResponse]:
    doc = await service.reject_other_document(case_id, doc_id, payload.reason, actor)
    return ApiResponse[OtherDocumentResponse].ok(
        mappers.other_document_to_response(doc, service.other_document_download_url(doc), service.other_document_attachment_url(doc))
    )
