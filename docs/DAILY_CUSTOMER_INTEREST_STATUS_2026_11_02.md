# Customer Interest Status implementation

Implemented for the existing single-company database scope, explicitly confirmed by the user on 2026-11-02. No shared-database multi-tenancy, company switching, authentication or RBAC redesign is introduced.

## Behavior

Daily Follow-up Add and Edit share the new optional searchable Customer Interest Status field, below Follow-up Status and before More Details. The dropdown supports search, clear, Add Custom Option, Manage Options, rename, removal confirmation and restore. Management lists creator, creation date and update date. Newly created options are selected immediately. Loading, empty, duplicate/conflict, failure and success states are handled; mutation locks prevent double submission. Existing Follow-up Status, rejection reasons, employee assignment and loan linkage validation remain independent.

Options come from MongoDB. The ten suggested names are initial seed data, never a permanent frontend list. The existing startup catalog installer creates indexes and inserts missing deterministic seed IDs using set-on-insert; subsequent startup never resets renamed/archived seed documents. An existing custom active name is preserved. No follow-up backfill, deletion or rewrite runs.

The active Daily Follow-up page refreshes the shared React Query cache every five seconds while visible. Dropdown opening, window focus and Refresh options also refresh it; successful management invalidates it immediately in the current session. This is bounded polling, not a websocket push guarantee. Options persist across browsers, devices and logout/login. Options are fetched once per shared query, never for each record row.

Records store the server-validated option ID and a label snapshot. Reusing that ID retains the original snapshot even after rename/archive. Selecting a different active option captures its current label. Clearing is explicit. An archived option cannot be selected on a new record, but an existing record can retain its saved value. Old clients and existing CSV updates that omit the new field retain existing values. Clients cannot submit the snapshot or server actor/company fields.

The list includes a snapshot column, the More filters interface supports active and archived option IDs, and CSV/Excel exports include CUSTOMER INTEREST STATUS from the saved snapshot. The existing module has no PDF export. CSV imports retain their existing supported column contract; this release does not add name-based option creation or selection through CSV imports. Exported report columns are not an import template; use the existing template for import.

## Scope, permissions and persistence

The authenticated deployment database is the company boundary (decision 001). `company_id=default` refers to the existing company-settings singleton key inside that database. No frontend-provided company selector is accepted. This is not an authenticated multi-company resolver or permission to host multiple companies in the same database. Separate deployments require separate databases and authentication contexts. A database-isolation test verifies options from another database cannot be resolved or modified; defensive company predicates also reject foreign-tagged option documents in the local database.

All endpoints require the existing active-user authentication. Owners and active employees with Follow-up View can list. Management additionally requires Follow-up Create or Edit (existing default employee policy already grants these). Customers, partners, inactive/profileless employees are rejected. No owner approval is needed and no new permission/grant is installed. Existing record-assignment restrictions remain enforced by DailyOperationsService.

New collection: `daily_interest_options` with `_id`, company_id, name, normalized_name, is_active, version, created_by, created_by_name, created_at, updated_by, updated_at and deleted_at. Names are required, whitespace-normalized and limited to 60 visible characters. Duplicate comparison uses Unicode NFKC, collapsed whitespace and casefold.

Indexes:

- Unique `(company_id, normalized_name)` with partial filter `is_active=true` prevents concurrent active duplicates.
- `(company_id, is_active, name)` supports shared option queries.
- `daily_follow_ups(customer_interest_option_id, date DESC)` supports record filters.

Follow-ups gain optional `customer_interest_option_id` and server-owned `customer_interest_status_snapshot`, with no old-record backfill. Option renames/archive/restore use atomic ID/company/version compare-and-update; stale requests return 409. Option creation catches MongoDB duplicate-key conflicts. Archived documents are retained. All normal management actions write the existing append-only audit log with company, option, actor, before/after and server timestamp. Follow-up changes remain in existing record history.

## API

All paths below are under `/api/v1/daily-operations`:

| Method | Path | Body / behavior |
| --- | --- | --- |
| GET | `/interest-options` | Active options; `include_archived=true` includes retained options |
| POST | `/interest-options` | `{name}` |
| PATCH | `/interest-options/{id}` | `{name, version}` |
| POST | `/interest-options/{id}/archive` | `{version}` |
| POST | `/interest-options/{id}/restore` | `{version}`; duplicate active names return 409 |

Existing Follow-up POST/PATCH accept optional `customer_interest_option_id`. Existing list/export filters accept that ID. Responses keep the existing ApiResponse envelope. Snapshot and company/actor spoofing are rejected as unsupported request fields.

## Files

Created:

- `backend/app/features/daily_operations/interest_options.py`: option storage, validation, initialization, audit and snapshot rules.
- `frontend/src/features/daily_operations/interestOptions.ts`: API and shared cache hook.
- `frontend/src/features/daily_operations/CustomerInterestField.tsx`: searchable selector and inline management with shared removal confirmation.
- `frontend/src/features/daily_operations/CustomerInterestField.test.tsx`: component/form coverage.
- `tests/api/test_daily_interest_options.py`: API, sharing, permissions, history, filters, exports and compatibility.
- `tests/api/test_daily_interest_mongo.py`: actual MongoDB uniqueness, restart and database isolation.
- `tests/api/test_daily_interest_browser.py` and `scripts/daily-interest-ui-check.mjs`: actual local API/MongoDB two-session browser checks.
- This report and `docs/screenshots/daily-interest-2026-11-02/` evidence.

Modified only Daily Operations feature files: backend router/schemas/service/transfers; frontend RecordForm, DailyOperationsPage and two existing test mocks. No dependency, authentication, permission-engine, invoice, global routing or unrelated CRM module changes.

## Verification

Final run: **91 backend/API/integration tests passed** in 113.64 seconds, including the new API cases, existing Daily Operations/simple-entry/automation regression, real MongoDB concurrency/database isolation and the real-backend browser journey. **44 frontend tests passed** across four Daily Operations test files. Both desktop/mobile browser journeys passed (1440px and 390px). Existing MongoMock datetime deprecation warnings remain.

Production frontend build (including TypeScript compilation), changed-file ESLint, Ruff and formatting checks passed. The new interest-options module passes strict mypy. Checking the entire Daily Operations package follows imports into unchanged dependencies and reports **six errors in five unchanged files** (customer field validation/service, auth service, loan-management service and leads service); no new Daily Operations typing errors were reported. The existing frontend bundle-size warning remains. Full repository-wide static/regression success is not claimed. Browser tests use synthetic employees authenticated through API-test sessions in separate browser contexts; they do not claim production logins or a fresh login-form journey. The browser calls the actual FastAPI routes and actual loopback MongoDB in a random disposable namespace. Desktop 1440px and mobile 390px exercise two-employee sharing, creation/autoselection, save, refresh, editing, rename, confirmation/archive, retained historical display and exclusion from new selections. Database isolation is checked by a separate real MongoDB test, not by inventing a frontend tenant switch.

Reproduction from repository root (PowerShell):

```powershell
$env:DEBUG='false'
$env:AFS_INVOICE_TEST_MONGO_URI='mongodb://127.0.0.1:27017/'
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_daily_interest_options.py tests/api/test_daily_simple_entry.py tests/api/test_daily_operations.py tests/api/test_daily_automation_hardening.py tests/api/test_daily_interest_mongo.py -q
npm --prefix frontend test -- src/features/daily_operations
npm --prefix frontend run build
# Start Vite in a separate terminal:
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5175 --strictPort
# Browser test creates its own isolated backend on localhost:18765:
$env:AFS_DAILY_BROWSER_CHECK='1'
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_daily_interest_browser.py -q -s
```

The loopback MongoDB fixture is reused from the existing invoice integration test infrastructure and only creates/removes random `afs_invoice_test_*` databases. Production configuration/data is never used by these integration checks. Browser tooling uses the repository's existing cached Node 22, Playwright and local Chrome; no dependencies were installed.

## Migration and release (instructions only; not executed in production)

1. Back up the target database and deploy to staging first. Inspect any existing `daily_interest_options` collection for active normalized-name conflicts or incompatible index definitions before release. No production data inspection was performed here.
2. Release matching backend and frontend artifacts. New API routes must be available before exposing management controls. Use the existing daily-operations catalog migration; it now installs the additive option indexes and initial suggestions. No follow-up backfill or separate new migration script is needed.
3. On the approved Linux target, from its repository root:

```sh
cd backend
.venv/bin/python ../scripts/migrate_daily_operations.py
cd ../frontend
npm ci
npm run build
sudo systemctl restart afs-crm-backend afs-crm-arq-worker
sudo systemctl status afs-crm-backend afs-crm-arq-worker --no-pager
```

The existing backend startup also installs the daily catalog/indexes. Run these commands only against the explicitly approved target configuration, with the existing static-artifact publication process. Verify both employees can see changes and old records/export filters still work in staging before production release. No production migration or deployment was run.

Rollback: roll back frontend and backend together through the existing release process. Retain all new option documents, optional follow-up fields, history/audit entries and indexes. Previous binaries can ignore the additive stored fields; do not delete them to force rollback. Old clients do not support the field; a forward compatibility release is preferable if those clients will continue editing records. Do not restore an older database backup over new operational work merely to remove this feature. Rolling back does not undo already saved names/archives/history.

Known limits: the CRM is still single-company per database; no shared-database tenant certification is claimed. Cross-device visibility is bounded by five-second active-page polling, focus/open or explicit refresh. Full unrelated CRM regression and production acceptance are not claimed. Audit logging uses the existing shared writer after option commit; as elsewhere in the application, this is not a cross-collection transaction. A rare audit-write failure can leave the option saved while the request fails; refresh and review before retrying.
