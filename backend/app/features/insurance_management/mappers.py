from typing import Any

from app.features.insurance_management.schemas import (
    InsuranceCaseDetailResponse,
    InsuranceCaseDetailsResponse,
    InsuranceCaseListItem,
)
from app.features.workflow_engine.models import (
    ApplicationNote,
    ApplicationStatusHistory,
    ApplicationWorkflow,
)
from app.features.workflow_engine.schemas import CaseNoteResponse, CaseTimelineEntryResponse


def _details_response(case: ApplicationWorkflow) -> InsuranceCaseDetailsResponse:
    details = case.insurance_details
    assert details is not None
    return InsuranceCaseDetailsResponse(**details.model_dump())


def to_list_item(case: ApplicationWorkflow, customer_name: str | None, product_name: str, assigned_to_name: str | None) -> InsuranceCaseListItem:
    return InsuranceCaseListItem(
        id=case.require_id(), case_code=case.case_code, application_id=case.application_id, customer_id=case.customer_id,
        customer_name=customer_name, product_id=case.product_id, product_name=product_name,
        assigned_to=case.assigned_to, assigned_to_name=assigned_to_name, current_status=case.current_status,
        rejection_reason=case.rejection_reason, created_at=case.created_at,
    )


def to_detail_response(case: ApplicationWorkflow, customer_name: str | None, product_name: str, assigned_to_name: str | None) -> InsuranceCaseDetailResponse:
    return InsuranceCaseDetailResponse(
        **to_list_item(case, customer_name, product_name, assigned_to_name).model_dump(),
        pending_document_type_ids=case.pending_document_type_ids,
        insurance_details=_details_response(case),
        updated_at=case.updated_at,
    )


def note_to_response(note: ApplicationNote) -> CaseNoteResponse:
    return CaseNoteResponse(id=note.require_id(), text=note.text, created_by=note.created_by, created_at=note.created_at)


def timeline_entry_to_response(entry_type: str, doc: Any) -> CaseTimelineEntryResponse:
    if isinstance(doc, ApplicationStatusHistory):
        return CaseTimelineEntryResponse(
            type=entry_type, from_status=doc.from_status, to_status=doc.to_status, remarks=doc.remarks,
            created_by=doc.created_by, created_at=doc.created_at,
        )
    return CaseTimelineEntryResponse(type=entry_type, text=doc.text, created_by=doc.created_by, created_at=doc.created_at)
