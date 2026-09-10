"""Insurance Advisor Recruitment — business logic.

Authorization is at the router layer (`require_permission("insurance_management",
"recruitment", action)`), matching every module built after Access Control. This service
owns the explicit stage machine (see `constants.RecruitmentStage`), the
examination-PASS → Advisor promotion (idempotent), and the presigned-upload plumbing
(reused verbatim from the customer document flow).
"""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.constants.roles import OWNER
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.features.access_control.permission_engine import PermissionEngine
from app.features.auth.models import User
from app.features.employee.repository import EmployeeRepository
from app.features.recruitment.constants import (
    BankProofType,
    DocumentSlot,
    ExaminationOutcome,
    Profession,
    RecruitmentActivityType,
    RecruitmentAuditEvent,
    RecruitmentStage,
    SignatureMethod,
)
from app.features.recruitment.models import (
    Advisor,
    ExaminationResult,
    RecruitmentActivity,
    RecruitmentDocumentFile,
    RecruitmentDocuments,
    RecruitmentLead,
    RecruitmentNominee,
    RecruitmentNote,
    RecruitmentSignature,
)
from app.features.recruitment.repository import (
    AdvisorRepository,
    RecruitmentActivityRepository,
    RecruitmentLeadRepository,
    RecruitmentNoteRepository,
)
from app.features.recruitment.schemas import (
    ConfirmedFile,
    CreateRecruitmentLeadRequest,
    RecordExamFeeRequest,
    RecordExaminationRequest,
    SaveRecruitmentDocumentsRequest,
    SignatureInput,
    UpdateRecruitmentLeadRequest,
)
from app.features.system_settings.repository import LeadSourceRepository
from app.services.storage.client import (
    generate_presigned_download_url,
    generate_presigned_upload_url,
    get_object_size,
)
from app.shared.audit_log import write_audit_log
from app.utils.datetime import ist_date_to_utc_midnight, utc_now
from app.utils.id_generator import IdPrefix, generate_id

_NO_MATCH = "___no_match___"
_UPLOAD_URL_EXPIRE_SECONDS = 900
_DOWNLOAD_URL_EXPIRE_SECONDS = 900


class RecruitmentService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self._db = db
        self._leads = RecruitmentLeadRepository(db)
        self._activities = RecruitmentActivityRepository(db)
        self._notes = RecruitmentNoteRepository(db)
        self._advisors = AdvisorRepository(db)
        self._employees = EmployeeRepository(db)
        self._sources = LeadSourceRepository(db)
        self._permissions = PermissionEngine(db)

    # ---------------------------------------------------------------- helpers

    async def _validate_source(self, source_id: str) -> None:
        if await self._sources.find_by_id(source_id) is None:
            raise ValidationError("Unknown source_id.")

    async def _acting_employee_id(self, actor: User) -> str:
        employee = await self._employees.find_by_user_id(actor.require_id())
        return employee.require_id() if employee is not None else _NO_MATCH

    async def _has_broad_visibility(self, actor: User) -> bool:
        """An Owner, or an Employee whose role holds `insurance_management:recruitment:
        assign` (already trusted to distribute recruitment leads), sees the whole pool —
        same posture as `LeadService._has_broad_visibility`."""
        if actor.role == OWNER:
            return True
        return await self._permissions.has_permission(
            actor, module="insurance_management", resource="recruitment", action="assign"
        )

    async def _scope(self, actor: User) -> tuple[str | None, str | None]:
        """`(scope_user_id, scope_employee_id)` for the repository — `(None, None)` means
        unrestricted (Owner / broad visibility)."""
        if await self._has_broad_visibility(actor):
            return None, None
        return actor.require_id(), await self._acting_employee_id(actor)

    async def _log(self, lead_id: str, event_type: str, actor: User, metadata: dict[str, Any] | None = None) -> None:
        await self._activities.insert(
            RecruitmentActivity(recruitment_lead_id=lead_id, event_type=event_type, metadata=metadata, created_by=actor.require_id())
        )

    async def _audit(self, event_type: str, actor: User, lead_id: str, extra: dict[str, Any] | None = None) -> None:
        await write_audit_log(
            self._db, event_type=event_type, user_id=actor.require_id(),
            metadata={"recruitment_lead_id": lead_id, **(extra or {})},
        )

    @staticmethod
    def _documents_ready(lead: RecruitmentLead) -> bool:
        """Every requirement for an examination PASS: the four required documents, a
        passport photo, and one signature — plus, when the bank proof is a cheque, the
        printed-name attestation."""
        docs = lead.documents
        if docs is None:
            return False
        if docs.pan is None or docs.aadhaar is None or docs.bank_proof is None or docs.qualification is None:
            return False
        if docs.photo is None or docs.signature is None:
            return False
        return not (docs.bank_proof_type == BankProofType.CHEQUE and not docs.cheque_name_confirmed)

    @staticmethod
    def _latest_examination(lead: RecruitmentLead) -> ExaminationResult | None:
        return lead.examinations[-1] if lead.examinations else None

    # ---------------------------------------------------------------- read

    async def get_lead(self, lead_id: str) -> RecruitmentLead:
        lead = await self._leads.find_by_id(lead_id)
        if lead is None:
            raise NotFoundError("Recruitment lead not found.")
        return lead

    async def get_lead_scoped(self, lead_id: str, actor: User) -> RecruitmentLead:
        lead = await self.get_lead(lead_id)
        if actor.role == OWNER or await self._has_broad_visibility(actor):
            return lead
        employee_id = await self._acting_employee_id(actor)
        if lead.assigned_to == employee_id or lead.created_by == actor.require_id():
            return lead
        raise ForbiddenError("This recruitment lead isn't assigned to you.")

    async def list_leads(
        self, actor: User, *, search: str | None, stage: str | None, assigned_to: str | None,
        skip: int, limit: int, sort: list[tuple[str, int]] | None,
    ) -> tuple[list[RecruitmentLead], int]:
        scope_user_id, scope_employee_id = await self._scope(actor)
        stage_value: str | None = stage
        # Every recruitment tab is now its own real stage. "Agency Code" is the promoted
        # roster (assignment of the agency code happens in Advisor Management).
        if stage == "agency_code":
            stage_value = RecruitmentStage.ADVISOR
        return await self._leads.search_and_filter(
            search=search, stage=stage_value, stage_in=None, assigned_to=assigned_to,
            scope_user_id=scope_user_id, scope_employee_id=scope_employee_id, skip=skip, limit=limit, sort=sort,
        )

    async def get_counts(self, actor: User) -> dict[str, int]:
        scope_user_id, scope_employee_id = await self._scope(actor)

        async def n(*, stage: str | None = None, stage_in: tuple[str, ...] | None = None) -> int:
            return await self._leads.count_stage(
                stage=stage, stage_in=stage_in, scope_user_id=scope_user_id, scope_employee_id=scope_employee_id
            )

        return {
            "fresh": await n(stage=RecruitmentStage.FRESH),
            "bop": await n(stage=RecruitmentStage.BOP),
            "doc_collection": await n(stage=RecruitmentStage.DOC_COLLECTION),
            "exam_fee_status": await n(stage=RecruitmentStage.EXAM_FEE_STATUS),
            "examination": await n(stage=RecruitmentStage.EXAMINATION),
            "re_examination": await n(stage=RecruitmentStage.RE_EXAMINATION),
            "agency_code": await n(stage=RecruitmentStage.ADVISOR),
            "rejected": await n(stage=RecruitmentStage.REJECTED),
        }

    # ---------------------------------------------------------------- create / update

    async def create_lead(self, payload: CreateRecruitmentLeadRequest, actor: User) -> RecruitmentLead:
        await self._validate_source(payload.source_id)

        active = [d for d in await self._leads.find_by_mobile(payload.mobile) if d.stage != RecruitmentStage.REJECTED]
        if active:
            raise ConflictError(
                f"A recruitment lead already exists with this mobile number ({active[0].recruitment_code}).",
                details={"existing_id": active[0].require_id(), "existing_code": active[0].recruitment_code},
            )

        code = await generate_id(self._db, IdPrefix.RECRUITMENT)
        lead = RecruitmentLead(
            recruitment_code=code,
            full_name=payload.full_name,
            mobile=payload.mobile,
            email=payload.email,
            gender=payload.gender,
            age=payload.age,
            source_id=payload.source_id,
            profession=payload.profession,
            other_profession=payload.other_profession,
            remarks=payload.remarks,
            stage=RecruitmentStage.FRESH,
            created_by=actor.require_id(),
        )
        lead_id = await self._leads.insert(lead)
        await self._log(lead_id, RecruitmentActivityType.CREATED, actor, {"recruitment_code": code})
        await self._audit(RecruitmentAuditEvent.LEAD_CREATED, actor, lead_id, {"recruitment_code": code})
        return await self.get_lead(lead_id)

    async def update_lead(self, lead_id: str, payload: UpdateRecruitmentLeadRequest, actor: User) -> RecruitmentLead:
        lead = await self.get_lead_scoped(lead_id, actor)
        if lead.stage in RecruitmentStage.TERMINAL:
            raise ConflictError("A promoted or rejected recruitment lead can no longer be edited.")

        updates: dict[str, Any] = {}
        for field in ("full_name", "mobile", "email", "gender", "age", "source_id", "remarks"):
            value = getattr(payload, field)
            if value is not None:
                updates[field] = value
        if payload.source_id is not None:
            await self._validate_source(payload.source_id)
        if payload.mobile is not None and payload.mobile != lead.mobile:
            clash = [d for d in await self._leads.find_by_mobile(payload.mobile, exclude_id=lead_id) if d.stage != RecruitmentStage.REJECTED]
            if clash:
                raise ConflictError(f"Another recruitment lead already uses this mobile number ({clash[0].recruitment_code}).")

        new_profession = payload.profession or lead.profession
        if payload.profession is not None:
            updates["profession"] = payload.profession
        if new_profession == Profession.OTHER:
            other = payload.other_profession if payload.other_profession is not None else lead.other_profession
            if not (other or "").strip():
                raise ValidationError("other_profession is required when profession is 'other'.")
            updates["other_profession"] = other
        else:
            updates["other_profession"] = None

        updated = await self._leads.update(lead_id, updates, updated_by=actor.require_id())
        assert updated is not None
        await self._log(lead_id, RecruitmentActivityType.UPDATED, actor)
        await self._audit(RecruitmentAuditEvent.LEAD_UPDATED, actor, lead_id)
        return updated

    # ---------------------------------------------------------------- stage transitions

    async def _transition(
        self, lead: RecruitmentLead, to_stage: str, actor: User, event: str,
        *, extra_updates: dict[str, Any] | None = None, audit_extra: dict[str, Any] | None = None,
    ) -> RecruitmentLead:
        updates = {"stage": to_stage, **(extra_updates or {})}
        updated = await self._leads.update(lead.require_id(), updates, updated_by=actor.require_id())
        assert updated is not None
        await self._log(lead.require_id(), event, actor, {"from": lead.stage, "to": to_stage})
        await self._audit(RecruitmentAuditEvent.STAGE_CHANGED, actor, lead.require_id(), {"from": lead.stage, "to": to_stage, **(audit_extra or {})})
        return updated

    async def move_to_bop(self, lead_id: str, actor: User) -> RecruitmentLead:
        lead = await self.get_lead_scoped(lead_id, actor)
        if lead.stage != RecruitmentStage.FRESH:
            raise ConflictError("Only a Fresh recruitment lead can be moved to BOP.")
        return await self._transition(lead, RecruitmentStage.BOP, actor, RecruitmentActivityType.MOVED_TO_BOP)

    async def back_to_fresh(self, lead_id: str, actor: User) -> RecruitmentLead:
        lead = await self.get_lead_scoped(lead_id, actor)
        if lead.stage != RecruitmentStage.BOP:
            raise ConflictError("Only a BOP recruitment lead can be moved back to Fresh.")
        return await self._transition(lead, RecruitmentStage.FRESH, actor, RecruitmentActivityType.BACK_TO_FRESH)

    async def move_to_doc_collection(self, lead_id: str, actor: User) -> RecruitmentLead:
        lead = await self.get_lead_scoped(lead_id, actor)
        if lead.stage != RecruitmentStage.BOP:
            raise ConflictError("Only a BOP recruitment lead can be moved to Document Collection.")
        return await self._transition(
            lead, RecruitmentStage.DOC_COLLECTION, actor, RecruitmentActivityType.MOVED_TO_DOC_COLLECTION
        )

    async def reject(self, lead_id: str, reason: str, actor: User) -> RecruitmentLead:
        lead = await self.get_lead_scoped(lead_id, actor)
        if lead.stage == RecruitmentStage.REJECTED:
            raise ConflictError("This recruitment lead is already rejected.")
        if lead.stage == RecruitmentStage.ADVISOR:
            raise ConflictError("A promoted advisor cannot be rejected here.")
        return await self._transition(
            lead, RecruitmentStage.REJECTED, actor, RecruitmentActivityType.REJECTED,
            extra_updates={"rejected_reason": reason, "rejected_by": actor.require_id(), "rejected_at": utc_now()},
            audit_extra={"reason": reason},
        )

    # ---------------------------------------------------------------- documents

    def _s3_key(self, lead: RecruitmentLead, slot: str, file_name: str) -> str:
        return f"recruitment-documents/{lead.recruitment_code}/{slot}/{file_name}"

    async def generate_document_upload_url(self, lead_id: str, slot: str, file_name: str, content_type: str | None, actor: User) -> tuple[str, str]:
        lead = await self.get_lead_scoped(lead_id, actor)
        if lead.stage != RecruitmentStage.DOC_COLLECTION:
            raise ConflictError("Documents can only be uploaded while the lead is in Document Collection.")
        s3_key = self._s3_key(lead, slot, file_name)
        url = generate_presigned_upload_url(s3_key, expires_in=_UPLOAD_URL_EXPIRE_SECONDS, content_type=content_type)
        return url, s3_key

    async def _materialise_file(self, lead: RecruitmentLead, slot: str, confirmed: ConfirmedFile, actor: User) -> RecruitmentDocumentFile:
        # Never trust the client's `s3_key` — re-derive it from the exact same expression
        # `generate_document_upload_url` used, so a caller can't point this at another
        # lead's (or an employee-documents) key and read it back via the download URL.
        s3_key = self._s3_key(lead, slot, confirmed.file_name)
        if get_object_size(s3_key) is None:
            raise ValidationError(f"The upload for '{slot}' did not complete — please try again.")
        return RecruitmentDocumentFile(s3_key=s3_key, file_name=confirmed.file_name, uploaded_at=utc_now(), uploaded_by=actor.require_id())

    async def _materialise_signature(self, lead: RecruitmentLead, sig: SignatureInput, actor: User) -> RecruitmentSignature:
        if sig.method == SignatureMethod.TYPE:
            value = sig.value.strip()
            if not value:
                raise ValidationError("A typed signature cannot be blank.")
            return RecruitmentSignature(method=sig.method, value=value, updated_at=utc_now(), updated_by=actor.require_id())
        # draw / upload — `value` is the confirmed S3 key; re-derive and verify.
        assert sig.file_name is not None
        s3_key = self._s3_key(lead, DocumentSlot.SIGNATURE, sig.file_name)
        if get_object_size(s3_key) is None:
            raise ValidationError("The signature upload did not complete — please try again.")
        return RecruitmentSignature(
            method=sig.method, value=s3_key, file_name=sig.file_name, updated_at=utc_now(), updated_by=actor.require_id()
        )

    async def save_documents(self, lead_id: str, payload: SaveRecruitmentDocumentsRequest, actor: User) -> RecruitmentLead:
        lead = await self.get_lead_scoped(lead_id, actor)
        if lead.stage != RecruitmentStage.DOC_COLLECTION:
            raise ConflictError("Documents can only be saved while the lead is in Document Collection.")

        docs = lead.documents.model_copy(deep=True) if lead.documents is not None else RecruitmentDocuments()

        for slot in (DocumentSlot.PAN, DocumentSlot.AADHAAR, DocumentSlot.BANK_PROOF, DocumentSlot.QUALIFICATION, DocumentSlot.PHOTO):
            confirmed: ConfirmedFile | None = getattr(payload, slot)
            if confirmed is not None:
                setattr(docs, slot, await self._materialise_file(lead, slot, confirmed, actor))

        if payload.bank_proof_type is not None:
            docs.bank_proof_type = payload.bank_proof_type
        if payload.cheque_name_confirmed is not None:
            docs.cheque_name_confirmed = payload.cheque_name_confirmed
        # A passbook proof can never carry a stale cheque attestation.
        if docs.bank_proof_type == BankProofType.PASSBOOK:
            docs.cheque_name_confirmed = False

        if payload.email is not None:
            docs.email = payload.email
        if payload.mobile is not None:
            docs.mobile = payload.mobile
        if payload.alternate_number is not None:
            docs.alternate_number = payload.alternate_number

        if payload.nominee is not None:
            docs.nominee = RecruitmentNominee(
                name=payload.nominee.name,
                dob=ist_date_to_utc_midnight(payload.nominee.dob),
                relationship=payload.nominee.relationship,
            )
        if payload.signature is not None:
            docs.signature = await self._materialise_signature(lead, payload.signature, actor)

        # Backend gate (brief §3/§14): the candidate cannot be saved / completed in
        # Document Collection until EVERY required document is present. Same completeness
        # definition the examination-PASS gate uses (`_documents_ready`).
        merged = lead.model_copy(update={"documents": docs})
        if not self._documents_ready(merged):
            raise ValidationError("Please upload all required documents before saving.")

        updated = await self._leads.update(
            lead_id,
            {"documents": docs.model_dump(mode="json"), "stage": RecruitmentStage.EXAM_FEE_STATUS},
            updated_by=actor.require_id(),
        )
        assert updated is not None
        await self._log(lead_id, RecruitmentActivityType.DOCUMENTS_SAVED, actor,
                        {"from": lead.stage, "to": RecruitmentStage.EXAM_FEE_STATUS})
        await self._audit(RecruitmentAuditEvent.DOCUMENTS_SAVED, actor, lead_id)
        await self._audit(RecruitmentAuditEvent.STAGE_CHANGED, actor, lead_id,
                          {"from": lead.stage, "to": RecruitmentStage.EXAM_FEE_STATUS})
        return updated

    # ---------------------------------------------------------------- exam fee

    async def record_exam_fee(self, lead_id: str, payload: RecordExamFeeRequest, actor: User) -> RecruitmentLead:
        lead = await self.get_lead_scoped(lead_id, actor)
        if lead.stage != RecruitmentStage.EXAM_FEE_STATUS:
            raise ConflictError("The exam fee can only be recorded while the lead is at Exam Fee Status.")
        return await self._transition(
            lead, RecruitmentStage.EXAMINATION, actor, RecruitmentActivityType.EXAM_FEE_RECORDED,
            extra_updates={
                "exam_fee_paid": True,
                "exam_fee_paid_at": utc_now(),
                "exam_fee_reference": (payload.reference or "").strip() or None,
            },
        )

    # ---------------------------------------------------------------- examination

    async def _assert_ready_for_pass(self, lead: RecruitmentLead) -> None:
        if not self._documents_ready(lead):
            raise ValidationError(
                "All required documents, a passport photo and a signature must be collected before a PASS can be recorded."
            )

    async def record_examination(self, lead_id: str, payload: RecordExaminationRequest, actor: User) -> RecruitmentLead:
        lead = await self.get_lead_scoped(lead_id, actor)
        if lead.stage not in RecruitmentStage.EXAM_STAGES:
            raise ConflictError("An examination result can only be recorded for a lead at Examination or Re-Examination.")

        attempt = len(lead.examinations) + 1
        entry = ExaminationResult(
            attempt=attempt, result=payload.result, remarks=payload.remarks,
            recorded_by=actor.require_id(), recorded_at=utc_now(),
        )
        examinations = [*(e.model_dump(mode="json") for e in lead.examinations), entry.model_dump(mode="json")]

        if payload.result == ExaminationOutcome.PASS:
            await self._assert_ready_for_pass(lead)
            updated = await self._leads.update(lead_id, {"examinations": examinations}, updated_by=actor.require_id())
            assert updated is not None
            await self._log(lead_id, RecruitmentActivityType.EXAMINATION_RECORDED, actor, {"result": payload.result, "attempt": attempt})
            await self._audit(RecruitmentAuditEvent.EXAMINATION_RECORDED, actor, lead_id, {"result": payload.result})
            return await self._promote_to_advisor(updated, actor)

        # FAIL / ABSENT → Re-Examination (a lead already at Re-Examination stays put,
        # attempt count incremented).
        target = RecruitmentStage.RE_EXAMINATION
        updated = await self._leads.update(
            lead_id, {"examinations": examinations, "stage": target}, updated_by=actor.require_id()
        )
        assert updated is not None
        await self._log(lead_id, RecruitmentActivityType.EXAMINATION_RECORDED, actor, {"result": payload.result, "attempt": attempt})
        await self._audit(RecruitmentAuditEvent.EXAMINATION_RECORDED, actor, lead_id, {"result": payload.result})
        if lead.stage != target:
            await self._audit(RecruitmentAuditEvent.STAGE_CHANGED, actor, lead_id, {"from": lead.stage, "to": target})
        return updated

    async def move_to_advisor(self, lead_id: str, actor: User) -> RecruitmentLead:
        """Manual promotion. Idempotent — a second call (or a race with the automatic
        PASS promotion) returns the existing advisor, never a duplicate."""
        lead = await self.get_lead_scoped(lead_id, actor)
        if lead.advisor_id is not None:
            return lead
        if lead.stage not in RecruitmentStage.EXAM_STAGES:
            raise ConflictError("Only a lead at Examination or Re-Examination can be moved to Advisor.")
        latest = self._latest_examination(lead)
        if latest is None or latest.result != ExaminationOutcome.PASS:
            raise ConflictError("A lead can only be moved to Advisor after passing the examination.")
        return await self._promote_to_advisor(lead, actor)

    async def _promote_to_advisor(self, lead: RecruitmentLead, actor: User) -> RecruitmentLead:
        # Idempotency: the Advisor is keyed on `recruitment_lead_id` (unique index +
        # this lookup), so a repeated PASS or a race with the manual Move to Advisor
        # reuses the existing record instead of minting a second one.
        advisor = await self._advisors.find_by_recruitment_lead_id(lead.require_id())
        if advisor is None:
            advisor_code = await generate_id(self._db, IdPrefix.ADVISOR)
            advisor = Advisor(
                advisor_code=advisor_code,
                recruitment_lead_id=lead.require_id(),
                full_name=lead.full_name,
                mobile=lead.mobile,
                email=lead.email,
                profession=lead.profession,
                other_profession=lead.other_profession,
                created_by=actor.require_id(),
            )
            advisor_id = await self._advisors.insert(advisor)
            await self._audit(RecruitmentAuditEvent.ADVISOR_CREATED, actor, lead.require_id(), {"advisor_id": advisor_id, "advisor_code": advisor_code})
        else:
            advisor_id = advisor.require_id()

        updated = await self._leads.update(
            lead.require_id(), {"stage": RecruitmentStage.ADVISOR, "advisor_id": advisor_id}, updated_by=actor.require_id()
        )
        assert updated is not None
        if lead.stage != RecruitmentStage.ADVISOR or lead.advisor_id != advisor_id:
            await self._log(lead.require_id(), RecruitmentActivityType.MOVED_TO_ADVISOR, actor, {"advisor_id": advisor_id})
            await self._audit(RecruitmentAuditEvent.STAGE_CHANGED, actor, lead.require_id(), {"from": lead.stage, "to": RecruitmentStage.ADVISOR})
        return updated

    # ---------------------------------------------------------------- assignment

    async def assign(self, lead_id: str, employee_id: str, actor: User) -> RecruitmentLead:
        lead = await self.get_lead(lead_id)
        if actor.role != OWNER and lead.assigned_to is not None and not await self._has_broad_visibility(actor):
            raise ForbiddenError("Only an Owner can reassign a recruitment lead that's already assigned.")
        if await self._employees.find_by_id(employee_id) is None:
            raise ValidationError("Unknown employee_id.")
        updated = await self._leads.update(
            lead_id, {"assigned_to": employee_id, "assigned_by": actor.require_id(), "assigned_at": utc_now()},
            updated_by=actor.require_id(),
        )
        assert updated is not None
        await self._log(lead_id, RecruitmentActivityType.ASSIGNED, actor, {"employee_id": employee_id})
        await self._audit(RecruitmentAuditEvent.LEAD_ASSIGNED, actor, lead_id, {"employee_id": employee_id})
        return updated

    # ---------------------------------------------------------------- notes / timeline

    async def add_note(self, lead_id: str, text: str, actor: User) -> RecruitmentNote:
        await self.get_lead_scoped(lead_id, actor)
        note = RecruitmentNote(recruitment_lead_id=lead_id, text=text, created_by=actor.require_id())
        note_id = await self._notes.insert(note)
        await self._log(lead_id, RecruitmentActivityType.NOTE_ADDED, actor)
        await self._audit(RecruitmentAuditEvent.NOTE_ADDED, actor, lead_id)
        found = await self._notes.find_by_id(note_id)
        assert found is not None
        return found

    async def get_timeline(self, lead_id: str, actor: User) -> list[tuple[str, Any]]:
        await self.get_lead_scoped(lead_id, actor)
        activities = await self._activities.find_for_lead(lead_id)
        notes = await self._notes.find_for_lead(lead_id)
        combined: list[tuple[str, Any]] = [("activity", a) for a in activities] + [("note", n) for n in notes]
        combined.sort(key=lambda entry: entry[1].created_at, reverse=True)
        return combined

    # ---------------------------------------------------------------- lookups / name resolution

    async def get_lookup(self) -> list[Any]:
        return await self._sources.find_many({"status": "active"}, limit=500, sort=[("name", 1)])

    async def resolve_names(self, leads: list[RecruitmentLead]) -> tuple[dict[str, str], dict[str, str]]:
        source_ids = {lead.source_id for lead in leads}
        employee_ids = {lead.assigned_to for lead in leads if lead.assigned_to}
        sources = await self._sources.find_many({}, limit=1000) if source_ids else []
        employees = await self._employees.find_many({}, limit=1000) if employee_ids else []
        source_map = {s.require_id(): s.name for s in sources if s.require_id() in source_ids}
        employee_map = {e.require_id(): e.display_name for e in employees if e.require_id() in employee_ids}
        return source_map, employee_map

    def download_url(self, s3_key: str | None) -> str | None:
        if not s3_key:
            return None
        return generate_presigned_download_url(s3_key, expires_in=_DOWNLOAD_URL_EXPIRE_SECONDS)

    async def get_advisor_for_lead(self, lead: RecruitmentLead) -> Advisor | None:
        if lead.advisor_id is None:
            return None
        return await self._advisors.find_by_recruitment_lead_id(lead.require_id())

    @staticmethod
    def documents_ready(lead: RecruitmentLead) -> bool:
        return RecruitmentService._documents_ready(lead)

    @staticmethod
    def latest_examination_result(lead: RecruitmentLead) -> str | None:
        latest = RecruitmentService._latest_examination(lead)
        return latest.result if latest is not None else None
