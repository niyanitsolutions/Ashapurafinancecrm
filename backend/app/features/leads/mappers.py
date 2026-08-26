from app.features.customer.models import Application, Customer
from app.features.leads.models import Lead, LeadActivity, LeadNote
from app.features.leads.schemas import (
    LeadDetailResponse,
    LeadListItem,
    NoteResponse,
    TimelineEntryResponse,
)


def to_list_item(
    lead: Lead,
    source_name: str,
    product_name: str,
    assigned_to_name: str | None,
    actor_name_map: dict[str, str],
    *,
    application_id: str | None = None,
    application_status: str | None = None,
) -> LeadListItem:
    return LeadListItem(
        id=lead.require_id(),
        lead_code=lead.lead_code,
        full_name=lead.full_name,
        mobile=lead.mobile,
        email=lead.email,
        source_id=lead.source_id,
        source_name=source_name,
        product_category=lead.product_category,
        product_id=lead.product_id,
        product_name=product_name,
        assigned_to=lead.assigned_to,
        assigned_to_name=assigned_to_name,
        status=lead.status,
        stage=lead.stage,
        salary_in_hand=lead.salary_in_hand,
        next_follow_up_date=lead.next_follow_up_date,
        assigned_by=lead.assigned_by,
        assigned_by_name=actor_name_map.get(lead.assigned_by or "", None),
        assigned_at=lead.assigned_at,
        rejected_reason=lead.rejected_reason,
        rejected_by=lead.rejected_by,
        rejected_by_name=actor_name_map.get(lead.rejected_by or "", None),
        rejected_at=lead.rejected_at,
        application_id=application_id,
        application_status=application_status,
        is_potential_duplicate=len(lead.duplicate_of_lead_ids) > 0,
        created_at=lead.created_at,
    )


def lead_less_application_to_list_item(
    application: Application, customer: Customer | None, product_name: str, assigned_to_name: str | None,
) -> LeadListItem:
    """Production fix "DC vs LM" — the Lead-less counterpart of `to_list_item`, for an
    Application with no Lead at all (see `LeadService.list_document_collection`). Reuses
    the exact same `LeadListItem` shape so the frontend's Document Collection table
    needs no structural change — only `is_lead_less=True` distinguishes it. `lead_code`
    carries the Application's own code (there's no Lead code to show); `source_name` is
    "Direct" (no Lead Source applies); every Lead-only field (financial assessment,
    assignment/rejection audit trail) is null, since none of that exists for this row."""
    return LeadListItem(
        id=application.require_id(),
        lead_code=application.application_code,
        full_name=customer.full_name if customer else "",
        mobile=customer.mobile if customer else "",
        email=customer.email if customer else None,
        source_id="",
        source_name="Direct",
        product_category=application.product_category,
        product_id=application.product_id,
        product_name=product_name,
        assigned_to=application.assigned_to,
        assigned_to_name=assigned_to_name,
        status="active",
        stage="document_collection",
        salary_in_hand=None,
        next_follow_up_date=None,
        assigned_by=None,
        assigned_by_name=None,
        assigned_at=None,
        rejected_reason=None,
        rejected_by=None,
        rejected_by_name=None,
        rejected_at=None,
        application_id=application.require_id(),
        application_status=application.status,
        is_potential_duplicate=False,
        created_at=application.created_at,
        is_lead_less=True,
    )


def to_detail(
    lead: Lead,
    source_name: str,
    product_name: str,
    assigned_to_name: str | None,
    actor_name_map: dict[str, str],
    *,
    application_id: str | None = None,
    application_status: str | None = None,
    documents_required: int = 0,
    documents_verified: int = 0,
    documents_not_available: int = 0,
    all_documents_verified: bool = False,
) -> LeadDetailResponse:
    return LeadDetailResponse(
        **to_list_item(
            lead, source_name, product_name, assigned_to_name, actor_name_map,
            application_id=application_id, application_status=application_status,
        ).model_dump(),
        remarks=lead.remarks,
        city=lead.city,
        preferred_amount=lead.preferred_amount,
        duplicate_of_lead_ids=lead.duplicate_of_lead_ids,
        updated_at=lead.updated_at,
        form_definition_id=lead.form_definition_id,
        product_form_data=lead.product_form_data,
        financial_assessment=lead.financial_assessment,
        account_created=lead.account_created,
        documents_required=documents_required,
        documents_verified=documents_verified,
        documents_not_available=documents_not_available,
        all_documents_verified=all_documents_verified,
    )


def note_to_response(note: LeadNote) -> NoteResponse:
    return NoteResponse(id=note.require_id(), lead_id=note.lead_id, text=note.text, created_by=note.created_by, created_at=note.created_at)


def timeline_entry_to_response(entry_type: str, doc: LeadActivity | LeadNote) -> TimelineEntryResponse:
    if isinstance(doc, LeadActivity):
        return TimelineEntryResponse(
            type=entry_type, event_type=doc.event_type, metadata=doc.metadata, created_by=doc.created_by, created_at=doc.created_at
        )
    return TimelineEntryResponse(type=entry_type, text=doc.text, created_by=doc.created_by, created_at=doc.created_at)
