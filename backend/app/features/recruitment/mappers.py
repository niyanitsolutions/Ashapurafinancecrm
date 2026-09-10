from collections.abc import Callable

from app.features.recruitment.constants import SignatureMethod
from app.features.recruitment.models import (
    Advisor,
    AdvisorBusiness,
    RecruitmentActivity,
    RecruitmentDocumentFile,
    RecruitmentDocuments,
    RecruitmentLead,
    RecruitmentNote,
)
from app.features.recruitment.schemas import (
    AdvisorBusinessResponse,
    AdvisorDetailResponse,
    AdvisorListItem,
    AdvisorSummaryResponse,
    ExaminationResultResponse,
    NomineeResponse,
    RecruitmentDocumentFileResponse,
    RecruitmentDocumentsResponse,
    RecruitmentLeadDetailResponse,
    RecruitmentLeadListItem,
    RecruitmentNoteResponse,
    RecruitmentTimelineEntryResponse,
    SignatureResponse,
)
from app.features.recruitment.service import RecruitmentService

DownloadUrlFn = Callable[[str | None], str | None]


def _latest_result(lead: RecruitmentLead) -> str | None:
    return lead.examinations[-1].result if lead.examinations else None


def to_list_item(lead: RecruitmentLead, source_name: str, assigned_to_name: str | None) -> RecruitmentLeadListItem:
    return RecruitmentLeadListItem(
        id=lead.require_id(),
        recruitment_code=lead.recruitment_code,
        full_name=lead.full_name,
        mobile=lead.mobile,
        email=lead.email,
        gender=lead.gender,
        age=lead.age,
        source_id=lead.source_id,
        source_name=source_name,
        profession=lead.profession,
        other_profession=lead.other_profession,
        remarks=lead.remarks,
        stage=lead.stage,
        assigned_to=lead.assigned_to,
        assigned_to_name=assigned_to_name,
        latest_examination_result=_latest_result(lead),
        documents_ready=RecruitmentService.documents_ready(lead),
        advisor_id=lead.advisor_id,
        rejected_reason=lead.rejected_reason,
        rejected_at=lead.rejected_at,
        created_at=lead.created_at,
    )


def _file_response(file: RecruitmentDocumentFile | None, download_url: DownloadUrlFn) -> RecruitmentDocumentFileResponse | None:
    if file is None:
        return None
    return RecruitmentDocumentFileResponse(
        file_name=file.file_name, uploaded_at=file.uploaded_at, download_url=download_url(file.s3_key)
    )


def _documents_response(docs: RecruitmentDocuments | None, download_url: DownloadUrlFn) -> RecruitmentDocumentsResponse | None:
    if docs is None:
        return None
    signature: SignatureResponse | None = None
    if docs.signature is not None:
        if docs.signature.method == SignatureMethod.TYPE:
            signature = SignatureResponse(method=docs.signature.method, value=docs.signature.value)
        else:
            signature = SignatureResponse(
                method=docs.signature.method,
                value=download_url(docs.signature.value) or "",
                file_name=docs.signature.file_name,
            )
    nominee = (
        NomineeResponse(name=docs.nominee.name, dob=docs.nominee.dob, relationship=docs.nominee.relationship)
        if docs.nominee is not None
        else None
    )
    return RecruitmentDocumentsResponse(
        pan=_file_response(docs.pan, download_url),
        aadhaar=_file_response(docs.aadhaar, download_url),
        bank_proof=_file_response(docs.bank_proof, download_url),
        bank_proof_type=docs.bank_proof_type,
        cheque_name_confirmed=docs.cheque_name_confirmed,
        qualification=_file_response(docs.qualification, download_url),
        photo=_file_response(docs.photo, download_url),
        email=docs.email,
        mobile=docs.mobile,
        alternate_number=docs.alternate_number,
        nominee=nominee,
        signature=signature,
    )


def to_detail(
    lead: RecruitmentLead, source_name: str, assigned_to_name: str | None, download_url: DownloadUrlFn
) -> RecruitmentLeadDetailResponse:
    return RecruitmentLeadDetailResponse(
        **to_list_item(lead, source_name, assigned_to_name).model_dump(),
        updated_at=lead.updated_at,
        assigned_by=lead.assigned_by,
        assigned_at=lead.assigned_at,
        exam_fee_paid=lead.exam_fee_paid,
        exam_fee_paid_at=lead.exam_fee_paid_at,
        exam_fee_reference=lead.exam_fee_reference,
        documents=_documents_response(lead.documents, download_url),
        examinations=[
            ExaminationResultResponse(
                attempt=e.attempt, result=e.result, remarks=e.remarks, recorded_by=e.recorded_by, recorded_at=e.recorded_at
            )
            for e in lead.examinations
        ],
    )


def note_to_response(note: RecruitmentNote) -> RecruitmentNoteResponse:
    return RecruitmentNoteResponse(
        id=note.require_id(), recruitment_lead_id=note.recruitment_lead_id, text=note.text,
        created_by=note.created_by, created_at=note.created_at,
    )


def timeline_entry_to_response(entry_type: str, doc: RecruitmentActivity | RecruitmentNote) -> RecruitmentTimelineEntryResponse:
    if isinstance(doc, RecruitmentActivity):
        return RecruitmentTimelineEntryResponse(
            type=entry_type, event_type=doc.event_type, metadata=doc.metadata, created_by=doc.created_by, created_at=doc.created_at
        )
    return RecruitmentTimelineEntryResponse(type=entry_type, text=doc.text, created_by=doc.created_by, created_at=doc.created_at)


def advisor_to_summary(advisor: Advisor) -> AdvisorSummaryResponse:
    return AdvisorSummaryResponse(
        id=advisor.require_id(),
        advisor_code=advisor.advisor_code,
        recruitment_lead_id=advisor.recruitment_lead_id,
        full_name=advisor.full_name,
        mobile=advisor.mobile,
        email=advisor.email,
        channel=advisor.channel,
        agency_code=advisor.agency_code,
        agent_code=advisor.agent_code,
        status=advisor.status,
        created_at=advisor.created_at,
    )


# ---------------------------------------------------------------- Advisor Management (Phase 2)


def business_to_response(business: AdvisorBusiness) -> AdvisorBusinessResponse:
    return AdvisorBusinessResponse(
        id=business.require_id(),
        advisor_id=business.advisor_id,
        customer_name=business.customer_name,
        customer_mobile=business.customer_mobile,
        policy_number=business.policy_number,
        product_category=business.product_category,
        custom_category=business.custom_category,
        product_name=business.product_name,
        premium=business.premium,
        ppt=business.ppt,
        pt=business.pt,
        policy_issue_date=business.policy_issue_date,
        comment=business.comment,
        created_at=business.created_at,
    )


def advisor_to_list_item(advisor: Advisor, is_employee: bool, no_of_policies: int, total_premium: float) -> AdvisorListItem:
    return AdvisorListItem(
        id=advisor.require_id(),
        advisor_code=advisor.advisor_code,
        recruitment_lead_id=advisor.recruitment_lead_id,
        full_name=advisor.full_name,
        mobile=advisor.mobile,
        email=advisor.email,
        channel=advisor.channel,
        agency_code=advisor.agency_code,
        agent_code=advisor.agent_code,
        profession=advisor.profession,
        other_profession=advisor.other_profession,
        status=advisor.status,
        is_employee=is_employee,
        no_of_policies=no_of_policies,
        total_premium=total_premium,
        created_at=advisor.created_at,
    )


def advisor_to_detail(
    advisor: Advisor,
    is_employee: bool,
    no_of_policies: int,
    total_premium: float,
    businesses: list[AdvisorBusiness],
    recruitment: RecruitmentLeadDetailResponse | None,
) -> AdvisorDetailResponse:
    return AdvisorDetailResponse(
        **advisor_to_list_item(advisor, is_employee, no_of_policies, total_premium).model_dump(),
        updated_at=advisor.updated_at,
        recruitment=recruitment,
        businesses=[business_to_response(b) for b in businesses],
    )
