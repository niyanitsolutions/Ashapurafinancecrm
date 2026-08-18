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
from datetime import datetime, timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.constants.roles import EMPLOYEE, OWNER
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.features.access_control.repository import (
    EmployeeRoleRepository,
    PermissionRepository,
    RolePermissionRepository,
)
from app.features.auth.models import User
from app.features.customer.repository import ApplicationFormDefinitionRepository
from app.features.employee.constants import EmploymentStatus
from app.features.employee.repository import (
    BranchRepository,
    DesignationRepository,
    EmployeeRepository,
)
from app.features.leads.constants import PRODUCT_CATEGORY_MODULE, LeadActivityType
from app.features.leads.models import Lead, LeadActivity, LeadNote
from app.features.leads.repository import (
    NO_MATCH_SENTINEL,
    UNASSIGNED_SENTINEL,
    LeadActivityRepository,
    LeadNoteRepository,
    LeadRepository,
)
from app.features.leads.schemas import (
    CreateLeadRequest,
    EligibleAssigneeResponse,
    UpdateLeadRequest,
)
from app.features.system_settings.constants import MasterDataStatus
from app.features.system_settings.repository import (
    InsuranceProductRepository,
    LeadSourceRepository,
    LoanProductRepository,
)
from app.features.workflow_engine.constants import TERMINAL_STATUSES_BY_CASE_TYPE
from app.features.workflow_engine.repository import ApplicationWorkflowRepository
from app.shared.audit_log import write_audit_log
from app.utils.datetime import now_ist, start_of_day_ist
from app.utils.id_generator import IdPrefix, generate_id

_EXPORT_HEADER = ["Lead Code", "Name", "Mobile", "Email", "Source", "Product Category", "Product", "Status", "Assigned To", "Created At"]


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
        self._permissions = PermissionRepository(db)
        self._role_permissions = RolePermissionRepository(db)
        self._employee_roles = EmployeeRoleRepository(db)
        self._designations = DesignationRepository(db)
        self._branches = BranchRepository(db)
        self._workflow_cases = ApplicationWorkflowRepository(db)

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

        duplicates = await self._leads.find_by_mobile(payload.mobile)
        duplicate_ids = [d.require_id() for d in duplicates]

        # Looked up only to stamp `form_definition_id` for later reference — Create Lead
        # collects basic lead info only (see docs/decisions/DECISIONS.md); the Product
        # Schema Engine's *validation* belongs solely to the Customer's own Application
        # (features/customer/service.py:submit_application), never to Lead creation. A
        # product with no schema yet (or a Lead created before this existed) behaves
        # exactly as before — both fields stay null.
        form_def = await self._form_defs.find_by_product(payload.product_category, payload.product_id)

        lead_code = await generate_id(self._db, IdPrefix.LEAD)
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
            duplicate_of_lead_ids=duplicate_ids,
            form_definition_id=form_def.require_id() if form_def else None,
            product_form_data=payload.product_form_data,
            created_by=actor.require_id(),
        )
        lead_id = await self._leads.insert(lead)

        await self._log_activity(lead_id, LeadActivityType.CREATED, actor, {"lead_code": lead_code})
        if duplicate_ids:
            await self._log_activity(lead_id, LeadActivityType.DUPLICATE_DETECTED, actor, {"matches": duplicate_ids})

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

    async def _scope_query(self, actor: User, requested_assigned_to: str | None) -> tuple[str | None, str | None]:
        """Returns `(assigned_to, created_by)` to hand to `LeadRepository.search_and_filter`.

        An Owner sees whatever `assigned_to` was requested — a specific employee, the
        "unassigned"/"assigned to anyone" sentinels, or unfiltered — completely
        unrestricted, `created_by` stays unused.

        A non-Owner (Employee) can NEVER see another employee's leads or the shared
        "New Leads" pool: any request other than the unassigned sentinel is always
        overridden to their own employee_id, same as before.

        `UNASSIGNED_SENTINEL` from a non-Owner is the one case that changed: it no
        longer passes through unchanged (that used to expose every genuinely unassigned
        lead — including every Meta/website-captured one — to any employee holding
        `leads:leads:view`, before an Owner ever looked at it). It now resolves to "my
        own not-yet-assigned drafts only" — the repository ANDs `created_by` onto the
        `assigned_to=None` filter for this case. An unassigned lead a non-Owner did not
        personally create (including every Owner-authored or Meta-captured one) is
        Owner-only until explicitly assigned.

        The `created_by` value returned here is the actor's own User id (`Lead.created_by`
        is always stamped from `actor.require_id()`, BaseDocument's generic convention —
        NOT the Employee document id `assigned_to` uses), not `employee_id`."""
        if actor.role == OWNER:
            return requested_assigned_to, None
        employee = await self._employees.find_by_user_id(actor.require_id())
        employee_id = employee.require_id() if employee is not None else NO_MATCH_SENTINEL
        if requested_assigned_to == UNASSIGNED_SENTINEL:
            return UNASSIGNED_SENTINEL, actor.require_id()
        return employee_id, None

    async def list_leads(
        self, *, search: str | None, source_id: str | None, product_category: str | None, product_id: str | None,
        assigned_to: str | None, status: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None, actor: User,
    ) -> tuple[list[Lead], int]:
        scoped_assigned_to, scoped_created_by = await self._scope_query(actor, assigned_to)
        return await self._leads.search_and_filter(
            search=search, source_id=source_id, product_category=product_category, product_id=product_id,
            assigned_to=scoped_assigned_to, created_by=scoped_created_by, status=status, skip=skip, limit=limit, sort=sort,
        )

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

        for field in ("full_name", "mobile", "email", "remarks", "city", "preferred_amount"):
            value = getattr(payload, field)
            if value is not None:
                updates[field] = value

        if not updates:
            return lead

        updated = await self._leads.update(lead_id, updates, updated_by=actor.require_id())
        await self._log_activity(lead_id, LeadActivityType.UPDATED, actor, {"fields": list(updates.keys())})
        return updated or lead

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

    async def assign_lead(self, lead_id: str, employee_id: str, actor: User) -> Lead:
        await self.get_lead(lead_id)
        employee = await self._employees.find_by_id(employee_id)
        if employee is None:
            raise ValidationError("Unknown employee_id.")
        if employee.status != EmploymentStatus.ACTIVE:
            raise ValidationError("Cannot assign a lead to an inactive employee.")
        updated = await self._leads.update(lead_id, {"assigned_to": employee_id}, updated_by=actor.require_id())
        if updated is None:
            raise NotFoundError("Lead not found.")
        await self._log_activity(lead_id, LeadActivityType.ASSIGNED, actor, {"employee_id": employee_id})
        # NotificationType.LEAD_ASSIGNED has existed since Module 6D but was never wired
        # up to the one event it names — Reminders' own create_task is the only caller
        # that ever fired a notification. No import cycle: reminders/service.py doesn't
        # import from leads.
        from app.features.reminders.constants import NotificationType
        from app.features.reminders.service import RemindersService

        await RemindersService(self._db).create_notification(
            recipient_user_id=employee.user_id, notification_type=NotificationType.LEAD_ASSIGNED,
            title="New Lead Assigned", message=f'You have been assigned a new lead: "{updated.full_name}".',
            entity_type="lead", entity_id=lead_id,
        )
        return updated

    async def unassign_lead(self, lead_id: str, actor: User) -> Lead:
        await self.get_lead(lead_id)
        updated = await self._leads.update(lead_id, {"assigned_to": None}, updated_by=actor.require_id())
        if updated is None:
            raise NotFoundError("Lead not found.")
        await self._log_activity(lead_id, LeadActivityType.UNASSIGNED, actor)
        return updated

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

    async def resolve_names(self, leads: list[Lead]) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
        source_ids = {lead.source_id for lead in leads}
        loan_ids = {lead.product_id for lead in leads if lead.product_category == "loan"}
        insurance_ids = {lead.product_id for lead in leads if lead.product_category == "insurance"}
        employee_ids = {lead.assigned_to for lead in leads if lead.assigned_to}

        sources = await self._lead_sources.find_many({}, limit=500)
        loan_products = await self._loan_products.find_many({}, limit=500)
        insurance_products = await self._insurance_products.find_many({}, limit=500)
        employees = await self._employees.find_many({}, limit=500) if employee_ids else []

        source_map = {s.require_id(): s.name for s in sources if s.require_id() in source_ids}
        product_map = {p.require_id(): p.name for p in loan_products if p.require_id() in loan_ids}
        product_map.update({p.require_id(): p.name for p in insurance_products if p.require_id() in insurance_ids})
        employee_map = {e.require_id(): e.display_name for e in employees if e.require_id() in employee_ids}
        return source_map, product_map, employee_map

    async def export_leads_csv(self, actor: User) -> str:
        scoped_assigned_to, scoped_created_by = await self._scope_query(actor, None)
        leads, _ = await self._leads.search_and_filter(
            search=None, source_id=None, product_category=None, product_id=None,
            assigned_to=scoped_assigned_to, created_by=scoped_created_by, status=None,
            skip=0, limit=10_000, sort=[("created_at", -1)],
        )
        source_map, product_map, employee_map = await self.resolve_names(leads)

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(_EXPORT_HEADER)
        for lead in leads:
            writer.writerow([
                lead.lead_code, lead.full_name, lead.mobile, lead.email or "",
                source_map.get(lead.source_id, ""), lead.product_category, product_map.get(lead.product_id, ""), lead.status,
                employee_map.get(lead.assigned_to, "") if lead.assigned_to else "",
                lead.created_at.isoformat(),
            ])
        return buffer.getvalue()
