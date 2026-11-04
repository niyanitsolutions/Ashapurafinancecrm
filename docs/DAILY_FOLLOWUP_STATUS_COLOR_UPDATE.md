# Daily Follow-up Status color update

Implemented on 2026-11-04 for the existing single-company-per-database architecture, as confirmed by the user. This supersedes the active Customer Interest Status feature described in the earlier report.

## Delivered behavior

Customer Interest Status is removed from Add/Edit, the table, filters, exports, client state, API inputs and management endpoints. Old option configuration, stored record fields, historical events and audit entries remain in MongoDB without deletion or rewriting. Active API serialization hides the retired fields, including within returned history. The old endpoints have no registered handlers; request rejection may be 405/422 through the existing generic route rather than 404. Matching frontend/backend release is required; old clients submitting the removed field receive validation errors.

Follow-up Status now has company-wide configuration stored in MongoDB. Authorized employees and owners can add custom statuses, edit their names/colors/order, archive them with confirmation and restore them. The management UI supports a color picker, eight palette presets, six-digit HEX input, live preview, search and clear conflict/error feedback. New statuses select immediately; mutation locks prevent double submission. Configuration is refreshed on focus, management opening, cache invalidation and every five seconds on the active follow-up page.

The four default names are retained exactly: FOLLOW UP PENDING, NEXT FOLLOW UP, DISBURSE and REJECTED WITH REASON. Their colors and display order can be changed, but renaming/archiving them is blocked both in the UI and backend to preserve their business rules. Default palette suggestions are seeded once into the database: #FFF0C2, #DCEBFF, #D9F5E3 and #FFE0E0 respectively. The table has no separate hardcoded status-color mapping.

Every follow-up table row uses its effective status's configured color, including historical and archived custom statuses. All cells, including sticky actions, inherit the row background. Black/white foreground uses the WCAG relative-luminance calculation to select readable contrast. Hover brightness and focus outlines preserve identification; Edit, History and owner Delete remain visible. Missing legacy configuration uses the table's neutral styling rather than inventing a color.

Default due-date projection, automatic reconciliation, required next action, verified-loan DISBURSE validation and rejection reasons are preserved. Custom statuses are descriptive statuses with an optional follow-up date; they are not automatically converted into the two built-in date statuses and do not trigger loan/disbursement actions. No loan, invoice, authentication, session or RBAC-foundation files changed.

## Historical safety and configuration identity

Default `value` identifiers remain their exact existing status strings. New custom values use immutable `custom:<ObjectId>` identifiers. `name` is editable independently. The follow-up `status` stores the value; an optional server-owned `status_label` preserves the chosen custom label. The public `status_display` is the saved label or existing built-in status string. Renaming a configuration never rewrites records or historical events. Existing records retain their original label while recoloring follows the centrally configured value. New selections use the current name. Switching to a different status records the existing before/after history and clears stale custom labels when returning to a default.

Archived custom statuses remain in management/filter configuration and color lookup, but are excluded from new selections. Only an existing record retaining the same value can save an archived status. Unknown legacy strings can similarly be retained on their existing record, but cannot be newly assigned. CSV import preview and commit validate selected status values using the same service. CSV/Excel reports show saved human-readable labels; imports continue using the existing supported template and canonical status values. Report exports are not an import template.

## API and database

All paths are under `/api/v1/daily-operations`:

| Method | Endpoint | Request |
| --- | --- | --- |
| GET | `/follow-up-status-options` | Active by default; `include_archived=true` includes retained colors/options |
| POST | `/follow-up-status-options` | `name`, `color`, `display_order` |
| PATCH | `/follow-up-status-options/{id}` | `name`, optional color/order and required current `version` |
| POST | `/follow-up-status-options/{id}/archive` | `version` |
| POST | `/follow-up-status-options/{id}/restore` | `version` |

The existing Follow-up create/update API accepts `status` as a dynamic value, and the existing status filter remains in place. No second status-management API is maintained. The obsolete interest-option implementation was refactored/renamed rather than duplicated.

New collection `daily_followup_status_options` stores ID, immutable value, company_id, normalized_name, name, color, is_system, is_active, display_order, version, creator/updater identities and timestamps, and deleted_at. Indexes are active-only unique `(company_id, normalized_name)`, unique `(company_id, value)` and `(company_id, is_active, name)` for lookup. NFKC/casefold/collapsed-space duplicate normalization is retained. HEX validation only accepts `#RRGGBB`; no CSS fragments are accepted. Compare-and-update on company/ID/version prevents lost updates. Custom removal is archival, with no physical delete endpoint. Restore conflicts with an existing active name return 409.

Existing `daily_interest_options`, its indexes, retired follow-up fields and audit history are deliberately retained. No data conversion from interest options into follow-up statuses is performed; these are different business concepts. The new optional label has no backfill. The existing daily catalog installer seeds the four default status documents with deterministic IDs and `$setOnInsert`, preserving recolors/order and custom data across restart. No manual destructive migration is needed.

## Permissions and company scope

The existing authenticated database remains the company boundary. `company_id=default` is the existing company-settings singleton key, supplied by the backend. No client company, actor or system-status flag is accepted. This does not introduce shared-database multi-tenancy; separate company deployments require separate databases/authentication contexts, consistent with decision 001 and the user's earlier clarification.

Options require authenticated owner/active employee plus Follow-up View. Management also requires existing Follow-up Create or Edit (the current default employee policy supplies these). View-only UI hides management and backend checks remain authoritative. Inactive/profileless employees, customers and partners cannot manage options. Record assignment checks remain unchanged. Audit events `followup_status_option_created/updated/archived/restored` reuse the existing append-only writer, with company, option, actor, before/after and server timestamp. Seed rows identify Initial setup. As with the existing writer, an audit write is separate from the option commit; a rare audit failure requires refresh/review before retry.

## Changed files

Backend:

- Refactored `interest_options.py` into `backend/app/features/daily_operations/status_options.py`.
- `router.py`: status APIs replace interest APIs; retired filter/export removed; display labels exported.
- `schemas.py`: removed interest input, dynamic bounded status string with original default-specific validation.
- `service.py`: shared status validation/snapshot, retired data hidden, new initializer replaces interest initializer.
- `transfers.py`: status validation during import preview and removal of obsolete interest preservation logic.

Frontend:

- Refactored `CustomerInterestField.tsx` into `FollowUpStatusField.tsx` for selection, management, palette and live preview.
- Refactored `interestOptions.ts` into `statusOptions.ts` for the shared API/cache and contrast/row-style helpers.
- `RecordForm.tsx`: interest removed, existing status field uses shared configuration, default-dependent dates retained.
- `DailyOperationsPage.tsx`: removed interest column/filter, dynamic full-row styles, status configuration filters and readable historical status labels.
- Updated `DailyOperations.test.tsx`, `SimpleEntry.test.tsx`; replaced interest component tests with `FollowUpStatusField.test.tsx`.

Regression/browser infrastructure:

- Replaced the three `test_daily_interest_*` files with `test_daily_status_options.py`, `test_daily_status_mongo.py`, `test_daily_status_browser.py`.
- Refactored `scripts/daily-interest-ui-check.mjs` into `scripts/daily-status-ui-check.mjs`.
- Added this report and evidence under `docs/screenshots/daily-followup-status-2026-11-04/`.

Prior reports/screenshots remain as historical implementation evidence. No dependency, environment, global routing, authentication, invoice or unrelated module files changed.

## Validation

Executed results:

- **106 backend/API/regression/local-MongoDB tests passed** in 148.27 seconds (108 existing MongoMock datetime deprecation warnings).
- **45 frontend tests passed** across four Daily Operations files.
- **1 real-backend browser test passed**, executing both 1440px desktop and 390px mobile journeys. Both evidence results are PASS.
- Production build including TypeScript compilation passed (420 modules); the existing >500 kB bundle-size warning remains.
- Focused ESLint passed with zero errors/warnings after shared color helpers were moved into the API/cache module. Ruff and formatting checks passed.
- Strict mypy for the new status-options module passed. Checking the whole Daily Operations package reports six existing errors in five unchanged imported dependency files (customer field validation/service, auth service, loan-management service and leads service); no new Daily Operations errors were reported.

 The real-browser check uses two separate employee contexts, API-authenticated test sessions, actual FastAPI endpoints, and actual loopback MongoDB in a random disposable database. Desktop 1440px and mobile 390px verify removal of interest UI, shared configuration, creation/autoselection, full-row configured colors, dark contrast, rename/archive/history, immediate colors after status changes, default name protection, preview, refresh persistence and no mobile page overflow. It does not claim production acceptance or a login-form journey. Real MongoDB tests verify concurrent duplicate creation, recolor persistence across repeated initialization and separate-database isolation. Defensive company predicates reject foreign-tagged local options.

Reproduction from repository root (PowerShell):

```powershell
$env:DEBUG='false'
$env:AFS_INVOICE_TEST_MONGO_URI='mongodb://127.0.0.1:27017/'
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_daily_status_options.py tests/api/test_daily_status_mongo.py tests/api/test_daily_simple_entry.py tests/api/test_daily_operations.py tests/api/test_daily_automation_hardening.py tests/api/test_daily_update_navigation.py -q
npm --prefix frontend test -- src/features/daily_operations
npm --prefix frontend run build
# Separate terminal for browser checks:
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5175 --strictPort
$env:AFS_DAILY_BROWSER_CHECK='1'
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_daily_status_browser.py -q -s
```

The MongoDB fixture only allows loopback addresses and creates/removes random test namespaces; it never uses the application production database. Cached Node 22, Playwright and Chrome are reused without installing dependencies. Production data inspection, migration, deployment and full unrelated CRM regression were not performed.

## Release/migration and rollback instructions (not executed)

Release matching backend/frontend after staging verification and a target backup. Inspect any pre-existing `daily_followup_status_options` documents/index definitions for name/value conflicts in the approved target. Production data was not inspected during development. Run the existing `scripts/migrate_daily_operations.py` against the explicitly selected staging/production environment only after target approval; it now installs the additive status indexes/defaults. Existing application startup also calls the daily catalog initializer. No follow-up rewrite or interest-data deletion is performed.

Using the existing Linux release procedure, from the approved repository root:

```sh
cd backend
.venv/bin/python ../scripts/migrate_daily_operations.py
cd ../frontend
npm ci
npm run build
sudo systemctl restart afs-crm-backend afs-crm-arq-worker
sudo systemctl status afs-crm-backend afs-crm-arq-worker --no-pager
```

Publish frontend artifacts with the deployment's existing process. Verify two employees see the same options/colors, archived records edit safely, default status rules still work, and exports/search/assignment/history work in staging before production rollout.

Rollback requires a compatibility backend that can read dynamic status strings and preserve their labels. An older binary limited to the original four literals cannot safely read custom-status records. Prefer a forward fix or compatibility release; do not blindly roll back an old executable or rewrite statuses to force it to start. Retain status configuration, interest configuration, fields, indexes, historical snapshots and audit events. Do not restore a database backup over newer operational work just to undo color configuration. New configuration changes persist independently of a code rollback.

Known limits: company separation is by database, not shared-database tenant membership. Cross-session visibility uses bounded five-second active-page polling/focus refresh. Existing custom statuses are descriptive only, with no new automation semantics. Unknown legacy statuses with no configuration retain neutral row styling. There is no PDF export in the current module. Older clients posting the removed interest input must be updated. Full repository-wide regression/type-check cleanliness and production acceptance are not claimed.
