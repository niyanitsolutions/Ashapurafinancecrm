"""Module 6C — Insurance "Policy Leads" pipeline.

Policy Leads redesign (2026-09-07) — a FULL REPLACE of the decision-064 lifecycle:

    Fresh Lead ─► Policy Document ─► Policy Login ─► Policy Issued
        │               │                │
        └──────┬────────┴────────┬───────┘
               ▼                 ▼
           Rejected  ◄──────  (any non-terminal stage; + On Hold from any)
               │
               ▼
          Re-Eligible ─► Fresh Lead / Policy Document   (restart)

The underwriting / medical-verification / additional-documents / premium-acceptance /
policy-generation statuses and the customer premium accept/decline endpoints are gone.
`Move Back` is wired for insurance (`policy_login → policy_document`,
`policy_document → fresh_lead`). `Policy Document → Policy Login` is backend-gated on
**every non-hidden required document of the pinned Product Schema being VERIFIED**
(front+back needs both sides verified). Premium / PPT / PT are recorded by staff at
Policy Login (`update_policy_login`), which also allows a product change
(`change_product` — re-resolves the schema, preserves uploaded documents).

Same reuse posture as Loan for Module 6B's `Application`/`ApplicationDocument`: mostly
read-only, with two deliberate exceptions — `assign_case` mirrors `Application.
assigned_to`, and `change_product` mirrors `Application.product_id`/`form_definition_id`
(so Customer Applications never diverge from the case). See `loan_management/service.py`
for the full rationale.
"""

from datetime import date
from typing import Any, ClassVar

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.config.redis import get_redis
from app.constants.roles import EMPLOYEE, OWNER
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.customer.constants import DocumentSide, DocumentVerificationStatus
from app.features.customer.models import Application, ApplicationDocument
from app.features.customer.repository import (
    ApplicationDocumentRepository,
    ApplicationFormDefinitionRepository,
    ApplicationRepository,
    CustomerRepository,
)
from app.features.customer.service import CustomerService
from app.features.employee.repository import EmployeeRepository
from app.features.insurance_management.constants import InsurancePaymentStatus
from app.features.insurance_management.models import (
    InsuranceCaseAdditionalDocument,
    InsurancePaymentTransaction,
)
from app.features.insurance_management.repository import (
    InsuranceCaseAdditionalDocumentRepository,
    InsurancePaymentTransactionRepository,
)
from app.features.insurance_management.schemas import (
    ConfirmOtherDocumentRequest,
    CreateManualInsuranceCaseRequest,
    OtherDocumentUploadUrlRequest,
    PaymentUpdateRequest,
    PolicyLoginUpdateRequest,
)
from app.features.recruitment.constants import AdvisorStatus
from app.features.recruitment.repository import AdvisorRepository
from app.features.reminders.constants import NotificationType
from app.features.reminders.service import RemindersService
from app.features.system_settings.constants import MasterDataStatus
from app.features.system_settings.repository import (
    DocumentTypeRepository,
    InsuranceCategoryRepository,
    InsuranceProductRepository,
)
from app.features.workflow_engine.constants import (
    CaseType,
    InsuranceAuditEvent,
    InsuranceStatus,
    ReEligibilityPeriod,
    WorkflowAuditEvent,
)
from app.features.workflow_engine.engine import WorkflowEngine
from app.features.workflow_engine.hold import put_on_hold as engine_put_on_hold
from app.features.workflow_engine.hold import resume_case as engine_resume_case
from app.features.workflow_engine.models import (
    ApplicationNote,
    ApplicationWorkflow,
    InsuranceCaseDetails,
)
from app.features.workflow_engine.re_eligibility import (
    compute_re_eligible_date,
    re_eligibility_detail_updates,
    re_eligibility_note_text,
)
from app.features.workflow_engine.repository import (
    ApplicationNoteRepository,
    ApplicationStatusHistoryRepository,
    ApplicationWorkflowRepository,
)
from app.services.storage.client import (
    generate_presigned_download_url,
    generate_presigned_upload_url,
    get_object_size,
)
from app.shared.audit_log import write_audit_log
from app.utils.datetime import ist_date_to_utc_midnight, utc_now
from app.utils.helpers import to_object_id
from app.utils.id_generator import IdPrefix, generate_id

_NO_ASSIGNMENT_SENTINEL = "___none___"
_PRODUCT_CHANGE_STATUSES = (InsuranceStatus.FRESH_LEAD, InsuranceStatus.POLICY_DOCUMENT, InsuranceStatus.POLICY_LOGIN)


class InsuranceCaseService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self._db = db
        self._engine = WorkflowEngine(db)
        self._workflows = ApplicationWorkflowRepository(db)
        self._history = ApplicationStatusHistoryRepository(db)
        self._notes = ApplicationNoteRepository(db)
        self._applications = ApplicationRepository(db)
        self._documents = ApplicationDocumentRepository(db)
        self._form_defs = ApplicationFormDefinitionRepository(db)
        self._customers = CustomerRepository(db)
        self._employees = EmployeeRepository(db)
        self._products = InsuranceProductRepository(db)
        self._categories = InsuranceCategoryRepository(db)
        self._document_types = DocumentTypeRepository(db)
        self._other_documents = InsuranceCaseAdditionalDocumentRepository(db)
        self._payments = InsurancePaymentTransactionRepository(db)
        self._advisors = AdvisorRepository(db)
        self._reminders = RemindersService(db)

    def _customer_service(self) -> CustomerService:
        """The per-document verify/reject/history/list logic is product-agnostic and
        lives in `CustomerService` (Module 6B) — insurance reuses it verbatim behind an
        `insurance_management:applications`-gated route rather than duplicating it. Redis
        is only touched by that service's auth/OTP paths, never by the document methods,
        so a lazily-built client is safe (same pattern as `LoanCaseService`)."""
        return CustomerService(self._db, get_redis())

    # ---------------------------------------------------------------- case sync / lookup

    async def _create_case_for_application(
        self, application: Application, *, actor_id: str | None = None
    ) -> ApplicationWorkflow:
        case_code = await generate_id(self._db, IdPrefix.INSURANCE_CASE)
        return await self._engine.create_case(
            case_code=case_code, case_type=CaseType.INSURANCE, application_id=application.require_id(),
            customer_id=application.customer_id or "", product_id=application.product_id,
            product_category=application.product_category, assigned_to=None,
            actor_id=actor_id, initial_status=InsuranceStatus.FRESH_LEAD, insurance_details=InsuranceCaseDetails(),
        )

    async def _sync_new_cases(self) -> None:
        existing = await self._workflows.find_existing_application_ids(CaseType.INSURANCE, include_deleted=True)
        submitted = await self._applications.find_many(
            {"status": "submitted", "product_category": "insurance", "customer_id": {"$ne": None}}, limit=1000
        )
        for application in submitted:
            if application.require_id() not in existing:
                await self._create_case_for_application(application)

    async def _get_or_create_for_application_id(self, application_id: str) -> ApplicationWorkflow | None:
        existing = await self._workflows.find_by_application_id(application_id)
        if existing is not None:
            return existing
        if await self._workflows.find_by_application_id(application_id, include_deleted=True) is not None:
            return None
        application = await self._applications.find_by_id(application_id)
        if (
            application is None
            or application.status != "submitted"
            or application.product_category != "insurance"
            or application.customer_id is None
        ):
            raise NotFoundError("No insurance case exists for this application.")
        return await self._create_case_for_application(application)

    async def ensure_case_for_application(self, application_id: str) -> ApplicationWorkflow | None:
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
        if actor.role == EMPLOYEE and not await self._employee_can_see(case, actor):
            raise ForbiddenError("This case isn't yours.")
        return case

    async def _employee_can_see(self, case: ApplicationWorkflow, actor: User) -> bool:
        """Policy Leads are assigned to Advisors now (not staff users), so an Employee's
        visibility is by authorship: they see the cases they created (e.g. their own
        "+ Add Insurance Lead" walk-ins). A legacy `assigned_to` that still holds their
        employee id also counts, so no historical case silently disappears."""
        if case.created_by == actor.require_id():
            return True
        employee_id = await self._acting_employee_id(actor)
        return employee_id != _NO_ASSIGNMENT_SENTINEL and case.assigned_to == employee_id

    def _employee_scope_filter(self, actor: User, employee_id: str | None) -> dict[str, Any]:
        clauses: list[dict[str, Any]] = [{"created_by": actor.require_id()}]
        if employee_id is not None and employee_id != _NO_ASSIGNMENT_SENTINEL:
            clauses.append({"assigned_to": employee_id})
        return {"$and": [{"$or": clauses}]}

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
        extra_filter: dict[str, Any] | None = None
        if actor.role == EMPLOYEE:
            extra_filter = self._employee_scope_filter(actor, await self._acting_employee_id(actor))
            assigned_to, unassigned_only = None, False
        return await self._workflows.search_and_filter(
            case_type=CaseType.INSURANCE, search=search, customer_id=customer_id, assigned_to=assigned_to,
            unassigned_only=unassigned_only, status=status, skip=skip, limit=limit, sort=sort,
            extra_filter=extra_filter,
        )

    async def get_counts(self, actor: User) -> dict[str, int]:
        """One count per `InsuranceStatus.ALL` Policy Leads tab, built with the identical
        `assigned_to` scoping `list_cases` applies — a count can never disagree with what
        its tab's list call returns (same principle as Loan's `get_counts`)."""
        await self._sync_new_cases()
        extra_filter: dict[str, Any] | None = None
        if actor.role == EMPLOYEE:
            extra_filter = self._employee_scope_filter(actor, await self._acting_employee_id(actor))
        return {
            status: await self._workflows.count_filtered(
                case_type=CaseType.INSURANCE, status=status, extra_filter=extra_filter,
            )
            for status in InsuranceStatus.ALL
        }

    async def list_own_cases(self, actor: User) -> list[ApplicationWorkflow]:
        applications = await self._applications.find_for_user(actor.require_id(), status="submitted")
        insurance_apps = [a for a in applications if a.product_category == "insurance" and a.customer_id]
        cases = [await self._get_or_create_for_application_id(a.require_id()) for a in insurance_apps]
        return [c for c in cases if c is not None]

    # ---------------------------------------------------------------- assignment

    async def assign_case(self, case_id: str, advisor_id: str, actor: User) -> ApplicationWorkflow:
        """Assign a Policy Lead to an **Advisor** (the existing `advisors` master — never a
        separate collection). The advisor must exist AND be Active; an inactive-advisor id
        sent straight to the API is rejected here, not just hidden from the dropdown. The
        "only an Owner can reassign an already-assigned case" rule is unchanged."""
        case = await self._workflows.find_by_id(case_id)
        if case is None or case.case_type != CaseType.INSURANCE:
            raise NotFoundError("Insurance case not found.")
        if actor.role != OWNER and case.assigned_to is not None:
            raise ForbiddenError("Only an Owner can reassign a case that's already assigned to someone.")
        advisor = await self._advisors.find_by_id(advisor_id)
        if advisor is None:
            raise ValidationError("Unknown advisor.")
        if advisor.status != AdvisorStatus.ACTIVE:
            raise ValidationError("That advisor is inactive and cannot be assigned Policy Leads.")
        is_reassignment = case.assigned_to is not None
        updated = await self._workflows.update(case_id, {"assigned_to": advisor_id}, updated_by=actor.require_id())
        if updated is None:
            raise NotFoundError("Insurance case not found.")
        await write_audit_log(
            self._db, event_type=WorkflowAuditEvent.CASE_REASSIGNED if is_reassignment else WorkflowAuditEvent.CASE_ASSIGNED,
            user_id=actor.require_id(), metadata={"application_workflow_id": case_id, "advisor_id": advisor_id},
        )
        return updated

    # ---------------------------------------------------------------- hold / resume

    async def hold_case(
        self, case_id: str, reason: str, actor: User, *, other_reason: str | None = None, remarks: str | None = None
    ) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        normalized = (other_reason or "").strip() or None
        return await engine_put_on_hold(self._engine, case, reason, actor, remarks=remarks, other_reason=normalized)

    async def resume_case(self, case_id: str, actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        return await engine_resume_case(self._engine, case, actor)

    # ---------------------------------------------------------------- generic status control

    _SIMPLE_STATUS_TRANSITIONS: ClassVar[set[tuple[str, str]]] = {
        (InsuranceStatus.FRESH_LEAD, InsuranceStatus.POLICY_DOCUMENT),
    }

    async def update_status(self, case_id: str, new_status: str, actor: User) -> ApplicationWorkflow:
        """Generic Case Status control. Only `fresh_lead → policy_document` (no extra
        data) goes through here; every other move has a dedicated action that collects
        its mandatory data or enforces its gate."""
        case = await self.get_case(case_id, actor)
        if new_status == case.current_status:
            return case
        await self._engine.assert_transition_allowed(CaseType.INSURANCE, case.current_status, new_status)
        if (case.current_status, new_status) in self._SIMPLE_STATUS_TRANSITIONS:
            return await self.move_to_policy_document(case_id, actor)
        raise ConflictError(
            f"Moving this case to '{new_status}' needs the dedicated action for that step "
            "(Move to Policy Login, Update, Reject, Move Back, …)."
        )

    # ---------------------------------------------------------------- pipeline transitions

    async def move_to_policy_document(self, case_id: str, actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        if case.current_status != InsuranceStatus.FRESH_LEAD:
            raise ConflictError("Only a Fresh Lead can be moved to Policy Document.")
        return await self._engine.transition(case, InsuranceStatus.POLICY_DOCUMENT, actor)

    async def move_to_policy_login(self, case_id: str, actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        if case.current_status != InsuranceStatus.POLICY_DOCUMENT:
            raise ConflictError("Only a Policy Document case can be moved to Policy Login.")
        all_verified, missing = await self._required_documents_status(case)
        if not all_verified:
            names = await self._document_type_name_map(missing)
            raise ConflictError(
                "Every required document must be verified before moving to Policy Login. Still outstanding: "
                + ", ".join(names.get(m, m) for m in missing)
                + "."
            )
        return await self._engine.transition(case, InsuranceStatus.POLICY_LOGIN, actor)

    async def move_to_payment(self, case_id: str, actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        if case.current_status != InsuranceStatus.POLICY_LOGIN:
            raise ConflictError("Only a Policy Login case can be moved to Payment.")
        details = case.insurance_details or InsuranceCaseDetails()
        if details.premium_amount is None or details.ppt is None or details.pt is None:
            raise ValidationError("Record Premium, PPT and PT (Policy Login → Update) before moving to Payment.")
        # Starts every case at a clean, unambiguous "Not Paid" state — never inherits a
        # stale amount from a prior Payment cycle (e.g. a case moved back and forward
        # again), and gives `update_payment`/`move_to_policy_issued` a guaranteed non-None
        # `amount_paid` to compare against `premium_amount`.
        started = details.model_copy(update={"payment_status": InsurancePaymentStatus.NOT_PAID, "amount_paid": 0.0})
        return await self._engine.transition(case, InsuranceStatus.PAYMENT, actor, updates={"insurance_details": started.model_dump()})

    async def update_payment(self, case_id: str, payload: PaymentUpdateRequest, actor: User) -> ApplicationWorkflow:
        """"Add Payment" — `payload.amount` is ADDED to whatever is already recorded, never
        replaces it (production bug this fixes: a second payment used to overwrite the
        first). Case stays at `payment` (same "edit in place, no transition" shape as
        `update_policy_login`).

        The increment-and-validate step is one atomic, conditional `find_one_and_update`
        (`$inc` guarded by a `$lte` filter on the CURRENT stored `amount_paid`) rather
        than the usual read-modify-write-whole-subdocument pattern every other update in
        this service uses — that pattern would silently lose one of two near-simultaneous
        payments (classic lost-update race) and would also overwrite the increment this
        same call just made. The filter is evaluated against MongoDB's live document at
        write time, so two concurrent adds are serialized correctly: whichever lands
        first succeeds against the balance as it stood; the second re-validates against
        the NOW-updated total, and is atomically rejected (never silently lost, never
        silently over-applied) if it would exceed the Premium. `payment_status` is never
        taken from the request — always recomputed here from the confirmed new total, so
        it can never be saved out of sync with the actual amount (see
        `InsuranceCaseDetails.payment_status`)."""
        case = await self.get_case(case_id, actor)
        if case.current_status != InsuranceStatus.PAYMENT:
            raise ConflictError("Payment can only be updated at the Payment stage.")
        details = case.insurance_details or InsuranceCaseDetails()
        premium = details.premium_amount
        if premium is None:
            raise ConflictError("This case has no Premium recorded — update Policy Login first.")

        old_amount = details.amount_paid or 0.0
        doc = await self._workflows.collection.find_one_and_update(
            {
                "_id": to_object_id(case_id),
                "is_deleted": False,
                "current_status": InsuranceStatus.PAYMENT,
                "insurance_details.amount_paid": {"$lte": premium - payload.amount},
            },
            {"$inc": {"insurance_details.amount_paid": payload.amount}},
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            # Re-fetch to report the ACTUAL current balance (never a stale one) — the
            # case may have moved on, or (far more likely) someone else's payment landed
            # first and this amount would now exceed the remaining balance.
            current = await self.get_case(case_id, actor)
            if current.current_status != InsuranceStatus.PAYMENT:
                raise ConflictError("Payment can only be updated at the Payment stage.")
            current_paid = (current.insurance_details or InsuranceCaseDetails()).amount_paid or 0.0
            remaining = premium - current_paid
            raise ValidationError(
                f"Amount paid cannot exceed the remaining balance of ₹{remaining:,.2f} "
                f"(Premium ₹{premium:,.2f}, already paid ₹{current_paid:,.2f})."
            )

        new_total = doc["insurance_details"]["amount_paid"]
        new_status = InsurancePaymentStatus.compute(new_total, premium)
        updated = await self._workflows.collection.find_one_and_update(
            {"_id": to_object_id(case_id)},
            {"$set": {"insurance_details.payment_status": new_status, "updated_at": utc_now(), "updated_by": actor.require_id()}},
            return_document=ReturnDocument.AFTER,
        )
        assert updated is not None
        updated_case = ApplicationWorkflow.model_validate(updated)

        transaction = InsurancePaymentTransaction(
            insurance_case_id=case_id, amount=payload.amount, running_total=new_total, created_by=actor.require_id(),
        )
        await self._payments.insert(transaction)

        await write_audit_log(
            self._db, event_type=InsuranceAuditEvent.PAYMENT_UPDATED, user_id=actor.require_id(),
            metadata={
                "application_workflow_id": case_id, "amount_added": payload.amount,
                "from_amount": old_amount, "to_amount": new_total, "to_status": new_status,
            },
        )
        await self._notes.insert(ApplicationNote(
            application_workflow_id=case_id, created_by=actor.require_id(),
            text=(
                f"Payment added: ₹{payload.amount:,.2f}. Total Paid ₹{old_amount:,.2f} → ₹{new_total:,.2f} "
                f"({new_status})."
            ),
        ))
        return updated_case

    async def payment_history(self, case_id: str, actor: User) -> tuple[list[InsurancePaymentTransaction], float]:
        """The immutable payment ledger plus `unrecorded_amount` — the gap (if any)
        between the case's current `amount_paid` and the sum of recorded transactions.
        Non-zero only for a case whose `amount_paid` predates individual transaction
        tracking (e.g. a pre-existing ₹9,000 recorded under the old overwrite-only
        behaviour); never backfilled as a fake transaction with an invented date/staff
        member (per the brief — do not fabricate history)."""
        case = await self.get_case(case_id, actor)
        transactions = await self._payments.find_for_case(case_id)
        total_paid = (case.insurance_details or InsuranceCaseDetails()).amount_paid or 0.0
        recorded = sum(t.amount for t in transactions)
        unrecorded = max(0.0, total_paid - recorded)
        return transactions, unrecorded

    async def resolve_payment_creator_names(self, transactions: list[InsurancePaymentTransaction]) -> dict[str, str]:
        # Same convention as `CustomerService.resolve_verifier_names` — `created_by`
        # stores the acting user's own auth id (BaseDocument's usual created_by
        # convention), keyed by `Employee.user_id` since an Owner (no Employee record)
        # can also record a payment.
        creator_ids = {t.created_by for t in transactions if t.created_by}
        if not creator_ids:
            return {}
        employees = await self._employees.find_many({}, limit=500)
        return {e.user_id: e.display_name for e in employees if e.user_id in creator_ids}

    async def move_to_policy_issued(self, case_id: str, actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        if case.current_status != InsuranceStatus.PAYMENT:
            raise ConflictError("Only a Payment case can be moved to Policy Issued.")
        details = case.insurance_details or InsuranceCaseDetails()
        # Independently re-derived from the actual stored numbers — never trusts a
        # previously-saved `payment_status` string. A direct API call that tries to jump
        # to Policy Issued while genuinely under-paid (or with no Issue Date) is rejected
        # here regardless of what `payment_status` label was last saved.
        premium, paid = details.premium_amount, details.amount_paid
        if premium is None or paid is None or paid < premium:
            raise ValidationError("The Premium Amount must be fully paid before issuing the policy.")
        if details.policy_issue_date is None:
            raise ValidationError("Record the Issue Date (Policy Login → Update) before issuing the policy.")
        issued = details.model_copy(update={"policy_issued_at": utc_now()})
        return await self._engine.transition(case, InsuranceStatus.POLICY_ISSUED, actor, updates={"insurance_details": issued.model_dump()})

    _MOVE_BACK_TARGET: ClassVar[dict[str, str]] = {
        InsuranceStatus.POLICY_DOCUMENT: InsuranceStatus.FRESH_LEAD,
        InsuranceStatus.POLICY_LOGIN: InsuranceStatus.POLICY_DOCUMENT,
        InsuranceStatus.PAYMENT: InsuranceStatus.POLICY_LOGIN,
    }

    async def move_back(self, case_id: str, target: str, actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        expected = self._MOVE_BACK_TARGET.get(case.current_status)
        if expected is None or target != expected:
            raise ConflictError(f"A case in '{case.current_status}' cannot be moved back to '{target}'.")
        updated = await self._engine.transition(case, target, actor, remarks="Moved back a stage.")
        await write_audit_log(
            self._db, event_type=InsuranceAuditEvent.MOVED_BACK, user_id=actor.require_id(),
            metadata={"application_workflow_id": case_id, "from": case.current_status, "to": target},
        )
        return updated

    async def restart_from_re_eligible(self, case_id: str, target: str, actor: User) -> ApplicationWorkflow:
        """A Re-Eligible case restarts from Fresh Lead or Policy Document (or is rejected
        outright). The `re_eligible → …` restart edges are seeded; this just validates
        and drives the engine."""
        case = await self.get_case(case_id, actor)
        if case.current_status != InsuranceStatus.RE_ELIGIBLE:
            raise ConflictError("This case is not Re-Eligible.")
        if target not in (InsuranceStatus.FRESH_LEAD, InsuranceStatus.POLICY_DOCUMENT):
            raise ValidationError("A Re-Eligible case can only restart at Fresh Lead or Policy Document.")
        return await self._engine.transition(case, target, actor, remarks="Restarted from Re-Eligible.")

    # ---------------------------------------------------------------- reject / re-eligibility

    async def reject_case(
        self, case_id: str, reason: str, re_eligibility: str | None, re_eligible_date: date | None, actor: User
    ) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        if case.current_status in InsuranceStatus.TERMINAL:
            raise ConflictError("This case is already closed.")
        if case.current_status == InsuranceStatus.ON_HOLD:
            raise ConflictError("Resume the case before rejecting it.")
        if not (reason or "").strip():
            raise ValidationError("A rejection reason is mandatory.")
        # Validate the Re-Eligibility choice/date BEFORE the transition — a bad option
        # must 422 without leaving the case stranded in `rejected` with no schedule.
        choice = re_eligibility or ReEligibilityPeriod.NO
        now = utc_now()
        computed_date = compute_re_eligible_date(choice, re_eligible_date, now)
        await self._engine.transition(
            case, InsuranceStatus.REJECTED, actor, updates={"rejection_reason": reason}, remarks=reason
        )
        return await self._apply_re_eligibility_schedule(case_id, choice, computed_date, now, actor)

    async def _apply_re_eligibility_schedule(
        self, case_id: str, choice: str, re_eligible_date: Any, now: Any, actor: User
    ) -> ApplicationWorkflow:
        """Records the per-case Re-Eligibility schedule chosen at rejection time. Date
        math / validation happened in `reject_case` (before the transition); note copy is
        the shared `workflow_engine/re_eligibility.py` helper. Insurance-side writes only."""
        case = await self._workflows.find_by_id(case_id)
        assert case is not None
        details = case.insurance_details or InsuranceCaseDetails()

        updated_details = details.model_copy(
            update=re_eligibility_detail_updates(choice, re_eligible_date, actor.require_id(), now)
        )
        updated = await self._workflows.update(case_id, {"insurance_details": updated_details.model_dump()}, updated_by=actor.require_id())
        assert updated is not None
        await write_audit_log(
            self._db, event_type=InsuranceAuditEvent.RE_ELIGIBILITY_SCHEDULED, user_id=actor.require_id(),
            metadata={
                "application_workflow_id": case_id, "choice": choice,
                "re_eligible_date": re_eligible_date.isoformat() if re_eligible_date else None,
            },
        )
        await self._notes.insert(
            ApplicationNote(
                application_workflow_id=case_id, created_by=actor.require_id(),
                text=re_eligibility_note_text(choice, re_eligible_date),
            )
        )
        return updated

    async def mark_re_eligible(self, case_id: str, actor: User) -> ApplicationWorkflow:
        """Move a `rejected` case straight to `re_eligible` (the seeded `rejected →
        re_eligible` edge) — the manual equivalent of what the
        `auto_transition_re_eligible_cases` worker does on the scheduled date."""
        case = await self.get_case(case_id, actor)
        if case.current_status != InsuranceStatus.REJECTED:
            raise ConflictError("Only a Rejected case can be marked Re-Eligible.")
        details = (case.insurance_details or InsuranceCaseDetails()).model_copy(
            update={"re_eligible_date": None, "re_eligibility_auto_transitioned": False}
        )
        updated = await self._engine.transition(
            case, InsuranceStatus.RE_ELIGIBLE, actor,
            updates={"insurance_details": details.model_dump()}, remarks="Manually marked Re-Eligible.",
        )
        await write_audit_log(
            self._db, event_type=InsuranceAuditEvent.MARKED_RE_ELIGIBLE, user_id=actor.require_id(),
            metadata={"application_workflow_id": case_id},
        )
        return updated

    # ---------------------------------------------------------------- manual creation + staff "Move To"

    _STAGE_CHAIN: ClassVar[tuple[str, ...]] = (
        InsuranceStatus.FRESH_LEAD, InsuranceStatus.POLICY_DOCUMENT,
        InsuranceStatus.POLICY_LOGIN, InsuranceStatus.PAYMENT, InsuranceStatus.POLICY_ISSUED,
    )
    _STAGE_LABELS: ClassVar[dict[str, str]] = {
        InsuranceStatus.FRESH_LEAD: "Fresh Lead", InsuranceStatus.POLICY_DOCUMENT: "Policy Document",
        InsuranceStatus.POLICY_LOGIN: "Policy Login", InsuranceStatus.PAYMENT: "Payment",
        InsuranceStatus.POLICY_ISSUED: "Policy Issued",
        InsuranceStatus.RE_ELIGIBLE: "Re-Eligible", InsuranceStatus.REJECTED: "Rejected",
    }

    async def _assert_product_in_active_category(self, product_id: str, *, expected_category_id: str | None = None) -> None:
        product = await self._products.find_by_id(product_id)
        if product is None:
            raise ValidationError("Unknown insurance product.")
        category_id = getattr(product, "category_id", None)
        if category_id is None:
            raise ValidationError("That insurance product isn't linked to a category yet.")
        if expected_category_id is not None and category_id != expected_category_id:
            raise ValidationError("That product does not belong to the selected Insurance Category.")
        category = await self._categories.find_by_id(category_id)
        if category is None or category.status != MasterDataStatus.ACTIVE:
            raise ConflictError("That insurance product's category is inactive.")

    async def create_manual_case(self, payload: CreateManualInsuranceCaseRequest, actor: User) -> ApplicationWorkflow:
        """Staff "Add Insurance Lead" — provisions the customer + application (never a
        `Lead`), creates the workflow at Fresh Lead through the ordinary
        `ensure_case_for_application` path, then walks it to the requested initial stage
        with `move_case_to_stage` (every gate enforced). If the walk fails, everything
        this call created is removed so no half-formed case is left behind."""
        await self._assert_product_in_active_category(payload.product_id, expected_category_id=payload.insurance_category_id)

        application, rollback_user_id, rollback_customer_id = await self._customer_service().create_manual_insurance_application(
            full_name=payload.full_name, mobile=payload.mobile, email=payload.email, gender=payload.gender,
            age=payload.age, profession=payload.profession, annual_income=payload.annual_income,
            remarks=payload.remarks, product_id=payload.product_id, actor=actor,
            extra_form_data=payload.applicant_form_data(),
        )
        # `created_by = actor` on the workflow is what gives an Employee creator ownership
        # of the case (Policy Leads are assigned to Advisors, not staff users, so the old
        # "self-assign the employee" workaround no longer applies).
        case = await self._create_case_for_application(application, actor_id=actor.require_id())
        case_id = case.require_id()

        await write_audit_log(
            self._db, event_type=InsuranceAuditEvent.MANUAL_CASE_CREATED, user_id=actor.require_id(),
            metadata={
                "application_workflow_id": case_id, "application_id": application.require_id(), "stage": payload.stage,
            },
        )
        await self._notes.insert(ApplicationNote(
            application_workflow_id=case_id, created_by=actor.require_id(),
            text=f"Manually created by staff at stage “{self._STAGE_LABELS.get(payload.stage, payload.stage)}”.",
        ))

        if payload.stage == InsuranceStatus.FRESH_LEAD:
            return case
        try:
            return await self.move_case_to_stage(
                case_id, payload.stage, actor,
                reason=payload.reason, re_eligibility=payload.re_eligibility, re_eligible_date=payload.re_eligible_date,
            )
        except Exception:
            await self._rollback_manual_case(case_id, application.require_id(), rollback_user_id, rollback_customer_id)
            raise

    async def _rollback_manual_case(
        self, case_id: str, application_id: str, rollback_user_id: str | None, rollback_customer_id: str | None,
    ) -> None:
        """Hard-remove exactly what `create_manual_case` created when its stage-walk
        fails — a failed creation must never surface as a real lead. Uses the same raw
        `delete_one` the Bin's purge uses (`bin/service.py`)."""
        await self._db["application_status_history"].delete_many({"application_workflow_id": case_id})
        await self._db["application_notes"].delete_many({"application_workflow_id": case_id})
        await self._db["application_workflows"].delete_one({"_id": to_object_id(case_id)})
        await self._db["applications"].delete_one({"_id": to_object_id(application_id)})
        if rollback_customer_id is not None:
            await self._db["customers"].delete_one({"_id": to_object_id(rollback_customer_id)})
        if rollback_user_id is not None:
            await self._db["users"].delete_one({"_id": to_object_id(rollback_user_id)})

    async def move_case_to_stage(
        self, case_id: str, target: str, actor: User, *,
        reason: str | None = None, re_eligibility: str | None = None, re_eligible_date: date | None = None,
    ) -> ApplicationWorkflow:
        """Staff "Move To" — deliberately send a case to any Policy Leads stage. Every
        branch delegates to an existing, individually-gated transition; this only picks
        the right one(s) and, for a multi-step move, walks the chain hop by hop. A gate
        that blocks a hop (unverified documents, missing Premium/PPT/PT) stops the walk
        with that gate's own error — the case stays at the furthest stage it legally
        reached. Never patches `current_status` directly."""
        case = await self.get_case(case_id, actor)
        current = case.current_status
        if target == current:
            return case

        if target == InsuranceStatus.REJECTED:
            return await self.reject_case(case_id, reason or "", re_eligibility, re_eligible_date, actor)
        if target == InsuranceStatus.RE_ELIGIBLE:
            # `re_eligible` is only reachable from `rejected` (seeded edge). From any other
            # stage, reject first (staff supplies the reason + schedule) then mark it.
            if current != InsuranceStatus.REJECTED:
                await self.reject_case(case_id, reason or "", re_eligibility, re_eligible_date, actor)
            return await self.mark_re_eligible(case_id, actor)
        if current == InsuranceStatus.RE_ELIGIBLE and target in (InsuranceStatus.FRESH_LEAD, InsuranceStatus.POLICY_DOCUMENT):
            return await self.restart_from_re_eligible(case_id, target, actor)

        if current not in self._STAGE_CHAIN or target not in self._STAGE_CHAIN:
            raise ConflictError(
                f"A case in '{self._STAGE_LABELS.get(current, current)}' cannot be moved to "
                f"'{self._STAGE_LABELS.get(target, target)}'."
            )
        from_i, to_i = self._STAGE_CHAIN.index(current), self._STAGE_CHAIN.index(target)
        updated = case
        if to_i > from_i:
            forward = (self.move_to_policy_document, self.move_to_policy_login, self.move_to_payment, self.move_to_policy_issued)
            for step in range(from_i, to_i):
                updated = await forward[step](case_id, actor)
        else:
            for _ in range(from_i - to_i):
                cur = (await self._workflows.find_by_id(case_id))
                assert cur is not None
                updated = await self.move_back(case_id, self._MOVE_BACK_TARGET[cur.current_status], actor)

        await write_audit_log(
            self._db, event_type=InsuranceAuditEvent.STAGE_MOVED, user_id=actor.require_id(),
            metadata={"application_workflow_id": case_id, "from": current, "to": target},
        )
        await self._notes.insert(ApplicationNote(
            application_workflow_id=case_id, created_by=actor.require_id(),
            text=(
                f"Staff moved this case: {self._STAGE_LABELS.get(current, current)} → "
                f"{self._STAGE_LABELS.get(target, target)}."
            ),
        ))
        return updated

    # ---------------------------------------------------------------- policy login / product

    async def update_policy_login(self, case_id: str, payload: PolicyLoginUpdateRequest, actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        if case.current_status != InsuranceStatus.POLICY_LOGIN:
            raise ConflictError("Policy Login details can only be updated at the Policy Login stage.")
        if payload.product_id is not None and payload.product_id != case.product_id:
            case = await self._change_product(case, payload.product_id, actor)

        details = case.insurance_details or InsuranceCaseDetails()
        updates: dict[str, Any] = {}
        for field in ("premium_amount", "ppt", "pt"):
            value = getattr(payload, field)
            if value is not None:
                updates[field] = value
        if payload.remarks is not None:
            updates["policy_login_remarks"] = payload.remarks.strip() or None
        if payload.policy_number is not None:
            updates["policy_number"] = payload.policy_number.strip() or None
        if payload.policy_issue_date is not None:
            updates["policy_issue_date"] = ist_date_to_utc_midnight(payload.policy_issue_date)
        updated_details = details.model_copy(update=updates)
        updated = await self._workflows.update(case_id, {"insurance_details": updated_details.model_dump()}, updated_by=actor.require_id())
        assert updated is not None
        await write_audit_log(
            self._db, event_type=InsuranceAuditEvent.POLICY_LOGIN_UPDATED, user_id=actor.require_id(),
            metadata={"application_workflow_id": case_id, **{k: str(v) for k, v in updates.items()}},
        )
        return updated

    async def change_product(self, case_id: str, new_product_id: str, actor: User) -> ApplicationWorkflow:
        case = await self.get_case(case_id, actor)
        if case.current_status not in _PRODUCT_CHANGE_STATUSES:
            raise ConflictError("The product can only be changed before the policy is issued.")
        return await self._change_product(case, new_product_id, actor)

    async def _change_product(self, case: ApplicationWorkflow, new_product_id: str, actor: User) -> ApplicationWorkflow:
        if new_product_id == case.product_id:
            return case
        product = await self._products.find_by_id(new_product_id)
        if product is None:
            raise ValidationError("Unknown insurance product.")
        category_id = getattr(product, "category_id", None)
        if category_id is None:
            raise ValidationError("That insurance product isn't linked to a category yet.")
        category = await self._categories.find_by_id(category_id)
        if category is None or category.status != MasterDataStatus.ACTIVE:
            raise ConflictError("That insurance product's category is inactive.")
        form_def = await self._form_defs.find_by_product("insurance", new_product_id)
        if form_def is None:
            raise ValidationError("That insurance product has no active Product Schema yet.")

        # Deliberate write to the otherwise read-only Application — keeps Customer
        # Applications' product/schema pin in lockstep with the case. Uploaded
        # `ApplicationDocument`s are NOT touched (a doc no longer in the new schema
        # stays as historical — surfaced separately in Phase 5).
        await self._applications.update(
            case.application_id, {"product_id": new_product_id, "form_definition_id": form_def.require_id()},
            updated_by=actor.require_id(),
        )
        updated = await self._workflows.update(case.require_id(), {"product_id": new_product_id}, updated_by=actor.require_id())
        assert updated is not None
        await write_audit_log(
            self._db, event_type=InsuranceAuditEvent.PRODUCT_CHANGED, user_id=actor.require_id(),
            metadata={
                "application_workflow_id": case.require_id(), "application_id": case.application_id,
                "from_product_id": case.product_id, "to_product_id": new_product_id,
                "form_definition_id": form_def.require_id(),
            },
        )
        return updated

    # ---------------------------------------------------------------- documents (read-only helpers)

    async def _document_type_name_map(self, type_ids: list[str]) -> dict[str, str]:
        if not type_ids:
            return {}
        types = await self._document_types.find_many({}, limit=500)
        wanted = set(type_ids)
        return {t.require_id(): t.name for t in types if t.require_id() in wanted}

    async def _required_documents_status(self, case: ApplicationWorkflow) -> tuple[bool, list[str]]:
        """`(all_required_verified, missing_document_type_ids)` for the pinned Product
        Schema. A `front_back_upload` document needs BOTH sides verified. Optional/hidden
        documents are ignored (spec §43)."""
        application = await self._applications.find_by_id(case.application_id)
        if application is None:
            return False, []
        form_def = await self._form_defs.find_by_id(application.form_definition_id)
        if form_def is None:
            return True, []
        current = await self._documents.find_current_for_application(case.application_id)
        verified = {
            (d.document_type_id, d.side) for d in current if d.verification_status == DocumentVerificationStatus.VERIFIED
        }
        verified_types = {t for (t, _s) in verified}
        missing: list[str] = []
        for rd in form_def.required_documents:
            if not rd.required or rd.hidden:
                continue
            if rd.front_back_upload:
                if (rd.document_type_id, DocumentSide.FRONT) not in verified or (rd.document_type_id, DocumentSide.BACK) not in verified:
                    missing.append(rd.document_type_id)
            elif rd.document_type_id not in verified_types:
                missing.append(rd.document_type_id)
        return len(missing) == 0, missing

    async def applicant_details(self, case: ApplicationWorkflow) -> dict[str, Any]:
        """The extended applicant profile stored in `Application.form_data` (age /
        profession / nominee / height / ... ) — an empty dict for a case whose
        application predates these fields."""
        application = await self._applications.find_by_id(case.application_id)
        return dict(application.form_data) if application is not None else {}

    async def required_documents_summary(self, case: ApplicationWorkflow) -> dict[str, Any]:
        application = await self._applications.find_by_id(case.application_id)
        form_def = await self._form_defs.find_by_id(application.form_definition_id) if application else None
        required_total = (
            sum(1 for rd in form_def.required_documents if rd.required and not rd.hidden) if form_def else 0
        )
        all_verified, missing = await self._required_documents_status(case)
        return {
            "required_total": required_total,
            "verified_total": required_total - len(missing),
            "all_required_verified": all_verified,
        }

    # ---------------------------------------------------------------- per-document actions (schema documents)

    async def _schema_document_type_ids(self, case: ApplicationWorkflow) -> set[str]:
        application = await self._applications.find_by_id(case.application_id)
        if application is None:
            return set()
        form_def = await self._form_defs.find_by_id(application.form_definition_id)
        if form_def is None:
            return set()
        return {rd.document_type_id for rd in form_def.required_documents}

    async def list_case_documents(
        self, case_id: str, actor: User
    ) -> tuple[list[ApplicationDocument], set[str]]:
        case = await self.get_case(case_id, actor)
        documents = await self._customer_service().list_documents_for_staff(case.application_id, actor)
        return documents, await self._schema_document_type_ids(case)

    async def case_document_history(self, case_id: str, document_type_id: str, actor: User) -> list[ApplicationDocument]:
        case = await self.get_case(case_id, actor)
        return await self._customer_service().get_document_history(case.application_id, document_type_id, actor)

    async def verify_case_document(
        self, case_id: str, document_id: str, actor: User
    ) -> tuple[ApplicationDocument, set[str]]:
        case = await self.get_case(case_id, actor)
        document = await self._customer_service().verify_document(case.application_id, document_id, actor)
        return document, await self._schema_document_type_ids(case)

    async def reject_case_document(
        self, case_id: str, document_id: str, reason: str, actor: User
    ) -> tuple[ApplicationDocument, set[str]]:
        case = await self.get_case(case_id, actor)
        document = await self._customer_service().reject_document(case.application_id, document_id, reason, actor)
        return document, await self._schema_document_type_ids(case)

    async def resolve_document_type_names(self, documents: list[ApplicationDocument]) -> dict[str, str]:
        return await self._customer_service().resolve_document_type_names(documents)

    async def resolve_verifier_names(self, documents: list[ApplicationDocument]) -> dict[str, str]:
        return await self._customer_service().resolve_verifier_names(documents)

    def document_download_url(self, document: ApplicationDocument) -> str | None:
        return self._customer_service().document_download_url(document)

    def document_attachment_url(self, document: ApplicationDocument) -> str | None:
        return self._customer_service().document_attachment_url(document)

    # ---------------------------------------------------------------- "Add Other Document" (ad-hoc, per-case)

    _OTHER_DOCUMENT_KEY_PREFIX = "additional"
    _ADD_OTHER_DOCUMENT_STATUSES: ClassVar[tuple[str, ...]] = (
        InsuranceStatus.POLICY_DOCUMENT,
        InsuranceStatus.POLICY_LOGIN,
    )

    def _other_document_s3_key(self, application_code: str, doc_id: str, file_name: str) -> str:
        return f"application-documents/{application_code}/{self._OTHER_DOCUMENT_KEY_PREFIX}/{doc_id}/{file_name}"

    async def add_other_document(self, case_id: str, name: str, actor: User) -> InsuranceCaseAdditionalDocument:
        case = await self.get_case(case_id, actor)
        if case.current_status not in self._ADD_OTHER_DOCUMENT_STATUSES:
            raise ConflictError("Other documents can only be requested while the case is at Policy Document or Policy Login.")
        doc = InsuranceCaseAdditionalDocument(
            insurance_case_id=case_id, application_id=case.application_id, name=name, created_by=actor.require_id()
        )
        doc_id = await self._other_documents.insert(doc)
        await write_audit_log(
            self._db, event_type=InsuranceAuditEvent.ADDITIONAL_DOCUMENT_REQUESTED, user_id=actor.require_id(),
            metadata={"application_workflow_id": case_id, "name": name},
        )
        found = await self._other_documents.find_by_id(doc_id)
        assert found is not None
        return found

    async def list_other_documents(self, case_id: str, actor: User) -> list[InsuranceCaseAdditionalDocument]:
        await self.get_case(case_id, actor)
        return await self._other_documents.find_for_case(case_id)

    async def list_other_documents_own(self, case_id: str, actor: User) -> list[InsuranceCaseAdditionalDocument]:
        await self.get_own_case(case_id, actor)
        return await self._other_documents.find_for_case(case_id)

    async def other_document_history(self, case_id: str, doc_id: str, actor: User) -> list[InsuranceCaseAdditionalDocument]:
        await self.get_case(case_id, actor)
        doc = await self._other_documents.find_by_id(doc_id)
        if doc is None or doc.insurance_case_id != case_id:
            raise NotFoundError("Other document not found.")
        return await self._other_documents.history_for(case_id, doc.name)

    async def _resolve_other_document(
        self, case: ApplicationWorkflow, doc_id: str
    ) -> InsuranceCaseAdditionalDocument:
        doc = await self._other_documents.find_by_id(doc_id)
        if doc is None or doc.insurance_case_id != case.require_id():
            raise NotFoundError("Other document not found.")
        return doc

    async def _get_own_other_document(
        self, case_id: str, doc_id: str, actor: User
    ) -> tuple[ApplicationWorkflow, InsuranceCaseAdditionalDocument]:
        case = await self.get_own_case(case_id, actor)
        return case, await self._resolve_other_document(case, doc_id)

    async def _get_staff_other_document(
        self, case_id: str, doc_id: str, actor: User
    ) -> tuple[ApplicationWorkflow, InsuranceCaseAdditionalDocument]:
        case = await self.get_case(case_id, actor)
        return case, await self._resolve_other_document(case, doc_id)

    async def _mint_other_document_upload_url(
        self, case: ApplicationWorkflow, doc_id: str, payload: OtherDocumentUploadUrlRequest
    ) -> tuple[str, str]:
        application = await self._applications.find_by_id(case.application_id)
        if application is None:
            raise NotFoundError("Application not found.")
        # The key is per-version (`doc_id/file`) so a re-upload never overwrites the
        # previous file's object in storage.
        s3_key = self._other_document_s3_key(application.application_code, doc_id, payload.file_name)
        return generate_presigned_upload_url(s3_key, content_type=payload.content_type), s3_key

    async def _apply_other_document_upload(
        self, case: ApplicationWorkflow, doc: InsuranceCaseAdditionalDocument,
        payload: ConfirmOtherDocumentRequest, actor: User,
    ) -> InsuranceCaseAdditionalDocument:
        application = await self._applications.find_by_id(case.application_id)
        if application is None:
            raise NotFoundError("Application not found.")
        # Never trust the client-supplied key — re-derive it exactly as the upload URL was minted.
        s3_key = self._other_document_s3_key(application.application_code, doc.require_id(), payload.file_name)
        size = get_object_size(s3_key)
        if size is None:
            raise ValidationError("The file hasn't finished uploading yet. Please try again in a moment.")
        upload_fields: dict[str, Any] = {
            "document_status": "uploaded", "verification_status": "pending", "rejection_reason": None,
            "s3_key": s3_key, "file_name": payload.file_name, "content_type": payload.content_type,
            "file_size_bytes": size, "uploaded_at": utc_now(), "verified_by": None, "verified_at": None,
        }
        if doc.document_status == "requested":
            # First upload against the request — update in place, no prior version exists.
            updated = await self._other_documents.update(doc.require_id(), upload_fields, updated_by=actor.require_id())
            assert updated is not None
            return updated
        # Re-upload — supersede the current row, keep it in history, make the new file current.
        await self._other_documents.update(doc.require_id(), {"is_current": False}, updated_by=actor.require_id())
        new_id = await self._other_documents.insert(InsuranceCaseAdditionalDocument(
            insurance_case_id=doc.insurance_case_id, application_id=doc.application_id, name=doc.name,
            is_current=True, doc_version=doc.doc_version + 1, replaces_document_id=doc.require_id(),
            created_by=actor.require_id(), **upload_fields,
        ))
        created = await self._other_documents.find_by_id(new_id)
        assert created is not None
        return created

    async def mint_other_document_upload_url(
        self, case_id: str, doc_id: str, payload: OtherDocumentUploadUrlRequest, actor: User
    ) -> tuple[str, str]:
        case, _doc = await self._get_own_other_document(case_id, doc_id, actor)
        return await self._mint_other_document_upload_url(case, doc_id, payload)

    async def confirm_other_document_upload(
        self, case_id: str, doc_id: str, payload: ConfirmOtherDocumentRequest, actor: User
    ) -> InsuranceCaseAdditionalDocument:
        case, doc = await self._get_own_other_document(case_id, doc_id, actor)
        result = await self._apply_other_document_upload(case, doc, payload, actor)
        await self._notify_other_document_uploaded(case, doc.name, "Customer")
        return result

    async def staff_mint_other_document_upload_url(
        self, case_id: str, doc_id: str, payload: OtherDocumentUploadUrlRequest, actor: User
    ) -> tuple[str, str]:
        case, _doc = await self._get_staff_other_document(case_id, doc_id, actor)
        return await self._mint_other_document_upload_url(case, doc_id, payload)

    async def staff_confirm_other_document_upload(
        self, case_id: str, doc_id: str, payload: ConfirmOtherDocumentRequest, actor: User
    ) -> InsuranceCaseAdditionalDocument:
        case, doc = await self._get_staff_other_document(case_id, doc_id, actor)
        return await self._apply_other_document_upload(case, doc, payload, actor)

    async def _notify_other_document_uploaded(self, case: ApplicationWorkflow, doc_name: str, by_label: str) -> None:
        owners = await self._db["users"].find({"role": OWNER, "is_deleted": False}).to_list(length=50)
        for owner_doc in owners:
            await self._reminders.create_notification(
                recipient_user_id=str(owner_doc["_id"]), notification_type=NotificationType.DOCUMENT_UPLOADED,
                title="New Other Document", message=f"{by_label} uploaded: {doc_name}",
                entity_type="insurance_case", entity_id=case.require_id(),
            )

    async def verify_other_document(self, case_id: str, doc_id: str, actor: User) -> InsuranceCaseAdditionalDocument:
        await self.get_case(case_id, actor)
        doc = await self._other_documents.find_by_id(doc_id)
        if doc is None or doc.insurance_case_id != case_id:
            raise NotFoundError("Other document not found.")
        if doc.document_status != "uploaded":
            raise ConflictError("This document hasn't been uploaded yet.")
        updated = await self._other_documents.update(
            doc_id, {"verification_status": "verified", "rejection_reason": None, "verified_by": actor.require_id(), "verified_at": utc_now()},
            updated_by=actor.require_id(),
        )
        assert updated is not None
        return updated

    async def reject_other_document(self, case_id: str, doc_id: str, reason: str, actor: User) -> InsuranceCaseAdditionalDocument:
        case = await self.get_case(case_id, actor)
        doc = await self._other_documents.find_by_id(doc_id)
        if doc is None or doc.insurance_case_id != case_id:
            raise NotFoundError("Other document not found.")
        if doc.document_status != "uploaded":
            raise ConflictError("This document hasn't been uploaded yet.")
        updated = await self._other_documents.update(
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
                entity_type="insurance_case", entity_id=case_id,
            )
        return updated

    def other_document_download_url(self, doc: InsuranceCaseAdditionalDocument) -> str | None:
        return generate_presigned_download_url(doc.s3_key) if doc.s3_key else None

    def other_document_attachment_url(self, doc: InsuranceCaseAdditionalDocument) -> str | None:
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

    async def get_timeline(self, case_id: str, actor: User) -> list[tuple[str, Any]]:
        await self.get_case(case_id, actor)
        history = await self._history.find_for_workflow(case_id)
        notes = await self._notes.find_for_workflow(case_id)
        combined: list[tuple[str, Any]] = [("status", h) for h in history] + [("note", n) for n in notes]
        combined.sort(key=lambda entry: entry[1].created_at, reverse=True)
        return combined

    # ---------------------------------------------------------------- Add Insurance Lead pickers

    async def lookup_insurance_categories(self) -> list[Any]:
        """Active Insurance Categories for the "Add Insurance Lead" Category picker —
        the staff-facing read (gated `insurance_management:applications:view` at the
        router). Same active-only master data the Customer Portal's own
        `list_active_insurance_categories` returns, just reachable by staff."""
        return await self._categories.find_many({"status": MasterDataStatus.ACTIVE}, limit=500, sort=[("name", 1)])

    async def lookup_insurance_products(self, insurance_category_id: str | None) -> list[Any]:
        query: dict[str, Any] = {"status": MasterDataStatus.ACTIVE}
        if insurance_category_id:
            query["category_id"] = insurance_category_id
        return await self._products.find_many(query, limit=500, sort=[("name", 1)])

    # ---------------------------------------------------------------- name resolution

    async def resolve_names(
        self, cases: list[ApplicationWorkflow]
    ) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
        """Returns `(customer_map, product_map, assignee_map, assignee_channel_map)` —
        the last is the raw Advisor `channel` ("qr"/"non_qr"), keyed the same as
        `assignee_map`, so the case detail can show "Name — QR" without a second lookup.
        Absent for a legacy employee-id assignment (employees have no channel)."""
        customer_ids = {c.customer_id for c in cases if c.customer_id}
        product_ids = {c.product_id for c in cases}
        assignee_ids = {c.assigned_to for c in cases if c.assigned_to}

        customers = await self._customers.find_many({}, limit=1000) if customer_ids else []
        products = await self._products.find_many({}, limit=500)
        # `assigned_to` is an Advisor now; a legacy value may still be an employee id.
        advisors = await self._advisors.find_many({}, limit=1000) if assignee_ids else []
        employees = await self._employees.find_many({}, limit=500) if assignee_ids else []

        customer_map = {c.require_id(): c.full_name for c in customers if c.require_id() in customer_ids}
        product_map = {p.require_id(): p.name for p in products if p.require_id() in product_ids}
        assignee_map: dict[str, str] = {e.require_id(): e.display_name for e in employees if e.require_id() in assignee_ids}
        assignee_map.update({a.require_id(): a.full_name for a in advisors if a.require_id() in assignee_ids})
        assignee_channel_map = {a.require_id(): a.channel for a in advisors if a.require_id() in assignee_ids}
        return customer_map, product_map, assignee_map, assignee_channel_map
