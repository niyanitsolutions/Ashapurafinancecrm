# Customer Portal implementation report

Local implementation completed on 18 November 2026. No production deployment, production data change, real SMS, or real object-storage upload was performed. Browser fixtures use synthetic customer data and mocked storage/SMS providers. Local results are not production verification.

## Architecture and scope

The existing CRM was inspected before implementation: customer-only `/portal` routing and layout; shared LoginPage with separate customer and staff forms; verified registration/PIN sessions; Customer/User/Lead/Application relationships; schema-driven forms; draft autosave/tab locks; private document uploads/history; secure-link resolution/claim; Document Collection merging of Lead and lead-less applications; loan/insurance case creation; notification, messaging and support APIs; assignment/RBAC and company database scope.

This extends the existing modules. No second authentication, application, notification, messaging or document system was introduced. Product fields and wizard sections still come from the actual Product Schema, rather than fabricated personal/financial fields or empty mandatory steps.

## Batch 1 — customer presentation

- Added customer-scoped tokens and reusable page, progress, application-card and authentication-layout components. White/light-grey surfaces, accessible dark orange actions, readable text and touch targets replace customer-only decorative styling. No global stylesheet or shared staff controls were modified.
- CustomerPortalLayout now has desktop sidebar navigation, compact mobile navigation, a skip link, notification access, support and sign-out. Styling is restricted to customer-specific class boundaries.
- Dashboard shows the customer's actual name/reference, authoritative full application counts, drafts requiring completion, submissions, latest-application document count, recent applications and five quick actions. Existing offer-acceptance/additional-document action banners remain prominent. Duplicate dashboard widgets were removed. Counts are not capped by the existing 200-row application-list limit. Pending-document count is explicitly labelled as applying to the latest application.
- Customer applications use readable cards with references, real statuses/stages, dates, progress, relationship manager and continue/details actions. Details show processing stage, submission time and the next action without introducing new business statuses.
- Customer profile, document centre, messages/delivery history, notifications and support use the customer page boundary. Profile displays the registered mobile read-only and retains existing editing permissions and masked identity information. Support/product-list failures show errors instead of silently pretending the result is empty.
- Notifications reuse the existing inbox/read-state component, wrapped only at the customer route; staff notification screens remain unchanged. The existing delivery-history feed remains separately available.
- Registration uses a simple white customer-only card. Customer PIN Show/Hide and its panel presentation are isolated to PinAuthPanel; staff login pages/forms and the shared login shell are unchanged.

## Batch 2 — unified application journey

### Authentication and entry methods

Customer registration still validates mobile, optional email and matching PINs before sending the existing approved OTP. Account creation still requires verified ownership. After completion, the frontend calls the existing normal PIN login API and establishes the existing session, then opens `/portal` or the validated secure-link return path. If that separate login fails, account creation is not retried: the customer receives a successful-registration message on the existing login page.

Argon2id, OTP hashing/expiry/single use/limits, Forgot PIN, PIN epochs, session rotation and revocation were not changed. Owner/employee/partner authentication remains byte-for-byte unchanged. The existing enrollment/password compatibility path remains available according to the existing policy.

Staff-assisted creation retains its current API, IDs, assignments and workflow. Secure-link claims retain expiry/disabled/mobile/ownership checks and resume the same application. A customer needing profile setup now carries the exact application return path through setup, avoiding a generic-dashboard detour. Independent customers select the same available products and complete the same schema-driven workflow.

### Save, review and submit

The existing wizard, validation, schema sections and tab lock remain. Draft requests are queued so an older autosave cannot overtake the reviewed save. Save and Continue Later waits for successful persistence. In-app navigation with unsaved changes offers Save and Leave; unload protection and pre-logout flush remain. Final submission has a confirmation dialog and flushes the exact reviewed values before calling the submit API. Double-clicks are guarded.

New optional request keys make repeated independent application-start requests return the same Application. Secure-link creation uses a deterministic scoped key in addition to its existing get-or-create lookup. Deliberately starting a new application remains allowed: existing same-product/product-eligibility rules were not replaced with a blanket prohibition.

Submission uses an atomic draft-to-submitted compare-and-set. Repeated/concurrent requests return the existing submission, preserve the original timestamp and do not duplicate application-submission audit/timeline entries. Existing case creation is reconciled idempotently, including a concurrent unique-index collision. Draft edits cannot overwrite an already submitted application. These new protections do not require MongoDB transactions.

### Documents

The existing shared checklist and staff upload helper are unchanged. A customer-only wrapper adds real upload-byte progress, appropriate mobile camera controls and version history via existing authorized endpoints. Camera replacement respects the existing pending/verified/rejected single-slot rules; password-protected/front-back documents retain their existing controls. File size/type and all authoritative server checks remain in place. Upload confirmation occurs only after the signed storage PUT succeeds. Failures do not automatically retry or claim completion. No bearer token is attached to storage PUTs.

Private object keys still come from the server. Preview/download links are existing short-lived signed links, not public object URLs. Required/current/uploaded/rejected/not-available/verified records, rejection reasons and replacements retain the existing product rules. History is fetched only on request and remains ownership-checked server-side.

## CRM Document Collection integration

Direct loan applications already appeared as lead-less rows in the existing Document Collection view; that architecture was preserved instead of creating duplicate Leads. Newly observed independent insurance customer submissions are additionally visible there while their existing case is at Fresh Lead. This is an observational addition: insurance cases are not moved or assigned differently. Historical/manual insurance records are not swept into that view, and a case leaving Fresh Lead follows its existing insurance workflow. Enrichment is batched rather than issuing per-row customer/product/employee queries.

All three entry methods record known provenance when a new Application is created: `customer_portal`, `secure_link`, or `staff_assisted`. `customer_portal` means self-service application entry, not an invented claim about how an older account was registered. Historical rows default to `unknown`.

Document Collection exposes submission source, first submission timestamp and latest customer application activity. Its existing details/verification summary continues to provide document-completion status. Original Lead/Application/Customer IDs, product and assignment remain authoritative. A direct application uses its Application reference and the existing `is_lead_less` contract; no fake Lead ID or duplicate Lead is inserted.

The only staff-table changes are small conditional source/date text within the existing application-status cell and a loan-only guard on Move to Loan Management, so a newly visible insurance row cannot offer the wrong action. Existing headers, filters, tables, colours, navigation and modals were not redesigned. Owner sees the existing database scope; employees remain restricted by existing assignment/permission rules.

## Preservation verification

The source baseline is `3d1d9f25881d9df7707e82e2d315d20bf1a9eb4f`. A scoped Git comparison confirmed **849 protected tracked files unchanged**. Machine-readable evidence: [preservation.json](screenshots/customer-portal-modernisation/preservation.json).

| Surface | Verification |
| --- | --- |
| Owner UI | Shared controls/theme, dashboard and authentication pages unchanged; existing owner login and Document Collection exercised in the browser. Explicit metadata exception described above. |
| Employee UI | Employee modules and shared shell/forms unchanged; existing assignment, workflow, document/privacy and authentication regressions pass. No assignment algorithm changes. |
| Partner UI | Partner modules and login pages unchanged; partner-management/authentication regression suite passes. |
| Authentication | Backend auth/security/session code unchanged; shared login pages/forms/context unchanged. Customer-only presentation and post-registration use of existing PIN login are described above. |
| Airtel | Integration and communication provider source unchanged; no credentials, mappings, templates, test/activation guards or live configuration changed. |
| Database/ownership | Existing company database scope and User/Customer/Application/Lead IDs retained. Customer-owned API checks and staff assignment scopes remain in force. |

Two existing type inconsistencies were clarified to complete checks: the employee-assignee sort-key annotation now describes its existing tuple values (no algorithm change), and profile completion states the existing repository guarantee that a pending lead-conversion draft has a Lead ID. No valid workflow was changed by these annotations/invariants.

## APIs, schema and migration

Backward-compatible additions only:

- `POST /applications`: optional `request_key`; callers omitting it retain the existing ability to start another application.
- Application documents: optional persisted `creation_key`, `submission_source`, `last_customer_activity_at`. Creation keys are server-generated scoped hashes, not new primary IDs and not returned as authentication authority.
- Application list/detail responses expose source and customer activity. Existing fields remain.
- `POST /applications/{id}/submit`: now idempotent for an already submitted application. PATCH is conditional on draft status.
- Customer dashboard response adds full `application_counts`; recent activity displays business events rather than session-refresh internals. Audit/history records themselves are not removed or rewritten.
- Document Collection list adds source/submission/activity metadata and the bounded customer-insurance observation described above.
- New partial unique `applications.creation_key` index applies only to string keys. Existing rows lacking the field or containing null are unaffected. Startup's existing customer-index initializer creates it.

No new collections, destructive migration, bulk customer credential update, Lead backfill or historical provenance guess was added. Old sources remain unknown on read; no automatic data rewrite is required. Failed/retried keyed requests may leave harmless gaps in the existing application-code counter. Existing code rollback can leave the additive fields/index in place.

The new creation/submission concurrency path was tested against the existing **standalone** loopback MongoDB server. The pre-existing registration transaction requirement remains: production must support transactions for that already implemented registration flow. No production topology was assumed or changed. Registration regression fixtures used a separate local replica set.

## Files and frontend modules

Customer-only components added: `PortalPage`, `PortalApplicationCard`, `PortalOverview`, `CustomerAuthLayout`, `CustomerDocumentChecklist`; `portal.css`; customer-progress transport `customerUpload.ts`; `PortalNotificationsPage` wrapper. Existing CustomerPortalLayout and customer pages were enhanced in place, including application/list/timeline/product selection, documents, profile/setup, messages, support, registration and secure-link landing. Shared staff checklist/renderers remain unchanged.

Backend changes are confined to customer model/schema/mappers/index/service and Lead schema/mappers/list enrichment. The router change is solely the customer notifications wrapper. Source/date metadata is the explicit exception in LeadListPage and its response typing. Customer-only PinAuthPanel presentation changed; shared LoginPage/LoginForm/AuthPageLayout/AuthProvider did not.

New tests: `test_portal_modernisation.py`, `test_portal_mongo.py`, `test_customer_portal_browser.py`, customer upload-progress and camera-eligibility tests. Existing DocumentsPage/RegisterPage tests and customer registration browser harness were updated for the authorized frontend flow. Browser script: `scripts/customer-portal-ui-check.mjs`. A [full file inventory](screenshots/customer-portal-modernisation/changed-files.txt) accompanies the screenshots.

## Exact validation results

All tests use mocked external providers. No real SMS or S3 request was made. These are relevant suites, not a claim that every repository test was run.

| Check | Exact result |
| --- | --- |
| Customer/portal/document/workflow/assignment/insurance/auth/PIN/partner regression batch | **192 passed**, 1264 existing mongomock UTC deprecation warnings, **280.41s** |
| Verified registration, real Mongo PIN concurrency and retired-bypass regressions | **17 passed**, **95.99s** |
| Final focused portal/new standalone concurrency/dashboard suites | **29 passed**, **72.34s**; includes repeated/concurrent requests, one audit/case, ownership/history denial, insurance observation, full counts beyond 200, and legacy unknown metadata |
| Insurance enrichment after batching | **1 passed**, **4.01s** |
| Customer/auth/shared notification frontend suite | **91 passed across 15 files**, **21.03s** |
| Six-width portal browser suite | **1 passed**, 75 existing mock-date warnings, **37.14s** |
| Registration/PIN recovery browser suite | **1 passed**, **23.79s** for the final consolidated evidence run |
| Targeted mypy | **No issues in 8 source files** |
| Ruff / Node browser-script syntax / diff whitespace | **Passed** |
| Targeted ESLint | **0 errors**, one existing Fast Refresh export warning in the unchanged shared DocumentChecklist |
| Production build | **Passed** (`tsc -b && vite build`, 447 modules; Vite **13.75s**). Existing large-bundle advisory remains. |

Some suites overlap; their pass counts must not be summed as distinct tests.

Commands (PowerShell, repository root unless noted):

```powershell
$env:DEBUG='false'
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_customer.py tests/api/test_customer_portal_home.py tests/api/test_customer_portal_redesign.py tests/api/test_customer_documents.py tests/api/test_document_collection_lifecycle.py tests/api/test_assignment_consistency.py tests/api/test_workflow.py tests/api/test_insurance_policy_leads.py tests/api/test_auth.py tests/api/test_pin_auth.py tests/api/test_referral_partner_management.py -q -n 2 --tb=line
$env:AFS_PIN_TEST_MONGO_URI='mongodb://127.0.0.1:27028/?replicaSet=customerPinTest'
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_customer_pin_registration.py tests/api/test_pin_mongo_integration.py tests/api/test_registration_otp_bypass.py -q --tb=line
$env:AFS_INVOICE_TEST_MONGO_URI='mongodb://127.0.0.1:27017'
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_portal_modernisation.py tests/api/test_portal_mongo.py tests/api/test_customer_portal_home.py tests/api/test_customer_portal_redesign.py -q -n 2 --tb=line
npm --prefix frontend test -- src/features/customer src/features/auth src/features/reminders/pages/NotificationListPage.test.tsx
npm --prefix frontend run build
```

Browser fixtures require the **local production preview**, not the development Strict Mode server:

```powershell
npm --prefix frontend run preview -- --host 127.0.0.1 --port 5175
$env:AFS_PORTAL_BROWSER_CHECK='1'
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_customer_portal_browser.py -q -s --tb=short
$env:AFS_CUSTOMER_PIN_BROWSER_CHECK='1'
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_customer_pin_browser.py -q -s --tb=short
```

The portal browser uses actual local FastAPI APIs and existing session/permission logic with disposable test data and mocked private storage. It tests **360, 390, 768, 1024, 1366 and 1920px**: PIN login/visibility, navigation, dashboard, applications, wizard, save/resume, save-before-leave protection, upload, confirmation/submission, same secure application on resume, expired/disabled links, history, profile/messages/notifications/support, notification dropdown and staff Document Collection. Screenshots were inspected and show no horizontal overflow/runtime errors. Registration/recovery uses actual local APIs plus a disposable transaction-capable database and mocked Airtel transport at 1440/390px.

Evidence: [responsive results](screenshots/customer-portal-modernisation/results.json), [desktop overview](screenshots/customer-portal-modernisation/overview-1366.png), [mobile wizard](screenshots/customer-portal-modernisation/guided-form-360.png), [mobile documents](screenshots/customer-portal-modernisation/documents-390.png). All visible fixture values are synthetic, not production customer data.

## Remaining dependencies and limits

- Production topology, private-storage CORS/permissions, existing live Airtel activation and a real customer handset test were not inspected or exercised. They remain rollout prerequisites.
- The production build retains the existing large-bundle warning. No new image assets, animation framework or external UI dependency was added.
- In the development server, React Strict Mode's duplicate bootstrap effect can replay a refresh token on reload. The existing replay protection rejects it. Authentication was deliberately left unchanged; the production preview/browser journeys pass. This development-only issue should be tracked separately rather than disabling replay protection.
- Historical provenance is intentionally unknown. No claim of historical “self registration” is fabricated. Legacy staff insurance processing is preserved.
- Customer screenshots/functional tests plus protected-source comparison verify this local change; no before/after comparison of live production Owner/Employee/Partner sessions is claimed.

## Production deployment instructions — not executed

The checked-in [AWS deployment documentation](deployment/AWS-Deployment-Documentation.pdf), pages 5–10, documents `/opt/afs-crm`, the backend `.venv`, Nginx static `frontend/dist`, and systemd services `afs-crm-backend` / `afs-crm-worker`. Confirm the live installation still matches that runbook before using these commands. Release approval, backup and target verification must precede rollout. No release commit has been selected or deployed here.

For that documented layout, after the reviewed release is made available on the approved tracking branch:

```bash
cd /opt/afs-crm
git status --short
# Stop if the working tree is dirty or the tracking branch is not the approved release.
git pull --ff-only
cd /opt/afs-crm/backend
.venv/bin/python -m pip install .
```

Read-only preflight in the existing approved backend environment; it prints no URI, credentials, customer records or key values:

```bash
.venv/bin/python - <<'PY'
import asyncio
from app.config.database import close_client, get_database
async def check():
    try:
        db = get_database()
        hello = await db.client.admin.command('hello')
        duplicates = await db.applications.aggregate([
            {'$match': {'creation_key': {'$type': 'string'}}},
            {'$group': {'_id': '$creation_key', 'count': {'$sum': 1}}},
            {'$match': {'count': {'$gt': 1}}},
            {'$count': 'groups'}
        ]).to_list(None)
        print({'transaction_topology': bool(hello.get('setName') or hello.get('msg') == 'isdbgrid'),
               'duplicate_creation_key_groups': duplicates[0]['groups'] if duplicates else 0})
    finally:
        await close_client()
asyncio.run(check())
PY
```

Stop if the existing registration transaction prerequisite is unmet or duplicate string keys are found. Do not auto-convert MongoDB, delete records, assign provenance or drop indexes. A production infrastructure/data correction requires its own approved plan. Existing secure environment/configuration values must be retained.

After successful preflight and approval, create the additive customer indexes before accepting application traffic:

```bash
.venv/bin/python - <<'PY'
import asyncio
from app.config.database import close_client, get_database
async def run():
    try:
        await get_database().applications.create_index(
            'creation_key', unique=True, name='application_creation_key',
            partialFilterExpression={'creation_key': {'$type': 'string'}}
        )
    finally:
        await close_client()
asyncio.run(run())
PY
cd /opt/afs-crm/frontend
npm ci
npm run build
sudo systemctl restart afs-crm-backend afs-crm-worker
sudo nginx -t
sudo systemctl reload nginx
sudo systemctl is-active afs-crm-backend afs-crm-worker
curl -fsS http://127.0.0.1:8000/api/v1/health
```

The existing production environment must supply the same frontend API configuration and backend secrets as before. No Airtel setting/template change is part of deployment. For a different installation/orchestrator, use its verified runbook rather than these EC2 commands. Code rollback uses the previously approved release plus its matching frontend build; retain the additive index/metadata and do not perform a destructive database rollback.

## Manual production verification checklist

Only after separately approved deployment, use an owner-authorized handset and non-sensitive test files.

1. Check owner, employee and partner password login, dashboard, navigation, forms and assigned workflows against the prior release. Confirm only the documented Document Collection metadata addition is visible.
2. Register a new customer with optional email and matching PINs. Confirm no account exists before OTP verification. Receive the approved OTP, verify once, complete registration and enter the customer portal. Do not copy PINs/OTPs into logs or reports.
3. Log in normally with mobile + PIN without SMS. Use Forgot PIN, verify a newly received OTP and confirm the old PIN/sessions no longer work. Verify a historical customer can still explicitly enroll through the existing compatibility path.
4. Apply for an available loan and insurance product. Verify actual configured fields/requirements, inline errors, Previous/Continue, Save and Continue Later, and save-before-navigation. Reload and resume the same draft.
5. Upload an approved test file, check progress/private preview, have staff reject it, then replace it. Check reasons, current version/history and permission-denied access from a different customer. Never make objects public.
6. Review and confirm submission. Retry the same request/double-click; verify one Application, one underlying case, original first-submission timestamp and original Lead relationship. New independent applications must not fabricate Leads.
7. Verify Leads → Document Collection source/date/activity metadata and existing document-completion summary. Check employee assignment scope and that staff-assisted applications still use their existing flows. Insurance must retain its own existing processing actions.
8. Open a valid secure link as the intended customer, resume the same application, and check expired/disabled/wrong-account outcomes. A profile-setup detour must return to the requested application.
9. Check profile, messages, read/unread notifications, delivery history and support using actual data at all six requested widths. Confirm no overflow and keyboard/focus/touch usability.
10. Reconfirm Airtel credentials, DLT mappings, approved message and activation safeguards are unchanged. Record live results separately; local mocks do not prove production delivery/storage.
