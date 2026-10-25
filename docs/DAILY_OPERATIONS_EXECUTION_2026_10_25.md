# Daily Operations execution — 2026-10-25

## Inspection and implementation checklist

Baseline: branch `main`, HEAD `4c70325`; no tracked changes reported by initial git status.
FastAPI/Pydantic 2, Motor/MongoDB, Redis/ARQ, React 19/Vite/TypeScript/React Query.
Authentication: shared users, JWT access tokens and rotating refresh-token session families.
Authorization: PermissionEngine, Owner bypass, employee assignment scopes. BaseDocument explicitly
defers tenant_id; this deployment is single organization, not verified multi-tenant.
Mongo indexes are installed at application startup; scripts provide additive migrations/seeds.
Existing openpyxl/defusedxml bounded parser supports CSV/XLSX (5 MB, 500 rows).
Existing loans use ApplicationWorkflow, LoanCaseDetails, bank offers and status history;
the example lifecycle must not replace these. Leads already have notes and follow-up dates.
Sessions already record real authentication; rotation rows must be grouped by family.
SupportTicket requires a customer and its creation triggers customer-service effects: employee
operational issues need a separate internal workflow, without duplicating customer support.
Existing business timezone is Asia/Kolkata, timestamps UTC. Spreadsheet screenshots were not
attached; mapping is based on the headings in the supplied request.

File-level plan:

- [x] `backend/app/features/daily_operations/`: follow-up schemas/service/routes, atomic history,
  linked-record validation, optimistic concurrency, operational issues, session reporting.
- [x] Reuse existing canonical loan service/routes for lifecycle mutations, expose progress view.
- [x] `backend/app/features/bulk_import/files.py`: reusable bounded parser extension.
- [x] Daily operations transfer routes: templates, preview/revalidation, bounded row commits,
  idempotency, sanitized errors, CSV/XLSX export; never import fabricated sessions/financial values.
- [x] `backend/app/main.py`: additive router/index initialization.
- [x] `scripts/migrate_daily_operations.py`: additive permissions/nav/index installation.
- [x] `frontend/src/features/daily_operations/`: responsive tables, forms, transfer preview.
- [x] Router/nav: add DAILY OPERATIONS without replacing existing sections.
- [x] Backend/frontend tests, regressions, build/lint/types; evidence and release limitations below.

No production systems, calls, migrations or external messaging are authorized by this task.

## Executive summary and release verdict

Implemented the four operational work areas and a transfer centre within the existing CRM.
The new module reuses leads, applications, canonical loan cases, users, employees, session
families, permissions, UI primitives and internal notifications. Existing workflows remain
in place; customer support remains separate from internal employee issues.

**IMPLEMENTATION COMPLETE — PRODUCTION READINESS NOT YET VERIFIED.**

This verdict describes the bounded implementation below. It does not certify a deployment,
real-database migration, production permissions, backup recovery, browser accessibility or
production-scale performance. Repository-wide strict backend typing also remains a failed
release check in unchanged code; the new module itself passes strict typing.

## Implemented behavior and spreadsheet mapping

| Spreadsheet concept | CRM representation |
| --- | --- |
| DATE | Operational calendar date; stored as UTC instant of IST midnight, following existing helpers |
| LOAN TYPE | Read-only existing lead loan-product name; loan progress uses existing loan details |
| BANK / NBFCs | Follow-up bank text, bounded to 200 characters; existing CRM has no bank master |
| CX NAME / CX NUMBER | Derived from linked lead/customer; supplied import values must match, never create an identity |
| TODAY CASE STATUS | Follow-up status only; does not mutate the underlying loan lifecycle |
| REMARKS DATE / REMARKS | Current remark with atomic historical snapshots of every save |
| FOLLOW PENDING | Due calendar date, with a required next action for open follow-ups |
| Named employee columns | Current existing Lead.assigned_to; names resolved from employee records, no hardcoded names |
| APPLIED BANK OR NBFC / BANK OR NBFC | One normalized bank value from canonical loan details, not repeated milestone columns |
| LEAD ID | Actual CRM ObjectId, not customer name or telephone matching |
| TODAY CASE STAGE / CASE STAGE | Canonical ApplicationWorkflow.current_status; edit through existing Loan Management |
| WHAT'S NEXT FOLLOW-UP TMROW | Linked daily follow-up action; canonical due date is the fallback when no daily plan exists |
| OLD CASES UNDER PROGRESS | Derived age in days; minimum-age filter excludes existing canonical terminal statuses |
| DATE OF LOGIN | Existing Application.created_at, explicitly an application creation date; no invented bank login timestamp |
| APPROVED LOAN AMT | Existing LoanCaseDetails.offered_amount (selected offer), never inferred from follow-up text |
| UPDATE DATE | Canonical workflow.updated_at |
| DATE OF DISBURSE / LOAN AMOUNT | Canonical disbursed_at / disbursed_amount, shown only for disbursed cases |
| EMPLOYEE NAME / LOGIN TIME / LOGOUT TIME | Existing employees and auth session families; refresh rotations grouped into one login |
| INQUIRY OR ISSUE | Internal operational issue, with priority, assignee, resolution and audit fields |

Repeated spreadsheet headings are normalized into one linked loan/case and its existing
timeline. The UI keeps recognizable terminology; imports use explicit additional ID,
version, action and reason columns when necessary for integrity. Read-only identity columns
are present in follow-up templates but may be left blank for server derivation.

Follow-ups and issues support create/edit, bounded paging, text search, date/status/employee
filters and sorting. Follow-ups additionally support bank, loan-type and overdue filters.
Progress supports case-code search, date/stage/employee/bank/type/age filters and links to the
existing editable loan and timeline. Session reporting supports dates, employee selection,
pagination, original timestamps and Owner-only corrections. Loading, empty, server-error,
retry and success states use existing components. Tables scroll on narrow screens; forms
use labeled controls and the shared keyboard/focus-managed Modal.

Operational summaries use the same filtered datasets as the lists. Follow-up status,
employee, bank and loan-type summaries count follow-up records, not unique customers/cases;
breakdowns are limited to the largest 100 groups. Progress financial totals aggregate
canonical loan data across all filtered pages. Multiple DISBURSE follow-up rows do not
multiply financial totals. Existing dashboard metrics are unchanged; the sidebar provides
the minimal new integration.

## Files changed

New backend feature files under `backend/app/features/daily_operations/`:
`__init__.py`, `schemas.py`, `service.py`, `views.py`, `transfers.py`, `router.py`,
`upload_limits.py`, `notifications.py`, `catalog.py`.

Other backend integration files: `backend/app/main.py`,
`backend/app/features/bulk_import/files.py`, `backend/app/features/reminders/constants.py`,
`backend/app/worker/worker_settings.py`, new `backend/app/worker/tasks/daily_operations.py`.
The existing parser accepts optional schema/column/mapping arguments; existing callers
retain their previous defaults. No dependencies or existing applied migrations changed.

New frontend feature files under `frontend/src/features/daily_operations/`:
`api.ts`, `DailyOperationsPage.tsx`, `RecordForm.tsx`, `TransferCentre.tsx`,
`DailyOperations.test.tsx`.

Other frontend integration files: `frontend/src/app/router.tsx`,
`frontend/src/components/layout/navConfig.ts`,
`frontend/src/features/reminders/notificationDestination.ts`.

Migration/seed: new `scripts/migrate_daily_operations.py`, additive `scripts/seed.py` hook.
Tests: new `tests/api/test_daily_operations.py`. Documentation: this file.
Generated TypeScript build metadata is restored to its original content after verification.

## Storage, indexes and audit

New collections:

- `daily_follow_ups`: linked lead ObjectId, optional existing case ID, dates, summary,
  derived identity snapshot, version, import key and protected embedded history.
- `operational_issues`: creator identity, assignee, priority/status/resolution, version,
  import key, assignment notification marker and protected embedded history.
- `session_corrections`: keyed by existing session family; corrected timestamps, reason,
  version and correction history. Authentication rows/tokens are never changed.
- `daily_imports`: actor-bound normalized preview rows, explicit update opt-in and 30-minute
  expiry. TTL index deletes preview documents asynchronously; expiry is also checked in code.
- `daily_notification_cursors`: bounded worker scan positions and delivery counts.

Indexes: unique `import_key` on follow-ups and issues; compounds for deletion/assignee/date
and deletion/status/due date; follow-up lead ObjectId, case/update and bank/date indexes;
issue creator/deletion/date index; import expiry TTL. Session correction/cursor identity
uses Mongo's built-in unique `_id`. Existing indexes remain intact.

Create/update summary and its before/after history are written in the same Mongo document
operation. Updates compare the expected version and increment it atomically. No API accepts
arbitrary history, creator, updated-by or assignment audit values. Follow-up/issue history
is bounded to 250 saves to stay below Mongo's document size limit; reaching the bound fails
explicitly without discarding history. Session corrections allow up to 1,000 history entries.
An archive/export procedure is required before unusually long-running records reach these
bounds; no automatic archival/deletion is implemented.

Shared audit events record preview, commit counts, exports and internal notification delivery
using record/batch IDs, never uploaded customer text. Source histories contain confidential
before/after values and are accessible only through the record's authorized detail route.
Database-level immutability/runtime-role hardening has not been verified against a real server.

## API surface

All routes are under `/api/v1/daily-operations` and use the existing response/error envelope.

| Method and route | Purpose |
| --- | --- |
| GET `/follow-ups`, `/issues` | Filtered, sorted, paginated records and summaries |
| POST `/follow-ups`, `/issues` | Validated creation |
| GET/PATCH `/follow-ups/{id}`, `/issues/{id}` | Scoped history/detail and optimistic update |
| GET `/progress` | Canonical loan progress and financial aggregates |
| GET `/sessions` | Employee authentication-family report, original and corrected timestamps |
| POST `/sessions/{family}/correction` | Owner-only audited correction with expected version |
| GET `/transfers/{area}/template?format=csv|xlsx` | Exact accepted import headings |
| POST `/transfers/{area}/preview` | Multipart file, optional mapping JSON, optional allow_updates |
| POST `/transfers/{batch}/confirm` | Explicit `{ "confirmed": true }` and row revalidation |
| GET `/{area}/export?format=csv|xlsx` | Authorized export of the selected filters, maximum 500 rows |

Areas are `follow-ups`, `progress`, `sessions`, `issues`. Progress lifecycle mutation and
history continue to use the existing loan APIs. Error reports are generated by the frontend
from sanitized row/column messages; uploaded customer values are excluded from those reports.

## Permission and isolation rules

The additive `daily_operations` permission catalog uses the existing action vocabulary:
view/create/edit/import/export; issues additionally use assign and **approve** (resolve).
Progress has view/import/export; sessions have view/edit/import/export. The catalog migration
does not grant any employee access. Owner bypass follows the existing PermissionEngine.

Employees see follow-ups through the CURRENT assigned lead and also need lead-view permission.
Linked loan access must independently pass canonical LoanCaseService visibility and loan-view
permission. List ownership is resolved through the lead lookup so reassignment does not leave
the old employee with access. Employee issues are visible to their creator or assignee;
assignment and resolution require their separate permissions. Employees see only their own
session families and can never correct them, even with an edit grant. Only Owners correct
existing employee sessions. Progress uses current loan assignment and existing moved-to-loan
eligibility. Hidden frontend actions supplement, but never replace, server authorization.

This repository is single-organization: BaseDocument explicitly defers tenant_id. No
multi-tenant isolation or Mongo row-level security is claimed. Adding multi-tenancy needs a
separate repository-wide design, rather than pretending new records alone establish isolation.

## State and import rules

Open follow-up states are exactly FOLLOW UP PENDING and NEXT FOLLOW UP. Both require a next
action and due date; the due date cannot precede DATE. REJECTED WITH REASON requires a reason.
DISBURSE requires a correctly linked canonical loan already marked disbursed with verified
amount/date/reference fields. Resolved follow-ups cannot carry a pending due date. Following
the existing lifecycle, the daily status does not itself reject, approve or disburse a loan.
Follow-up statuses can be corrected with history; no new irreversible loan transitions exist.
Lead identity is immutable; an initially missing case link can be added after relationship
validation, but an existing case link cannot be silently replaced.

Issues start OPEN. Allowed transitions: OPEN → IN PROGRESS/RESOLVED;
IN PROGRESS → RESOLVED; RESOLVED → REOPENED; REOPENED → IN PROGRESS/RESOLVED.
Same-state edits are allowed. Resolution requires notes and approve permission. Reopening
clears the current resolution summary while prior notes/date remain in history.

Files are limited to 5 MB and 500 rows. Whole multipart envelopes are bounded before spooling
(file limit plus 64 KiB overhead), including chunked requests, with two concurrent uploads
per API process. Oversized/malformed files, unsupported extensions/MIME combinations, macros,
external workbook links, encrypted archives, sparse oversized sheets, unknown/repeated
columns and formula-prefixed import cells are rejected. The existing hardened parser reads
the first worksheet only. No formulas or macros execute. Additional worksheets are ignored.
CSV and XLSX output forces untrusted values to text and neutralizes formula prefixes.
Files are parsed in memory; framework multipart temp files are closed at request completion.
Preview rows remain in Mongo only until expiry/TTL cleanup and must be covered by normal
confidential-data backup and access controls.

Duplicate policy: no names or telephone numbers establish identity. Exact normalized rows
under the same actor/area receive a durable fingerprint; repeated rows/files skip committed
operations, including across preview expiry. Semantically different follow-up attempts may
legitimately target the same lead. Updates default OFF; enabled follow-up/issue updates need
RECORD ID, VERSION, edit permission and confirmation. Stale versions fail instead of
overwriting another employee. Each successful row and its audit history are one atomic
document write; rows commit independently, not as a whole-file transaction. After interruption,
upload/confirm again and committed fingerprints skip safely. A failed shared audit/response
write can require a retry, without duplicating a committed business row.

Loan-progress imports add follow-up actions to existing cases and require an existing linked
lead and bank. They do not create applications or import historical financial snapshots;
loan stages, banks, offers, amounts and disbursements must use canonical Loan Management.
Session imports only correct existing families with reason/version and Owner authorization;
they never fabricate employee logins or payroll hours. Exports include extra audit metadata;
use the import templates and remove unsupported metadata columns before reimporting.
Large files must be split; no unbounded/background bulk-file import is provided.

## Internal automation

An ARQ task checks due/overdue follow-ups and issue assignments every 15 minutes. Scans are
bounded to 100 records per area with rotating cursors, so inaccessible records cannot starve
later candidates. Deterministic notification IDs prevent duplicate inbox entries after
retries/crashes. Delivery uses current active users and view permissions (and lead view for
follow-ups). Messages contain no customer details; destination pages reauthorize access.
Notification source markers are conditionally updated. Cursor records expose the last scan
result. Existing internal inbox semantics apply; the CRM has no per-user notification
preference model to extend. No email, SMS, WhatsApp, paid API, or external delivery was added.

## Verification evidence

Commands use the existing `backend/.venv` because the system Python lacked defusedxml and
had an older openpyxl. Test commands set `$env:DEBUG='false'` for that process: the inherited
host DEBUG value was `release`, which is not a valid Settings boolean. No local env file was
edited. The first root-level pytest invocation also lacked the backend pytest configuration;
the corrected commands below explicitly select it. Those setup failures are not counted as
passing tests.

| Status | Check and actual result |
| --- | --- |
| PASS | Full backend regression: `backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests -q -n 4 --tb=short` — **1,437 passed, 1 skipped, 645 warnings; 703.57 s**. The skip is the Linux-only POSIX resource-limit test on Windows. |
| PASS | Final affected backend rerun after the last functional changes: same command targeting `tests/api/test_daily_operations.py tests/api/test_bulk_import.py tests/api/test_reminders.py -n 3` — **85 passed, 90 warnings; 87.20 s**. Covers the final schemas, templates, update opt-in, fingerprints, concurrent confirmation, dates and notifications. |
| PASS | Full frontend rerun: `npm test -- --maxWorkers=2` — **73 files, 361 tests passed; 165.00 s**. A preceding run timed out in an unchanged AddInsuranceLeadModal test under concurrent load (360 passed/1 timeout); the unchanged test passed in the successful complete rerun. No timeout setting or assertion was weakened. |
| PASS | `npm run typecheck` and `npm run build` — TypeScript passes; Vite build passes (413 modules). Existing architecture still emits a >500 kB bundle warning; final main bundle approximately 1.336 MB uncompressed. |
| PASS | `npm run lint` — zero errors, ten warnings in unchanged files. |
| PASS | Backend `ruff check` across app plus new migration/tests — no lint errors after fixing the new import order. |
| PASS | `ruff format --check` for new feature/parser/task/migration/tests — 13 files formatted. |
| PASS | Strict module typing: `mypy --config-file backend/pyproject.toml backend/app/features/daily_operations backend/app/worker/tasks/daily_operations.py --follow-imports=silent` — **10 source files, no issues**. |
| FAIL | Repository-wide `cd backend; .venv/Scripts/python.exe -m mypy app` — **116 errors in 11 unchanged files (388 checked)**: invoice PDF/router/schemas/calculations, customer validation/service, auth/owner/loan/lead services and lead router. No new-module errors remain. These unrelated typing failures were not hidden or weakened. |
| PASS | `backend/.venv/Scripts/python.exe -m pip check` — no broken requirements. |
| PASS | `cd frontend; npm ls --depth=0` — installed top-level dependency tree resolves without errors. |
| PASS | Migration catalog/index tests against isolated mongomock, including repeat installation and no implicit grants. |
| PASS | `git diff --check` — no whitespace errors. |
| BLOCKED | Real MongoDB migration, runtime-role/constraint behavior and real-database persistence/concurrency/load checks. `mongod` was not found; Docker CLI exists but its engine pipe is unavailable. No real test database was selected, and no existing configured database was contacted. |
| NOT RUN | Production migration/deployment, production role inspection, backup/restore rehearsal and external acceptance; not authorized. |
| NOT RUN | Browser/assistive-technology visual/accessibility acceptance and realistic production-volume benchmarks. UI tests use the existing jsdom infrastructure. |
| NOT RUN | Online vulnerability audit; no dependencies changed. Installed dependency consistency is checked separately above. |

Full regression ran before the final isolated module additions; the final affected-suite run
then covered the current implementation. These are complementary recorded runs, not a claim
that a single full run included every later-added test. Raw local output is retained under
`.pytest_cache/daily-operations-*.txt` (ignored, not shipped as source).

## Deployment, recovery and remaining acceptance

1. Review code, field mapping and the limits above with the owner. In particular confirm
   application creation date is the intended DATE OF LOGIN meaning and validate against the
   original screenshots (not supplied here). Do not use session duration for payroll.
2. Provision/select an explicitly isolated real MongoDB test environment. Run additive index
   installation and test import, correction, reassignment, history, restart/retry and realistic
   query plans there. Verify compatible Mongo aggregation support and least-privilege runtime
   access. Schema relationships are enforced by services; Mongo has no SQL-style foreign keys.
3. Back up the new collections along with leads, applications, workflows, users, employees,
   sessions and audit_logs. Rehearse restoring their linked IDs and embedded histories together.
   Session correction/import data needs the same confidential-data protections as CRM data.
4. After explicit owner authorization for the target deployment, run from `backend`:
   `.venv/Scripts/python.exe ../scripts/migrate_daily_operations.py` using that target's
   approved configuration. The script only adds catalogs/indexes; no backfill or business
   mutation occurs. Existing `seed.py` also calls this additive installer for fresh setups.
5. Owner assigns the required new permissions using existing role management. Lead/loan view
   permissions remain independently necessary. Verify representative employee accounts and
   inaccessible-object attempts before release. No blanket employee access is seeded.
6. Deploy backend/frontend through the existing release process and update the existing ARQ
   worker to load the new internal notification task. No worker or server was restarted here.
   Monitor import rejection rates, 409 conflicts, upload-capacity responses, TTL cleanup,
   history limits and notification cursor progress. Keep backup retention for idempotency
   markers and audit histories; deleting them can affect duplicate detection.
7. Rollback is a code rollback to the prior approved release plus worker version, retaining
   all new collections. Old code ignores the additive data. Remove/hide only new navigation
   catalog rows if needed; do not delete operational records, correction overlays or histories.
   Reapplying the migration is idempotent. Prefer forward fixes to data rewrites. Real-server
   rollback and restore rehearsal remains a release prerequisite, not a claimed local result.

Owner/external dependencies: source screenshot review; real test database and production
acceptance access; existing strict typing cleanup before a fully green release gate;
browser accessibility and scale verification; operational history-archive procedure at the
document bounds. Any future historical financial import, payroll attendance policy,
multi-tenant conversion, larger background import capability or external messaging needs its
own approved scope rather than bypassing the controls above.
