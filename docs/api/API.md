# API

For the response envelope, versioning, and pagination conventions, see `docs/api/API_STANDARDS.md`. For error codes, see `docs/api/ERROR_CODES.md`.

## Health

`GET /api/v1/health` — confirms Mongo + Redis connectivity. No auth required.

## Authentication (`/api/v1/auth`)

Implemented in `backend/app/features/auth/`. All 9 endpoints below — no others exist in this module (see `docs/decisions/DECISIONS.md` #007/#011 for why there's no signup endpoint for Owner/Employee, and why Customer/Referral Partner signup isn't public either). Full flow diagrams and rationale: `docs/AUTHENTICATION.md`.

Bearer auth: `Authorization: Bearer <access_token>`, no cookies (decision 008).

### `POST /auth/send-otp`
**Requires auth** — Owner/Employee only, and only for roles they're allowed to invite (Owner → Customer or Referral Partner; Employee → Customer only). There is no public signup entry point for any role (decision 011). Rate-limited (5/min).
- Body: `{ mobile: string, role: "customer" | "referral_partner" }` — `mobile` is the invitee, not the caller
- 200: `{ message, dev_otp }` — `dev_otp` is the raw OTP, populated only outside `production` (see `docs/KNOWN_LIMITATIONS.md`)
- Errors: `invalid_role_for_signup` (422), `forbidden` (403 — caller's role can't invite this role), `already_registered` (409)

### `POST /auth/forgot-password`
Rate-limited (5/min).
- Body: `{ mobile: string }`
- 200: `{ message, dev_otp }` — always 200, even for an unregistered/inactive mobile (no account-existence leak); `dev_otp` is `null` in that case since no OTP is actually issued

### `POST /auth/verify-otp`
Rate-limited (10/min). Used by both the signup and forgot-password flows.
- Body: `{ mobile: string, otp: string, purpose: "signup" | "forgot_password" }`
- 200: `{ otp_verified_token: string, is_new_user: boolean }` — the ticket is a short-lived (`OTP_VERIFIED_TOKEN_EXPIRE_MINUTES`, default 10min), single-use JWT consumed by `reset-password`
- Errors: `otp_not_found` (422), `otp_mismatch` (422), `otp_max_attempts_exceeded` (429)

### `POST /auth/reset-password`
Also used as "Create Password" for new signups — same semantics either way.
- Body: `{ otp_verified_token: string, new_password: string }` (8–72 chars)
- 200: no data
- Errors: `invalid_or_expired_ticket` (401) — expired, malformed, or already-used ticket

### `POST /auth/change-password`
Requires auth.
- Body: `{ current_password: string, new_password: string }`
- 200: no data
- Errors: `invalid_credentials` (401) if `current_password` is wrong

### `POST /auth/login`
Rate-limited (10/min).
- Body: `{ mobile: string, password: string }`
- 200: `{ access_token, refresh_token, token_type: "bearer", expires_in, role, user_id }`
- Errors: `invalid_credentials` (401), `account_locked` (423 — after 5 failed attempts, 15min lock, both configurable)

### `POST /auth/logout`
Requires auth.
- Body: `{ refresh_token: string }`
- 200: no data — marks that session `logged_out`

### `POST /auth/refresh`
- Body: `{ refresh_token: string }`
- 200: `{ access_token, refresh_token, token_type, expires_in }` — refresh token is rotated (old one stops working)
- Errors: `invalid_refresh_token` (401) — expired, invalid, session no longer active, **or** the presented token was already rotated out, in which case the entire session family is revoked as a side effect (reuse detection — see decision 013 and `docs/AUTHENTICATION.md`)

### `GET /auth/profile`
Requires auth.
- 200: `{ user_id, mobile, role, status, is_mobile_verified, created_at }` — identity fields only; no name/address/etc., those belong to future per-role profile collections (User Management)

## User & Employee Management (`/api/v1/employees`, `/api/v1/departments`, `/api/v1/designations`, `/api/v1/branches`)

Implemented in `backend/app/features/employee/`. No permission engine yet (Module 3) — authorization is a plain Owner-vs-self role check (`require_owner` dependency, or service-layer `_ensure_can_view`/`_ensure_self`).

**Self-service** (`/employees/me*`) — any authenticated Employee, own record only:
- `GET /employees/me`, `PATCH /employees/me` (narrow field set — see `SelfUpdateEmployeeRequest`), `POST /employees/me/photo/upload-url` + `PATCH /employees/me/photo`, `GET /employees/me/sessions`, `GET /employees/me/login-history`.

**Owner-only:**
- `POST /employees` — create. Body includes `mobile` + `initial_password` (decision 017) plus the full profile. Errors: `conflict` (409, duplicate mobile or email), `validation_error` (422, unknown department/designation/branch/reporting-manager id).
- `GET /employees` — list. Query params: `page`, `page_size`, `sort_by`, `sort_dir`, `search` (matches employee_code/name/email/mobile), `department_id`, `designation_id`, `branch_id`, `status`.
- `GET /employees/export` — CSV download of the full (unpaginated) list.
- `PATCH /employees/{id}` — edit. Any employee-editable field including `status` (triggers the login-blocking pairing — decision 016).
- `PATCH /employees/{id}/activate`, `PATCH /employees/{id}/deactivate` — convenience wrappers around the status-edit + login-sync.
- `POST /employees/{id}/reset-password` — triggers the existing `forgot-password` flow for that employee's mobile (decision 015). No data returned; the employee receives the OTP.
- `POST /employees/{id}/force-logout` — revokes every active session (decision 015). Returns `{ sessions_revoked: number }`.
- `POST /employees/{id}/documents/upload-url` + `POST /employees/{id}/documents` — presigned-upload-then-confirm, same pattern as the photo flow. No frontend page yet.

**Owner or self** (self only for own record, service-enforced):
- `GET /employees/{id}`, `GET /employees/{id}/sessions`, `GET /employees/{id}/login-history`, `GET /employees/{id}/activity-summary`, `GET /employees/{id}/documents`.

**Master data** (owner-only; full management UI deferred to a future Settings module — decision 019):
- `GET /departments`, `POST /departments`; `GET /designations`, `POST /designations`; `GET /branches`, `POST /branches`. All 409 on duplicate name/code.

## Role, Permission & Access Control (`/api/v1/roles`, `/permissions`, `/employees/{id}/roles`, `/temporary-access`, `/geo-exceptions`)

Implemented in `backend/app/features/access_control/`. All owner-only (`require_owner`, reused from Module 2). Full model/engine detail: `docs/PERMISSIONS.md`.

**Roles:**
- `POST /roles`, `GET /roles`, `GET /roles/{id}`, `PATCH /roles/{id}` — CRUD. 409 on duplicate name.
- `PATCH /roles/{id}/activate`, `PATCH /roles/{id}/deactivate`.
- `POST /roles/{id}/duplicate` — body `{ new_name }`. Copies the role's entire permission matrix to the new role.

**Permission catalog** (data-driven — `module`/`resource` are free text, not enums):
- `GET /permissions`, `POST /permissions` — body `{ module, resource, actions[], label? }`. `actions` validated against the fixed `PermissionAction` vocabulary. 409 on duplicate (module, resource) pair.

**Permission matrix:**
- `GET /roles/{id}/permissions` — current grants for a role.
- `PUT /roles/{id}/permissions` — bulk replace. Body `{ grants: [{ permission_id, granted_actions[], department_ids?, branch_ids? }] }`. 422 if an action isn't in the referenced catalog entry's own `actions`.

**Employee ↔ Role assignment:**
- `POST /roles/{id}/assign`, `POST /roles/{id}/remove` — body `{ employee_id }`. 409 on duplicate assignment.
- `GET /employees/{employee_id}/roles` — reverse lookup. New route registered from Access Control's own router (not added to Module 2's `router.py`).
- `GET /employees/{employee_id}/accessible-modules` — derived list of modules the employee has any granted action in (not stored).

**Temporary Access** (daily recurring window — see decision 022):
- `POST /temporary-access` — body `{ employee_id, grants[{permission_id, actions[]}], start_date, end_date, start_time, end_time, reason }`.
- `GET /temporary-access?employee_id=` (optional filter), `POST /temporary-access/{id}/revoke`.

**Geo Exceptions** (administrative only — decision 023, no enforcement engine exists):
- `POST /geo-exceptions` — body `{ employee_id, latitude, longitude, radius_meters, start_date, end_date, start_time, end_time, reason }`.
- `GET /geo-exceptions?employee_id=`, `POST /geo-exceptions/{id}/revoke`.

## Settings / Master Data (`/api/v1/departments`, `/designations`, `/branches`, `/lead-sources`, `/loan-products`, `/insurance-products`, `/document-types`, `/status-masters`, `/notification-templates`, `/api-settings`, `/company-settings`)

Implemented in `backend/app/features/system_settings/`. Every endpoint (read and write) requires `Depends(require_permission("system_settings", resource, action))` — Owner bypasses entirely (superuser); an Employee needs an explicit role grant on the matching `system_settings:<resource>` catalog entry (`scripts/seed.py` seeds one per resource so an Owner can grant immediately). Full detail: `docs/PERMISSIONS.md`, `docs/decisions/DECISIONS.md` #025–#030.

**Departments/Designations/Branches** — `GET`/`POST` stay on Module 2's own paths (see above, unchanged). This module adds:
- `PATCH /departments/{id}`, `PATCH /departments/{id}/activate`, `PATCH /departments/{id}/deactivate` (same shape for `/designations/{id}`).
- `PATCH /branches/{id}` (body: any of `name`/`code`/`address`/`phone`), `PATCH /branches/{id}/activate`, `PATCH /branches/{id}/deactivate`. 409 on duplicate `code`.

**Lead Sources / Loan Products / Insurance Products / Document Types** (`/lead-sources`, `/loan-products`, `/insurance-products`, `/document-types` — identical shape, one generic implementation, decision 027):
- `GET /{resource}`, `POST /{resource}` (body `{ name, description? }`, 409 on duplicate name).
- `GET /{resource}/{id}`, `PATCH /{resource}/{id}` (body `{ name?, description? }`, 409 on duplicate name).
- `PATCH /{resource}/{id}/activate`, `PATCH /{resource}/{id}/deactivate`.

**Status Masters** (`category` is free text, e.g. `loan_status`/`insurance_status`/`customer_status`):
- `GET /status-masters?category=` (optional filter), `POST /status-masters` (body `{ category, name, sequence?, description? }`, 409 on duplicate `(category, name)`).
- `GET /status-masters/{id}`, `PATCH /status-masters/{id}` (body `{ name?, sequence?, description? }`), `PATCH /status-masters/{id}/activate`, `PATCH /status-masters/{id}/deactivate`.

**Notification Templates** (`channel` is free text, e.g. `sms`/`email`/`whatsapp`):
- `GET /notification-templates?channel=` (optional filter), `POST /notification-templates` (body `{ channel, key, subject?, body, available_variables? }`, 409 on duplicate `(channel, key)`).
- `GET /notification-templates/{id}`, `PATCH /notification-templates/{id}` (body `{ subject?, body?, available_variables? }`), `PATCH /notification-templates/{id}/activate`, `PATCH /notification-templates/{id}/deactivate`.

**API Settings** (`config` is write-only — see decision 028):
- `GET /api-settings`, `POST /api-settings` (body `{ provider, label, config?, is_enabled? }`, 409 on duplicate `(provider, label)`). Response never includes `config` — only `configured_keys: list[str]` (the key names, not values).
- `GET /api-settings/{id}`, `PATCH /api-settings/{id}` (body `{ label?, config?, is_enabled? }` — `config` is merged into the existing blob, not replaced), `PATCH /api-settings/{id}/activate`, `PATCH /api-settings/{id}/deactivate`.

**Company Settings** (singleton — decision 030):
- `GET /company-settings` — creates a default row on first call if none exists yet.
- `PATCH /company-settings` — body `{ company_name?, primary_color?, secondary_color?, business_hours? }`.
- `POST /company-settings/logo/upload-url` + `PATCH /company-settings/logo` — presigned-upload-then-confirm, same pattern as Module 2's employee photo flow.

## Dashboard Framework (`/api/v1/dashboard`)

Implemented in `backend/app/features/dashboard/`. Every endpoint just requires an authenticated Owner/Employee (`get_current_active_user`, reused from Auth) — per-item visibility (which nav items, which widgets) is resolved *inside* the service via `PermissionEngine`, not at the route-dependency level. Full detail: `docs/decisions/DECISIONS.md` #032–#038.

- `GET /dashboard/nav` — the current user's permitted Sidebar items (`nav_items` catalog, filtered by `owner_only`/`required_module`+`resource`+`action`).
- `GET /dashboard/layout` — every widget the user is permitted to see (catalog defaults merged with their own `DashboardLayoutPreference`, if any), **without** computing data — used by the "Customize" UI, includes currently-hidden widgets so they can be re-enabled.
- `PUT /dashboard/layout` — body `{ widgets: [{ widget_key, is_visible, order, refresh_interval_seconds }] }`. Upserts one preference row per widget. 422 (`validation_error`) on an unknown `widget_key`.
- `GET /dashboard` — the resolved, **visible-only**, ordered widget list, each with its live `data` (computed via `widget_providers.py`). This is what the Dashboard home page renders.
- `GET /dashboard/notifications` — Notification Bell dropdown data. Always `{ available: false, items: [], unread_count: 0 }` today — no Notification Management module exists yet (decision 038).
- `GET /dashboard/search?q=` — Quick Search. Currently searches Employees only (Module 2's data), and only if the caller can see `employee_management:employee_records:view` (Owner always can). Extends to more entity types as their owning modules are built.

## Lead Management — 6A: Lead Foundation (`/api/v1/leads`)

Implemented in `backend/app/features/leads/`. Every endpoint requires `Depends(require_permission("leads", "leads", action))` — Owner bypasses; an Employee needs an explicit grant on the `leads:leads` catalog entry (`scripts/seed.py` seeds it). Full detail: `docs/decisions/DECISIONS.md` #040–#045.

- `GET /leads` — list. Query params: `page`, `page_size`, `sort_by`, `sort_dir`, `search` (matches lead_code/full_name/mobile/email), `source_id`, `product_category`, `product_id`, `assigned_to`, `status`. Action: `view`.
- `GET /leads/export` — CSV download of the full (unpaginated) list. Action: `export`.
- `GET /leads/check-duplicate?mobile=` — returns every existing Lead with that mobile, without creating anything. Action: `view`.
- `POST /leads` — create. Body: `{ full_name, mobile, email?, source_id, product_category, product_id, remarks? }`. Always succeeds even if `mobile` matches existing Leads — see `duplicate_of_lead_ids` in the response (decision 041). Errors: `validation_error` (422, unknown `source_id`/`product_id`). Action: `create`.
- `GET /leads/{id}` — detail. Action: `view`.
- `PATCH /leads/{id}` — edit any of `full_name`/`mobile`/`email`/`source_id`/`product_category`/`product_id`/`remarks`. Status is not editable here — fixed to `"new"` until Module 6C. Action: `edit`.
- `POST /leads/{id}/assign` — body `{ employee_id }`. Errors: `validation_error` (422, unknown `employee_id`). Action: `assign`.
- `POST /leads/{id}/unassign` — clears `assigned_to`. Action: `assign`.
- `GET /leads/{id}/timeline` — merged, newest-first feed of system-logged Activities and user-authored Notes (decision 042). Action: `view`.
- `POST /leads/{id}/notes` — body `{ text }`. Action: `edit`.

**Note for Create/Edit Lead UI:** the Source/Product dropdowns call Module 4's `GET /lead-sources`, `/loan-products`, `/insurance-products` — each gated by its *own* `system_settings:*` permission, not bundled with `leads:leads` (decision 045). An Employee role needs both grants for the form to fully work.

## Lead Management — 6B: Customer Onboarding & Application Flow

Implemented in `backend/app/features/customer/`. Full detail: `docs/CUSTOMER.md`, `docs/decisions/DECISIONS.md` #046–#052.

### Public (no auth — `public_router.py`)

- `GET /secure-links/{token}` — resolves a Flow 1 link: returns the Lead's `full_name`/`mobile`/`product_category`/`product_id`, whether an active account already exists for that mobile (`has_active_account`), and the link's own `link_status`.
- `POST /secure-links/{token}/start-signup`, rate-limited (5/min) — kicks off Auth's existing OTP signup for the Lead's mobile, using the link-generating Employee/Owner as `inviter` (decision 046). Errors: `already_registered` (409) if the mobile already has an active account — log in instead.
- `POST /customer-registration/start`, rate-limited (5/min) — Flow 2 entry. Body `{ mobile }`. Kicks off the same OTP signup using any seeded Owner as the technical `inviter` (decision 049).

From here, both flows use Auth's own existing, unmodified public endpoints directly: `POST /auth/verify-otp`, `POST /auth/reset-password` (create password), `POST /auth/login`.

### Customer self-service (requires an authenticated Customer)

- `POST /secure-links/{token}/claim` — Flow 1 only. Creates (or returns, idempotently) the draft Application for the Lead behind this link, tied to the now-authenticated Customer's `user_id`. 403 if the caller's mobile doesn't match the Lead's, or the link was already claimed by someone else.
- `GET /customers/me` — own profile, or `null` if not completed yet (Flow 1, pre-submission).
- `POST /customers/me` — complete profile (`CompleteProfileRequest`: name/email/DOB/gender/PAN/Aadhaar/address). 409 if it already exists.
- `PATCH /customers/me` — update profile fields.
- `GET /application-form-definitions?product_category=&product_id=` — the dynamic form's field list + required document types for a product.
- `POST /applications` — Flow 2 only (`StartApplicationRequest: { product_category, product_id }`) — requires a completed profile first (422 otherwise).
- `GET /applications/me?status=` — own applications (draft + submitted).
- `PATCH /applications/{id}` — update `form_data`/`pending_profile` while still `draft`. 409 once submitted.
- `POST /applications/{id}/submit` — validates every required field/document is present (422 otherwise); if `customer_id` is still null (Flow 1), requires `{ profile: CompleteProfileRequest }` in the body and creates the Customer (the Lead "conversion") as part of submitting.
- `POST /applications/{id}/documents/upload-url` + `POST /applications/{id}/documents` — presigned-upload-then-confirm, same pattern as Module 2's employee photo/document flow.

### Shared (Customer-self OR Owner/Employee-staff — `GET /applications/{id}`, `GET /applications/{id}/documents`)

Dispatches internally by `current_user.role` — a Customer gets their own-application check, Owner/Employee get the staff (assignment-scoped for Employee) check. No single permission gate could express both without incorrectly denying the Customer.

### Owner/Employee staff views (`require_staff` — Owner or Employee, no Access Control grant needed, decision 050)

- `GET /customers`, `GET /customers/{id}` — Owner sees all; Employee only sees Customers with an Application assigned to them.
- `GET /applications` — same scoping. Query params: `page`, `page_size`, `search` (application_code), `customer_id`, `assigned_to`, `unassigned_only` (bool — the "Unassigned Applications" queue, `assigned_to: null`; takes precedence over `assigned_to` when true; **Owner-only** — force-disabled/ignored for Employee actors, decision 053), `status`, `product_category`.
- `POST /applications/{id}/assign` — **Owner-only** (`require_owner`, not `require_staff`). Body `{ employee_id }`. 422 on an unknown `employee_id`.

### Secure link generation/revocation (staff)

- `POST /leads/{lead_id}/secure-links` — generates a Flow 1 link (`require_staff`). 409 if this Lead was already converted to a Customer.
- `POST /secure-links/{link_id}/revoke` — invalidates it early.

## Module 6C — Loan & Insurance Processing Pipeline

A case is never created directly — the first staff `GET /loan-cases`/`GET /insurance-cases` (list or single) lazily creates one for any submitted Application of the matching `product_category` that doesn't have one yet (decision 058). All staff endpoints below are gated by `require_permission("loan_management"|"insurance_management", "applications", action)` (decision 059) — `view` for reads, `edit` for data-entry/advance/hold-resume actions, `approve` for disbursement/policy-issuance, `assign` for (re)assignment. Both pipelines also support `POST /{loan,insurance}-cases/{id}/hold` (body `{ reason, remarks? }`, `reason` one of `waiting_for_customer`/`waiting_for_bank`/`waiting_for_insurance_company`/`internal_review`/`document_clarification`) and `POST .../resume` — an Optional Status on the workflow definition, not hardcoded (decision 064); 409 if already on hold / not on hold, respectively.

### Loan Cases (`/loan-cases`)

- `GET /loan-cases` — staff list. Query params: `page`, `page_size`, `search` (case_code), `status`, `assigned_to`, `unassigned_only` (bool, Owner-only, same semantics as 6B's — decision 053's pattern).
- `GET /loan-cases/{id}`, `GET /loan-cases/{id}/timeline` — detail / merged status+notes Timeline.
- `POST /loan-cases/{id}/notes` — add a note. `POST /loan-cases/{id}/assign` — body `{ employee_id }`, audited as `workflow_case_assigned` or `workflow_case_reassigned`.
- `POST /loan-cases/{id}/hold`, `POST /loan-cases/{id}/resume` — pause/resume at exactly the status it was paused at.
- `POST /loan-cases/{id}/documents/request` — body `{ document_type_ids[] }`; from `new_customer` this also advances to `documents_pending`. `POST /loan-cases/{id}/documents/verify` — checks all pending types are uploaded (reuses 6B's `application_documents`, unmodified — decision 060); advances `documents_pending → credit_evaluation` or `additional_documents → esign_nach_kyc`.
- `POST /loan-cases/{id}/bank-details` — body `{ bank_nbfc_name?, bank_application_id?, bank_reference_number?, assigned_officer?, bank_decision?, bank_remarks? }`; no status change (decision 061).
- `POST /loan-cases/{id}/credit-evaluation` — body `{ credit_score?, credit_remarks?, decision: "approved"|"rejected", rejection_reason? }`; 422 if rejecting without a reason. Approves to `offer_acceptance`, rejects to `rejected` (one of two exit points — decision 055).
- `POST /loan-cases/{id}/offer` — body `{ offered_amount, offered_tenure_months, offered_interest_rate }`; no status change (Customer's own accept/decline advances it — see below).
- `POST /loan-cases/{id}/esign-nach-kyc` — body `{ esign_completed, nach_completed, kyc_completed }`; advances to `final_evaluation` only once all three are `true`.
- `POST /loan-cases/{id}/final-evaluation` — same shape as credit-evaluation; approves to `send_for_disbursement`, rejects to `rejected` (the second exit point).
- `POST /loan-cases/{id}/disburse` — body `{ disbursed_amount, disbursed_reference }`; **`approve` permission**; advances to `disbursed` (terminal).
- Customer self-service (`require_customer`, ownership checked via the underlying Application's `user_id`): `GET /loan-cases/mine`, `GET /loan-cases/mine/{id}`, `POST /loan-cases/{id}/offer/accept` (→ `additional_documents`), `POST /loan-cases/{id}/offer/decline` (→ `rejected`). **No frontend screen calls these yet** — decision 062.

### Insurance Cases (`/insurance-cases`)

Same shape as Loan Cases, with its own finalized lifecycle (decision 064, superseding the draft flagged in decision 057):

- `GET /insurance-cases`, `GET /insurance-cases/{id}`, `GET /insurance-cases/{id}/timeline`, `POST /insurance-cases/{id}/notes`, `POST /insurance-cases/{id}/assign`.
- `POST /insurance-cases/{id}/hold`, `POST /insurance-cases/{id}/resume` — same as Loan.
- `POST /insurance-cases/{id}/documents/request`, `POST /insurance-cases/{id}/documents/verify` — valid from `application_submitted`/`documents_pending` (→ `underwriting`) and again from `additional_documents` (→ `premium_acceptance`).
- `POST /insurance-cases/{id}/underwriting` — body `{ sum_insured?, underwriting_remarks?, requires_medical, requires_additional_documents, decision: "approved"|"rejected", rejection_reason? }`; approves to `medical_verification` (if `requires_medical`), else `additional_documents` (if `requires_additional_documents`), else `premium_acceptance`; rejects to `rejected` (first exit point).
- `POST /insurance-cases/{id}/medical-verification` — body `{ outcome: "cleared"|"failed", medical_remarks?, rejection_reason? }`; cleared → `additional_documents` (if flagged) or `premium_acceptance`, failed → `rejected` (second exit point).
- `POST /insurance-cases/{id}/premium` — body `{ premium_amount }`; no status change.
- `POST /insurance-cases/{id}/policy/generate` — body `{ policy_number }`; records the policy number, stays in `policy_generation` (decision 064 — a distinct event from issuance, not the same action).
- `POST /insurance-cases/{id}/policy/issue` — no body (requires a policy number already generated, else 422); **`approve` permission**; advances to `policy_issued` (terminal).
- Customer self-service: `GET /insurance-cases/mine`, `GET /insurance-cases/mine/{id}`, `POST /insurance-cases/{id}/premium/accept` (→ `policy_generation`), `POST /insurance-cases/{id}/premium/decline` (→ `rejected`). Same "no frontend screen yet" caveat as Loan.

## Module 6D — Reminder & Notification Engine

Internal database notifications only — no WhatsApp/SMS/Email/push/external API (`app/features/notification_management/` stays reserved). Nothing here is scheduled ad hoc; three Arq cron jobs (`app/worker/tasks/reminders.py`) do the actual scanning and drive their behavior entirely from `reminder_rules` rows, never a hardcoded value.

### Tasks (`/tasks`, `require_permission("reminders", "tasks", action)`)

- `POST /tasks` — body `{ title, description?, assigned_to, due_at }`; `create`. Also creates a `task_assigned` Notification for the assignee.
- `GET /tasks` — `view`. Owner sees all; Employee sees only tasks assigned to them. Query params: `page`, `page_size`, `status` (`pending`|`completed`).
- `GET /tasks/{id}` — `view`; 403 if it's not the Employee's own task.
- `PATCH /tasks/{id}` — body `{ title?, description?, due_at? }`; `edit`.
- `POST /tasks/{id}/complete` — **not permission-gated**, self-service (`require_staff` + ownership: the assignee, or the Owner). Sets `status="completed"`, `completed_at`.

### Reminder Rules (`/reminder-rules`, `require_permission("reminders", "reminder_rules", action)`)

- `POST /reminder-rules` — body `{ rule_type: "re_eligibility"|"task_due", label, ...type-specific fields }`; `create`. `notify_before_days`/`notify_before_minutes` are `list[int]` (e.g. `[30, 15, 7, 1]`), not a single value — a rule can define multiple independent trigger points (decision 074); each configured offset fires its own reminder, tracked separately so a case/task that has already crossed several thresholds "catches up" on all of them in one scheduler pass instead of firing once.
- `GET /reminder-rules`, `GET /reminder-rules/{id}` — `view`.
- `PATCH /reminder-rules/{id}` — `edit`. `PATCH /reminder-rules/{id}/activate`, `/deactivate` — `edit`; toggles `status` active/inactive without deleting the rule.

### Notifications (`/notifications` — self-service, `require_staff` only, no permission catalog entry)

- `GET /notifications` — the caller's own inbox only. Query params: `page`, `page_size`, `status` (`unread`|`read`|`archived`|`dismissed`), `category` (`assignment`|`reminder`|`task`|`workflow`|`document`|`system`|`security` — decision 073). Every notification carries a `category`, derived automatically from its `notification_type` at creation time (never caller-supplied), so classification can never drift from the type that produced it.
- `GET /notifications/unread-count` — `{ unread_count }`, for a frontend badge.
- `POST /notifications/{id}/read`, `/archive`, `/dismiss` — 404 if the notification isn't the caller's own (ownership check, not just a 403 — mirrors the "not found, not forbidden" pattern used for cross-tenant-style isolation elsewhere in this project).

## Module 7 — Referral Partner Portal

Every management endpoint below (`/referral-partners` except `.../me*`, `/commission-rules`, `/commission-entries`) is `require_owner`-gated, not `require_permission` — the brief names no Employee capability anywhere in this module (decision 081). `/referral-partners/me*` routes are self-service, gated by a plain `require_referral_partner` role check plus (beyond reading your own profile) an `approval_status == "active"` check in the service layer.

### Referral Partner lifecycle (Owner)

- `POST /referral-partners` — body `{ full_name, mobile, email?, business_name? }`. Creates the `User` (pending_password) via Auth's own unmodified invite mechanism (decisions 003/011) *and* the `ReferralPartner` profile in one call; `approval_status` starts `pending_approval`.
- `GET /referral-partners` — query params: `page`, `page_size`, `search`, `approval_status`.
- `GET /referral-partners/{id}`.
- `POST /referral-partners/{id}/approve` — `pending_approval`|`deactivated` → `active`. 422 if already active.
- `POST /referral-partners/{id}/deactivate` — → `deactivated`. Login itself is untouched (Auth's own `User.status`) — this only blocks portal *actions* (add lead, edit lead, dashboard, commission history).

### Referral Partner self-service (`/referral-partners/me*`)

- `GET /referral-partners/me` — own profile; readable even before approval, so a partner can see why they're blocked.
- `POST /referral-partners/me/leads` — body `{ full_name, mobile, email?, product_category, product_id, remarks? }`. Requires `approval_status == "active"` (403 otherwise). Creates a real `Lead` (source forced to the seeded "Referral" `LeadSource`) via Module 6A's unmodified `LeadService.create_lead`, plus a `referral_leads` mapping row — `Lead`'s own schema is never touched (decision 077).
- `PATCH /referral-partners/me/leads/{lead_id}` — body `{ full_name?, mobile?, email?, remarks? }` only (never `product_category`/`product_id`/`source_id`). 403 once the lead is no longer `editable` (see below).
- `GET /referral-partners/me/leads` — query params: `page`, `page_size`. Each item includes `external_status` and `editable`.
- `GET /referral-partners/me/dashboard` — `{ total_leads, approved_leads, rejected_leads, commission_pending, commission_approved, commission_paid, commission_balance, recent_leads }`. Deliberately minimal, per explicit instruction — no Referral Reports here (that's Reports & Analytics' job, not built yet).
- `GET /referral-partners/me/commission-entries` — query params: `page`, `page_size`, `status`.

**External status (`external_status`, decision 078):** exactly one of `submitted` / `in_progress` / `approved` / `rejected` — never an internal Lead/Application/Case status, computed on every read rather than stored. **Editable (`editable`, decision 078):** `true` only while *"processing hasn't started"* — defined as "no Employee has been assigned to this Lead, and no Application exists for it yet" — deliberately not `Lead.status` (which never changes away from `"new"` at this stage of Module 6A and so can't signal anything).

### Commission Rules (Owner, `/commission-rules`)

- `POST /commission-rules` — body `{ label, product_category?, partner_id?, calculation_type: "percentage"|"flat", rate_or_amount, trigger_event: "loan_disbursed"|"insurance_policy_issued" }`. `product_category=null` = applies to every product; `partner_id=null` = the default rule for that product (a partner-specific rule overrides it) — never hardcoded, Owner-editable data (decision 079).
- `GET /commission-rules`, `PATCH /commission-rules/{id}`, `PATCH /commission-rules/{id}/activate`, `.../deactivate`. Editing or retiring a rule never changes any `CommissionEntry` already created from it (see below) — it only affects future entries.

### Commission Ledger (Owner, `/commission-entries`)

- `GET /commission-entries` — query params: `page`, `page_size`, `partner_id`, `status` (`pending`|`approved`|`paid`). Entries are created only by the daily `check_commission_triggers` Arq job (`app/worker/tasks/referral_partner.py`) — there's no manual-create endpoint. Each entry stores a full snapshot (`rule_id` plus the *applied* `calculation_type`/`rate_or_amount`, plus `base_amount`/`commission_amount` computed once at trigger time) — a later `CommissionRule` edit can never retroactively change it (decision 079).
- `POST /commission-entries/{id}/approve` — `pending` → `approved`. 422 otherwise.
- `POST /commission-entries/{id}/settle` — body `{ payment_reference }`. `approved` → `paid`. 422 if not yet approved. Manual only — no payment gateway integration exists (per explicit instruction).

## Module 8 — Reports & Analytics

The Reporting Framework built first, per explicit instruction — Business Reports are `report_definitions` rows (a seeded Mongo collection, decision 090) reached through two generic endpoints, never a bespoke route per report (decision 082). 10 of 17 reports are pure configuration, run by a generic executor keyed on `report_type` (`count`/`sum`/`list`); the remaining 7 (`report_type="custom"`) still need a matching function in `CUSTOM_REPORT_RUNNERS`, but their catalog metadata is data too. `/reports*` and `/scheduled-reports*` are `require_permission("reporting", "reports"|"scheduled_reports", action)` — delegable, unlike Module 7's Owner-only posture (decision 087).

### Report Engine (`/reports`)

- `GET /reports` — the catalog: `[{ key, label, category, description }, ...]` for all 17 reports (`view`).
- `GET /reports/{key}` — runs a report. Query params: `date_from`, `date_to` (both optional `YYYY-MM-DD`, inclusive — the one Date Range convention every report accepts). Returns `{ columns: [{key,label}], rows: [...], summary: {...} | null }` (`view`). 404 for an unknown key.
- `GET /reports/{key}/export` — same query params, returns `text/csv` (`Content-Disposition: attachment`) instead of JSON (`export`).
- The 17 keys: `lead_by_source`, `lead_conversion`, `lead_by_employee`, `lead_by_product`, `loan_applications`, `loan_approved`, `loan_rejected`, `loan_disbursed`, `bank_performance`, `insurance_applications`, `insurance_policies_issued`, `insurance_rejections`, `employee_task_summary`, `referral_leads`, `referral_conversions`, `referral_commission`, `dashboard_analytics`.

### Saved Filters (`/saved-filters` — self-service, `require_staff` only, no permission catalog entry)

- `POST /saved-filters` — body `{ report_key, label, filters }` (`filters` is whatever query params that report accepts — today just `date_from`/`date_to`). Strictly the caller's own preset (decision 086).
- `GET /saved-filters` — the caller's own presets only. Query param: `report_key` (optional filter).
- `DELETE /saved-filters/{id}` — 404 if it isn't the caller's own.

### Scheduled Reports (`/scheduled-reports`) — **framework only, nothing executes these yet** (decision 085)

- `POST /scheduled-reports` — body `{ report_key, label, filters?, frequency: "daily"|"weekly"|"monthly", recipient_user_ids? }` (`create`).
- `GET /scheduled-reports`, `GET /scheduled-reports/{id}` (`view`).
- `PATCH /scheduled-reports/{id}` — body any subset of the create fields plus `is_active` (`edit`).
- `DELETE /scheduled-reports/{id}` (`delete`).
- No Arq job reads this collection — `last_run_at` is never set by any code. Creating a schedule records intent only; see `docs/KNOWN_LIMITATIONS.md`.

## Module 9A — API Management

Configuration/management only — no endpoint here ever sends a WhatsApp message, fetches a Meta lead, sends an SMS, or sends an email; Test Connection is the only external call, and it never triggers a business action (decision 094). Every endpoint is `require_permission("integrations", "configs", action)`. Full detail: `docs/INTEGRATIONS.md`.

### Providers (`/integration-providers` — seeded catalog, read-only)

- `GET /integration-providers` — the known `(integration_type, provider)` catalog (`view`). Used by the frontend's provider picker; adding a new provider for an existing type is a new seeded row here, never a code change (decision 095).

### Configs (`/integration-configs`)

- `POST /integration-configs` — body `{ integration_type, provider, name, config }`. `provider` must exist in the catalog for that `integration_type` (422 otherwise). `config` is a flexible `dict[str,str]` — no per-provider schema is enforced server-side (decision 093). `create`.
- `GET /integration-configs` — query params: `page`, `page_size`, `integration_type` (optional filter). `view`.
- `GET /integration-configs/{id}` — `view`. Every response masks secret-looking config keys (App Secret/Access Token/Webhook Verify Token/Webhook Secret/API Key/Password — detected by naming convention) to their last 4 characters; non-secret keys (App ID, Phone Number ID, From Email, ...) are returned in full.
- `PATCH /integration-configs/{id}` — body `{ name?, config? }`. `config` merges into the existing decrypted dict rather than replacing it — rotating one secret never requires resupplying the others. `edit`.
- `PATCH /integration-configs/{id}/enable`, `.../disable` — `edit`. Disabling a config also clears its own `is_active` (decision 092).
- `POST /integration-configs/{id}/activate` — marks this config as the single Active one for its `integration_type`, deactivating any other. 422 if the config isn't enabled yet. `edit`.
- `POST /integration-configs/{id}/test` — runs a live Test Connection (decision 094), records the result to the config's own `last_tested_at`/`last_success_at`/`last_failure_at`/`last_error_message` plus an append-only test log, and returns `{ success, response_time_ms, error_message, tested_at }`. `edit`.
- `GET /integration-configs/{id}/test-logs` — the full test-attempt history for this config, newest first. `view`.

## Module 9B — Lead Capture

Every capture funnels through one shared pipeline reusing Module 6A's frozen `LeadService.create_lead` (decision 097). Full detail: `docs/LEAD_CAPTURE.md`.

### Public (no auth)

- `POST /lead-capture/website` — body `{ full_name, mobile, email?, product_category, product_id, remarks?, form_id? }`, all fields optional at the schema level (deliberately — see decision 099) so a bad submission still becomes a logged `CaptureFailure`, not just a bare 422. Rate-limited (20/min per IP). Returns `{ status: "created", lead_code }` on success; 422 (after logging) on missing fields or an invalid mobile number.
- `GET /lead-capture/webhooks/meta` — Meta's own webhook verification handshake (`hub.mode`, `hub.verify_token`, `hub.challenge` query params). Echoes `hub.challenge` back as plain text if `hub.verify_token` matches the active Meta `IntegrationConfig`'s `webhook_verify_token` (Module 9A); 403 otherwise.
- `POST /lead-capture/webhooks/meta` — the actual leadgen notification. Verifies the `X-Hub-Signature-256` header via HMAC-SHA256 against the active Meta config's `webhook_secret`; 403 immediately on mismatch, no processing attempted. Once verified, always returns 200 (Meta's own ack contract) — per-entry outcomes (success, or a logged `CaptureFailure`) don't change the HTTP response. Rate-limited (120/min).

### Staff — Manual capture (`require_permission("lead_capture", "captures", "create")`)

- `POST /lead-capture/manual` — body `{ full_name, mobile, email?, product_category, product_id, remarks? }`, strictly validated (no `CaptureFailure` on a bad request — the authenticated caller just fixes and resubmits). Returns `{ lead_code, lead_id }`.

### Staff — Source Mapping (`require_permission("lead_capture", "sources", action)`)

- `GET /lead-capture/sources` — the 3 seeded capture channels and their current Lead Source / default product mapping (`view`).
- `PATCH /lead-capture/sources/{key}` — body `{ lead_source_id?, default_product_category?, default_product_id? }` (`edit`). Remaps which Module 4 Lead Source a channel attributes to, or sets/changes the default product Meta Lead Ads falls back to when its own payload doesn't supply one.

### Staff — Capture Failures (`require_permission("lead_capture", "failures", action)`)

- `GET /lead-capture/failures` — query params: `page`, `page_size`, `capture_source`, `status` (`pending`|`resolved`|`exhausted`|`ignored`), `failure_reason` (`view`).
- `POST /lead-capture/failures/{id}/retry` — immediately re-attempts this one failure through the same shared pipeline, regardless of its `next_retry_at` (`edit`). Same outcome handling as the automatic retry job: success → `resolved`; permanently invalid → `ignored`; still failing → `retry_count` incremented, rescheduled or `exhausted`.

## Module 9C — Communication Engine

`Business Module -> Communication Service -> Queue -> Provider Adapter -> Provider -> Delivery Status -> Communication History.` No endpoint here lets a business module call a provider directly — every business-event-triggered queue item is still created by the worker's business-event poller (decision 104) and sent by the worker's queue processor. Stage 3 added a real, permissioned "send now"/CRM-linked-message endpoint and a Bulk Messaging surface (still worker-processed, never synchronous — decision 119); there remains no arbitrary campaign builder. Full detail: `docs/COMMUNICATION.md`.

### Templates (`require_permission("communication", "templates", action)`)

- `POST /communication/templates` — body `{ name, channel, category, subject?, body, language?, provider_template_name?, provider_template_namespace?, provider_template_language? }` (the `provider_template_*` fields are WhatsApp + MSG91 only, Stage 2). `variables` (the `{{name}}` placeholders the body references) is derived automatically, never supplied by the caller. `create`.
- `GET /communication/templates` — query params: `page`, `page_size`, `channel`, `category`. `view`.
- `GET /communication/templates/{id}` — `view`.
- `PATCH /communication/templates/{id}` — body `{ name?, subject?, body?, status?, language?, provider_template_name?, provider_template_namespace?, provider_template_language? }`; `variables` is recomputed whenever `body` changes. `edit`.

### Queue + Retry (`require_permission("communication", "queue", action)`)

- `GET /communication/queue` — query params: `page`, `page_size`, `status` (`pending`|`processing`|`sent`|`delivered`|`failed`|`retrying`|`exhausted`), `channel`. `view`. This same list, filtered to `status=failed` or `exhausted`, is the "Failed Messages" view — there is no separate endpoint for it.
- `POST /communication/queue/{id}/retry` — the Retry Action. Only valid on a `failed` or `exhausted` item; resets it to `pending` and immediately re-attempts through the same send path a scheduled worker run would use. `edit`.

### Delivery History (`require_permission("communication", "history", action)`)

- `GET /communication/history` — query params: `page`, `page_size`, `status`, `channel`. One row per queue item's terminal outcome — updated in place on a later transition (e.g. a manual retry that succeeds), never duplicated. `view`.

### CRM Record Messaging (`require_permission("communication", "send", action)`, Stage 3)

- `POST /communication/messages` — body `{ entity_type: "lead"|"customer", entity_id, channel, template_id, variables? }`. The recipient address is always resolved server-side from the authorized Lead/Customer record — never client-supplied. Authorization: the permission itself, plus the same per-record scoping Lead/Customer already use elsewhere (Owner bypasses; a non-Owner Employee must be the record's own assignee). `create`. Response: `{ success, queue_item_id, status, error }` — `error` surfaces the real reason (e.g. "MSG91 is not configured for this channel.") on failure, never a raw provider stack trace.
- `GET /communication/messages?entity_type=&entity_id=` — every message ever sent about that specific record, in-flight and terminal alike. Same IDOR scoping as sending. `view`.

### Bulk Messaging (`require_permission("communication", "bulk", action)`, Stage 3)

- `POST /communication/bulk-messages` — body `{ channel, template_id, recipient_type: "lead"|"customer", recipient_ids: string[] (1–10000, deduplicated) }`. Creates a `BulkMessageJob`; nothing is sent synchronously — a worker cron (`process_bulk_message_jobs`, every minute) does the actual per-recipient enqueue in resumable batches, idempotent per `(job, recipient, channel)`. `create`. Authorization is feature-level, not per-recipient IDOR-scoped (decision 120).
- `GET /communication/bulk-messages` — paginated list of past jobs. `view`.
- `GET /communication/bulk-messages/{id}` — job detail with live `pending`/`sent`/`delivered`/`failed` counts computed from the queue/history at read time. `view`.
- `GET /communication/bulk-messages/{id}/failed` — the job's own failed/exhausted queue items. `view`.
- `POST /communication/bulk-messages/{id}/retry-failed` — retries every failed/exhausted item for this job through the existing Retry Action code path. `edit`.
- `POST /communication/bulk-messages/{id}/cancel` — only valid while `queued`/`processing`; stops future enqueueing, does not affect already-enqueued items. `edit`.

### Public: MSG91 Delivery Webhook (Stage 2, no authentication — see `docs/COMMUNICATION.md`)

- `POST /communication/webhooks/msg91?secret=...` — SMS delivery-report callback. 200 for anything processed (including unknown/duplicate message ids), 403 for a missing/wrong secret, 400 only for a malformed body.

Endpoints for other modules are documented here as each is built.
