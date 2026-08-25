"""Module 6C — Loan Case processing pipeline routes.

Every staff action is gated with `Depends(require_permission("loan_management",
"applications", action))` (Access Control, Module 3) — no new authorization mechanism,
per the brief. `resource="applications"` (not "cases") deliberately matches the exact
name Dashboard's own "Disbursed"/"Rejected" widget catalog rows already reference
(decision 032/044's forward-compatibility pattern) so those widgets become grantable
with zero Dashboard code changes.
"""

from datetime import date
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
from app.features.loan_management import mappers
from app.features.loan_management.dependencies import (
    CurrentUserDep,
    CustomerDep,
    get_loan_case_service,
)
from app.features.loan_management.schemas import (
    AdditionalDocumentRequest,
    AdditionalDocumentResponse,
    AdditionalDocumentUploadUrlRequest,
    AdditionalDocumentUploadUrlResponse,
    BankOfferRequest,
    BankOfferResponse,
    CaseRemarksRequest,
    ConfirmAdditionalDocumentRequest,
    CreditEvaluationRequest,
    CustomerBankOfferResponse,
    DisbursementItem,
    DisbursementListResponse,
    DisburseRequest,
    EsignNachKycRequest,
    FinalEvaluationRequest,
    LoanCaseCountsResponse,
    LoanCaseDetailResponse,
    LoanCaseListItem,
    LoanStatusUpdateRequest,
    NewCustomerDetailsRequest,
    RejectAdditionalDocumentRequest,
    RvOvRefRequest,
)
from app.features.loan_management.service import LoanCaseService
from app.features.workflow_engine.schemas import (
    AddCaseNoteRequest,
    AssignCaseRequest,
    CaseNoteResponse,
    CaseTimelineEntryResponse,
    HoldCaseRequest,
    RequestDocumentsRequest,
)

router = APIRouter(prefix="/loan-cases", tags=["loan-management"])

ServiceDep = Annotated[LoanCaseService, Depends(get_loan_case_service)]
PageParamsDep = Annotated[PageParams, Depends(page_params)]
DbDep = Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]
_MODULE = "loan_management"
_RESOURCE = "applications"


def _perm(action: str) -> Any:
    return require_permission(_MODULE, _RESOURCE, action)


async def _detail(service: LoanCaseService, case_id: str, actor: User, *, own: bool = False) -> ApiResponse[LoanCaseDetailResponse]:
    case = await (service.get_own_case(case_id, actor) if own else service.get_case(case_id, actor))
    customer_map, product_map, employee_map = await service.resolve_names([case])
    transitions = await service.status_transition_map()
    previous = await service.previous_status_map()
    # Requirement 21's full customer/application/bank_offers block is staff-only — the
    # customer path must NEVER see `BankOfferResponse`'s staff-only fields (decision,
    # assigned_officer, internal remarks, bank_application_id, reference_number). A
    # customer already has trimmed, dedicated endpoints for their own offers
    # (`/mine/{case_id}/bank-offers` -> `CustomerBankOfferResponse`); this block simply
    # stays empty on their own detail response rather than risk ever leaking it.
    customer = application = None
    bank_offers: list[Any] = []
    if not own:
        customer, application, bank_offers = await service.get_case_context(case)
    return ApiResponse[LoanCaseDetailResponse].ok(
        mappers.to_detail_response(
            case, customer_map.get(case.customer_id), product_map.get(case.product_id, ""), employee_map.get(case.assigned_to or ""),
            transitions.get(case.current_status), allowed_previous_statuses=previous.get(case.current_status),
            customer=customer, application=application, bank_offers=bank_offers,
        )
    )


# ---------------------------------------------------------------------- Customer self-service ("mine")


@router.get("/mine")
async def list_own_cases(service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep) -> ApiResponse[list[LoanCaseListItem]]:
    cases = await service.list_own_cases(current_user)
    customer_map, product_map, employee_map = await service.resolve_names(cases)
    transitions = await service.status_transition_map()
    items = [
        mappers.to_list_item(
            c, customer_map.get(c.customer_id), product_map.get(c.product_id, ""), employee_map.get(c.assigned_to or ""),
            transitions.get(c.current_status),
        )
        for c in cases
    ]
    return ApiResponse[list[LoanCaseListItem]].ok(items)


@router.get("/mine/{case_id}")
async def get_own_case(case_id: str, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep) -> ApiResponse[LoanCaseDetailResponse]:
    return await _detail(service, case_id, current_user, own=True)


@router.get("/mine/{case_id}/bank-offers")
async def list_own_bank_offers(
    case_id: str, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[list[CustomerBankOfferResponse]]:
    offers = await service.list_bank_offers_own(case_id, current_user)
    return ApiResponse[list[CustomerBankOfferResponse]].ok([mappers.bank_offer_to_customer_response(o) for o in offers])


@router.post("/mine/{case_id}/bank-offers/{offer_id}/select")
async def select_own_bank_offer(
    case_id: str, offer_id: str, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[LoanCaseDetailResponse]:
    await service.select_bank_offer_as_customer(case_id, offer_id, current_user)
    return await _detail(service, case_id, current_user, own=True)


@router.post("/mine/{case_id}/offer-acceptance/confirm")
async def confirm_own_offer_acceptance(
    case_id: str, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[LoanCaseDetailResponse]:
    await service.confirm_offer_acceptance_as_customer(case_id, current_user)
    return await _detail(service, case_id, current_user, own=True)


@router.get("/mine/{case_id}/additional-documents")
async def list_own_additional_documents(
    case_id: str, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[list[AdditionalDocumentResponse]]:
    docs = await service.list_additional_documents_own(case_id, current_user)
    return ApiResponse[list[AdditionalDocumentResponse]].ok([mappers.additional_document_to_response(d) for d in docs])


@router.post("/mine/{case_id}/additional-documents/{doc_id}/upload-url")
async def mint_own_additional_document_upload_url(
    case_id: str, doc_id: str, payload: AdditionalDocumentUploadUrlRequest, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[AdditionalDocumentUploadUrlResponse]:
    upload_url, s3_key = await service.mint_additional_document_upload_url(case_id, doc_id, payload, current_user)
    return ApiResponse[AdditionalDocumentUploadUrlResponse].ok(AdditionalDocumentUploadUrlResponse(upload_url=upload_url, s3_key=s3_key))


@router.post("/mine/{case_id}/additional-documents/{doc_id}/confirm")
async def confirm_own_additional_document_upload(
    case_id: str, doc_id: str, payload: ConfirmAdditionalDocumentRequest, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[AdditionalDocumentResponse]:
    doc = await service.confirm_additional_document_upload(case_id, doc_id, payload, current_user)
    return ApiResponse[AdditionalDocumentResponse].ok(mappers.additional_document_to_response(doc))


# ---------------------------------------------------------------------- Staff (Owner/Employee)


@router.get("")
async def list_cases(
    service: ServiceDep, actor: Annotated[User, _perm("view")], page: PageParamsDep,
    customer_id: str | None = None, assigned_to: str | None = None, unassigned_only: bool = False, status: str | None = None,
) -> ApiResponse[list[LoanCaseListItem]]:
    cases, total = await service.list_cases(
        actor, search=page.search, customer_id=customer_id, assigned_to=assigned_to, unassigned_only=unassigned_only,
        status=status, skip=page.skip, limit=page.page_size, sort=page.sort,
    )
    customer_map, product_map, employee_map = await service.resolve_names(cases)
    transitions = await service.status_transition_map()
    items = [
        mappers.to_list_item(
            c, customer_map.get(c.customer_id), product_map.get(c.product_id, ""), employee_map.get(c.assigned_to or ""),
            transitions.get(c.current_status),
        )
        for c in cases
    ]
    return ApiResponse[list[LoanCaseListItem]].ok(items, meta=ResponseMeta(pagination=page.build_meta(total)))


@router.get("/counts")
async def get_counts(service: ServiceDep, actor: Annotated[User, _perm("view")]) -> ApiResponse[LoanCaseCountsResponse]:
    # Registered before "/{case_id}" so "counts" is never captured as a case_id.
    counts = await service.get_counts(actor)
    return ApiResponse[LoanCaseCountsResponse].ok(LoanCaseCountsResponse(**counts))


@router.get("/disbursements")
async def list_disbursements(
    service: ServiceDep, actor: Annotated[User, _perm("view")],
    page: PageParamsDep,
    date_from: date | None = None, date_to: date | None = None, product_id: str | None = None, search: str | None = None,
) -> ApiResponse[DisbursementListResponse]:
    # Registered before "/{case_id}" for the same reason as "/counts" above. Date-preset
    # (This Week/Month/Quarter/Year/Custom) resolution to concrete date_from/date_to is a
    # frontend concern — the backend only ever sees plain calendar dates, same shape as
    # every other date-filtered report in this codebase.
    items, total_count, total_amount = await service.list_disbursements(
        actor, date_from=date_from, date_to=date_to, product_id=product_id, search=search, skip=page.skip, limit=page.page_size,
    )
    customer_map, product_map, _employee_map = await service.resolve_names(items)
    disbursement_items = [
        DisbursementItem(
            id=c.require_id(), case_code=c.case_code, customer_name=customer_map.get(c.customer_id), product_name=product_map.get(c.product_id, ""),
            approved_amount=c.loan_details.offered_amount if c.loan_details else None,
            disbursed_amount=c.loan_details.disbursed_amount if c.loan_details else None,
            disbursed_reference=c.loan_details.disbursed_reference if c.loan_details else None,
            disbursed_at=c.loan_details.disbursed_at if c.loan_details else None,
        )
        for c in items
    ]
    return ApiResponse[DisbursementListResponse].ok(
        DisbursementListResponse(items=disbursement_items, total_count=total_count, total_amount=total_amount),
        meta=ResponseMeta(pagination=page.build_meta(total_count)),
    )


@router.get("/{case_id}")
async def get_case(case_id: str, service: ServiceDep, actor: Annotated[User, _perm("view")]) -> ApiResponse[LoanCaseDetailResponse]:
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
) -> ApiResponse[LoanCaseDetailResponse]:
    await service.assign_case(case_id, payload.employee_id, actor)
    return await _detail(service, case_id, actor)


@router.patch("/{case_id}/status")
async def update_status(
    case_id: str, payload: LoanStatusUpdateRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[LoanCaseDetailResponse]:
    await service.update_status(case_id, payload.status, actor, remarks=payload.remarks)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/hold")
async def hold_case(case_id: str, payload: HoldCaseRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]) -> ApiResponse[LoanCaseDetailResponse]:
    await service.hold_case(case_id, payload.reason, actor, remarks=payload.remarks)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/resume")
async def resume_case(case_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")]) -> ApiResponse[LoanCaseDetailResponse]:
    await service.resume_case(case_id, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/documents/request")
async def request_documents(
    case_id: str, payload: RequestDocumentsRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[LoanCaseDetailResponse]:
    await service.request_documents(case_id, payload.document_type_ids, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/documents/verify")
async def verify_documents(
    case_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")], db: DbDep, payload: GeoCoordinatesRequest | None = None
) -> ApiResponse[LoanCaseDetailResponse]:
    # Additive geo-fencing check (see app/features/geo_fencing/enforcement.py) — a no-op
    # unless an active Geo Fence is configured for document_collection, so existing
    # callers that send no body (or one with no coordinates) are unaffected.
    coords = payload or GeoCoordinatesRequest()
    await enforce_geo_fence(db, actor=actor, activity=GeoActivity.DOCUMENT_COLLECTION, latitude=coords.latitude, longitude=coords.longitude)
    await service.verify_documents(case_id, actor)
    return await _detail(service, case_id, actor)


@router.get("/{case_id}/additional-documents")
async def list_additional_documents(
    case_id: str, service: ServiceDep, actor: Annotated[User, _perm("view")]
) -> ApiResponse[list[AdditionalDocumentResponse]]:
    docs = await service.list_additional_documents(case_id, actor)
    return ApiResponse[list[AdditionalDocumentResponse]].ok(
        [mappers.additional_document_to_response(d, service.additional_document_download_url(d), service.additional_document_attachment_url(d)) for d in docs]
    )


@router.post("/{case_id}/additional-documents")
async def add_additional_document(
    case_id: str, payload: AdditionalDocumentRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[AdditionalDocumentResponse]:
    doc = await service.add_additional_document(case_id, payload.name, actor)
    return ApiResponse[AdditionalDocumentResponse].ok(mappers.additional_document_to_response(doc))


@router.post("/{case_id}/additional-documents/{doc_id}/verify")
async def verify_additional_document(
    case_id: str, doc_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[AdditionalDocumentResponse]:
    doc = await service.verify_additional_document(case_id, doc_id, actor)
    return ApiResponse[AdditionalDocumentResponse].ok(mappers.additional_document_to_response(doc))


@router.post("/{case_id}/additional-documents/{doc_id}/reject")
async def reject_additional_document(
    case_id: str, doc_id: str, payload: RejectAdditionalDocumentRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[AdditionalDocumentResponse]:
    doc = await service.reject_additional_document(case_id, doc_id, payload.reason, actor)
    return ApiResponse[AdditionalDocumentResponse].ok(mappers.additional_document_to_response(doc))


@router.post("/{case_id}/new-customer-details")
async def record_new_customer_details(
    case_id: str, payload: NewCustomerDetailsRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[LoanCaseDetailResponse]:
    # Kept for backward compatibility with any existing caller of the old single-slot
    # New Customer form — the current frontend instead captures bank/NBFC records via
    # the bank-offers endpoints below and calls move_to_credit_evaluation to advance.
    await service.record_new_customer_details(case_id, payload, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/move-to-credit-evaluation")
async def move_to_credit_evaluation(
    case_id: str, payload: CaseRemarksRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[LoanCaseDetailResponse]:
    await service.move_to_credit_evaluation(case_id, actor, remarks=payload.remarks)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/move-back")
async def move_back(
    case_id: str, payload: CaseRemarksRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[LoanCaseDetailResponse]:
    await service.move_back(case_id, actor, remarks=payload.remarks)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/credit-evaluation")
async def credit_evaluation(
    case_id: str, payload: CreditEvaluationRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[LoanCaseDetailResponse]:
    await service.credit_evaluation(case_id, payload, actor)
    return await _detail(service, case_id, actor)


@router.get("/{case_id}/bank-offers")
async def list_bank_offers(case_id: str, service: ServiceDep, actor: Annotated[User, _perm("view")]) -> ApiResponse[list[BankOfferResponse]]:
    offers = await service.list_bank_offers(case_id, actor)
    return ApiResponse[list[BankOfferResponse]].ok([mappers.bank_offer_to_response(o) for o in offers])


@router.post("/{case_id}/bank-offers")
async def add_bank_offer(
    case_id: str, payload: BankOfferRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[BankOfferResponse]:
    offer = await service.add_bank_offer(case_id, payload, actor)
    return ApiResponse[BankOfferResponse].ok(mappers.bank_offer_to_response(offer))


@router.patch("/{case_id}/bank-offers/{offer_id}")
async def update_bank_offer(
    case_id: str, offer_id: str, payload: BankOfferRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[BankOfferResponse]:
    offer = await service.update_bank_offer(case_id, offer_id, payload, actor)
    return ApiResponse[BankOfferResponse].ok(mappers.bank_offer_to_response(offer))


@router.delete("/{case_id}/bank-offers/{offer_id}")
async def delete_bank_offer(case_id: str, offer_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")]) -> ApiResponse[None]:
    await service.delete_bank_offer(case_id, offer_id, actor)
    return ApiResponse[None].ok(None)


@router.post("/{case_id}/bank-offers/{offer_id}/select")
async def select_bank_offer(
    case_id: str, offer_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[LoanCaseDetailResponse]:
    await service.select_bank_offer(case_id, offer_id, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/offer-acceptance/confirm")
async def confirm_offer_acceptance(
    case_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[LoanCaseDetailResponse]:
    await service.confirm_offer_acceptance(case_id, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/rv-ov-ref")
async def record_rv_ov_ref(
    case_id: str, payload: RvOvRefRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[LoanCaseDetailResponse]:
    await service.record_rv_ov_ref(case_id, payload, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/esign-nach-kyc")
async def record_esign_nach_kyc(
    case_id: str, payload: EsignNachKycRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[LoanCaseDetailResponse]:
    await service.record_esign_nach_kyc(case_id, payload, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/final-evaluation")
async def final_evaluation(
    case_id: str, payload: FinalEvaluationRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[LoanCaseDetailResponse]:
    await service.final_evaluation(case_id, payload, actor)
    return await _detail(service, case_id, actor)


@router.post("/{case_id}/disburse")
async def disburse(case_id: str, payload: DisburseRequest, service: ServiceDep, actor: Annotated[User, _perm("approve")]) -> ApiResponse[LoanCaseDetailResponse]:
    await service.disburse(case_id, payload, actor)
    return await _detail(service, case_id, actor)
