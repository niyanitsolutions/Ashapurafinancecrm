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

import re
from datetime import date
from typing import Any, ClassVar

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.constants.roles import EMPLOYEE, OWNER
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.customer.constants import AuditEvent, DocumentAvailabilityStatus
from app.features.customer.models import Application, Customer
from app.features.customer.repository import (
    ApplicationDocumentRepository,
    ApplicationRepository,
    CustomerRepository,
)
from app.features.employee.repository import EmployeeRepository
from app.features.loan_management.models import LoanCaseAdditionalDocument, LoanCaseBankOffer
from app.features.loan_management.repository import (
    LoanCaseAdditionalDocumentRepository,
    LoanCaseBankOfferRepository,
)
from app.features.loan_management.schemas import (
    AdditionalDocumentUploadUrlRequest,
    BankOfferRequest,
    ConfirmAdditionalDocumentRequest,
    CreditEvaluationRequest,
    DisburseRequest,
    EsignNachKycRequest,
    FinalEvaluationRequest,
    NewCustomerDetailsRequest,
    RvOvRefRequest,
    ScheduleTopUpRequest,
)
from app.features.reminders.constants import NotificationType
from app.features.reminders.service import RemindersService
from app.features.reporting.aggregations import date_range_match
from app.features.system_settings.repository import DocumentTypeRepository, LoanProductRepository
from app.features.workflow_engine.constants import (
    BankOfferDecision,
    CaseType,
    DecisionOutcome,
    DecisionType,
    LoanAuditEvent,
    LoanStatus,
    ReEligibilityPeriod,
    TopUpPeriod,
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
    WorkflowDefinitionRepository,
)
from app.services.storage.client import (
    generate_presigned_download_url,
    generate_presigned_upload_url,
    get_object_size,
)
from app.shared.audit_log import write_audit_log
from app.utils.datetime import add_calendar_months, ensure_utc, ist_date_to_utc_midnight, to_ist, utc_now
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
        self._additional_documents = LoanCaseAdditionalDocumentRepository(db)
        self._definitions = WorkflowDefinitionRepository(db)
        self._reminders = RemindersService(db)

    # ---------------------------------------------------------------- case sync / lookup

    async def _create_case_for_application(self, application: Application) -> ApplicationWorkflow:
        case_code = await generate_id(self._db, IdPrefix.LOAN_CASE)
        # Eligibility gate (decision #130, revised — production fix "DC vs LM"): EVERY
        # new case starts gated (`moved_to_loan_management_at=None`), Lead-originated and
        # Lead-less alike. A Lead-originated application (Flow 1) is ungated by
        # `LeadService.set_stage`'s loan_management branch; a Lead-less application
        # (Flow 2 — the customer registered and applied directly, no Lead ever created)
        # is now ungated by `LeadService.move_lead_less_application_to_loan_management`,
        # which enforces the identical submitted+all-required-documents-verified gate and
        # is what also makes it visible in Document Collection until then (see that
        # module's `_lead_less_document_collection_pool`). Decision #130 originally
        # exempted Flow 2 from this gate entirely ("no Document Collection pipeline
        # exists for it") — that pipeline now exists, so the exemption is removed.
        # Existing production cases that already have this timestamp set from before
        # this change are unaffected (their stored value doesn't change) and correctly
        # remain visible in Loan Management — no migration needed.
        moved_to_loan_management_at = None
        return await self._engine.create_case(
            case_code=case_code, case_type=CaseType.LOAN, application_id=application.require_id(),
            customer_id=application.customer_id or "", product_id=application.product_id,
            product_category=application.product_category, assigned_to=application.assigned_to,
            actor_id=None, initial_status=LoanStatus.NEW_CUSTOMER, loan_details=LoanCaseDetails(),
            moved_to_loan_management_at=moved_to_loan_management_at,
        )

    async def _sync_new_cases(self) -> None:
        # `include_deleted=True`: a submitted Application whose case is currently in the
        # Bin must NOT be re-synced into a fresh case (see
        # `ApplicationWorkflowRepository.find_existing_application_ids`).
        existing = await self._workflows.find_existing_application_ids(CaseType.LOAN, include_deleted=True)
        submitted = await self._applications.find_many(
            {"status": "submitted", "product_category": "loan", "customer_id": {"$ne": None}}, limit=1000
        )
        for application in submitted:
            if application.require_id() not in existing:
                await self._create_case_for_application(application)

    async def _get_or_create_for_application_id(self, application_id: str) -> ApplicationWorkflow | None:
        """Returns the live case for `application_id`, creating one if the application is a
        valid submitted Loan application with none yet. Returns `None` when a case DOES
        exist but is soft-deleted (in the Bin) — the caller must treat that application as
        "has no active case", never re-create it (the unique `application_id` index counts
        the deleted row, and re-creating resurrects a deliberately-binned record)."""
        existing = await self._workflows.find_by_application_id(application_id)
        if existing is not None:
            return existing
        if await self._workflows.find_by_application_id(application_id, include_deleted=True) is not None:
            return None
        application = await self._applications.find_by_id(application_id)
        if application is None or application.status != "submitted" or application.product_category != "loan" or application.customer_id is None:
            raise NotFoundError("No loan case exists for this application.")
        return await self._create_case_for_application(application)

    async def ensure_case_for_application(self, application_id: str) -> ApplicationWorkflow | None:
        """Public entry point for `CustomerService.submit_application` (see that method) —
        case creation used to be entirely lazy, synced only when someone opened the case
        list (`_sync_new_cases`/`list_own_cases`), so a freshly-submitted application had
        no case, and was invisible to every dashboard/report/notification keyed on cases,
        until a staff member happened to view the list. Idempotent (same underlying
        lookup-or-create as the lazy paths), so calling it eagerly at submission time is
        safe even if a lazy sync also fires for the same application. Returns `None` if the
        application's case is currently soft-deleted."""
        return await self._get_or_create_for_application_id(application_id)

    async def mark_moved_to_loan_management(self, application_id: str, actor: User) -> None:
        """Called by `LeadService.set_stage`'s loan_management branch (Lead-originated)
        or `LeadService.move_lead_less_application_to_loan_management` (Lead-less) —
        both only after their own identical eligibility checks (application submitted,
        every required document verified) already passed. This is the ONE method either
        path uses to actually make a case visible in Loan Management (decision #130).
        Idempotent — a no-op if already set, so calling this twice never clobbers the
        original timestamp."""
        case = await self._get_or_create_for_application_id(application_id)
        if case is None:
            return  # the case for this application is currently in the Bin — nothing to move
        if case.moved_to_loan_management_at is not None:
            return
        updated = await self._workflows.update(
            case.require_id(), {"moved_to_loan_management_at": utc_now()}, updated_by=actor.require_id()
        )
        assert updated is not None
        await write_audit_log(
            self._db, event_type=LoanAuditEvent.MOVED_TO_LOAN_MANAGEMENT, user_id=actor.require_id(),
            metadata={"application_workflow_id": case.require_id(), "application_id": application_id},
        )

    async def _acting_employee_id(self, actor: User) -> str | None:
        if actor.role != EMPLOYEE:
            return None
        employee = await self._employees.find_by_user_id(actor.require_id())
        return employee.require_id() if employee else _NO_ASSIGNMENT_SENTINEL

    async def get_case(self, case_id: str, actor: User) -> ApplicationWorkflow:
        case = await self._workflows.find_by_id(case_id)
        if case is None or case.case_type != CaseType.LOAN:
            raise NotFoundError("Loan case not found.")
        # Eligibility gate (decision #130): a case not yet moved into Loan Management must
        # not be reachable through this endpoint either, not just the list — but the Owner
        # is deliberately exempted, for admin/troubleshooting visibility into a case still
        # sitting in Document Collection.
        if case.moved_to_loan_management_at is None and actor.role != OWNER:
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
        if case.moved_to_loan_management_at is None:
            raise NotFoundError("Loan case not found.")
        application = await self._applications.find_by_id(case.application_id)
        if application is None or application.user_id != actor.require_id():
            raise ForbiddenError("This case isn't yours.")
        return case

    async def list_cases(
        self, actor: User, *, search: str | None, customer_id: str | None, assigned_to: str | None,
        unassigned_only: bool, status: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None,
        top_up_eligible: bool = False,
    ) -> tuple[list[ApplicationWorkflow], int]:
        await self._sync_new_cases()
        if actor.role == EMPLOYEE:
            assigned_to = await self._acting_employee_id(actor)
            unassigned_only = False
        extra_filter: dict[str, Any] = dict(self._LOAN_MANAGEMENT_GATE)
        if top_up_eligible:
            # Top Up Loan is a derived view, not a `LoanStatus` value: every case here is
            # still plainly `disbursed`, filtered further to only those whose Top Up
            # eligibility date has actually been reached — see `_TOP_UP_ELIGIBLE_FILTER`.
            status = LoanStatus.DISBURSED
            extra_filter.update(self._top_up_eligible_filter())
        return await self._workflows.search_and_filter(
            case_type=CaseType.LOAN, search=search, customer_id=customer_id, assigned_to=assigned_to,
            unassigned_only=unassigned_only, status=status, skip=skip, limit=limit, sort=sort,
            extra_filter=extra_filter,
        )

    async def get_counts(self, actor: User) -> dict[str, int]:
        """One count per `LoanStatus.ALL` tab, built from the identical `assigned_to`
        scoping `list_cases` itself applies — a count can never disagree with what its
        matching tab's list call returns, same principle Leads' `get_tab_counts`
        established (decision 125). `top_up_eligible` is an additional, non-`LoanStatus`
        count on this same response — see `list_cases`' `top_up_eligible` branch, which
        this must stay consistent with."""
        await self._sync_new_cases()
        assigned_to: str | None = None
        if actor.role == EMPLOYEE:
            assigned_to = await self._acting_employee_id(actor)
        counts = {
            status: await self._workflows.count_filtered(
                case_type=CaseType.LOAN, status=status, assigned_to=assigned_to, extra_filter=self._LOAN_MANAGEMENT_GATE,
            )
            for status in LoanStatus.ALL
        }
        counts["top_up_eligible"] = await self._workflows.count_filtered(
            case_type=CaseType.LOAN, status=LoanStatus.DISBURSED, assigned_to=assigned_to,
            extra_filter={**self._LOAN_MANAGEMENT_GATE, **self._top_up_eligible_filter()},
        )
        return counts

    @staticmethod
    def _top_up_eligible_filter() -> dict[str, Any]:
        return {"loan_details.top_up_eligibility_date": {"$ne": None, "$lte": utc_now()}}

    async def list_own_cases(self, actor: User) -> list[ApplicationWorkflow]:
        applications = await self._applications.find_for_user(actor.require_id(), status="submitted")
        loan_apps = [a for a in applications if a.product_category == "loan" and a.customer_id]
        cases = [await self._get_or_create_for_application_id(a.require_id()) for a in loan_apps]
        # Decision #130: must stay consistent with `get_own_case`'s gate below — a case
        # not yet moved into Loan Management (Lead-originated or Lead-less alike) must
        # not appear in the customer's own list either, or "mine" would show an entry
        # that 404s the moment they click into it. `None` = the case is in the Bin.
        return [c for c in cases if c is not None and c.moved_to_loan_management_at is not None]

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

    # Eligibility gate (decision #130) — applied to every Loan Management list/count
    # query. A case with `moved_to_loan_management_at is None` exists (created lazily at
    # submission) but has not actually entered Loan Management yet.
    _LOAN_MANAGEMENT_GATE: ClassVar[dict[str, Any]] = {"moved_to_loan_management_at": {"$ne": None}}

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
        (LoanStatus.NEW_CUSTOMER, LoanStatus.REJECTED),
        (LoanStatus.NEW_CUSTOMER, LoanStatus.DOCUMENTS_PENDING),
        (LoanStatus.DOCUMENTS_PENDING, LoanStatus.CREDIT_EVALUATION),
        (LoanStatus.DOCUMENTS_PENDING, LoanStatus.REJECTED),
        (LoanStatus.CREDIT_EVALUATION, LoanStatus.REJECTED),
        (LoanStatus.CREDIT_EVALUATION, LoanStatus.RE_ELIGIBLE),
        # Re-Eligible Case Management enhancement — the restart-safe destinations a
        # re-eligible case's "Move Case To" dropdown offers. All genuinely bodiless.
        (LoanStatus.RE_ELIGIBLE, LoanStatus.NEW_CUSTOMER),
        (LoanStatus.RE_ELIGIBLE, LoanStatus.DOCUMENTS_PENDING),
        (LoanStatus.RE_ELIGIBLE, LoanStatus.CREDIT_EVALUATION),
        (LoanStatus.RE_ELIGIBLE, LoanStatus.REJECTED),
        (LoanStatus.OFFER_ACCEPTANCE, LoanStatus.REJECTED),
        (LoanStatus.ADDITIONAL_DOCUMENTS, LoanStatus.RV_OV_REF),
        (LoanStatus.ADDITIONAL_DOCUMENTS, LoanStatus.REJECTED),
        (LoanStatus.RV_OV_REF, LoanStatus.REJECTED),
        (LoanStatus.ESIGN_NACH_KYC, LoanStatus.REJECTED),
        (LoanStatus.SEND_FOR_DISBURSEMENT, LoanStatus.REJECTED),
    }

    async def update_status(
        self, case_id: str, new_status: str, actor: User, *, remarks: str | None = None,
        re_eligibility: str | None = None, re_eligible_date: date | None = None,
    ) -> ApplicationWorkflow:
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
            if transition_key == (LoanStatus.ADDITIONAL_DOCUMENTS, LoanStatus.RV_OV_REF):
                # Requirement 18 — backend-enforced gate: every named Additional Document
                # requested for this case must be verified (none pending/rejected/still
                # unuploaded) before the case can move on. The frontend's own "enabled
                # once all verified" hint is only a courtesy; this is the real check.
                await self._assert_additional_documents_complete(case_id)
            updated = await self._engine.transition(case, new_status, actor, remarks=remarks)
            if new_status == LoanStatus.REJECTED:
                updated = await self._workflows.update(case_id, {"rejection_reason": remarks}, updated_by=actor.require_id())
                assert updated is not None
                # Reject → Re-Eligibility scheduling (production add-on). The frontend
                # popup always sends an explicit choice; a caller that omits it defaults
                # to "No" (never automatically Re-Eligible) — the safe default, never a
                # duration.
                updated = await self._apply_re_eligibility_schedule(
                    case_id, re_eligibility or ReEligibilityPeriod.NO, re_eligible_date, actor
                )
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
        if case.current_status not in (LoanStatus.NEW_CUSTOMER, LoanStatus.DOCUMENTS_PENDING, LoanStatus.ADDITIONAL_DOCUMENTS):
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
        confirms every requested type is uploaded, then advances the case:
        `new_customer`/`documents_pending` -> `credit_evaluation`, `additional_documents`
        -> `rv_ov_ref`. Not the only way to reach either target — `update_status`'s plain
        transitions reach the same destinations without a document request ever having
        been made; this is purely a convenience for when one was."""
        case = await self.get_case(case_id, actor)
        if case.current_status not in (LoanStatus.NEW_CUSTOMER, LoanStatus.DOCUMENTS_PENDING, LoanStatus.ADDITIONAL_DOCUMENTS):
            raise ConflictError("This case is not awaiting document verification.")
        # An empty `pending_document_type_ids` (nothing was actually requested — the
        # application's own documents already sufficed) is vacuously satisfied, not an
        # error: verify still advances the case to the next stage.
        uploaded = await self._documents.find_current_for_application(case.application_id)
        uploaded_type_ids = {d.document_type_id for d in uploaded if d.document_status == DocumentAvailabilityStatus.UPLOADED}
        missing = [t for t in case.pending_document_type_ids if t not in uploaded_type_ids]
        if missing:
            raise ValidationError("Not all requested documents have been uploaded yet.")
        next_status = (
            LoanStatus.RV_OV_REF if case.current_status == LoanStatus.ADDITIONAL_DOCUMENTS else LoanStatus.CREDIT_EVALUATION
        )
        return await self._engine.transition(case, next_status, actor, updates={"pending_document_type_ids": []})

    # ---------------------------------------------------------------- RV / OV / Ref

    async def record_rv_ov_ref(self, case_id: str, payload: RvOvRefRequest, actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        if case.current_status != LoanStatus.RV_OV_REF:
            raise ConflictError("This case is not awaiting RV/OV/Ref verification.")
        assert case.loan_details is not None
        details = case.loan_details.model_copy(update=payload.model_dump())
        updated = await self._engine.transition(case, LoanStatus.ESIGN_NACH_KYC, actor, updates={"loan_details": details.model_dump()})
        await write_audit_log(
            self._db, event_type=LoanAuditEvent.RV_OV_REF_COMPLETED, user_id=actor.require_id(),
            metadata={"application_workflow_id": case_id},
        )
        return updated

    # ---------------------------------------------------------------- New Customer

    async def record_new_customer_details(self, case_id: str, payload: NewCustomerDetailsRequest, actor: User) -> ApplicationWorkflow:
        """New Customer's own bank/branch/loan-type/amount preferences (decision #132) —
        deliberately NOT written onto `bank_nbfc_name`/`bank_application_id`/etc. (those
        are owned exclusively by `_select_bank_offer_core`'s bank-offer-selection flow,
        decision #129) — distinctly-named fields avoid two different concepts writing the
        same field at two different stages. Recording this always advances the case to
        `credit_evaluation`; `new_customer -> credit_evaluation` is no longer a bodiless
        `_PLAIN_TRANSITIONS` move, closing the one-click-no-data-instant-transition bug."""
        case = await self.get_case(case_id, actor)
        if case.current_status != LoanStatus.NEW_CUSTOMER:
            raise ConflictError("New Customer details can only be recorded while this case is at New Customer.")
        assert case.loan_details is not None
        details = case.loan_details.model_copy(update=payload.model_dump())
        updated = await self._engine.transition(case, LoanStatus.CREDIT_EVALUATION, actor, updates={"loan_details": details.model_dump()})
        await write_audit_log(
            self._db, event_type=LoanAuditEvent.NEW_CUSTOMER_DETAILS_RECORDED, user_id=actor.require_id(),
            metadata={"application_workflow_id": case_id},
        )
        return updated

    # ---------------------------------------------------------------- bank/NBFC + decisions

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

    # Bank/NBFC records can now be captured starting at New Customer (this round) — the
    # SAME record is later edited in place at Credit Evaluation to add its decision, so
    # staff is never asked to re-enter data the case already has.
    _BANK_OFFER_EDITABLE_STATUSES: ClassVar[tuple[str, ...]] = (LoanStatus.NEW_CUSTOMER, LoanStatus.CREDIT_EVALUATION)

    async def add_bank_offer(self, case_id: str, payload: BankOfferRequest, actor: User) -> LoanCaseBankOffer:
        case = await self.get_case(case_id, actor)
        if case.current_status not in self._BANK_OFFER_EDITABLE_STATUSES:
            raise ConflictError("Bank offers can only be added while this case is at New Customer or Credit Evaluation.")
        offer = LoanCaseBankOffer(
            loan_case_id=case_id, bank_name=payload.bank_name, branch=payload.branch, loan_type=payload.loan_type,
            requested_amount=payload.requested_amount, bank_application_id=payload.bank_application_id,
            reference_number=payload.reference_number, assigned_officer=payload.assigned_officer,
            decision=payload.decision or BankOfferDecision.PENDING, approved_amount=payload.approved_amount,
            interest_rate=payload.interest_rate, tenure_months=payload.tenure_months, processing_fee=payload.processing_fee,
            emi_per_month=payload.emi_per_month, remarks=payload.remarks, created_by=actor.require_id(),
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
        case = await self.get_case(case_id, actor)
        if case.current_status not in self._BANK_OFFER_EDITABLE_STATUSES:
            raise ConflictError("Bank offers can only be edited while this case is at New Customer or Credit Evaluation.")
        offer = await self._bank_offers.find_by_id(offer_id)
        if offer is None or offer.loan_case_id != case_id:
            raise NotFoundError("Bank offer not found.")
        updates = {
            "bank_name": payload.bank_name, "branch": payload.branch, "loan_type": payload.loan_type,
            "requested_amount": payload.requested_amount, "bank_application_id": payload.bank_application_id,
            "reference_number": payload.reference_number, "assigned_officer": payload.assigned_officer,
            "decision": payload.decision or BankOfferDecision.PENDING, "approved_amount": payload.approved_amount,
            "interest_rate": payload.interest_rate, "tenure_months": payload.tenure_months,
            "processing_fee": payload.processing_fee, "emi_per_month": payload.emi_per_month, "remarks": payload.remarks,
        }
        updated = await self._bank_offers.update(offer_id, updates, updated_by=actor.require_id())
        assert updated is not None
        return updated

    async def delete_bank_offer(self, case_id: str, offer_id: str, actor: User) -> None:
        case = await self.get_case(case_id, actor)
        if case.current_status not in self._BANK_OFFER_EDITABLE_STATUSES:
            raise ConflictError("Bank offers can only be deleted while this case is at New Customer or Credit Evaluation.")
        offer = await self._bank_offers.find_by_id(offer_id)
        if offer is None or offer.loan_case_id != case_id:
            raise NotFoundError("Bank offer not found.")
        if offer.is_selected:
            raise ConflictError("The offer the case has already selected cannot be deleted.")
        deleted = await self._bank_offers.soft_delete(offer_id, deleted_by=actor.require_id())
        if not deleted:
            raise NotFoundError("Bank offer not found.")

    async def move_to_credit_evaluation(self, case_id: str, actor: User, *, remarks: str | None = None) -> ApplicationWorkflow:
        """New Customer's "Move to Credit Evaluation" action (this round) — the bank/NBFC
        records themselves are already saved independently via `add_bank_offer`/
        `update_bank_offer` before this is ever called; this only requires at least one
        exists, then advances the case. Supersedes `record_new_customer_details` as the
        button's backend action (that method is kept, unused by the current frontend, for
        any external/legacy caller)."""
        case = await self.get_case(case_id, actor)
        if case.current_status != LoanStatus.NEW_CUSTOMER:
            raise ConflictError("This case is not at New Customer.")
        offers = await self._bank_offers.find_for_case(case_id)
        if not offers:
            raise ValidationError("Add at least one Bank/NBFC record before moving to Credit Evaluation.")
        return await self._engine.transition(case, LoanStatus.CREDIT_EVALUATION, actor, remarks=remarks)

    async def move_back(self, case_id: str, actor: User, *, remarks: str | None = None) -> ApplicationWorkflow:
        """Generic "Move Back" (this round) — reads the ONE configured previous status
        for the case's current status off `WorkflowDefinition.allowed_previous_statuses`
        (reserved on the schema since Module 6C's first version, wired up for real here)
        and transitions there. Deliberately independent of `_PLAIN_TRANSITIONS` (that set
        is for forward, bodiless moves only) but still goes through the same
        `WorkflowEngine.assert_transition_allowed` check every other transition does."""
        case = await self.get_case(case_id, actor)
        definition = await self._engine.get_definition(CaseType.LOAN, case.current_status)
        if not definition.allowed_previous_statuses:
            raise ConflictError(f"'{case.current_status}' has no configured previous status to move back to.")
        target = definition.allowed_previous_statuses[0]
        return await self._engine.transition(case, target, actor, remarks=remarks)

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
        details = case.loan_details.model_copy(
            update={
                "offered_amount": offer.approved_amount, "bank_nbfc_name": offer.bank_name,
                "offered_interest_rate": offer.interest_rate, "offered_tenure_months": offer.tenure_months,
            }
        )
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
        await self._engine.transition(
            case, LoanStatus.REJECTED, actor,
            updates={"loan_details": details.model_dump(), "rejection_reason": payload.rejection_reason}, remarks=payload.rejection_reason,
        )
        # Reject → Re-Eligibility scheduling — same mechanism as the generic status
        # control's Reject (see `update_status`); an omitted choice defaults to "No".
        return await self._apply_re_eligibility_schedule(
            case_id, payload.re_eligibility or ReEligibilityPeriod.NO, payload.re_eligible_date, actor
        )

    # ---------------------------------------------------------------- Reject → Re-Eligibility scheduling

    _RE_ELIGIBILITY_LABELS: ClassVar[dict[str, str]] = {
        ReEligibilityPeriod.THREE_MONTHS: "3 Months", ReEligibilityPeriod.SIX_MONTHS: "6 Months",
        ReEligibilityPeriod.NINE_MONTHS: "9 Months", ReEligibilityPeriod.TWELVE_MONTHS: "12 Months",
        ReEligibilityPeriod.CUSTOM: "Custom",
    }
    # A custom Re-Eligible date more than this far out is almost certainly a typo.
    _MAX_RE_ELIGIBILITY_MONTHS: ClassVar[int] = 60

    @staticmethod
    def _re_eligibility_note_text(choice: str, re_eligible_date: Any) -> str:
        if choice == ReEligibilityPeriod.NO:
            return "Rejected — Re-Eligibility: No (this case will never automatically become Re-Eligible)."
        label = LoanCaseService._RE_ELIGIBILITY_LABELS.get(choice, choice)
        return f"Rejected — Re-Eligibility scheduled ({label}); eligible from {to_ist(re_eligible_date).strftime('%d %b %Y')}."

    async def _apply_re_eligibility_schedule(
        self, case_id: str, choice: str, custom_date: date | None, actor: User
    ) -> ApplicationWorkflow:
        """Records the per-case Re-Eligibility schedule chosen at rejection time. Called
        right after a case has entered `rejected` (via the generic status control or
        Final Evaluation's reject decision). `choice == "no"` stores an explicit "never"
        (`re_eligible_date` stays None) — the `auto_transition_re_eligible_cases` worker
        job only ever selects cases with a non-null `re_eligible_date`, so a "No" case
        provably never auto-transitions. The eligibility date is always computed from the
        rejection instant (`utc_now()`), same calendar-month math Top Up already uses."""
        if choice not in ReEligibilityPeriod.ALL:
            raise ValidationError(f"'{choice}' is not a valid Re-Eligibility option.")
        case = await self._workflows.find_by_id(case_id)
        assert case is not None and case.loan_details is not None
        now = utc_now()

        if choice == ReEligibilityPeriod.NO:
            re_eligible_date: Any = None
        elif choice == ReEligibilityPeriod.CUSTOM:
            if custom_date is None:
                raise ValidationError("A Re-Eligible date is required when the Re-Eligibility option is 'custom'.")
            re_eligible_date = ist_date_to_utc_midnight(custom_date)
            if re_eligible_date <= now:
                raise ValidationError("The custom Re-Eligible date must be in the future.")
            if re_eligible_date > add_calendar_months(now, self._MAX_RE_ELIGIBILITY_MONTHS):
                raise ValidationError("The custom Re-Eligible date is too far in the future.")
        else:
            re_eligible_date = add_calendar_months(now, ReEligibilityPeriod.MONTHS_BY_PERIOD[choice])

        details = case.loan_details.model_copy(
            update={
                "re_eligibility_choice": choice, "re_eligible_date": re_eligible_date,
                "re_eligibility_scheduled_at": now, "re_eligibility_scheduled_by": actor.require_id(),
                "re_eligibility_auto_transitioned": False,
            }
        )
        updated = await self._workflows.update(case_id, {"loan_details": details.model_dump()}, updated_by=actor.require_id())
        assert updated is not None
        await write_audit_log(
            self._db, event_type=LoanAuditEvent.RE_ELIGIBILITY_SCHEDULED, user_id=actor.require_id(),
            metadata={
                "application_workflow_id": case_id, "choice": choice,
                "re_eligible_date": re_eligible_date.isoformat() if re_eligible_date else None,
            },
        )
        await self._notes.insert(
            ApplicationNote(
                application_workflow_id=case_id, created_by=actor.require_id(),
                text=self._re_eligibility_note_text(choice, re_eligible_date),
            )
        )
        return updated

    async def disburse(self, case_id: str, payload: DisburseRequest, actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        if case.current_status != LoanStatus.SEND_FOR_DISBURSEMENT:
            raise ConflictError("This case is not ready for disbursement.")
        assert case.loan_details is not None
        details = case.loan_details.model_copy(
            update={"disbursed_amount": payload.disbursed_amount, "disbursed_reference": payload.disbursed_reference, "disbursed_at": utc_now()}
        )
        return await self._engine.transition(case, LoanStatus.DISBURSED, actor, updates={"loan_details": details.model_dump()})

    # ---------------------------------------------------------------- Top Up Loan

    @staticmethod
    def _is_top_up_eligible(case: ApplicationWorkflow) -> bool:
        if case.current_status != LoanStatus.DISBURSED or case.loan_details is None:
            return False
        eligibility_date = case.loan_details.top_up_eligibility_date
        return eligibility_date is not None and ensure_utc(eligibility_date) <= utc_now()

    @staticmethod
    def _top_up_note_text(period: str, eligibility_date: Any, remarks: str | None) -> str:
        if period == TopUpPeriod.NO:
            text = "Top Up: customer declined — no eligibility scheduled."
        else:
            label = {"3_months": "3 Months", "6_months": "6 Months", "12_months": "12 Months", "custom": "Custom"}[period]
            text = f"Top Up scheduled ({label}) — eligible from {to_ist(eligibility_date).strftime('%d %b %Y')}."
        return f"{text} Remarks: {remarks}" if remarks else text

    async def schedule_top_up(self, case_id: str, payload: ScheduleTopUpRequest, actor: User) -> ApplicationWorkflow:
        """Backs BOTH the "Top Up" action on a Disbursed row (initial scheduling) and
        "Rejected" on a Top Up Loan row (reject + reschedule) — one endpoint, one popup,
        per spec. Never a `WorkflowEngine` transition: the case stays `current_status=
        disbursed` throughout every Top Up cycle; only `loan_details.top_up_*` changes.
        The eligibility date is always computed from the case's own stored
        `disbursed_at` (never "now"), so repeated reject/reschedule cycles keep anchoring
        to the same original disbursement, exactly as the spec requires."""
        case = await self.get_case(case_id, actor)
        if case.current_status != LoanStatus.DISBURSED:
            raise ValidationError("Only a disbursed case can be scheduled for Top Up.")
        assert case.loan_details is not None
        disbursed_at = case.loan_details.disbursed_at
        if disbursed_at is None:
            raise ValidationError("This case has no recorded disbursement date.")
        disbursed_at = ensure_utc(disbursed_at)

        if payload.period == TopUpPeriod.NO:
            eligibility_date = None
        elif payload.period == TopUpPeriod.CUSTOM:
            assert payload.custom_date is not None  # enforced by ScheduleTopUpRequest
            eligibility_date = ist_date_to_utc_midnight(payload.custom_date)
            if eligibility_date < disbursed_at:
                raise ValidationError("The custom eligibility date cannot be earlier than the disbursed date.")
        else:
            eligibility_date = add_calendar_months(disbursed_at, TopUpPeriod.MONTHS_BY_PERIOD[payload.period])

        details = case.loan_details.model_copy(
            update={
                "top_up_period": payload.period, "top_up_eligibility_date": eligibility_date,
                "top_up_remarks": payload.remarks, "top_up_scheduled_at": utc_now(), "top_up_scheduled_by": actor.require_id(),
            }
        )
        updated = await self._workflows.update(case_id, {"loan_details": details.model_dump()}, updated_by=actor.require_id())
        assert updated is not None
        await write_audit_log(
            self._db, event_type=LoanAuditEvent.TOP_UP_SCHEDULED, user_id=actor.require_id(),
            metadata={
                "application_workflow_id": case_id, "period": payload.period,
                "eligibility_date": eligibility_date.isoformat() if eligibility_date else None,
            },
        )
        await self._notes.insert(
            ApplicationNote(
                application_workflow_id=case_id, created_by=actor.require_id(),
                text=self._top_up_note_text(payload.period, eligibility_date, payload.remarks),
            )
        )
        return updated

    async def move_top_up_to_document_collection(self, case_id: str, actor: User) -> Application:
        """Top Up Loan's "Move to Document Collection" action. Per spec, this must enter
        the EXISTING Leads -> Document Collection -> Loan Management flow completely
        unmodified — never a second, Top-Up-specific Document Collection. The original,
        already-`disbursed` case's history (disbursed_amount/disbursed_at/original
        approval) is never touched; only its `top_up_eligibility_date` is cleared (this
        Top Up slot has now been consumed). A brand-new, ordinary Lead-less `Application`
        is created for the same customer/product via `CustomerService.
        create_application_for_customer` — the exact same Application-creation path a
        customer applying directly through the portal would create for themselves — so
        it surfaces in Document Collection exactly like any other Lead-less application,
        with zero new/duplicated Document Collection logic."""
        case = await self.get_case(case_id, actor)
        if case.current_status != LoanStatus.DISBURSED:
            raise ValidationError("Only a disbursed case can be moved to Document Collection for a Top Up application.")
        if not self._is_top_up_eligible(case):
            raise ValidationError("This case is not currently eligible for Top Up.")

        from app.config.redis import get_redis  # deferred: avoid the customer <-> loan_management import cycle
        from app.features.customer.service import CustomerService

        application = await CustomerService(self._db, get_redis()).create_application_for_customer(
            customer_id=case.customer_id, product_category=case.product_category, product_id=case.product_id, actor=actor,
        )

        assert case.loan_details is not None
        details = case.loan_details.model_copy(update={"top_up_eligibility_date": None})
        await self._workflows.update(case_id, {"loan_details": details.model_dump()}, updated_by=actor.require_id())
        await write_audit_log(
            self._db, event_type=LoanAuditEvent.TOP_UP_MOVED_TO_DOCUMENT_COLLECTION, user_id=actor.require_id(),
            metadata={"application_workflow_id": case_id, "new_application_id": application.require_id()},
        )
        await self._notes.insert(
            ApplicationNote(
                application_workflow_id=case_id, created_by=actor.require_id(),
                text=f"Top Up: moved to Document Collection — new application {application.application_code} started.",
            )
        )
        return application

    # ---------------------------------------------------------------- additional documents (named, ad-hoc)

    _ADDITIONAL_DOCUMENT_KEY_PREFIX = "additional"

    async def _assert_additional_documents_complete(self, case_id: str) -> None:
        docs = await self._additional_documents.find_for_case(case_id)
        unverified = [d for d in docs if d.verification_status != "verified"]
        if unverified:
            raise ValidationError("Every requested Additional Document must be verified before moving to the next stage.")

    async def add_additional_document(self, case_id: str, name: str, actor: User) -> LoanCaseAdditionalDocument:
        case = await self.get_case(case_id, actor)
        if case.current_status != LoanStatus.ADDITIONAL_DOCUMENTS:
            raise ConflictError("Additional documents can only be requested while this case is at Additional Documents.")
        doc = LoanCaseAdditionalDocument(loan_case_id=case_id, application_id=case.application_id, name=name, created_by=actor.require_id())
        doc_id = await self._additional_documents.insert(doc)
        found = await self._additional_documents.find_by_id(doc_id)
        assert found is not None
        return found

    async def list_additional_documents(self, case_id: str, actor: User) -> list[LoanCaseAdditionalDocument]:
        await self.get_case(case_id, actor)
        return await self._additional_documents.find_for_case(case_id)

    async def list_additional_documents_own(self, case_id: str, actor: User) -> list[LoanCaseAdditionalDocument]:
        await self.get_own_case(case_id, actor)
        return await self._additional_documents.find_for_case(case_id)

    def _additional_document_s3_key(self, application_code: str, doc_id: str, file_name: str) -> str:
        # Same convention as Module 6B's own ApplicationDocument keys
        # (`application-documents/{code}/{document_type_id}/{file_name}`) — a distinct
        # `additional/{doc_id}` segment in place of a document_type_id, since these
        # documents have no catalog entry. Same S3 bucket/prefix, no second storage
        # mechanism.
        return f"application-documents/{application_code}/{self._ADDITIONAL_DOCUMENT_KEY_PREFIX}/{doc_id}/{file_name}"

    async def _get_own_additional_document(self, case_id: str, doc_id: str, actor: User) -> tuple[ApplicationWorkflow, LoanCaseAdditionalDocument]:
        case = await self.get_own_case(case_id, actor)
        doc = await self._additional_documents.find_by_id(doc_id)
        if doc is None or doc.loan_case_id != case_id:
            raise NotFoundError("Additional document not found.")
        return case, doc

    async def mint_additional_document_upload_url(
        self, case_id: str, doc_id: str, payload: AdditionalDocumentUploadUrlRequest, actor: User
    ) -> tuple[str, str]:
        case, _doc = await self._get_own_additional_document(case_id, doc_id, actor)
        application = await self._applications.find_by_id(case.application_id)
        if application is None:
            raise NotFoundError("Application not found.")
        s3_key = self._additional_document_s3_key(application.application_code, doc_id, payload.file_name)
        upload_url = generate_presigned_upload_url(s3_key, content_type=payload.content_type)
        return upload_url, s3_key

    async def confirm_additional_document_upload(
        self, case_id: str, doc_id: str, payload: ConfirmAdditionalDocumentRequest, actor: User
    ) -> LoanCaseAdditionalDocument:
        case, doc = await self._get_own_additional_document(case_id, doc_id, actor)
        application = await self._applications.find_by_id(case.application_id)
        if application is None:
            raise NotFoundError("Application not found.")
        # Never trust the client-supplied s3_key — re-derive it the same way the upload
        # URL was minted, same reasoning as Module 6B's `ConfirmDocumentRequest`.
        s3_key = self._additional_document_s3_key(application.application_code, doc_id, payload.file_name)
        size = get_object_size(s3_key)
        if size is None:
            raise ValidationError("The file hasn't finished uploading yet. Please try again in a moment.")
        updated = await self._additional_documents.update(
            doc_id,
            {
                "document_status": "uploaded", "verification_status": "pending", "rejection_reason": None,
                "s3_key": s3_key, "file_name": payload.file_name, "content_type": payload.content_type,
                "file_size_bytes": size, "uploaded_at": utc_now(),
            },
            updated_by=actor.require_id(),
        )
        assert updated is not None
        # Staff notification (requirement 15) — reuses the existing Reminders engine
        # verbatim, same mechanism as every other in-app notification here. Notify the
        # case's assigned employee if there is one, otherwise every Owner (same
        # "notify every Owner" fallback CustomerService.raise_support_request already
        # established).
        if case.assigned_to:
            employee = await self._employees.find_by_id(case.assigned_to)
            if employee is not None:
                await self._reminders.create_notification(
                    recipient_user_id=employee.user_id, notification_type=NotificationType.DOCUMENT_UPLOADED,
                    title="New Additional Document", message=f"Customer uploaded: {doc.name}",
                    entity_type="loan_case", entity_id=case_id,
                )
        else:
            owners = await self._db["users"].find({"role": OWNER, "is_deleted": False}).to_list(length=50)
            for owner_doc in owners:
                await self._reminders.create_notification(
                    recipient_user_id=str(owner_doc["_id"]), notification_type=NotificationType.DOCUMENT_UPLOADED,
                    title="New Additional Document", message=f"Customer uploaded: {doc.name}",
                    entity_type="loan_case", entity_id=case_id,
                )
        return updated

    async def verify_additional_document(self, case_id: str, doc_id: str, actor: User) -> LoanCaseAdditionalDocument:
        await self.get_case(case_id, actor)
        doc = await self._additional_documents.find_by_id(doc_id)
        if doc is None or doc.loan_case_id != case_id:
            raise NotFoundError("Additional document not found.")
        if doc.document_status != "uploaded":
            raise ConflictError("This document hasn't been uploaded yet.")
        updated = await self._additional_documents.update(
            doc_id, {"verification_status": "verified", "rejection_reason": None, "verified_by": actor.require_id(), "verified_at": utc_now()},
            updated_by=actor.require_id(),
        )
        assert updated is not None
        return updated

    async def reject_additional_document(self, case_id: str, doc_id: str, reason: str, actor: User) -> LoanCaseAdditionalDocument:
        case = await self.get_case(case_id, actor)
        doc = await self._additional_documents.find_by_id(doc_id)
        if doc is None or doc.loan_case_id != case_id:
            raise NotFoundError("Additional document not found.")
        if doc.document_status != "uploaded":
            raise ConflictError("This document hasn't been uploaded yet.")
        updated = await self._additional_documents.update(
            doc_id, {"verification_status": "rejected", "rejection_reason": reason, "verified_by": actor.require_id(), "verified_at": utc_now()},
            updated_by=actor.require_id(),
        )
        assert updated is not None
        application = await self._applications.find_by_id(case.application_id)
        if application is not None:
            await self._reminders.notify(
                recipient_user_id=application.user_id, notification_type=NotificationType.DOCUMENT_REJECTED,
                default_title="Document Rejected", default_message=f"Your {doc.name} was rejected. {reason}",
                variables={"document_name": doc.name, "reason": reason},
                entity_type="loan_case", entity_id=case_id,
            )
        return updated

    def additional_document_download_url(self, doc: LoanCaseAdditionalDocument) -> str | None:
        return generate_presigned_download_url(doc.s3_key) if doc.s3_key else None

    def additional_document_attachment_url(self, doc: LoanCaseAdditionalDocument) -> str | None:
        if not doc.s3_key or not doc.file_name:
            return None
        return generate_presigned_download_url(doc.s3_key, response_content_disposition=f'attachment; filename="{doc.file_name}"')

    # ---------------------------------------------------------------- notes / timeline

    async def add_note(self, case_id: str, text: str, actor: User) -> ApplicationNote:
        await self.get_case(case_id, actor)
        note = ApplicationNote(application_workflow_id=case_id, text=text, created_by=actor.require_id())
        note_id = await self._notes.insert(note)
        await write_audit_log(self._db, event_type=WorkflowAuditEvent.NOTE_ADDED, user_id=actor.require_id(), metadata={"application_workflow_id": case_id})
        found = await self._notes.find_by_id(note_id)
        assert found is not None
        return found

    async def add_follow_up(self, case_id: str, comment: str, follow_up_date: date | None, actor: User) -> ApplicationWorkflow:
        """Re-Eligible Case Management enhancement — a follow-up comment (a NEW
        `ApplicationNote`, never overwriting a prior one, exactly like `add_note`) plus an
        optional follow-up date. When a date is given it's also denormalised onto
        `ApplicationWorkflow.next_follow_up_date` (the case's current follow-up plan — same
        overwrite semantics as `LeadService.set_follow_up`). The follow-up date is NEVER
        used to move the case automatically; it's a reminder only."""
        case = await self.get_case(case_id, actor)
        fu_utc = ist_date_to_utc_midnight(follow_up_date) if follow_up_date is not None else None
        note = ApplicationNote(
            application_workflow_id=case_id, text=comment, follow_up_date=fu_utc, created_by=actor.require_id(),
        )
        await self._notes.insert(note)
        await write_audit_log(
            self._db, event_type=WorkflowAuditEvent.NOTE_ADDED, user_id=actor.require_id(),
            metadata={"application_workflow_id": case_id, "follow_up_date": follow_up_date.isoformat() if follow_up_date else None},
        )
        if fu_utc is not None:
            updated = await self._workflows.update(case_id, {"next_follow_up_date": fu_utc}, updated_by=actor.require_id())
            assert updated is not None
            return updated
        return case

    async def get_timeline(self, case_id: str, actor: User) -> list[tuple[str, Any]]:
        await self.get_case(case_id, actor)
        history = await self._history.find_for_workflow(case_id)
        notes = await self._notes.find_for_workflow(case_id)
        combined: list[tuple[str, Any]] = [("status", h) for h in history] + [("note", n) for n in notes]
        combined.sort(key=lambda entry: entry[1].created_at, reverse=True)
        return combined

    async def status_transition_map(self) -> dict[str, list[str]]:
        """One `{status: allowed_next_statuses}` lookup, batch-fetched once per
        request (list/detail) rather than per row — lets responses surface the backend's
        real, configured transition graph instead of only the frontend's hand-maintained
        UX hint (`statusControl.ts`)."""
        definitions = await self._definitions.find_for_case_type(CaseType.LOAN)
        return {d.status: d.allowed_next_statuses for d in definitions}

    async def previous_status_map(self) -> dict[str, list[str]]:
        """Same batch-fetch pattern as `status_transition_map`, for the new "Move Back"
        feature's `allowed_previous_statuses` instead of `allowed_next_statuses`."""
        definitions = await self._definitions.find_for_case_type(CaseType.LOAN)
        return {d.status: d.allowed_previous_statuses for d in definitions}

    # ---------------------------------------------------------------- complete application view

    async def get_case_context(self, case: ApplicationWorkflow) -> tuple[Customer | None, Application | None, list[LoanCaseBankOffer]]:
        """Requirement 21 — the Loan Case View's "complete application" data, all sourced
        from repositories this service already holds read-only references to (no new
        cross-module coupling). Returns `None` for customer/application gracefully rather
        than raising, so a legacy or inconsistent record still renders the rest of the
        page (requirement 33)."""
        customer = await self._customers.find_by_id(case.customer_id) if case.customer_id else None
        application = await self._applications.find_by_id(case.application_id)
        bank_offers = await self._bank_offers.find_for_case(case.require_id())
        return customer, application, bank_offers

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

    # ---------------------------------------------------------------- disbursements report

    async def list_disbursements(
        self, actor: User, *, date_from: date | None, date_to: date | None, product_id: str | None, search: str | None, skip: int, limit: int,
    ) -> tuple[list[ApplicationWorkflow], int, float]:
        """One `$facet` aggregation — list page, total count, and total amount all read
        off the SAME filtered match (requirement 29: card/table/pagination can never
        disagree, because there is only one query to disagree with). `actor` is accepted
        for symmetry with every other list method here and because the router's
        `_perm("view")` dependency already gates the endpoint; no further per-row scoping
        is applied — Disbursements is a company-wide report, same visibility rule as the
        existing Disbursed tab and `loan_disbursed` report definition."""
        match: dict[str, Any] = {"is_deleted": False, "case_type": CaseType.LOAN, "current_status": LoanStatus.DISBURSED}
        match.update(date_range_match("loan_details.disbursed_at", date_from, date_to))
        if product_id:
            match["product_id"] = product_id
        if search:
            match["case_code"] = re.compile(re.escape(search), re.IGNORECASE)

        pipeline: list[dict[str, Any]] = [
            {"$match": match},
            {"$sort": {"loan_details.disbursed_at": -1}},
            {
                "$facet": {
                    "items": [{"$skip": skip}, {"$limit": limit}],
                    "count": [{"$count": "total"}],
                    "sum": [{"$group": {"_id": None, "total_amount": {"$sum": "$loan_details.disbursed_amount"}}}],
                }
            },
        ]
        result = await self._workflows.collection.aggregate(pipeline).to_list(length=1)
        facet = result[0] if result else {"items": [], "count": [], "sum": []}
        items = [ApplicationWorkflow.model_validate(doc) for doc in facet["items"]]
        total_count = facet["count"][0]["total"] if facet["count"] else 0
        total_amount = facet["sum"][0]["total_amount"] if facet["sum"] else 0.0
        return items, total_count, float(total_amount or 0.0)
