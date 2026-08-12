# Requirements (Living SRS)

Transcribed from the original project brief. This is the source of truth for scope — update it when a requirement is clarified, changed, or a new one is confirmed with the user; don't let it drift from what's actually being built.

## Portals

- Owner Portal
- Employee Portal
- Customer Portal
- Referral Partner Portal

One backend (FastAPI) powers all four, plus the future Flutter Android/iOS apps — no backend redesign for mobile.

## Roles

Owner, Employee, Customer, Referral Partner. Future: Super Admin.

## Authentication — **implemented and frozen**, Module 1 (see `docs/AUTHENTICATION.md`, `docs/api/API.md`, `docs/SECURITY.md`)

- Mobile number + password (not email) for Owner/Employee. **No self-service signup for any role** — Owner/Employee accounts are provisioned (Owner via `scripts/seed.py` bootstrap; Employee via the Owner's Create Employee action, Module 2, decision 017); Customer/Referral Partner accounts are created only when an authenticated Owner (either role) or Employee (Customer only) invites them — decision 011.
- Two-tier for Customer/Referral Partner: staff-invited OTP signup (Owner/Employee triggers → invitee gets OTP → verify → create password) + full account (mobile+password) for return visits. The "secure link scoped to one resource" half of decision 003 (tying a customer to a specific assigned application) is deferred until Lead Management exists — see `docs/KNOWN_LIMITATIONS.md`.
- Forgot password: mobile → OTP → verify → new password. Same OTP/ticket mechanism as signup, different `purpose`. Unlike signup, this remains publicly callable (it's for an already-existing active account, not account creation).
- OTP expires in 5 minutes, max 5 attempts, account locks for 15 minutes after 5 failed *login* attempts (a separate counter from OTP attempts) — all four values configurable via env.
- JWT (access 15min/refresh 7day, both configurable) + refresh token rotation with family/reuse detection (decision 013), session tracking (`sessions` collection, Login History fields) for future Session Management screen. Pure Bearer transport, no cookies — decision 008, with the client-storage trade-off documented in decision 012.
- **Frozen as of the review round** — see `docs/AUTHENTICATION.md`'s Freeze Rule. Future modules consume these APIs rather than modifying this module's behavior.

## User & Employee Management — **implemented and frozen**, Module 2 (see `docs/api/API.md`, `docs/decisions/DECISIONS.md` #015–#019)

- Owner: Create/Edit/Activate/Deactivate/View/Search/Filter/Export Employee, Reset Employee Password, Force Logout Employee, View Employee Sessions/Login History/Activity Summary. No delete (soft-delete infrastructure exists via `BaseRepository.soft_delete` but no delete action is exposed — not in the feature list).
- Employee (self-service only): view/update own profile (narrow field set), upload own photo, view own sessions/login history, change password via existing Auth API.
- Employee profile: personal info, contact info (mobile mirrors `users.mobile`, denormalized at creation), addresses, emergency contact, employment (department/designation/branch/joining date/employment type/reporting manager/status), bank details (account number encrypted, decision 018), documents (PAN/Aadhaar/offer letter/etc. — API only, no frontend page).
- Employee Code: `AFS-EMP-000001` format, auto-generated (Foundation's `id_generator`).
- Departments/Designations/Branches: DB-driven, not hardcoded. Seeded with starter data (Loan/Insurance departments, 5 designations, 1 branch); full management UI deferred to a future Settings (Master Data) module (decision 019).
- Business rules: no duplicate mobile (enforced via `users` unique index) or email (enforced via `employees` unique index); Employment status changes pair with login-blocking (decision 016, `on_leave` is the one non-blocking status — a judgment call, see `docs/KNOWN_LIMITATIONS.md`).
- **Frozen** — future modules (starting with Role/Permission/Access Control) consume its APIs rather than modifying this module's behavior.

## Role, Permission & Access Control — **implemented and frozen**, Module 3 (see `docs/PERMISSIONS.md`, `docs/decisions/DECISIONS.md` #020–#024)

- Owner: Create/Edit/Activate/Deactivate/View Role, Duplicate Role (copies its full permission matrix), Assign/Remove Role for an Employee.
- Permission catalog is fully data-driven: `module`/`resource` are free text (per explicit instruction — don't hardcode module names, so future modules are added by creating permission records, not by changing the engine). `PermissionAction` (View/Create/Edit/Delete/Assign/Approve/Reject/Export/Import/Upload/Download/Print/Share) is a fixed vocabulary, given as a closed set in the brief.
- Permission Matrix: bulk-set which actions a role has on each catalog entry, optionally scoped to specific departments/branches (Module 2's collections, read-only reference).
- Temporary Access and Geo Exceptions: both use a **daily recurring** date+time window (start_date/end_date/start_time/end_time) — an interpretation of the brief's 4 separate fields, not a confirmed spec (decision 022). Expiry is lazy (evaluated at check time), not a background sweep.
- Geo Exception is administrative record-keeping only — there is still no geo-fencing *enforcement* engine to except from (decision 023; the underlying use case was never confirmed, see Open Business-Logic Questions below).
- `PermissionEngine`/`require_permission` is new, tested infrastructure for **future** modules to gate their own routes — Module 2's endpoints are deliberately not retrofitted (decision 024).
- Audit logging for all role/permission/assignment/temporary-access/geo-exception changes, reusing the existing shared `write_audit_log`.
- **Frozen** — future modules consume `require_permission(...)` to gate their own routes rather than modifying this module's engine, models, or APIs.

## Settings (Master Data) — **implemented and frozen**, Module 4 (see `docs/decisions/DECISIONS.md` #025–#030)

- Departments/Designations/Branches (Module 2's collections): Edit/Activate/Deactivate added here — list/create stay Module 2's (decision 025).
- Lead Sources, Loan Products, Insurance Products, Document Types: full CRUD (name+description+status), one shared code path (`NamedMasterData`, decision 027). Seeded with the literal examples from the brief (Website/Meta/Manual/Referral/Walk-in; Personal/Business/Property Loan; Life/Health; PAN/Aadhaar/Bank Statement/Salary Slip).
- Status Masters: `category` (free text — e.g. `loan_status`/`insurance_status`/`customer_status`) + `name` + `sequence`, full CRUD. No example status values seeded — pipelines are unconfirmed business logic (decision 029, see Open Business-Logic Questions below).
- Notification Templates: `channel` (free text) + `key` + `subject`/`body`/`available_variables`, full CRUD. No example templates seeded (decision 029) — the future Reminder & Notification Engine module is the intended consumer.
- API Settings: `provider`/`label` + arbitrary `config` (encrypted as one blob, never returned in plaintext — decision 028), enable/disable. No credentials seeded; `app/services/{meta,whatsapp,sms,email,maps}` remain unwired stubs regardless of what's configured here.
- Company Settings: singleton (name, logo, primary/secondary color, business hours) — decision 030. Colors/logo are stored but not yet applied by the frontend at runtime.
- Every endpoint (read and write) is gated with `require_permission("system_settings", resource, action)` — the first real consumer of Access Control's engine (decision 026), resolving the "built but unused" gap flagged after Module 3.
- **Frozen** — future modules consume its master-data collections (read) and `require_permission` (for anything that writes Settings data) rather than modifying this module's models, engine, or APIs.

## Dashboard Framework — **implemented and frozen**, Module 5 (see `docs/decisions/DECISIONS.md` #032–#038)

- Layout: `AppShell` (Sidebar + Topbar + content) now wraps every authenticated route — replaces the Foundation-era placeholder that no route ever actually rendered inside. Sidebar is DB-driven (`nav_items` catalog, gated to mirror each linked route's *actual* protection — decision 033), responsive (off-canvas below `lg`). Topbar: Quick Search (Employees today, permission-gated), Notification Bell (framework-ready, no data yet), Profile Menu (own info + working Logout, wired to Module 1's previously-unused `/auth/logout` — decision 034).
- Dashboard Engine: 13 widgets, each permission-based (`required_module`/`resource`/`action`, resolved via `PermissionEngine` — forward-compatible with modules that don't exist yet, decision 032) and configurable per user (hide/show, order, refresh interval, via `DashboardLayoutPreference` + `PUT /dashboard/layout`).
- Only 3 of the 13 widgets compute real data today — Recent Activities (`audit_logs`), Department Summary and Employee Summary (Module 2's `employees`/`departments`) — the other 10 (Today's Leads, Pending Follow-ups, Pending Documents, Assigned Leads, Disbursed, Rejected, Revenue, Tasks, Notifications, Referral Summary) honestly return `available: false` rather than a fabricated number, since their owning modules don't exist yet (decision 038).
- No Lead/Customer CRUD, Loan/Insurance processing — explicitly out of scope per the brief, framework only.
- **Frozen** — future modules (Lead Management onward) add their own nav item + wire any relevant widget as part of their own build; they don't modify this module's engine, models, or APIs.

## Lead Management — Module 6, split into 6A–6D per the user's explicit instruction (it's the largest module — "the heart of the CRM")

### 6A: Lead Foundation — **implemented and frozen** (see `docs/decisions/DECISIONS.md` #040–#045)

- Lead entity carries its own contact info (`full_name`/`mobile`/`email`) — no Customer record exists yet to link to; that's 6B's job (decision 040).
- Lead Sources reuse Module 4's already-seeded `lead_sources` (Website/Meta/Manual/Referral/Walk-in) — no new source concept invented.
- Duplicate Detection flags (`duplicate_of_lead_ids`, matched on `mobile`) but never blocks creation — a standalone check endpoint lets the UI warn pre-submission (decision 041).
- Assignment: Owner/permitted-Employee assigns/unassigns a Lead to an Employee (Module 2, read-only reference).
- Timeline = merged system-logged Activities + user-authored Notes, lead-scoped — not the shared, still-reserved `features/timeline` module (decision 042).
- Search/Filters: name/mobile/email/lead_code search, source/product/assignee/status filters, pagination, CSV export.
- Status is fixed to `"new"` only this round — the real, configurable-per-product-type pipeline (see Lead Status Pipeline below) is 6C's job.
- No public/unauthenticated lead-capture endpoint — every Lead is created via the authenticated API; real Website-form/Meta Lead Ads webhook ingestion is future Integrations-module work (decision 043).
- Two of Dashboard's (Module 5) previously-placeholder widgets — Today's Leads, Assigned Leads — now compute real data; Pending Follow-ups stays a placeholder until 6D (decision 044).
- Gated entirely by `require_permission("leads", "leads", action)` — Owner bypasses; an Employee needs `leads:leads` granted, *plus* the relevant `system_settings:*` view permissions for the Create/Edit form's Source/Product dropdowns to populate (decision 045).
- **Frozen** — Module 6B (Customer Application Flow) builds on top of it (converts a Lead) rather than modifying this sub-module's models, engine, or APIs.

### 6B: Customer Onboarding & Application Flow — **implemented and frozen** (see `docs/decisions/DECISIONS.md` #046–#052, `docs/CUSTOMER.md`)

- Two entry flows — Flow 1 (existing Lead: secure link → login/create account → Application opens directly) and Flow 2 (direct portal: create account → complete profile → choose product → same Application form) — merge into the exact same Application form/validation/submit code path once the form opens, per the user's explicit "never duplicate business logic" instruction.
- Authentication is 100% reused from Module 1, unmodified: `AuthService.send_otp` is called with a resolved `inviter` (the link-generating Employee/Owner for Flow 1, any seeded Owner for Flow 2, decisions 046/049) rather than relaxing Auth's invitation-only rule; OTP verify/create-password/login all go through Auth's existing public endpoints as-is.
- Customer Profile (name/contact/address/KYC, PAN/Aadhaar encrypted) is a fixed schema, not the dynamic form engine — collected at registration for Flow 2, inline within the application (and used to create the profile at submission) for Flow 1, per the user's own refined wording on Lead-to-Customer conversion timing (decision 047).
- The Lead-to-Customer link is a reverse pointer (`Customer.converted_from_lead_id`) — Module 6A's `Lead` model is never modified (decision 048).
- Application: one Customer can hold multiple independent applications; status is fixed to draft/submitted only — the real pipeline is 6C's job.
- Dynamic Application Form Engine: `ApplicationFormDefinition` (seeded, product-specific fields only) + a generic renderer understanding a fixed field-type vocabulary — future products need only a new seeded row, never an engine change. Document requirements reference Module 4's `document_types` (including a new "Property Documents" entry, added via Module 4's own open create endpoint).
- Owner: View Customers/Applications, Search, Filter, Assign Employee, View Documents — nothing more. Employee: View *assigned* Customers/Applications/Documents only, enforced unconditionally in the service layer rather than via an Access Control grant (decision 050 — the brief frames this as inherent, not delegable).
- **Frozen** — Module 6C (Loan & Insurance Pipeline) builds the real status engine on top of `Application`/`ApplicationDocument` rather than modifying this sub-module's models, engine, or APIs.

### 6C: Loan & Insurance Processing Pipeline — **implemented and frozen** (see `docs/decisions/DECISIONS.md` #054–#064, `docs/MODULE_6C_WORKFLOW_PROPOSAL.md`, `docs/WORKFLOWS.md`)

- The real, configurable status engine (decision 004's original deferral, now built): `workflow_engine` (first real use of this reserved folder since Foundation, decision 005) drives both pipelines generically off seeded `workflow_definitions` rows — a future case type, an amended lifecycle, or a new Optional Status (like `on_hold`, below) is a data change, not new branching code.
- One unified `application_workflows` collection (discriminated by `case_type`), not split `loan_cases`/`insurance_cases` (decision 054). Reverse-points at Module 6B's frozen `Application` (decision 048's pattern) — 6B is never modified; a case is created lazily (get-or-create on first staff/customer read), since a live hook into 6B's frozen `submit_application` isn't permitted and this project's mongomock-based test infra doesn't support Mongo change streams (decision 058).
- Loan pipeline (exact sequence given in the brief): New Customer → Documents Pending → Credit Evaluation → Offer Acceptance → Additional Documents → eSign/NACH/KYC → Final Evaluation → Rejected / Send for Disbursement → Disbursed, with **two** rejection exit points (Credit Evaluation and Final Evaluation, decision 055) rather than only the last step.
- Insurance pipeline — its own lifecycle, not a copy of Loan's, **finalized by the user** (decision 064, superseding the draft flagged as an assumption in decision 057): Application Submitted → Documents Pending → Underwriting → Medical Verification (optional) → Additional Documents (optional) → Premium Acceptance → Policy Generation → Policy Issued, Rejected reachable from Underwriting or Medical Verification. Both optional stages are per-case flags recorded once during Underwriting, not fixed product attributes; Policy Generation and Policy Issued are two distinct business events, not one.
- **"On Hold" / "Resume"** — an Optional Status on both pipelines' workflow definitions, not a hardcoded branch (decision 064): every non-terminal status can transition to the shared `on_hold` status (closed reason vocabulary: waiting for customer/bank/insurance company, internal review, document clarification) and later resume back to exactly the status it paused at. Implemented as two thin calls into the existing generic `WorkflowEngine.transition()` (`workflow_engine/hold.py`) — no new engine validation logic.
- Bank/NBFC (Name, Application ID, Reference Number, Assigned Officer, Decision, Remarks) recorded as case fields, not a pipeline stage (decision 061); manual processing only, no bank integration.
- Document requirements reuse Module 4's `document_types` and Module 6B's own upload endpoints unmodified (decision 060) — no new document collection.
- Every action gated by real `require_permission("loan_management"|"insurance_management", "applications", action)` (decision 059) — a deliberate reversal of 6B's decision 050, since this is a genuinely delegable process.
- No rollback in v1 (decision 056) — On Hold/Resume is a temporary pause back to the *same* status, not a rollback to an earlier one. No Customer-facing frontend was built this round, per the explicit "Do NOT build Customer Portal enhancements" instruction (decision 062) — the Customer self-service API exists and is tested, just not reachable from any screen yet.
- Dashboard's "Disbursed"/"Rejected" widgets now compute real data (decision 063, same precedent as 6A's decision 044).
- **Frozen** — Module 6D (Re-Eligible & Reminder Engine) and any future Notification Management module consume this module's events/data rather than modifying its engine, models, or APIs.

### 6D: Reminder & Notification Engine — **implemented and frozen** (see `docs/decisions/DECISIONS.md` #065–#072)

- Internal database notifications only — no WhatsApp/SMS/Email/push/external API this round, per explicit instruction; `notification_management` stays reserved for that future work.
- Re-Eligible Reminder: a Rejected Loan/Insurance Case (Module 6C) becomes eligible again after a configurable number of days; the assigned Employee is notified a configurable number of days before that — both numbers live in an Owner-editable `reminder_rules` row, never hardcoded (decision 067).
- Task Reminder: a new `Task` entity (Owner assigns, Employee completes) with a due-soon reminder, then an escalation ladder — repeat reminders to the assignee, then one final notification to every Owner once fully escalated (decision 069). First real use of Dashboard's pre-reserved `reminders`/`tasks` widget gate (decision 068).
- Internal Notification Queue + History: every notification tracks unread/read/archived/dismissed + created/read timestamps, self-service per user (decision 066, 071).
- Scheduler: the first real Arq jobs (decision 002's original deferral) — `poll_audit_events` (every 5 min, reacts to Lead-assignment/document-upload by scanning the existing `audit_logs` collection rather than a live hook into those frozen modules, decision 065), `check_task_reminders` (every 15 min), `check_re_eligible_cases` (daily).
- **Frozen** — the Referral Partner Portal and any future Notification Management module consume this module's `Notification`/`Task` model rather than modifying its engine, models, or APIs.

## Security

JWT, refresh token, rate limiting, password hashing, OTP expiration, account lock, audit logs, geo-fencing ready, future two-factor ready.

## Dashboard Theme

Modern fintech. Dark sidebar (`#121212`), light content, primary orange `#FF7A00`, secondary orange `#FF9A3D`, background `#F5F7FA`, cards white, border `#E5E7EB`, text `#111827`. Responsive: desktop, tablet, future mobile.

## Sidebar (Owner)

Original full aspirational list: Dashboard, Loan Leads, Insurance Leads, Re-Eligible Leads, Customers, Referral Partners, Employees, Reports, Analytics, Notifications, Settings, Audit Logs, Logout. Employees see only modules their permissions allow (DB-driven — implemented as of Module 5, see `docs/PERMISSIONS.md` and the Dashboard Framework section above). 5 items are seeded so far (Dashboard, Employees, Roles & Permissions, Settings, Leads as of 6A) — the rest are added by their owning module as it's built, not invented ahead of time (decision 032).

## Dashboard Widgets

Original full aspirational list: Today Leads, New Leads, Assigned Leads, Pending Documents, Approved, Rejected, Disbursed, Today's Follow-ups, Overdue Tasks, Referral Leads, Commission Pending, Conversion Rate, Revenue, Monthly Chart, Department Performance, Employee Performance, Recent Activities. The 13-widget catalog actually implemented (Module 5, see above) is a close but not line-for-line match — some were merged/renamed (e.g. "New Leads"/"Today's Follow-ups" → `today_leads`/`pending_followups`) and some (Monthly Chart, Conversion Rate, Commission Pending) were left out of the initial catalog since they're derived/analytics-shaped rather than a direct count, better suited to the future Reporting module feeding a widget once real data exists. As of Module 6A, `today_leads` and `assigned_leads` compute real data (decision 044); as of Module 6C, `disbursed` and `rejected` do too (decision 063); as of Module 6D, `tasks` and `notifications` do too (decision 070) — 9 of 13 widgets are now real.

## Workflows

See `docs/WORKFLOWS.md` for Owner/Employee/Customer/Referral Partner/Lead workflows in full.

## Lead Status Pipeline

Configurable per product type (see decision 004) — not one hardcoded sequence. **Implemented by Module 6C** as `workflow_definitions` (seeded config, one row per case-type+status), not as a change to Module 6A's `Lead.status` (which stays fixed to `"new"`, unmodified) — the real pipeline lives on the new `application_workflows` collection instead, reverse-pointing at the submitted `Application`. See the 6C section above and `docs/WORKFLOWS.md` for the exact implemented sequences.

## Reminder Engine — **implemented and frozen, Module 6D** (see the 6D section above and `docs/decisions/DECISIONS.md` #065–#072)

- Re-eligible reminder: rejected lead becomes eligible again after 90 days; notify employee 10 days before. **Implemented against Rejected Loan/Insurance Cases (Module 6C)**, not `Lead` itself — Module 6A's Lead has no rejected status (fixed to `"new"` only, decision 040). Both numbers are seeded starter values in an Owner-editable `reminder_rules` row, not hardcoded.
- Task reminder: notify employee 1 hour before deadline; notify again if deadline passes; notify owner if still not completed. **Implemented** with a 30-minute default before-deadline reminder (per the user's own later, more specific worked example during the 6D review round — both this doc's "1 hour" and the later "30 minutes" are just starter `reminder_rules` values, changeable via `PATCH /reminder-rules/{id}` without a code change) — repeat escalations to the assignee, then one final notification to every Owner once fully escalated (decision 069).

## Integrations — Module 9, split into 9A–9D per the user's explicit instruction, each depending on the previous

Original brief: "Meta, WhatsApp, SMS, SMTP, Google Maps (geofencing) — owner-managed in System Settings (add keys, test connection, enable/disable). Future integrations follow the same pattern." Built as its own module (`features/integrations`), not inside System Settings — `system_settings.ApiSetting` already covered similar ground but is frozen (Module 4) and lacks concepts this needs (decision 091).

### 9A: API Management — **implemented and frozen** (see `docs/decisions/DECISIONS.md` #091–#096, `docs/INTEGRATIONS.md`)

- Configuration/management platform only — no message sent, no lead fetched, no business action beyond an optional Test Connection, per explicit instruction. 9B (Lead Capture)/9C (Communication) consume what's configured here.
- Multiple named configurations per integration type ("Meta Production", "Meta Sandbox", ...), exactly one Active — the user's own recommendation, given before implementation (decision 092).
- One encrypted config blob per configuration (Foundation's `security/encryption.py`, unmodified — same primitive as `ApiSetting`, decision 028), secrets masked to their last 4 characters in every response (decision 093).
- Test Connection: real live checks for Meta (Graph API)/Google Maps (Geocode API); generic reachability for WhatsApp/SMS/API-based Email (the brief's own "support multiple providers in the future"); a real SMTP handshake, no mail sent (decision 094).
- Seeded `integration_providers` catalog — "Integration Type → Provider → Configuration → Status," never hardcoded (decision 095).
- Reserved (not implemented) `health_status` field, `integration_test_logs` confirmed as permanent history by design (decision 096).

### 9B: Lead Capture — **implemented and frozen** (see `docs/decisions/DECISIONS.md` #097–#103, `docs/LEAD_CAPTURE.md`)

- One shared Webhook → Provider → Parser → Lead pipeline (decision 097) — Website form, Meta Lead Ads, and Manual API all reuse Module 6A's frozen `LeadService.create_lead` directly, never a new Lead-creation code path.
- Meta Lead Ads: a real webhook — HMAC-SHA256 signature verification (constant-time), then a real, live Graph API call to retrieve each lead's field data (decision 100) — the first place 9A's stored `webhook_verify_token`/`webhook_secret` are actually used.
- A system-actor pattern for the two unauthenticated capture paths (a real, persisted Owner satisfies `create_lead`'s requirement, `created_by` is nulled out immediately after — the same precedent Module 6B's direct-portal registration established, decision 098). The real provenance lives on the Lead's own Timeline instead.
- Capture Failures (duplicate/invalid_data/missing_required_fields/api_error) — never silently dropped, per explicit instruction; only `api_error` (transient) retries automatically via a 15-minute Arq job with exponential backoff (decision 099).
- Idempotency via `capture_receipts`, only for Meta (a real external id exists — `leadgen_id`); Website/Manual rely on 6A's own cross-lead `duplicate_of_lead_ids` flagging instead (decision 101).
- Source Mapping: a seeded, Owner-remappable `capture_sources` catalog — never hardcoded (decision 102).
- Reserved, at freeze review (decision 103): an inert `webhook_events` collection for future observability, and a Lead Source Metadata / Website Form Version passthrough (campaign/ad set/ad/UTM/form version) captured only when a source's payload actually supplies it.

### 9C: Communication Engine — **implemented and frozen** (see `docs/decisions/DECISIONS.md` #104–#108, `docs/COMMUNICATION.md`)

- Scope: WhatsApp, SMS, Email only — templates, queue, retry, delivery status, history, Failed Messages + Retry Action. Not a second notification system (6D already owns in-app notifications) and not an integration system (9A already owns provider credentials).
- `Business Module -> Communication Service -> Queue -> Provider Adapter -> Provider -> Delivery Status -> Communication History` — no business module ever calls a provider directly (decision 104). A worker poller consumes the same already-written `audit_logs` entries 6D's own notification engine reads (decision 065), for 5 named business events: Lead Assigned, Reminder Triggered, Application Submitted, Document Requested, Commission Ready.
- A common Provider Adapter interface (`DeliveryOutcome`); real WhatsApp/SMS sends (generic HTTP POST — the same honest "no single fixed API contract" limitation 9A's own Test Connection already disclosed for these two channels) and a real Email send (SMTP via `smtplib`, or a generic HTTP POST for an API-based provider) (decision 105).
- Owner-authored templates only (`{{variable}}` substitution, ships with zero seeded rows — same posture as Notification Templates, decision 029); OTP is a reserved template category only — Auth (Module 1) is frozen and OTP delivery must stay synchronous, so it is never routed through this queue (decision 106).
- Recipient resolution is read-only against each frozen module's own repository (Employee/Customer/ReferralPartner/User) — never a new coupling; a dedicated `communication_checkpoints` polling cursor, separate from 6D's own (decision 107).
- Retry only transient failures, configurable attempts (`MAX_RETRY_ATTEMPTS=5`), exponential backoff; permanent failures go straight to `failed`, never retried. The manual Retry Action reuses the exact same send path a scheduled worker run would use (decision 108).

### 9D: Future Integrations — **not started, pending 9C approval**

## Explicitly Not Hardcoded

Statuses, Loan Types, Insurance Types, Permissions, Departments, Notification Templates, Business Settings — all DB-driven/configurable.

## Open Business-Logic Questions

See `docs/roadmap/TODO.md` — commission rules, geo-fencing's concrete use case (still open as of Module 3 — Geo Exceptions are administrative-only pending this), and rejection-branching stages are not yet defined and must not be invented. As of Module 4, this also covers concrete Status Master values (Loan/Insurance/Customer status pipelines) and Notification Template copy — the collections and full CRUD UI exist, but no example rows were invented; the Owner defines them via the UI when the underlying pipeline/copy decisions are made.
