"""Module 6A — Lead Foundation business logic. Reuses Module 4's `LeadSourceRepository`/
`LoanProductRepository`/`InsuranceProductRepository` and Module 2's `EmployeeRepository`
read-only (reference validation + name resolution) — the same composition pattern every
module since Access Control has used. No permission checks here — authorization is
`Depends(require_permission("leads", "leads", action))` at the router layer, matching
Settings (Module 4) and Dashboard's own convention for modules built after Access
Control (decision 026).
"""

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.constants.roles import EMPLOYEE, OWNER
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.features.access_control.permission_engine import PermissionEngine
from app.features.access_control.repository import (
    EmployeeRoleRepository,
    PermissionRepository,
    RolePermissionRepository,
)
from app.features.auth.models import User
from app.features.auth.repository import UserRepository
from app.features.customer.constants import ApplicationStatus, DocumentVerificationStatus
from app.features.customer.models import Application
from app.features.customer.repository import (
    ApplicationDocumentRepository,
    ApplicationFormDefinitionRepository,
    ApplicationRepository,
)
from app.features.employee.constants import EmploymentStatus
from app.features.employee.repository import (
    BranchRepository,
    DesignationRepository,
    EmployeeRepository,
)
from app.features.leads.constants import PRODUCT_CATEGORY_MODULE, LeadActivityType, LeadStage
from app.features.leads.models import Lead, LeadActivity, LeadFinancialAssessment, LeadNote
from app.features.leads.repository import (
    ASSIGNED_SENTINEL,
    NO_MATCH_SENTINEL,
    SELF_SENTINEL,
    UNASSIGNED_SENTINEL,
    LeadActivityRepository,
    LeadNoteRepository,
    LeadRepository,
)
from app.features.leads.schemas import (
    CreateLeadRequest,
    EligibleAssigneeResponse,
    FinancialAssessmentRequest,
    LeadCountsResponse,
    UpdateLeadRequest,
)
from app.features.owner.repository import OwnerProfileRepository
from app.features.system_settings.constants import MasterDataStatus
from app.features.system_settings.repository import (
    InsuranceProductRepository,
    LeadSourceRepository,
    LoanProductRepository,
)
from app.features.workflow_engine.constants import TERMINAL_STATUSES_BY_CASE_TYPE
from app.features.workflow_engine.repository import ApplicationWorkflowRepository
from app.shared.audit_log import write_audit_log
from app.utils.datetime import ist_date_to_utc_midnight, now_ist, start_of_day_ist, utc_now
from app.utils.id_generator import IdPrefix, generate_id

_EXPORT_HEADER = ["Lead Code", "Name", "Mobile", "Email", "Source", "Product Category", "Product", "Status", "Stage", "Assigned To", "Created At"]


@dataclass
class DocumentCollectionSummary:
    """Leads workflow redesign Phase 3 (decision 126) — read-only enrichment surfaced on
    a Lead's detail response, derived entirely from the existing Application/
    ApplicationDocument entities (Module 6B). `None`/zero fields mean no Application
    exists for this lead yet (a legitimate state, not an error — see
    LeadService.get_document_collection_summary)."""

    application_id: str | None
    application_status: str | None
    documents_required: int
    documents_verified: int
    all_documents_verified: bool


class LeadService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self._db = db
        self._leads = LeadRepository(db)
        self._notes = LeadNoteRepository(db)
        self._activities = LeadActivityRepository(db)
        self._employees = EmployeeRepository(db)
        self._lead_sources = LeadSourceRepository(db)
        self._loan_products = LoanProductRepository(db)
        self._insurance_products = InsuranceProductRepository(db)
        self._form_defs = ApplicationFormDefinitionRepository(db)
        self._applications = ApplicationRepository(db)
        self._application_documents = ApplicationDocumentRepository(db)
        self._owners = OwnerProfileRepository(db)
        self._users = UserRepository(db)
        self._permissions = PermissionRepository(db)
        self._role_permissions = RolePermissionRepository(db)
        self._employee_roles = EmployeeRoleRepository(db)
        self._designations = DesignationRepository(db)
        self._branches = BranchRepository(db)
        self._workflow_cases = ApplicationWorkflowRepository(db)
        self._permission_engine = PermissionEngine(db)

    # ---------------------------------------------------------------- validation helpers

    async def _validate_source(self, source_id: str) -> None:
        if await self._lead_sources.find_by_id(source_id) is None:
            raise ValidationError("Unknown source_id.")

    async def _validate_product(self, product_category: str, product_id: str) -> None:
        repo = self._loan_products if product_category == "loan" else self._insurance_products
        if await repo.find_by_id(product_id) is None:
            raise ValidationError(f"Unknown product_id for category '{product_category}'.")

    async def _log_activity(self, lead_id: str, event_type: str, actor: User, metadata: dict[str, Any] | None = None) -> None:
        activity = LeadActivity(lead_id=lead_id, event_type=event_type, metadata=metadata, created_by=actor.require_id())
        await self._activities.insert(activity)
        await write_audit_log(
            self._db, event_type=f"lead_{event_type}", user_id=actor.require_id(), metadata={"lead_id": lead_id, **(metadata or {})}
        )

    # ---------------------------------------------------------------- create / read / update

    async def create_lead(self, payload: CreateLeadRequest, actor: User) -> Lead:
        await self._validate_source(payload.source_id)
        await self._validate_product(payload.product_category, payload.product_id)

        # Duplicate-lead prevention (production bug fix): `mobile` is already normalized
        # by CreateLeadRequest's own strict pattern (`^[6-9]\d{9}$`, no separators/
        # whitespace possible) before this method ever runs — that IS the normalization
        # step; no separate transform is needed on an already-schema-validated value.
        # Company-wide, unscoped lookup (matches the existing `find_by_mobile` docstring
        # precedent below) — a genuine duplicate must be caught regardless of who owns
        # the existing lead. Only an ACTIVE (non-rejected) duplicate blocks creation — a
        # previously rejected lead for this mobile doesn't prevent a fresh inquiry later;
        # that pipeline already concluded. See `LeadRepository`'s new partial unique
        # index (`rejected_at=None`) for the matching database-level safety net against
        # a race between two simultaneous creates for the same mobile.
        duplicates = await self._leads.find_by_mobile(payload.mobile)
        active_duplicate = next((d for d in duplicates if d.stage != LeadStage.REJECTED), None)
        if active_duplicate is not None:
            raise ConflictError(
                f"A lead already exists with this mobile number ({active_duplicate.lead_code}).",
                details={"existing_lead_id": active_duplicate.require_id(), "existing_lead_code": active_duplicate.lead_code},
            )
        # Only rejected leads can remain here — kept as the existing non-blocking
        # "possible duplicate" flag (spec: duplicate detection flags a rejected-mobile
        # match, never blocks it).
        duplicate_ids = [d.require_id() for d in duplicates]

        # Looked up only to stamp `form_definition_id` for later reference — Create Lead
        # collects basic lead info only (see docs/decisions/DECISIONS.md); the Product
        # Schema Engine's *validation* belongs solely to the Customer's own Application
        # (features/customer/service.py:submit_application), never to Lead creation. A
        # product with no schema yet (or a Lead created before this existed) behaves
        # exactly as before — both fields stay null.
        form_def = await self._form_defs.find_by_product(payload.product_category, payload.product_id)

        lead_code = await generate_id(self._db, IdPrefix.LEAD)
        next_follow_up = ist_date_to_utc_midnight(payload.next_follow_up_date) if payload.next_follow_up_date else None
        lead = Lead(
            lead_code=lead_code,
            full_name=payload.full_name,
            mobile=payload.mobile,
            email=payload.email,
            source_id=payload.source_id,
            product_category=payload.product_category,
            product_id=payload.product_id,
            remarks=payload.remarks,
            city=payload.city,
            preferred_amount=payload.preferred_amount,
            salary_in_hand=payload.salary_in_hand,
            next_follow_up_date=next_follow_up,
            duplicate_of_lead_ids=duplicate_ids,
            form_definition_id=form_def.require_id() if form_def else None,
            product_form_data=payload.product_form_data,
            created_by=actor.require_id(),
        )
        lead_id = await self._leads.insert(lead)

        await self._log_activity(lead_id, LeadActivityType.CREATED, actor, {"lead_code": lead_code})
        if duplicate_ids:
            await self._log_activity(lead_id, LeadActivityType.DUPLICATE_DETECTED, actor, {"matches": duplicate_ids})

        # `add_note`/`_assign` both re-fetch and ownership-check the lead by id — safe and
        # cheap here since the actor who just created it always passes `get_lead_scoped`
        # (it's their own, still-unassigned draft) until `_assign` moves it out from under
        # that check.
        if payload.comment:
            await self.add_note(lead_id, payload.comment, actor)

        if payload.assigned_to:
            employee_id = await self._resolve_assignee(payload.assigned_to, actor)
            return await self._assign(lead_id, employee_id, actor)

        return await self._leads.find_by_id(lead_id) or lead

    async def get_lead(self, lead_id: str) -> Lead:
        lead = await self._leads.find_by_id(lead_id)
        if lead is None:
            raise NotFoundError("Lead not found.")
        return lead

    async def get_lead_scoped(self, lead_id: str, actor: User) -> Lead:
        """The single-record counterpart of `list_leads`' own scoping: an Owner reads any
        lead. A non-Owner may read a lead currently assigned to them, OR one they
        personally created that hasn't been assigned to anyone yet (their own draft) —
        creating a lead must not cost the creator visibility of it the moment it's still
        unassigned. `get_lead` itself stays unscoped and is still used internally by
        `assign_lead`/`unassign_lead`, where the distinct, coarser `assign` permission
        (not per-record ownership) is the intended boundary — a lead must be
        readable-by-id in order to be picked up/reassigned in the first place. This
        variant is for the read/edit/timeline/notes routes, which `list_leads` already
        implies should be ownership-scoped for a non-Owner."""
        lead = await self.get_lead(lead_id)
        if actor.role != OWNER:
            employee = await self._employees.find_by_user_id(actor.require_id())
            employee_id = employee.require_id() if employee is not None else NO_MATCH_SENTINEL
            is_assigned_to_me = lead.assigned_to == employee_id
            # `Lead.created_by` is stamped from `actor.require_id()` at creation time
            # (BaseDocument's generic convention) — the actor's own User id, NOT their
            # Employee document id (which is what `assigned_to` stores, from
            # AssignLeadRequest.employee_id). Comparing against the wrong id space here
            # would silently never match a real self-authored draft.
            is_my_unassigned_draft = lead.assigned_to is None and lead.created_by == actor.require_id()
            if not (is_assigned_to_me or is_my_unassigned_draft):
                raise ForbiddenError("This lead isn't assigned to you.")
        return lead

    async def _has_broad_visibility(self, actor: User) -> bool:
        """Owner-level visibility into the shared, company-wide Fresh Leads / Document
        Collection / Rejected / Assigned pools (decision 125's visibility-gap fix),
        reusing the existing `leads:leads:assign` permission — an actor already trusted
        to distribute leads across the team is trusted to see the pool they're
        distributing from. Deliberately NOT a new permission: an Owner granting "Assign"
        to a role already means "this role manages lead distribution," and inventing a
        second, separate visibility permission would be redundant configuration for the
        same underlying trust decision."""
        if actor.role == OWNER:
            return True
        return await self._permission_engine.has_permission(actor, module="leads", resource="leads", action="assign")

    async def _scope_query(
        self, actor: User, requested_assigned_to: str | None, requested_stage: str | None = None
    ) -> tuple[str | None, str | None]:
        """Returns `(assigned_to, created_by)` to hand to `LeadRepository.search_and_filter`
        /`count_filtered`. `requested_stage` only ever affects which SCOPING branch below
        applies — it's passed straight through to the repository unchanged by the caller,
        never transformed here.

        `SELF_SENTINEL` ("My Leads") resolves to the actor's own Employee id for an
        Employee. Production bug fix: an Owner has no Employee record by design
        (`OwnerProfile` is its own collection, separate from `employees` — the same
        "login identity lives in the shared `users` collection, profile data lives in
        its own collection" split every role already uses) — for an Owner actor this
        instead resolves to the Owner's own User id (`actor.require_id()`), which is
        what `_assign` will store directly in `Lead.assigned_to` for an Owner
        self-assignment. See `_assign`'s own docstring for the full explanation.

        An Owner otherwise sees whatever `assigned_to` was requested — a specific
        employee, the "unassigned"/"assigned to anyone" sentinels, or unfiltered —
        completely unrestricted, `created_by` stays unused.

        A non-Owner (Employee) can NEVER see another employee's leads by default: any
        request other than the sentinels below is always overridden to their own
        employee_id.

        `UNASSIGNED_SENTINEL` (Fresh Leads): a broad-visibility actor (see
        `_has_broad_visibility`) gets the true, company-wide unassigned pool. Anyone else
        gets "my own not-yet-assigned drafts only" — the repository ANDs `created_by`
        onto the `assigned_to=None` filter for this case. An unassigned lead a non-broad
        actor did not personally create is invisible to them until explicitly assigned.

        `ASSIGNED_SENTINEL` (Assigned tab) or `requested_stage` in
        {document_collection, rejected} (Document Collection / Rejected tabs): a
        broad-visibility actor sees the company-wide set; anyone else is scoped to their
        own `assigned_to=<employee_id>` — visible-but-self-scoped rather than hidden,
        since every role sees all 5 tabs (decision 125).

        The `created_by` value returned here is the actor's own User id (`Lead.created_by`
        is always stamped from `actor.require_id()`, BaseDocument's generic convention —
        NOT the Employee document id `assigned_to` uses), not `employee_id`."""
        if requested_assigned_to == SELF_SENTINEL:
            if actor.role == OWNER:
                return actor.require_id(), None
            employee = await self._employees.find_by_user_id(actor.require_id())
            return (employee.require_id() if employee is not None else NO_MATCH_SENTINEL), None

        if actor.role == OWNER:
            return requested_assigned_to, None

        employee = await self._employees.find_by_user_id(actor.require_id())
        employee_id = employee.require_id() if employee is not None else NO_MATCH_SENTINEL

        if requested_assigned_to == UNASSIGNED_SENTINEL:
            if await self._has_broad_visibility(actor):
                return UNASSIGNED_SENTINEL, None
            return UNASSIGNED_SENTINEL, actor.require_id()

        if requested_assigned_to == ASSIGNED_SENTINEL or requested_stage in (LeadStage.DOCUMENT_COLLECTION, LeadStage.REJECTED):
            if await self._has_broad_visibility(actor):
                return requested_assigned_to, None
            return employee_id, None

        return employee_id, None

    async def list_leads(
        self, *, search: str | None, source_id: str | None, product_category: str | None, product_id: str | None,
        assigned_to: str | None, status: str | None, stage: str | None = None, exclude_stage: str | None = None,
        skip: int, limit: int, sort: list[tuple[str, int]] | None, actor: User,
    ) -> tuple[list[Lead], int]:
        scoped_assigned_to, scoped_created_by = await self._scope_query(actor, assigned_to, stage)
        return await self._leads.search_and_filter(
            search=search, source_id=source_id, product_category=product_category, product_id=product_id,
            assigned_to=scoped_assigned_to, created_by=scoped_created_by, status=status, stage=stage,
            exclude_stage=exclude_stage, skip=skip, limit=limit, sort=sort,
        )

    async def get_application_info_for_leads(self, leads: list[Lead], stage: str | None) -> dict[str, tuple[str, str]]:
        """Leads workflow redesign Phase 3 (decision 126) — batched `lead_id ->
        (application_id, application_status)` lookup for the Document Collection tab's
        list view, so it can show "Pending"/"Submitted" without one query per row. Only
        runs when the effective tab filter is `document_collection` — every other tab's
        list call is completely unaffected, cost-wise or otherwise."""
        if stage != LeadStage.DOCUMENT_COLLECTION or not leads:
            return {}
        lead_ids = [lead.require_id() for lead in leads]
        applications = await self._applications.find_for_leads(lead_ids)
        result: dict[str, tuple[str, str]] = {}
        for application in applications:
            if application.lead_id and application.lead_id not in result:
                result[application.lead_id] = (application.require_id(), application.status)

        # Fallback for leads not resolved via the direct lead_id join — Application.lead_id
        # is only ever set by the secure-link claim flow (Flow 1); `start_application`
        # (Flow 2, and any Flow-1 customer continuing after profile completion) always
        # leaves it null even though Lead.customer_id/Application.customer_id are
        # reliably linked. See ApplicationRepository.find_for_customers_and_products.
        unresolved = [lead for lead in leads if lead.require_id() not in result and lead.customer_id]
        if unresolved:
            triples = [(lead.customer_id, lead.product_category, lead.product_id) for lead in unresolved if lead.customer_id]
            fallback_applications = await self._applications.find_for_customers_and_products(triples)
            by_customer_and_product = {(a.customer_id, a.product_category, a.product_id): a for a in reversed(fallback_applications)}
            for lead in unresolved:
                fallback_application = by_customer_and_product.get((lead.customer_id, lead.product_category, lead.product_id))
                if fallback_application is not None:
                    result[lead.require_id()] = (fallback_application.require_id(), fallback_application.status)
        return result

    async def _document_completion(self, application: Application) -> tuple[int, int]:
        """`(documents_required, documents_verified)` for `application`, counting only
        CURRENT documents — a superseded row from before a re-upload must never count
        toward verification, matching the exact `is_current` discipline the Application/
        ApplicationDocument system itself already enforces on every other read (see
        `customer/service.py`'s `supersede_current`)."""
        form_def = await self._form_defs.find_by_id(application.form_definition_id)
        required_ids = set(form_def.required_document_type_ids) if form_def else set()
        if not required_ids:
            return 0, 0
        current_docs = await self._application_documents.find_current_for_application(application.require_id())
        verified_ids = {
            d.document_type_id
            for d in current_docs
            if d.document_type_id in required_ids and d.verification_status == DocumentVerificationStatus.VERIFIED
        }
        return len(required_ids), len(verified_ids)

    async def get_document_collection_summary(self, lead: Lead) -> DocumentCollectionSummary:
        """Detail-level counterpart of `get_application_info_for_leads` — always computed
        (cheap at single-lead granularity), backing both `GET /leads/{id}` and every other
        detail-returning endpoint, and the "N of M documents verified" text in My Leads'
        Update screen. `application_id=None` means the customer hasn't used Generate Link
        yet — a legitimate "Pending" state, never an error."""
        application = await self._applications.find_by_lead_id(lead.require_id())
        if application is None and lead.customer_id:
            # Fallback via the reliable customer_id join — see
            # ApplicationRepository.find_latest_by_customer_and_product's own docstring.
            application = await self._applications.find_latest_by_customer_and_product(
                lead.customer_id, lead.product_category, lead.product_id
            )
        if application is None:
            return DocumentCollectionSummary(
                application_id=None, application_status=None, documents_required=0, documents_verified=0, all_documents_verified=False
            )
        required, verified = await self._document_completion(application)
        return DocumentCollectionSummary(
            application_id=application.require_id(), application_status=application.status,
            documents_required=required, documents_verified=verified, all_documents_verified=verified >= required,
        )

    async def get_tab_counts(self, actor: User) -> LeadCountsResponse:
        """One count per Leads tab, each built from the identical scoping
        (`_scope_query`) the matching tab's list call uses — counts and list results can
        never disagree (decision 125's counts requirement)."""
        fresh_assigned_to, fresh_created_by = await self._scope_query(actor, UNASSIGNED_SENTINEL, LeadStage.FRESH)
        fresh = await self._leads.count_filtered(assigned_to=fresh_assigned_to, created_by=fresh_created_by, stage=LeadStage.FRESH)

        my_assigned_to, my_created_by = await self._scope_query(actor, SELF_SENTINEL, LeadStage.ASSIGNED)
        my_leads = await self._leads.count_filtered(assigned_to=my_assigned_to, created_by=my_created_by, stage=LeadStage.ASSIGNED)

        dc_assigned_to, dc_created_by = await self._scope_query(actor, None, LeadStage.DOCUMENT_COLLECTION)
        document_collection = await self._leads.count_filtered(
            assigned_to=dc_assigned_to, created_by=dc_created_by, stage=LeadStage.DOCUMENT_COLLECTION
        )

        rej_assigned_to, rej_created_by = await self._scope_query(actor, None, LeadStage.REJECTED)
        rejected = await self._leads.count_filtered(assigned_to=rej_assigned_to, created_by=rej_created_by, stage=LeadStage.REJECTED)

        asg_assigned_to, asg_created_by = await self._scope_query(actor, ASSIGNED_SENTINEL, None)
        assigned = await self._leads.count_filtered(assigned_to=asg_assigned_to, created_by=asg_created_by, exclude_stage=LeadStage.REJECTED)

        return LeadCountsResponse(fresh=fresh, my_leads=my_leads, document_collection=document_collection, rejected=rejected, assigned=assigned)

    async def _resolve_assignee(self, assigned_to: str, actor: User) -> str:
        """Production bug fix: "Assign To: Self" now works for an Owner too — an Owner
        has no Employee record by design, so it resolves to the Owner's own User id
        instead of raising. See `_assign`'s docstring for how that id is then handled."""
        if assigned_to == SELF_SENTINEL:
            if actor.role == OWNER:
                return actor.require_id()
            employee = await self._employees.find_by_user_id(actor.require_id())
            if employee is None:
                raise ValidationError("You have no employee record to assign a lead to.")
            return employee.require_id()
        return assigned_to

    async def update_lead(self, lead_id: str, payload: UpdateLeadRequest, actor: User, *, skip_ownership_check: bool = False) -> Lead:
        """`skip_ownership_check` is for callers (e.g. Referral Partner Management's own
        lead-edit endpoint) that have already authorized the edit through their own,
        non-Employee ownership model before delegating here — `get_lead_scoped` only
        knows how to scope Owner vs. Employee actors, so it wrongly rejects any other
        role (e.g. a Referral Partner) even when that caller already confirmed the
        actor may edit this lead. Defaults to the existing scoped behavior."""
        lead = await self.get_lead(lead_id) if skip_ownership_check else await self.get_lead_scoped(lead_id, actor)
        updates: dict[str, Any] = {}

        if payload.source_id is not None:
            await self._validate_source(payload.source_id)
            updates["source_id"] = payload.source_id

        new_category = payload.product_category or lead.product_category
        if payload.product_id is not None or payload.product_category is not None:
            new_product_id = payload.product_id or lead.product_id
            await self._validate_product(new_category, new_product_id)
            updates["product_category"] = new_category
            updates["product_id"] = new_product_id

        for field in ("full_name", "mobile", "email", "remarks", "city", "preferred_amount", "salary_in_hand"):
            value = getattr(payload, field)
            if value is not None:
                updates[field] = value

        if payload.next_follow_up_date is not None:
            updates["next_follow_up_date"] = ist_date_to_utc_midnight(payload.next_follow_up_date)

        if updates:
            updated = await self._leads.update(lead_id, updates, updated_by=actor.require_id())
            await self._log_activity(lead_id, LeadActivityType.UPDATED, actor, {"fields": list(updates.keys())})
            lead = updated or lead

        # Deliberately still excludes `form_definition_id`/`product_form_data` — the
        # Product Schema Engine's own dynamic fields stay Lead-edit-untouched, preserving
        # the original reason those were kept off Create Lead too (see the field's own
        # comment on CreateLeadRequest).
        if payload.assigned_to is not None:
            employee_id = await self._resolve_assignee(payload.assigned_to, actor)
            lead = await self._assign(lead_id, employee_id, actor)

        if payload.comment:
            await self.add_note(lead_id, payload.comment, actor)

        return lead

    async def check_duplicate(self, mobile: str, actor: User) -> list[Lead]:
        # Unlike the internal creation-time duplicate check (which intentionally scans
        # company-wide — a genuine duplicate must be caught regardless of who owns the
        # existing lead), this is the pre-submission `/leads/check-duplicate` lookup
        # exposed to any actor holding just `leads:leads:view`. Returning full
        # LeadListItem detail (name/email/product/assignee) for leads outside the same
        # visibility `list_leads` already enforces would let a low-privilege Employee
        # harvest the whole company's lead book by mobile number.
        matches = await self._leads.find_by_mobile(mobile)
        if actor.role == OWNER:
            return matches
        employee = await self._employees.find_by_user_id(actor.require_id())
        employee_id = employee.require_id() if employee is not None else NO_MATCH_SENTINEL
        # `lead.created_by` is a User id (BaseDocument's generic stamp), not the Employee
        # id `assigned_to`/`employee_id` use — see get_lead_scoped's docstring.
        return [
            lead
            for lead in matches
            if lead.assigned_to == employee_id or (lead.assigned_to is None and lead.created_by == actor.require_id())
        ]

    # ---------------------------------------------------------------- assignment

    async def _assign(self, lead_id: str, assignee_id: str, actor: User) -> Lead:
        """Shared by `assign_lead` (POST /leads/{id}/assign), Create Lead's inline
        `assigned_to`, and Edit Lead's inline `assigned_to` — one place that stamps
        `stage=assigned`/`assigned_by`/`assigned_at` alongside `assigned_to`, so every
        assignment path keeps those fields consistent (decision 125).

        `assignee_id` is normally an Employee document id. Production bug fix: an Owner
        assigning a lead to themselves ("Assign To: Self", resolved by
        `_resolve_assignee`/`_scope_query`) has no Employee record, so for that case
        `assignee_id` is instead the Owner's own User id. Detected here by looking the
        id up in `users` and checking `role == OWNER` — deliberately NOT via
        `OwnerProfileRepository`, since an `OwnerProfile` row is optional profile detail
        (display name etc.) that a legacy/grandfathered Owner account may not have (see
        Owner Account Management's grandfather logic), while `User.role` is the one
        authoritative, always-present source of "is this id an Owner." This also
        correctly handles an Owner assigning a lead to a DIFFERENT existing Owner
        account (Secondary Owner) if ever driven through this same path. This never
        creates an Employee record for an Owner and never introduces a second assignment
        mechanism — `assigned_to` remains the single field on `Lead`, just correctly
        able to hold either id space, exactly the same way `Lead.created_by` already
        holds a User id while `assigned_to` normally holds an Employee id (see
        `get_lead_scoped`'s docstring)."""
        assignee_user = await self._users.find_by_id(assignee_id)
        if assignee_user is not None and assignee_user.role == OWNER:
            recipient_user_id = assignee_id
        else:
            employee = await self._employees.find_by_id(assignee_id)
            if employee is None:
                raise ValidationError("Unknown employee_id.")
            if employee.status != EmploymentStatus.ACTIVE:
                raise ValidationError("Cannot assign a lead to an inactive employee.")
            recipient_user_id = employee.user_id

        updated = await self._leads.update(
            lead_id,
            {"assigned_to": assignee_id, "stage": LeadStage.ASSIGNED, "assigned_by": actor.require_id(), "assigned_at": utc_now()},
            updated_by=actor.require_id(),
        )
        if updated is None:
            raise NotFoundError("Lead not found.")
        await self._log_activity(lead_id, LeadActivityType.ASSIGNED, actor, {"employee_id": assignee_id})
        # NotificationType.LEAD_ASSIGNED has existed since Module 6D but was never wired
        # up to the one event it names — Reminders' own create_task is the only caller
        # that ever fired a notification. No import cycle: reminders/service.py doesn't
        # import from leads.
        from app.features.reminders.constants import NotificationType
        from app.features.reminders.service import RemindersService

        await RemindersService(self._db).create_notification(
            recipient_user_id=recipient_user_id, notification_type=NotificationType.LEAD_ASSIGNED,
            title="New Lead Assigned", message=f'You have been assigned a new lead: "{updated.full_name}".',
            entity_type="lead", entity_id=lead_id,
        )
        return updated

    async def assign_lead(self, lead_id: str, employee_id: str, actor: User) -> Lead:
        await self.get_lead(lead_id)
        return await self._assign(lead_id, employee_id, actor)

    async def unassign_lead(self, lead_id: str, actor: User) -> Lead:
        lead = await self.get_lead(lead_id)
        if lead.stage == LeadStage.REJECTED:
            raise ValidationError("A rejected lead cannot be unassigned.")
        updated = await self._leads.update(
            lead_id, {"assigned_to": None, "stage": LeadStage.FRESH, "assigned_by": None, "assigned_at": None},
            updated_by=actor.require_id(),
        )
        if updated is None:
            raise NotFoundError("Lead not found.")
        await self._log_activity(lead_id, LeadActivityType.UNASSIGNED, actor)
        return updated

    # ---------------------------------------------------------------- reject / stage / follow-up (decision 125)

    async def reject_lead(self, lead_id: str, reason: str, actor: User) -> Lead:
        """Reject is reachable only from an already-assigned lead (My Leads ->
        Rejected, per the spec) — a still-unassigned Fresh lead has no owner to have
        made the rejection call, and disallowing it here keeps the Rejected tab's own
        visibility scoping simple (every rejected lead still has a non-null
        `assigned_to`, so the same `assigned_to=<employee_id>` scoping `_scope_query`
        already uses for Document Collection/Assigned applies unchanged to Rejected)."""
        lead = await self.get_lead_scoped(lead_id, actor)
        if lead.assigned_to is None:
            raise ValidationError("Only an assigned lead can be rejected.")
        if lead.stage == LeadStage.REJECTED:
            raise ValidationError("This lead has already been rejected.")
        if lead.stage == LeadStage.LOAN_MANAGEMENT:
            raise ValidationError("A lead that has moved to Loan Management can no longer be rejected here.")
        updated = await self._leads.update(
            lead_id,
            {"stage": LeadStage.REJECTED, "rejected_reason": reason, "rejected_by": actor.require_id(), "rejected_at": utc_now()},
            updated_by=actor.require_id(),
        )
        if updated is None:
            raise NotFoundError("Lead not found.")
        await self._log_activity(lead_id, LeadActivityType.REJECTED, actor, {"reason": reason})
        return updated

    async def set_stage(self, lead_id: str, stage: str, actor: User) -> Lead:
        """Phase 1 supports My Leads <-> Document Collection (`SetStageRequest` validated
        `stage` is one of `assigned`/`document_collection`/`loan_management` — Fresh and
        Rejected are reached exclusively via `_assign`/`reject_lead`, never this
        endpoint). Phase 3 (decision 126) adds Document Collection -> Loan Management,
        gated on the linked Application being submitted and every required document
        verified — the one new business rule this phase introduces.

        Decision #130 (amends the note this docstring used to carry): a Loan Case is
        still created lazily and automatically the moment the customer submits (see
        `LeadStage.LOAN_MANAGEMENT`'s own docstring and decision #058) — that part is
        unchanged. But the case stays gated (`moved_to_loan_management_at is None`,
        invisible to Loan Management's list/counts/detail) until THIS method's checks
        pass, at which point it explicitly marks the case as moved. This closes the gap
        where a case was fully visible/actionable in Loan Management from the moment of
        submission, regardless of whether a Lead ever reached this stage or whether its
        documents were ever actually verified. Only loan-category applications are
        marked here — Insurance's own visibility is a separate, untouched concern."""
        lead = await self.get_lead_scoped(lead_id, actor)
        if lead.assigned_to is None:
            raise ValidationError("Only an assigned lead can change stage.")
        if lead.stage == LeadStage.REJECTED:
            raise ValidationError("A rejected lead cannot change stage.")
        application: Application | None = None
        if stage == LeadStage.LOAN_MANAGEMENT:
            if lead.stage != LeadStage.DOCUMENT_COLLECTION:
                raise ValidationError("Only a lead in Document Collection can move to Loan Management.")
            application = await self._applications.find_by_lead_id(lead_id)
            if application is None or application.status != ApplicationStatus.SUBMITTED:
                raise ValidationError("The customer must submit their application before this lead can move to Loan Management.")
            required, verified = await self._document_completion(application)
            if verified < required:
                raise ValidationError(
                    f"{verified} of {required} required documents are verified. All required documents must be "
                    "verified before moving to Loan Management."
                )
        updated = await self._leads.update(lead_id, {"stage": stage}, updated_by=actor.require_id())
        if updated is None:
            raise NotFoundError("Lead not found.")
        event_type = LeadActivityType.MOVED_TO_LOAN_MANAGEMENT if stage == LeadStage.LOAN_MANAGEMENT else LeadActivityType.STAGE_CHANGED
        await self._log_activity(lead_id, event_type, actor, {"from": lead.stage, "to": stage})
        if stage == LeadStage.LOAN_MANAGEMENT and application is not None and application.product_category == "loan":
            # Deferred import: loan_management imports this module's `Application` model
            # at module level, so importing it back at module level here would be
            # circular — same precedent as `CustomerService.submit_application`.
            from app.features.loan_management.service import LoanCaseService

            await LoanCaseService(self._db).mark_moved_to_loan_management(application.require_id(), actor)
        return updated

    async def set_follow_up(self, lead_id: str, next_follow_up_date: date, comment: str | None, actor: User) -> Lead:
        await self.get_lead_scoped(lead_id, actor)
        updated = await self._leads.update(
            lead_id, {"next_follow_up_date": ist_date_to_utc_midnight(next_follow_up_date)}, updated_by=actor.require_id()
        )
        if updated is None:
            raise NotFoundError("Lead not found.")
        # Comment History (decision 125): a follow-up comment is a NEW LeadNote, exactly
        # like `add_note` — never overwrites a prior entry.
        if comment:
            await self.add_note(lead_id, comment, actor)
        await self._log_activity(lead_id, LeadActivityType.FOLLOW_UP_SET, actor, {"next_follow_up_date": next_follow_up_date.isoformat()})
        return updated

    # ---------------------------------------------------------------- financial assessment (Phase 2, decision 125)

    async def set_financial_assessment(self, lead_id: str, payload: FinancialAssessmentRequest, actor: User) -> Lead:
        """My Leads' Update screen. A whole-object replace, not a partial-field PATCH —
        the frontend always submits the full current form state, so there's no ambiguity
        about what an omitted field means (unlike `update_lead`'s per-field-optional
        convention). Does not touch `stage`, `status`, `assigned_to`, or counts."""
        await self.get_lead_scoped(lead_id, actor)
        data = payload.model_dump()
        # Mutually exclusive by construction: "Don't Know" always wins over a
        # stray/previously-entered score, cleanly rather than leaving both set.
        if data["cibil_unknown"]:
            data["cibil_score"] = None
        assessment = LeadFinancialAssessment(**data, updated_at=utc_now(), updated_by=actor.require_id())
        updated = await self._leads.update(lead_id, {"financial_assessment": assessment.model_dump()}, updated_by=actor.require_id())
        if updated is None:
            raise NotFoundError("Lead not found.")
        await self._log_activity(lead_id, LeadActivityType.FINANCIAL_ASSESSMENT_UPDATED, actor)
        return updated

    # ---------------------------------------------------------------- public audit-log wrapper

    async def log_activity(self, lead_id: str, event_type: str, actor: User, metadata: dict[str, Any] | None = None) -> None:
        """Public entry point into `_log_activity` for cross-module callers that act on a
        Lead from outside this service (e.g. the router composing
        `CustomerService.create_staff_initiated_account` for Phase 2's Create Customer
        Account) — keeps the Lead-scoped audit trail owned by Leads even when the action
        itself is owned by another module."""
        await self._log_activity(lead_id, event_type, actor, metadata)

    async def _employees_with_module_access(self, module: str) -> set[str]:
        """Every employee whose role holds at least one granted action on ANY
        permission catalog entry under `module` — the same "has module access" concept
        PermissionEngine.get_accessible_modules already uses for nav/menu filtering
        (see access_control/permission_engine.py), computed here in bulk across every
        employee instead of per-user. Deliberately module-wide, not tied to one
        `resource` — a future module with more than one resource (e.g. `loan_management`
        later adding a `disbursements` resource alongside `applications`) should make an
        employee eligible via access to *either*, without this method changing."""
        permissions = await self._permissions.find_by_module(module)
        permission_ids = {p.require_id() for p in permissions}
        if not permission_ids:
            return set()
        grants = await self._role_permissions.find_many({"permission_id": {"$in": list(permission_ids)}}, limit=5000)
        role_ids = {g.role_id for g in grants if g.granted_actions}
        if not role_ids:
            return set()
        employee_roles = await self._employee_roles.find_for_roles(list(role_ids))
        return {er.employee_id for er in employee_roles}

    async def list_eligible_assignees(
        self, product_category: str, product_id: str | None, actor: User
    ) -> list[EligibleAssigneeResponse]:
        """Active employees who have module access for this lead's product category —
        e.g. a "loan" lead's eligible assignees are every active employee whose role
        grants any access under the "loan_management" module (see
        PRODUCT_CATEGORY_MODULE in leads/constants.py, the one place that mapping
        lives). Deliberately NOT a `leads:leads:assign` permission check — an Owner
        already grants module access when setting up a role and should never need to
        configure a second, separate assignment permission just so employees can
        receive leads. Works for any current or future product category purely by
        adding an entry to PRODUCT_CATEGORY_MODULE — this method never branches on
        "loan" vs "insurance" itself. Enriched with designation/branch/workload/product-
        specialization purely as business context for the Owner/Employee choosing —
        never itself an authorization check (see EligibleAssigneeResponse docstring).

        Recommendation priority (all tie-breaks, never a filter — eligibility itself is
        decided entirely above by module access): product specialization match (see
        Employee.product_ids — optional, has no effect until an Owner starts curating
        it) > lowest current active lead count > lowest open case count on this
        category's pipeline > fewest assignments today > fewest assignments this week >
        same branch as the assigning Employee (skipped for an Owner actor, who has no
        branch of their own) > alphabetical. A specialist is preferred over a generalist
        even at a higher workload; among equally-specialized (or equally
        unspecialized) candidates, workload still distributes new leads across the
        eligible team instead of always picking the same employee."""
        module = PRODUCT_CATEGORY_MODULE.get(product_category)
        eligible_employee_ids = await self._employees_with_module_access(module) if module else set()
        if not eligible_employee_ids:
            return []

        all_active = await self._employees.find_many({"status": EmploymentStatus.ACTIVE}, limit=1000)
        candidates = [e for e in all_active if e.require_id() in eligible_employee_ids]
        if not candidates:
            return []

        designations = await self._designations.find_many({}, limit=500)
        branches = await self._branches.find_many({}, limit=500)
        desig_ids = {e.designation_id for e in candidates}
        branch_ids = {e.branch_id for e in candidates}
        desig_map = {d.require_id(): d.name for d in designations if d.require_id() in desig_ids}
        branch_map = {b.require_id(): b.name for b in branches if b.require_id() in branch_ids}

        actor_employee = await self._employees.find_by_user_id(actor.require_id()) if actor.role == EMPLOYEE else None
        actor_branch_id = actor_employee.branch_id if actor_employee else None

        candidate_ids = [e.require_id() for e in candidates]
        assigned_activities = await self._activities.find_assigned_for_employees(candidate_ids)
        # "Today"/"this week" mean the business (IST) calendar day/week, not UTC — see
        # app/utils/datetime.py. Both are tz-aware UTC instants; `activity.created_at`
        # (read from Mongo with tz_aware=True) is tz-aware UTC too, so these compare
        # directly with no naive/aware mismatch.
        ist_now = now_ist()
        today_start = start_of_day_ist(ist_now)
        week_start = today_start - timedelta(days=ist_now.weekday())  # Monday, IST calendar
        last_assigned_map: dict[str, datetime] = {}
        today_count_map: dict[str, int] = {}
        week_count_map: dict[str, int] = {}
        for activity in assigned_activities:
            employee_id = (activity.metadata or {}).get("employee_id")
            if not employee_id:
                continue
            if employee_id not in last_assigned_map or activity.created_at > last_assigned_map[employee_id]:
                last_assigned_map[employee_id] = activity.created_at
            if activity.created_at >= week_start:
                week_count_map[employee_id] = week_count_map.get(employee_id, 0) + 1
                if activity.created_at >= today_start:
                    today_count_map[employee_id] = today_count_map.get(employee_id, 0) + 1

        # Empty for a category with no case-tracking pipeline yet (e.g. a brand-new
        # product category added to PRODUCT_CATEGORY_MODULE before workflow_engine grows
        # a matching case_type) — open-case workload just contributes 0 then, never an error.
        open_case_terminal = set(TERMINAL_STATUSES_BY_CASE_TYPE.get(product_category, ()))

        results = []
        sort_keys: dict[str, tuple[int, int, int, int, bool, bool, str]] = {}
        for employee in candidates:
            employee_id = employee.require_id()
            current_lead_count = await self._leads.count({"assigned_to": employee_id})
            open_case_count = (
                await self._workflow_cases.count(
                    {"case_type": product_category, "assigned_to": employee_id, "current_status": {"$nin": list(open_case_terminal)}}
                )
                if open_case_terminal
                else 0
            )
            product_match = bool(product_id) and product_id in employee.product_ids
            same_branch = actor_branch_id is not None and employee.branch_id == actor_branch_id
            results.append(
                EligibleAssigneeResponse(
                    id=employee_id,
                    display_name=employee.display_name,
                    designation_name=desig_map.get(employee.designation_id, ""),
                    branch_name=branch_map.get(employee.branch_id, ""),
                    current_lead_count=current_lead_count,
                    product_match=product_match,
                    recommended=False,
                )
            )
            sort_keys[employee_id] = (
                not product_match,
                current_lead_count,
                open_case_count,
                today_count_map.get(employee_id, 0),
                week_count_map.get(employee_id, 0),
                not same_branch,
                employee.display_name,
            )

        results.sort(key=lambda r: sort_keys[r.id])
        if results:
            results[0].recommended = True
        return results

    # ---------------------------------------------------------------- notes / timeline

    async def add_note(self, lead_id: str, text: str, actor: User) -> LeadNote:
        await self.get_lead_scoped(lead_id, actor)
        note = LeadNote(lead_id=lead_id, text=text, created_by=actor.require_id())
        note_id = await self._notes.insert(note)
        await self._log_activity(lead_id, LeadActivityType.NOTE_ADDED, actor, {"note_id": note_id})
        return await self._notes.find_by_id(note_id) or note

    async def get_timeline(self, lead_id: str, actor: User) -> list[tuple[str, LeadActivity | LeadNote]]:
        await self.get_lead_scoped(lead_id, actor)
        activities = await self._activities.find_for_lead(lead_id)
        notes = await self._notes.find_for_lead(lead_id)

        # Enriches each "assigned" activity's metadata with the employee's name at read
        # time (never persisted) so the Timeline can render "Lead assigned to Rahul"
        # instead of just the bare event type — the activity itself only ever stored
        # `employee_id`, matching every other cross-module reference in this collection.
        assigned_employee_ids = {
            a.metadata.get("employee_id")
            for a in activities
            if a.event_type == LeadActivityType.ASSIGNED and a.metadata and a.metadata.get("employee_id")
        }
        if assigned_employee_ids:
            employees = await self._employees.find_many({}, limit=500)
            name_map = {e.require_id(): e.display_name for e in employees if e.require_id() in assigned_employee_ids}
            for a in activities:
                employee_id = (a.metadata or {}).get("employee_id") if a.event_type == LeadActivityType.ASSIGNED else None
                if employee_id and employee_id in name_map:
                    a.metadata = {**(a.metadata or {}), "employee_name": name_map[employee_id]}

        combined: list[tuple[str, LeadActivity | LeadNote]] = [("activity", a) for a in activities] + [("note", n) for n in notes]
        combined.sort(key=lambda entry: entry[1].created_at, reverse=True)
        return combined

    # ---------------------------------------------------------------- lookup data (Create Lead form)

    async def get_lookup_data(self) -> tuple[list[Any], list[Any], list[Any]]:
        """Lead Sources + Loan/Insurance Products for the Create Lead form's dropdowns —
        owned by Leads (gated on `leads:leads:view`, the permission this form's caller
        already has), not proxied through `system_settings`'s own CRUD-permission-gated
        endpoints (`system_settings:lead_sources:view` etc.), which would otherwise force
        granting Settings administration access just to populate a dropdown. Reuses the
        exact same repositories/sort order `resolve_names` already reads from — no new
        data access pattern, just a different, narrower permission boundary in front of
        the same read.

        Filtered to `status=active` — a deactivated Lead Source/Product must not appear
        as a selectable option on a brand new Lead (Product Visibility Rule); this never
        affects `resolve_names`, which reads an already-assigned lead's source/product by
        id directly and must keep showing historical selections regardless of status."""
        active_filter = {"status": MasterDataStatus.ACTIVE}
        sources = await self._lead_sources.find_many(active_filter, limit=500, sort=[("name", 1)])
        loan_products = await self._loan_products.find_many(active_filter, limit=500, sort=[("name", 1)])
        insurance_products = await self._insurance_products.find_many(active_filter, limit=500, sort=[("name", 1)])
        return sources, loan_products, insurance_products

    # ---------------------------------------------------------------- name resolution / export

    async def resolve_names(self, leads: list[Lead]) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
        source_ids = {lead.source_id for lead in leads}
        loan_ids = {lead.product_id for lead in leads if lead.product_category == "loan"}
        insurance_ids = {lead.product_id for lead in leads if lead.product_category == "insurance"}
        employee_ids = {lead.assigned_to for lead in leads if lead.assigned_to}
        # `assigned_by`/`rejected_by` are the ACTING USER's id (BaseDocument's
        # created_by/updated_by convention), not an Employee id — resolved below via
        # Employee.user_id, distinct from `employee_map` (keyed by Employee id, for
        # `assigned_to`).
        actor_user_ids = {lead.assigned_by for lead in leads if lead.assigned_by} | {lead.rejected_by for lead in leads if lead.rejected_by}

        sources = await self._lead_sources.find_many({}, limit=500)
        loan_products = await self._loan_products.find_many({}, limit=500)
        insurance_products = await self._insurance_products.find_many({}, limit=500)
        employees = await self._employees.find_many({}, limit=500) if (employee_ids or actor_user_ids) else []

        source_map = {s.require_id(): s.name for s in sources if s.require_id() in source_ids}
        product_map = {p.require_id(): p.name for p in loan_products if p.require_id() in loan_ids}
        product_map.update({p.require_id(): p.name for p in insurance_products if p.require_id() in insurance_ids})
        employee_map = {e.require_id(): e.display_name for e in employees if e.require_id() in employee_ids}
        # Production bug fix: `assigned_to` can now also hold an Owner's User id (Owner
        # self-assignment, see `_assign`'s docstring) — resolve those into names too, so
        # the frontend never has to special-case rendering a raw id. Falls back to the
        # generic "Owner" label (same convention as `actor_name_map` below) for a
        # legacy/grandfathered Owner with no `OwnerProfile` row, rather than a blank name.
        unresolved_assignee_ids = employee_ids - set(employee_map.keys())
        if unresolved_assignee_ids:
            owners = await self._owners.find_many({"user_id": {"$in": list(unresolved_assignee_ids)}}, limit=50)
            owner_name_by_user_id = {o.user_id: o.full_name for o in owners}
            employee_map.update({uid: owner_name_by_user_id.get(uid, "Owner") for uid in unresolved_assignee_ids})
        # A `assigned_by`/`rejected_by` user with no matching Employee record performed
        # the action as an Owner (Owners have no Employee row) — falls back to "Owner"
        # rather than a blank name.
        actor_by_user_id = {e.user_id: e.display_name for e in employees if e.user_id in actor_user_ids}
        actor_name_map = {uid: actor_by_user_id.get(uid, "Owner") for uid in actor_user_ids}
        return source_map, product_map, employee_map, actor_name_map

    async def export_leads_csv(self, actor: User) -> str:
        scoped_assigned_to, scoped_created_by = await self._scope_query(actor, None)
        leads, _ = await self._leads.search_and_filter(
            search=None, source_id=None, product_category=None, product_id=None,
            assigned_to=scoped_assigned_to, created_by=scoped_created_by, status=None,
            skip=0, limit=10_000, sort=[("created_at", -1)],
        )
        source_map, product_map, employee_map, _actor_name_map = await self.resolve_names(leads)

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(_EXPORT_HEADER)
        for lead in leads:
            writer.writerow([
                lead.lead_code, lead.full_name, lead.mobile, lead.email or "",
                source_map.get(lead.source_id, ""), lead.product_category, product_map.get(lead.product_id, ""), lead.status, lead.stage,
                employee_map.get(lead.assigned_to, "") if lead.assigned_to else "",
                lead.created_at.isoformat(),
            ])
        return buffer.getvalue()
