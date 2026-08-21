"""Seeds foundational config data — NOT business data. Safe to re-run (idempotent).

Currently seeds:
  - counters: zeroes the sequence for each id_generator prefix so it exists before first use.
  - permission catalog: one grounded starter entry (Employee Management's own actions) so
    the `permissions` collection isn't empty and Role Permission Matrix testing has
    something real to work with. Does NOT seed example roles — which roles an org wants
    (Branch Manager, Loan Officer, ...) is business configuration for the Owner to create
    via the real UI, not something to invent here.
  - bootstrap Primary Owner account: Owner/Employee have no self-signup (see
    docs/decisions/DECISIONS.md #007), so without this there is no way to ever log in.
    Requires BOOTSTRAP_OWNER_MOBILE + BOOTSTRAP_OWNER_PASSWORD + BOOTSTRAP_OWNER_NAME +
    BOOTSTRAP_OWNER_EMAIL env vars; skipped with a warning if unset (e.g. in CI) rather
    than failing the whole script. Idempotent: never overwrites an existing Primary Owner
    (see Owner Account Management — owner/service.py, owner/models.py).
  - departments/designations/branches: minimal starter master data (Loan/Insurance
    departments per the brief) so Employee creation has something to reference before a
    future Settings (Master Data) module provides real management screens.
  - settings master data (Module 4): Lead Sources, Loan Products, Insurance Products,
    Document Types — only the literal examples named in the brief. Status Masters,
    Notification Templates, and API Settings are left empty (real business content /
    credentials, not to be invented here).
  - dashboard catalog (Module 5): 13 dashboard widgets + 4 nav items — code-backed
    catalogs, not Owner-editable business data, so seeding them here (not leaving them
    for the Owner to create) is correct rather than a shortcut.
  - leads nav item (Module 6A): adds its own `nav_items` row rather than editing Module
    5's `seed_dashboard_catalog` — the "future modules add their own nav item" pattern
    decision 038's freeze note anticipated.
  - "Property Documents" document type (Module 6B) — one more row in Module 4's own,
    still-open `document_types` collection (Owner-manageable via its existing CRUD API
    regardless), not a change to Module 4's code.
  - application form definitions (Module 6B): illustrative, non-authoritative field
    lists for the 5 already-seeded Loan/Insurance products so the dynamic form engine
    is demonstrably functional end-to-end — not asserting these are Ashapura's real
    required fields (decision, see docs/decisions/DECISIONS.md). No Owner-facing CRUD
    exists for these this round (out of 6B's explicit Owner-capability scope).
  - "Policy Document" document type (Module 6C) — one more row in Module 4's own,
    still-open `document_types` collection, needed at the Insurance pipeline's Policy
    Issuance stage.
  - loan_management/insurance_management permission catalog entries (Module 6C):
    `resource="applications"` on both, matching Dashboard's own pre-existing
    Disbursed/Rejected widget catalog rows by naming convention.
  - workflow definitions (Module 6C): the full Loan and (separate) Insurance status
    pipelines — the *data* half of the Workflow Engine (see docs/MODULE_6C_WORKFLOW_
    PROPOSAL.md); the engine code that walks them is generic and case-type-agnostic.
  - reminder rules (Module 6D): the starter Re-Eligibility (Loan/Insurance, 90-day) and
    Task Due (30-minute) rules named in the brief — timings are never hardcoded in the
    scheduler jobs (`app/worker/tasks/reminders.py`), only read from these rows.
  - reminders/notifications permission catalog entries + nav items (Module 6D):
    `resource="tasks"` matches Dashboard's own pre-existing Tasks widget catalog row.

Run from backend/: python ../scripts/seed.py
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config.database import get_database
from app.constants.roles import OWNER
from app.features.access_control.constants import PermissionAction
from app.features.access_control.models import Permission
from app.features.auth.models import ACCOUNT_STATUS_ACTIVE, User
from app.features.dashboard.constants import WidgetType
from seed_product_schemas import seed_real_product_schemas
from app.features.dashboard.models import DashboardWidget, NavItem
from app.features.employee.models import Branch, Department, Designation
from app.features.integrations.constants import IntegrationType
from app.features.integrations.models import IntegrationProvider
from app.features.lead_capture.constants import CaptureSourceKey
from app.features.lead_capture.models import CaptureSource
from app.features.owner.constants import OwnerType
from app.features.owner.indexes import ensure_owner_indexes
from app.features.owner.models import OwnerProfile
from app.features.reminders.constants import ReminderRuleType
from app.features.reminders.models import ReminderRule
from app.features.reporting.constants import ReportCategory, ReportType
from app.features.reporting.models import ReportDefinition, ReportDefinitionColumn
from app.features.system_settings.models import (
    DocumentType,
    InsuranceProduct,
    LeadSource,
    LoanProduct,
)
from app.features.workflow_engine.constants import (
    ON_HOLD_STATUS,
    CaseType,
    InsuranceAuditEvent,
    InsuranceStatus,
    LoanAuditEvent,
    LoanStatus,
    WorkflowAuditEvent,
)
from app.features.workflow_engine.models import WorkflowDefinition
from app.security.password import hash_password
from app.utils.id_generator import IdPrefix


async def seed_counters() -> None:
    db = get_database()
    counters = db["counters"]
    prefixes = [
        IdPrefix.EMPLOYEE,
        IdPrefix.CUSTOMER,
        IdPrefix.LEAD,
        IdPrefix.APPLICATION,
        IdPrefix.REFERRAL_PARTNER,
        IdPrefix.LOAN_CASE,
        IdPrefix.INSURANCE_CASE,
        IdPrefix.INTEGRATION,
    ]
    for prefix in prefixes:
        await counters.update_one({"_id": prefix}, {"$setOnInsert": {"seq": 0}}, upsert=True)
    print(f"counters: ensured {len(prefixes)} prefixes")


async def seed_permission_catalog() -> None:
    # Replaces an earlier placeholder that wrote {key, label, permissions} documents into
    # this same `roles`-adjacent space before Access Control (Module 3) existed to build
    # it properly — see docs/decisions/DECISIONS.md. Old placeholder shape simply doesn't
    # match this collection's queries (different field names), so it's inert, not migrated.
    db = get_database()
    permissions = db["permissions"]
    entries = [
        Permission(
            module="employee_management",
            resource="employee_records",
            actions=[PermissionAction.VIEW, PermissionAction.CREATE, PermissionAction.EDIT, PermissionAction.DELETE, PermissionAction.EXPORT],
            label="Employee Records",
        ),
    ]
    # Module 4 (Settings/Master Data) resources — full CRUD except company_settings,
    # a singleton with no create/delete concept.
    crud_actions = [PermissionAction.VIEW, PermissionAction.CREATE, PermissionAction.EDIT, PermissionAction.DELETE]
    for resource, label in (
        ("departments", "Departments"),
        ("designations", "Designations"),
        ("branches", "Branches"),
        ("lead_sources", "Lead Sources"),
        ("loan_products", "Loan Products"),
        ("insurance_products", "Insurance Products"),
        ("document_types", "Document Types"),
        ("status_masters", "Status Masters"),
        ("notification_templates", "Notification Templates"),
        ("api_settings", "API Settings"),
    ):
        entries.append(Permission(module="system_settings", resource=resource, actions=crud_actions, label=label))
    entries.append(
        Permission(module="system_settings", resource="company_settings", actions=[PermissionAction.VIEW, PermissionAction.EDIT], label="Company Settings")
    )
    # Product Schema Engine — the Owner-authorable master schema behind
    # ApplicationFormDefinition (Module 6B's own model, extended), shared read by every
    # portal's dynamic form; authoring itself lives with the other master-data resources.
    entries.append(
        Permission(
            module="system_settings", resource="product_schema",
            actions=[PermissionAction.VIEW, PermissionAction.CREATE, PermissionAction.EDIT], label="Product Schemas",
        )
    )
    # Module 5 (Dashboard Framework) — Recent Activities widget is real (backed by the
    # already-existing audit_logs collection), unlike the leads/loans/etc. widgets whose
    # owning modules don't exist yet, so this is the one new catalog entry this module
    # adds. Widgets referencing not-yet-built modules deliberately have no catalog entry
    # here — that module seeds its own when it's built (see docs/decisions/DECISIONS.md).
    entries.append(Permission(module="audit", resource="activity_logs", actions=[PermissionAction.VIEW], label="Recent Activities"))
    # Module 6A (Lead Foundation) — same module/resource name Dashboard's own
    # today_leads/pending_followups/assigned_leads widgets already reference (decision
    # 032), so those widgets become real and grantable to Employees the moment this
    # entry exists, with zero Dashboard code changes.
    # REJECT added by decision 125 (Leads workflow redesign, Phase 1) — additive to the
    # existing action list; no existing RolePermission.granted_actions value changes, an
    # Owner simply gains a new "Reject" checkbox to grant per role going forward.
    entries.append(
        Permission(
            module="leads", resource="leads",
            actions=[
                PermissionAction.VIEW, PermissionAction.CREATE, PermissionAction.EDIT, PermissionAction.ASSIGN,
                PermissionAction.EXPORT, PermissionAction.REJECT,
            ],
            label="Leads",
        )
    )
    # Module 6C (Loan & Insurance Pipeline) — `resource="applications"` deliberately
    # matches the exact name Dashboard's own "Disbursed"/"Rejected" widget catalog rows
    # already reference (decision 032/044's forward-compatibility pattern), so those
    # widgets become grantable to an Employee with zero Dashboard code changes.
    case_actions = [PermissionAction.VIEW, PermissionAction.EDIT, PermissionAction.APPROVE, PermissionAction.REJECT, PermissionAction.ASSIGN]
    entries.append(Permission(module="loan_management", resource="applications", actions=case_actions, label="Loan Cases"))
    entries.append(Permission(module="insurance_management", resource="applications", actions=case_actions, label="Insurance Cases"))
    # Module 6D (Reminder & Notification Engine) — `resource="tasks"` matches Dashboard's
    # own pre-existing "Tasks" widget catalog row (module="reminders", resource="tasks"),
    # same forward-compatibility pattern as loan/insurance_management above.
    entries.append(
        Permission(module="reminders", resource="tasks", actions=[PermissionAction.VIEW, PermissionAction.CREATE, PermissionAction.EDIT], label="Tasks")
    )
    entries.append(
        Permission(module="reminders", resource="reminder_rules", actions=[PermissionAction.VIEW, PermissionAction.CREATE, PermissionAction.EDIT], label="Reminder Rules")
    )
    # Module 8 (Reporting Framework) — running/exporting a report is delegable (unlike
    # Module 7, this brief doesn't restrict Reports & Analytics to Owner only).
    entries.append(Permission(module="reporting", resource="reports", actions=[PermissionAction.VIEW, PermissionAction.EXPORT], label="Reports"))
    entries.append(
        Permission(
            module="reporting", resource="scheduled_reports", actions=[PermissionAction.VIEW, PermissionAction.CREATE, PermissionAction.EDIT, PermissionAction.DELETE],
            label="Scheduled Reports",
        )
    )
    # Module 9A (API Management) — view/create/edit only, matching the brief's own
    # capability list (view, edit config, test connection, enable/disable — no delete).
    entries.append(
        Permission(module="integrations", resource="configs", actions=[PermissionAction.VIEW, PermissionAction.CREATE, PermissionAction.EDIT], label="Integration Configs")
    )
    # Module 9B (Lead Capture) — three narrow resources rather than one broad one,
    # since "who can trigger a manual import" and "who can remap sources/retry
    # failures" are different capabilities an Owner may want to delegate separately.
    entries.append(Permission(module="lead_capture", resource="captures", actions=[PermissionAction.CREATE], label="Manual Lead Capture"))
    entries.append(Permission(module="lead_capture", resource="sources", actions=[PermissionAction.VIEW, PermissionAction.EDIT], label="Capture Source Mapping"))
    entries.append(Permission(module="lead_capture", resource="failures", actions=[PermissionAction.VIEW, PermissionAction.EDIT], label="Capture Failures"))
    # Module 9C (Communication Engine) — three narrow resources, same "separate
    # capabilities an Owner may want to delegate independently" reasoning as 9B above:
    # authoring templates, viewing the queue (+ retrying), viewing delivery history.
    entries.append(
        Permission(module="communication", resource="templates", actions=[PermissionAction.VIEW, PermissionAction.CREATE, PermissionAction.EDIT], label="Communication Templates")
    )
    entries.append(Permission(module="communication", resource="queue", actions=[PermissionAction.VIEW, PermissionAction.EDIT], label="Communication Queue"))
    entries.append(Permission(module="communication", resource="history", actions=[PermissionAction.VIEW], label="Delivery History"))
    # Stage 3 (Geo Fencing/Temporary Permissions/MSG91 request) — "send" gates the
    # individual Send Message action + a record's own Messages panel; "bulk" gates Bulk
    # Messaging (create a job, view jobs/failed messages, edit = cancel/retry-failed).
    # Kept separate from "queue" since Queue is about managing the retry pipeline, not
    # composing new sends.
    entries.append(Permission(module="communication", resource="send", actions=[PermissionAction.VIEW, PermissionAction.CREATE], label="Send Message"))
    entries.append(
        Permission(module="communication", resource="bulk", actions=[PermissionAction.VIEW, PermissionAction.CREATE, PermissionAction.EDIT], label="Bulk Messaging")
    )
    # Geo Fencing — named work-area CRUD, delete included since the service itself
    # guards it (blocked while an active Geo Exception still references the fence).
    entries.append(
        Permission(
            module="geo_fencing", resource="fences",
            actions=[PermissionAction.VIEW, PermissionAction.CREATE, PermissionAction.EDIT, PermissionAction.DELETE],
            label="Geo Fencing",
        )
    )
    # Employee Permission Matrix redesign — Customers gains its first module-level
    # permission gate (previously any Owner/Employee could reach the Customer routes
    # with no fine-grained check at all; the existing assigned-application-derived
    # per-record scoping in customer/service.py is unchanged, this is an additional
    # outer gate). No staff-initiated "create a Customer" route exists yet — `create`
    # is scaffolded here for matrix completeness, currently a no-op grant.
    entries.append(
        Permission(
            module="customer", resource="customers",
            actions=[PermissionAction.VIEW, PermissionAction.CREATE, PermissionAction.EDIT],
            label="Customers",
        )
    )
    # Referral Partner Management's first-ever Employee access path — today Owner-only
    # (require_owner). `module`/`resource` here already matches the dashboard widget
    # catalog's referral_summary row, same forward-compatibility naming precedent as
    # loan_management/insurance_management above. No `PATCH /referral-partners/{id}`
    # route exists yet — `edit` is scaffolded for matrix completeness, currently a
    # no-op grant. Commission Rules/Ledger stay Owner-only, no permission entry here.
    entries.append(
        Permission(
            module="referral_partner_management", resource="partners",
            actions=[PermissionAction.VIEW, PermissionAction.CREATE, PermissionAction.EDIT],
            label="Referral Partners",
        )
    )

    for entry in entries:
        payload = entry.model_dump(by_alias=True, exclude={"id"})
        await permissions.update_one({"module": entry.module, "resource": entry.resource}, {"$setOnInsert": payload}, upsert=True)
    print(f"permission catalog: ensured {len(entries)} entries")


async def seed_bootstrap_owner() -> None:
    """Bootstraps the one and only Primary Owner from environment variables — never from
    a hardcoded credential in this file. Owner/Employee have no self-signup (see
    docs/decisions/DECISIONS.md #007), so without this there is no way to ever log in on
    a fresh environment. Idempotent and safe against a pre-existing Primary Owner: if one
    already exists (by owner_type, not merely by this mobile number), this is a no-op —
    it never overwrites or resets an existing Owner's password.
    """
    mobile = os.environ.get("BOOTSTRAP_OWNER_MOBILE")
    password = os.environ.get("BOOTSTRAP_OWNER_PASSWORD")
    full_name = os.environ.get("BOOTSTRAP_OWNER_NAME")
    email = os.environ.get("BOOTSTRAP_OWNER_EMAIL")
    if not mobile or not password or not full_name or not email:
        print(
            "bootstrap owner: skipped (set BOOTSTRAP_OWNER_MOBILE + BOOTSTRAP_OWNER_PASSWORD + "
            "BOOTSTRAP_OWNER_NAME + BOOTSTRAP_OWNER_EMAIL to enable)"
        )
        return

    db = get_database()
    # Ensures the owner_type backfill/indexes exist before checking for an existing
    # Primary Owner — this script can run standalone, before the app's own lifespan
    # startup has ever called ensure_owner_indexes.
    await ensure_owner_indexes(db)

    owner_profiles = db["owner_profiles"]
    users = db["users"]
    # Checked two ways: a real owner_profiles row (the normal case), and — since a
    # pre-fix version of this same script used to insert directly into `users` with no
    # matching profile — any owner-role `users` row at all. Either one means an Owner
    # already exists and this bootstrap must not create a second one, matching the "at
    # most one Owner ever" invariant this script has always upheld (see
    # docs/decisions/DECISIONS.md #007 and Owner Account Management's owner_type field).
    existing_primary = await owner_profiles.find_one({"owner_type": OwnerType.PRIMARY, "is_deleted": False})
    existing_owner_user = await users.find_one({"role": OWNER, "is_deleted": False})
    if existing_primary or existing_owner_user:
        print("bootstrap owner: an Owner account already exists, skipped")
        return

    owner = User(
        mobile=mobile, role=OWNER, status=ACCOUNT_STATUS_ACTIVE,
        password_hash=hash_password(password), is_mobile_verified=True,
    )
    result = await users.insert_one(owner.model_dump(by_alias=True, exclude={"id"}))
    user_id = str(result.inserted_id)

    profile = OwnerProfile(user_id=user_id, full_name=full_name, mobile=mobile, email=email, owner_type=OwnerType.PRIMARY)
    await owner_profiles.insert_one(profile.model_dump(by_alias=True, exclude={"id"}))

    print(f"bootstrap owner: created Primary Owner {mobile}")


async def seed_master_data() -> None:
    # Built via the real Pydantic models (not raw dicts) so every BaseDocument field
    # (status, is_deleted, version, ...) is present — repositories filter on is_deleted,
    # so a doc missing that field would be invisible to every find_many/find_by_id call.
    db = get_database()

    departments = db["departments"]
    for name in ("Loan", "Insurance"):
        payload = Department(name=name).model_dump(by_alias=True, exclude={"id"})
        await departments.update_one({"name": name}, {"$setOnInsert": payload}, upsert=True)

    designations = db["designations"]
    for name in ("Manager", "Executive", "Telecaller", "Branch Manager", "Sales Manager"):
        payload = Designation(name=name).model_dump(by_alias=True, exclude={"id"})
        await designations.update_one({"name": name}, {"$setOnInsert": payload}, upsert=True)

    branches = db["branches"]
    branch_payload = Branch(name="Head Office", code="HO").model_dump(by_alias=True, exclude={"id"})
    await branches.update_one({"code": "HO"}, {"$setOnInsert": branch_payload}, upsert=True)

    print("master data: ensured departments/designations/default branch")


async def seed_settings_master_data() -> None:
    # Only seeds values the user explicitly named as examples in the Module 4 brief
    # (Lead Sources, Loan Products, Insurance Products, Document Types). Status Masters,
    # Notification Templates, and API Settings are deliberately left empty — their real
    # content is business configuration (status pipelines, template copy, provider
    # credentials) the Owner must define, not something to invent here. See
    # docs/decisions/DECISIONS.md.
    db = get_database()

    lead_sources = db["lead_sources"]
    for name in ("Website", "Meta", "Manual", "Referral", "Walk-in"):
        payload = LeadSource(name=name).model_dump(by_alias=True, exclude={"id"})
        await lead_sources.update_one({"name": name}, {"$setOnInsert": payload}, upsert=True)

    loan_products = db["loan_products"]
    for name in ("Personal Loan", "Business Loan", "Property Loan"):
        payload = LoanProduct(name=name).model_dump(by_alias=True, exclude={"id"})
        await loan_products.update_one({"name": name}, {"$setOnInsert": payload}, upsert=True)

    insurance_products = db["insurance_products"]
    for name in ("Life", "Health"):
        payload = InsuranceProduct(name=name).model_dump(by_alias=True, exclude={"id"})
        await insurance_products.update_one({"name": name}, {"$setOnInsert": payload}, upsert=True)

    document_types = db["document_types"]
    # "Property Documents" added in Module 6B — the brief's Document Upload section
    # named it as a supported type alongside the four seeded in Module 4; using Module
    # 4's own still-open create path (not a schema/code change) to add it.
    # "Policy Document" added in Module 6C — same still-open create path, needed at the
    # Insurance pipeline's Policy Issuance stage.
    for name in ("PAN", "Aadhaar", "Bank Statement", "Salary Slip", "Property Documents", "Policy Document"):
        payload = DocumentType(name=name).model_dump(by_alias=True, exclude={"id"})
        await document_types.update_one({"name": name}, {"$setOnInsert": payload}, upsert=True)

    print("settings master data: ensured lead sources/loan products/insurance products/document types")


async def seed_dashboard_catalog() -> None:
    # Widget/NavItem catalogs are seeded once, not Owner-CRUD-able (each entry needs real
    # backend code — a data provider or an actual route — to mean anything; see
    # docs/decisions/DECISIONS.md). `required_module`/`required_resource` reference
    # permission-catalog entries by naming convention: some exist already
    # (employee_management, audit — seeded above), the rest (leads, loan_management, ...)
    # don't exist yet since those modules aren't built — harmless: Owner bypasses
    # permission checks entirely, and an Employee simply can't be granted a widget whose
    # module doesn't exist yet, which is the correct behavior, not a bug.
    db = get_database()
    widgets = db["dashboard_widgets"]

    widget_defs = [
        ("today_leads", "Today's Leads", "leads", WidgetType.METRIC, "leads", "leads"),
        ("pending_followups", "Pending Follow-ups", "leads", WidgetType.METRIC, "leads", "leads"),
        ("pending_documents", "Pending Documents", "documents", WidgetType.METRIC, "document_management", "documents"),
        ("assigned_leads", "Assigned Leads", "leads", WidgetType.METRIC, "leads", "leads"),
        ("disbursed", "Disbursed", "loans", WidgetType.METRIC, "loan_management", "applications"),
        ("rejected", "Rejected", "loans", WidgetType.METRIC, "loan_management", "applications"),
        ("revenue", "Revenue", "revenue", WidgetType.METRIC, "reporting", "revenue"),
        ("tasks", "Tasks", "tasks", WidgetType.LIST, "reminders", "tasks"),
        ("notifications", "Notifications", "notifications", WidgetType.LIST, "notification_management", "notifications"),
        ("recent_activities", "Recent Activities", "activity", WidgetType.LIST, "audit", "activity_logs"),
        ("department_summary", "Department Summary", "team", WidgetType.LIST, "employee_management", "employee_records"),
        ("employee_summary", "Employee Summary", "team", WidgetType.METRIC, "employee_management", "employee_records"),
        ("referral_summary", "Referral Summary", "referrals", WidgetType.METRIC, "referral_partner_management", "referral_partners"),
    ]
    for order, (key, label, category, widget_type, module, resource) in enumerate(widget_defs):
        widget = DashboardWidget(
            key=key, label=label, category=category, widget_type=widget_type,
            required_module=module, required_resource=resource, required_action=PermissionAction.VIEW,
            default_order=order,
        )
        payload = widget.model_dump(by_alias=True, exclude={"id"})
        await widgets.update_one({"key": key}, {"$setOnInsert": payload}, upsert=True)
    print(f"dashboard widgets: ensured {len(widget_defs)} catalog entries")

    # Phase 4 (Employee Dashboard & Dynamic Navigation) — 25 more widgets, gated on the
    # exact same real Permission-catalog module/resource pairs as everything else here.
    # `module=None` (Customers/Applications summaries) means "inherent, any Owner/
    # Employee" per decision 050 — Module 6B has no delegable permission of its own.
    # Referral/Revenue widgets point at module/resource pairs with no seeded Permission
    # row (matching `referral_summary`/`revenue`'s own precedent above), so they stay
    # Owner-only in practice without a hardcoded owner check.
    phase4_widget_defs: list[tuple[str, str, str, str, str | None, str | None]] = [
        ("total_leads", "Total Leads", "leads", WidgetType.METRIC, "leads", "leads"),
        ("lead_conversion_rate", "Lead Conversion", "leads", WidgetType.METRIC, "leads", "leads"),
        ("lead_source_chart", "Leads by Source", "leads", WidgetType.LIST, "leads", "leads"),
        ("customers_summary", "Customers", "customers", WidgetType.METRIC, None, None),
        ("applications_summary", "Applications", "customers", WidgetType.METRIC, None, None),
        ("applications_submitted", "Applications Submitted", "performance", WidgetType.METRIC, None, None),
        ("loan_cases_total", "Loan Cases", "loans", WidgetType.METRIC, "loan_management", "applications"),
        ("loan_pipeline_chart", "Loan Pipeline", "loans", WidgetType.LIST, "loan_management", "applications"),
        ("loan_re_eligible", "Loan Re-Eligible", "loans", WidgetType.METRIC, "loan_management", "applications"),
        ("insurance_cases_total", "Insurance Cases", "insurance", WidgetType.METRIC, "insurance_management", "applications"),
        ("policies_issued", "Policies Issued", "insurance", WidgetType.METRIC, "insurance_management", "applications"),
        ("insurance_rejected", "Insurance Rejected", "insurance", WidgetType.METRIC, "insurance_management", "applications"),
        ("insurance_re_eligible", "Insurance Re-Eligible", "insurance", WidgetType.METRIC, "insurance_management", "applications"),
        ("insurance_pipeline_chart", "Insurance Pipeline", "insurance", WidgetType.LIST, "insurance_management", "applications"),
        ("tasks_completed", "Tasks Completed", "tasks", WidgetType.METRIC, "reminders", "tasks"),
        ("today_performance", "Today's Performance", "performance", WidgetType.METRIC, "leads", "leads"),
        ("monthly_performance", "Monthly Performance", "performance", WidgetType.METRIC, "leads", "leads"),
        ("employee_performance_chart", "Employee Performance", "team", WidgetType.LIST, "employee_management", "employee_records"),
        ("referral_pending_commission", "Pending Commission", "referrals", WidgetType.METRIC, "referral_partner_management", "referral_partners"),
        ("referral_paid_commission", "Paid Commission", "referrals", WidgetType.METRIC, "referral_partner_management", "referral_partners"),
        ("referral_performance_chart", "Referral Performance", "referrals", WidgetType.LIST, "referral_partner_management", "referral_partners"),
        ("loan_revenue", "Loan Revenue", "revenue", WidgetType.METRIC, "reporting", "revenue"),
        ("insurance_revenue", "Insurance Revenue", "revenue", WidgetType.METRIC, "reporting", "revenue"),
        ("monthly_revenue", "Monthly Revenue", "revenue", WidgetType.METRIC, "reporting", "revenue"),
        ("revenue_trend_chart", "Revenue Trend", "revenue", WidgetType.LIST, "reporting", "revenue"),
    ]
    for order, (key, label, category, widget_type, module, resource) in enumerate(phase4_widget_defs, start=len(widget_defs)):
        widget = DashboardWidget(
            key=key, label=label, category=category, widget_type=widget_type,
            required_module=module, required_resource=resource, required_action=PermissionAction.VIEW if module else None,
            default_order=order,
        )
        payload = widget.model_dump(by_alias=True, exclude={"id"})
        await widgets.update_one({"key": key}, {"$setOnInsert": payload}, upsert=True)
    print(f"dashboard widgets: ensured {len(phase4_widget_defs)} Phase 4 catalog entries")

    nav_items = db["nav_items"]
    nav_defs = [
        NavItem(key="dashboard", label="Dashboard", route="/", order=0),
        # Owner Account Management — owner_only mirrors how the route is actually
        # protected (RequireOwner-equivalent at the nav-catalog level; the real,
        # Primary-Owner-only restriction is enforced server-side per request by
        # require_primary_owner, not by this catalog entry — see decision 033's "gate
        # must mirror how the target route is protected" note on NavItem.owner_only).
        NavItem(key="owner_accounts", label="Owner Management", route="/owner-accounts", order=5, owner_only=True),
        NavItem(key="employees", label="Employees", route="/employees", order=10, owner_only=True),
        NavItem(key="roles", label="Roles & Permissions", route="/roles", order=20, owner_only=True),
        NavItem(
            key="settings", label="Settings", route="/settings", order=30,
            required_module="system_settings", required_resource="company_settings", required_action=PermissionAction.VIEW,
        ),
    ]
    for nav_item in nav_defs:
        payload = nav_item.model_dump(by_alias=True, exclude={"id"})
        await nav_items.update_one({"key": nav_item.key}, {"$setOnInsert": payload}, upsert=True)
    print(f"nav items: ensured {len(nav_defs)} catalog entries")


async def seed_leads_nav_item() -> None:
    db = get_database()
    nav_item = NavItem(
        key="leads", label="Leads", route="/leads", order=15,
        required_module="leads", required_resource="leads", required_action=PermissionAction.VIEW,
    )
    payload = nav_item.model_dump(by_alias=True, exclude={"id"})
    await db["nav_items"].update_one({"key": nav_item.key}, {"$setOnInsert": payload}, upsert=True)
    print("nav items: ensured leads")


async def seed_workflow_nav_items() -> None:
    # Module 6C — same "future modules add their own nav item" pattern as Module 6A's
    # seed_leads_nav_item, not an edit to Module 5's own seed_dashboard_catalog.
    db = get_database()
    nav_defs = [
        NavItem(key="loan_cases", label="Loan Cases", route="/loan-cases", order=25, required_module="loan_management", required_resource="applications", required_action=PermissionAction.VIEW),
        NavItem(
            key="insurance_cases", label="Insurance Cases", route="/insurance-cases", order=26,
            required_module="insurance_management", required_resource="applications", required_action=PermissionAction.VIEW,
        ),
    ]
    for nav_item in nav_defs:
        payload = nav_item.model_dump(by_alias=True, exclude={"id"})
        await db["nav_items"].update_one({"key": nav_item.key}, {"$setOnInsert": payload}, upsert=True)
    print(f"nav items: ensured {len(nav_defs)} Module 6C entries")


# NOTE: the illustrative, non-authoritative `seed_customer_form_definitions()` demo
# (5 fake field sets for Personal/Business/Property Loan + generic "Life"/"Health") was
# removed here in Phase 2 — it upserted schemas for the same 3 real loan product names
# real seed data now uses, which would have permanently blocked the real spec-accurate
# schemas via the idempotent $setOnInsert (first-write-wins). Superseded by
# `scripts/seed_product_schemas.py::seed_real_product_schemas()`, called from `main()`
# below — see that module for the full, spec-sourced product catalog.


async def seed_workflow_definitions() -> None:
    # Module 6C's workflow *data* — the engine (workflow_engine/engine.py) is generic
    # code that walks these rows for any case type; this is the one place the Loan and
    # (separate, finalized per decision 064) Insurance lifecycles are actually defined.
    # See docs/MODULE_6C_WORKFLOW_PROPOSAL.md and docs/decisions/DECISIONS.md. No
    # rollback in v1 — `allowed_previous_statuses` stays empty on every row. "On Hold" is
    # an Optional Status, not a hardcoded branch: every non-terminal row below gets
    # `ON_HOLD_STATUS` appended to its own `allowed_next_statuses`, and each case type's
    # own `on_hold` row lists every status it can `resume` back into.
    db = get_database()
    definitions = db["workflow_definitions"]

    loan_rows = [
        (LoanStatus.NEW_CUSTOMER, "New Customer", 1, [LoanStatus.DOCUMENTS_PENDING], False, False, LoanAuditEvent.CASE_CREATED, "loan_case.created"),
        (LoanStatus.DOCUMENTS_PENDING, "Documents Pending", 2, [LoanStatus.CREDIT_EVALUATION], True, True, LoanAuditEvent.DOCUMENTS_REQUESTED, "loan_case.documents_requested"),
        (LoanStatus.CREDIT_EVALUATION, "Credit Evaluation", 3, [LoanStatus.OFFER_ACCEPTANCE, LoanStatus.REJECTED], False, True, LoanAuditEvent.DOCUMENTS_VERIFIED, "loan_case.documents_verified"),
        (LoanStatus.OFFER_ACCEPTANCE, "Offer Acceptance", 4, [LoanStatus.ADDITIONAL_DOCUMENTS, LoanStatus.REJECTED], True, True, LoanAuditEvent.CREDIT_EVALUATED, "loan_case.offer_ready"),
        (LoanStatus.ADDITIONAL_DOCUMENTS, "Upload Additional Documents", 5, [LoanStatus.ESIGN_NACH_KYC], True, True, LoanAuditEvent.OFFER_ACCEPTED, "loan_case.offer_accepted"),
        (LoanStatus.ESIGN_NACH_KYC, "eSign / NACH / KYC", 6, [LoanStatus.FINAL_EVALUATION], False, True, LoanAuditEvent.ADDITIONAL_DOCS_VERIFIED, "loan_case.additional_docs_verified"),
        (LoanStatus.FINAL_EVALUATION, "Final Evaluation", 7, [LoanStatus.SEND_FOR_DISBURSEMENT, LoanStatus.REJECTED], False, True, LoanAuditEvent.ESIGN_NACH_KYC_COMPLETED, "loan_case.esign_nach_kyc_completed"),
        (LoanStatus.SEND_FOR_DISBURSEMENT, "Send For Disbursement", 8, [LoanStatus.DISBURSED], False, True, LoanAuditEvent.FINAL_EVALUATED, "loan_case.approved"),
        (LoanStatus.DISBURSED, "Disbursed", 9, [], False, False, LoanAuditEvent.DISBURSED, "loan_case.disbursed"),
        (LoanStatus.REJECTED, "Application Rejected", 10, [], False, False, LoanAuditEvent.REJECTED, "loan_case.rejected"),
    ]
    insurance_rows = [
        (InsuranceStatus.APPLICATION_SUBMITTED, "Application Submitted", 1, [InsuranceStatus.DOCUMENTS_PENDING], False, False, InsuranceAuditEvent.CASE_CREATED, "insurance_case.created"),
        (InsuranceStatus.DOCUMENTS_PENDING, "Documents Pending", 2, [InsuranceStatus.UNDERWRITING], True, True, InsuranceAuditEvent.DOCUMENTS_REQUESTED, "insurance_case.documents_requested"),
        (
            InsuranceStatus.UNDERWRITING, "Underwriting", 3,
            [InsuranceStatus.MEDICAL_VERIFICATION, InsuranceStatus.ADDITIONAL_DOCUMENTS, InsuranceStatus.PREMIUM_ACCEPTANCE, InsuranceStatus.REJECTED],
            False, True, InsuranceAuditEvent.DOCUMENTS_VERIFIED, "insurance_case.documents_verified",
        ),
        (
            InsuranceStatus.MEDICAL_VERIFICATION, "Medical Verification", 4,
            [InsuranceStatus.ADDITIONAL_DOCUMENTS, InsuranceStatus.PREMIUM_ACCEPTANCE, InsuranceStatus.REJECTED],
            False, True, InsuranceAuditEvent.MEDICAL_VERIFICATION_REQUIRED, "insurance_case.medical_verification_required",
        ),
        (
            InsuranceStatus.ADDITIONAL_DOCUMENTS, "Additional Documents", 5, [InsuranceStatus.PREMIUM_ACCEPTANCE],
            True, True, InsuranceAuditEvent.ADDITIONAL_DOCUMENTS_REQUIRED, "insurance_case.additional_documents_required",
        ),
        (
            InsuranceStatus.PREMIUM_ACCEPTANCE, "Premium Acceptance", 6,
            [InsuranceStatus.POLICY_GENERATION, InsuranceStatus.REJECTED],
            True, True, InsuranceAuditEvent.PREMIUM_READY, "insurance_case.premium_ready",
        ),
        (InsuranceStatus.POLICY_GENERATION, "Policy Generation", 7, [InsuranceStatus.POLICY_ISSUED], False, True, InsuranceAuditEvent.PREMIUM_ACCEPTED, "insurance_case.premium_accepted"),
        (InsuranceStatus.POLICY_ISSUED, "Policy Issued", 8, [], False, False, InsuranceAuditEvent.POLICY_ISSUED, "insurance_case.policy_issued"),
        (InsuranceStatus.REJECTED, "Application Rejected", 9, [], False, False, InsuranceAuditEvent.REJECTED, "insurance_case.rejected"),
    ]

    ensured = 0
    for case_type, rows, resumable in ((CaseType.LOAN, loan_rows, LoanStatus.RESUMABLE), (CaseType.INSURANCE, insurance_rows, InsuranceStatus.RESUMABLE)):
        module = "loan_management" if case_type == CaseType.LOAN else "insurance_management"
        for status, label, sequence, allowed_next, customer_editable, employee_editable, audit_event, notification_key in rows:
            # Every non-terminal status can also be placed On Hold (Optional Status,
            # decision 064) — appended here rather than duplicated in every row above.
            full_allowed_next = [*allowed_next, ON_HOLD_STATUS] if status in resumable else allowed_next
            definition = WorkflowDefinition(
                case_type=case_type, status=status, label=label, sequence=sequence, allowed_next_statuses=full_allowed_next,
                required_permission=f"{module}:applications:edit",
                customer_editable=customer_editable, employee_editable=employee_editable, audit_event=audit_event,
                notification_trigger_key=notification_key, reminder_trigger_key=None,
            )
            payload = definition.model_dump(by_alias=True, exclude={"id"})
            await definitions.update_one({"case_type": case_type, "status": status}, {"$setOnInsert": payload}, upsert=True)
            ensured += 1

        # The shared "On Hold" status itself — resumable back into anything it could
        # have been entered from.
        on_hold_definition = WorkflowDefinition(
            case_type=case_type, status=ON_HOLD_STATUS, label="On Hold", sequence=len(rows) + 1,
            allowed_next_statuses=list(resumable), required_permission=f"{module}:applications:edit",
            customer_editable=False, employee_editable=True, audit_event=WorkflowAuditEvent.CASE_ON_HOLD, notification_trigger_key=None,
        )
        payload = on_hold_definition.model_dump(by_alias=True, exclude={"id"})
        await definitions.update_one({"case_type": case_type, "status": ON_HOLD_STATUS}, {"$setOnInsert": payload}, upsert=True)
        ensured += 1
    print(f"workflow definitions: ensured {ensured} entries")


async def seed_reminder_rules() -> None:
    # Module 6D — "Don't hardcode reminder timings. Instead, create Reminder Rules in
    # the database." These three are the starter rules named in the brief itself
    # (90-day loan/insurance re-eligibility, 30-minute task-due reminder); an Owner can
    # add more or edit these via the Reminder Rules API without any code change.
    db = get_database()
    rules = db["reminder_rules"]
    # notify_before_days/notify_before_minutes are lists — a rule can define multiple
    # trigger points (e.g. 30/15/7/1 days before eligibility); only one is seeded today,
    # but adding more later is a data edit (PATCH /reminder-rules/{id}), not a code change.
    rule_defs = [
        {"rule_type": ReminderRuleType.RE_ELIGIBILITY, "label": "Rejected Loan Re-Eligibility", "case_type": "loan", "eligible_after_days": 90, "notify_before_days": [10]},
        {
            "rule_type": ReminderRuleType.RE_ELIGIBILITY, "label": "Rejected Insurance Re-Eligibility", "case_type": "insurance",
            "eligible_after_days": 90, "notify_before_days": [10],
        },
        {
            "rule_type": ReminderRuleType.TASK_DUE, "label": "Task Due Reminder", "notify_before_minutes": [30],
            "escalation_repeat_minutes": 60, "escalation_max_repeats": 2,
        },
    ]
    ensured = 0
    for rule_def in rule_defs:
        rule = ReminderRule(**rule_def)
        payload = rule.model_dump(by_alias=True, exclude={"id"})
        await rules.update_one({"label": rule.label}, {"$setOnInsert": payload}, upsert=True)
        ensured += 1
    print(f"reminder rules: ensured {ensured} entries")


async def seed_reminders_nav_items() -> None:
    # Module 6D — same "future modules add their own nav item" pattern as every prior
    # module's own seed_*_nav_item function, not an edit to Module 5's seed code.
    db = get_database()
    nav_defs = [
        NavItem(key="tasks", label="Tasks", route="/tasks", order=27, required_module="reminders", required_resource="tasks", required_action=PermissionAction.VIEW),
        NavItem(key="notifications", label="Notifications", route="/notifications", order=28),
    ]
    for nav_item in nav_defs:
        payload = nav_item.model_dump(by_alias=True, exclude={"id"})
        await db["nav_items"].update_one({"key": nav_item.key}, {"$setOnInsert": payload}, upsert=True)
    print(f"nav items: ensured {len(nav_defs)} Module 6D entries")


async def seed_referral_partner_management_nav_items() -> None:
    # Module 7 — same "future modules add their own nav item" pattern. Commission Rules
    # and Commission Ledger stay Owner-only (require_owner server-side — no Employee
    # role for those, see referral_partner_management/dependencies.py's own docstring),
    # so `owner_only=True` remains the correct gate for those two. Referral Partners
    # itself was retrofitted (Employee Permission Matrix redesign) with a real
    # require_permission("referral_partner_management", "partners", "view") gate on
    # list/detail alongside the existing require_owner routes (approve/deactivate stay
    # Owner-only) — its nav item must mirror that with required_module/resource/action,
    # not owner_only, or a permission-holding Employee would pass the backend check but
    # never see the link at all.
    db = get_database()
    nav_defs = [
        NavItem(
            key="referral_partners", label="Referral Partners", route="/referral-partners", order=29,
            required_module="referral_partner_management", required_resource="partners", required_action=PermissionAction.VIEW,
        ),
        NavItem(key="commission_rules", label="Commission Rules", route="/commission-rules", order=30, owner_only=True),
        NavItem(key="commission_ledger", label="Commission Ledger", route="/commission-ledger", order=31, owner_only=True),
    ]
    for nav_item in nav_defs:
        payload = nav_item.model_dump(by_alias=True, exclude={"id"})
        await db["nav_items"].update_one({"key": nav_item.key}, {"$setOnInsert": payload}, upsert=True)
    print(f"nav items: ensured {len(nav_defs)} Module 7 entries")


async def seed_reporting_nav_items() -> None:
    # Module 8 — same "future modules add their own nav item" pattern.
    db = get_database()
    nav_defs = [
        NavItem(key="reports", label="Reports", route="/reports", order=32, required_module="reporting", required_resource="reports", required_action=PermissionAction.VIEW),
        NavItem(
            key="scheduled_reports", label="Scheduled Reports", route="/scheduled-reports", order=33, required_module="reporting", required_resource="scheduled_reports",
            required_action=PermissionAction.VIEW,
        ),
    ]
    for nav_item in nav_defs:
        payload = nav_item.model_dump(by_alias=True, exclude={"id"})
        await db["nav_items"].update_one({"key": nav_item.key}, {"$setOnInsert": payload}, upsert=True)
    print(f"nav items: ensured {len(nav_defs)} Module 8 entries")


async def seed_report_definitions() -> None:
    # Module 8, decision 090 — "New Report -> New Configuration -> No Code." 11 of these
    # 17 rows (report_type in count/sum/list) are pure parameters for a generic executor
    # in app/features/reporting/reports.py; the other 6 (report_type="custom") still need
    # a matching function there (a join, a reused service call, a multi-branch
    # conditional sum) — this row still supplies their real label/category/columns/
    # description, so the catalog never needs a code change for those either.
    db = get_database()
    rows = [
        ReportDefinition(
            key="lead_by_source", label="Leads by Source", category=ReportCategory.LEAD, description="Lead count grouped by Lead Source.",
            report_type=ReportType.COUNT, columns=[ReportDefinitionColumn(key="source", label="Source"), ReportDefinitionColumn(key="count", label="Leads")],
            collection="leads", group_field="source_id", date_field="created_at", name_resolution_collection="lead_sources", name_resolution_field="name",
        ),
        ReportDefinition(
            key="lead_conversion", label="Lead Conversion", category=ReportCategory.LEAD, description="Leads that became an Application, by Source.",
            report_type=ReportType.CUSTOM,
            columns=[
                ReportDefinitionColumn(key="source", label="Source"), ReportDefinitionColumn(key="total_leads", label="Total Leads"),
                ReportDefinitionColumn(key="converted", label="Converted"), ReportDefinitionColumn(key="conversion_rate_pct", label="Conversion %"),
            ],
        ),
        ReportDefinition(
            key="lead_by_employee", label="Leads by Employee", category=ReportCategory.LEAD, description="Lead count grouped by assigned Employee.",
            report_type=ReportType.COUNT, columns=[ReportDefinitionColumn(key="employee", label="Employee"), ReportDefinitionColumn(key="count", label="Leads")],
            collection="leads", group_field="assigned_to", date_field="created_at", name_resolution_collection="employees", name_resolution_field="display_name",
        ),
        ReportDefinition(
            key="lead_by_product", label="Leads by Product", category=ReportCategory.LEAD, description="Lead count grouped by Product.",
            report_type=ReportType.CUSTOM,
            columns=[
                ReportDefinitionColumn(key="product_category", label="Category"), ReportDefinitionColumn(key="product", label="Product"),
                ReportDefinitionColumn(key="count", label="Leads"),
            ],
        ),
        ReportDefinition(
            key="loan_applications", label="Loan Applications", category=ReportCategory.LOAN, description="Loan case count grouped by status.",
            report_type=ReportType.COUNT, columns=[ReportDefinitionColumn(key="status", label="Status"), ReportDefinitionColumn(key="count", label="Applications")],
            collection="application_workflows", group_field="current_status", date_field="created_at", extra_match={"case_type": "loan"},
        ),
        ReportDefinition(
            key="loan_approved", label="Loan Approved", category=ReportCategory.LOAN, description="Loan cases whose offer was accepted.",
            report_type=ReportType.LIST,
            columns=[
                ReportDefinitionColumn(key="case_code", label="Case"), ReportDefinitionColumn(key="status", label="Status"),
                ReportDefinitionColumn(key="amount", label="Offered Amount"), ReportDefinitionColumn(key="date", label="Date"),
            ],
            collection="application_workflows", date_field="created_at", amount_field="offered_amount",
            extra_match={"case_type": "loan", "loan_details.offer_decision": "accepted"},
        ),
        ReportDefinition(
            key="loan_rejected", label="Loan Rejected", category=ReportCategory.LOAN, description="Rejected Loan cases.", report_type=ReportType.LIST,
            columns=[ReportDefinitionColumn(key="case_code", label="Case"), ReportDefinitionColumn(key="status", label="Status"), ReportDefinitionColumn(key="date", label="Date")],
            collection="application_workflows", date_field="updated_at", extra_match={"case_type": "loan", "current_status": LoanStatus.REJECTED},
        ),
        ReportDefinition(
            key="loan_disbursed", label="Loan Disbursed", category=ReportCategory.LOAN, description="Disbursed Loan cases and amounts.", report_type=ReportType.LIST,
            columns=[
                ReportDefinitionColumn(key="case_code", label="Case"), ReportDefinitionColumn(key="status", label="Status"),
                ReportDefinitionColumn(key="amount", label="Disbursed Amount"), ReportDefinitionColumn(key="date", label="Disbursed At"),
            ],
            collection="application_workflows", date_field="loan_details.disbursed_at", amount_field="disbursed_amount",
            extra_match={"case_type": "loan", "current_status": LoanStatus.DISBURSED},
        ),
        ReportDefinition(
            key="bank_performance", label="Bank Performance", category=ReportCategory.LOAN, description="Disbursed count/amount grouped by Bank/NBFC.",
            report_type=ReportType.SUM,
            columns=[
                ReportDefinitionColumn(key="bank", label="Bank / NBFC"), ReportDefinitionColumn(key="disbursed_count", label="Disbursed Count"),
                ReportDefinitionColumn(key="disbursed_amount", label="Disbursed Amount"),
            ],
            collection="application_workflows", group_field="loan_details.bank_nbfc_name", sum_field="loan_details.disbursed_amount",
            date_field="loan_details.disbursed_at", extra_match={"case_type": "loan", "current_status": LoanStatus.DISBURSED},
        ),
        ReportDefinition(
            key="insurance_applications", label="Insurance Applications", category=ReportCategory.INSURANCE, description="Insurance case count grouped by status.",
            report_type=ReportType.COUNT, columns=[ReportDefinitionColumn(key="status", label="Status"), ReportDefinitionColumn(key="count", label="Applications")],
            collection="application_workflows", group_field="current_status", date_field="created_at", extra_match={"case_type": "insurance"},
        ),
        ReportDefinition(
            key="insurance_policies_issued", label="Policies Issued", category=ReportCategory.INSURANCE, description="Issued Insurance policies and premium amounts.",
            report_type=ReportType.LIST,
            columns=[
                ReportDefinitionColumn(key="case_code", label="Case"), ReportDefinitionColumn(key="status", label="Status"),
                ReportDefinitionColumn(key="amount", label="Premium Amount"), ReportDefinitionColumn(key="date", label="Policy Issued At"),
            ],
            collection="application_workflows", date_field="insurance_details.policy_issued_at", amount_field="premium_amount",
            extra_match={"case_type": "insurance", "current_status": InsuranceStatus.POLICY_ISSUED},
        ),
        ReportDefinition(
            key="insurance_rejections", label="Insurance Rejections", category=ReportCategory.INSURANCE, description="Rejected Insurance cases.", report_type=ReportType.LIST,
            columns=[ReportDefinitionColumn(key="case_code", label="Case"), ReportDefinitionColumn(key="status", label="Status"), ReportDefinitionColumn(key="date", label="Date")],
            collection="application_workflows", date_field="updated_at", extra_match={"case_type": "insurance", "current_status": InsuranceStatus.REJECTED},
        ),
        ReportDefinition(
            key="employee_task_summary", label="Employee Task Summary", category=ReportCategory.EMPLOYEE, description="Assigned/Completed/Pending tasks per Employee.",
            report_type=ReportType.CUSTOM,
            columns=[
                ReportDefinitionColumn(key="employee", label="Employee"), ReportDefinitionColumn(key="assigned", label="Assigned"),
                ReportDefinitionColumn(key="completed", label="Completed"), ReportDefinitionColumn(key="pending", label="Pending"),
            ],
        ),
        ReportDefinition(
            key="referral_leads", label="Referral Leads", category=ReportCategory.REFERRAL, description="Leads submitted by Referral Partners.",
            report_type=ReportType.CUSTOM,
            columns=[
                ReportDefinitionColumn(key="partner", label="Referral Partner"), ReportDefinitionColumn(key="lead_code", label="Lead"),
                ReportDefinitionColumn(key="full_name", label="Name"), ReportDefinitionColumn(key="external_status", label="Status"),
                ReportDefinitionColumn(key="submitted_at", label="Submitted At"),
            ],
        ),
        ReportDefinition(
            key="referral_conversions", label="Referral Conversions", category=ReportCategory.REFERRAL, description="Referral lead conversion rate, by Partner.",
            report_type=ReportType.CUSTOM,
            columns=[
                ReportDefinitionColumn(key="partner", label="Referral Partner"), ReportDefinitionColumn(key="total_leads", label="Total Leads"),
                ReportDefinitionColumn(key="approved", label="Approved"), ReportDefinitionColumn(key="conversion_rate_pct", label="Conversion %"),
            ],
        ),
        ReportDefinition(
            key="referral_commission", label="Referral Commission", category=ReportCategory.REFERRAL, description="Pending/Approved/Paid commission per Partner.",
            report_type=ReportType.CUSTOM,
            columns=[
                ReportDefinitionColumn(key="partner", label="Referral Partner"), ReportDefinitionColumn(key="commission_pending", label="Pending"),
                ReportDefinitionColumn(key="commission_approved", label="Approved"), ReportDefinitionColumn(key="commission_paid", label="Paid"),
                ReportDefinitionColumn(key="commission_balance", label="Balance"),
            ],
        ),
        ReportDefinition(
            key="dashboard_analytics", label="Dashboard Analytics", category=ReportCategory.DASHBOARD,
            description="Company-wide headline metrics, matching Dashboard's own widget definitions.", report_type=ReportType.CUSTOM,
            columns=[ReportDefinitionColumn(key="metric", label="Metric"), ReportDefinitionColumn(key="value", label="Value")],
        ),
    ]
    for row in rows:
        payload = row.model_dump(by_alias=True, exclude={"id"})
        await db["report_definitions"].update_one({"key": row.key}, {"$setOnInsert": payload}, upsert=True)
    print(f"report definitions: ensured {len(rows)} entries")


async def seed_integration_providers() -> None:
    # Module 9A, decision — "Integration Type -> Provider -> Configuration -> Status,
    # not hardcoded." Adding a future provider for an existing type (e.g. a second
    # WhatsApp provider) is a new seeded row here, never a change to
    # app/features/integrations' CRUD/service code.
    db = get_database()
    rows = [
        IntegrationProvider(integration_type=IntegrationType.META, provider="meta", label="Meta (Facebook/Instagram)"),
        IntegrationProvider(integration_type=IntegrationType.WHATSAPP, provider="whatsapp_business_api", label="WhatsApp Business API"),
        IntegrationProvider(integration_type=IntegrationType.SMS, provider="generic_sms", label="Generic SMS Provider"),
        IntegrationProvider(integration_type=IntegrationType.EMAIL, provider="smtp", label="SMTP"),
        IntegrationProvider(integration_type=IntegrationType.EMAIL, provider="email_api", label="Email API Provider"),
        IntegrationProvider(integration_type=IntegrationType.MAPS, provider="google_maps", label="Google Maps"),
        # Stage 2 (Geo Fencing / Temporary Permissions / MSG91 request) — MSG91 as a real,
        # named provider for all 3 required channels. Email deliberately reuses the
        # existing "smtp" provider mechanics (MSG91 issues standard SMTP relay
        # credentials — no MSG91-specific email code was written, see
        # docs/COMMUNICATION.md's MSG91 section) but gets its own catalog row so the
        # Communication Providers UI can group it under one "MSG91" card.
        IntegrationProvider(integration_type=IntegrationType.SMS, provider="msg91", label="MSG91 SMS"),
        IntegrationProvider(integration_type=IntegrationType.WHATSAPP, provider="msg91", label="MSG91 WhatsApp"),
        IntegrationProvider(integration_type=IntegrationType.EMAIL, provider="msg91", label="MSG91 Email (SMTP)"),
    ]
    for row in rows:
        payload = row.model_dump(by_alias=True, exclude={"id"})
        await db["integration_providers"].update_one({"integration_type": row.integration_type, "provider": row.provider}, {"$setOnInsert": payload}, upsert=True)
    print(f"integration providers: ensured {len(rows)} entries")


async def seed_integrations_nav_item() -> None:
    db = get_database()
    nav_item = NavItem(
        key="integrations", label="Integrations", route="/integrations", order=34, required_module="integrations", required_resource="configs",
        required_action=PermissionAction.VIEW,
    )
    payload = nav_item.model_dump(by_alias=True, exclude={"id"})
    await db["nav_items"].update_one({"key": nav_item.key}, {"$setOnInsert": payload}, upsert=True)
    print("nav items: ensured 1 Module 9A entry")


async def seed_capture_sources() -> None:
    # Module 9B, Source Mapping — never hardcode which Lead Source a capture channel
    # attributes to; each row's `lead_source_id` is resolved once here (by the exact
    # names Module 6A's own Lead Sources are seeded with) and remains Owner-remappable
    # afterward via PATCH /lead-capture/sources/{key} without any code change.
    db = get_database()
    name_by_key = {
        CaptureSourceKey.WEBSITE_FORM: ("Website", "Website Form"),
        CaptureSourceKey.META_LEAD_ADS: ("Meta", "Meta Lead Ads"),
        CaptureSourceKey.MANUAL_API: ("Manual", "Manual API"),
    }
    seeded = 0
    for key, (lead_source_name, label) in name_by_key.items():
        lead_source_doc = await db["lead_sources"].find_one({"name": lead_source_name, "is_deleted": False})
        if lead_source_doc is None:
            print(f"capture sources: skipped '{key}' — Lead Source '{lead_source_name}' not found yet (run seed_settings_master_data first)")
            continue
        source = CaptureSource(key=key, label=label, lead_source_id=str(lead_source_doc["_id"]))
        payload = source.model_dump(by_alias=True, exclude={"id"})
        await db["capture_sources"].update_one({"key": key}, {"$setOnInsert": payload}, upsert=True)
        seeded += 1
    print(f"capture sources: ensured {seeded} entries")


async def seed_lead_capture_nav_item() -> None:
    db = get_database()
    nav_item = NavItem(
        key="lead_capture", label="Lead Capture", route="/lead-capture", order=35, required_module="lead_capture", required_resource="sources",
        required_action=PermissionAction.VIEW,
    )
    payload = nav_item.model_dump(by_alias=True, exclude={"id"})
    await db["nav_items"].update_one({"key": nav_item.key}, {"$setOnInsert": payload}, upsert=True)
    print("nav items: ensured 1 Module 9B entry")


async def seed_communication_nav_item() -> None:
    # No seed_communication_templates function exists on purpose — templates are
    # entirely Owner-authored (same "ships with zero seeded rows" posture as Module 6D's
    # own Notification Templates, decision 029); nothing is actually sent for a given
    # business event until the Owner creates a matching template.
    db = get_database()
    nav_item = NavItem(
        key="communication", label="Communication", route="/communication", order=36, required_module="communication", required_resource="templates",
        required_action=PermissionAction.VIEW,
    )
    payload = nav_item.model_dump(by_alias=True, exclude={"id"})
    await db["nav_items"].update_one({"key": nav_item.key}, {"$setOnInsert": payload}, upsert=True)
    print("nav items: ensured 1 Module 9C entry")


async def seed_ui_navigation_nav_items() -> None:
    # UI Navigation Enhancement pass — five existing routes (built by earlier modules)
    # that never got a nav_items row, so they were only reachable by typed URL. Each
    # gate mirrors exactly how its route is actually protected today (decision 033's own
    # rule), verified against the real backend dependency each route uses, not guessed.
    # Customers/Applications (customer/router.py) were originally gated by `_staff:
    # StaffDep` only (any authenticated Owner or Employee, no fine-grained permission);
    # the Employee Permission Matrix redesign later added `CustomerViewDep` —
    # `require_permission("customer", "customers", "view")` — in front of both routes
    # (list_customers, list_applications), but this nav catalog was never updated to
    # match, so the sidebar link stayed visible to every employee regardless of grant
    # even though the API itself would 403 them. Gated here to match the route for real.
    # Reminder Rules (reminders/router.py) is gated by `require_permission("reminders",
    # "reminder_rules", "view")`. Temporary Access / Geo Exceptions
    # (access_control/router.py) — the API itself only requires an authenticated user,
    # but the frontend route wraps them in RequireOwner, so `owner_only=True` matches the
    # same "mirror the frontend guard" precedent already used for Employees/Roles/
    # Referral Partner Management above.
    db = get_database()
    nav_defs = [
        NavItem(
            key="customers", label="Customers", route="/customers", order=40,
            required_module="customer", required_resource="customers", required_action=PermissionAction.VIEW,
        ),
        NavItem(
            key="applications", label="Applications", route="/applications", order=41,
            required_module="customer", required_resource="customers", required_action=PermissionAction.VIEW,
        ),
        NavItem(key="reminder_rules", label="Reminder Rules", route="/reminder-rules", order=42, required_module="reminders", required_resource="reminder_rules", required_action=PermissionAction.VIEW),
        NavItem(key="temporary_access", label="Temporary Access", route="/temporary-access", order=43, owner_only=True),
        NavItem(key="geo_exceptions", label="Geo Exceptions", route="/geo-exceptions", order=44, owner_only=True),
    ]
    for nav_item in nav_defs:
        payload = nav_item.model_dump(by_alias=True, exclude={"id"})
        await db["nav_items"].update_one({"key": nav_item.key}, {"$setOnInsert": payload}, upsert=True)
    print(f"nav items: ensured {len(nav_defs)} previously-unlinked entries")


async def main() -> None:
    await seed_counters()
    await seed_permission_catalog()
    await seed_bootstrap_owner()
    await seed_master_data()
    await seed_settings_master_data()
    await seed_dashboard_catalog()
    await seed_leads_nav_item()
    await seed_real_product_schemas()
    await seed_workflow_definitions()
    await seed_workflow_nav_items()
    await seed_reminder_rules()
    await seed_reminders_nav_items()
    await seed_referral_partner_management_nav_items()
    await seed_reporting_nav_items()
    await seed_report_definitions()
    await seed_integration_providers()
    await seed_integrations_nav_item()
    await seed_capture_sources()
    await seed_lead_capture_nav_item()
    await seed_communication_nav_item()
    await seed_ui_navigation_nav_items()


if __name__ == "__main__":
    asyncio.run(main())
