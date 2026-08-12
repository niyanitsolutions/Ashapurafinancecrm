from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response

from app.core.pagination import PageParams, page_params
from app.core.response import ApiResponse, ResponseMeta
from app.features.access_control.permission_engine import require_permission
from app.features.auth.models import User
from app.features.leads import mappers
from app.features.leads.dependencies import get_lead_service
from app.features.leads.schemas import (
    AddNoteRequest,
    AssignLeadRequest,
    CreateLeadRequest,
    DuplicateCheckResponse,
    EligibleAssigneeResponse,
    LeadDetailResponse,
    LeadListItem,
    NoteResponse,
    TimelineEntryResponse,
    UpdateLeadRequest,
)
from app.features.leads.service import LeadService

router = APIRouter(prefix="/leads", tags=["leads"])

ServiceDep = Annotated[LeadService, Depends(get_lead_service)]
PageParamsDep = Annotated[PageParams, Depends(page_params)]
_MODULE = "leads"
_RESOURCE = "leads"


def _perm(action: str) -> Any:
    return require_permission(_MODULE, _RESOURCE, action)


@router.get("")
async def list_leads(
    service: ServiceDep,
    actor: Annotated[User, _perm("view")],
    page: PageParamsDep,
    source_id: str | None = None,
    product_category: str | None = None,
    product_id: str | None = None,
    assigned_to: str | None = None,
    status: str | None = None,
) -> ApiResponse[list[LeadListItem]]:
    leads, total = await service.list_leads(
        search=page.search, source_id=source_id, product_category=product_category, product_id=product_id,
        assigned_to=assigned_to, status=status, skip=page.skip, limit=page.page_size, sort=page.sort, actor=actor,
    )
    source_map, product_map, employee_map = await service.resolve_names(leads)
    items = [
        mappers.to_list_item(lead, source_map.get(lead.source_id, ""), product_map.get(lead.product_id, ""), employee_map.get(lead.assigned_to or "", None))
        for lead in leads
    ]
    return ApiResponse[list[LeadListItem]].ok(items, meta=ResponseMeta(pagination=page.build_meta(total)))


@router.get("/export")
async def export_leads(service: ServiceDep, actor: Annotated[User, _perm("export")]) -> Response:
    csv_content = await service.export_leads_csv(actor)
    return Response(content=csv_content, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=leads.csv"})


@router.get("/check-duplicate")
async def check_duplicate(service: ServiceDep, actor: Annotated[User, _perm("view")], mobile: str) -> ApiResponse[DuplicateCheckResponse]:
    matches = await service.check_duplicate(mobile, actor)
    source_map, product_map, employee_map = await service.resolve_names(matches)
    items = [
        mappers.to_list_item(lead, source_map.get(lead.source_id, ""), product_map.get(lead.product_id, ""), employee_map.get(lead.assigned_to or "", None))
        for lead in matches
    ]
    return ApiResponse[DuplicateCheckResponse].ok(DuplicateCheckResponse(matches=items))


@router.get("/eligible-assignees")
async def get_eligible_assignees(
    service: ServiceDep, actor: Annotated[User, _perm("assign")], product_category: str, product_id: str | None = None
) -> ApiResponse[list[EligibleAssigneeResponse]]:
    # `_perm("assign")` here gates the ACTOR — is this caller (Owner, or an Employee
    # whose own role holds leads:leads:assign) allowed to use the Assign feature at all.
    # That's unrelated to and unchanged by this refactor, which only replaced how
    # CANDIDATES (who shows up in the picker) are computed — see
    # LeadService.list_eligible_assignees.
    return ApiResponse[list[EligibleAssigneeResponse]].ok(await service.list_eligible_assignees(product_category, product_id, actor))


@router.post("")
async def create_lead(payload: CreateLeadRequest, service: ServiceDep, actor: Annotated[User, _perm("create")]) -> ApiResponse[LeadDetailResponse]:
    lead = await service.create_lead(payload, actor)
    source_map, product_map, employee_map = await service.resolve_names([lead])
    detail = mappers.to_detail(lead, source_map.get(lead.source_id, ""), product_map.get(lead.product_id, ""), employee_map.get(lead.assigned_to or "", None))
    return ApiResponse[LeadDetailResponse].ok(detail)


@router.get("/{lead_id}")
async def get_lead(lead_id: str, service: ServiceDep, actor: Annotated[User, _perm("view")]) -> ApiResponse[LeadDetailResponse]:
    lead = await service.get_lead_scoped(lead_id, actor)
    source_map, product_map, employee_map = await service.resolve_names([lead])
    detail = mappers.to_detail(lead, source_map.get(lead.source_id, ""), product_map.get(lead.product_id, ""), employee_map.get(lead.assigned_to or "", None))
    return ApiResponse[LeadDetailResponse].ok(detail)


@router.patch("/{lead_id}")
async def update_lead(
    lead_id: str, payload: UpdateLeadRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[LeadDetailResponse]:
    lead = await service.update_lead(lead_id, payload, actor)
    source_map, product_map, employee_map = await service.resolve_names([lead])
    detail = mappers.to_detail(lead, source_map.get(lead.source_id, ""), product_map.get(lead.product_id, ""), employee_map.get(lead.assigned_to or "", None))
    return ApiResponse[LeadDetailResponse].ok(detail)


@router.post("/{lead_id}/assign")
async def assign_lead(
    lead_id: str, payload: AssignLeadRequest, service: ServiceDep, actor: Annotated[User, _perm("assign")]
) -> ApiResponse[LeadDetailResponse]:
    lead = await service.assign_lead(lead_id, payload.employee_id, actor)
    source_map, product_map, employee_map = await service.resolve_names([lead])
    detail = mappers.to_detail(lead, source_map.get(lead.source_id, ""), product_map.get(lead.product_id, ""), employee_map.get(lead.assigned_to or "", None))
    return ApiResponse[LeadDetailResponse].ok(detail)


@router.post("/{lead_id}/unassign")
async def unassign_lead(lead_id: str, service: ServiceDep, actor: Annotated[User, _perm("assign")]) -> ApiResponse[LeadDetailResponse]:
    lead = await service.unassign_lead(lead_id, actor)
    source_map, product_map, employee_map = await service.resolve_names([lead])
    detail = mappers.to_detail(lead, source_map.get(lead.source_id, ""), product_map.get(lead.product_id, ""), employee_map.get(lead.assigned_to or "", None))
    return ApiResponse[LeadDetailResponse].ok(detail)


@router.get("/{lead_id}/timeline")
async def get_timeline(lead_id: str, service: ServiceDep, actor: Annotated[User, _perm("view")]) -> ApiResponse[list[TimelineEntryResponse]]:
    entries = await service.get_timeline(lead_id, actor)
    return ApiResponse[list[TimelineEntryResponse]].ok([mappers.timeline_entry_to_response(t, doc) for t, doc in entries])


@router.post("/{lead_id}/notes")
async def add_note(lead_id: str, payload: AddNoteRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]) -> ApiResponse[NoteResponse]:
    note = await service.add_note(lead_id, payload.text, actor)
    return ApiResponse[NoteResponse].ok(mappers.note_to_response(note))
