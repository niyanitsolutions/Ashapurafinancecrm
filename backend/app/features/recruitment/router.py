"""Insurance Advisor Recruitment routes.

Same gating pattern as `insurance_management.router` — `require_permission(
"insurance_management", "recruitment", action)`, no new authorization mechanism. Every
workflow transition is backend-validated in the service (frontend button visibility is
never the boundary).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.core.pagination import PageParams, page_params
from app.core.response import ApiResponse, ResponseMeta
from app.features.access_control.permission_engine import require_any_permission, require_permission
from app.features.auth.models import User
from app.features.recruitment import mappers
from app.features.recruitment.dependencies import get_recruitment_service
from app.features.recruitment.schemas import (
    AddRecruitmentNoteRequest,
    AdvisorSummaryResponse,
    AssignRecruitmentLeadRequest,
    CreateRecruitmentLeadRequest,
    LookupItem,
    RecordExaminationRequest,
    RecruitmentCountsResponse,
    RecruitmentDocumentUploadUrlRequest,
    RecruitmentDocumentUploadUrlResponse,
    RecruitmentLeadDetailResponse,
    RecruitmentLeadListItem,
    RecruitmentLookupResponse,
    RecruitmentNoteResponse,
    RecruitmentTimelineEntryResponse,
    RejectRecruitmentLeadRequest,
    SaveRecruitmentDocumentsRequest,
    UpdateRecruitmentLeadRequest,
)
from app.features.recruitment.service import RecruitmentService

router = APIRouter(prefix="/recruitment-leads", tags=["insurance-management"])

ServiceDep = Annotated[RecruitmentService, Depends(get_recruitment_service)]
PageParamsDep = Annotated[PageParams, Depends(page_params)]
_MODULE = "insurance_management"
_RESOURCE = "recruitment"


def _perm(action: str) -> Any:
    return require_permission(_MODULE, _RESOURCE, action)


async def _detail(service: RecruitmentService, lead_id: str, actor: User) -> ApiResponse[RecruitmentLeadDetailResponse]:
    lead = await service.get_lead_scoped(lead_id, actor)
    source_map, employee_map = await service.resolve_names([lead])
    return ApiResponse[RecruitmentLeadDetailResponse].ok(
        mappers.to_detail(lead, source_map.get(lead.source_id, ""), employee_map.get(lead.assigned_to or ""), service.download_url)
    )


# ---------------------------------------------------------------- lists / lookups


@router.get("")
async def list_recruitment_leads(
    service: ServiceDep, actor: Annotated[User, _perm("view")], page: PageParamsDep,
    stage: str | None = None, assigned_to: str | None = None,
) -> ApiResponse[list[RecruitmentLeadListItem]]:
    leads, total = await service.list_leads(
        actor, search=page.search, stage=stage, assigned_to=assigned_to, skip=page.skip, limit=page.page_size, sort=page.sort
    )
    source_map, employee_map = await service.resolve_names(leads)
    items = [mappers.to_list_item(lead, source_map.get(lead.source_id, ""), employee_map.get(lead.assigned_to or "")) for lead in leads]
    return ApiResponse[list[RecruitmentLeadListItem]].ok(items, meta=ResponseMeta(pagination=page.build_meta(total)))


@router.get("/counts")
async def get_recruitment_counts(service: ServiceDep, actor: Annotated[User, _perm("view")]) -> ApiResponse[RecruitmentCountsResponse]:
    return ApiResponse[RecruitmentCountsResponse].ok(RecruitmentCountsResponse(**await service.get_counts(actor)))


@router.get("/lookup")
async def get_recruitment_lookup(service: ServiceDep, actor: Annotated[User, _perm("view")]) -> ApiResponse[RecruitmentLookupResponse]:
    sources = await service.get_lookup()
    return ApiResponse[RecruitmentLookupResponse].ok(
        RecruitmentLookupResponse(sources=[LookupItem(id=s.require_id(), name=s.name) for s in sources])
    )


# ---------------------------------------------------------------- create / read / update


@router.post("")
async def create_recruitment_lead(
    payload: CreateRecruitmentLeadRequest, service: ServiceDep, actor: Annotated[User, _perm("create")]
) -> ApiResponse[RecruitmentLeadDetailResponse]:
    lead = await service.create_lead(payload, actor)
    return await _detail(service, lead.require_id(), actor)


@router.get("/{lead_id}")
async def get_recruitment_lead(lead_id: str, service: ServiceDep, actor: Annotated[User, _perm("view")]) -> ApiResponse[RecruitmentLeadDetailResponse]:
    return await _detail(service, lead_id, actor)


@router.patch("/{lead_id}")
async def update_recruitment_lead(
    lead_id: str, payload: UpdateRecruitmentLeadRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[RecruitmentLeadDetailResponse]:
    lead = await service.update_lead(lead_id, payload, actor)
    return await _detail(service, lead.require_id(), actor)


# ---------------------------------------------------------------- stage transitions


@router.post("/{lead_id}/move-to-bop")
async def move_to_bop(lead_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")]) -> ApiResponse[RecruitmentLeadDetailResponse]:
    await service.move_to_bop(lead_id, actor)
    return await _detail(service, lead_id, actor)


@router.post("/{lead_id}/back-to-fresh")
async def back_to_fresh(lead_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")]) -> ApiResponse[RecruitmentLeadDetailResponse]:
    await service.back_to_fresh(lead_id, actor)
    return await _detail(service, lead_id, actor)


@router.post("/{lead_id}/move-to-doc-collection")
async def move_to_doc_collection(
    lead_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[RecruitmentLeadDetailResponse]:
    await service.move_to_doc_collection(lead_id, actor)
    return await _detail(service, lead_id, actor)


@router.post("/{lead_id}/reject")
async def reject_recruitment_lead(
    lead_id: str, payload: RejectRecruitmentLeadRequest, service: ServiceDep,
    actor: Annotated[User, require_any_permission(_MODULE, _RESOURCE, ("edit", "approve"))],
) -> ApiResponse[RecruitmentLeadDetailResponse]:
    await service.reject(lead_id, payload.reason, actor)
    return await _detail(service, lead_id, actor)


# ---------------------------------------------------------------- documents


@router.post("/{lead_id}/documents/upload-url")
async def get_document_upload_url(
    lead_id: str, payload: RecruitmentDocumentUploadUrlRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[RecruitmentDocumentUploadUrlResponse]:
    url, s3_key = await service.generate_document_upload_url(lead_id, payload.slot, payload.file_name, payload.content_type, actor)
    return ApiResponse[RecruitmentDocumentUploadUrlResponse].ok(RecruitmentDocumentUploadUrlResponse(upload_url=url, s3_key=s3_key))


@router.put("/{lead_id}/documents")
async def save_documents(
    lead_id: str, payload: SaveRecruitmentDocumentsRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[RecruitmentLeadDetailResponse]:
    await service.save_documents(lead_id, payload, actor)
    return await _detail(service, lead_id, actor)


# ---------------------------------------------------------------- examination / advisor promotion


@router.post("/{lead_id}/examination")
async def record_examination(
    lead_id: str, payload: RecordExaminationRequest, service: ServiceDep,
    actor: Annotated[User, require_any_permission(_MODULE, _RESOURCE, ("edit", "approve"))],
) -> ApiResponse[RecruitmentLeadDetailResponse]:
    await service.record_examination(lead_id, payload, actor)
    return await _detail(service, lead_id, actor)


@router.post("/{lead_id}/move-to-advisor")
async def move_to_advisor(lead_id: str, service: ServiceDep, actor: Annotated[User, _perm("approve")]) -> ApiResponse[RecruitmentLeadDetailResponse]:
    await service.move_to_advisor(lead_id, actor)
    return await _detail(service, lead_id, actor)


@router.get("/{lead_id}/advisor")
async def get_lead_advisor(lead_id: str, service: ServiceDep, actor: Annotated[User, _perm("view")]) -> ApiResponse[AdvisorSummaryResponse | None]:
    lead = await service.get_lead_scoped(lead_id, actor)
    advisor = await service.get_advisor_for_lead(lead)
    return ApiResponse[AdvisorSummaryResponse | None].ok(mappers.advisor_to_summary(advisor) if advisor is not None else None)


# ---------------------------------------------------------------- assignment / notes / timeline


@router.post("/{lead_id}/assign")
async def assign_recruitment_lead(
    lead_id: str, payload: AssignRecruitmentLeadRequest, service: ServiceDep, actor: Annotated[User, _perm("assign")]
) -> ApiResponse[RecruitmentLeadDetailResponse]:
    await service.assign(lead_id, payload.employee_id, actor)
    return await _detail(service, lead_id, actor)


@router.get("/{lead_id}/timeline")
async def get_timeline(
    lead_id: str, service: ServiceDep, actor: Annotated[User, _perm("view")]
) -> ApiResponse[list[RecruitmentTimelineEntryResponse]]:
    entries = await service.get_timeline(lead_id, actor)
    return ApiResponse[list[RecruitmentTimelineEntryResponse]].ok(
        [mappers.timeline_entry_to_response(t, doc) for t, doc in entries]
    )


@router.post("/{lead_id}/notes")
async def add_note(
    lead_id: str, payload: AddRecruitmentNoteRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[RecruitmentNoteResponse]:
    note = await service.add_note(lead_id, payload.text, actor)
    return ApiResponse[RecruitmentNoteResponse].ok(mappers.note_to_response(note))
