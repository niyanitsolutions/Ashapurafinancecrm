# Enterprise CRM enhancement - 25 November 2026

## Architecture assessment

Inspected living REQUIREMENTS.md, DECISIONS.md, previous assignment report, Customer/Application/Lead models and services, Document Collection, daily operations, effective permission engine, Bin, dashboard search, schema validation and document upload components. No repository AGENTS.md or requirements traceability file was found. Starting checkout was clean.

Confirmed gaps: Document Collection merges capped 1000-row sources in Python before pagination; global header search only searches employees; profile editing is self-service only; document password labels default to Bank Statement for unrelated document types; profile PAN accepts loose lengths; date display uses abbreviated month names. Existing reusable capabilities include OTP registration/recovery controls, encrypted document password storage, shared Customer ownership, Owner-only Bin APIs and versioned documents. Preserve these mechanisms rather than introduce replacements.

Implemented locally. Validation outcomes and operational limitations follow below. No production changes, deployment, historical repair or real SMS were performed.


## Document Collection

The Leads Document Collection tab now uses `/leads/document-collection/grouped`, a Mongo aggregation over existing Applications, Leads, Customers, workflow cases, document versions, daily follow-ups and assignment audit. It filters the eligible, actor-scoped dataset before grouping, then sorts with an ID tiebreaker, counts and paginates inside Mongo. Default 200 customer groups; UI choices 10/25/50/100/200. Expanded applications are independently paginated at 25. Browser memory receives only requested pages. Leads without an application retain a distinct intake representation, rather than generating a fake application/customer. Customer relationships with invalid user ownership never expose the referenced profile.

Search covers verified-schema applicant names, current profile name, Customer ID, Application ID, Lead code, mobile and email. Advanced filters combine assignment employee/actor/date, product/category, application status, created dates, source, branch, employee designation, account status, next-follow-up dates/overdue/status/employee, bank/NBFC and document states. Real stored IDs/statuses drive selectors. Assignment history provides historical Assigned By/On where record-level metadata is absent; new individual assignments retain those fields too. Document filters inspect current uploads, not superseded versions. No lifecycle transition is inferred from document completion alone.

One authoritative Customer ID groups multiple application IDs, with count/latest submission and newest submission first in expansion. Application assignments, documents, history and follow-ups remain independent. Expand/collapse does not load all applications. URL-backed criteria preserve pagination/navigation; Apply resets page one, Clear removes criteria. Existing Create Lead, Bulk Upload, Lead edit/link and independent application's Move to Loan Management entry points reuse existing components/services. The existing bulk assignment preview/consent flow is retained for selected expanded applications (maximum 100).

Compatibility boundary: the older ungrouped `/leads?stage=document_collection` response remains unchanged for legacy clients, including its existing merge/candidate limits. The new grouped UI does not use that capped read path. Existing tab badge semantics remain legacy record counts rather than grouped customer counts. Do not mistake that badge for the new grouped list's total.

## Customer identity and editing

Current Customer profile is authoritative; verified product-schema name keys and the existing pending profile supply display fallback only when no established current name exists. Aggregation and ordinary read paths share explicit name-resolution rules. Missing/mismatched profiles stay separate and display safe fallback names; no mobile/name-based automatic customer merge occurs.

The employee-side application page now distinguishes Customer Details/current profile from original application answers. Authorized staff can edit the shared profile, bound to the existing assigned-application visibility and customer edit permission. PAN, Aadhaar and DOB changes are Owner-only because the current permission catalog has no separate sensitive-identity grant. Mobile is not changed through this editor: mobile ownership remains an authentication operation. A required reason, expected version and compare-and-set prevent lost updates. Field-level before/after history is appended atomically to the Customer; PAN/Aadhaar values remain encrypted in that history; DOB follows the existing BSON date convention behind the same sensitive-edit boundary. The separate audit log records actor, customer, fields and resulting version without raw personal values. Submitted form data/documents are untouched.

Daily Follow-up opening/editing now resolves current identity through the exact application/user/customer relationship, with schema-verified fallback. Page reads batch-resolve linked application names instead of querying each row individually. Independent daily entries keep their own existing identity/history behavior. A mismatched linked customer reference is refused for editing rather than silently exposing another profile.

## Forms, dates and documents

Profile PAN requests trim, uppercase and validate the existing Indian PAN shape. The two verified seeded PAN keys (`pan_number`, `pan_card_number`) gain PAN validation at model read/validation time without rewriting historical schema documents. The dynamic schema engine uppercases PAN-format values on both frontend and backend even without a separate uppercase flag. Shared profile inputs uppercase real values, not only CSS. Existing encrypted PAN storage remains intact.

Shared date display uses DD/MM/YYYY in IST. Shared FormField/dynamic schema date inputs now display and accept DD/MM/YYYY, validate calendar round trips and deliver ISO calendar dates to existing handlers/APIs. Invalid dates are blocked using input validity; min/max constraints and business validators remain. Stored BSON/ISO conventions and timestamp timezones are unchanged. Tests cover leap days and no timezone day shift.

Document password labels now use their actual document type, only when that document supports passwords. Values remain component-local/transient on upload and encrypted using the existing backend mechanism. Existing encrypted passwords are not rewritten or discarded. Normal responses remain password-free; the old password-reveal service now returns Forbidden even to authorized staff, and Show Password is removed. This deliberately changes the old reveal contract to satisfy this batch's explicit write-only requirement. No password, OTP, PAN or document body is added to application logs.

Passport-size photo labels are mapped to Recent Selfie Photo in document responses/overrides/sections. Stable document type IDs, old filenames, references and upload histories are preserved; master-data/files are not destructively renamed.

## Global search and Owner controls

Header search is now available to staff across CRM screens, including mobile. It debounces input, guards against stale responses, groups Customers/Applications/Leads/Employees, supports keyboard selection, and provides loading/empty/error states and bounded per-entity pagination. Applications include Customer ID, product, status and assignment context. Search resolves exact IDs to their existing detail routes. Customer/application results use current identity and verified schema fallback. Products, assignment employee/actor, branch, status and calendar dates are included where stored. Employee results remain Owner-only, matching the employee detail route.

The UI uses POST `/dashboard/search`, keeping identity/PAN queries out of normal URL query-string access logs. Legacy GET remains compatible. Module permission plus existing employee-assignment scope applies before projection; restricted results and full PAN values are never returned. Search uses existing collections rather than a separate search engine. Queries are escaped, length-limited, actor-scoped and paginated. Substring searches can still scan an actor's eligible rows; indexes support identity equality, ownership and join paths, not arbitrary substring acceleration.

Exact Owner-only PAN search uses a domain-separated keyed digest created on new/updated PAN values. Historical encrypted PANs without that digest are intentionally not decrypted/scanned or backfilled automatically. Those historical values require a separately previewed and approved index repair before PAN search can find them. Existing IDs/unique constraints are unchanged.

Owner-only application deletion is available in grouped expansion with confirmation, through the existing Bin API. Existing Bin controls remain the sole delete/recovery mechanism. Customers with active applications and Leads with active applications cannot be deleted through an unsafe parent operation. Applications with open workflow cases require dependency review first. Application deletion never deletes its Customer or sibling applications. Automatic physical purge now skips Customer/Application entries, preserving shared identity/document data for explicit retention review; restoration still follows existing retention eligibility. Other modules retain their existing Owner-only Bin permissions.

## Authentication

Registration and recovery continue using the existing OTP/PIN service, delivery adapter, ownership proof, transaction, expiry/attempt/rate/lock controls and session revocation. Login does not create accounts. A safe uniform login-failure message now gives mobile/PIN checks, Forgot PIN/Create Account and lock-wait guidance without confirming account existence. Employee/partner/Owner authentication and Airtel configuration are unchanged. Browser OTP tests use mocked SMS transport and a disposable loopback Mongo replica set; no live delivery is claimed.

## Database and preservation

Additive Customer PAN lookup digest and response version; profile history remains in the existing Customer document. Added ownership/status/date pagination, customer/product, current-document and assignment-audit join indexes. No unique constraint changes, identity regeneration, customer merge, full-collection rewrite or production backfill. Schema labels are presentation aliases. Application submission snapshots and documents retain their IDs/content. The original standalone local Mongo was left intact; transaction tests use a separate owned loopback replica set and disposable databases.

## Validation

Actual final results are appended after the last checks. Counts from overlapping runs must not be added together. Test artifacts under `docs/screenshots/enterprise-crm-2026-11-25` contain synthetic data only. Production configuration, real Airtel delivery and actual production query plans were not accessed or verified.

## Deployment instructions - manual, not executed

Do not assume a deployment directory. The commands below derive it from the installed backend service and verify the repository root. Service names come from the repository's deployment documentation; verify those units exist on the intended server first. Use the established backup procedure, a reviewed clean release, and the existing intended backend environment without printing secrets. No production migration/backfill is included.

```bash
BACKEND_UNIT=afs-crm-backend.service
WORKER_UNIT=afs-crm-worker.service
BACKEND_DIR=$(systemctl show "$BACKEND_UNIT" --property=WorkingDirectory --value)
test -n "$BACKEND_DIR" && test -f "$BACKEND_DIR/pyproject.toml" || exit 1
APP_ROOT=$(git -C "$BACKEND_DIR" rev-parse --show-toplevel) || exit 1
test -z "$(git -C "$APP_ROOT" status --porcelain)" || exit 1
RELEASE_COMMIT='<reviewed-release-commit>'
git -C "$APP_ROOT" fetch origin
git -C "$APP_ROOT" checkout --detach "$RELEASE_COMMIT"
cd "$BACKEND_DIR"
# With the established production environment loaded securely:
.venv/bin/python "$APP_ROOT/scripts/audit_unified_crm.py"
# Stop if identity/dependency issues are reported; do not repair them automatically.
.venv/bin/pip install .
cd "$APP_ROOT/frontend"
npm ci
npm run build
sudo systemctl restart "$BACKEND_UNIT" "$WORKER_UNIT"
sudo systemctl status "$BACKEND_UNIT" "$WORKER_UNIT" --no-pager
sudo nginx -t && sudo systemctl reload nginx
```

The existing frontend hosting configuration must serve this release's dist directory. Backend and worker must run the same approved release. Startup adds the new indexes through the existing initializer. Review index creation time for the actual production dataset before rollout. Run the normal health checks, then test authorized grouping/search/profile edit and Bin recovery with an approved synthetic record. No live SMS is necessary for rollout validation. Rollback uses the previous approved code/artifact and restarts both services; do not drop additive fields, indexes or history, or reverse business/profile edits automatically.


## Final validation outcomes

| Check | Actual result |
| --- | --- |
| Full frontend suite | 500 passed, zero failed |
| Final affected frontend rerun | 15 passed across six files |
| Backend focused integration | 98 passed (90 dependency warnings) |
| Broader auth/employee/loan/insurance/reminder/integration regression | 173 passed (44 warnings) |
| Product schema/PAN regression | 22 passed |
| Final identity/grouping/combined-filter real-Mongo regression | 10 passed |
| Bin regression | 12 passed |
| Staff integrated browser journey | 1 passed; 390, 768, 1366 pixels |
| Customer OTP registration/login/recovery browser | 1 passed; 390, 768, 1366 pixels; SMS mocked |
| TypeScript and final production build | Passed; existing large-bundle advisory |
| ESLint | Zero errors, eight existing fast-refresh warnings |
| Ruff and formatting | Changed Python code lint passes; new modules/tests formatted |
| Strict new-module mypy | Four source files, zero errors |
| Full project mypy | 117 errors in 12 files, identical to clean HEAD baseline; zero added diagnostics |

These backend runs overlap and are not a summed distinct-test count. The original standalone Mongo could not execute transactional registration; those tests were rerun successfully on an owned, disposable loopback replica set. The broad initial test run's password-reveal expectations were deliberately updated to assert write-only rejection while retaining encryption, audit hygiene and unauthorized-access coverage.

The large fixture contains 1,212 applications across 206 customer groups, verifies a complete 200-group page plus remaining groups, all supported page sizes, stable/nonoverlapping pages and search beyond the previous 1,000-row cap. Additional real-Mongo checks compose assignment, actor/date, product/status, source/branch/designation, customer status, follow-up/bank/overdue and document filters with AND semantics. This is local correctness evidence, not a production latency or query-plan benchmark.

Browser screenshots were inspected. Final profile/delete modal checks also assert that their bounding rectangles fit the viewport. The newer document-specific password contract, numeric date inputs, safe stale-date handling and schema normalization have regression coverage. Authentication browser checks verify OTP before account creation, PIN login, recovery, old-PIN rejection and no PIN/OTP persistence in localStorage. No SMS was transmitted.

Evidence: [validation](screenshots/enterprise-crm-2026-11-25/validation.json), [staff browser](screenshots/enterprise-crm-2026-11-25/results.json), [OTP browser](screenshots/enterprise-crm-2026-11-25/otp/results.json), [type-check baseline comparison](screenshots/enterprise-crm-2026-11-25/typecheck-comparison.json), [preservation](screenshots/enterprise-crm-2026-11-25/preservation.json), [changed files](screenshots/enterprise-crm-2026-11-25/changed-files.txt).

Production records, production service configuration and real Airtel delivery remain unverified because no production access/deployment/SMS was performed. Historical PAN index repair and any migration from legacy ungrouped API consumers require an explicit subsequent operational decision; neither is silently applied by startup or deployment. The implementation is frozen after the reported checks.

Final cleanup: owned Vite preview and disposable replica set were stopped. The pre-existing MongoDB on port 27017 remains untouched. Historical screenshots/build cache were restored; final Ruff and whitespace checks pass. The password-access authorization check also passed after test-only lint cleanup.
