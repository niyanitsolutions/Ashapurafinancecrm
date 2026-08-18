"""Module 6C — Insurance Case processing pipeline (docs/MODULE_6C_WORKFLOW_PROPOSAL.md).

Finalized lifecycle (decision 064, superseding the draft flagged as an assumption in
decision 057): Application Submitted -> Documents Pending -> Underwriting -> [Medical
Verification, optional] -> [Additional Documents, optional] -> Premium Acceptance ->
Policy Generation -> Policy Issued, with Rejected reachable from Underwriting or Medical
Verification. Whether Medical Verification and/or Additional Documents are needed is a
per-case judgment the underwriter records during Underwriting — never a fixed product
attribute. Policy Generation (the policy number/document is prepared) and Policy Issued
(terminal) are deliberately two distinct statuses, not one.

Same reuse posture as Loan: Module 6B's `Application`/`ApplicationDocument` are read-only,
never modified.
"""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.constants.roles import EMPLOYEE, OWNER
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.customer.constants import DocumentAvailabilityStatus
from app.features.customer.models import Application
from app.features.customer.repository import (
    ApplicationDocumentRepository,
    ApplicationRepository,
    CustomerRepository,
)
from app.features.employee.repository import EmployeeRepository
from app.features.insurance_management.schemas import (
    GeneratePolicyRequest,
    MedicalVerificationRequest,
    PremiumRequest,
    UnderwritingRequest,
)
from app.features.system_settings.repository import (
    DocumentTypeRepository,
    InsuranceProductRepository,
)
from app.features.workflow_engine.constants import (
    CaseType,
    DecisionOutcome,
    DecisionType,
    InsuranceStatus,
    OfferDecision,
    WorkflowAuditEvent,
)
from app.features.workflow_engine.engine import WorkflowEngine
from app.features.workflow_engine.hold import put_on_hold as engine_put_on_hold
from app.features.workflow_engine.hold import resume_case as engine_resume_case
from app.features.workflow_engine.models import (
    ApplicationDecision,
    ApplicationNote,
    ApplicationWorkflow,
    InsuranceCaseDetails,
)
from app.features.workflow_engine.repository import (
    ApplicationDecisionRepository,
    ApplicationNoteRepository,
    ApplicationStatusHistoryRepository,
    ApplicationWorkflowRepository,
)
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now
from app.utils.id_generator import IdPrefix, generate_id

_NO_ASSIGNMENT_SENTINEL = "___none___"
_DOCUMENT_REQUEST_STATUSES = (InsuranceStatus.APPLICATION_SUBMITTED, InsuranceStatus.ADDITIONAL_DOCUMENTS)
_DOCUMENT_VERIFY_STATUSES = (InsuranceStatus.DOCUMENTS_PENDING, InsuranceStatus.ADDITIONAL_DOCUMENTS)


class InsuranceCaseService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self._db = db
        self._engine = WorkflowEngine(db)
        self._workflows = ApplicationWorkflowRepository(db)
        self._history = ApplicationStatusHistoryRepository(db)
        self._notes = ApplicationNoteRepository(db)
        self._decisions = ApplicationDecisionRepository(db)
        self._applications = ApplicationRepository(db)
        self._documents = ApplicationDocumentRepository(db)
        self._customers = CustomerRepository(db)
        self._employees = EmployeeRepository(db)
        self._products = InsuranceProductRepository(db)
        self._document_types = DocumentTypeRepository(db)

    # ---------------------------------------------------------------- case sync / lookup

    async def _create_case_for_application(self, application: Application) -> ApplicationWorkflow:
        case_code = await generate_id(self._db, IdPrefix.INSURANCE_CASE)
        return await self._engine.create_case(
            case_code=case_code, case_type=CaseType.INSURANCE, application_id=application.require_id(),
            customer_id=application.customer_id or "", product_id=application.product_id,
            product_category=application.product_category, assigned_to=application.assigned_to,
            actor_id=None, initial_status=InsuranceStatus.APPLICATION_SUBMITTED, insurance_details=InsuranceCaseDetails(),
        )

    async def _sync_new_cases(self) -> None:
        existing = await self._workflows.find_existing_application_ids(CaseType.INSURANCE)
        submitted = await self._applications.find_many(
            {"status": "submitted", "product_category": "insurance", "customer_id": {"$ne": None}}, limit=1000
        )
        for application in submitted:
            if application.require_id() not in existing:
                await self._create_case_for_application(application)

    async def _get_or_create_for_application_id(self, application_id: str) -> ApplicationWorkflow:
        existing = await self._workflows.find_by_application_id(application_id)
        if existing is not None:
            return existing
        application = await self._applications.find_by_id(application_id)
        if application is None or application.status != "submitted" or application.product_category != "insurance" or application.customer_id is None:
            raise NotFoundError("No insurance case exists for this application.")
        return await self._create_case_for_application(application)

    async def ensure_case_for_application(self, application_id: str) -> ApplicationWorkflow:
        """See the identical method on `LoanCaseService` — public entry point for
        `CustomerService.submit_application` so case creation happens at submission time
        instead of being purely lazy."""
        return await self._get_or_create_for_application_id(application_id)

    async def _acting_employee_id(self, actor: User) -> str | None:
        if actor.role != EMPLOYEE:
            return None
        employee = await self._employees.find_by_user_id(actor.require_id())
        return employee.require_id() if employee else _NO_ASSIGNMENT_SENTINEL

    async def get_case(self, case_id: str, actor: User) -> ApplicationWorkflow:
        case = await self._workflows.find_by_id(case_id)
        if case is None or case.case_type != CaseType.INSURANCE:
            raise NotFoundError("Insurance case not found.")
        if actor.role == EMPLOYEE:
            employee_id = await self._acting_employee_id(actor)
            if case.assigned_to != employee_id:
                raise ForbiddenError("This case isn't assigned to you.")
        return case

    async def get_own_case(self, case_id: str, actor: User) -> ApplicationWorkflow:
        case = await self._workflows.find_by_id(case_id)
        if case is None or case.case_type != CaseType.INSURANCE:
            raise NotFoundError("Insurance case not found.")
        application = await self._applications.find_by_id(case.application_id)
        if application is None or application.user_id != actor.require_id():
            raise ForbiddenError("This case isn't yours.")
        return case

    async def list_cases(
        self, actor: User, *, search: str | None, customer_id: str | None, assigned_to: str | None,
        unassigned_only: bool, status: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None,
    ) -> tuple[list[ApplicationWorkflow], int]:
        await self._sync_new_cases()
        if actor.role == EMPLOYEE:
            assigned_to = await self._acting_employee_id(actor)
            unassigned_only = False
        return await self._workflows.search_and_filter(
            case_type=CaseType.INSURANCE, search=search, customer_id=customer_id, assigned_to=assigned_to,
            unassigned_only=unassigned_only, status=status, skip=skip, limit=limit, sort=sort,
        )

    async def list_own_cases(self, actor: User) -> list[ApplicationWorkflow]:
        applications = await self._applications.find_for_user(actor.require_id(), status="submitted")
        insurance_apps = [a for a in applications if a.product_category == "insurance" and a.customer_id]
        return [await self._get_or_create_for_application_id(a.require_id()) for a in insurance_apps]

    # ---------------------------------------------------------------- assignment

    async def assign_case(self, case_id: str, employee_id: str, actor: User) -> ApplicationWorkflow:
        case = await self._workflows.find_by_id(case_id)
        if case is None or case.case_type != CaseType.INSURANCE:
            raise NotFoundError("Insurance case not found.")
        # See the identical comment in loan_management/service.py::assign_case — an
        # Employee holding only `assign` could otherwise reassign any already-assigned
        # case (including a colleague's) to themselves and gain full access via
        # `get_case`'s `assigned_to` check. Unassigned-case pickup stays self-service;
        # reassigning someone else's case is an Owner action.
        if actor.role != OWNER and case.assigned_to is not None:
            raise ForbiddenError("Only an Owner can reassign a case that's already assigned to someone.")
        if await self._employees.find_by_id(employee_id) is None:
            raise ValidationError("Unknown employee_id.")
        is_reassignment = case.assigned_to is not None
        updated = await self._workflows.update(case_id, {"assigned_to": employee_id}, updated_by=actor.require_id())
        if updated is None:
            raise NotFoundError("Insurance case not found.")
        await write_audit_log(
            self._db, event_type=WorkflowAuditEvent.CASE_REASSIGNED if is_reassignment else WorkflowAuditEvent.CASE_ASSIGNED,
            user_id=actor.require_id(), metadata={"application_workflow_id": case_id, "employee_id": employee_id},
        )
        return updated

    # ---------------------------------------------------------------- hold / resume

    async def hold_case(self, case_id: str, reason: str, actor: User, *, remarks: str | None = None) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        return await engine_put_on_hold(self._engine, case, reason, actor, remarks=remarks)

    async def resume_case(self, case_id: str, actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        return await engine_resume_case(self._engine, case, actor)

    # ---------------------------------------------------------------- documents

    async def request_documents(self, case_id: str, document_type_ids: list[str], actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        if case.current_status not in _DOCUMENT_REQUEST_STATUSES:
            raise ConflictError("Documents cannot be requested at this stage.")
        for doc_type_id in document_type_ids:
            if await self._document_types.find_by_id(doc_type_id) is None:
                raise ValidationError(f"Unknown document_type_id: {doc_type_id}")
        merged = sorted(set(case.pending_document_type_ids) | set(document_type_ids))

        updated: ApplicationWorkflow | None
        if case.current_status == InsuranceStatus.APPLICATION_SUBMITTED:
            # The first document request is what actually begins "Documents Pending" —
            # there's no separate manual action between case creation and this.
            updated = await self._engine.transition(case, InsuranceStatus.DOCUMENTS_PENDING, actor, updates={"pending_document_type_ids": merged})
        else:
            updated = await self._workflows.update(case_id, {"pending_document_type_ids": merged}, updated_by=actor.require_id())
            assert updated is not None

        await write_audit_log(
            self._db, event_type=WorkflowAuditEvent.DOCUMENTS_REQUESTED, user_id=actor.require_id(),
            metadata={"application_workflow_id": case_id, "document_type_ids": document_type_ids},
        )
        return updated

    async def verify_documents(self, case_id: str, actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        if case.current_status not in _DOCUMENT_VERIFY_STATUSES:
            raise ConflictError("This case is not awaiting document verification.")
        # An empty `pending_document_type_ids` (nothing was actually requested) is
        # vacuously satisfied, not an error — verify still advances the case.
        uploaded = await self._documents.find_current_for_application(case.application_id)
        uploaded_type_ids = {d.document_type_id for d in uploaded if d.document_status == DocumentAvailabilityStatus.UPLOADED}
        missing = [t for t in case.pending_document_type_ids if t not in uploaded_type_ids]
        if missing:
            raise ValidationError("Not all requested documents have been uploaded yet.")
        next_status = InsuranceStatus.UNDERWRITING if case.current_status == InsuranceStatus.DOCUMENTS_PENDING else InsuranceStatus.PREMIUM_ACCEPTANCE
        return await self._engine.transition(case, next_status, actor, updates={"pending_document_type_ids": []})

    # ---------------------------------------------------------------- decisions

    async def underwriting(self, case_id: str, payload: UnderwritingRequest, actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        if case.current_status != InsuranceStatus.UNDERWRITING:
            raise ConflictError("This case is not awaiting underwriting.")
        assert case.insurance_details is not None
        details = case.insurance_details.model_copy(
            update={
                "sum_insured": payload.sum_insured, "underwriting_remarks": payload.underwriting_remarks,
                "requires_medical": payload.requires_medical, "requires_additional_documents": payload.requires_additional_documents,
            }
        )
        outcome = DecisionOutcome.APPROVED if payload.decision == "approved" else DecisionOutcome.REJECTED
        await self._decisions.insert(
            ApplicationDecision(
                application_workflow_id=case_id, case_type=CaseType.INSURANCE, decision_type=DecisionType.UNDERWRITING,
                outcome=outcome, remarks=payload.underwriting_remarks, created_by=actor.require_id(),
            )
        )
        if payload.decision == "approved":
            if payload.requires_medical:
                next_status = InsuranceStatus.MEDICAL_VERIFICATION
            elif payload.requires_additional_documents:
                next_status = InsuranceStatus.ADDITIONAL_DOCUMENTS
            else:
                next_status = InsuranceStatus.PREMIUM_ACCEPTANCE
            return await self._engine.transition(case, next_status, actor, updates={"insurance_details": details.model_dump()})
        if not payload.rejection_reason:
            raise ValidationError("A rejection reason is mandatory when rejecting an application.")
        return await self._engine.transition(
            case, InsuranceStatus.REJECTED, actor,
            updates={"insurance_details": details.model_dump(), "rejection_reason": payload.rejection_reason}, remarks=payload.rejection_reason,
        )

    async def medical_verification(self, case_id: str, payload: MedicalVerificationRequest, actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        if case.current_status != InsuranceStatus.MEDICAL_VERIFICATION:
            raise ConflictError("This case is not awaiting medical verification.")
        assert case.insurance_details is not None
        details = case.insurance_details.model_copy(
            update={"medical_verification_outcome": payload.outcome, "medical_verification_remarks": payload.medical_remarks}
        )
        outcome = DecisionOutcome.CLEARED if payload.outcome == "cleared" else DecisionOutcome.FAILED
        await self._decisions.insert(
            ApplicationDecision(
                application_workflow_id=case_id, case_type=CaseType.INSURANCE, decision_type=DecisionType.MEDICAL_VERIFICATION,
                outcome=outcome, remarks=payload.medical_remarks, created_by=actor.require_id(),
            )
        )
        if payload.outcome == "cleared":
            next_status = InsuranceStatus.ADDITIONAL_DOCUMENTS if details.requires_additional_documents else InsuranceStatus.PREMIUM_ACCEPTANCE
            return await self._engine.transition(case, next_status, actor, updates={"insurance_details": details.model_dump()})
        if not payload.rejection_reason:
            raise ValidationError("A rejection reason is mandatory when rejecting an application.")
        return await self._engine.transition(
            case, InsuranceStatus.REJECTED, actor,
            updates={"insurance_details": details.model_dump(), "rejection_reason": payload.rejection_reason}, remarks=payload.rejection_reason,
        )

    async def record_premium(self, case_id: str, payload: PremiumRequest, actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        if case.current_status != InsuranceStatus.PREMIUM_ACCEPTANCE:
            raise ConflictError("This case is not awaiting a premium quote.")
        assert case.insurance_details is not None
        details = case.insurance_details.model_copy(update={"premium_amount": payload.premium_amount, "premium_decision": OfferDecision.PENDING})
        updated = await self._workflows.update(case_id, {"insurance_details": details.model_dump()}, updated_by=actor.require_id())
        assert updated is not None
        return updated

    async def accept_premium(self, case_id: str, actor: User) -> ApplicationWorkflow:
        case = await self.get_own_case(case_id, actor)
        if case.current_status != InsuranceStatus.PREMIUM_ACCEPTANCE:
            raise ConflictError("This case is not awaiting a premium decision.")
        assert case.insurance_details is not None
        if case.insurance_details.premium_amount is None:
            raise ValidationError("No premium quote has been issued for this case yet.")
        details = case.insurance_details.model_copy(update={"premium_decision": OfferDecision.ACCEPTED})
        return await self._engine.transition(case, InsuranceStatus.POLICY_GENERATION, actor, updates={"insurance_details": details.model_dump()})

    async def decline_premium(self, case_id: str, actor: User) -> ApplicationWorkflow:
        case = await self.get_own_case(case_id, actor)
        if case.current_status != InsuranceStatus.PREMIUM_ACCEPTANCE:
            raise ConflictError("This case is not awaiting a premium decision.")
        assert case.insurance_details is not None
        details = case.insurance_details.model_copy(update={"premium_decision": OfferDecision.DECLINED})
        reason = "Customer declined the premium quote."
        return await self._engine.transition(
            case, InsuranceStatus.REJECTED, actor, updates={"insurance_details": details.model_dump(), "rejection_reason": reason}, remarks=reason
        )

    async def generate_policy(self, case_id: str, payload: GeneratePolicyRequest, actor: User) -> ApplicationWorkflow:
        """Policy Generation is its own event, distinct from Policy Issued: records the
        policy number/document but keeps the case in `policy_generation` — a separate
        `issue_policy` action moves it to the terminal `policy_issued` status."""
        case = await self.get_case(case_id, actor)
        if case.current_status != InsuranceStatus.POLICY_GENERATION:
            raise ConflictError("This case is not awaiting policy generation.")
        assert case.insurance_details is not None
        details = case.insurance_details.model_copy(update={"policy_number": payload.policy_number, "policy_generated_at": utc_now()})
        updated = await self._workflows.update(case_id, {"insurance_details": details.model_dump()}, updated_by=actor.require_id())
        assert updated is not None
        return updated

    async def issue_policy(self, case_id: str, actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        if case.current_status != InsuranceStatus.POLICY_GENERATION:
            raise ConflictError("This case is not ready to be issued.")
        assert case.insurance_details is not None
        if not case.insurance_details.policy_number:
            raise ValidationError("Generate the policy number before issuing it.")
        details = case.insurance_details.model_copy(update={"policy_issued_at": utc_now()})
        return await self._engine.transition(case, InsuranceStatus.POLICY_ISSUED, actor, updates={"insurance_details": details.model_dump()})

    # ---------------------------------------------------------------- notes / timeline

    async def add_note(self, case_id: str, text: str, actor: User) -> ApplicationNote:
        await self.get_case(case_id, actor)
        note = ApplicationNote(application_workflow_id=case_id, text=text, created_by=actor.require_id())
        note_id = await self._notes.insert(note)
        await write_audit_log(self._db, event_type=WorkflowAuditEvent.NOTE_ADDED, user_id=actor.require_id(), metadata={"application_workflow_id": case_id})
        found = await self._notes.find_by_id(note_id)
        assert found is not None
        return found

    async def get_timeline(self, case_id: str, actor: User) -> list[tuple[str, Any]]:
        await self.get_case(case_id, actor)
        history = await self._history.find_for_workflow(case_id)
        notes = await self._notes.find_for_workflow(case_id)
        combined: list[tuple[str, Any]] = [("status", h) for h in history] + [("note", n) for n in notes]
        combined.sort(key=lambda entry: entry[1].created_at, reverse=True)
        return combined

    # ---------------------------------------------------------------- name resolution

    async def resolve_names(self, cases: list[ApplicationWorkflow]) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
        customer_ids = {c.customer_id for c in cases if c.customer_id}
        product_ids = {c.product_id for c in cases}
        employee_ids = {c.assigned_to for c in cases if c.assigned_to}

        customers = await self._customers.find_many({}, limit=1000) if customer_ids else []
        products = await self._products.find_many({}, limit=500)
        employees = await self._employees.find_many({}, limit=500) if employee_ids else []

        customer_map = {c.require_id(): c.full_name for c in customers if c.require_id() in customer_ids}
        product_map = {p.require_id(): p.name for p in products if p.require_id() in product_ids}
        employee_map = {e.require_id(): e.display_name for e in employees if e.require_id() in employee_ids}
        return customer_map, product_map, employee_map
