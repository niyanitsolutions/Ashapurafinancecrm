"""Module 6C — Loan Case processing pipeline (docs/MODULE_6C_WORKFLOW_PROPOSAL.md).

Reuses, mostly read-only: Module 6B's `ApplicationRepository`/`ApplicationDocumentRepository`/
`CustomerRepository` — Application's own `draft`/`submitted` status is never touched here,
Module 2's `EmployeeRepository`, Module 4's `LoanProductRepository`/`DocumentTypeRepository`.
The generic `WorkflowEngine` (workflow_engine/engine.py) performs every status transition;
this service supplies loan-specific data/decisions only.

One deliberate, narrow exception to "Application is read-only": `assign_case` also writes
`Application.assigned_to` (see that method) — Application and its Case each used to carry
an independently-editable `assigned_to`, which is exactly why Loan Management could show a
case as assigned while Customer Applications showed the same underlying application as
Unassigned. The two are now kept as mirrors of each other; `CustomerService.
assign_application` performs the matching write in the other direction.

A case is created lazily (get-or-create), not via a live hook into 6B's frozen
`submit_application` — see docs/decisions/DECISIONS.md and
docs/MODULE_6C_WORKFLOW_PROPOSAL.md for why (no code in a frozen module may be modified,
and this project's mongomock-based test infrastructure doesn't support Mongo change
streams). `list_cases`/`list_own_cases` sync any newly-submitted Loan Applications into a
case on every call; `get_own_case`/staff `get_case` also sync individually by
`application_id` so a case is never more than one request away from existing.
"""

from typing import Any, ClassVar

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.constants.roles import EMPLOYEE, OWNER
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.customer.constants import AuditEvent, DocumentAvailabilityStatus
from app.features.customer.models import Application
from app.features.customer.repository import (
    ApplicationDocumentRepository,
    ApplicationRepository,
    CustomerRepository,
)
from app.features.employee.repository import EmployeeRepository
from app.features.loan_management.models import LoanCaseBankOffer
from app.features.loan_management.repository import LoanCaseBankOfferRepository
from app.features.loan_management.schemas import (
    BankDetailsRequest,
    BankOfferRequest,
    CreditEvaluationRequest,
    DisburseRequest,
    EsignNachKycRequest,
    FinalEvaluationRequest,
)
from app.features.system_settings.repository import DocumentTypeRepository, LoanProductRepository
from app.features.workflow_engine.constants import (
    BankOfferDecision,
    CaseType,
    DecisionOutcome,
    DecisionType,
    LoanAuditEvent,
    LoanStatus,
    WorkflowAuditEvent,
)
from app.features.workflow_engine.engine import WorkflowEngine
from app.features.workflow_engine.hold import put_on_hold as engine_put_on_hold
from app.features.workflow_engine.hold import resume_case as engine_resume_case
from app.features.workflow_engine.models import (
    ApplicationDecision,
    ApplicationNote,
    ApplicationWorkflow,
    LoanCaseDetails,
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


class LoanCaseService:
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
        self._products = LoanProductRepository(db)
        self._document_types = DocumentTypeRepository(db)
        self._bank_offers = LoanCaseBankOfferRepository(db)

    # ---------------------------------------------------------------- case sync / lookup

    async def _create_case_for_application(self, application: Application) -> ApplicationWorkflow:
        case_code = await generate_id(self._db, IdPrefix.LOAN_CASE)
        return await self._engine.create_case(
            case_code=case_code, case_type=CaseType.LOAN, application_id=application.require_id(),
            customer_id=application.customer_id or "", product_id=application.product_id,
            product_category=application.product_category, assigned_to=application.assigned_to,
            actor_id=None, initial_status=LoanStatus.NEW_CUSTOMER, loan_details=LoanCaseDetails(),
        )

    async def _sync_new_cases(self) -> None:
        existing = await self._workflows.find_existing_application_ids(CaseType.LOAN)
        submitted = await self._applications.find_many(
            {"status": "submitted", "product_category": "loan", "customer_id": {"$ne": None}}, limit=1000
        )
        for application in submitted:
            if application.require_id() not in existing:
                await self._create_case_for_application(application)

    async def _get_or_create_for_application_id(self, application_id: str) -> ApplicationWorkflow:
        existing = await self._workflows.find_by_application_id(application_id)
        if existing is not None:
            return existing
        application = await self._applications.find_by_id(application_id)
        if application is None or application.status != "submitted" or application.product_category != "loan" or application.customer_id is None:
            raise NotFoundError("No loan case exists for this application.")
        return await self._create_case_for_application(application)

    async def ensure_case_for_application(self, application_id: str) -> ApplicationWorkflow:
        """Public entry point for `CustomerService.submit_application` (see that method) —
        case creation used to be entirely lazy, synced only when someone opened the case
        list (`_sync_new_cases`/`list_own_cases`), so a freshly-submitted application had
        no case, and was invisible to every dashboard/report/notification keyed on cases,
        until a staff member happened to view the list. Idempotent (same underlying
        lookup-or-create as the lazy paths), so calling it eagerly at submission time is
        safe even if a lazy sync also fires for the same application."""
        return await self._get_or_create_for_application_id(application_id)

    async def _acting_employee_id(self, actor: User) -> str | None:
        if actor.role != EMPLOYEE:
            return None
        employee = await self._employees.find_by_user_id(actor.require_id())
        return employee.require_id() if employee else _NO_ASSIGNMENT_SENTINEL

    async def get_case(self, case_id: str, actor: User) -> ApplicationWorkflow:
        case = await self._workflows.find_by_id(case_id)
        if case is None or case.case_type != CaseType.LOAN:
            raise NotFoundError("Loan case not found.")
        if actor.role == EMPLOYEE:
            employee_id = await self._acting_employee_id(actor)
            if case.assigned_to != employee_id:
                raise ForbiddenError("This case isn't assigned to you.")
        return case

    async def get_own_case(self, case_id: str, actor: User) -> ApplicationWorkflow:
        case = await self._workflows.find_by_id(case_id)
        if case is None or case.case_type != CaseType.LOAN:
            raise NotFoundError("Loan case not found.")
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
            case_type=CaseType.LOAN, search=search, customer_id=customer_id, assigned_to=assigned_to,
            unassigned_only=unassigned_only, status=status, skip=skip, limit=limit, sort=sort,
        )

    async def get_counts(self, actor: User) -> dict[str, int]:
        """One count per `LoanStatus.ALL` tab, built from the identical `assigned_to`
        scoping `list_cases` itself applies — a count can never disagree with what its
        matching tab's list call returns, same principle Leads' `get_tab_counts`
        established (decision 125)."""
        await self._sync_new_cases()
        assigned_to: str | None = None
        if actor.role == EMPLOYEE:
            assigned_to = await self._acting_employee_id(actor)
        return {
            status: await self._workflows.count_filtered(case_type=CaseType.LOAN, status=status, assigned_to=assigned_to)
            for status in LoanStatus.ALL
        }

    async def list_own_cases(self, actor: User) -> list[ApplicationWorkflow]:
        applications = await self._applications.find_for_user(actor.require_id(), status="submitted")
        loan_apps = [a for a in applications if a.product_category == "loan" and a.customer_id]
        return [await self._get_or_create_for_application_id(a.require_id()) for a in loan_apps]

    # ---------------------------------------------------------------- assignment

    async def assign_case(self, case_id: str, employee_id: str, actor: User) -> ApplicationWorkflow:
        case = await self._workflows.find_by_id(case_id)
        if case is None or case.case_type != CaseType.LOAN:
            raise NotFoundError("Loan case not found.")
        # This used to go straight to `find_by_id` above with no ownership check at all —
        # an Employee holding only the `assign` permission could reassign ANY case
        # (including one already assigned to a colleague) to themselves, and `get_case`'s
        # `assigned_to` check would then let them straight through on every other action.
        # Picking up a currently-unassigned case is legitimate self-service; reassigning a
        # case someone else already owns is a management action reserved for the Owner.
        if actor.role != OWNER and case.assigned_to is not None:
            raise ForbiddenError("Only an Owner can reassign a case that's already assigned to someone.")
        if await self._employees.find_by_id(employee_id) is None:
            raise ValidationError("Unknown employee_id.")
        is_reassignment = case.assigned_to is not None
        updated = await self._workflows.update(case_id, {"assigned_to": employee_id}, updated_by=actor.require_id())
        if updated is None:
            raise NotFoundError("Loan case not found.")
        await write_audit_log(
            self._db, event_type=WorkflowAuditEvent.CASE_REASSIGNED if is_reassignment else WorkflowAuditEvent.CASE_ASSIGNED,
            user_id=actor.require_id(), metadata={"application_workflow_id": case_id, "employee_id": employee_id},
        )
        # Assignment-consistency fix — see module docstring. Mirrors this reassignment
        # onto the Application the case came from, so Customer Applications / the
        # Customer View can never show a different assignee than this case does.
        if await self._applications.update(case.application_id, {"assigned_to": employee_id}, updated_by=actor.require_id()) is not None:
            await write_audit_log(
                self._db, event_type=AuditEvent.APPLICATION_ASSIGNED, user_id=actor.require_id(),
                metadata={"application_id": case.application_id, "employee_id": employee_id},
            )
        return updated

    # ---------------------------------------------------------------- hold / resume

    async def hold_case(self, case_id: str, reason: str, actor: User, *, remarks: str | None = None) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        return await engine_put_on_hold(self._engine, case, reason, actor, remarks=remarks)

    async def resume_case(self, case_id: str, actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        return await engine_resume_case(self._engine, case, actor)

    # ---------------------------------------------------------------- generic status control

    # (from_status, to_status) pairs the generic Case Status control (detail page dropdown
    # + PATCH /{case_id}/status) is allowed to execute directly — deliberately NOT every
    # edge `WorkflowDefinition.allowed_next_statuses` permits. Every other forward move in
    # this pipeline already requires mandatory business data a bare `{"status": ...,
    # "remarks": ...}` request can't carry (bank-offer selection, Offer Acceptance's own
    # confirm step, eSign/NACH/KYC's completion flags, Final Evaluation's decision+reason,
    # Disbursement's amount+reference, Hold's reason) — those keep using their existing
    # dedicated action/form; this control never bypasses them. Each pair below is a
    # genuinely bodiless move — nothing beyond an optional remark is ever required
    # (decision #129).
    _PLAIN_TRANSITIONS: ClassVar[set[tuple[str, str]]] = {
        (LoanStatus.NEW_CUSTOMER, LoanStatus.CREDIT_EVALUATION),
        (LoanStatus.CREDIT_EVALUATION, LoanStatus.REJECTED),
        (LoanStatus.CREDIT_EVALUATION, LoanStatus.RE_ELIGIBLE),
        (LoanStatus.RE_ELIGIBLE, LoanStatus.CREDIT_EVALUATION),
        (LoanStatus.RE_ELIGIBLE, LoanStatus.REJECTED),
        (LoanStatus.OFFER_ACCEPTANCE, LoanStatus.REJECTED),
        (LoanStatus.ADDITIONAL_DOCUMENTS, LoanStatus.RV_OV_REF),
        (LoanStatus.RV_OV_REF, LoanStatus.ESIGN_NACH_KYC),
    }

    async def update_status(self, case_id: str, new_status: str, actor: User, *, remarks: str | None = None) -> ApplicationWorkflow:
        """The single Case Status control's backend — database status is the only source
        of truth (list/filter/customer portal all read it live, nothing caches a second
        copy). Selecting the case's own current status is a no-op (idempotent, no
        history/audit noise from a double-submit). Any other target must both be a real
        next step per the existing Workflow Engine's transition graph (`WorkflowEngine.
        assert_transition_allowed` — the same check every dedicated action already goes
        through) AND be one of `_PLAIN_TRANSITIONS`; anything else means the target
        status has existing mandatory business data this bare control can't collect, so
        it's rejected with a pointer to the real action instead of silently dropping that
        requirement.
        """
        case = await self.get_case(case_id, actor)
        if new_status == case.current_status:
            return case
        await self._engine.assert_transition_allowed(CaseType.LOAN, case.current_status, new_status)
        transition_key = (case.current_status, new_status)
        if transition_key in self._PLAIN_TRANSITIONS:
            if new_status == LoanStatus.REJECTED and not remarks:
                # Same "rejection reason is mandatory" rule the dedicated Credit/Final
                # Evaluation actions already enforce — the plain control must not offer a
                # quieter way to reject a case with no reason recorded (decision #129).
                raise ValidationError("A reason is mandatory when rejecting a case.")
            updated = await self._engine.transition(case, new_status, actor, remarks=remarks)
            if new_status == LoanStatus.REJECTED:
                updated = await self._workflows.update(case_id, {"rejection_reason": remarks}, updated_by=actor.require_id())
                assert updated is not None
            return updated
        raise ConflictError(
            f"Moving this case to '{new_status}' requires additional information — use the dedicated action for this step instead."
        )

    # ---------------------------------------------------------------- documents

    async def request_documents(self, case_id: str, document_type_ids: list[str], actor: User) -> ApplicationWorkflow:
        """Production redesign (decision #129): used to auto-transition
        `new_customer -> documents_pending` on the first call — that status no longer
        exists in the mandatory pipeline (a Lead only reaches Loan Management once its
        required documents are already verified, decision #127). This is now purely an
        optional, non-pipeline-driving action at either status: it just records which
        document types staff is waiting on; the case's own status only ever moves via
        `update_status`'s plain transitions or `verify_documents` below."""
        case = await self.get_case(case_id, actor)
        if case.current_status not in (LoanStatus.NEW_CUSTOMER, LoanStatus.ADDITIONAL_DOCUMENTS):
            raise ConflictError("Documents cannot be requested at this stage.")
        for doc_type_id in document_type_ids:
            if await self._document_types.find_by_id(doc_type_id) is None:
                raise ValidationError(f"Unknown document_type_id: {doc_type_id}")
        merged = sorted(set(case.pending_document_type_ids) | set(document_type_ids))
        updated = await self._workflows.update(case_id, {"pending_document_type_ids": merged}, updated_by=actor.require_id())
        assert updated is not None
        await write_audit_log(
            self._db, event_type=WorkflowAuditEvent.DOCUMENTS_REQUESTED, user_id=actor.require_id(),
            metadata={"application_workflow_id": case_id, "document_type_ids": document_type_ids},
        )
        return updated

    async def verify_documents(self, case_id: str, actor: User) -> ApplicationWorkflow:
        """Optional dedicated action for staff who actually called `request_documents` —
        confirms every requested type is uploaded, then advances the case. Retargeted
        (decision #129): `new_customer -> credit_evaluation` (previously via
        `documents_pending`) and `additional_documents -> rv_ov_ref` (previously
        `esign_nach_kyc`). Not the only way to reach either target — `update_status`'s
        plain transitions reach the same destinations without a document request ever
        having been made; this is purely a convenience for when one was."""
        case = await self.get_case(case_id, actor)
        if case.current_status not in (LoanStatus.NEW_CUSTOMER, LoanStatus.ADDITIONAL_DOCUMENTS):
            raise ConflictError("This case is not awaiting document verification.")
        # An empty `pending_document_type_ids` (nothing was actually requested — the
        # application's own documents already sufficed) is vacuously satisfied, not an
        # error: verify still advances the case to the next stage.
        uploaded = await self._documents.find_current_for_application(case.application_id)
        uploaded_type_ids = {d.document_type_id for d in uploaded if d.document_status == DocumentAvailabilityStatus.UPLOADED}
        missing = [t for t in case.pending_document_type_ids if t not in uploaded_type_ids]
        if missing:
            raise ValidationError("Not all requested documents have been uploaded yet.")
        next_status = LoanStatus.CREDIT_EVALUATION if case.current_status == LoanStatus.NEW_CUSTOMER else LoanStatus.RV_OV_REF
        return await self._engine.transition(case, next_status, actor, updates={"pending_document_type_ids": []})

    # ---------------------------------------------------------------- bank/NBFC + decisions

    async def record_bank_details(self, case_id: str, payload: BankDetailsRequest, actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        assert case.loan_details is not None
        details = case.loan_details.model_copy(update=payload.model_dump(exclude_unset=True))
        updated = await self._workflows.update(case_id, {"loan_details": details.model_dump()}, updated_by=actor.require_id())
        assert updated is not None
        return updated

    async def credit_evaluation(self, case_id: str, payload: CreditEvaluationRequest, actor: User) -> ApplicationWorkflow:
        """Records the case-level credit score/remarks only (decision #129) — data
        capture, independent of any individual bank/NBFC's own decision (see
        `LoanCaseBankOffer` below) and never itself transitions the case; the case only
        ever leaves Credit Evaluation via a bank-offer selection or the generic plain
        status update (Rejected/Re-Eligible)."""
        case = await self.get_case(case_id, actor)
        if case.current_status != LoanStatus.CREDIT_EVALUATION:
            raise ConflictError("This case is not in credit evaluation.")
        assert case.loan_details is not None
        details = case.loan_details.model_copy(update={"credit_score": payload.credit_score, "credit_remarks": payload.credit_remarks})
        updated = await self._workflows.update(case_id, {"loan_details": details.model_dump()}, updated_by=actor.require_id())
        assert updated is not None
        return updated

    # ---------------------------------------------------------------- bank/NBFC offers

    async def add_bank_offer(self, case_id: str, payload: BankOfferRequest, actor: User) -> LoanCaseBankOffer:
        case = await self.get_case(case_id, actor)
        if case.current_status != LoanStatus.CREDIT_EVALUATION:
            raise ConflictError("Bank offers can only be added while this case is in Credit Evaluation.")
        offer = LoanCaseBankOffer(
            loan_case_id=case_id, bank_name=payload.bank_name, bank_application_id=payload.bank_application_id,
            reference_number=payload.reference_number, assigned_officer=payload.assigned_officer,
            decision=payload.decision, approved_amount=payload.approved_amount, remarks=payload.remarks,
            created_by=actor.require_id(),
        )
        offer_id = await self._bank_offers.insert(offer)
        await write_audit_log(
            self._db, event_type=LoanAuditEvent.BANK_OFFER_ADDED, user_id=actor.require_id(),
            metadata={"application_workflow_id": case_id, "bank_offer_id": offer_id, "bank_name": payload.bank_name, "decision": payload.decision},
        )
        found = await self._bank_offers.find_by_id(offer_id)
        assert found is not None
        return found

    async def update_bank_offer(self, case_id: str, offer_id: str, payload: BankOfferRequest, actor: User) -> LoanCaseBankOffer:
        await self.get_case(case_id, actor)
        offer = await self._bank_offers.find_by_id(offer_id)
        if offer is None or offer.loan_case_id != case_id:
            raise NotFoundError("Bank offer not found.")
        updates = {
            "bank_name": payload.bank_name, "bank_application_id": payload.bank_application_id,
            "reference_number": payload.reference_number, "assigned_officer": payload.assigned_officer,
            "decision": payload.decision, "approved_amount": payload.approved_amount, "remarks": payload.remarks,
        }
        updated = await self._bank_offers.update(offer_id, updates, updated_by=actor.require_id())
        assert updated is not None
        return updated

    async def list_bank_offers(self, case_id: str, actor: User) -> list[LoanCaseBankOffer]:
        await self.get_case(case_id, actor)
        return await self._bank_offers.find_for_case(case_id)

    async def list_bank_offers_own(self, case_id: str, actor: User) -> list[LoanCaseBankOffer]:
        """Customer-facing — approved offers only; the trim down to customer-safe fields
        happens at the mapper layer (never internal fields like bank_application_id/
        assigned_officer/remarks reach a Customer response)."""
        await self.get_own_case(case_id, actor)
        offers = await self._bank_offers.find_for_case(case_id)
        return [o for o in offers if o.decision == BankOfferDecision.APPROVED]

    async def _select_bank_offer_core(self, case: ApplicationWorkflow, offer_id: str, actor: User) -> ApplicationWorkflow:
        """Selection only — marks which offer the case is proceeding with and moves the
        case into `offer_acceptance`. Deliberately does NOT itself complete acceptance;
        `confirm_offer_acceptance` is the separate, explicit second step required to
        advance further (confirmed business requirement, decision #129)."""
        if case.current_status != LoanStatus.CREDIT_EVALUATION:
            raise ConflictError("This case is not awaiting an offer selection.")
        offer = await self._bank_offers.find_by_id(offer_id)
        if offer is None or offer.loan_case_id != case.require_id():
            raise NotFoundError("Bank offer not found.")
        if offer.decision != BankOfferDecision.APPROVED:
            raise ValidationError("Only an Approved offer can be selected.")
        for existing in await self._bank_offers.find_for_case(case.require_id()):
            if existing.is_selected and existing.require_id() != offer_id:
                await self._bank_offers.update(existing.require_id(), {"is_selected": False}, updated_by=actor.require_id())
        now = utc_now()
        await self._bank_offers.update(
            offer_id, {"is_selected": True, "selected_at": now, "selected_by": actor.require_id()}, updated_by=actor.require_id()
        )
        assert case.loan_details is not None
        details = case.loan_details.model_copy(update={"offered_amount": offer.approved_amount, "bank_nbfc_name": offer.bank_name})
        updated = await self._engine.transition(case, LoanStatus.OFFER_ACCEPTANCE, actor, updates={"loan_details": details.model_dump()})
        await write_audit_log(
            self._db, event_type=LoanAuditEvent.BANK_OFFER_SELECTED, user_id=actor.require_id(),
            metadata={"application_workflow_id": case.require_id(), "bank_offer_id": offer_id, "bank_name": offer.bank_name},
        )
        return updated

    async def select_bank_offer(self, case_id: str, offer_id: str, actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        return await self._select_bank_offer_core(case, offer_id, actor)

    async def select_bank_offer_as_customer(self, case_id: str, offer_id: str, actor: User) -> ApplicationWorkflow:
        case = await self.get_own_case(case_id, actor)
        return await self._select_bank_offer_core(case, offer_id, actor)

    # ---------------------------------------------------------------- offer acceptance confirmation

    async def _confirm_offer_acceptance_core(self, case: ApplicationWorkflow, actor: User) -> ApplicationWorkflow:
        if case.current_status != LoanStatus.OFFER_ACCEPTANCE:
            raise ConflictError("This case is not awaiting offer acceptance confirmation.")
        assert case.loan_details is not None
        if case.loan_details.offered_amount is None:
            raise ValidationError("No offer has been selected for this case yet.")
        updated = await self._engine.transition(case, LoanStatus.ADDITIONAL_DOCUMENTS, actor)
        await write_audit_log(
            self._db, event_type=LoanAuditEvent.OFFER_ACCEPTED, user_id=actor.require_id(),
            metadata={"application_workflow_id": case.require_id()},
        )
        return updated

    async def confirm_offer_acceptance(self, case_id: str, actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        return await self._confirm_offer_acceptance_core(case, actor)

    async def confirm_offer_acceptance_as_customer(self, case_id: str, actor: User) -> ApplicationWorkflow:
        case = await self.get_own_case(case_id, actor)
        return await self._confirm_offer_acceptance_core(case, actor)

    async def record_esign_nach_kyc(self, case_id: str, payload: EsignNachKycRequest, actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        if case.current_status != LoanStatus.ESIGN_NACH_KYC:
            raise ConflictError("This case is not awaiting eSign/NACH/KYC.")
        assert case.loan_details is not None
        details = case.loan_details.model_copy(
            update={
                "esign_completed": payload.esign_completed, "nach_completed": payload.nach_completed, "kyc_completed": payload.kyc_completed,
            }
        )
        if payload.esign_completed and payload.nach_completed and payload.kyc_completed:
            return await self._engine.transition(case, LoanStatus.FINAL_EVALUATION, actor, updates={"loan_details": details.model_dump()})
        updated = await self._workflows.update(case_id, {"loan_details": details.model_dump()}, updated_by=actor.require_id())
        assert updated is not None
        return updated

    async def final_evaluation(self, case_id: str, payload: FinalEvaluationRequest, actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        if case.current_status != LoanStatus.FINAL_EVALUATION:
            raise ConflictError("This case is not awaiting final evaluation.")
        assert case.loan_details is not None
        details = case.loan_details.model_copy(update={"final_evaluation_remarks": payload.remarks})
        outcome = DecisionOutcome.APPROVED if payload.decision == "approved" else DecisionOutcome.REJECTED
        await self._decisions.insert(
            ApplicationDecision(
                application_workflow_id=case_id, case_type=CaseType.LOAN, decision_type=DecisionType.FINAL_EVALUATION,
                outcome=outcome, remarks=payload.remarks, created_by=actor.require_id(),
            )
        )
        if payload.decision == "approved":
            return await self._engine.transition(case, LoanStatus.SEND_FOR_DISBURSEMENT, actor, updates={"loan_details": details.model_dump()})
        if not payload.rejection_reason:
            raise ValidationError("A rejection reason is mandatory when rejecting an application.")
        return await self._engine.transition(
            case, LoanStatus.REJECTED, actor,
            updates={"loan_details": details.model_dump(), "rejection_reason": payload.rejection_reason}, remarks=payload.rejection_reason,
        )

    async def disburse(self, case_id: str, payload: DisburseRequest, actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        if case.current_status != LoanStatus.SEND_FOR_DISBURSEMENT:
            raise ConflictError("This case is not ready for disbursement.")
        assert case.loan_details is not None
        details = case.loan_details.model_copy(
            update={"disbursed_amount": payload.disbursed_amount, "disbursed_reference": payload.disbursed_reference, "disbursed_at": utc_now()}
        )
        return await self._engine.transition(case, LoanStatus.DISBURSED, actor, updates={"loan_details": details.model_dump()})

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
