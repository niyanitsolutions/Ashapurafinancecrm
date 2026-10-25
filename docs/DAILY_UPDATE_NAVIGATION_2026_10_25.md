# Daily Update navigation and integration — 2026-10-25

Baseline: clean `main` at `9fe65d8` (Daily operations nav added). The prior implementation
report and existing sidebar, ModuleTabs, Insurance Management layout, router, permission
engine and dashboard navigation service were inspected before editing.

Verified repository defect: Sidebar only renders keys returned by `/dashboard/nav`.
Daily Operations catalog installation ran only in the manual seed/migration, while normal
application startup installed only its indexes. Missing catalog rows therefore hide every
Daily Operations link even for an Owner. A second defect is the five sidebar entries with
no shared tab layout. Local HEAD contains the feature commit. The deployed Git revision and
database state are not verified; the supplied screenshot cannot establish them, and a
read-only public-site requests were inaccessible through both the web tool and a native
HTTPS request (WebException). No authenticated production access, deployment, migration
or restart has been performed. The actual deployed branch, bundle and catalog contents
remain external verification steps; the screenshot alone does not prove their state.

Implementation checklist:

- [x] Replace five sidebar leaves with one Daily Update leaf, preserving other order.
- [x] Nest the existing five routes under a shared ModuleTabs layout and retain bookmarks.
- [x] Resolve the default tab from real permissions and reject unauthorized direct routes.
- [x] Keep filters/page in the existing route's query parameters.
- [x] Install the existing additive catalog idempotently during normal backend startup.
- [x] Verify navigation, owner/employee scoping, imports/exports and relevant regressions.
- [x] Record exact checks, deployment steps and remaining acceptance boundaries below.

## Final structure and behavior

One sidebar leaf, **Daily Update**, appears after Insurance Management and before Finance /
Billing. The previous five Daily Operations sidebar leaves are removed. Every other sidebar
item keeps its name, destination and relative order. The existing Sidebar, AppShell, Topbar,
greeting, mobile drawer and collapse behavior are retained.

The parent `/daily-operations` route renders `DailyUpdateLayout`. It places the shared
`ModuleTabs` immediately below the existing CRM header and renders only the selected
existing page through an Outlet. The same orange text/underline, hover styles, spacing
and horizontal overflow used by Insurance Management apply. Route links support Tab/Enter
keyboard activation and `aria-current="page"`; the strip has an accessible navigation label.
Insurance Management markup/styles/behavior are unchanged; the shared component only gains
an optional accessible label.

| Tab | Stable route | Existing functional component |
| --- | --- | --- |
| Daily Follow-up Data | `/daily-operations/follow-ups` | DailyOperationsPage, follow-ups |
| Loan Progress Tracking | `/daily-operations/progress` | DailyOperationsPage, progress |
| Employee Login & Logout | `/daily-operations/sessions` | DailyOperationsPage, sessions |
| Inquiry or Issue | `/daily-operations/issues` | DailyOperationsPage, issues |
| Import & Export Centre | `/daily-operations/transfers` | TransferCentre |

All existing tab URLs/bookmarks are preserved. The bare parent route selects the first tab
the current user may view, so an Employee with issue-only access lands on Inquiry or Issue
rather than an inaccessible follow-up page. The default redirect retains search/hash;
direct tab URLs stay on that tab after refresh. Search, filters, sort and pagination now
use query parameters and are restored on refresh/back navigation. Switching to a different
tab starts its own filter scope. Existing distinct page keys prevent form/filter state
from leaking between work areas. Other tabs' datasets are not prefetched.

No follow-up/loan/session/issue models, lifecycle rules, API endpoints or reporting formulas
were replaced. Existing forms, spreadsheet headings, tables, history and import processing
remain in use. Customer Support Tickets remain unchanged; the pre-existing employee issue
workflow is reused as implemented in the prior module.

## Root-cause fix and access control

The backend now calls the existing `install_catalog` from normal application lifespan,
instead of calling only `ensure_daily_operations_indexes`. The installer still creates its
indexes and uses `$setOnInsert` to register four area permission/nav definitions. Repeated
startup is idempotent, existing definitions are preserved, and no employee role grants or
business records are created or changed. No new migration file is necessary; the existing
manual migration remains valid for explicitly approved release procedures.

A regression test reproduces missing navigation with an otherwise functioning dashboard,
runs the real lifespan catalog path with unrelated startup services isolated, and verifies
that all four nav keys become visible to the canonical Owner. Running startup twice does
not duplicate definitions or grant employees permissions. The sidebar consolidates these
four existing backend keys into a single frontend leaf, following the CRM's existing
consolidated-navigation pattern. The database does not need a duplicate parent permission.

Tab visibility uses the existing server-computed effective permissions through
`usePermissions`; Owner's canonical role bypass gives access to all five tabs. Employees
see only view-authorized areas. The transfer tab is shown only when at least one visible
area permits import or export; destination choices are similarly filtered. Export-only
users can open the correct area for filtered exports without being offered uploads.
Unauthorized direct routes render an access-denied state before mounting the feature page.

Sidebar navigation cache keys now include authenticated user ID. A second account cannot
reuse the first account's cached nav allow-list. The existing permissions cache and page
dataset keys already include authenticated identity. Loading permissions does not start
data queries. Backend list/detail/create/edit/assignment/import/export/aggregate/session
correction checks are unchanged and independently enforce real access even when frontend
controls or URLs are bypassed. Record scoping and the repository's single-organization
model remain as documented in the prior implementation report; no new tenant bypass exists.

## Exact files changed

- `backend/app/main.py`: automatic additive catalog installation at normal startup.
- `frontend/src/components/layout/navConfig.ts`: one Daily Update sidebar leaf.
- `frontend/src/components/layout/ModuleTabs.tsx`: optional accessible strip label.
- `frontend/src/components/layout/useNavKeys.ts`: user-scoped nav cache.
- New `frontend/src/components/layout/useNavKeys.test.tsx`: cross-account cache regression.
- New `frontend/src/features/daily_operations/navigation.ts`: shared ordered tab definitions
  and effective permission filtering.
- New `frontend/src/features/daily_operations/DailyUpdateLayout.tsx`: persistent strip,
  first-authorized default routing, loading and direct-route denial.
- `frontend/src/app/router.tsx`: existing five functional routes nested under that layout.
- `frontend/src/app/router.test.tsx`: actual route/component wiring regression.
- `frontend/src/features/daily_operations/DailyOperationsPage.tsx`: query-backed filters/page
  and permission-aware transfer link.
- `frontend/src/features/daily_operations/TransferCentre.tsx`: authorized destinations and
  filtered-export link, reusing the existing import implementation.
- `frontend/src/features/daily_operations/DailyOperations.test.tsx`: updated single-leaf check.
- New `frontend/src/features/daily_operations/DailyUpdateLayout.test.tsx`: sidebar/tab/page,
  permission, loading, keyboard, refresh and filtering integration tests.
- New `tests/api/test_daily_update_navigation.py`: startup recovery, idempotency, canonical
  Owner access and Employee navigation/API/import/export denial.
- New `scripts/daily-update-ui-check.mjs`: local Chrome/Playwright navigation regression
  harness using isolated synthetic API fixtures and existing cached development tooling.
- New `docs/screenshots/daily-update-2026-10-25/`: desktop/mobile screenshots, denied Employee
  screenshot and evidence.json. These contain synthetic identities and no production data.
- This report. Generated TypeScript build metadata is restored after checks.

## Checks executed

PowerShell test processes set `$env:DEBUG='false'` because the host's inherited DEBUG value
is `release`; no environment files or production settings are edited. Python commands use
the existing backend virtual environment and explicitly select its pytest configuration.

| Status | Executed check and actual result |
| --- | --- |
| PASS | Targeted frontend: `npm test -- src/features/daily_operations src/components/layout/useNavKeys.test.tsx src/app/router.test.tsx src/features/insurance_management/pages/InsuranceManagementLayout.test.tsx --maxWorkers=2` — **33 tests in 5 files**, 10.18 seconds. |
| PASS | Full frontend: `npm test -- --maxWorkers=2` — **378 tests in 75 files**, 193.98 seconds. Includes unchanged Insurance Management, Dashboard, Leads, Loan Management and other UI regression tests. |
| PASS | Targeted backend: `backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_daily_update_navigation.py tests/api/test_daily_operations.py -q -n 2 --tb=short` — **43 passed**, 90 mongomock deprecation warnings, 29.41 seconds. |
| PASS | Broader backend regression: same pytest options with `-n 4`, targeting `test_daily_update_navigation.py`, `test_daily_operations.py`, `test_bulk_import.py`, `test_reminders.py`, `test_dashboard.py`, `test_leads.py`, `test_loan_management_visibility.py`, `test_loan_management_redesign.py`, `test_workflow.py`, `test_reporting.py` under `tests/api/` — **266 passed**, 90 warnings, 201.45 seconds. |
| PASS | `npm run typecheck` — no TypeScript errors. |
| PASS | `npm run build` — TypeScript and Vite succeed, 415 modules; Vite build 20.02 seconds. Existing >500 kB chunk warning remains (main bundle 1,336.90 kB / gzip 346.45 kB). |
| PASS | `npm run lint` — zero errors; ten warnings in unchanged files. |
| PASS | `backend/.venv/Scripts/python.exe -m ruff check backend/app tests/api/test_daily_update_navigation.py` — no lint errors. |
| PASS | `ruff format --check tests/api/test_daily_update_navigation.py` — formatted. Frontend has no separate formatter command; ESLint and whitespace checks apply. |
| PASS | `mypy --config-file backend/pyproject.toml backend/app/main.py --follow-imports=silent` — no issues in the changed backend entrypoint. |
| FAIL | Repository-wide `cd backend; .venv/Scripts/python.exe -m mypy app` — **116 errors in 11 unchanged files (388 checked)**, matching the previous report. No changed-entrypoint errors. Unrelated invoice and other existing typing failures are not suppressed or weakened. |
| PASS | Local Chrome/Playwright: `frontend/node_modules/.cache/voice-node22/node.exe scripts/daily-update-ui-check.mjs` — **3 scenarios**: Owner at 1440px, Owner at 390px, and restricted Employee. All five tabs exercised, active styles, no full-page reload on switches, query/refresh, keyboard/sidebar selection, mobile scrolling and direct-route denial checked. No Owner browser page errors. |
| PASS | Browser screenshots reviewed at desktop/mobile widths. Mobile strip measured scrollWidth 899 / clientWidth 390 with overflow-x:auto. Desktop tabs fit the 1160px content width. Unauthorized Employee progress page made zero progress API requests. |
| PASS | `git diff --check` — no whitespace errors. |
| BLOCKED | Actual deployed Git branch/revision, public bundle inspection, authenticated live nav response and production catalog verification. Public-site read attempts failed; no production session or server access was used. |
| NOT RUN | Production deployment/migrations/restarts, real-server catalog installation, real-database release smoke tests or production-scale performance tests. These are outside the authorized local implementation boundary. |

The browser harness uses real frontend components with synthetic local API responses; it
is not evidence of real persistence or live production access. Backend fixtures use the
repository's isolated mongomock database and real API authorization paths. The system Node
18 was too old for the existing cached Playwright, so the already-cached local Node 22.23.3
runtime was used; no dependencies/software were installed. An initial dev-server browser
navigation timed out under concurrent checks; the successful run used a warmed local
server and an explicit DOM-ready navigation wait. Assertions were not removed or bypassed.

Browser evidence: [desktop](screenshots/daily-update-2026-10-25/owner-1440.png),
[mobile](screenshots/daily-update-2026-10-25/owner-390.png),
[restricted Employee](screenshots/daily-update-2026-10-25/employee-denied.png),
[machine-readable checks](screenshots/daily-update-2026-10-25/evidence.json).

## Deployment instructions for owner review

1. Review this change and the existing Daily Operations limitations. Verify the intended
   release includes the original feature commit `9fe65d8` plus this navigation fix. The
   actual currently deployed revision is not established by this local work.
2. In an approved isolated/staging environment, deploy matching backend and frontend builds
   through the existing release process. Normal backend lifespan now installs missing
   code-backed catalogs/indexes. Confirm that the runtime has the existing required catalog
   and index privileges. It does not grant employees access or reset business data.
3. Verify authenticated `/api/v1/dashboard/nav` returns the four `daily_*` area keys for an
   Owner. For an Employee, expect only keys backed by that account's effective view grants.
   If keys are missing, inspect that environment's startup completion, permission/nav
   catalog rows, soft-deletion state, effective grants and deployed code revision; do not
   bypass backend permissions or hardcode Owner names in the frontend.
4. Verify the browser loads the matching new frontend assets, then confirm one Daily Update
   sidebar entry, five Owner tabs, restricted Employee tabs, tab refresh/back behavior and
   actual authorized records. Retest the existing five data workflows against the real
   isolated database. Inspect unauthorized API/import/export attempts independently of UI.
5. Resolve the existing repository-wide typing failures and complete the real-environment
   acceptance checks required by the release owner before asserting full production readiness.
   No production migration, deployment or service restart was performed here.

**Verdict: local navigation/integration fix implemented and tested; ready for owner review
and isolated-environment deployment verification. Production readiness is not yet verified.**
