from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.core.pagination import PageParams, page_params
from app.core.response import ApiResponse, ResponseMeta
from app.features.access_control.permission_engine import require_permission
from app.features.auth.models import User
from app.features.customer.dependencies import get_customer_service
from app.features.customer.service import CustomerService
from app.features.geo_fencing.constants import GeoActivity
from app.features.geo_fencing.enforcement import enforce_geo_fence
from app.features.leads import mappers
from app.features.leads.constants import LeadActivityType
from app.features.leads.dependencies import get_lead_service
from app.features.leads.schemas import (
    AddNoteRequest,
    AssignLeadRequest,
    CreateCustomerAccountRequest,
    CreateLeadRequest,
    DuplicateCheckResponse,
    EligibleAssigneeResponse,
    FinancialAssessmentRequest,
    FollowUpRequest,
    LeadCountsResponse,
    LeadDetailResponse,
    LeadListItem,
    LeadLookupResponse,
    LookupItem,
    NoteResponse,
    RejectLeadRequest,
    SetStageRequest,
    TimelineEntryResponse,
    UpdateLeadRequest,
)
from app.features.leads.service import LeadService

router = APIRouter(prefix="/leads", tags=["leads"])

ServiceDep = Annotated[LeadService, Depends(get_lead_service)]
PageParamsDep = Annotated[PageParams, Depends(page_params)]
DbDep = Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]
_MODULE = "leads"
_RESOURCE = "leads"


def _perm(action: str) -> Any:
    return require_permission(_MODULE, _RESOURCE, action)


async def _detail(service: LeadService, lead: Any, source_map: dict, product_map: dict, employee_map: dict, actor_name_map: dict) -> LeadDetailResponse:
    # Phase 3 (decision 126) — document-collection summary always computed for the detail
    # response (cheap at single-lead granularity); zeros/None when no Application exists.
    summary = await service.get_document_collection_summary(lead)
    return mappers.to_detail(
        lead, source_map.get(lead.source_id, ""), product_map.get(lead.product_id, ""), employee_map.get(lead.assigned_to or "", None),
        actor_name_map,
        application_id=summary.application_id, application_status=summary.application_status,
        documents_required=summary.documents_required, documents_verified=summary.documents_verified,
        all_documents_verified=summary.all_documents_verified,
    )


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
    stage: str | None = None,
    exclude_stage: str | None = None,
) -> ApiResponse[list[LeadListItem]]:
    leads, total = await service.list_leads(
        search=page.search, source_id=source_id, product_category=product_category, product_id=product_id,
        assigned_to=assigned_to, status=status, stage=stage, exclude_stage=exclude_stage,
        skip=page.skip, limit=page.page_size, sort=page.sort, actor=actor,
    )
    source_map, product_map, employee_map, actor_name_map = await service.resolve_names(leads)
    # Phase 3 (decision 126) — only queries anything when `stage == "document_collection"`;
    # empty dict (a no-op lookup below) for every other tab's list call.
    application_info = await service.get_application_info_for_leads(leads, stage)
    items = [
        mappers.to_list_item(
            lead, source_map.get(lead.source_id, ""), product_map.get(lead.product_id, ""),
            employee_map.get(lead.assigned_to or "", None), actor_name_map,
            application_id=application_info.get(lead.require_id(), (None, None))[0],
            application_status=application_info.get(lead.require_id(), (None, None))[1],
        )
        for lead in leads
    ]
    return ApiResponse[list[LeadListItem]].ok(items, meta=ResponseMeta(pagination=page.build_meta(total)))


@router.get("/counts")
async def get_lead_counts(service: ServiceDep, actor: Annotated[User, _perm("view")]) -> ApiResponse[LeadCountsResponse]:
    return ApiResponse[LeadCountsResponse].ok(await service.get_tab_counts(actor))


@router.get("/lookup")
async def get_lookup_data(service: ServiceDep, actor: Annotated[User, _perm("view")]) -> ApiResponse[LeadLookupResponse]:
    # Backs the Create Lead form's Source/Product dropdowns — gated on leads:leads:view
    # (not system_settings:lead_sources:view etc.), see LeadService.get_lookup_data.
    sources, loan_products, insurance_products = await service.get_lookup_data()
    return ApiResponse[LeadLookupResponse].ok(
        LeadLookupResponse(
            sources=[LookupItem(id=s.require_id(), name=s.name) for s in sources],
            loan_products=[LookupItem(id=p.require_id(), name=p.name) for p in loan_products],
            insurance_products=[LookupItem(id=p.require_id(), name=p.name) for p in insurance_products],
        )
    )


@router.get("/export")
async def export_leads(service: ServiceDep, actor: Annotated[User, _perm("export")]) -> Response:
    csv_content = await service.export_leads_csv(actor)
    return Response(content=csv_content, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=leads.csv"})


@router.get("/check-duplicate")
async def check_duplicate(service: ServiceDep, actor: Annotated[User, _perm("view")], mobile: str) -> ApiResponse[DuplicateCheckResponse]:
    matches = await service.check_duplicate(mobile, actor)
    source_map, product_map, employee_map, actor_name_map = await service.resolve_names(matches)
    items = [
        mappers.to_list_item(
            lead, source_map.get(lead.source_id, ""), product_map.get(lead.product_id, ""),
            employee_map.get(lead.assigned_to or "", None), actor_name_map,
        )
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
async def create_lead(
    payload: CreateLeadRequest, service: ServiceDep, actor: Annotated[User, _perm("create")], db: DbDep
) -> ApiResponse[LeadDetailResponse]:
    # Additive geo-fencing check (see app/features/geo_fencing/enforcement.py) — a no-op
    # unless an active Geo Fence is configured for lead_creation, so existing callers that
    # never send latitude/longitude are unaffected.
    await enforce_geo_fence(db, actor=actor, activity=GeoActivity.LEAD_CREATION, latitude=payload.latitude, longitude=payload.longitude)
    lead = await service.create_lead(payload, actor)
    source_map, product_map, employee_map, actor_name_map = await service.resolve_names([lead])
    return ApiResponse[LeadDetailResponse].ok(await _detail(service, lead, source_map, product_map, employee_map, actor_name_map))


@router.get("/{lead_id}")
async def get_lead(lead_id: str, service: ServiceDep, actor: Annotated[User, _perm("view")]) -> ApiResponse[LeadDetailResponse]:
    lead = await service.get_lead_scoped(lead_id, actor)
    source_map, product_map, employee_map, actor_name_map = await service.resolve_names([lead])
    return ApiResponse[LeadDetailResponse].ok(await _detail(service, lead, source_map, product_map, employee_map, actor_name_map))


@router.patch("/{lead_id}")
async def update_lead(
    lead_id: str, payload: UpdateLeadRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[LeadDetailResponse]:
    lead = await service.update_lead(lead_id, payload, actor)
    source_map, product_map, employee_map, actor_name_map = await service.resolve_names([lead])
    return ApiResponse[LeadDetailResponse].ok(await _detail(service, lead, source_map, product_map, employee_map, actor_name_map))


@router.post("/{lead_id}/assign")
async def assign_lead(
    lead_id: str, payload: AssignLeadRequest, service: ServiceDep, actor: Annotated[User, _perm("assign")]
) -> ApiResponse[LeadDetailResponse]:
    lead = await service.assign_lead(lead_id, payload.employee_id, actor)
    source_map, product_map, employee_map, actor_name_map = await service.resolve_names([lead])
    return ApiResponse[LeadDetailResponse].ok(await _detail(service, lead, source_map, product_map, employee_map, actor_name_map))


@router.post("/{lead_id}/unassign")
async def unassign_lead(lead_id: str, service: ServiceDep, actor: Annotated[User, _perm("assign")]) -> ApiResponse[LeadDetailResponse]:
    lead = await service.unassign_lead(lead_id, actor)
    source_map, product_map, employee_map, actor_name_map = await service.resolve_names([lead])
    return ApiResponse[LeadDetailResponse].ok(await _detail(service, lead, source_map, product_map, employee_map, actor_name_map))


@router.post("/{lead_id}/reject")
async def reject_lead(
    lead_id: str, payload: RejectLeadRequest, service: ServiceDep, actor: Annotated[User, _perm("reject")]
) -> ApiResponse[LeadDetailResponse]:
    lead = await service.reject_lead(lead_id, payload.reason, actor)
    source_map, product_map, employee_map, actor_name_map = await service.resolve_names([lead])
    return ApiResponse[LeadDetailResponse].ok(await _detail(service, lead, source_map, product_map, employee_map, actor_name_map))


@router.post("/{lead_id}/stage")
async def set_lead_stage(
    lead_id: str, payload: SetStageRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[LeadDetailResponse]:
    lead = await service.set_stage(lead_id, payload.stage, actor)
    source_map, product_map, employee_map, actor_name_map = await service.resolve_names([lead])
    return ApiResponse[LeadDetailResponse].ok(await _detail(service, lead, source_map, product_map, employee_map, actor_name_map))


@router.post("/{lead_id}/follow-up")
async def set_lead_follow_up(
    lead_id: str, payload: FollowUpRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[LeadDetailResponse]:
    lead = await service.set_follow_up(lead_id, payload.next_follow_up_date, payload.comment, actor)
    source_map, product_map, employee_map, actor_name_map = await service.resolve_names([lead])
    return ApiResponse[LeadDetailResponse].ok(await _detail(service, lead, source_map, product_map, employee_map, actor_name_map))


@router.patch("/{lead_id}/financial-assessment")
async def set_lead_financial_assessment(
    lead_id: str, payload: FinancialAssessmentRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[LeadDetailResponse]:
    lead = await service.set_financial_assessment(lead_id, payload, actor)
    source_map, product_map, employee_map, actor_name_map = await service.resolve_names([lead])
    return ApiResponse[LeadDetailResponse].ok(await _detail(service, lead, source_map, product_map, employee_map, actor_name_map))


@router.post("/{lead_id}/customer-account")
async def create_customer_account(
    lead_id: str,
    payload: CreateCustomerAccountRequest,
    service: ServiceDep,
    actor: Annotated[User, _perm("edit")],
    customer_service: Annotated[CustomerService, Depends(get_customer_service)],
) -> ApiResponse[LeadDetailResponse]:
    # Module 6B (Customer) owns account creation itself; Module 6A (Leads) only invokes
    # it and keeps this Lead's own audit trail (Phase 2 / decision 125) — same
    # cross-module composition shape as `enforce_geo_fence` above, just for a POST body
    # instead of a query param.
    customer = await customer_service.create_staff_initiated_account(lead_id, payload.password, actor)
    await service.log_activity(lead_id, LeadActivityType.CUSTOMER_ACCOUNT_CREATED, actor, {"customer_id": customer.require_id()})
    lead = await service.get_lead_scoped(lead_id, actor)
    source_map, product_map, employee_map, actor_name_map = await service.resolve_names([lead])
    return ApiResponse[LeadDetailResponse].ok(await _detail(service, lead, source_map, product_map, employee_map, actor_name_map))


@router.get("/{lead_id}/timeline")
async def get_timeline(lead_id: str, service: ServiceDep, actor: Annotated[User, _perm("view")]) -> ApiResponse[list[TimelineEntryResponse]]:
    entries = await service.get_timeline(lead_id, actor)
    return ApiResponse[list[TimelineEntryResponse]].ok([mappers.timeline_entry_to_response(t, doc) for t, doc in entries])


@router.post("/{lead_id}/notes")
async def add_note(lead_id: str, payload: AddNoteRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]) -> ApiResponse[NoteResponse]:
    note = await service.add_note(lead_id, payload.text, actor)
    return ApiResponse[NoteResponse].ok(mappers.note_to_response(note))
