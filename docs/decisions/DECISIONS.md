# Architecture Decisions

Each entry: the decision, why, and what it touches. Append new entries at the bottom; don't rewrite history — if a decision is reversed, add a new entry that supersedes it and link back.

---

## 001 — Multi-tenancy deferred to Phase 2

**Decision:** `tenant_id` is not added to collections/queries in Phase 1.

**Why:** Considered adding it now (zero-migration path to SaaS multi-tenancy later) but the user chose to defer — Phase 1 is single-tenant (Ashapura Financial Services only), and the added complexity in every query isn't justified yet.

**Impact:** `BaseDocument` (`backend/app/shared/base_document.py`) and `BaseRepository` (`backend/app/shared/base_repository.py`) are written so `tenant_id` can be added to both in one place when needed. Every feature built before that point will need a retroactive migration + query-filter update. Tracked as a known limitation — see `docs/KNOWN_LIMITATIONS.md`.

## 002 — Arq for background jobs / scheduling

**Decision:** Use Arq (asyncio-native task queue, Redis-backed) rather than Celery or APScheduler for the Reminder Engine, re-eligibility checks, and task escalations.

**Why:** FastAPI's architecture is fully async; Arq's worker model is async-native and shares the same Redis instance already required for OTP/sessions/cache, avoiding a second broker. Celery's worker model is sync-first and would sit awkwardly alongside the rest of the stack. APScheduler is in-process and doesn't scale to multiple worker instances.

**Impact:** `backend/app/worker/worker_settings.py` defines the Arq `WorkerSettings`; `backend/app/worker/tasks/` is where the Reminder Engine module adds its first jobs. `docker/backend/Dockerfile` is shared between the `backend` and `worker` services in `deployment/docker-compose.yml`, differing only by command.

## 003 — Two-tier auth for Customer / Referral Partner

**Decision:** Customers and Referral Partners get (a) a scoped, expiring secure-link token for a specific assigned resource (e.g. one lead's application form) requiring no password, and (b) a full mobile+password account for ongoing portal access.

**Why:** The Employee workflow generates a link for the customer to fill their application — that shouldn't require account setup first. But customers also need to log back in later to track status. One mechanism can't cleanly serve both without either forcing account creation up front (friction) or making the portal permanently link-only (no persistent access).

**Impact:** `backend/app/security/tokens.py` issues/validates the secure-link JWTs (separate from `jwt.py`'s session tokens because they're scoped to one resource, not a user). The Authentication module (next after this scaffold) implements the account side using the same `security/jwt.py` + `security/password.py` primitives Owner/Employee use.

## 004 — Lead Status is configurable per product type

**Decision:** Lead Status is not one hardcoded pipeline. It's a config collection keyed by product type (Loan, Insurance, future types), each with its own ordered status list.

**Why:** The originally given status pipeline (Bank/NBFC application ID, NACH, e-Sign) is loan-specific and doesn't fit Insurance's lifecycle (proposal, medical, policy issuance). This is also required by the existing "never hardcode statuses" rule.

**Impact:** No schema is defined yet — `leads` and the future `loan_applications` / `insurance_applications` collections are placeholders in `docs/database/COLLECTIONS.md` until the Lead Management module is planned. The `workflow_engine` feature folder (`backend/app/features/workflow_engine/`, empty this pass) is reserved specifically so status transitions are configured once and reused, not hardcoded per module — see decision 005.

## 005 — Reusable workflow_engine and event_engine instead of per-module state handling

**Decision:** Add two cross-cutting feature folders, not tied to any one business object: `workflow_engine` (configurable state machines — statuses, allowed transitions, required fields per transition) and `event_engine` (pub/sub for side effects like "lead assigned → notify → remind → log").

**Why:** The CRM has many approval chains (Loan, Insurance, Customer document lock/unlock) that are structurally similar state machines. Hardcoding transitions inside each feature would duplicate logic and make adding a new product type (e.g. a future loan sub-type) require code changes instead of configuration. Likewise, side effects of an action (assignment, status change) fan out to multiple features (notifications, reminders, audit) — routing that through direct cross-feature calls creates tight coupling; an event bus keeps features decoupled.

**Impact:** Both folders are empty structure only in this pass (`backend/app/features/workflow_engine/`, `backend/app/features/event_engine/`). They become real when Lead Management is built, since that's the first feature with a non-trivial state machine.

## 006 — Explicit feature-folder naming over short names

**Decision:** Feature folders use unambiguous, extensible names: `loan_management` not `loan`, `insurance_management` not `insurance`, `document_management` not `documents`, `notification_management` not `notifications`, `system_settings` not `settings`, `reporting` (consolidating reports + analytics) not `reports`, `audit` not `audit_logs`, `access_control` (permissions + roles + departments + designations + delegation) not `permissions`.

**Why:** Each of these will grow beyond its literal name (e.g. `system_settings` will hold API settings, company settings, notification settings, security settings, workflow settings, status settings — not just one settings screen). Naming them for their eventual scope avoids a rename/restructure later.

**Impact:** `backend/app/features/*` and `frontend/src/features/*` folder names (see `docs/database/COLLECTIONS.md` and `docs/architecture/MODULES.md` for the full list). `docs/NAMING_CONVENTIONS.md` documents the convention itself.

---

# Module 1 — Authentication

## 007 — Single shared `users` identity collection; no self-signup for Owner/Employee

**Decision:** All four roles share one `users` collection with a globally unique `mobile` field. Login takes only `{mobile, password}` — role is never client-asserted, it's read from the matched record. Owner and Employee accounts are never created via self-service OTP signup; only Customer and Referral Partner can self-signup (`SELF_SIGNUP_ROLES` in `backend/app/features/auth/constants.py`).

**Why:** The brief's Auth API scope lists Login/Logout/Forgot-Password/Reset/Change/Refresh/Profile for Owner and Employee — no signup endpoint. User Management (which would create Employee records) is explicitly out of scope for this module. Allowing open self-signup for Owner would let anyone with a valid mobile number become an Owner of a financial CRM — a security hole, not an oversight. A single identity collection with a global mobile-uniqueness constraint also avoids inventing an unspecified "same phone number, multiple roles" business rule.

**Impact:** `backend/app/features/auth/models.py:User`; unique index on `users.mobile` (`backend/app/features/auth/indexes.py`). `scripts/seed.py` gained a bootstrap-Owner step (`BOOTSTRAP_OWNER_MOBILE`/`BOOTSTRAP_OWNER_PASSWORD` env vars) since without it there would be no way to ever log in. Employee records can only be seeded manually until User Management exists.

## 008 — Pure Bearer JWT confirmed over cookies

**Decision:** Access and refresh tokens are both returned in the JSON response body and sent via the `Authorization` header — no cookies anywhere, for either token.

**Why:** This was raised explicitly at the start of the module because the brief suggested "HttpOnly cookies" as an example strategy, which would have conflicted with the Foundation's already-frozen `docs/api/API_STANDARDS.md` commitment to one identical contract for React web and future Flutter apps. Offered as a choice; pure Bearer was confirmed, preserving that contract and avoiding CSRF exposure entirely (no ambient browser credentials).

**Impact:** `backend/app/security/jwt.py`. Frontend: access token lives only in React context memory (`frontend/src/features/auth/context.tsx`), never persisted; refresh token is persisted to `localStorage` so a page reload doesn't force re-login — the accepted tradeoff of not using cookies, see `docs/KNOWN_LIMITATIONS.md`.

## 009 — Refresh tokens are stateful (DB-backed sessions), access tokens stay stateless

**Decision:** Access tokens are pure stateless JWTs (verified by signature/expiry alone, no DB lookup). Refresh tokens are tied to a `sessions` document via a `jti` claim; refreshing rotates both the JWT and the session's stored token id/hash, and logout/lockout can invalidate a session server-side.

**Why:** The brief requires a Session Management data source (device, browser, OS, IP, login/logout time, status, last activity, token identifier) and the ability to revoke sessions — neither is possible with a fully stateless refresh token. Access tokens stay stateless to avoid a DB round-trip on every authenticated request.

**Impact:** `backend/app/features/auth/models.py:Session`, `backend/app/features/auth/service.py` (`login`/`refresh`/`logout`). No Session Management *screen* is built this module (Settings/Dashboard are out of scope) — this only establishes the data and the rotation/revocation mechanics it will read from.

*Refined by decision 013:* rotation was originally "update the same session doc in place"; it now inserts a new chained row per rotation instead, to support reuse detection.

## 010 — `BaseDocument` gains a real `id` field (Foundation bug fix)

**Decision:** `BaseDocument` (`backend/app/shared/base_document.py`) now declares `id: PyObjectId | None = Field(default=None, alias="_id")`. `BaseRepository.insert` excludes `id` from the write payload so Mongo always generates the real value.

**Why:** Discovered while building this module: Pydantic v2 silently drops unrecognized fields by default, so every document read back from Mongo was losing its own `_id` — `find_by_id`/`find_many`/etc. all returned models with no usable identifier. This is a bug in already-approved Foundation code, not a restructuring, so it was fixed in place rather than deferred.

**Impact:** Every current and future `BaseDocument` subclass gets a working `.id` (and the new `.require_id()` helper, for the common "this came from the DB, id is definitely set" case) with no per-model changes needed. `backend/app/shared/base_repository.py`'s `TModel` bound was tightened from `BaseModel` to `BaseDocument` since the repository now depends on this field existing.

---

# Module 1 — Authentication, round 2 (post-review hardening)

The user reviewed the initial Authentication build and requested five changes before freezing the module. Four became decisions below; the fifth (Login History enrichment: geoip, login method, failure reason) is mechanics, not an architectural fork, and is just described in `docs/AUTHENTICATION.md`.

## 011 — No public self-signup for any role; Customer/Referral Partner signup is invitation-only

**Decision:** `POST /auth/send-otp` now requires an authenticated caller and enforces who can invite whom: Owner or Employee may invite a Customer; only Owner may invite a Referral Partner. There is no unauthenticated path to creating any account, for any role.

**Why:** The original build (see decision 007) already blocked Owner/Employee self-signup, but left Customer/Referral Partner signup open to anyone who could reach the endpoint with a valid-shaped mobile number — which doesn't match the actual business workflow (Website Lead → Employee → generate link → Customer signs up; Owner → invites → Referral Partner). Reviewed and confirmed: signup should always be staff-initiated, never public.

**Scope note:** The brief's "Generate Secure Link" step still cannot be a real clickable link tied to a specific application/Lead — Lead Management is out of scope for this module (see decision 003, `docs/KNOWN_LIMITATIONS.md`). This decision implements the security-relevant core (no public signup, staff-authorized invitation) using the existing `send-otp` endpoint rather than adding a 10th API — the literal link-delivery UX is still deferred.

**Impact:** `backend/app/features/auth/constants.py:INVITER_ROLES_BY_INVITEE_ROLE`, `backend/app/features/auth/service.py:send_otp` (now takes `inviter: User`), `backend/app/features/auth/router.py` (`send-otp` now requires `CurrentUserDep`). Frontend: removed the self-service "Create an account" toggle from `LoginPage.tsx` — there is currently no UI that can trigger an invitation (that belongs to a future Owner/Employee portal), so this flow is API-complete and tested but has no frontend entry point yet, same pattern as `change-password`.

## 012 — Refresh token client-side storage: `localStorage`, with rotation + reuse detection as the mitigation

**Decision:** The refresh token is persisted to the browser's `localStorage` (access token stays memory-only, per decision 008). This is a deliberate, documented choice, not a default left unexamined.

**Why — trade-offs considered:**
- Decision 008 already ruled out cookies entirely (no HttpOnly option) to preserve one identical contract for React web and future Flutter apps. That constraint means *any* client-side persistence of the refresh token is readable by JavaScript running on the page — `localStorage`, `sessionStorage`, and `IndexedDB` are all in the same exposure class from an XSS attacker's perspective; none of them is meaningfully safer than the others against a targeted payload.
- The real choice is therefore **persist vs. don't**: persisting (any of the three) survives a page reload without forcing re-login; not persisting (memory-only) shrinks the XSS exposure window to "attacker script runs while the token happens to be in memory" but forces a fresh login on every reload/tab close — poor UX, and there's no Dashboard/shell yet to make that tolerable.
- `localStorage` was chosen over `sessionStorage` for one concrete reason: `sessionStorage` doesn't survive a closed tab, which would force re-login far more often than is reasonable for a business CRM used across a workday.
- The residual risk (a stolen refresh token being long-lived) is what decision 013 (rotation + reuse detection) exists to bound: a stolen token can be used at most once before the theft is detected and the entire session family is killed, rather than granting an attacker indefinite access for the token's full 7-day lifetime.

**Consistency across clients:** the future Flutter apps should use platform secure storage (`flutter_secure_storage`, backed by Keychain/Keystore) for the refresh token — not the web `localStorage` equivalent — since mobile platforms *do* have a meaningfully more secure storage tier that iOS/Android sandbox from other apps. The wire contract (pure Bearer, decision 008) stays identical either way; only the client-side storage mechanism differs per platform, which is expected and consistent with "same API contract, platform-appropriate storage."

**Impact:** `frontend/src/features/auth/context.tsx`. Documented in `docs/AUTHENTICATION.md` and `docs/KNOWN_LIMITATIONS.md` rather than left as an implicit, unexamined default.

## 013 — Refresh token family / reuse detection

**Decision:** Every login generates a `family_id` (random, constant across a rotation chain). Each refresh does not overwrite the session document in place — it marks the current row `rotated` and inserts a new row carrying the same `family_id`. If a refresh request ever presents a token whose row is already `rotated` (i.e. a stale, previously-valid-but-superseded token), that's treated as evidence of theft/replay: **the entire family is revoked**, killing every token in the chain, not just rejecting that one request.

**Why:** Plain rotation (decision 009) already prevents an old token from being reused *successfully*, but a naive implementation just rejects that one request while leaving the legitimate current token (which the attacker doesn't have) working fine — an attacker who stole an old token gets a clear, silent signal that it's dead, with no consequence to the legitimate session. Family-wide revocation on reuse turns that same signal into "someone had a token they shouldn't have" and responds by forcing everyone in that chain to log in again, which is the standard mitigation for this class of attack (used by most major refresh-token implementations).

**Impact:** `backend/app/features/auth/models.py:Session` (`family_id`, `SESSION_STATUS_ROTATED`), `backend/app/features/auth/repository.py:SessionRepository.revoke_family`, `backend/app/features/auth/service.py:refresh`. New audit event `suspicious_refresh_reuse`. Tested in `tests/api/test_auth.py:test_refresh_reuse_revokes_entire_family`.

## 014 — Login History enrichment: GeoIP stub, login method, failure reason

**Decision:** `Session` gained `city`/`country` (populated by a new `app/services/geoip/` stub, unconfigured — same pattern as `sms`/`whatsapp`/`email`) and `login_method` (currently always `"password"`, the only method that creates a session today). Failed-login audit log entries now carry a `reason` (`account_not_found` | `account_inactive` | `invalid_password`) in `metadata` — internal-only detail; the client-facing error response stays the same generic "Invalid mobile number or password" regardless of reason, to avoid account enumeration.

**Why:** Requested to make future audit/support work easier without waiting for a real GeoIP provider or additional login methods (OTP-based login, invitation auto-login) to exist — the fields are ready now, populated with real data as soon as those capabilities are built.

**Impact:** `backend/app/services/geoip/client.py`, `backend/app/features/auth/models.py`, `backend/app/features/auth/constants.py:LoginMethod`, `backend/app/features/auth/service.py:_login_failure_reason`. `city`/`country` are always `null` today — see `docs/KNOWN_LIMITATIONS.md`.

---

**Freeze:** Authentication is approved and frozen as of this round. No architectural changes to this module without explicit approval. Future modules consume these APIs (`docs/api/API.md`) rather than modifying Authentication's behavior.

---

# Module 2 — User & Employee Management

## 015 — Owner-adjacent Auth actions reuse existing internals, add zero new Auth capabilities

**Decision:** "Reset Employee Password" calls `AuthService.forgot_password()` directly (unmodified — that method was already public and role-agnostic, it just needed the target mobile number). "Force Logout" and the sessions/login-history views query the `sessions`/`audit_logs` collections directly via Auth's existing, unmodified `SessionRepository` (its inherited `find_many`/`update` from `BaseRepository` were already sufficient — no new method was needed). No file under `app/features/auth/` was touched.

**Why:** The Owner Features list requires both actions, but Authentication is frozen and had no admin-initiated equivalents (only self-service `change-password`/`logout`, gated by knowing the current password or presenting your own refresh token). Rather than requesting an exception to extend Auth's API surface, both were achievable by composing Auth's already-existing, already-tested internals from Module 2's own service layer — genuinely zero lines changed in `app/features/auth/`.

**Impact:** `backend/app/features/employee/service.py:reset_employee_password`, `force_logout_employee`, `list_employee_sessions`, `list_employee_login_history`. Verified in `tests/api/test_employee.py` (`test_reset_employee_password_triggers_forgot_password_flow`, `test_force_logout_revokes_active_sessions`).

## 016 — Employment status is paired with login-blocking; ON_LEAVE is the one exception

**Decision:** `Employee.status` (employment status: active/inactive/suspended/on_leave/resigned) and `users.status` (login-blocking: active/disabled) are kept in sync on every status change via `EmployeeService._sync_login_status`. All statuses disable login except `on_leave`.

**Why:** Not specified in the brief — a judgment call. Blocking login on Inactive/Suspended/Resigned is the obvious safe default (matches "Deactivate Employee" being a named feature). On Leave was judged to *not* block login since an employee on leave may still reasonably need portal access (e.g. checking something, or the leave ending early) — this is the one part of this decision that's a genuine guess rather than an obvious default, flagged in `docs/KNOWN_LIMITATIONS.md` for explicit confirmation.

**Impact:** `backend/app/features/employee/constants.py:EmploymentStatus.LOGIN_BLOCKED`, `service.py:_sync_login_status` (called from `create`... no — from `activate_employee`, `deactivate_employee`, and `update_employee` whenever `status` changes).

## 017 — Employee accounts get an Owner-set initial password, not an OTP invite

**Decision:** `POST /employees` requires the Owner to supply `initial_password` directly; the account is `active` immediately (no `pending_password` state, unlike Customer/Referral Partner signup).

**Why:** Decision 007/011 already established Owner/Employee accounts have no OTP-invite path. Since User Management (this module) is the thing that actually provisions Employee `users` records, a decision was needed for how those records get a usable password without an invite flow. Extending `forgot_password`'s active-only check to also accept `pending_password` accounts was considered and rejected — it would have required modifying frozen Auth code. Owner-set initial password requires zero Auth changes: the employee logs in immediately and can change it via the existing self-service `change-password`.

**Impact:** `backend/app/features/employee/schemas.py:CreateEmployeeRequest.initial_password`, `service.py:create_employee`. Frontend: `CreateEmployeePage.tsx` collects it as a plain field (no "generate and email" flow — the Owner sees/sets it directly, same as most admin user-creation forms).

## 018 — Bank account numbers are encrypted at rest; nothing else is (yet)

**Decision:** `Employee.bank_details.account_number` is encrypted via the existing `app.security.encryption` module (Foundation-provided, unmodified) before storage, and only ever returned to the API as a masked last-4-digits string (`account_number_masked`) — never decrypted back out over the API.

**Why:** This is exactly the use case `security/encryption.py`'s docstring anticipated since Foundation ("bank account numbers, PAN, etc.") — the first feature to actually need field-level encryption. PAN/Aadhaar remain uploaded *documents* (S3, per the existing "never store documents in MongoDB" rule), not text fields, so they don't need this treatment.

**Impact:** `backend/app/features/employee/service.py:_encrypt_bank_details_required`, `mask_account_number`; `mappers.py`. Does **not** resolve the known placeholder-key limitation from Foundation (encryption key still derives from `JWT_SECRET_KEY`) — see `docs/KNOWN_LIMITATIONS.md`, now higher-priority since a real sensitive field is actually using it.

## 019 — Departments/Designations/Branches: collections + seed data now, management screens later

**Decision:** `departments`, `designations`, `branches` collections exist now (Employee records reference them), with starter data via `scripts/seed.py` (Loan/Insurance departments, five designations, one Head Office branch) and minimal owner-only list/create API endpoints. No dedicated frontend management screens this module.

**Why:** Per the user's own roadmap change (adding a "Settings (Master Data)" module before Dashboard Framework), these are explicitly slated to get real management UI later. Building throwaway screens now would be rework. The collections have to exist now regardless, since Employee creation requires real `department_id`/`designation_id`/`branch_id` references to validate against.

**Impact:** `backend/app/features/employee/{models,repository,service,router}.py`. See `ai/decisions/2026-07-25-roadmap-settings-before-dashboard.md`.

---

**Freeze (confirmed):** Module 2 (User & Employee Management) is approved and frozen. Do not modify its architecture, database schema, APIs, or business logic unless explicitly approved. Future modules must consume the Employee service instead of directly modifying employee data — Module 3 (Access Control) reads `employees`/`users` to resolve role assignments and adds its own new endpoints under `/employees/{id}/roles`, but does not add, remove, or change any existing Module 2 file.

---

# Module 3 — Role, Permission & Access Control

## 020 — `roles` collection schema completes Foundation's own stated placeholder, doesn't violate it

**Decision:** `scripts/seed.py`'s old `seed_roles()` (writing `{key, label, permissions: []}` documents into `roles`) is replaced with a proper `Role` model (`name`, `description`, `status` + full `BaseDocument` fields) and a real CRUD API. No example role names are seeded — which roles an org wants (Branch Manager, Loan Officer, ...) is business configuration for the Owner to create, not invented here.

**Why:** Foundation's original seed comment said, verbatim, "Full permission sets are assigned when the Access Control module is built — this only ensures the role keys exist." Module 3 *is* that module. The old placeholder shape doesn't match any query this module makes (different field names entirely), so old documents (if any exist in a dev DB) are simply inert, not corrupted or migrated.

**Impact:** `scripts/seed.py`, `backend/app/features/access_control/models.py:Role`. `app/constants/roles.py` (Foundation, frozen) is untouched — that file's `ALL_ROLES` is the four *account* roles (owner/employee/customer/referral_partner), a completely different concept from Access Control's `Role` documents (named permission bundles like "Branch Manager").

## 021 — Permission key shape: (module, resource, action), not Foundation's (feature, action)

**Decision:** `app/features/access_control` defines its own 3-part key concept (module + resource + action) rather than using Foundation's `app/constants/permissions.py:permission_key(feature, action)` 2-part helper. That helper is left untouched and unused.

**Why:** The user's explicit design instruction was module/resource/action-shaped ("Module: loan_management, Resource: leads, Allowed actions: ..."), which doesn't fit Foundation's 2-part format. Extending a frozen Foundation function's signature was rejected in favor of Module 3 owning its own convention entirely — zero Foundation files touched.

**Impact:** `backend/app/features/access_control/models.py:Permission` (module + resource fields, not a single key string).

## 022 — Time windows are a daily recurring window; expiry is lazy, not swept

**Decision:** `TemporaryAccess`/`GeoException`'s 4 time fields (start_date, end_date, start_time, end_time) are interpreted as a **daily recurring** window (e.g. 9am–5pm every day within a date range), not one continuous span. A grant's validity is evaluated at permission-check time (`PermissionEngine._within_daily_window`) — there's no background job flipping a status to "expired"; a grant simply stops passing the check once its window has passed. `status` only ever holds `active`/`revoked`.

**Why:** The brief gave 4 separate fields rather than 2 datetimes, which reads more naturally as a recurring business-hours window than a continuous span — but this is an interpretation of an ambiguous spec, not a confirmed rule (flagged in `docs/KNOWN_LIMITATIONS.md`). Lazy evaluation was chosen over a sweep job because it's simpler, is already fully correct (an expired grant is never usable regardless of whether a job has "noticed" yet), and a scheduled sweep would be the first real Arq job — which belongs to the future Reminder & Notification Engine module, not here.

**Impact:** `backend/app/features/access_control/models.py` (time fields stored as `datetime`/`"HH:MM"` strings — see the BSON date-type note in `docs/database/DATABASE.md`), `permission_engine.py:_within_daily_window`. Overnight windows (e.g. 22:00–06:00) aren't supported — simple string comparison only works same-day.

## 023 — Geo Exception is administrative record-keeping only; no enforcement engine exists

**Decision:** `GeoException` CRUD (create/list/revoke) is built, but nothing in the system actually checks an employee's real-time location against it. There is no geo-fencing *enforcement* mechanism to except from.

**Why:** Geo-fencing's concrete use case (employee attendance? login-location restriction? something else?) was flagged as an open question back in Foundation and was never resolved (`docs/roadmap/TODO.md`). Building enforcement would mean inventing the business rule it's supposed to be an exception to. The data model and admin workflow are built now (matching the brief's explicit ask for this module), ready to plug into real enforcement once that base requirement is confirmed.

**Impact:** `backend/app/features/access_control/models.py:GeoException`. Documented prominently in `docs/KNOWN_LIMITATIONS.md` so this isn't mistaken for working geo-fencing.

## 024 — `PermissionEngine` is new infrastructure; Module 2 is not retrofitted

**Decision:** `has_permission`/`require_permission` (`backend/app/features/access_control/permission_engine.py`) are built and tested, ready for **future** modules to gate their routes with. Module 2's existing endpoints keep their original simple Owner-vs-self check, unchanged.

**Why:** Per the Module 2 freeze ("do not modify its... business logic unless explicitly approved") — swapping Module 2's authorization model would be exactly that kind of change, done here without being asked. Owner bypasses the engine entirely (superuser, consistent with every other module's convention); Customer/Referral Partner are never covered by it (this system is staff-only, matching the entire brief's framing).

**Impact:** `backend/app/features/access_control/permission_engine.py`. Verified directly (not via HTTP, since no consuming endpoint exists yet) in `tests/api/test_access_control.py`.

---

**Freeze (confirmed):** Role, Permission & Access Control is approved and frozen. The user proceeded directly to Module 4 (Settings/Master Data) without requesting changes, confirming completion. Future modules consume `PermissionEngine`/`require_permission` to gate their own routes; they don't modify this module's engine, models, or APIs.

---

# Module 4 — Settings (Master Data)

## 025 — Departments/Designations/Branches: edit/activate/deactivate added via composition, zero lines changed in Module 2

**Decision:** Module 4 adds `PATCH /departments/{id}`, `/activate`, `/deactivate` (and the same for designations/branches) from its own router, calling Module 2's existing `DepartmentRepository`/`DesignationRepository`/`BranchRepository` directly (their inherited `find_by_id`/`update`, already part of `BaseRepository`). `GET`/`POST` for these three resources stay exactly where Module 2 put them — Module 4 never re-registers those paths, avoiding any route collision.

**Why:** Decision 019 explicitly deferred "full CRUD *management screens*" for these three to a future Settings module, anticipating this. The Module 2 freeze forbids modifying its architecture/schema/APIs/business logic — adding new routes from a *different* module's router, calling only already-existing generic repository methods, is the same read+write reuse pattern Module 2 itself used against Auth's `SessionRepository` (decision 015), not a modification.

**Impact:** `backend/app/features/system_settings/{service,router}.py`. Nothing under `app/features/employee/` changed.

## 026 — Every Module 4 route is gated by `require_permission`, not `require_owner`

**Decision:** Every Settings endpoint (read and write) is wrapped in `Depends(require_permission("system_settings", resource, action))`. There's no single `CurrentUserDep` the way Modules 2/3 had — different actions on different resources need different permission checks.

**Why:** `docs/architecture/MODULES.md` already stated the intent: "Settings (Master Data) onward should gate their write endpoints with `require_permission(...)` from Access Control rather than a bespoke role check." Module 4 is the first module built after Access Control, so it's the first real consumer of `PermissionEngine` — resolving the "built but unused" limitation flagged in Module 3's `docs/KNOWN_LIMITATIONS.md`. Owner bypasses the engine entirely (superuser), so behavior is identical to `require_owner` until an Owner actually grants a role permissions here — see the seeded catalog entries this module adds to `scripts/seed.py`.

**Impact:** `backend/app/features/system_settings/router.py`. Gating reads (not just writes) with `require_permission` too was a deliberate simplification — one auth strategy for the whole module rather than mixing `require_permission` for writes and open-to-any-employee for reads.

## 027 — `NamedMasterData` shared base + generic CRUD for the four simplest resources

**Decision:** Lead Sources, Loan Products, Insurance Products, and Document Types are all `name + description + status` — one Pydantic base (`NamedMasterData`), one set of generic service-layer helpers (`_list_named`/`_create_named`/`_update_named`/`_set_status_named`), and one generic frontend component (`NamedMasterDataPage`) serve all four (plus Department/Designation editing, which are the same shape from a different module's collections).

**Why:** Four (six, counting Department/Designation) near-identical copies of the same list/create/edit/activate/deactivate logic is exactly the kind of duplication that drifts and re-introduces the same bug four times over. This is the one deliberate deviation from this project's usual "write it out explicitly per resource" style (visible in Modules 2/3's routers) — justified here because the shape is genuinely identical across a known, immediate set of resources, not a speculative future one.

**Impact:** `backend/app/features/system_settings/{models,service}.py`, `frontend/src/features/system_settings/pages/NamedMasterDataPage.tsx`. Status Masters, Notification Templates, API Settings, and Company Settings have extra fields and got their own dedicated code instead.

## 028 — API Settings config is encrypted as one JSON blob and never returned in plaintext

**Decision:** `ApiSetting.config_encrypted` stores the entire provider config dict (API keys, tokens, sender IDs, ...) as one `encrypt(json.dumps(...))` blob via Foundation's `security/encryption.py` — the same primitive Module 2 first used for bank account numbers (decision 018). Updates merge into the decrypted dict rather than replacing it wholesale, so the Owner can add/rotate one key without resupplying every other secret. API responses only ever expose the configured key *names* (`configured_keys: list[str]`), never values.

**Why:** Provider config shape varies entirely by provider (Meta needs different fields than SMTP) — a single flexible blob avoids hardcoding a schema per provider, consistent with the project's data-driven philosophy. Never echoing secrets back is standard practice for credential-management UI and costs little: the Owner doesn't need to *see* an old API key to rotate it.

**Impact:** `backend/app/features/system_settings/{models,service,mappers}.py`. `POST/PATCH /api-settings` — see `docs/api/API.md`.

## 029 — Status Masters, Notification Templates, and API Settings ship with zero seeded example rows

**Decision:** Unlike Lead Sources/Loan Products/Insurance Products/Document Types (seeded with exactly the literal examples the user named in the brief), `status_masters`, `notification_templates`, and `api_settings` are left empty by `scripts/seed.py`.

**Why:** The user's brief named *categories* for Status Masters (Loan Status/Insurance Status/Customer Status) but no concrete status values, and named *channels* for Notification Templates (SMS/Email/WhatsApp) but no template copy. Inventing specific status pipelines or message content would be exactly the kind of unconfirmed business logic `docs/REQUIREMENTS.md`'s "Open Business-Logic Questions" section already warns against (rejection-branching stages, commission rules, ...) — status *values* are the same category of decision. API Settings has no credentials to seed at all. The Owner defines all three via the real UI this module ships.

**Impact:** `scripts/seed.py:seed_settings_master_data`. Documented in `docs/KNOWN_LIMITATIONS.md` so an empty Status Masters list isn't mistaken for a bug.

## 030 — Company Settings is a singleton located by a unique `singleton_key`, not a well-known ObjectId

**Decision:** `CompanySettings` has exactly one document, found via `find_one({"singleton_key": "default"})` (a unique index) rather than a hardcoded ObjectId. `CompanySettingsRepository.get_or_create()` creates a default row (`company_name="Ashapura Financial Services"`) on first read if none exists yet — `scripts/seed.py` also seeds it, but the service doesn't depend on seed order.

**Why:** A well-known fixed ObjectId would work too but reads oddly in Mongo tooling and couples the schema to a magic constant; a unique marker field on an otherwise-ordinary `BaseDocument` keeps every repository method (`find_by_id`/`update`) working unmodified. This is the project's first singleton-shaped collection — the pattern (marker field + unique index + get-or-create) is reusable for future ones (e.g. a future global notification-settings record).

**Impact:** `backend/app/features/system_settings/{models,repository}.py`.

---

**Freeze (confirmed):** Settings (Master Data) is approved and frozen. Future modules consume its master-data collections (read) and `require_permission("system_settings", ...)` (for anything that needs to *write* Settings data) rather than modifying this module's models, engine, or APIs.

---

## 031 — Unified freeze policy: Foundation through Settings, bug/security fixes only

**Decision:** The user issued a single blanket freeze covering all five completed modules — Foundation, Authentication, User & Employee Management, Access Control, Settings (Master Data) — with this exact rule: *"No architectural modifications. Only Bug Fixes or Security Fixes."* This supersedes the module-by-module freeze notes above with one consistent policy applied uniformly, and is the first time Foundation itself was given an explicit freeze statement (it had only ever been referred to as frozen in passing, e.g. `app/constants/roles.py (Foundation, frozen)`, never formally declared).

**Why:** Five modules now exist and depend on each other in a real dependency chain (Auth → Employee → Access Control → Settings, each consuming the previous one's APIs read-only or read+write per the established reuse pattern). A tightened, explicit rule going forward — "architecture is done, only bugs/security from here" — keeps that chain stable while Dashboard Framework and everything after it is built purely as new, additive modules.

**What counts as in-scope going forward (both remain allowed, unlike architectural changes):**
- **Bug fixes**: incorrect behavior relative to what the module's own docs/decisions say it should do.
- **Security fixes**: e.g. the still-outstanding `ENCRYPTION_KEY`/`JWT_SECRET_KEY` sharing noted in `docs/KNOWN_LIMITATIONS.md` would qualify if addressed later, without needing a fresh "change request."

**What does NOT count** (needs an explicit change request, same as before): new endpoints, schema changes, changing an existing module's authorization model, or repurposing a collection for a new meaning.

**Impact:** No code changed by this decision itself — it's a policy statement. `docs/roadmap/TODO.md`, `docs/architecture/MODULES.md`, and this file's per-module freeze notes above all remain accurate and are not being rewritten; this entry is the single place that states the *combined, current* rule. Module 5 (Dashboard Framework) is built entirely additively per this rule — see its own decisions below for exactly which Foundation-provisioned placeholder files (`AppShell.tsx`, `Sidebar.tsx`, `Topbar.tsx`) it was always intended to complete, as opposed to any file under a frozen module's own feature folder.

---

# Module 5 — Dashboard Framework

## 032 — Widget/nav permission gates reference future modules by naming convention; no code changes needed when they're built

**Decision:** Widgets like `today_leads`, `disbursed`, `revenue` reference `required_module`/`required_resource` values (`leads`, `loan_management`, `reporting`, ...) for modules that don't exist yet — no permission-catalog entry backs them today. `PermissionEngine.has_permission` already returns `False` for a module/resource with no catalog entry (Module 3 behavior, unchanged), so these widgets are simply invisible to every Employee until the owning module is built and seeds its own catalog entry — and instantly, correctly grantable the moment it does, no Dashboard code change required. Verified directly: `tests/api/test_dashboard.py::test_widget_for_unbuilt_module_becomes_grantable_once_catalog_entry_exists` creates a `leads:leads:view` permission by hand and confirms the `today_leads` widget becomes visible.

**Why:** This is the same forward-compatible, data-driven design the whole permission system was built for (decision 021) — Dashboard is simply the first consumer to lean on it for content that doesn't exist yet, not just actions on content that does.

**Impact:** `scripts/seed.py:seed_dashboard_catalog`. Owner always sees every widget regardless (bypasses `PermissionEngine` entirely, per every prior module's convention).

## 033 — Nav item gating mirrors how the target route is ACTUALLY protected, not a generic permission check

**Decision:** `NavItem.owner_only` is a separate, simpler gate alongside the `required_module`/`resource`/`action` one. The seeded catalog uses `owner_only=True` for "Employees" and "Roles & Permissions" (their underlying routes are `require_owner`-gated, decisions from Modules 2/3 — Module 2 was deliberately never retrofitted to `require_permission`, decision 024) and `required_module="system_settings"` for "Settings" (its routes genuinely are `require_permission`-gated, Module 4).

**Why:** Caught during design, not after: gating the "Employees" nav item purely by a `employee_management:employee_records:view` permission grant would have been actively misleading — an Employee could be granted that permission (the catalog entry already exists, seeded by Module 3), see the nav item, click it, and get a 403 anyway, because Module 2's actual endpoints don't check that permission at all. The nav item's visibility has to match the real authorization the linked page/API enforces, not an aspirational one.

**Impact:** `backend/app/features/dashboard/models.py:NavItem`, `scripts/seed.py:seed_dashboard_catalog`. Worth re-checking this mapping any time a module's own authorization model changes.

## 034 — Real server-side logout wired into Profile Menu without touching any frozen Auth file

**Decision:** `ProfileMenu`'s Logout button calls the existing `POST /auth/logout` (Module 1, unmodified) with the refresh token read from `localStorage`, then clears client session state — a real capability that never had frontend UI before (`docs/api/API.md` always documented the endpoint; nothing called it). Since `features/auth/context.tsx`'s `REFRESH_TOKEN_STORAGE_KEY` constant isn't exported, the key string is duplicated in `ProfileMenu.tsx` with a comment pointing back to the source of truth, rather than exporting it from (i.e., editing) a frozen Auth file for one constant.

**Why:** Session hygiene is a legitimate security-adjacent concern (an unrevoked refresh token left active after a user believes they've logged out) — allowed under the freeze policy (decision 031) as a fix rather than an architectural change, and implemented entirely from Dashboard's own new file consuming an existing, untouched public API.

**Impact:** `frontend/src/features/dashboard/components/ProfileMenu.tsx`. Zero lines changed under `frontend/src/features/auth/`.

## 035 — `AppShell` wraps every authenticated route via `<Outlet/>`; existing pages are not rewritten

**Decision:** `AppShell` (Sidebar + Topbar + `<Outlet/>`) now wraps the entire authenticated route tree in `router.tsx`. Modules 2–4's pages keep using `SimplePageLayout` for their own header exactly as built — nesting them inside `AppShell` means two header-ish rows stack (Topbar, then each page's own `SimplePageLayout` title bar), a minor visual redundancy accepted rather than editing any frozen page component to remove its own header now that Topbar exists.

**Why:** `SimplePageLayout`'s own docstring anticipated this: "deliberately NOT the sidebar shell... since building that out is Dashboard Framework's job." Building the real shell without ever routing anything through it would leave Sidebar/Topbar theoretical. Routing every authenticated page through it, while leaving each page's own content/header untouched, delivers a working shell with zero risk to already-verified pages.

**Impact:** `frontend/src/app/router.tsx`, `frontend/src/components/layout/{AppShell,Sidebar,Topbar}.tsx`. The root `/` route also changes meaning: previously a public, unauthenticated placeholder (`AppShell` rendered standalone, outside `RequireAuth`) that no other module ever linked to; now the authenticated Dashboard home page (`index: true` under `AppShell`), gated the same as every other route in that tree.

## 036 — Refresh Interval is one shared poll at the shortest visible widget's interval, not N independent loops

**Decision:** `GET /dashboard` returns every visible widget's data in one response. The frontend computes `min(refresh_interval_seconds)` across currently-visible widgets (floored at 30s) and refetches the whole dashboard on that one timer, rather than running a separate polling loop per widget that would each re-fetch (and the backend re-compute) the same combined payload independently.

**Why:** Per-widget refresh interval is one of the four explicitly-requested configurable behaviors (Hide/Show, Order, Refresh Interval) and needed to be genuinely functional, not just a stored-but-unused number (the trap Module 4's Company Settings theme fields fell into, decision noted in `docs/KNOWN_LIMITATIONS.md`). Since one endpoint already returns everything together, N independent timers would add real complexity (and N redundant network round-trips) for a behavior indistinguishable from one shared timer at the tightest configured interval.

**Impact:** `frontend/src/features/dashboard/pages/DashboardPage.tsx`. A widget set to a very short interval (e.g. 30s) does make the *entire* dashboard refresh that often, not just itself — a reasonable, documented simplification, not a bug.

## 037 — Widget/NavItem catalogs are seeded once, not Owner-CRUD-able

**Decision:** Unlike Access Control's `Permission` catalog (Owner-creatable via `POST /permissions`, decision 021) or Settings' master-data resources (full Owner CRUD, Module 4), `DashboardWidget` and `NavItem` have no create/update endpoints at all — `scripts/seed.py:seed_dashboard_catalog` is their only writer. What IS Owner/Employee-editable is `DashboardLayoutPreference` (per-user visibility/order/refresh-interval, via `PUT /dashboard/layout`).

**Why:** A `Permission` catalog entry is pure metadata (module+resource+actions) — creating one via the API is immediately meaningful. A `DashboardWidget` entry is not: it names a `key` that must already have a matching function in `widget_providers.py:WIDGET_PROVIDERS`, or a `NavItem` that must point at a route that actually exists. Letting an Owner "create" one via API would produce a widget that always resolves to the not-yet-available placeholder, or a nav link to a 404 — a dead-end feature, not real configurability. The genuinely configurable part of the brief (hide/show, order, refresh interval) got a real, unrestricted-shape API instead.

**Impact:** `backend/app/features/dashboard/{router,service}.py` — no catalog-mutation endpoints exist. Documented in `docs/KNOWN_LIMITATIONS.md` so this isn't mistaken for an oversight.

## 038 — Three widgets are real (Recent Activities, Department Summary, Employee Summary); the other ten are honest placeholders

**Decision:** `widget_providers.py` computes genuine values for `recent_activities` (reads the shared `audit_logs` collection, Owner sees system-wide activity, an Employee only ever sees their own regardless of what's granted — a distinct, more sensitive concern than "can see the widget exists"), `department_summary` and `employee_summary` (both read Module 2's `employees`/`departments` collections directly, read-only). The other ten widgets (`today_leads`, `pending_followups`, `pending_documents`, `assigned_leads`, `disbursed`, `rejected`, `revenue`, `tasks`, `notifications`, `referral_summary`) always return `{"available": false, "value": 0}` / `{"available": false, "items": []}` — never a fabricated number — because their owning modules (Leads, Loan/Insurance Management, Document Management, Reminders, Notification Management, Referral Partner) don't exist yet.

**Why:** Same discipline as decision 029 (Settings shipping Status Masters/Notification Templates empty rather than inventing content) applied to computed data instead of seeded rows: showing "0" indistinguishably from a real zero-count would be misleading, so every placeholder widget carries an explicit `available: false` the frontend renders as "Not available yet" rather than a number.

**Impact:** `backend/app/features/dashboard/widget_providers.py`. Recent Activities' Owner-vs-Employee scoping is enforced in the provider itself, not just at the nav/widget-visibility permission gate — even a future, deliberately-broad `audit:activity_logs:view` grant to an Employee would still only surface their own activity.

---

**Freeze (confirmed):** Dashboard Framework is approved and frozen. Future modules (Lead Management onward) consume its nav/widget catalogs (adding their own rows via their own seed step, per decision 032/037) and `require_permission(...)` for their own routes, rather than modifying this module's engine, models, or APIs.

---

## 039 — Freeze policy reconfirmed to include Dashboard Framework

**Decision:** The user reissued the blanket freeze (decision 031), this time explicitly naming all six completed modules — Foundation, Authentication, User & Employee Management, Access Control, Settings, **and Dashboard Framework**. Same rule: *"No modifications"* (a slightly tightened restatement of decision 031's "no architectural modifications, only bug fixes or security fixes" — read as the same policy, not a stricter new one, since the user's Module 6 instructions immediately afterward explicitly rely on modules built after Dashboard being able to *wire their own widgets into it*, which decision 038's freeze note already anticipated as the sanctioned "future modules add their own nav item + wire any relevant widget" carve-out).

**Why:** Six modules now form the stable base the rest of the CRM builds on. Reconfirming the freeze at the start of "the heart of the CRM" (Module 6, Lead Management, explicitly flagged by the user as likely the largest module) sets the same expectation as every prior freeze: architecture in these six is done, only bugs/security from here.

**Impact:** No code changed by this decision itself. Module 6A (Lead Foundation) goes on to wire two previously-placeholder Dashboard widgets (`today_leads`, `assigned_leads`) to real data by editing `backend/app/features/dashboard/widget_providers.py` — this is the exact, pre-authorized "future module wires its own widget" pattern from decision 038, not a freeze violation. `pending_followups` deliberately stays a placeholder — it needs a follow-up/reminder date concept that doesn't exist until Module 6D. No other Dashboard file changes.

---

# Module 6A — Lead Foundation

Per the user's explicit instruction, Module 6 (Lead Management — "the heart of the CRM", likely the largest module) is split into four sub-modules built and verified one at a time: 6A Lead Foundation, 6B Customer Application Flow, 6C Loan & Insurance Pipeline, 6D Re-Eligible & Reminder Engine. This section covers 6A only.

## 040 — A Lead carries its own contact info; no Customer record exists yet to link to

**Decision:** `Lead` stores `full_name`/`mobile`/`email` directly rather than referencing a `customers` collection. `Customer` (`features/customer/`) is still scaffolded/empty — the "Customer Portal connection" step that would create a real Customer record is explicitly Module 6B's job, not 6A's.

**Why:** The brief itself splits this way — 6A's own scope list is "Lead entity, Lead CRUD... Duplicate Detection" with no "Customer Creation" bullet (that's 6B: "Secure Link, Customer Portal connection, Form completion..."). Duplicate detection in particular needs raw contact info to compare against *before* any conversion happens, so the Lead has to carry it itself.

**Impact:** `backend/app/features/leads/models.py:Lead`. When 6B builds the real conversion flow, it will need to copy `full_name`/`mobile`/`email` onto a new `Customer` document — not a foreign key, since a Lead may never convert.

## 041 — Duplicate detection flags, never blocks

**Decision:** Creating a Lead with a `mobile` that matches an existing, non-deleted Lead always succeeds — the new Lead is created with `duplicate_of_lead_ids` populated (every prior match, not just the most recent) and a `duplicate_detected` activity logged. A standalone `GET /leads/check-duplicate?mobile=` endpoint lets the frontend warn *before* submission.

**Why:** The brief says "Duplicate Detection," not "Duplicate Prevention" — blocking creation outright risks silently dropping a genuine second inquiry (a returning customer, a different product interest, a data-entry correction attempt) with no record it ever happened. Flagging for staff review is the safer default for inbound lead capture; nothing here rules out adding a harder block later if that turns out to be wanted.

**Impact:** `backend/app/features/leads/{models,service}.py`. Matching is on `mobile` only (not mobile+product) — a person inquiring about both a loan and insurance separately still gets flagged, which is an assumption worth confirming, not a considered product decision; see `docs/KNOWN_LIMITATIONS.md`.

## 042 — Timeline = merged Activities + Notes, lead-scoped, not the shared future Timeline module

**Decision:** `LeadActivity` (system-logged: created/updated/assigned/unassigned/note_added/duplicate_detected) and `LeadNote` (user-authored free text) are two small collections scoped to `leads/`, merged and sorted by `created_at` in `GET /leads/{id}/timeline`. The reserved, cross-entity `features/timeline` module (`docs/architecture/MODULES.md`) stays untouched and scaffolded.

**Why:** The brief listed Timeline/Notes/Activities as three separate bullets under 6A's own scope, not under the still-unbuilt generic Timeline module — building the narrow, lead-specific version now (matching the project's established pattern of narrow-then-generic, e.g. Module 2's `employee_documents` predating any generic Document Management) satisfies the actual ask without reaching into a module that isn't scoped for this pass.

**Impact:** `backend/app/features/leads/{models,repository,service,mappers}.py`. Every mutating Lead action also writes to the shared `audit_logs` collection (`write_audit_log`, prefixed `lead_*`) in addition to `LeadActivity` — consistent with every prior module, and it's what feeds Dashboard's Recent Activities widget for Lead events too.

## 043 — No public/unauthenticated lead-capture endpoint this round

**Decision:** The only way to create a Lead is the authenticated `POST /leads` (Owner or a permitted Employee). "Website Leads"/"Meta Leads" are recorded via `source_id` (reusing Module 4's already-seeded `lead_sources`: Website, Meta, Manual, Referral, Walk-in) describing *where* a lead came from, not via an actual inbound webhook that auto-creates one.

**Why:** Real Website-form or Meta Lead Ads ingestion is integration work (a public endpoint, webhook signature verification, mapping external payloads) that belongs to the still-scaffolded Integrations module, not Lead Foundation. Inventing a public endpoint now would mean guessing at a contract with an external system nobody has configured yet.

**Impact:** None — `source_id` already covers the "record where it came from" need; the "actually receive it automatically" need is deferred and flagged in `docs/KNOWN_LIMITATIONS.md`.

## 044 — Dashboard's `today_leads`/`assigned_leads` widgets wired to real data; `pending_followups` stays a placeholder

**Decision:** `widget_providers.py` gains `_today_leads` (count of Leads created since UTC midnight) and `_assigned_leads` (Owner: every assigned Lead company-wide; Employee: only Leads assigned to them, resolved via their own Employee record — the same Owner-vs-Employee scoping convention as Recent Activities, decision 038). `pending_followups` is left as `_not_yet_available` — it needs a follow-up/reminder date field that doesn't exist on `Lead` and won't until Module 6D.

**Why:** This is the sanctioned "future module wires its own widget" pattern from decision 038/039 — Dashboard's engine and catalog are untouched, only two provider functions are added. Verified end-to-end in `tests/api/test_leads.py::test_dashboard_today_leads_and_assigned_leads_widgets_reflect_real_data`, not just unit-tested in isolation.

**Impact:** `backend/app/features/dashboard/widget_providers.py`. `scripts/seed.py` gains a `leads:leads` permission-catalog entry (the exact module/resource these widgets already referenced) and a `leads` nav item — added via 6A's own new seed functions, not by editing Module 5's `seed_dashboard_catalog`.

## 045 — Lead read/write is gated entirely by `leads:leads`; Source/Product dropdowns depend on Settings' own permissions

**Decision:** Every `/leads*` endpoint (reads included) requires `require_permission("leads", "leads", action)`. The Create/Edit Lead frontend forms populate their Source/Product dropdowns by calling Module 4's own `GET /lead-sources`, `/loan-products`, `/insurance-products` — each gated by *its own* `system_settings:*` permission, not bundled with `leads:leads`.

**Why:** Consistent with every permission in this system being narrowly scoped to one resource (decision 021) — bundling Settings' read access into the Leads permission would be a special case with no precedent. The consequence is real: an Owner must grant both `leads:leads` (create/edit) *and* the relevant `system_settings:lead_sources`/`loan_products`/`insurance_products` (view) for an Employee's Create Lead form to fully work — documented as a known limitation rather than silently worked around.

**Impact:** `backend/app/features/leads/router.py`, `frontend/src/features/leads/pages/CreateLeadPage.tsx`. Not fixed with a bundled permission or a backend proxy — both would be new precedent-setting mechanisms for one form's convenience.

---

**Freeze (confirmed):** Lead Foundation (Module 6A) is approved and frozen. Module 6B (Customer Application Flow) builds on top of it — converting a Lead, not modifying this sub-module's models, engine, or APIs.

---

# Module 6B — Customer Onboarding & Application Flow

Preceded by the user reconfirming the blanket freeze across all seven completed modules (Foundation through Lead Foundation) before handing over 6B, and by an explicit refinement to the brief's own conversion-timing sentence (adopted verbatim into decision 047 below): Lead-originated applications convert their Lead into a Customer *at submission*; direct-portal applications create the Customer *at registration*, then the Application itself is the "internal record for processing."

## 046 — Both onboarding flows reuse Auth's invitation-only signup unmodified; zero lines changed under `app/features/auth/`

**Decision:** Neither flow calls `POST /auth/send-otp` directly (it requires an authenticated Owner/Employee caller — decision 011). Instead, Module 6B's own service calls `AuthService.send_otp(mobile=..., role=CUSTOMER, inviter=<resolved User>)` directly:
- **Flow 1 (secure link):** `inviter` is the actual Owner/Employee who generated the link (`SecureLink.created_by`, looked up as a `User`) — a real, already-authenticated staff action, just resolved asynchronously once the customer clicks through later.
- **Flow 2 (direct portal):** there is no human inviter at all — `inviter` is any seeded Owner account (`_any_owner()`), standing in as the technical authority that operates the public portal.

Everything downstream — OTP verification, password creation, login — calls Auth's existing public `/auth/verify-otp`, `/auth/reset-password`, `/auth/login` endpoints exactly as built, with zero new wrapper endpoints needed (they were already public).

**Why:** The instruction was explicit: "Authentication must reuse Module 1. Do not modify Authentication." `AuthService.send_otp` already takes `inviter: User` as a plain parameter (not hardcoded to the HTTP layer's authenticated caller) — Module 6B supplies a different, still-legitimate `User` for each flow rather than relaxing Auth's invitation requirement. This is the same "compose from the new module's own service layer" pattern used since Module 2 reused `AuthService.forgot_password()`.

**Impact:** `backend/app/features/customer/service.py:generate_secure_link/start_signup_from_secure_link/start_direct_registration`. `frontend/src/features/customer/pages/{RegisterPage,SecureLinkLandingPage}.tsx` hand off to Auth's existing, unmodified `/verify-otp` and `/reset-password` pages via `react-router` state — no Auth frontend file touched either. A pending secure-link token survives that detour via a `sessionStorage` bridge (`SecureLinkLandingPage.tsx`'s `PENDING_SECURE_LINK_KEY`, resumed by `app/HomeRedirect.tsx`), since Auth's pages can't be taught to carry it through their own state without editing them.

## 047 — Personal/Contact/Address/KYC lives on a fixed-schema Customer profile, not the dynamic form; collected at different points per flow

**Decision:** `ApplicationFormDefinition.fields` holds product-specific fields *only* (loan amount, sum insured, ...) — never personal/contact/address/KYC. Those live on `Customer`, filled in via a fixed (non-dynamic) schema, at two different points depending on flow:
- **Flow 2:** `POST /customers/me` (`CompleteProfileRequest`) right after registration — the Customer row is created immediately, before any product is even chosen.
- **Flow 1:** no Customer row exists yet when the application opens (per the user's own refinement — "convert that Lead into a Customer after the application is successfully submitted"). Personal/contact/KYC fields are collected inline as part of completing the application (`Application.pending_profile`) and only turned into a real `Customer` row at submission, alongside the Lead conversion.

**Why:** The brief's flow diagrams show Flow 1 going straight from "Create Account" to "Application opens directly" — no separate profile step — while Flow 2 explicitly creates the Customer before product selection. Reading personal/KYC fields as *always* part of one dynamic form would have blurred a distinction the user asked to keep sharp ("Lead, Customer, and Application... clear for future modules"). The two flows still "merge into the exact same application workflow after the form opens" as instructed — only the pre-form-opening path (and where profile data is collected) legitimately differs.

**Impact:** `backend/app/features/customer/{models,schemas,service}.py` (`Application.pending_profile`, `SubmitApplicationRequest.profile`). `frontend/.../CompleteProfilePage.tsx` (Flow 2 only) vs. `ApplicationPage.tsx`'s inline "Your Details" section (shown only when `customer_id` is still null).

**Superseded (2026-07-31):** the user rejected keeping two different profile-collection
paths ("that creates two different onboarding paths that you'll maintain forever... every
customer completes the same profile step before entering any application"). `/portal/profile/setup`
(`CompleteProfilePage.tsx`) is now the single, shared profile-completion step for both flows,
reached right after authentication and before the customer ever opens their application.
`CustomerService.complete_profile` now resolves any pending Flow-1 application for the
authenticated user (`ApplicationRepository.find_pending_conversion_for_user`) and both sets
`converted_from_lead_id` and links `Application.customer_id` immediately, instead of waiting
for submission. `submit_application`'s original conversion branch (`_create_customer_from_profile`
called with `payload.profile` if `customer_id` is still null) is kept as a defensive fallback
only — not expected to fire for any application created after this change, but left in place
for whatever was already in flight. `ApplicationPage.tsx`'s inline "Your Details" card is,
likewise, now a legacy fallback rather than the primary Flow-1 UX.

## 048 — `Customer.converted_from_lead_id` is the one reverse-pointer; Module 6A's `Lead` is not modified

**Decision:** Nothing is added to `Lead` (status value, new field, or otherwise) to mark it "converted." Instead, `Customer` (Module 6B's own new model) carries `converted_from_lead_id: str | None`. "Is this lead already converted" is answered by querying `customers` for that value, not by inspecting the Lead itself.

**Why:** Module 6A is frozen — no architectural changes, including schema additions, without explicit approval. A reverse-pointer on the *new* module's own collection achieves the same lookup capability (and blocks generating a second secure link for an already-converted lead — enforced in `generate_secure_link`) without touching a single frozen file.

**Impact:** `backend/app/features/customer/models.py:Customer`, `repository.py:CustomerRepository.find_by_lead_id`. Consequence: the Lead List/Details pages (Module 6A, also frozen) show no visual "converted" badge — checking requires knowing to look at the Customer side. Documented in `docs/KNOWN_LIMITATIONS.md`.

## 049 — Direct portal registration's technical inviter is any seeded Owner account — **corrected by decision 053**

**Decision (original, as first shipped):** `_any_owner()` looks up any `role="owner"` user and uses it as the `inviter` argument for Flow 2's `AuthService.send_otp` call. Which Owner (if more than one exists) is an implementation detail, not a business decision — it never appears anywhere the Owner or Customer would see it.

**Why:** Flow 2 has no human staff member inviting a specific mobile number — the closest real-world analogue is "the business itself (the Owner) operates a public application portal and implicitly authorizes anyone who applies through it." This is the one place in the whole reuse strategy that required judgment rather than a mechanical read of the brief; flagged prominently here and in `docs/KNOWN_LIMITATIONS.md` rather than buried in a code comment.

**Impact:** `backend/app/features/customer/service.py:_any_owner`. If zero Owner accounts exist (shouldn't happen given the bootstrap-Owner seed step, Module 1), registration fails with a clear `validation_error` rather than a confusing 500.

**Correction:** During Module 6B's business review, the user rejected the implicit-attribution reading above: "A customer registering directly should not be linked to any owner or employee at registration time." `_any_owner()` is kept *only* as the technical value needed to satisfy Auth's frozen `send_otp(inviter: User)` signature (decision 011) — it is no longer allowed to persist as attribution. See decision 053.

## 050 — Staff (Owner + Employee) visibility for Customers/Applications uses plain role checks, not `require_permission`

**Decision:** `GET /customers`, `GET /customers/{id}`, `GET /applications`, `GET /applications/{id}`, `GET /applications/{id}/documents` require only `require_staff` (Owner or Employee, no Access Control grant needed). `POST /applications/{id}/assign` requires `require_owner`. An Employee's results are hard-scoped to applications/customers assigned to them *in the service layer*, unconditionally — not as a Permission Matrix grant.

**Why:** Every prior module built after Access Control (Settings, Dashboard, Leads) used `require_permission` because the brief implied real delegation (an Owner choosing *which* Employees get *which* access). Here, the brief frames Employee visibility as inherent ("View Assigned Customers/Applications") and Owner-only actions as exclusive ("Assign Employee" appears only under Owner's capability list, never Employee's) — there is no delegation to model. Adding `require_permission` gates that Owner always bypasses and Employee's own hard-coded scoping already makes irrelevant would be ceremony, not real flexibility — the same reasoning Module 2 used to justify never adopting `PermissionEngine` at all (decision 024).

**Impact:** `backend/app/features/customer/dependencies.py`. No `customers`-module permission-catalog entries were seeded — there's nothing meaningful for an Owner to grant here.

## 051 — Application form definitions are seeded, illustrative, and not Owner-manageable in this module — **explicitly marked temporary by the user, not frozen architecture**

**Decision:** `scripts/seed.py:seed_customer_form_definitions` seeds one `ApplicationFormDefinition` per already-seeded Loan/Insurance product (Personal/Business/Property Loan, Life, Health) with a plausible, generic field list (loan amount, tenure, sum insured, nominee, ...) and required-document references into Module 4's `document_types`. No API exists for an Owner to create or edit these.

**Why:** The brief's own Owner-capability list for 6B is exhaustive and explicitly excludes form authoring ("View Customers, View Customer Applications, Search, Filter, Assign Employee, View Documents. Nothing more."). Seeding *some* real fields (rather than shipping every form empty, the way Module 4 handled Status Masters/Notification Templates, decision 029) was necessary here because an application form with zero fields would make the module's central deliverable — "the dynamic form engine actually renders and validates a real form" — unverifiable end-to-end. The field choices themselves are generic/illustrative, not asserted as Ashapura's actual required fields.

**Impact:** `scripts/seed.py`, `backend/app/features/customer/models.py:ApplicationFormDefinition`. Flagged in `docs/KNOWN_LIMITATIONS.md` so these aren't mistaken for confirmed business requirements. A future Owner-facing form-builder UI (if ever wanted) is out of scope here and would be a new, explicitly-requested capability, not an oversight.

**Clarification (user, at 6B approval):** "Treat the seeded form definitions as temporary development data. They are not part of the frozen architecture and will be replaced with Ashapura-approved field definitions later without changing the form engine." Accordingly, the *engine* (`ApplicationFormDefinition`/`FormFieldDefinition` schema, the render/validate code path in `service.py`/`ApplicationPage.tsx`) is part of Module 6B's frozen surface as normal — but the specific seeded rows in `scripts/seed.py:seed_customer_form_definitions` are development fixtures, exempt from the freeze policy, and expected to be replaced by real Ashapura-supplied Personal/Business/Home Loan and Health/Life Insurance field definitions in a later data-only change (re-seeding or an admin edit), not a code change.

## 052 — "Generate Secure Link" has no entry point on Module 6A's Lead Details page — **resolved by decision 053 as an approved UX exception**

**Decision (original, as first shipped):** `GenerateSecureLinkPage` (`/leads/{id}/secure-link`) exists as a standalone route with no link pointing to it from `LeadDetailsPage.tsx` — reachable only by typing the URL (appending `/secure-link` to a Lead's own detail URL, which *is* still visible).

**Why:** `LeadDetailsPage.tsx` belongs to frozen Module 6A. Adding a button to it is a new capability, not a bug fix or security fix — outside what the freeze policy (decision 031/039) allows without explicit approval. This is the same judgment call as Module 6A's own decision 045 (Create Lead's dropdowns depending on a separate permission) and Module 4's undiscovered Employee CSV export bug: an honest, documented UX gap rather than a quiet freeze violation.

**Impact (original):** `frontend/src/features/customer/pages/GenerateSecureLinkPage.tsx`, `frontend/src/app/router.tsx`. Documented in `docs/KNOWN_LIMITATIONS.md`.

**Resolution:** The user reviewed this exact gap and approved closing it explicitly under the freeze policy's UX-enhancement exception (no database, API, or business-logic change): "Add a 'Generate Secure Link' action to Lead Details using the existing API. Do not change the Lead architecture or business rules." A single `<Link to={`/leads/{id}/secure-link`}>` action was added to `LeadDetailsPage.tsx`'s header actions — no other line in that file, no backend route, and no API contract changed. See decision 053.

## 053 — Direct-registration attribution fix and the "Unassigned Applications" queue

**Decision:** Two corrections adopted verbatim from the user's post-6B business review, both scoped as business-rule refinements rather than architectural changes:

1. **No artificial ownership at registration.** `CustomerService.start_direct_registration` still calls `_any_owner()` to obtain a real `User` satisfying Auth's frozen `send_otp(inviter: User)` signature (decision 011 — unchanged, unmodifiable), but immediately after `send_otp` returns, it looks up the newly-created pending `User` row by mobile and resets `created_by` to `None` — matching `BaseDocument`'s own documented convention for "system-created, no human attribution," rather than leaving it pointing at the technical Owner. A direct-portal Customer is therefore not attributed to any Owner or Employee anywhere in its own or its User row's data.
2. **"Unassigned Applications" queue.** `Application.assigned_to` already defaulted to `None`; what was missing was a way to *query* for exactly that. Added `unassigned_only: bool` threaded through `GET /applications` → `CustomerService.list_applications_for_staff` → `ApplicationRepository.search_and_filter`, implemented as an explicit `{"assigned_to": None}` match that takes precedence over any `assigned_to` filter. Force-disabled for Employee actors in the service layer (their `assigned_to` is always hard-scoped to themselves regardless of what the request sends) — the queue is conceptually Owner-only, since work assigned to nobody isn't an Employee's to see. The Owner Dashboard/Applications list surfaces this via a checkbox visible only to the `owner` role.

**Why:** The user's own stated workflow — "Customer Registration → Customer Account Created → Application Submitted → Application enters 'Unassigned' queue → Owner Dashboard → Owner assigns Employee → Processing starts" — treats registration and assignment as two separate, sequential business events. The originally-shipped design (decision 049) conflated them by using a real Owner id as a stand-in for "no owner," which risked reading as actual attribution even though never surfaced in any UI. Both fixes are data/query-level corrections to Module 6B's own code (`customer/service.py`, `customer/repository.py`, `customer/router.py`) — nothing in Auth, Lead, or any other frozen module changed.

**Impact:** `backend/app/features/customer/service.py` (`start_direct_registration`, `list_applications_for_staff`), `repository.py` (`ApplicationRepository.search_and_filter`), `router.py` (`GET /applications` gains `unassigned_only`). `frontend/src/features/customer/api.ts` (`listApplicationsStaff` param), `StaffApplicationListPage.tsx` (Owner-only "Unassigned Applications only" checkbox). Tests: `tests/api/test_customer.py::test_direct_registration_is_not_attributed_to_a_seeded_owner`, `::test_unassigned_applications_queue_is_owner_only`. The `OTP_SENT` audit-log entry for direct registration still names the technical Owner as `user_id` — `audit_logs` is intentionally append-only (`shared/audit_log.py`) with no update path, so this one field cannot be corrected after the fact; noted as a residual, accepted limitation in `docs/KNOWN_LIMITATIONS.md`, not a bug.

---

**Freeze (reconfirmed):** Customer Onboarding & Application Flow (Module 6B) is approved and frozen, incorporating the three business-rule refinements above (decisions 049's correction, 051's temporary-data clarification, 052's resolution) plus the new decision 053. Module 6C (Loan & Insurance Pipeline) builds the real status engine on top of `Application`/`ApplicationDocument` rather than modifying this sub-module's models, engine, or APIs. Per the user's explicit instruction, Module 6C implementation does not begin until the separate Module 6C Workflow Proposal (no code) is reviewed and approved.

# Module 6C — Loan & Insurance Processing Pipeline

Implemented after the user reviewed `docs/MODULE_6C_WORKFLOW_PROPOSAL.md` and resolved its open questions: unified `application_workflows` collection (not split loan/insurance collections), two rejection exit points per pipeline, no rollback in v1, and Access Control's real `require_permission` gating. The Insurance lifecycle's exact stages were left to be amended by the user but no replacement sequence was subsequently provided, so the proposal's own draft lifecycle was adopted as-is and is flagged below as an assumption, not a confirmed decision.

## 054 — One unified `application_workflows` collection for both Loan and Insurance, not two separate case collections

**Decision:** A single collection, discriminated by `case_type` ("loan"/"insurance"), holds every case — `ApplicationWorkflow` (`backend/app/features/workflow_engine/models.py`) carries the fields common to any case (status, assignment, pending documents, rejection reason) plus two optional, strongly-typed sub-documents, `loan_details`/`insurance_details`, populated according to `case_type`.

**Why:** User's explicit choice, presented as an option against a split-collection alternative during the pre-implementation clarification round. Matches the collection names given in the brief itself (`application_workflows`, `application_status_history`, `application_notes`, `application_decisions` — all case-type-agnostic names) and extends the "engine is code, catalog is data" pattern one step further than 6B's Dynamic Form Engine: here even the *record* itself is shared, not just the transition rules.

**Impact:** `backend/app/features/workflow_engine/models.py`, `repository.py`, `engine.py` own the shared model/collection/generic transition logic; `loan_management`/`insurance_management` each own only their own sub-document type, service logic, and routes. A future third case type (e.g. a Gold Loan or BNPL pipeline with genuinely different needs) is a new `case_type` value plus a new optional `*_details` sub-document, not a new collection.

## 055 — Two rejection exit points per pipeline (not one)

**Decision:** Loan: `credit_evaluation` and `final_evaluation` can both transition directly to `rejected`. Insurance: `underwriting` and `medical_examination` can both transition directly to `rejected`. Every other status has exactly one allowed next status (or two non-rejection choices, for `underwriting`'s conditional medical-exam branch).

**Why:** User's explicit choice against the alternative (a single exit point matching the brief's example sequence literally) — closer to real-world processing, where a clearly bad case is rejected early rather than run through every remaining stage first.

**Impact:** `scripts/seed.py:seed_workflow_definitions` (`allowed_next_statuses` per status), `LoanCaseService.credit_evaluation`/`.final_evaluation`, `InsuranceCaseService.underwriting`/`.medical_examination` — each accepts a `decision: approved|rejected` and requires a mandatory `rejection_reason` when rejecting (business rule, enforced as `ValidationError` if omitted).

## 056 — No rollback in v1; `allowed_previous_statuses` is reserved, always empty

**Decision:** `WorkflowDefinition.allowed_previous_statuses` exists on every row (satisfying the brief's own "Allowed Previous Status (if rollback is permitted)" field requirement) but is populated as `[]` for every status in both pipelines. A case can only ever move forward or into `rejected` — never backward.

**Why:** User's explicit choice, against defining specific rollback paths (e.g. a failed Final Evaluation reopening Credit Evaluation). Matches the brief's own linear diagrammed sequence; keeps the generic engine's `transition()` validation simple (only `allowed_next_statuses` is actually consulted this round).

**Impact:** `backend/app/features/workflow_engine/models.py:WorkflowDefinition.allowed_previous_statuses`, `engine.py` (never reads this field yet). A future rollback feature is additive: populate the field per status and add the corresponding check to `assert_transition_allowed` — no schema change needed.

## 057 — Insurance lifecycle stages — **superseded by decision 064's finalized lifecycle**

**Decision (original draft, as first implemented):** New Customer → Documents Pending → Underwriting → Medical Examination (conditional, a per-case underwriter judgment recorded during Underwriting, not a fixed product attribute) → Premium Acceptance → Policy Issuance → Active, with Rejected reachable from Underwriting or Medical Examination.

**Why:** The brief only said Insurance needed "a separate lifecycle... because insurance processing differs from loans" without dictating exact stages (unlike Loan, whose sequence was given verbatim). The user was asked to confirm or amend this proposal's own draft lifecycle and chose to amend it, but no replacement sequence followed before implementation proceeded. Per the instruction to still move forward once clarified where possible, the original draft was implemented as-is — **explicitly flagged as an assumption requiring the user's confirmation, not asserted as approved business logic.**

**Impact (original):** `scripts/seed.py:seed_workflow_definitions` (insurance rows), `InsuranceStatus` (`workflow_engine/constants.py`), `InsuranceCaseService`. Because the *engine* is generic and the stages are seeded data, amending this lifecycle later (renaming/reordering/adding stages) is a data change to `workflow_definitions`, not a code change.

**Resolution:** The user reviewed this exact draft and replaced it with a corrected, final sequence — see decision 064. The prediction above (amending is a low-cost data change, not a code change) held: the finalization touched `workflow_definitions` seed rows and `InsuranceCaseDetails`/`InsuranceStatus` field/status renames, but no change to the generic `WorkflowEngine` itself.

## 058 — Case creation is a lazy get-or-create, not a live hook into Module 6B's frozen `submit_application`

**Decision:** No code in `app/features/customer/` was touched. Instead, `LoanCaseService`/`InsuranceCaseService` each expose a `_get_or_create_for_application_id`/`_sync_new_cases` pair: every staff list call scans `applications` (Module 6B, read-only) for `status="submitted"` rows of the matching `product_category` that don't yet have a case, and creates one on the spot; every single-case fetch does the same for that one `application_id`.

**Why:** Module 6B is frozen — adding a call into its `submit_application` (e.g. via the `event_engine` bus) would require editing that method, which the freeze policy prohibits without explicit approval. A MongoDB change-stream watcher on the `applications` collection would achieve the same "instant" trigger without touching 6B's code, but this project's entire test suite runs against `mongomock-motor` (no live MongoDB is available in this environment), which does not support change streams — building the core case-creation path on a mechanism the test suite structurally cannot exercise was rejected in favor of the lazy, fully-testable alternative.

**Impact:** `backend/app/features/loan_management/service.py`, `insurance_management/service.py`. A case reliably exists no later than the first time any Owner/Employee/Customer looks at the relevant list — in practice indistinguishable from "instant" for a human user, at the cost of not being a true real-time push. Documented in `docs/KNOWN_LIMITATIONS.md`.

## 059 — Module 6C uses real `require_permission` gating, reversing 6B's decision 050

**Decision:** Every `loan_management`/`insurance_management` staff endpoint is gated by `Depends(require_permission(module, "applications", action))` (Access Control, Module 3) — `view`/`edit`/`approve`/`reject`/`assign` — not a plain `require_staff` role check. `resource="applications"` (not "cases") deliberately matches the exact name Dashboard's own pre-existing "Disbursed"/"Rejected" widget catalog rows already reference (decision 032), so those widgets became grantable to an Employee with zero Dashboard code changes.

**Why:** The brief's own instruction is explicit: "Every action must use the existing Access Control Platform. No new authorization mechanism." Unlike 6B (decision 050, where Employee visibility was framed as inherent and non-delegable), 6C's capabilities — who may evaluate credit, who may do final evaluation, who may disburse — are exactly the kind of granular, Owner-delegable grant Access Control exists for, the same reasoning that made Module 4 the first real `require_permission` consumer.

**Impact:** `scripts/seed.py:seed_permission_catalog` (two new entries: `loan_management:applications`, `insurance_management:applications`, actions `[view, edit, approve, reject, assign]`). An Employee sees nothing until granted a role with one of these; Owner bypasses entirely as always.

## 060 — Additional case documents reuse Module 6B's existing `application_documents`/upload endpoints unmodified; only "what's still outstanding" is 6C's own state

**Decision:** No new document-upload endpoints or collection were added. An Employee "requesting" documents mid-pipeline only adds `document_type_id`s to `ApplicationWorkflow.pending_document_type_ids`; the Customer (or staff, on their behalf) still calls 6B's own `POST /applications/{id}/documents/upload-url` + `POST /applications/{id}/documents` (unmodified, not status-gated) against the same `application_id`. "Verify Documents" checks the existing `application_documents` collection for a matching row per pending type, then clears the list and advances the case.

**Why:** 6B's document endpoints already accept uploads at any Application status (verified by reading `confirm_document`/`get_document_upload_url` — neither checks `status`), so duplicating that plumbing in 6C would be pure repetition. Reuse-without-modification is this project's standing pattern since Module 2.

**Impact:** `backend/app/features/loan_management/service.py`/`insurance_management/service.py` (`request_documents`, `verify_documents`); zero lines changed under `app/features/customer/`. Known gap: there is currently no staff-facing "upload on the Customer's behalf" affordance beyond what 6B's Customer-only endpoints already allow — see `docs/KNOWN_LIMITATIONS.md`.

## 061 — Bank/NBFC details are case fields, not a pipeline stage

**Decision:** The brief's own example sequence lists "Bank / NBFC Name + Application ID" as a stage between Documents Pending and Credit Evaluation. Per the instruction to defer to the approved Workflow Proposal wherever it differs from the example, and because the proposal's own status list didn't include this as a distinct status, Bank/NBFC Name, Application ID, Reference Number, Assigned Officer, Decision, and Remarks are recorded as fields on `LoanCaseDetails`, editable via `POST /loan-cases/{id}/bank-details` at any point before disbursement — not a status a case must pass through.

**Why:** Treating it as data collected alongside processing (rather than a gate that blocks the pipeline) avoids forcing every Loan Case through an extra status transition purely to record administrative reference numbers, while still fully satisfying the brief's "Support recording Bank/NBFC Name, Application ID, Reference Number, Assigned Officer, Decision, Remarks... Manual processing only" requirement.

**Impact:** `backend/app/features/loan_management/models.py` (via `workflow_engine.models.LoanCaseDetails`), `schemas.py:BankDetailsRequest`, `router.py`'s `/bank-details` endpoint. Frontend: an always-visible "Bank / NBFC Details" panel on `LoanCaseDetailsPage.tsx`, not a conditional one gated by status.

## 062 — No Customer-facing frontend was built for Module 6C

**Decision:** The backend exposes Customer self-service endpoints (`GET /loan-cases/mine`, `POST /loan-cases/{id}/offer/accept`, `/offer/decline`, and the Insurance equivalents) so the pipeline's data model is complete and testable end-to-end, but **no Customer Portal screen or link was built to reach them.**

**Why:** The brief's own exclusion list is explicit: "Do NOT build ... Customer Portal enhancements." Building a Customer-facing offer/premium review screen would be exactly that. The Frontend section's own "Only build" list is also entirely staff-facing (Application Processing, Workflow Timeline, Status Change, Document Verification, Bank/NBFC Details, Decision Screen, Application History) — no customer screen appears there either.

**Impact:** A submitted Loan/Insurance case can be driven all the way to Offer Acceptance / Premium Acceptance by staff, but the Customer's own accept/decline action is currently reachable only by direct API call, not through any UI — see `docs/KNOWN_LIMITATIONS.md`. Building that screen is explicitly deferred to a future, explicitly-requested Customer Portal enhancement round, not an oversight.

## 063 — Dashboard's "Disbursed"/"Rejected" widgets wired to real data

**Decision:** `backend/app/features/dashboard/widget_providers.py`'s `_disbursed`/`_rejected` functions now query `application_workflows` for real counts (Owner sees company-wide, Employee sees their own assignment-scoped count, same convention as `_assigned_leads`), replacing the `_not_yet_available` placeholders.

**Why:** Same precedent as decision 044 (6A wiring Today's Leads/Assigned Leads) — Dashboard's widget catalog already reserved these exact widget keys/module names for whichever module eventually built loan/insurance processing; 6C is that module. `widget_providers.py` is the one Dashboard file every subsequent module has always been expected to extend, not a frozen surface in the same sense as Dashboard's engine/models.

**Impact:** `backend/app/features/dashboard/widget_providers.py`. No Dashboard schema, engine, or API changed — only two function bodies, exactly like 6A's own edit to the same file.

## 064 — Insurance lifecycle finalized, and "On Hold" added as an Optional Status on both pipelines

**Decision:** Two final refinements requested by the user before freezing Module 6C, both implemented as data/config changes to the existing generic engine — no new engine capability beyond what `WorkflowEngine.transition()` already provides:

1. **Insurance lifecycle finalized**, superseding decision 057's flagged assumption: Application Submitted → Documents Pending → Underwriting → **Medical Verification** (optional) → **Additional Documents** (optional) → Premium Acceptance → **Policy Generation** → **Policy Issued**, with Rejected reachable from Underwriting or Medical Verification. Both optional stages are per-case flags (`requires_medical`, `requires_additional_documents`) recorded once during Underwriting — `requires_additional_documents` is consulted again after Medical Verification clears, so a case needing both passes through Medical Verification *then* Additional Documents, in that order, never the reverse. Policy Generation (the policy number/document is prepared, case stays in this status) and Policy Issued (terminal) are two distinct statuses, not one — `POST /insurance-cases/{id}/policy/generate` records the policy number without transitioning; a separate `POST /insurance-cases/{id}/policy/issue` (requires a policy number already set) transitions to the terminal status. The former `active` terminal status is removed — `policy_issued` is now the terminal success state.
2. **"On Hold" — an Optional Status, not a hardcoded branch.** Every non-terminal status on both pipelines gets `on_hold` appended to its own `allowed_next_statuses` (config, `scripts/seed.py:seed_workflow_definitions`); each case type's shared `on_hold` `WorkflowDefinition` row lists every status it can `resume` back into (`LoanStatus.RESUMABLE`/`InsuranceStatus.RESUMABLE`). `workflow_engine/hold.py`'s `put_on_hold`/`resume_case` are the only new code, and both are just the *existing* generic `WorkflowEngine.transition()` — hold records `on_hold_previous_status`/`on_hold_reason`/`on_hold_since` on the case and moves it to `on_hold`; resume reads that recorded status back out and transitions there, then clears the bookkeeping fields. A closed `HoldReason` vocabulary (`waiting_for_customer`/`waiting_for_bank`/`waiting_for_insurance_company`/`internal_review`/`document_clarification`) is required on every hold. Every stage-specific action (credit evaluation, underwriting, document verification, ...) is naturally blocked while a case is `on_hold`, since none of those actions' own status guard-clauses match `on_hold` — enforced implicitly by the existing per-action checks, not a new guard.

**Why:** The insurance draft (decision 057) was explicitly flagged as unconfirmed; the user reviewed it and gave a corrected, final sequence directly, including the specific reasoning that not every insurance product needs a medical exam and that Policy Generation/Policy Issued are distinct business events. "On Hold" was the user's own explicit recommendation, with the explicit instruction "Don't hardcode it. Make it Workflow Definition → Optional Status" — satisfied by treating it as ordinary seeded config consumed by the same generic transition-validation code every other status already uses, rather than a special-cased status the engine treats differently.

**Impact:** `backend/app/features/workflow_engine/{constants,models,hold}.py` (new `HoldReason`, `ON_HOLD_STATUS`, on-hold fields on `ApplicationWorkflow`, `WorkflowAuditEvent.CASE_ON_HOLD`/`CASE_RESUMED`), `insurance_management/{constants via workflow_engine,schemas,service,router}.py` (renamed/added statuses and fields: `requires_additional_documents`, `medical_verification_outcome`/`_remarks`, `policy_generated_at`; new `generate_policy`/`issue_policy` split), `loan_management/{service,router}.py` (hold/resume endpoints, reusing the shared `workflow_engine.hold` functions — no Loan-specific hold logic needed). `scripts/seed.py:seed_workflow_definitions` rewritten with the finalized Insurance rows plus a shared `on_hold` row per case type. `tests/api/test_workflow.py` — new/updated: `test_insurance_pipeline_without_medical_or_additional_docs_to_policy_issued`, `test_insurance_pipeline_with_medical_and_additional_docs`, `test_insurance_medical_verification_failure_rejects_case`, `test_loan_case_hold_and_resume`.

---

**Freeze:** Loan & Insurance Processing Pipeline (Module 6C) is approved and frozen. Decision 057's assumption is superseded and closed by decision 064 — the Insurance lifecycle is now settled business logic, not a placeholder. No architectural changes to this module without explicit approval; Module 6D (Reminder Engine) consumes its data (e.g. a Rejected Loan/Insurance Case feeding the 90-day re-eligibility reminder) rather than modifying its engine, models, or APIs.

# Module 6D — Reminder & Notification Engine

Scoped explicitly to internal database notifications only — no WhatsApp/SMS/Email/push/external API this round (the brief's own exclusion list); `app/features/notification_management/` remains reserved for that future work, untouched.

## 065 — Notification triggers reuse the `audit_logs` polling pattern (decision 058), not a live event hook

**Decision:** `poll_audit_events` (`app/worker/tasks/reminders.py`) scans the existing, already-written `audit_logs` collection for exactly two event types named in the brief's own examples — `lead_assigned` (Module 6A) and `document_uploaded` (Module 6B) — since the last processed timestamp (tracked in a new, tiny `notification_checkpoints` collection, one row per event type), and creates a Notification for the relevant Employee. Neither Leads' nor Customer's frozen code is touched.

**Why:** Same reasoning as decision 058 (6C's lazy case-creation): hooking into a frozen module's write path isn't permitted, and this project's mongomock-based test suite can't exercise Mongo change streams (the only mechanism that would make a live push genuinely instant). Since `audit_logs` is already written by every module on every meaningful action, polling it is a zero-modification, fully-testable way to react to events in frozen modules.

**Impact:** `backend/app/worker/tasks/reminders.py:poll_audit_events`, `app/features/reminders/{models,repository}.py:NotificationCheckpoint`. Notifications lag the real event by up to one polling interval (5 minutes) — see `docs/KNOWN_LIMITATIONS.md`. `document_uploaded` only notifies if the Application is *already* assigned at poll time; an upload against a still-unassigned Application is silently skipped (no retroactive catch-up once it's later assigned).

## 066 — Internal Notification Queue lives in `features/reminders`, not deferred to `features/notification_management`

**Decision:** `Notification`/`Task`/`ReminderRule`/`Reminder` all live in `app/features/reminders/`. `app/features/notification_management/` (reserved since Foundation, decision 006, for external channel delivery — WhatsApp/SMS/Email) is not touched and gains no code this round.

**Why:** The user's own Module 6D scope explicitly listed "3. Internal Notification Queue" and "4. Notification History" as part of *this* module, not a separate one — matching the folder split's original intent (`reminders` = re-eligibility/task reminders + their notifications; `notification_management` = external channel plumbing for whenever that's built).

**Impact:** `backend/app/features/reminders/{models,repository,service,router}.py`. A future Notification Management module can read/write the same `notifications` collection (e.g. to additionally deliver a copy over SMS) without needing to redefine the schema — it would consume this module's `Notification` model, not invent its own.

## 067 — `ReminderRule` is one unified collection discriminated by `rule_type`

**Decision:** `re_eligibility` and `task_due` rules share one `reminder_rules` collection/model, with rule-type-specific fields left `None` for the other kind (`case_type`/`eligible_after_days`/`notify_before_days` vs. `notify_before_minutes`/`escalation_repeat_minutes`/`escalation_max_repeats`).

**Why:** Same "engine is code, catalog is data" reasoning as decision 054 (6C's unified `application_workflows`) — the scheduler jobs are generic code reading whichever fields apply to the rule's own `rule_type`; a future third rule kind is a new discriminator value plus new optional fields, not a new collection.

**Impact:** `backend/app/features/reminders/models.py:ReminderRule`. Per the explicit instruction "Don't hardcode reminder timings... create Reminder Rules in the database" — `scripts/seed.py:seed_reminder_rules` seeds exactly the three starter rules named in the brief (Loan/Insurance 90-day re-eligibility, 30-minute task-due), Owner-editable via `GET/POST/PATCH /reminder-rules` without any code change.

## 068 — `Task` is a new entity, introduced by this module

**Decision:** No `Task` concept existed anywhere in the project before Module 6D. `Task(BaseDocument)` (`title`, `description`, `assigned_to`, `assigned_by`, `due_at`, `status` pending/completed, `completed_at`, `owner_escalated`) is added to `app/features/reminders/models.py`.

**Why:** Dashboard's own "Tasks" widget catalog row (seeded in Module 5, decision 037) already referenced `required_module="reminders"`, `required_resource="tasks"` — confirming this module was always intended to be Tasks' real home, per decision 032's forward-compatibility pattern (a widget can reference a module/resource before that module exists; the grant becomes meaningful once it's built).

**Impact:** New collection `tasks`. Permission catalog: `Permission(module="reminders", resource="tasks", actions=[view,create,edit])` — the exact `(module, resource)` pair Dashboard's Tasks widget already expects, so it becomes grantable to an Employee with zero Dashboard code changes (same forward-compatibility payoff as 6C's `loan_management:applications`).

## 069 — Task escalation ladder: repeat reminders to the assignee, then one final notification to every Owner

**Decision:** A `task_due` rule's `escalation_repeat_minutes`/`escalation_max_repeats` drive a ladder: once a task is overdue, the assignee gets a `task_escalation` reminder every `escalation_repeat_minutes` (tracked as accumulating `Reminder` rows, `repeat_count` incrementing); once the count reaches `escalation_max_repeats`, one additional `task_owner_escalation` notification is sent to every `role="owner"` user, and `Task.owner_escalated` is set `True` so this final step never repeats for that task. Matches the brief's own diagram: "Owner Assigns Task → Reminder → Not Completed → Reminder Again → Still Not Completed → Notify Owner."

**Why:** A boolean flag (rather than, say, counting owner-notifications) is the simplest way to make the terminal step idempotent — once the Owner has been told, further overdue-ness doesn't need to keep re-notifying them under the current scope; a future round could add a distinct "re-escalate" concept if wanted, without changing this flag's meaning.

**Impact:** `backend/app/features/reminders/models.py:Task.owner_escalated`, `app/worker/tasks/reminders.py:check_task_reminders`. Notification types: `task_due`, `task_escalation`, `task_owner_escalation` (`app/features/reminders/constants.py:NotificationType`).

## 070 — Dashboard's "Tasks"/"Notifications" widgets wired to real data

**Decision:** `backend/app/features/dashboard/widget_providers.py`'s `_tasks`/`_notifications` now query the real `tasks`/`notifications` collections (Owner sees company-wide pending tasks; each user — Owner included — sees only their *own* notification inbox, never another user's), replacing the `_not_yet_available_list` placeholders. `pending_followups` stays a placeholder — it needs a follow-up-date field on `Lead` that Module 6A's frozen schema doesn't have, a different concept from 6D's reminders.

**Why:** Same precedent as decisions 044/063 (6A/6C wiring their own reserved widget keys) — `widget_providers.py` is the one Dashboard file every subsequent module has always been expected to extend.

**Impact:** `backend/app/features/dashboard/widget_providers.py` only — no Dashboard schema/engine/API change. `GET /dashboard/notifications` (and therefore the Topbar Notification Bell, Module 5, frozen) now shows real unread counts/items for the calling user; the Bell's own rendering (`NotificationBell.tsx`, frozen) still just `JSON.stringify`s each item since that file isn't touched — see `docs/KNOWN_LIMITATIONS.md`.

## 071 — Tasks/Reminder Rules use real `require_permission`; Notifications are self-service like 6B/6C's own inboxes

**Decision:** `POST/GET/PATCH /tasks` and `/reminder-rules` are gated by `require_permission("reminders", "tasks"|"reminder_rules", action)` (Access Control) — no new authorization mechanism, per explicit instruction. `POST /tasks/{id}/complete` and all of `/notifications/*` are self-service instead: gated only by a plain `require_staff` role check (reused from `app.features.customer.dependencies`, not duplicated) plus an ownership check in the service layer (a Notification's `recipient_user_id` must match the caller; a Task can only be completed by its assignee or the Owner).

**Why:** Assigning/configuring is a delegable, Owner-grantable capability (same reasoning as 6C's decision 059) — but reading or dismissing *your own* notification, or marking *your own* task done, isn't a capability an Owner would ever need to grant or withhold; it mirrors exactly how 6B/6C scoped Customer/assignee self-service actions without an Access Control grant.

**Impact:** `backend/app/features/reminders/{router,dependencies}.py`. Permission catalog: `reminders:tasks` (`view`/`create`/`edit`), `reminders:reminder_rules` (`view`/`create`/`edit`).

## 072 — `ensure_utc` added to the shared `utils/datetime.py` (Foundation, additive-only)

**Decision:** Motor/PyMongo returns a stored datetime as naive (no `tz_aware=True` configured on this project's client) even though every write anywhere in the codebase uses `utc_now()` (tz-aware) — comparing a value just read back from Mongo against a fresh `utc_now()` raises `TypeError: can't compare offset-naive and offset-aware datetimes`. A new function, `ensure_utc(dt) -> dt if dt.tzinfo else dt.replace(tzinfo=UTC)`, is added to `app/utils/datetime.py` and used wherever the scheduler jobs compare a DB-read timestamp (a case's rejection time, a task's `due_at`, a reminder's `fired_at`) against `utc_now()`.

**Why:** This is the first module to need full datetime (not just `.date()`) precision comparisons between a fresh timestamp and one read back from Mongo — Access Control's own lazy time-window expiry (decision 022) sidesteps the exact same underlying gap by comparing only `.date()` on both sides, which isn't precise enough for task-due/escalation timing. Adding one new function to `utils/datetime.py` (never modifying `utc_now()`/`is_expired()`) is the same additive-only pattern already established for `id_generator.py`'s `IdPrefix` — a genuinely new-behavior addition, not a change to an existing frozen function.

**Impact:** `backend/app/utils/datetime.py:ensure_utc` (new), `app/worker/tasks/reminders.py` (all three jobs). No existing caller of `utc_now()`/`is_expired()` is affected.

---

## 073 — Notification Category taxonomy, derived automatically from `notification_type`

**Decision:** Every `Notification` now carries a `category` field — one of `assignment`/`reminder`/`task`/`workflow`/`document`/`system`/`security` (`NotificationCategory`, `app/features/reminders/constants.py`) — computed by `RemindersService.create_notification` from a fixed `CATEGORY_BY_NOTIFICATION_TYPE` lookup keyed on the notification's own `notification_type`, never accepted as caller input. `GET /notifications` gained an optional `category` query param. `workflow`/`system`/`security` are reserved categories with no current producer — no notification type maps to them yet, but the taxonomy has a slot ready for e.g. a future workflow-status-change or security-event notification without a schema change.

**Why:** The user's own recommendation, given as a small, additive improvement rather than a redesign: "Instead of only storing notifications, also classify them... Then later users can filter notifications easily. This is a small enhancement and doesn't require redesigning the notification engine." Deriving the category from `notification_type` (rather than letting a caller set it directly) makes misclassification structurally impossible — a `task_due` notification can never accidentally end up tagged `security`, since the mapping is one fixed dict, not a per-call choice.

**Impact:** `backend/app/features/reminders/{constants,models,service,repository,schemas,mappers,router}.py`, `frontend/src/features/reminders/{api,pages/NotificationListPage}.tsx` (category filter dropdown + badge on each notification card). `tests/api/test_reminders.py::test_notification_inbox_read_archive_dismiss_and_ownership` extended to assert the derived category and the filter's behavior.

## 074 — Reminder Rules support multiple independent trigger points per rule

**Decision:** `ReminderRule.notify_before_days`/`notify_before_minutes` changed from `int | None` to `list[int] | None` (both `re_eligibility` and `task_due` rule types). `Reminder` gained `trigger_offset: int | None`, recording which specific configured offset a given fired reminder corresponds to; `ReminderRepository.find_existing` now takes `trigger_offset` so idempotency is checked per offset, not per rule. Both scheduler jobs (`check_re_eligible_cases`, `check_task_reminders`) iterate every configured offset independently, computing its own `notify_at` and firing/skipping per offset — a case or task that has already crossed several configured thresholds since the last scheduler run "catches up" on all of them in one pass rather than firing only the nearest one.

**Why:** The user's own recommendation, using the exact worked example "Rejected Case → 90 Days → Notify → 30 Days Before → 15 Days Before → 7 Days Before → 1 Day Before," with the explicit framing "Even if you only use one reminder now, designing the rule to support multiple trigger points will make future enhancements easier." The seeded starter rules still configure only a single offset each (`[10]`/`[30]`) — this is schema/engine capacity, not a change to current default behavior.

**Impact:** `backend/app/features/reminders/{models,repository,service,schemas,mappers}.py`, `app/worker/tasks/reminders.py` (both cron jobs rewritten to loop over `rule.notify_before_days`/`notify_before_minutes`), `scripts/seed.py:seed_reminder_rules` (values wrapped in single-element lists), `frontend/src/features/reminders/{api,pages/ReminderRulesPage}.tsx` (comma-separated text input parsed to `number[]` — the simplest UI clearing the bar the user set, not a polished multi-value editor). New test: `tests/api/test_reminders.py::test_check_re_eligible_cases_fires_each_configured_trigger_point_independently`.

---

**Freeze:** Reminder & Notification Engine (Module 6D) is approved and frozen, after two small additive enhancements (decisions 073, 074 — Notification categories, multi-trigger Reminder Rules) requested before the freeze was finalized. Future modules (Referral Partner Portal onward) consume its Notification/Task model rather than modifying its engine, models, or APIs.

# Module 7 — Referral Partner Portal

Built from a written design proposal the user reviewed and refined before implementation began (same rhythm as Module 6C's own workflow proposal) — five refinements were folded in before a line of code was written: the edit cutoff is "processing started," not "left status=new"; every `CommissionEntry` stores a full snapshot of the rule that produced it; Referral Partner hierarchy is reserved (schema slot only, zero logic); external status stays a fixed four-value vocabulary; and settlement stays manual, no payment gateway.

## 075 — `referral_partner`/`referral_partner_management` folder rename (Foundation-era naming gap closed)

**Decision:** The empty, reserved `features/referral_partner` folders (backend and frontend, scaffolded since Foundation) are renamed to `referral_partner_management` before any code is added.

**Why:** Module 5's own Dashboard widget catalog (decision 037) already seeded a `referral_summary` widget row expecting `required_module="referral_partner_management"` — the folder name and the widget's own gate had drifted apart since Foundation. Since the folders were empty apart from a placeholder file, renaming them is a zero-risk alignment, not a change to any working code — the same class of fix as 6D's `resource="tasks"` matching Dashboard's pre-existing naming (decision 068).

**Impact:** `backend/app/features/referral_partner_management/`, `frontend/src/features/referral_partner_management/` (renamed, empty at rename time). No other file referenced the old path.

## 076 — Referral Partner account: Auth's existing invite mechanism, plus a second, independent approval gate

**Decision:** `POST /referral-partners` (Owner-only) creates the `ReferralPartner` profile row *and* calls Auth's own `AuthService.send_otp(mobile, role="referral_partner", inviter=owner)` (decisions 003/011, unmodified) to create the pending `User` and send the signup OTP — the exact same invite path already used for Customer, just invoked directly rather than requiring the Owner to make a second `/auth/send-otp` call. A Referral Partner can set their password and log in immediately once they verify the OTP (Auth's own flow, untouched) — but `ReferralPartner.approval_status` (`pending_approval` → `active` → `deactivated`, Owner-only `POST .../approve`/`.../deactivate`) is a second, independent gate: every self-service action beyond reading your own profile (`add_lead`, `update_own_lead`, dashboard, commission history) requires `approval_status == "active"`, checked in this module's own service layer, not in Auth.

**Why:** The user's own approved sequence — "Owner Creates Referral Partner → Invitation → Referral Partner Sets Password → Approval Pending → Owner Approves → Active → Can Submit Leads" — treats "can log in" and "can act" as two separate moments. Reusing Auth's invite mechanism outright (rather than reimplementing OTP issuance) keeps Auth (frozen) completely untouched; the approval gate is new, Module-7-only state that doesn't belong in Auth's own `User.status`.

**Impact:** `backend/app/features/referral_partner_management/{models,service,router}.py` (new `ReferralPartner.approval_status`/`approved_at`/`approved_by`). No change to `app/features/auth/*`.

## 077 — `ReferralLead` mapping collection; `Lead` (Module 6A, frozen) untouched

**Decision:** A Referral Partner's "Add Lead" creates an ordinary `Lead` via Module 6A's own, unmodified `LeadService.create_lead` (source forced to the already-seeded "Referral" `LeadSource`, never caller-supplied) and records the relationship in a new `referral_leads` collection (`partner_id`, `lead_id`) rather than adding any field to `Lead` itself.

**Why:** The user's own explicit approval: "I completely agree with not touching the frozen Lead schema... That keeps Module 6A frozen." Same precedent as 6D's `NotificationCheckpoint`/6C's case-tracking — a new mapping collection, not a retrofit to a frozen model.

**Impact:** `backend/app/features/referral_partner_management/{models,repository}.py:ReferralLead`. `Lead`'s own edit path (`LeadService.update_lead`) is also reused unmodified for a Referral Partner's own-lead edits (`update_own_lead`), restricted to `full_name`/`mobile`/`email`/`remarks` only.

## 078 — External Lead status: a fixed four-value vocabulary, never an internal status; the edit cutoff is "processing started," not `Lead.status`

**Decision:** A Referral Partner only ever sees one of `submitted` / `in_progress` / `approved` / `rejected` for their own leads — computed on read (`ReferralPartnerManagementService.external_status_and_editable`), never stored, never derived from any raw Lead/Application/Case status string. "Processing started" (the point past which the lead becomes read-only for the partner) is defined as *"an Employee has been assigned to this Lead, OR an Application already exists for it"* — explicitly **not** `Lead.status`, which never changes away from `"new"` at this stage of Module 6A regardless of what's actually happening with the lead.

**Why:** Two of the user's own review points, both folded in before implementation: (1) "Referral Partners should never see internal statuses like Credit Evaluation ↓ NACH ↓ KYC ↓ Final Evaluation. Instead show: Submitted ↓ In Progress ↓ Approved ↓ Rejected." (2) The edit-cutoff correction — "Instead of 'Editable until status = New' I recommend 'Editable until Employee opens processing'... Sometimes Lead = New but Employee already started reviewing." Using `Lead.status` for this literally cannot work as the user described, since Module 6A's own `Lead.status` has exactly one value at this stage (see `leads/constants.py`) and never changes on assignment — `assigned_to`/Application-existence is the only signal that actually tracks "has anyone started working this."

**Impact:** `backend/app/features/referral_partner_management/{constants,service}.py` (`ExternalLeadStatus`, `external_status_and_editable`). Reads Module 6A's `Lead.assigned_to`, Module 6B's `Application` (by `lead_id`), and Module 6C's `ApplicationWorkflow.current_status` — all read-only, no writes to any frozen collection.

## 079 — Commission Rules are Owner-configurable data; Commission Entries store a full snapshot and are never recomputed

**Decision:** `CommissionRule` (product_category + partner_id scoping, `calculation_type` percentage/flat, `rate_or_amount`, `trigger_event`) is an Owner-managed catalog — no rate is ever hardcoded, matching the "engine is code, catalog is data" split used since Access Control/6C/6D. When a referred lead's case reaches its trigger event (Loan → `disbursed`, Insurance → `policy_issued` — 6C's own terminal "success" statuses, decision 064), a `CommissionEntry` is created **once**, storing a full snapshot of the rule that produced it (`rule_id` plus the *applied* `calculation_type`/`rate_or_amount`) and the computed `commission_amount` itself. Editing or retiring a `CommissionRule` afterward never touches any `CommissionEntry` already created from it — the entry's own stored fields are the only source of truth for that payout, forever.

**Why:** The user's own explicit, strongly-worded requirement: "Suppose Commission Rule 2%, later Owner changes 3%. Old commission entries must stay 2%... This is extremely important," followed by "When a commission becomes payable, don't calculate it every time. Instead: Trigger → Calculate Once → Store Amount → Ledger. Never recalculate from Rule." Getting this wrong would mean a rate change silently rewriting historical payout history — exactly the "commissions are difficult to change later" risk the user named as the reason for reviewing this module more carefully than usual.

**Impact:** `backend/app/features/referral_partner_management/models.py:CommissionEntry` (full snapshot fields), `service.py:create_commission_entry_if_applicable`/`_pick_rule` (most-specific-match: partner-specific + product-specific > partner-specific + all-products > default + product-specific > default + all-products), `app/worker/tasks/referral_partner.py:check_commission_triggers` (new daily Arq cron job, registered in `worker_settings.py` — reads `application_workflows` read-only, the same "re-scan a terminal-status collection each run, rely on a unique index for idempotency" trade-off as 6D's `check_re_eligible_cases`). Settlement (`POST /commission-entries/{id}/approve`, `.../settle`) is manual only — no payment gateway integration, per the user's explicit "Keep manual commission settlement only; no payment gateway yet." Test: `tests/api/test_referral_partner_management.py::test_commission_rule_crud_entry_creation_and_snapshot_is_immutable` asserts a rule-rate edit after entry creation leaves the entry's `commission_amount` unchanged.

## 080 — Referral Partner hierarchy: reserved, not implemented

**Decision:** `ReferralPartner.parent_partner_id: str | None = None` exists on the model with no reader or writer anywhere in this module — no API field, no UI, no business logic.

**Why:** The user's own explicit instruction: "Referral Partner Hierarchy — Not now. Just reserve it... You don't implement it. Just make sure the architecture doesn't prevent it." A nullable, currently-inert field is the same "reserve a slot, no logic" pattern already used for `event_engine.publish()`'s currently-zero subscribers and `WorkflowDefinition.notification_trigger_key` (see docs/KNOWN_LIMITATIONS.md) — adding real parent/child logic later needs no migration, since the field already exists.

**Impact:** `backend/app/features/referral_partner_management/models.py:ReferralPartner.parent_partner_id` only. Documented in `docs/KNOWN_LIMITATIONS.md` as inert-by-design, not a gap.

## 081 — Every Module 7 management capability is `require_owner`-gated, not `require_permission`

**Decision:** Partner lifecycle (create/approve/deactivate), Commission Rules, and the Commission Ledger/Settlement are all gated by a plain `require_owner` role check — no Access Control permission catalog entries were added for this module.

**Why:** Unlike 6C/6D, the brief never names an Employee capability anywhere in this module — every bullet under both the "Referral Partner" and "Owner" headings is either external-actor self-service or explicitly Owner's own action. Adding `require_permission` scaffolding for a capability the brief never frames as delegable would be unrequested flexibility, not a fix for a real gap — consistent with 6B's own precedent of matching the brief's exhaustive capability list exactly (decision 050).

**Impact:** `backend/app/features/referral_partner_management/dependencies.py` (`require_owner`, reused from `app.features.employee.dependencies`, not duplicated). Dashboard's `referral_summary` widget (decision 070's own precedent) is wired to real data (`_referral_summary`, company-wide totals) — it will only ever be visible to Owner in practice, since no Employee permission for this module's resources is ever seeded.

---

**Freeze:** Referral Partner Portal (Module 7) is approved and frozen. Future modules (Reports & Analytics onward) consume its `ReferralPartner`/`CommissionEntry` data (read-only, for reporting) rather than modifying its engine, models, or APIs.

**Unified freeze policy reconfirmed:** Foundation through Referral Partner Portal (Module 7) — eleven modules/sub-modules — are all frozen under one rule: no architectural modifications, only bug fixes, security fixes, or explicitly approved business changes, as Reports & Analytics begins.

# Module 8 — Reports & Analytics

Per the user's own explicit process change — "Don't build reports one by one. Instead, first build [a] Reporting Framework... Then Business Reports become configuration" — the framework (`features/reporting/`) was built first, and all 17 named Business Reports are registry entries on top of it, not one-off hand-built screens.

## 082 — Report Engine: a registry of `(key, label, category, description, run)` entries, not a bespoke route per report

*Initially implemented as a Python dict (`REPORT_DEFINITIONS`); decision 090 (below) moved the registry itself into a database collection for every report expressible as generic parameters, keeping a Python-side registry (`CUSTOM_REPORT_RUNNERS`) only for the reports that genuinely need custom logic. This entry describes the original, still-accurate shape of the Report Engine's contract; 090 describes what changed.*

**Decision:** `backend/app/features/reporting/reports.py` defines a `run(db, date_from, date_to) -> ReportResult` function per report, resolved by `key`. Two generic router endpoints — `GET /reports/{key}` and `GET /reports/{key}/export` — reach every report the same way; adding a new report never means a new route, schema, or permission.

**Why:** The user's own framing: "Business Reports become configuration" once the framework exists. This mirrors the "engine is code, catalog is data" split already used for Access Control's `PermissionEngine`/`Permission`, 6C's `WorkflowEngine`/`WorkflowDefinition`, and 6D/7's `ReminderRule`/`CommissionRule` — here the "catalog" is a Python dict rather than a database collection (report *logic* is inherently code; nothing about a report's shape is meaningfully Owner-editable data the way a commission rate or a reminder timing is).

**Impact:** `backend/app/features/reporting/{reports,schemas,service,router}.py`. `ReportResult` (`columns`, `rows`, `summary`) is the one response shape every report returns — the frontend's `ReportViewerPage` renders any report generically from its `columns`/`rows`, without per-report frontend code.

## 083 — Aggregation Layer: four generic Mongo helpers (`group_count`, `group_sum`, `count_matching`, `resolve_names`) shared by all 17 reports

**Decision:** `backend/app/features/reporting/aggregations.py` holds a handful of generic functions — group-and-count, group-and-sum, a plain filtered count, and an id→name resolver — built on `date_range_match` (the one shared Date Range convention every report accepts: `date_from`/`date_to`, inclusive, end-of-day on `date_to`). The 5 `count`/`sum`-type reports (decision 090) call `group_count`/`group_sum` directly through a generic executor; the 5 `list`-type reports use a third generic executor that queries directly (no grouping) but still reuses `date_range_match`; the remaining 7 `custom` reports (needing a `$lookup` join, a compound group key, or a reused service call) write bespoke pipelines, still reusing `date_range_match`/`resolve_names`/`count_matching`/the `is_deleted: False` convention where applicable.

**Why:** The user's own explicit instruction to build "an Aggregation Layer," reused by report definitions rather than each one hand-rolling its own Mongo pipeline — matching `shared/base_repository.py`'s own "generic primitives, many thin call sites" shape, applied one level up.

**Impact:** `backend/app/features/reporting/aggregations.py` (new, no other module depends on it). Every helper reads a frozen module's collection directly and read-only — the same reuse pattern as every prior cross-module read (6C reading 6B, 6D reading 6C, 7 reading 6A).

## 084 — "Dashboard Analytics" recomputes Dashboard's own metric definitions read-only; it does not import Dashboard's frozen `widget_providers.py`

**Decision:** The `dashboard_analytics` report computes company-wide totals (total leads, assigned leads, loans disbursed, policies issued, pending tasks, active referral partners) by querying the same source collections Dashboard's own widgets read — but as fresh, module-8-owned queries, not by calling into `app/features/dashboard/widget_providers.py` (frozen since Module 5).

**Why:** The user's instruction — "Dashboard Analytics: Reuse Dashboard. Don't duplicate calculations." — is satisfied in spirit (the report never invents a different definition of "today's leads" than Dashboard uses) without violating the freeze: Dashboard's widget functions are also *per-viewer* scoped (an Employee's own assigned-tasks count, their own notification inbox) — a fundamentally different contract than a company-wide report metric, so literally importing them wouldn't produce the right shape anyway. Recomputing from the same collections, same semantics, is the closest safe equivalent to "reuse, don't duplicate" available without modifying a frozen file.

**Impact:** `backend/app/features/reporting/reports.py:_dashboard_analytics`. No change to `app/features/dashboard/*`.

## 085 — Scheduled Reports: framework only — CRUD and storage exist, nothing executes yet

**Decision:** `ScheduledReport` (report_key, filters, frequency, recipient_user_ids, is_active, `last_run_at`) has full CRUD (`POST/GET/PATCH/DELETE /scheduled-reports`) but no Arq job reads this collection — `last_run_at` is set by no code anywhere.

**Why:** The user's own explicit scope: "Scheduled Reports (framework only)." Same "reserve the schema, no logic yet" posture as Referral Partner's `parent_partner_id` (decision 080) — a future round can add the actual distribution job (reading `is_active` schedules due to run, executing their report, emailing/notifying `recipient_user_ids`) without any migration, since the shape already exists.

**Impact:** `backend/app/features/reporting/models.py:ScheduledReport`. Documented as inert-by-design in `docs/KNOWN_LIMITATIONS.md`, not a gap.

## 086 — Saved Filters are self-service, per-user, never shared

**Decision:** `SavedFilter` (user_id, report_key, label, filters) is a strictly own-user preset — `GET /saved-filters` only ever returns the caller's own rows, `DELETE` 404s on any other user's filter — the same posture as Reminders' Notification inbox (decision 066) and Referral Partner's own-lead scoping.

**Why:** A saved filter is a personal convenience (e.g. "my usual date range for this report"), not shared team configuration — no capability in the brief suggests otherwise, and this avoids inventing an unrequested sharing/visibility model.

**Impact:** `backend/app/features/reporting/{models,repository,service,router}.py`. No permission catalog entry — gated by plain `require_staff`, matching 6D's Notifications.

## 087 — Reports/Scheduled Reports are `require_permission`-gated (delegable), unlike Module 7's Owner-only posture

**Decision:** `GET /reports`, `GET /reports/{key}`, `GET /reports/{key}/export`, and all of `/scheduled-reports` are gated by `require_permission("reporting", "reports"|"scheduled_reports", action)` — real, Owner-delegable Access Control permissions, not a hardcoded `require_owner` check.

**Why:** Unlike Module 7 (where the brief named no Employee capability anywhere), this brief doesn't restrict Reports & Analytics to Owner only — reports are generically useful to delegate (e.g. a Branch Manager role viewing their own branch's reports once role-scoping is added later). Matches the majority pattern used by every module since Access Control existed (6A leads, 6C loan/insurance, 6D tasks/reminder_rules) rather than 7's narrower exception.

**Impact:** `scripts/seed.py:seed_permission_catalog` — new `reporting:reports` (view, export) and `reporting:scheduled_reports` (view, create, edit, delete) entries. Nav items (`seed_reporting_nav_items`) gate on these same permissions, not `owner_only`.

## 088 — Known approximations in report definitions (documented, not silently assumed)

**Decision:** A few reports use a reasonable but imperfect proxy where the exact concept doesn't exist as a stored field on a frozen collection: **"Loan Approved"** = `loan_details.offer_decision == "accepted"` (no separate credit-approval flag exists on `ApplicationWorkflow`, decision 055's schema); **"Loan/Insurance Rejected"** date = `updated_at` (no dedicated `rejected_at` timestamp exists); **"Leads by Product"** resolves a product name by checking `loan_products` first, `insurance_products` second, keyed only by `product_id` (a same-value collision across the two collections is astronomically unlikely but not structurally prevented).

**Why:** Rather than adding new fields to a frozen collection (out of scope for a reporting module) or silently guessing without disclosure, each approximation is called out inline (code comment) and centrally here, so a future business review can decide whether a dedicated timestamp/flag is worth adding to 6C's schema as an approved business change.

**Impact:** `backend/app/features/reporting/reports.py` (comments at each approximation site). Full list in `docs/KNOWN_LIMITATIONS.md`.

## 089 — Snapshot Reporting timestamps: recorded as a Phase 2 schema improvement, not implemented now

**Decision:** Decision 088's approximations (`updated_at` standing in for a rejection timestamp, `offer_decision` standing in for a distinct "approved" flag) are not fixed by adding real fields to `ApplicationWorkflow` (`submitted_at`/`approved_at`/`rejected_at`/`disbursed_at`/`policy_issued_at` etc.) in this round. This is recorded as a deferred Phase 2 schema improvement, to be implemented only if reporting accuracy requirements demand it later.

**Why:** The user's own explicit instruction: "I would not freeze that approximation... However, because Module 6C is frozen, I would not modify it now. Instead, record this as a Phase 2 schema improvement." Adding fields to `ApplicationWorkflow` would be an architectural change to a frozen module (Module 6C) — exactly the kind of change the freeze policy reserves for explicit approval, not something to fold in silently while building an unrelated module (Reporting).

**Impact:** None to any code this round. Recorded here and in `docs/KNOWN_LIMITATIONS.md`/`docs/roadmap/TODO.md` as an explicit deferred item, so a future session doesn't need to rediscover the same gap — if/when it's approved, it's an additive field change to `ApplicationWorkflow`/`LoanCaseDetails`/`InsuranceCaseDetails` (populated going forward; historical rows would keep using the `updated_at` proxy for anything that predates the change).

## 090 — Report Definitions become data (`report_definitions` collection), not a Python dict — for every report expressible as generic parameters

**Decision:** Supersedes part of decision 082. `REPORT_DEFINITIONS` (a Python dict) is replaced by `report_definitions`, a seeded Mongo collection — the same "engine is code, catalog is data" move already made for `WorkflowDefinition`/`ReminderRule`/`CommissionRule`. Each row carries `report_type` (`count` | `sum` | `list` | `custom`), `columns`, and — for the three generic types — the parameters a generic executor needs (`collection`, `group_field`/`sum_field`/`amount_field`, `date_field`, `extra_match`, optional name-resolution collection/field). **10 of the 17 reports are now pure configuration** (`lead_by_source`, `lead_by_employee` — `count`; `bank_performance` — `sum`; `loan_applications`, `insurance_applications` — `count`; `loan_approved`, `loan_rejected`, `loan_disbursed`, `insurance_policies_issued`, `insurance_rejections` — `list`; plus any future report expressible the same way) — adding one is a new `report_definitions` row, zero Python. The remaining **7 reports stay `report_type="custom"`** (`lead_conversion` — needs a `$lookup` join; `lead_by_product` — compound group key across two product collections; `employee_task_summary`/`referral_commission` — multi-status conditional sums in one row; `referral_leads`/`referral_conversions` — reuse Module 7's own `external_status_and_editable()`; `dashboard_analytics` — a multi-metric single-row summary, not a group/list shape at all). Their row still carries real metadata (label/category/columns/description, used by the catalog and CSV header) — only their *query logic* remains a registered Python function, in a small `CUSTOM_REPORT_RUNNERS` dict keyed by the same `key`.

**Why:** The user's explicit instruction: "Don't hardcode report definitions. Create a collection (or equivalent configuration)... New Report → New Configuration → No Code," with an explicit out if it was already equivalent. On inspection, 10 of the original 17 report functions were already *just* thin, parameterized calls into the Aggregation Layer (decision 083) with no genuine per-report logic — meaning the "code" was really just data wearing a function signature. Promoting those parameters into a real collection delivers exactly what was asked for the majority of reports, while being honest that 7 reports have irreducible custom logic (a join, a reused service call, a multi-branch conditional, a cross-metric summary) that configuration alone can't express without building a much larger query DSL — which would be over-engineering for 7 reports.

**Impact:** `backend/app/features/reporting/models.py:ReportDefinition` (new document model, replacing the dataclass in `reports.py`), `repository.py:ReportDefinitionRepository`, `reports.py` (three generic executors — `run_count_report`/`run_sum_report`/`run_list_report` — plus `CUSTOM_REPORT_RUNNERS` for the 7 custom keys), `service.py` (`run_report`/`list_report_definitions` now read the DB collection and dispatch on `report_type`), `scripts/seed.py:seed_report_definitions` (seeds all 17 rows — the concrete "add a report via configuration" mechanism this round). No Owner-facing CRUD was added for `report_definitions` — same posture as `WorkflowDefinition` (seeded config, not an Owner-editable screen), since authoring a new report's aggregation parameters is a developer-level task, not day-to-day business configuration the way a Commission Rule's rate is.

---

**Freeze:** Reports & Analytics (Module 8) is approved and frozen, after two refinements folded in before freeze: Report Definitions moved from a Python dict to seeded data for every report expressible as generic parameters (decision 090), and the reporting-accuracy approximations (decision 088) were recorded as a deferred Phase 2 schema improvement rather than fixed now (decision 089, since Module 6C is frozen). Future modules (External Integrations onward) consume its data read-only rather than modifying its engine, models, or APIs.

**Unified freeze policy reconfirmed:** Foundation through Reports & Analytics (Module 8) — twelve modules/sub-modules — are all frozen under one rule: no architectural modifications, only bug fixes, security fixes, or explicitly approved business changes, as External Integrations begins.

# Module 9A — API Management

Scoped explicitly to the integration *management* platform only, per the user's own instruction: "It should not send WhatsApp messages, create Meta leads, or call external services except for optional connection tests." No business action (sending a message, fetching a lead) exists anywhere in this module's code — that remains 9B (Lead Capture)/9C (Communication)'s job, both of which will consume what's configured here.

## 091 — New `features/integrations`, not an extension of frozen `system_settings.ApiSetting`

**Decision:** `system_settings.ApiSetting` (Module 4, frozen, decision 028) already stores an encrypted config blob per `(provider, label)` and was explicitly built with exactly Meta/WhatsApp/SMS/SMTP/Maps credentials in mind. Module 9A does not add fields to it or repurpose it — it builds a wholly new, additive `features/integrations` with its own three collections (`integration_providers`, `integration_configs`, `integration_test_logs`).

**Why:** The freeze policy (decision 031) explicitly disallows "repurposing a collection for a new meaning" without an explicit change request — and this module needs concepts `ApiSetting` never had: an Active-per-integration-type config (the user's own recommendation, decision 092), Test Connection with a full result history (decision 094), and Last Tested/Success/Failure tracking. Retrofitting all of that onto a frozen collection would be exactly the kind of architectural change the freeze exists to prevent; a fresh, purpose-built module is the same "new module consumes, doesn't modify, a frozen one" pattern used throughout this project (6C/6B, 6D/6C, 7/6A, 8/6C). `ApiSetting` itself is untouched and remains available for any other generic credential-storage need; `IntegrationConfig` is now the actual, richer home for these five providers' credentials specifically.

**Impact:** `backend/app/features/integrations/` (new). `system_settings/{models,service,router}.py` — zero changes. Both collections (`api_settings` and `integration_configs`) now exist with overlapping *purpose* (not overlapping *rows* — nothing migrates); worth a future cleanup decision if `ApiSetting`'s original five providers' rows are still present, but out of scope to resolve now since that would mean editing a frozen module's data model.

## 092 — Multiple named configurations per integration type, exactly one Active

**Decision:** `IntegrationConfig` is not one row per `integration_type` — an Owner can create any number of named configs per type ("Meta Production", "Meta Sandbox", "WhatsApp Test", ...), each with its own independent encrypted credentials. `is_active` marks which single config is currently live for its `integration_type`; activating one (`POST .../activate`) automatically deactivates any other active config of the same type (service-enforced, `IntegrationConfigRepository.deactivate_others`). `is_enabled` is a separate, per-config flag — a config can be enabled (ready, tested) without being the active one; disabling a config also clears its own `is_active` (an active config that isn't enabled is a contradiction the service prevents by construction, not by validation).

**Why:** The user's own explicit recommendation, given before implementation began: "design the storage to support multiple named configurations... Each configuration can have its own credentials, with one marked as Active. That gives you flexibility for testing, provider migration, and future tenant-specific configurations without changing the architecture later."

**Impact:** `backend/app/features/integrations/models.py:IntegrationConfig.{is_enabled,is_active}`, `repository.py:deactivate_others`, `service.py:{set_enabled,activate_config}` (`activate_config` 422s if the target config isn't enabled yet).

## 093 — Config storage: one flexible encrypted dict per config, secrets masked by naming convention

**Decision:** `IntegrationConfig.config_encrypted` stores the entire provider config as one `encrypt(json.dumps(config_dict))` blob via Foundation's `security/encryption.py` — the identical, unmodified primitive `ApiSetting` already uses (decision 028), reused rather than duplicated. There is no per-provider field-schema catalog enforced server-side (the brief's own field lists per type are realized as frontend-only UI guidance, `frontend/src/features/integrations/providerFields.ts`) — matching decision 028's own reasoning that provider config shape varies too much to hardcode. A config key is treated as secret — masked to its last 4 characters in every API response, never returned in full — purely by a naming-convention check (`is_secret_key`: the key contains "secret", "token", "key", or "password", case-insensitive). Every literal secret field named in the brief across all 5 integration types (App Secret, Access Token, Webhook Verify Token, Webhook Secret, API Key, Password) matches this convention with zero special-casing.

**Why:** Per explicit instruction: "Encrypt secrets before storing. Never return secrets in API responses. Show only masked values in the UI. Allow replacing secrets without exposing existing ones." Updates merge into the decrypted dict rather than replacing it wholesale (identical to `ApiSetting`'s own update logic) — rotating one key never requires resupplying every other secret. The masking convention (last-4-visible) matches Employee's own bank-account masking (decision 018), which is closer to "show a masked value" than `ApiSetting`'s stricter all-or-nothing `configured_keys` list — a deliberate choice since the brief asks for masked *values*, not just a configured/unconfigured flag.

**Impact:** `backend/app/features/integrations/{models,mappers,constants}.py`. `docs/KNOWN_LIMITATIONS.md` notes the same "no reveal, only overwrite" caveat `ApiSetting` already has.

## 094 — Test Connection: real checks where the API is well-known, generic reachability where the provider is open-ended — never a business action

**Decision:** `app/features/integrations/testers.py` implements one function per `integration_type`. **Meta** and **Google Maps** (single, well-known public APIs) get a real, live, read-only authenticated GET (`/me` on the Graph API; a minimal Geocode API call) — genuinely validates the credentials. **WhatsApp/SMS/API-based Email** (the brief itself asks these to support multiple future providers, decision 095) have no fixed API contract to target, so their check is a generic HTTP reachability request against the stored `api_url`, with an Authorization header if a token/key is present — proves the endpoint is reachable and auth-shaped, not a full provider-specific validation. **SMTP Email** gets a real connection + STARTTLS + login handshake via Python's standard-library `smtplib`, run off the event loop via `asyncio.to_thread`, and disconnects (`QUIT`) without ever sending mail. Every path returns `{success, response_time_ms, error_message}`, recorded to both `IntegrationConfig.last_tested_at/last_success_at/last_failure_at/last_error_message` and an append-only `IntegrationTestLog` row.

**Why:** Per explicit instruction: "Support a Test Connection action... Do not trigger business actions." No path here ever calls `send_template_message`/`send_sms`/`send_email`/`fetch_new_leads` (the existing `app/services/{whatsapp,sms,email,meta}` stub Protocols, still untouched and still raising `NotImplementedError` — 9B/9C's job to implement for real). Being honest that WhatsApp/SMS/generic-email checks can only be a *reachability* check (not a fully authenticated provider-specific call) rather than pretending deeper validation exists is the same "disclose the approximation" posture as decision 088.

**Impact:** `backend/app/features/integrations/testers.py` (new — the only file with real network/SMTP code in this module). `tests/api/test_integrations.py` monkeypatches `app.features.integrations.service.TESTERS` (a shared dict reference) to avoid live network calls in the test suite — no real credentials exist anywhere in this project.

## 095 — Integration Type → Provider → Configuration → Status via a seeded catalog, not hardcoded

**Decision:** `integration_providers` is a seeded collection of known `(integration_type, provider, label)` triples (`meta/meta`, `whatsapp/whatsapp_business_api`, `sms/generic_sms`, `email/smtp`, `email/email_api`, `maps/google_maps`) — `IntegrationConfig.create` validates the chosen `(integration_type, provider)` pair against this catalog (422 if unknown) rather than hardcoding an enum of providers in code. Adding a future provider for an existing type (e.g. a second WhatsApp provider) is one new seeded row (`scripts/seed.py:seed_integration_providers`), never a change to the CRUD/service/router code.

**Why:** Per explicit instruction: "Do not hardcode provider names. Instead: Integration Type → Provider → Configuration → Status. This allows adding new providers later without redesigning the module" — and the brief explicitly calls out WhatsApp/SMS as needing "Support multiple providers in the future." Matches the "engine is code, catalog is data" split used throughout this project.

**Impact:** `backend/app/features/integrations/models.py:IntegrationProvider`, `service.py:create_config`'s provider-catalog validation, `scripts/seed.py:seed_integration_providers`. Frontend's provider picker (`IntegrationListPage`) reads this catalog live rather than a hardcoded dropdown.

## 096 — `IntegrationConfig.health_status` reserved, not implemented; `IntegrationTestLog` history is permanent by design

**Decision:** Two small points folded in at the user's freeze review, before Module 9A was finalized. First, `IntegrationConfig` gained a `health_status: str | None = None` field (vocabulary reserved in `constants.py:HealthStatus` — `healthy`/`warning`/`error`) with no reader or writer anywhere — not exposed in any API response or UI. Second, `IntegrationTestLog` was confirmed as permanent, unbounded history — no TTL, no pruning, no delete endpoint exists or is planned for it; this was already how the module was built, not a new change.

**Why:** The user's own explicit instructions: "I would add one field in the future... Health Status. No need to implement now — just reserve it for later," and "Keep `integration_test_logs` for history. Don't delete old logs... Historical logs are valuable" (to later answer "why did Meta stop working," "how often is WhatsApp unavailable," etc.). Reserving `health_status` now (rather than adding it later) means a future round that computes it from `last_success_at`/`last_failure_at` needs zero migration. Same "reserve a slot, no logic" posture as `ReferralPartner.parent_partner_id` (decision 080) and `ScheduledReport` (decision 085).

**Impact:** `backend/app/features/integrations/{constants,models}.py` only — no API/schema/UI change, no test-log retention code change (there was nothing to change).

---

**Freeze:** API Management (Module 9A) is approved and frozen, after two small additions folded in first: a reserved (not implemented) `health_status` field, and confirming `integration_test_logs` is permanent history by design (decision 096). No frozen module was modified. Future sub-modules (9B Lead Capture onward) consume its `IntegrationConfig`/provider catalog read-only rather than modifying its engine, models, or APIs.

**Unified freeze policy reconfirmed:** Foundation through API Management (Module 9A) — thirteen modules/sub-modules — are all frozen under one rule: no architectural modifications, only bug fixes, security fixes, or explicitly approved business changes, as Module 9B (Lead Capture) begins.

# Module 9B — Lead Capture

## 097 — One shared pipeline (Webhook → Provider → Parser → Lead); every source reuses `LeadService.create_lead` unmodified

**Decision:** `LeadCaptureService._process_raw_payload` is the single function every capture source funnels through: parse the source's own payload shape (source-specific code, `parsers.py`/`meta_client.py`) → resolve Source Mapping (`CaptureSource`) → call Module 6A's frozen, unmodified `LeadService.create_lead` → write a Timeline entry → record an idempotency receipt if the source has one. Website form, Meta Lead Ads, and the retry queue all call this exact same function — a retried capture behaves identically to a first attempt, and a future source (Google Forms, Facebook, a partner API) only needs a new parser function, never a new pipeline.

**Why:** Per explicit instruction: "Build a generic webhook framework. Don't build Meta-specific code everywhere. Instead: Webhook → Provider → Parser → Lead." Reusing `create_lead` directly (rather than reimplementing Lead creation) is the same reuse pattern Module 7 already established for Referral Partner leads — it gets duplicate-flagging (`duplicate_of_lead_ids`, decision 041), id generation, and audit logging for free, with zero new Lead-creation logic to get wrong.

**Impact:** `backend/app/features/lead_capture/{service,parsers,meta_client}.py`. No change to `app/features/leads/*` (frozen, Module 6A).

## 098 — System actor for unauthenticated captures: a real, persisted Owner, `created_by` nulled out immediately after

**Decision:** Website form submissions and Meta webhook notifications have no authenticated human in the loop, but `LeadService.create_lead` requires a real `User` with a persisted `id` (its `actor.require_id()` call would otherwise raise). `LeadCaptureService._system_actor()` fetches any real, persisted Owner (`find_many({"role": "owner"}, limit=1)`) to satisfy that requirement, then immediately issues `LeadRepository.update(lead_id, {"created_by": None})` so the resulting Lead never looks like that Owner personally created it. Manual API capture (an authenticated Owner/Employee) needs none of this — the real caller is the actor throughout.

**Why:** This is the exact same "technical actor, then correct the attribution" pattern `CustomerService._any_owner()` already established for Module 6B's direct-portal registration (decision 053) — there is no `"system"` role in this project (`app.constants.roles.ALL_ROLES` is a closed set), and no in-memory synthetic `User` can be constructed either (`require_id()` requires a real persisted `id`). Reusing an established precedent here, rather than inventing a new "system user" concept, keeps the codebase's actor model consistent.

**Impact:** `backend/app/features/lead_capture/service.py:_system_actor`. The real provenance ("captured via website form," "captured via Meta," which external id) is recorded on the Lead's own Timeline (a new `LeadActivity(event_type="captured", ...)` row — `event_type` is a free-form `^[a-z_]+$` field, not a closed enum, so this needed no change to Module 6A) — that, not `Lead.created_by`, is the meaningful "Imported By" trail the brief asked for.

## 099 — Capture Failures: every inbound request that doesn't become a Lead is recorded, never silently dropped; only `api_error` retries automatically

**Decision:** `CaptureFailure` (duplicate/invalid_data/missing_required_fields/api_error) is written for every capture that doesn't succeed — including a malformed Website form submission, which still gets a clear 422 response *and* a persisted record (the request schema is deliberately lenient/all-optional so FastAPI's own automatic validation never rejects a payload before the service gets a chance to log it). Only `failure_reason=api_error` (a transient/technical condition — e.g. Meta's Graph API being temporarily unreachable) is retried automatically, on a backoff schedule (15 minutes, doubling each attempt, up to `MAX_RETRY_ATTEMPTS=5` before giving up as `exhausted`). Duplicate/invalid_data/missing_required_fields are permanent until a human fixes the source data — logged as `ignored`, never retried, since retrying the exact same bad data would just fail again.

**Why:** Per explicit instruction: "Never lose inbound requests," with the worked example "Meta → Temporary Failure → Retry → Lead Created. Instead of simply dropping the lead." Distinguishing retryable-vs-not by failure reason (rather than retrying everything, or nothing) avoids both silently losing a recoverable failure and wastefully re-attempting a request that can never succeed as-is.

**Impact:** `backend/app/features/lead_capture/{models,service}.py:CaptureFailure`, `app/worker/tasks/lead_capture.py:retry_capture_failures` (new Arq cron job, every 15 minutes, registered in `worker_settings.py`).

## 100 — Meta webhook: real HMAC-SHA256 signature verification + a real, live Graph API lead-retrieval call — Lead Retrieval is genuinely in scope here, unlike 9A's Test-Connection-only constraint

**Decision:** `POST /lead-capture/webhooks/meta` verifies Meta's `X-Hub-Signature-256` header via `hmac.compare_digest` (constant-time, mirroring the existing primitive in `app/security/hashing.py`) against the active Meta `IntegrationConfig`'s `webhook_secret` (Module 9A) — signature mismatch is a bare 403, no processing attempted. Once verified, each `leadgen_id` in the notification triggers a real, live call to Meta's Graph API (`GET /{leadgen_id}?fields=field_data`) using that same config's `access_token`, to retrieve the lead's actual field values — the webhook notification itself carries no field data, only a reference. The `GET /lead-capture/webhooks/meta` verification handshake (`hub.mode`/`hub.verify_token`/`hub.challenge`) is also implemented, checked against the config's `webhook_verify_token`.

**Why:** Unlike Module 9A's Test Connection (explicitly never a business action), Module 9B's whole purpose *is* the business action of capturing a real lead — "Lead Retrieval" is named directly in the brief's own Meta bullet list. This is the first place either `webhook_verify_token` or `webhook_secret` (stored, encrypted, since 9A) is actually read and used — 9A's own `KNOWN_LIMITATIONS.md` flagged this as future work, and this module is exactly that future work.

**Impact:** `backend/app/features/lead_capture/meta_client.py` (new — signature/challenge verification, Graph API call, Meta's own `field_data` shape parsing). No change to `app/features/integrations/*` (frozen, Module 9A) — read-only reuse of its stored, encrypted config.

## 101 — Idempotency via `CaptureReceipt`, only where a real external id exists (Meta); Website/Manual rely on 6A's own cross-lead duplicate flagging

**Decision:** `CaptureReceipt` (capture_source, external_id, lead_id — unique per source+id) prevents a retried Meta webhook delivery for the same `leadgen_id` from creating a second Lead — checked before processing, recorded after a successful capture. Website form submissions have no natural external id and don't use this mechanism at all; Module 6A's own `duplicate_of_lead_ids` cross-lead flagging (decision 041, "flags but never blocks") still applies to every capture path regardless, unaffected by this idempotency check — the two are answering different questions ("is this the exact same inbound notification I already processed?" vs. "does a Lead with this mobile number already exist?").

**Why:** Meta's own webhook delivery contract can and does redeliver the same notification (network retries, at-least-once delivery) — without this check, a single real-world lead could turn into several duplicate `Lead` rows. Website forms have no equivalent problem to solve (a visitor re-submitting the same form twice is a *different* concern — genuinely two submissions — that 6A's own duplicate flagging already handles by design, not a delivery-retry artifact).

**Impact:** `backend/app/features/lead_capture/{models,repository,service}.py:CaptureReceipt`. No change to `Lead.duplicate_of_lead_ids`'s existing behavior.

## 102 — Source Mapping: a seeded `CaptureSource` catalog, remappable, never hardcoded

**Decision:** `CaptureSource` (website_form/meta_lead_ads/manual_api) stores which Module 4 `lead_sources` row each capture channel attributes its leads to (`lead_source_id`), plus an optional default product mapping (`default_product_category`/`default_product_id`) for sources like Meta that don't naturally carry product information in their payload. Seeded once (resolving Module 6A's own seeded Lead Source names — "Website"/"Meta"/"Manual" — to their ids), then Owner-remappable via `PATCH /lead-capture/sources/{key}` with zero code change.

**Why:** Per explicit instruction: "Source Mapping. Never hardcode. Map: Meta → Lead Source → Settings → Lead." Matches the same "seeded config, Owner-remappable, no code change" posture used by `WorkflowDefinition`/`ReminderRule`/`CommissionRule`/9A's own `IntegrationProvider` catalog.

**Impact:** `backend/app/features/lead_capture/models.py:CaptureSource`, `scripts/seed.py:seed_capture_sources`. No change to `system_settings.lead_sources` (Module 4, frozen) — read-only reference.

## 103 — Three reservations folded in at the freeze review: `webhook_events`, Lead Source Metadata, Website Form Version

**Decision:** Three small additions, all explicitly "reserve, don't implement": (1) `WebhookEvent` (`webhook_events` collection) — a model only, no repository, no service usage, no index; reserved for future observability (recording *every* inbound webhook event, not just failures). (2) `ParsedLead.source_metadata: dict[str, str]` — a passthrough of whatever campaign/ad set/ad/form/UTM identifiers a source's own raw payload happens to carry (`parsers.py:extract_source_metadata`, keyed on `form_id`/`form_version`/`campaign_id`/`adset_id`/`ad_id`/`utm_source`/`utm_campaign`/`utm_medium`) — never fabricated when a source doesn't supply one. (3) `WebsiteCaptureRequest.form_version`/`utm_source`/`utm_campaign`/`utm_medium` — new optional fields feeding the same passthrough. All three are recorded on the Lead's own Timeline (`LeadActivity.metadata["source_metadata"]`) for every successful Website/Meta capture.

**Why:** The user's own explicit instructions, all phrased the same way — "No need to implement now — just keep it in mind" / "make sure the architecture can accommodate it" / "no implementation required now." `webhook_events` stays a genuinely inert schema reservation (matching decision 080/096's "field/model exists, nothing uses it yet" posture) since building real observability infrastructure wasn't asked for. Source Metadata and Form Version, by contrast, needed only a trivial passthrough (the data was already flowing through each source's raw payload/request; capturing it costs nothing and avoids losing it before a future round builds real Campaign/ROI reporting on top) — genuinely satisfying "don't force it if not available" by construction, since `extract_source_metadata` only ever includes keys that are actually present.

**Impact:** `backend/app/features/lead_capture/models.py:WebhookEvent` (new, unused), `parsers.py:{ParsedLead.source_metadata,extract_source_metadata}`, `schemas.py:WebsiteCaptureRequest` (4 new optional fields), `service.py` (`_parse_meta_entry` passes the raw webhook entry through; `_process_raw_payload`'s `LeadActivity` write includes `source_metadata`). No new collection is actually written to (`webhook_events` has zero call sites) and no existing behavior changed — a website/Meta capture that supplies none of these optional fields behaves exactly as before.

---

**Freeze:** Lead Capture (Module 9B) is approved and frozen, after three reservations folded in first (decision 103): an inert `webhook_events` collection reserved for future observability, and a Lead Source Metadata / Website Form Version passthrough (captured only when a source's payload actually supplies it, never fabricated). No frozen module was modified. Future sub-modules (9C Communication onward) consume its `Lead`/`CaptureSource` data read-only rather than modifying its engine, models, or APIs.

**Unified freeze policy reconfirmed:** Foundation through Lead Capture (Module 9B) — fourteen modules/sub-modules — are all frozen under one rule: no architectural modifications, only bug fixes, security fixes, or explicitly approved business changes, as Module 9C (Communication) begins.

# Module 9C — Communication Engine

## 104 — `Business Module -> Communication Service -> Queue -> Provider Adapter -> Provider -> Delivery Status -> Communication History`, triggered by polling `audit_logs` — no frozen module is modified

**Decision:** `CommunicationService.poll_business_events` (an Arq cron job, every 2 minutes) scans the existing, already-written `audit_logs` collection for 5 fixed audit `event_type` values — `lead_assigned`, `notification_created` (filtered to `notification_type == "reminder_triggered"`), `application_submitted`, `workflow_documents_requested`, `commission_entry_created` — each mapped to one of this module's own named `BusinessEvent` values. For each matching row, it resolves a recipient using the owning frozen module's own existing repository class (`EmployeeRepository`/`CustomerRepository`/`ReferralPartnerRepository`/`UserRepository`, all read-only), then enqueues a `CommunicationQueueItem` per available channel if an active template exists for that (category, channel) pair. A per-business-event checkpoint (`communication_checkpoints`, mirroring 6D's own `notification_checkpoints`) means each run only scans genuinely new rows.

**Why:** Per explicit instruction: "Build a centralized communication service that uses the providers configured in Module 9A and is triggered by business modules such as Leads, Customers, Workflow, Reminder Engine, and Referral Partner. Do not modify any frozen modules." This is the exact same "lazy scan of a read-only, already-existing signal" pattern Module 6D established for its own notification engine (decision 065) and Module 7/9B both reused since — applied here for a third time, for a different consumer, with zero changes to any of the five business modules being consumed.

**Impact:** `backend/app/features/communication/{constants,models,repository,service}.py` (new). `app/worker/tasks/communication.py`, registered in `worker_settings.py`. No change to `app/features/{leads,customer,workflow_engine,reminders,referral_partner_management}/*` (all frozen) — every audit event type and metadata shape consumed here was confirmed by reading each module's own existing `write_audit_log` call sites, never guessed.

## 105 — Provider Adapter Pattern: one real function per channel behind a common interface; WhatsApp/SMS generic HTTP, Email real SMTP or generic HTTP

**Decision:** `app/features/communication/adapters.py` defines one `DeliveryOutcome{success, provider_message_id, error, is_transient, response_time_ms}` interface and one function per channel, registered in an `ADAPTERS` dict the queue processor dispatches through by channel name alone — never branching on provider identity. WhatsApp and SMS send via a generic HTTP POST to the active `IntegrationConfig`'s own `api_url` (Bearer auth) — there is no single fixed API contract to target more deeply, since the brief itself asks these to support arbitrary future providers. Email sends a real message via `smtplib` (STARTTLS + login, off the event loop via `asyncio.to_thread`) when the active config looks like SMTP (`host` present), or a generic HTTP POST for an API-based email provider otherwise.

**Why:** Per explicit instruction: "Each provider must implement the same interface... Future providers should plug into the same interface." This is the same "real checks where the API is well-known, generic reachability where the provider is open-ended" honesty Module 9A's own Test Connection already established (decision 094) — except here the action is a genuine send, not a connection check, so Email's SMTP path goes further and actually delivers a message (9A's own SMTP check deliberately stops at `QUIT` without sending).

**Impact:** `backend/app/features/communication/adapters.py` (new — the only file in this module with real network/SMTP send code). `tests/api/test_communication.py` monkeypatches `app.features.communication.adapters.ADAPTERS` (a shared dict reference, same technique 9A's own `TESTERS` dict monkeypatching used) to avoid live network/SMTP calls — no real WhatsApp/SMS/SMTP credentials exist anywhere in this project.

## 106 — Owner-authored templates only, ships empty; OTP is a reserved category, deliberately excluded from this engine

**Decision:** `CommunicationTemplate` (Channel, Category, Subject [Email only], Body, Variables [derived, never hand-entered], Language) ships with zero seeded rows — the exact same posture as Module 6D's own Notification Templates (decision 029). A minimal template engine (`template_engine.py`) does `{{variable_name}}` substitution only, no conditionals/loops; a missing variable is left as the literal placeholder rather than raising, so one typo in one template can't take down the whole queue processor. Separately: `TemplateCategory.OTP` exists in the vocabulary (the brief names OTP as an example category), but OTP delivery itself is **never** routed through this queue — Auth (Module 1) is frozen and its OTP delivery must remain synchronous (a queued, polled send arrives too late to satisfy an OTP's whole purpose). OTP keeps using whatever direct send path Auth already has; this module changes nothing about it.

**Why:** Per explicit instruction: "Do not hardcode message content inside business logic," matching the same "engine is code, catalog is data" split used throughout this project. The OTP exclusion is a scope decision reached by directly checking Auth's own OTP send path (frozen, synchronous, request-response) against this engine's own architecture (async, queued, polled, retried with backoff) — the two are fundamentally incompatible for a time-sensitive one-time code, not an oversight to fix later.

**Impact:** `backend/app/features/communication/{models,template_engine}.py`. No change to `app/features/auth/*` (frozen, Module 1) — OTP delivery is completely untouched by this module.

## 107 — Recipient resolution is read-only against each frozen module's own repository; a dedicated `communication_checkpoints` cursor, separate from 6D's own

**Decision:** `CommunicationService._entity_ref_and_contact` resolves a mobile/email pair per business event entirely by reading each owning frozen module's own existing, already-public repository class — `EmployeeRepository.find_by_id` (Lead Assigned), a role-dispatching `_resolve_user_contact` helper across `UserRepository`/`EmployeeRepository`/`CustomerRepository`/`ReferralPartnerRepository` (Reminder Triggered, since `User` itself has no email field), `CustomerRepository.find_by_user_id`/`find_by_id` (Application Submitted / Document Requested), and `ReferralPartnerRepository.find_by_id` (Commission Ready). None of these repositories are modified. A new `CommunicationCheckpoint` model/collection (`communication_checkpoints`) tracks each business event's own polling cursor — a separate collection from Module 6D's `notification_checkpoints` rather than sharing it, since sharing would mean an unrelated consumer (this module) writing into a frozen module's own collection.

**Why:** Reusing each frozen module's own existing repository methods (rather than querying `db["employees"]`/etc. directly, or duplicating query logic) keeps this module additive-only, per the freeze policy. A dangling reference (e.g. an Employee deleted after the triggering audit-log row was written) is simply skipped — there's no recipient to notify, and this isn't treated as a `capture_failures`-style error since it's not a delivery failure, just an unresolvable event (documented in `KNOWN_LIMITATIONS.md`).

**Impact:** `backend/app/features/communication/{models,repository,service}.py`. No change to `app/features/{employee,customer,referral_partner_management,auth}/repository.py` (all frozen) — every read goes through their existing public methods.

## 108 — Retry only transient failures, exponential backoff, `MAX_RETRY_ATTEMPTS=5`; manual Retry Action reuses the same send path

**Decision:** A failed send is classified by the adapter itself (`DeliveryOutcome.is_transient`) — a permanent failure (no active integration configured, a clearly invalid recipient) goes straight to `QueueStatus.FAILED` and is never retried automatically. A transient failure (network/timeout/5xx-shaped) schedules a retry with exponential backoff (`RETRY_BACKOFF_MINUTES=5 * 2^attempt`), up to `MAX_RETRY_ATTEMPTS=5`, after which it becomes `QueueStatus.EXHAUSTED`. The manual Retry Action (`POST /communication/queue/{id}/retry`, only valid on `failed`/`exhausted`) calls the exact same `_send_one` function a scheduled worker run would use — there is no separate "manual send" code path to keep in sync.

**Why:** Per explicit instruction: "Retry only transient failures. Configurable retry attempts. Use exponential backoff. Permanent failures should not retry." The same retry-classification and backoff shape Module 9B's own `capture_failures` retry queue already established (decision 099) — reused here for a second, unrelated queue, rather than inventing a new retry policy.

**Impact:** `backend/app/features/communication/service.py:{_send_one,_finalize_failure,retry_message_now}`, `app/worker/tasks/communication.py:{process_pending_queue,process_retry_queue}` (two Arq cron jobs — pending every minute, retries every 5 minutes).

---

**Freeze:** Communication Engine (Module 9C) is approved and frozen. No frozen module (Leads, Customer, Workflow Engine, Reminders, Referral Partner Management, Access Control) was modified — every trigger is consumed via the existing `audit_logs` collection (decision 104), every recipient resolved via each module's own existing repository methods (decision 107). One unrelated pre-existing bug was fixed in a frozen module's frontend during this round's verification: `LeadCapturePage.tsx`'s `loadSources` callback (an arrow function with an expression body) returned a `Promise` to `useEffect`, which `npm run build`'s `tsc -b` rejects (plain `tsc --noEmit` does not catch it) — wrapped in a block body so it returns `void`; no behavior change, permitted under the freeze policy's "bug fixes" allowance.

**Unified freeze policy reconfirmed:** Foundation through Communication Engine (Module 9C) — fifteen modules/sub-modules — are all frozen under one rule: no architectural modifications, only bug fixes, security fixes, or explicitly approved business changes, as Module 9D (Future Integrations) begins.

# Module 10 — Geo Fencing (Stage 1 of the Geo Fencing / Temporary Permissions / MSG91 request)

Out-of-original-roadmap work, explicitly requested by the user (same "later message expands scope" precedent as Owner Account Management) and delivered in stages: Stage 1 (Geo Fencing + real enforcement, this module) → Stage 2 (MSG91 provider) → Stage 3 (Bulk Messaging + CRM record linkage), each with its own check-in.

## 109 — `GeoFence` (a named work-area with a radius and allowed activities) is the first real use of the `geo_fencing` folder; Temporary Permissions and Geo Fencing Exceptions (Module 3) already existed and are reused unmodified where possible

**Decision:** Before writing any code, the existing system was inspected rather than assumed empty. Two of the five requested capabilities were already fully built by Module 3 (Access Control): **Temporary Permissions** (`TemporaryAccess` — grant/revoke, enforced live inside `PermissionEngine._check_temporary_access`, with a working frontend page at `/temporary-access`) and **Geo Fencing Exceptions** (`GeoException` — grant/revoke, Owner-only, audited, IDOR-safe, frontend page at `/geo-exceptions`), explicitly documented in that page's own code comment as "administrative record-keeping only — there's no geo-fencing enforcement engine yet to except from." Neither was rebuilt. What was genuinely missing — a named `GeoFence` area (Area Name/Address/Lat/Lng/Radius/Allowed Activities/Status) and a real enforcement engine to check against — is new: `backend/app/features/geo_fencing/{models,schemas,repository,service,mappers,indexes,dependencies,router,enforcement,geomath}.py`, gated with `require_permission("geo_fencing", "fences", action)` (Access Control's own engine, not a new authorization mechanism), following the exact per-feature file layout every other module uses.

**Why:** The task's own instructions required inspecting the existing architecture before changing anything and reusing existing patterns rather than duplicating them — doing so here avoided rebuilding two already-complete, tested features from scratch.

**Impact:** New module `backend/app/features/geo_fencing/*`, wired into `app/main.py` (router + index registration, additive lines) and `scripts/seed.py` (one new `Permission(module="geo_fencing", resource="fences", ...)` catalog entry, same pattern as every prior module). New frontend `frontend/src/features/geo_fencing/{api.ts,pages/GeoFencingPage.tsx}`, reachable at Settings → Geo Fencing (`SettingsLayout.tsx`/`SettingsHomePage.tsx`/`router.tsx`, additive entries). No file under `app/features/access_control/{router,service}.py`'s existing endpoints, or the existing `TemporaryAccessPage.tsx`, was touched.

## 110 — `GeoException` gains an optional `geo_fence_id` (additive extension to a frozen Module 3 model), not a rewrite

**Decision:** `GeoException` (frozen, Module 3) gains one new optional field, `geo_fence_id: str | None = None`. `CreateGeoExceptionRequest`'s `latitude`/`longitude`/`radius_meters` became optional (previously required) with a service-layer rule: at least one of `geo_fence_id` or the 3 coordinate fields must fully resolve the exception's own area, else a 422. When `geo_fence_id` is supplied, the service looks up the fence and **prefills** (never references live) `allowed_location`/`radius_meters` from it — the exception keeps its own copy, so editing or deleting the fence later never invalidates an already-granted exception, and an exception can still deliberately override with different coordinates than its fence (e.g. "let them work from home today"). The frontend `GeoExceptionPage.tsx` gained a "Geo Fence" dropdown (reusing the existing `SelectField` component already used on `TemporaryAccessPage.tsx`) that autofills the 3 fields on selection, still editable — every existing field/behavior (freeform creation, revoke, list) is unchanged, proven by the pre-existing `test_geo_exception_create_list_revoke` test passing unmodified.

**Why:** The spec's own mockup for Geo Fencing Exceptions shows a "Geo Fence *" dropdown, not freeform coordinates — but Module 3's `GeoException` predates `GeoFence`'s existence and has real production-shaped test coverage. An additive, backward-compatible extension (same category of exception this codebase's history already used for the Secure Application Link button, decision 052/053, and the reset-password bug fix, decision 031) satisfies the new requirement without risking the existing, working feature.

**Impact:** `backend/app/features/access_control/{models,schemas,service,mappers,repository,indexes}.py` (all additive — one new field, one new optional request field, one new repository method `find_active_by_fence_id` used by `geo_fencing`'s own safe-delete check, one new index). `frontend/src/features/access_control/{api.ts,pages/GeoExceptionPage.tsx}`. Two new tests added to `tests/api/test_access_control.py`; the file's 14 pre-existing tests are untouched and still pass.

## 111 — Enforcement is wired to exactly two activities (`lead_creation`, `document_collection`); `customer_visit`/`loan_application`/`insurance_application` remain selectable but unenforced

**Decision:** The spec's example `allowed_activities` are Lead Creation, Customer Visit, Document Collection, Loan Application, Insurance Application. Investigation found only two map to a real, single, employee-initiated action anywhere in this codebase: `POST /leads` (`leads/router.py:create_lead`) and `POST /{case_id}/documents/verify` (both `loan_management/router.py` and `insurance_management/router.py`, chosen as the closest "employee collected/verified documents" action). "Customer Visit" has no check-in/visit feature anywhere in this system. "Loan Application"/"Insurance Application" have no employee-side *creation* action at all — Applications are only ever submitted by the Customer through the frozen Customer Portal flow (`customer/router.py POST /applications`); every staff-side Loan/Insurance action is a *processing* step on an already-existing case (notes, assign, hold, verify-documents, offer, disburse), none titled "Application." All 5 values remain valid, storable `allowed_activities` choices on a `GeoFence` (for completeness with the spec's field list and possible future use), but only the two above actually call `enforce_geo_fence`.

**Why:** Confirmed explicitly with the user before implementation (same resolution applied consistently to all three ambiguous activities): build real enforcement only where a real single action exists to attach it to, rather than force-fitting it onto an unrelated multi-step case-processing action or inventing new functionality (a visit/check-in feature) beyond the requested scope.

**Impact:** `backend/app/features/{leads,loan_management,insurance_management}/router.py` each gained exactly one optional coordinate parameter and one `await enforce_geo_fence(...)` call immediately before the existing service call — no other line in any of these three frozen router functions changed. A caller that never sends coordinates (every existing test, every existing mobile/API client) behaves byte-for-byte as before, proven by `test_create_lead_end_to_end_unaffected_when_no_fence_configured` and the unchanged pass rate of the full pre-existing test suite (298 passed / 15 pre-existing failures, identical failure set to the pre-Stage-1 baseline).

## 112 — Enforcement resolution: any matching active fence allows; a valid `GeoException` bypasses the distance check entirely; fence overlap is a non-blocking warning, not a conflict

**Decision:** `enforce_geo_fence` (`app/features/geo_fencing/enforcement.py`): Owner bypasses entirely (superuser, matching every other engine in this codebase). If zero active fences list the activity, it's a silent no-op — geo-fencing is opt-in per activity, never a blanket restriction. If fences exist but no coordinates were supplied, it rejects with "Location is required for this action." — never silently allows. It then checks the employee's active `GeoException`s using the *exact same* daily-recurring-window logic `PermissionEngine` already uses for Temporary Access (extracted to a shared `app/utils/datetime.py:within_daily_window`, replacing `permission_engine.py`'s own private copy, behavior unchanged) — a currently-valid exception allows regardless of distance. Otherwise, a haversine great-circle distance (stdlib `math`, no mapping SDK) is computed against every candidate fence; being inside **any** matching active fence's radius allows (naturally handles "multiple matching fences"). Every outcome — allowed or denied — writes one audit log entry via the existing shared `write_audit_log`, recording activity/employee/which fence-or-exception matched, but never raw coordinates. Two fences whose radii overlap are flagged as a non-blocking warning (`overlaps_with` in the API response) rather than rejected — two legitimately close branches/work-areas is a real business case, not a data-entry mistake to block.

**Why:** Matches the spec's own explicit rules ("never trust frontend-only allowed=true," "only enforce where configuration says it applies," "don't expose unnecessary sensitive location information") while reusing rather than duplicating Module 3's existing time-window evaluation logic.

**Impact:** `backend/app/features/geo_fencing/{enforcement,geomath}.py` (new). `backend/app/utils/datetime.py` (new `within_daily_window`, moved from `permission_engine.py`'s private `_within_daily_window` — identical logic, `access_control/permission_engine.py`'s only change is importing it instead of defining it locally). `tests/api/test_geo_fencing.py` — 30 new tests covering CRUD, validation, permission-gating/IDOR, and every enforcement branch (no fence configured, inside/outside radius, missing coordinates, valid/expired exception, multiple matching fences, Owner bypass, the second enforced activity) plus 3 true end-to-end tests through `POST /leads`.

---

**Stage 1 status:** Geo Fencing (GeoFence CRUD + real enforcement) is complete and tested. Temporary Permissions and Geo Fencing Exceptions required no new backend/frontend work beyond decision 110's additive `geo_fence_id` link. Stages 2 (MSG91 + Communication Providers) and 3 (Bulk Messaging + CRM record linkage) are separate, not-yet-started follow-on work — see `docs/KNOWN_LIMITATIONS.md`'s Module 10 section for what remains.

## 113 — Communication Providers reuses Module 9A's `IntegrationConfig` storage unmodified; it is a filtered frontend view, not a new backend feature

**Decision:** MSG91 credentials live in the exact same encrypted `IntegrationConfig` collection every other provider (Meta, generic WhatsApp/SMS/Email, Google Maps) already uses — no new credential store, no schema change to `IntegrationConfig` itself. `msg91` was added as a seeded `IntegrationProvider` catalog row for all 3 required channels (`scripts/seed.py`, matching the exact pre-existing upsert pattern every other provider row uses). The new Settings → Communication Providers page (`/settings/communication-providers`) calls the same `integration-configs`/`integration-providers` API the existing Connections (API Connections) page already uses — `create/update/enable/disable/activate/test` — filtered client-side to `provider === "msg91"` and grouped one card per channel to match the spec's own mockup. `CreateConfigForm`/`StepHeading`/`TYPE_LABELS` were exported (additive — `export` keyword only, zero behavior change) from the existing, frozen `IntegrationListPage.tsx` and reused rather than rebuilding the same credential-entry + Test Connection flow a second time.

**Why:** Per the user's own explicit instruction for this stage: "use the existing encrypted IntegrationConfig storage." Reusing the platform Module 9A already built (encryption, masking, one-active-per-type, Test Connection history) rather than duplicating it satisfies "reuse existing patterns" and avoids a second credential-storage mechanism to keep in sync.

**Impact:** `scripts/seed.py` (3 new `IntegrationProvider` rows). `frontend/src/features/integrations/pages/IntegrationListPage.tsx` (3 `export` keywords added, no other change — the page's own behavior is byte-for-byte unchanged, proven by the existing `test_integrations.py` suite passing unmodified). New `frontend/src/features/communication/pages/CommunicationProvidersPage.tsx`, `frontend/src/features/integrations/providerFields.ts` (MSG91-specific field lists, additive). No backend endpoint, model, or schema under `app/features/integrations/` was changed.

## 114 — MSG91 SMS (Flow API v5) and WhatsApp (template outbound API) are real, sourced implementations; the adapter interface gained 3 optional keyword arguments, ignored by every existing/non-MSG91 path

**Decision:** `communication/adapters.py`'s `send_sms`/`send_whatsapp` branch to a real MSG91 API call when the active config's own `provider == "msg91"` (threaded into the adapter call via a `_provider` key `_send_one` injects into the decrypted config dict — the queue processor itself never branches on provider identity, unchanged). SMS uses MSG91's Flow API (`POST https://api.msg91.com/api/v5/flow/`, body `{flow_id, sender, recipients: [{mobiles, VAR1, VAR2, ...}]}`), chosen over the older `v2/sendsms` specifically because DLT compliance requires an approved template, matching the spec's own DLT Entity ID/template-configuration language. WhatsApp uses MSG91's template outbound endpoint (`POST .../whatsapp-outbound-message/bulk/`, body carrying `template.name`/`namespace`/`language`/`to_and_components`), since WhatsApp Business never sends arbitrary free text — only a pre-approved provider-side template. Both API contracts were fetched and read directly from `docs.msg91.com`/`api.msg91.com`'s own documentation pages (not guessed) — see `docs/COMMUNICATION.md`'s MSG91 section for the exact sourced shapes. The adapter interface gained `variables: dict[str, str] | None`, `variable_order: list[str] | None`, `provider_template_meta: dict[str, str | None] | None` — all optional, default `None`, threaded from `_send_one`'s already-in-scope `item.variables`/`template.variables`/template's new provider fields; every existing adapter (the 2 generic branches, `send_email`) accepts and ignores them, proven unchanged by the full pre-existing `test_communication.py` suite passing after this change (5 pre-existing test-local fake adapters needed `**kwargs` added to keep accepting calls with the new keyword arguments — a mechanical fix, not a behavior change).

**Why:** Per explicit instruction: "Use the official/current MSG91 API documentation... Do not guess the MSG91 API. Implement only APIs/capabilities actually supported by the configured MSG91 account and current official API." Extending the adapter signature (rather than collapsing every template's variables into one opaque string) was the more correct engineering choice given WhatsApp/DLT templates are inherently positional — the alternative (guessing a single-variable-only template convention) would have been a real correctness compromise, not just a simplification.

**Impact:** `backend/app/features/communication/adapters.py` (MSG91 send functions, error classification, mobile-number normalization — all new; the pre-existing generic/SMTP paths are textually unchanged). `backend/app/features/communication/service.py:_send_one` (provider injection + the 3 new kwargs passed through). `backend/app/features/communication/{models,schemas,mappers}.py` (3 new optional `CommunicationTemplate` fields). `tests/api/test_communication.py` (5 fake-adapter signatures widened with `**_kwargs`). `tests/api/test_msg91.py` (new — adapter unit tests with `_send_msg91_request` monkeypatched, never a live call).

## 115 — MSG91 Email has zero MSG91-specific code — it reuses the existing generic SMTP adapter entirely unchanged

**Decision:** No new code was written for MSG91 Email sending or testing. MSG91 issues standard SMTP relay credentials for transactional email (confirmed via MSG91's own "How to use SMTP in MSG91" help documentation) — `send_email`'s pre-existing `host`-present branch and `test_email`'s pre-existing SMTP test already handle this correctly with no changes. The Owner enters MSG91's own SMTP host/port/username/password (obtained from MSG91's dashboard) into the same generic SMTP fields every other SMTP-based email provider already uses.

**Why:** The alternative — guessing a custom MSG91 Email JSON API contract — was explicitly ruled out: every attempt to source MSG91's own Email API v5 JSON schema from official documentation in this environment returned only navigation/marketing content, never a confirmable request/response shape (see `docs/KNOWN_LIMITATIONS.md`). Rather than fabricate one, using MSG91's own separately-confirmed, standards-based SMTP relay avoids guessing entirely while still delivering a fully real, working MSG91 Email path.

**Impact:** None to `communication/adapters.py`/`integrations/testers.py` — this decision is documented specifically because it deliberately involved writing zero new code, not because any file changed.

## 116 — MSG91 Test Connection via the balance-check endpoint; the DLR webhook uses a shared secret embedded in the callback URL, idempotent on `provider_message_id`, only the sourced SMS payload shape is parsed

**Decision:** `integrations/testers.py` gained `_test_msg91_authkey`, calling MSG91's balance-check endpoint (`GET https://api.msg91.com/api/balance.php?authkey=...&type=4`) — the closest lightweight, read-only, never-a-business-action call MSG91 offers to validate an authkey (MSG91 has no dedicated health/whoami endpoint); shared by both the SMS and WhatsApp testers since one account authkey covers both. A new public route, `POST /communication/webhooks/msg91?secret=...`, receives MSG91's SMS delivery-report callback (`requestId`/`status`/`telNum`/`deliveryTime`, sourced from MSG91's own webhook documentation) and is authenticated by a shared secret embedded in the URL (compared against a `webhook_secret` field stored on the MSG91 SMS/WhatsApp config) rather than a cryptographic signature, since MSG91 does not publicly document an HMAC-style webhook-signing scheme. `CommunicationService.process_delivery_webhook` is idempotent (a duplicate/out-of-order callback for the same `provider_message_id` is a safe no-op) and only ever advances a `sent` item to `delivered`/`failed` — never regresses an already-terminal one, and ignores a callback for an item not yet marked `sent`. Only the SMS payload shape is parsed; a WhatsApp DLR callback (unconfirmed field names) is treated as malformed/unrecognized rather than guessed at.

**Why:** Matches the spec's own explicit rules: "authenticate/verify webhook where supported," "prevent duplicate processing," "never expose secrets," "handle unknown message IDs safely," "handle malformed webhook payloads," and "never mark a message Delivered just because the API accepted it" (this is exactly why `QueueStatus.DELIVERED`/`delivered_at`, reserved since Module 9C, only ever get set by this webhook — never by a successful send). Not fabricating a WhatsApp DLR parser without a confirmed contract follows the same "do not guess the MSG91 API" instruction decision 114 already applied to sending.

**Impact:** `backend/app/features/integrations/testers.py` (`_test_msg91_authkey`, `MSG91_BALANCE_URL`, provider-aware branches in `test_sms`/`test_whatsapp`), `backend/app/features/integrations/{service,schemas}.py` (provider threaded into the tester call for both the real `/test` endpoint and `/test-draft`). `backend/app/features/communication/{router,service,repository,indexes,constants}.py` (new `public_router` + `receive_msg91_webhook`, `process_delivery_webhook`, `verify_msg91_webhook_secret`, `find_by_provider_message_id`, a new index, `AuditEvent.MESSAGE_DELIVERED`/`WEBHOOK_REJECTED`). `backend/app/main.py` (public router registration, additive). `tests/api/test_msg91.py` (webhook secret/malformed-payload/unknown-id/delivered/failed/duplicate/unrecognized-status coverage, plus a direct `process_delivery_webhook` state-machine test).

---

**Stage 2 status:** MSG91 (SMS + WhatsApp + Email) and Communication Providers are complete and tested against mocked provider responses — no real MSG91 account/credentials exist in this environment, so nothing here is live-tested; see `docs/KNOWN_LIMITATIONS.md`'s Stage 2 section. Stage 3 (Bulk Messaging + CRM record linkage) is separate, not-yet-started follow-on work.

## 117 — `send_now()` generalized to require `entity_type`/`entity_id` and accept `template_id` as an alternative to `category`; return type widened to `(success, queue_item_id, error_message)`

**Decision:** `entity_type`/`entity_id` became required keyword arguments (previously hardcoded to a fixed `"secure_link"` placeholder with no real id). Exactly one of `category` (the original, business-event-category lookup) or `template_id` (Stage 3's usage — a person explicitly picks one exact template, e.g. from the Send Message modal's dropdown) must be given. The return type widened from a bare `bool` to `(success, queue_item_id, error_message)` — the one pre-existing caller (`notify_secure_link`) only ever needed the boolean and still only reads it; the new callers (`send_crm_message`) need the real failure reason to show a user-facing error rather than a generic "failed."

**Why:** Per explicit instruction: "Generalize the existing `send_now()` communication capability to accept `entity_type` and `entity_id`." Adding `template_id` as an alternative resolution path (rather than forcing every ad-hoc send to invent a fake business-event category) matches how the spec's own Send Message / Bulk Messaging mockups describe picking a named template directly, not a category.

**Impact:** `backend/app/features/communication/service.py:send_now`. `backend/app/features/customer/service.py:notify_secure_link` — the one existing call site, updated to pass `entity_type="lead", entity_id=lead.require_id()` and unpack the new 3-tuple; `status_map[channel] = "sent" if sent else "failed"` logic itself is unchanged. Proven backward-compatible by the full pre-existing `test_customer.py`/`test_communication.py` suites passing unmodified (same 4 pre-existing `test_customer.py` failures as baseline, unrelated to this change — a `start-signup` 404 that predates Stage 1).

## 118 — Individual "Send Message" (`POST /communication/messages`) resolves the recipient server-side only, and independently re-implements Lead's/Customer's own IDOR rules rather than importing their services (avoids a circular import)

**Decision:** `SendMessageRequest` never carries a recipient address — only `entity_type`/`entity_id`/`channel`/`template_id`/optional extra `variables`. `CommunicationService.send_crm_message` resolves `mobile`/`email` from the Lead/Customer record itself, after two authorization checks: the coarse `communication:send:create` permission, then a per-record scoping check copying (not importing) `LeadService.get_lead_scoped`'s and `CustomerService.get_customer_for_staff`'s own existing rules. Importing those services directly was ruled out: `customer.service` already imports `CommunicationService` (the pre-existing Secure Application Link flow, decision 104's own "no frozen module is modified to call this engine directly, except this one narrow case"), so `communication.service` importing `CustomerService` back would be a circular import; the same choice was made for `LeadService` too, for consistency, even though `leads.service` itself has no such cycle (confirmed by inspecting its imports before writing this code).

**Why:** Per explicit instruction: "Add appropriate authorization/RBAC and IDOR protection for individual and bulk messaging" and "Validate inactive/invalid recipients... expired/invalid secure links." A caller-supplied recipient address would let an authorized-to-message-*a*-Lead actor redirect a message to an arbitrary phone number/email, silently consuming the business's own provider credits — never allowed. Re-implementing (not importing) the two IDOR rules is a real, accepted tradeoff: kept in sync manually, not automatically enforced — see `docs/KNOWN_LIMITATIONS.md`.

**Impact:** `backend/app/features/communication/{schemas,service,router,mappers}.py`. New permission `communication:send` (view/create), seeded in `scripts/seed.py`. No file under `app/features/{leads,customer}/*` was modified beyond decision 117's one-line `notify_secure_link` update. `tests/api/test_communication_stage3.py` — 10 tests covering success (all 3 channels), invalid recipient, missing/wrong-channel template, missing provider config (real error surfaced, not a generic failure), forged entity id (404), unsupported entity_type (422), and 5 IDOR/authorization tests (no permission, unassigned Lead, unassigned Customer, unauthenticated, message-history IDOR).

## 119 — Bulk Messaging: recipients resolved by the caller (reusing existing Lead/Customer search, no new filter engine), enqueue is worker-driven and resumable, idempotency reuses `_enqueue`'s existing dedup key via a synthetic `business_event`

**Decision:** `POST /communication/bulk-messages` accepts a pre-resolved, Owner/staff-chosen `recipient_ids` list (deduplicated at creation) rather than raw filter criteria — the Bulk Messages composer's own recipient picker calls the *existing*, already-authorized `GET /leads`/`GET /customers` staff search endpoints (unmodified) instead of a new dedicated filter-query system. A new `BulkMessageJob` document is created (`status="queued"`), but nothing is sent or even enqueued synchronously in that request. A new Arq cron, `process_bulk_message_jobs` (every minute, alongside the existing `process_pending_queue`/`process_retry_queue`), does the actual per-recipient enqueue in batches of `BULK_ENQUEUE_BATCH_SIZE=100`, persisting a resumable `next_index` cursor after every batch. Each recipient's enqueue reuses the *exact same* `(business_event, entity_type, entity_id, channel)` idempotency check `_enqueue` (the business-event poller's own internal method, decision 104) already performs — scoped to one job via a synthetic `business_event=f"bulk:{job_id}"` string, not a new dedup mechanism, field, or index. Once enqueued (as `PENDING`), every item is picked up and sent by the pre-existing, completely unmodified `process_pending_queue`/`process_retry_queue` cron jobs — bulk messages get the identical retry/backoff/exhaustion behavior as a business-event-triggered or Send-Message-triggered send, with zero special-casing.

**Why:** Per explicit instruction: "Bulk sending must be queued through the existing Arq communication queue, not sent synchronously from the frontend," "Make bulk enqueue idempotent per recipient," and "Respect the existing retry/backoff/failure/exhaustion behavior." Reusing `_enqueue`'s own dedup key (rather than inventing a `(bulk_job_id, recipient, channel)` unique index) means zero new indexes/fields were needed on `CommunicationQueueItem` beyond the two already added for entity-message-linkage (decision 118) and the DLR webhook (Stage 2) — the exact same collection, exact same idempotency primitive, just a different `business_event` string shape. Resolving recipients via the *existing* Lead/Customer search endpoints (rather than a new filter engine matching the original spec's Product/Status/Location/Date/Assigned-Employee mockup) was a deliberate scope reduction — see `docs/KNOWN_LIMITATIONS.md` — to avoid touching the Lead/Customer list pages/backends at all and avoid building a second, parallel filter-query system this round.

**Impact:** New `backend/app/features/communication/models.py:BulkMessageJob`, `repository.py:BulkMessageJobRepository`, and the bulk-messaging half of `service.py`/`schemas.py`/`router.py`/`mappers.py`. `backend/app/worker/tasks/communication.py` (`process_bulk_message_jobs`), `backend/app/worker/worker_settings.py` (one new cron registration, every minute). New permission `communication:bulk` (view/create/edit), seeded in `scripts/seed.py`. `tests/api/test_communication_stage3.py` — 15 bulk-specific tests: dedup at creation, missing/wrong-channel template rejected, empty recipients rejected, permission gating, skip-on-no-contact, **idempotency under simulated worker restart** (force a job back to `processing`/`next_index=0` and re-run — asserts zero duplicate `CommunicationQueueItem`s), **resumability across multiple batches** (a monkeypatched `BULK_ENQUEUE_BATCH_SIZE=1` forces 3 ticks for 3 recipients, asserting `next_index` actually advances incrementally), live progress counts reflecting real send outcomes (via the unmodified `process_pending_queue`), View Failed + Retry Failed (reusing the existing `retry_message_now`), Cancel (queued/processing only; a completed job can't be cancelled), and Customer recipients (not just Lead).

## 120 — Bulk Messaging authorization is feature-level (`communication:bulk:create`), not per-recipient IDOR-scoped like individual Send Message

**Decision:** Unlike `send_crm_message` (decision 118), `create_bulk_message_job` does not check whether the caller is individually authorized (via Lead/Customer assignment) for every recipient in the list — it only requires the `communication:bulk:create` permission itself. Any recipient id the caller's own prior search returned (via the existing, already-authorized `GET /leads`/`GET /customers` endpoints) can be targeted.

**Why:** A "Selected Leads"/"Filtered Leads" bulk campaign is inherently a cross-assignment, feature-level action (an Owner or a delegated manager-type role broadcasting to many records at once) — the spec's own framing never suggested restricting a bulk campaign to only the caller's individually-assigned records, and doing so would make "Filtered Leads" (the spec's own named recipient-source option) largely meaningless for anyone but an Owner. This is a considered, documented choice — flagged explicitly for confirmation in `docs/KNOWN_LIMITATIONS.md`, not silently assumed.

**Impact:** `backend/app/features/communication/service.py:create_bulk_message_job` — no per-recipient authorization check exists there by design. `tests/api/test_communication_stage3.py:test_bulk_job_requires_bulk_permission` proves the feature-level gate is real; no test asserts per-recipient IDOR for bulk, since none is implemented.

## 121 — CRM record linkage reads `communication_queue` directly (not `communication_history`), since a Lead/Customer's Messages panel must also show in-flight (not-yet-terminal) messages

**Decision:** `GET /communication/messages?entity_type=&entity_id=` queries `communication_queue` (`CommunicationQueueRepository.find_for_entity`, a new read-only method + a new `(entity_type, entity_id)` index) rather than `communication_history`. `communication_history` only gets a row once a queue item first reaches a terminal state (`_upsert_history` is called from `_send_one`'s success/failure paths, never at enqueue time) — a message still `pending`/`processing`/`retrying` would be invisible on a Messages panel if it read history instead.

**Why:** The spec's own mockup shows a Lead's Messages panel with per-message channel + status (e.g. "Delivered") — a real-time view of everything ever attempted for that record, not just completed ones. Reading the queue (the always-present source of truth for status, including in-flight) rather than history (a completed-outcome-only projection) is the more correct choice for this specific read.

**Impact:** `backend/app/features/communication/repository.py:CommunicationQueueRepository.find_for_entity`, `indexes.py` (new `(entity_type, entity_id)` index — the pre-existing compound index on `(business_event, entity_type, entity_id, channel)` doesn't serve an entity-only query efficiently since `business_event` is the leading field). Same IDOR scoping as sending (decision 118) applies to this read.

---

**Stage 3 status:** Individual Send Message (Lead + Customer, all 3 channels), CRM message linkage, and Bulk Messaging (idempotent, resumable, retry/backoff-respecting) are complete and tested — 32 new tests (`tests/api/test_communication_stage3.py`), full baseline (328 passed / 15 pre-existing failures) preserved with zero new failures. No real AWS/MSG91 live send was possible in this environment; every test uses a monkeypatched provider adapter, same posture as Stages 1–2. Bulk recipient filtering was deliberately scoped down from the original spec's dedicated Product/Status/Location/Date/Assigned-Employee filter UI to "search + multi-select" reusing existing endpoints — see `docs/KNOWN_LIMITATIONS.md` for the full list of Stage 3 scope decisions and open questions worth confirming.

## 122 — Stage 4 hardening: an uncaught adapter exception can no longer crash the queue-processing loop or strand an item in `PROCESSING` forever; MSG91 webhook secret comparison made constant-time

**Decision:** `_send_one`'s adapter call is now wrapped in a broad `except Exception`, converting any unexpected exception into a normal, non-transient `DeliveryOutcome` failure (marked `FAILED`, error message truncated to 300 characters, no raw traceback stored or returned) — the exact same handling path a provider-reported failure already went through. Separately, `verify_msg91_webhook_secret`'s `stored_secret == provided_secret` became `hmac.compare_digest(stored_secret, provided_secret)`.

**Why:** Found during Stage 4's security review, not asked for in any spec — a genuine, confirmed, pre-existing production blocker, not new feature work, so fixed under the Stage 4 instruction's own "a confirmed production blocker requires a minimal fix" allowance. Concretely reproduced: Python's `email` package raises `email.errors.HeaderParseError` (neither an `OSError` nor an `smtplib.SMTPException`) when a Subject/From/To header value contains an embedded CR/LF — and nothing anywhere validates a Lead's or Customer's `full_name` against control characters, so a self-registered Customer's own name could already trigger this before Stage 3 existed. Uncaught, this exception propagated out of `_send_one`, aborted the entire `process_pending_queue`/`process_retry_queue` `for` loop for that worker tick (every other due item in the same batch of up to 200 silently skipped, that tick), and left the triggering item stuck in `PROCESSING` forever — `find_due_pending`/`find_due_for_retry` only ever query `PENDING`/`RETRYING`, so a `PROCESSING` item is never picked up again by anything. Stage 3's Bulk Messaging materially raises the odds of this actually firing in production (many customer-supplied names flowing through unattended, at scale, instead of one at a time under a staff member's eye). The webhook secret fix closes a real, if narrow (a webhook is a lower-value target than an auth token), timing side-channel identified during the same review pass — trivial, safe, and the exact file/function already under review, not a detour into unrelated code.

**Impact:** `backend/app/features/communication/service.py:_send_one` (new `try/except` around the adapter call, `DeliveryOutcome`/`hmac` imports added), `:verify_msg91_webhook_secret` (comparison only). New `tests/api/test_communication_hardening.py` — 2 tests: an adapter exception marks the item `FAILED` (not stuck in `PROCESSING`, no raw traceback in the stored error), and a bad item in a batch does not prevent a good item later in the same batch from being sent (exercises the real `process_pending_queue` entry point, unmodified). Full regression suite reconfirmed green afterward (see `docs/KNOWN_LIMITATIONS.md`'s Stage 4 section for the exact before/after counts).

## 123 — `GeoException` redesigned to carry no location fields — a bypass of the Geo Fence, not a second one; decision 110's `geo_fence_id` link removed as a consequence

**Decision:** A real production bug report: the "Grant Geo Exception" modal asked for Latitude/Longitude/Radius (plus an optional Geo Fence dropdown to prefill them, decision 110), which models an exception as *another* location restriction rather than what the business rule actually requires — a temporary *bypass* of the Geo Fence restriction for a specific employee/activity during a valid window. `enforce_geo_fence` (`geo_fencing/enforcement.py`) was, in fact, never reading those fields to decide anything — a matching active `GeoException` already short-circuited the distance check unconditionally, before this change, so removing them is a pure data-model correction with zero enforcement-logic change. `GeoException` (`access_control/models.py`) drops `geo_fence_id`, `allowed_location`, `radius_meters`; `CreateGeoExceptionRequest`/`GeoExceptionResponse` follow. Since an exception no longer references any one fence, `GeoFencingService.delete_geo_fence`'s decision-110 safety rule ("blocked while an active GeoException references it") is removed — there is nothing left for a fence delete to invalidate. Separately (same bug report): the modal's Employee dropdown rendered empty because `EmployeeSelect`/`useEmployeeNameMap` requested `page_size=200`, above this app's `MAX_PAGE_SIZE=100` — FastAPI 422s that request and the frontend's own `.catch` silently swallowed it. Fixed at the source (both shared components now request 100), plus a new optional `activeOnly` prop on `EmployeeSelect` (default off, every other call site unchanged) so Geo Exceptions' own dropdown excludes deactivated employees, per the business rule.

**Why:** Per explicit instruction: "a Geo Exception must NOT ask for or require another latitude, longitude, or radius. Do not replace them with another location field." Confirmed by re-reading `enforce_geo_fence` itself before touching anything — the exception's location fields were already fully inert (see decision 112's own resolution order, unchanged by this decision), so this is a model/API/UI correction, not a behavior change to any enforcement path.

**Impact:** `backend/app/features/access_control/{models,schemas,service,mappers,repository,indexes}.py` (all field/method removals, no new fields). `backend/app/features/geo_fencing/service.py` (`delete_geo_fence` safety-rule removal, `ConflictError`/`GeoExceptionRepository` imports dropped). `frontend/src/features/access_control/{api.ts,pages/GeoExceptionPage.tsx}` (Geo Fence dropdown and lat/lng/radius fields removed from the modal; list columns reordered to Employee/Activity/Reason/Start Date/End Date/Time Window/Status/Actions). `frontend/src/components/forms/{EmployeeSelect.tsx,useEmployeeNameMap.ts}` (`page_size` fix; `EmployeeSelect` also gained loading/empty/error states and the `activeOnly` prop). `tests/api/test_access_control.py`/`tests/api/test_geo_fencing.py` — every `GeoException`-constructing test updated to drop the removed fields; new tests for a blanket ("All Activities") exception covering two different enforced activities, an activity-scoped exception NOT covering a different activity, a revoked exception no longer bypassing, an unknown `employee_id` being rejected, and the `/employees?status=active` filter the dropdown itself relies on.

## 124 — Global timezone standardization to IST (Asia/Kolkata): UTC stays the canonical storage instant everywhere; a new centralized IST utility (backend + frontend) governs every business-day/business-hour calculation; MongoDB reads become tz-aware at the client level, the actual root cause of the "wrong clock" symptom

**Decision:** The immediate bug report (decision 123's Geo Exception feature evaluating business hours against the wrong clock) turned out to be one symptom of a codebase-wide gap: nothing anywhere resolved "business time" as IST — every "today"/"this month"/daily-window/report-date-range calculation was silently built on UTC wall-clock instead. A full audit (two parallel research passes over backend and frontend, plus direct verification of every finding) established, before any code changed: (1) the backend's internal datetime discipline was already good — zero raw `datetime.utcnow()`/`date.today()` calls exist, everything already funnels through a shared `utc_now()`; (2) the real defect was conceptual, not syntactic, confined to a small, enumerable set of "UTC midnight treated as the business-day boundary" call sites; (3) a second, independent, root-cause bug existed in parallel — Motor's default client decodes stored datetimes as **naive**, so API responses serialized timestamps with no `Z`/offset; a naive ISO string is parsed by JS `Date` as **browser-local time**, not UTC, meaning every frontend timestamp display was silently mis-interpreting a real UTC instant as if it were already the viewer's local time — for an India-based viewer this reproduces exactly the "shows the raw UTC clock value instead of IST" symptom described in the bug report, across the entire app, not just Geo Fencing; (4) auth/token/OTP/lockout expiry logic is duration-based (JWT `exp`, Redis TTL) or an absolute-instant comparison, already timezone-safe by construction, confirmed by reading every relevant file rather than assumed; (5) no attendance/timesheet feature exists anywhere in this codebase (grepped, zero matches) — nothing to migrate there.

Landed as one continuous, two-phase pass (backend architecture + highest-impact business logic + a first slice of frontend pages, verified with the full suite; then the shared frontend formatter mechanically applied to every remaining display call site the audit found, verified again) rather than a blind find-and-replace:

- **Central utility**: `backend/app/utils/datetime.py` gained `now_ist()`, `to_ist()`, `start_of_day_ist()`/`end_of_day_ist()`/`start_of_month_ist()`/`ist_month_start_utc()`, `ist_date_range_to_utc_bounds()` — all built on stdlib `zoneinfo.ZoneInfo`, reading the IANA zone name from one place (`Settings.timezone`, `APP_TIMEZONE=Asia/Kolkata`, added to `Settings`/every `.env*` file), never a fixed `+05:30` offset scattered around. `within_daily_window` (unchanged internals — see decision 022/112) now expects its `now` argument pre-converted to the business timezone; every call site (`geo_fencing/enforcement.py`, `access_control/permission_engine.py`) was updated from `utc_now()` to `now_ist()`. Mirrored on the frontend: `frontend/src/shared/dateFormat.ts` (new, zero new npm dependency — native `Intl.DateTimeFormat` with `timeZone: "Asia/Kolkata"` already does everything needed) — `formatISTDateTime`/`formatISTDate`/`formatISTTime`/`istDateKey`/`todayISTDateString`/`istWallClockToUtcISO`/`currentISTHour`.
- **Root-cause fix**: `app/config/database.py`'s `get_client()` gained `tz_aware=True` — every datetime read from Mongo, everywhere in the app, is now tz-aware UTC instead of naive, fixing the ambiguous-serialization bug at its single source rather than patching ~20 mapper files individually. Verified both real Motor and the `mongomock_motor` test double honor the flag identically before relying on it. Applied identically to every test-side `AsyncMongoMockClient(...)` construction (`tests/api/conftest.py`, `tests/integration/test_dashboard_widget_scoping.py`). Surfaced one real, pre-existing latent bug this flip made observable: `leads/service.py`'s "fewest assignments today/this week" tie-break used to deliberately strip `tzinfo` from `utc_now()` to match Motor's old naive-read behavior (`# noqa: DTZ901`) — with reads now aware, that strip caused a naive-vs-aware `TypeError` comparing against `activity.created_at`. Fixed as part of the same IST day/week-boundary correction (`start_of_day_ist()`), not patched around. Also required `tzdata>=2024.1` as an explicit runtime dependency (`backend/pyproject.toml`) — `zoneinfo` has no bundled IANA database on Windows or on minimal Linux container images (e.g. `python:3.12-slim`) that lack `/usr/share/zoneinfo`; discovered when the isolated post-flip test run failed every timezone-touching test with `ZoneInfoNotFoundError`.
- **Business-day/hour fixes**: `dashboard/widget_providers.py`'s ~6 "today"/"this month" UTC-midnight computations (`_today_leads`, `_day_over_day_trend`, `_today_performance`, `_monthly_performance`, `_monthly_revenue`, `_revenue_trend_chart`'s month-bucket keys) now use the IST boundary helpers. `reporting/aggregations.py`'s `date_range_match()` (every report's date-range filter) replaced a naive `datetime.combine(date, time.min/time.max)` with `ist_date_range_to_utc_bounds()`. `employee/service.py`'s `list_activity` (Employee Activity Overview's date filter, previously accepting full `datetime` query params) changed to accept bare `date` params and route through the same helper, matching the reporting module's contract exactly rather than inventing a second convention.
- **Frontend**: three genuine input/round-trip bugs fixed — `AddTaskModal.tsx`'s task due-time (`datetime-local` input misinterpreted as browser-local via `new Date(...).toISOString()`) now uses `istWallClockToUtcISO`; `GeoExceptionPage.tsx`'s client-side expiry check (a hybrid UTC-date-parse + browser-local `.setHours()` bug) rebuilt on the same helper; `CreateEmployeePage.tsx`'s default joining-date now uses the IST calendar date instead of UTC. Every remaining `new Date(iso).toLocaleString()`/`.toLocaleDateString()` display call site found by the audit (~30 files across Leads/Dashboard/Sessions/Loan/Insurance/Customer/Communication/Integrations/Reminders/Owner) was swapped for the shared formatter; a post-pass re-grep for `toLocaleDateString(`/`toLocaleString(`/`toLocaleTimeString(`/`new Date(` (applied to a backend timestamp)/`getHours(`/`getDate(`/`getDay(`/`getMonth(` confirmed nothing was missed. Left deliberately unchanged (timezone-agnostic, duration/instant-only): `RecentActivitiesCard`'s relative-time math, `TaskOverviewRow`'s overdue check, `GenerateLinkModal`'s expiry comparison, `ApplicationPage`'s local "saved Xs ago" indicator.
- **Background jobs**: `worker_settings.py`'s three fixed-hour daily cron jobs (`check_re_eligible_cases`/`check_commission_triggers`/`refresh_meta_tokens`) got a disclosed-limitation comment block, not a code fix — arq's `cron(hour=...)` matches the worker process's own OS wall-clock with no tz-aware primitive in this stack, and their own business decisions never do a calendar-day-boundary comparison (`check_re_eligible_cases` compares an absolute instant; `check_commission_triggers`/`refresh_meta_tokens` re-scan by status, not by date) — confirmed timezone-safe as-is by reading each. `check_task_reminders`/`check_re_eligible_cases`'s own `now < due_at`-style comparisons got a one-line comment recording the same finding so it isn't re-investigated as a bug later.

**Why:** Per explicit instruction: audit the complete codebase before changing anything, do not blindly rewrite existing timestamps, centralize rather than scatter timezone logic, and the acceptance bar is "the CRM behaves as IST even if the server's own OS clock is UTC" — which is exactly what the `tz_aware` root-cause fix plus the IST-aware business-boundary helpers deliver, verified true rather than asserted.

**Impact:** Backend — `app/utils/datetime.py`, `app/config/{settings,database}.py`, `.env*`/`.env.example`, `app/features/{geo_fencing/enforcement,access_control/permission_engine,dashboard/widget_providers,reporting/aggregations,leads/service,employee/{router,service},worker/worker_settings,worker/tasks/reminders}.py`, `pyproject.toml` (`tzdata`). New `tests/api/test_timezone.py` (16 tests: UTC/IST conversion parity against the spec's own worked example, `within_daily_window` boundary sweep, a midnight-crossing IST-vs-UTC-calendar-date case, a Mongo `tz_aware` regression lock, an end-to-end `enforce_geo_fence` wiring check at the frozen worked instant, a Dashboard "today" boundary check, and a JWT-expiry-unaffected sanity check) plus one pre-existing test (`test_list_all_employee_activity_date_range_filter`) updated for the `datetime`→`date` query-param contract change. Frontend — new `frontend/src/shared/dateFormat.ts`; ~35 page/component files across every feature module. Full backend suite: 462 passed / 0 failed (was 446 baseline + 16 new). Frontend `tsc -b --noEmit`/`eslint`/`vite build` all clean (same 8 pre-existing warnings). Explicitly not done: arq cron trigger-hour IST-awareness (disclosed limitation, `docs/KNOWN_LIMITATIONS.md`); no live AWS/browser/server-OS-clock verification was performed — everything here is code-level and `mongomock_motor`-verified only.

---

# Leads Workflow Redesign (Module 6A, additive exception to the freeze)

## 125 — Leads redesigned into a 5-tab pipeline (Fresh Leads / My Leads / Document Collection / Rejected / Assigned) via an additive `Lead.stage` field, follow-up tracking, and assignment-at-creation — Phase 1 of a user-approved, explicitly staged rollout

**Decision:** Module 6A (frozen per decisions #031/#039/#045) gains, all additive — no existing field removed or repurposed, no existing endpoint's contract broken:

- A new `Lead.stage` field (`LeadStage`: `fresh`/`assigned`/`document_collection`/`rejected`), kept **entirely separate** from the existing, untouched `Lead.status`/`LeadStatus` (still exactly `NEW = "new"` as decision #004/`constants.py` originally described — the real Module 6C pipeline that field was reserved for still hasn't been repurposed, and this redesign doesn't repurpose it either). `stage` drives the redesigned Leads UI's 5 tabs; `status` continues to mean whatever a future feature eventually gives it.
- New `Lead` fields: `salary_in_hand`, `next_follow_up_date`, `assigned_by`/`assigned_at`, `rejected_reason`/`rejected_by`/`rejected_at`.
- New endpoints: `GET /leads/counts` (server-computed tab badges), `POST /leads/{id}/reject`, `POST /leads/{id}/stage` (My Leads <-> Document Collection only in Phase 1), `POST /leads/{id}/follow-up`. `POST /leads` and `PATCH /leads/{id}` gain optional fields (`salary_in_hand`, `next_follow_up_date`, `comment`, `assigned_to`) — every previously-valid request body remains valid and behaves identically.
- A redesigned Leads UI: 5 tabs (Fresh Leads / My Leads / Document Collection / Rejected / Assigned) with live server-side counts, replacing the current 2-tab New Leads/Assigned Leads split (itself only ever a client-side derivation from `assigned_to`, never a real stage concept). "Customers" removed from the sidebar (the underlying Customer entity, its routes, and Loan Management's dependency on them are untouched — only the confusing top-level nav entry is removed, per the user's explicit instruction not to delete customer/account functionality).
- The existing visibility-scoping gap in `LeadService._scope_query` is closed: a non-Owner actor requesting the "unassigned" pool used to always be forced onto "my own unassigned drafts only," even one holding the existing `leads:leads:assign` permission (i.e., already trusted to distribute leads across the team). That actor now sees the true, company-wide Fresh Leads pool — reusing `assign`, not a new permission, since granting "may assign leads" already implies "may see the pool being assigned from." The same check now scopes the new Document Collection/Rejected/Assigned tab queries identically.
- `reject_lead`/`set_stage` are both guarded to only accept an already-**assigned** lead (`assigned_to is not None`) — matching the spec's own "My Leads -> Rejected"/"My Leads -> Document Collection" wording exactly, and keeping every non-`fresh` stage's visibility scoping simple (a rejected or in-Document-Collection lead always still carries the `assigned_to` it had when it left My Leads, so the same `assigned_to=<employee_id>` scoping rule applies to those tabs unchanged for a non-broad-visibility actor).

**Why:** User-requested, explicitly approved redesign of the Leads lifecycle — the current 2-tab layout has no follow-up tracking, no non-overwriting comment history exposed on the list view, no rejection workflow, and no real pipeline concept at all (just an `assigned_to`-presence derivation). Delivered as an explicitly user-mandated, staged rollout (same framing as #052/#053's approved, scoped exception to a frozen module): Phase 1 here is Lead-entity-only — no dependency on Module 6B's `Application`/`ApplicationDocument` or Module 6C's case pipeline. Phase 2 (the full financial-assessment Update form + staff-initiated Customer Account creation) and Phase 3 (wiring the Document Collection tab to the real `Application`/`ApplicationDocument` entities, reusing them rather than duplicating a second document system, plus the Document Collection -> Loan Management handoff) are each their own future decision entry, implemented only after this phase is tested end-to-end and the user explicitly approves proceeding — **not automatically chained**, per the user's own explicit instruction when approving this plan.

**Impact:** `backend/app/features/leads/{models,constants,schemas,repository,service,mappers,router,indexes}.py`, `backend/app/utils/datetime.py` (new `ist_date_to_utc_midnight`, extracted from the existing `ist_date_range_to_utc_bounds`, decision #124's convention), `scripts/seed.py` (`leads:leads` permission catalog gains the `reject` action — additive, no existing `RolePermission.granted_actions` value changes), new `scripts/migrate_backfill_lead_stage.py` (backfills `stage` for every pre-existing Lead based on `assigned_to`, and `$addToSet`s the new `reject` action onto an already-seeded `leads:leads` Permission document — must run before this phase's backend is deployed). Frontend: `frontend/src/components/layout/{navConfig,ModuleTabs}.tsx`, `frontend/src/app/router.tsx`, `frontend/src/features/leads/api.ts`, `frontend/src/features/leads/pages/{LeadsLayout,LeadListPage,CreateLeadPage,LeadDetailsPage}.tsx`, new `frontend/src/features/leads/components/{FollowUpModal,RejectLeadModal,UpdateStageModal}.tsx`. Extended `tests/api/test_leads.py` plus new `tests/api/test_migrate_backfill_lead_stage.py`.

**Freeze (reconfirmed):** Module 6A remains frozen for anything beyond what this entry lists. Phase 2 and Phase 3 of this same redesign — touching Module 6B (Customer Application Flow) and Module 6C (Loan & Insurance Processing) respectively — each require their own decision entry and explicit user approval before implementation begins; this entry does not authorize either.

## 126 — My Leads' Update screen gains the financial/customer assessment form and staff-initiated Customer Account creation — Phase 2 of the Leads redesign, plus two fixes an end-to-end manual test surfaced

**Decision:** Module 6A gains one more additive field — `Lead.financial_assessment` (a new embedded `LeadFinancialAssessment` sub-object: Mock Off Salary, Salary Mode, EMI Range, Total/Current Company Experience, Company Location, Any Loan/Balance, Last 3 Months Salary, CIBIL Score/Don't Know, Remarks) — and two new endpoints: `PATCH /leads/{id}/financial-assessment` (whole-object replace per save, not a partial merge) and `POST /leads/{id}/customer-account`. The latter composes a new Module 6B method, `CustomerService.create_staff_initiated_account(lead_id, password, actor)`: a staff member (Owner/Employee) sets a Customer's password directly, with zero OTP round-trip — the same "staff-initiated account, no OTP" precedent decision #017 already established for Employee creation (`initial_password`, `must_change_password=True`), extended here to `role=CUSTOMER` for the first time. The account's mobile is always the Lead's own `mobile` (never a separately staff-typed value), so the existing `_link_existing_leads_to_customer` mobile-matching logic correctly attaches `customer_id`/`user_id`/`account_created` with no new linking code. Deliberately creates **no** `Application` — `Customer` is product-agnostic; associating the account with a real application is Phase 3's job, reached only via the pre-existing Generate Link flow.

**Why:** User-requested continuation of decision #125's staged rollout, scoped explicitly to the fields/actions listed above — no Application/ApplicationDocument work, no change to the 5 tabs, counts, follow-up, comment history, assignment logic, or `Lead.status`.

**Impact:** `backend/app/features/leads/{models,constants,schemas,service,router}.py`; `backend/app/features/customer/service.py` (one new additive method, `create_staff_initiated_account`, plus its `hash_password`/`CUSTOMER` imports — no existing method changed). Frontend: `frontend/src/features/leads/api.ts`, `frontend/src/features/leads/components/UpdateStageModal.tsx` (extended in place with the Financial Assessment and Create Customer Account sections, per decision #125's own forward note — not a rename or rebuild). Tests: `tests/api/test_leads.py` (+6), `tests/api/test_customer.py` (+6, the account-creation flow — happy path, duplicate-account block, weak-password rejection, real login with the submitted password, and an explicit assertion that no `Application` is created).

**Manual end-to-end browser testing** (this repo's own `docs/RUN_LOCAL.md` + a temporary Playwright driver, since `chromium-cli` wasn't available in this environment) surfaced two things the automated suite hadn't caught, both fixed and covered by new regression tests before this phase was signed off:
1. **Real bug, `access_control/service.py`'s hardcoded `_MY_PERMISSIONS_CATALOG`** (the list `get_my_permissions` — the `/my-permissions` UI-support endpoint — iterates over) was never updated when decision #125 added the `reject` action to the `leads:leads` permission catalog. Net effect: an Employee granted `leads:leads:reject` had the Reject button silently hidden from them in My Leads' Update screen, even though the grant itself and the real `POST /leads/{id}/reject` gate both worked correctly — a UI-visibility-only gap, not an authorization hole. Fixed with a one-line addition (`("leads","leads",(...,"reject"))`); allowed under Module 3's freeze policy as a bug fix, not an architectural change. New regression test: `tests/api/test_access_control.py::test_my_permissions_includes_reject_for_leads_leads`.
2. **UX gap**: the Document Collection tab had no button to move a lead back to My Leads — only My Leads exposed the "Update" action that opens `UpdateStageModal` (which already correctly renders "Move back to My Leads" once open). Fixed by extending the same existing `ActionButton` gate in `LeadListPage.tsx` to `tab === "document_collection"` too — reuses the modal verbatim, no new logic, no new endpoint.

**Freeze (reconfirmed):** Module 6A and Module 6B both remain frozen for anything beyond what this entry (and decision #125) list. Phase 3 — wiring Document Collection to the real `Application`/`ApplicationDocument` entities and the handoff to Loan/Insurance Management — requires its own decision entry and explicit user approval; this entry does not authorize it.

## 127 — Document Collection wired to the existing Application/ApplicationDocument entities, plus the one new business rule this required: a verified-documents gate before a lead can hand off to Loan/Insurance Management — Phase 3, and the final phase, of the Leads redesign

**Decision:** No new document system. The Document Collection tab's "Pending"/"Submitted" status and its "View" action are read-only surfacing of the **existing, unmodified** `Application`/`ApplicationDocument` entities (Module 6B) and the **existing, unmodified** `/applications/:applicationId` → `StaffApplicationDetailsPage.tsx` staff page (Accept/Reject/Re-upload/version history — all already worked, including staff re-uploading on a customer's behalf, confirmed unchanged). One new additive read method, `ApplicationRepository.find_by_lead_id`/`find_for_leads` (mirrors the inline lookup `claim_secure_link` already does), lets `LeadService` resolve which Application (if any) belongs to a Lead — a Lead can sit in `document_collection` with no Application yet (the customer hasn't used Generate Link), which is treated as a legitimate "Pending" state, never an error.

The one genuinely new piece of business logic: `LeadStage` gains a terminal value, `loan_management`, reachable only via `POST /leads/{id}/stage` from `document_collection`, gated on the linked Application being `submitted` **and every required document's current version being `verified`** — a check that did not exist anywhere in this codebase before (the existing `submit_application`/case-creation path only ever checked "uploaded," never "verified"). This gate creates, reads, or touches nothing under `case_type`/`LoanCaseService`/`InsuranceCaseService` — the real Loan or Insurance case was already created automatically, correctly branched by `application.product_category`, back when the customer submitted (`CustomerService.submit_application`, decision #058's lazy-get-or-create). The Lead-side `loan_management` stage value is purely a Leads-pipeline bookkeeping label meaning "this lead has left the Document Collection working queue" — it is not itself a case, does not create one, and never misroutes an Insurance lead into Loan Management's own pipeline (confirmed by a dedicated test seeding an insurance-category lead through the same gate). No 6th Leads tab: a `loan_management`-stage lead simply stops matching Document Collection/My Leads' `stage` filters and the real work continues in the pre-existing Loan Management/Insurance Management sidebar sections, exactly as before this phase.

**Why:** User-requested final phase of decision #125/#126's staged rollout, explicitly scoped to reuse rather than rebuild — the acceptance bar was "do not create a second document-management system," which this entry satisfies by linking to the real page rather than reimplementing any part of it.

**Impact:** `backend/app/features/leads/{constants,service,router,schemas,mappers}.py`; `backend/app/features/customer/repository.py` (two new additive `ApplicationRepository` methods only). Frontend: `frontend/src/features/leads/api.ts`, `frontend/src/features/leads/pages/LeadListPage.tsx` (Document Collection's Status column, tab-aware View action), `frontend/src/features/leads/components/UpdateStageModal.tsx` (Application & Documents section, "Move to Loan Management" button). `StaffApplicationDetailsPage.tsx`, `DocumentChecklist.tsx`, Loan/Insurance Management's own pages: untouched. Tests: `tests/api/test_leads.py` (+13 — Pending/Submitted list states, the document-completion summary correctly ignoring superseded/non-current documents, the gate's every blocking/passing branch, reject-blocked-once-handed-off, permission gating, and an explicit insurance-category test proving the gate never misroutes a case).

**Freeze (reconfirmed):** Modules 6A/6B/6C all remain frozen for anything beyond what decisions #125/#126/#127 list. This closes the Leads workflow redesign initiative — any further change to this pipeline needs its own new decision entry and explicit approval, the same as any other frozen-module change from here on.
