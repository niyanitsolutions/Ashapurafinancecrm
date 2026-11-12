# Daily Follow-up: multiple banks and independent DISBURSE

Implemented on 2026-11-12 in Daily Update / Daily Follow-up Data. Scope remains the existing single-company database, as previously confirmed by the user. No production data inspection, migration or deployment was performed.

## Summary

Add and Edit use the same searchable Bank / NBFC multi-select. It supports multiple choices, removable chips, duplicate prevention, native checkbox keyboard interaction, search/empty/loading/failure states, custom option creation, rename, archive confirmation and restore. A new custom bank is saved centrally and selected immediately. The list refreshes on opening/focus and every five seconds while the form is mounted. Option mutations are locked against duplicate submissions.

A follow-up stores `banks: [{option_id, name}, ...]` as server-validated option references and historical name snapshots, with up to 30 banks. Active selections require valid same-company IDs. Removed/renamed options do not rewrite saved names; an existing record can retain its archived bank, but that bank cannot be newly assigned. Duplicate IDs or equivalent normalized names are rejected. At least one bank is required. Bank names use NFKC, whitespace/casefold normalization, reject control characters, and are limited to 200 characters.

The existing scalar `bank` remains as a compatibility/report string containing all selected names. The table shows wrapped text capped to two lines, with the full list in its tooltip; history formats bank arrays as names. Bank filtering matches any saved selection (or a legacy scalar). Search, sort and CSV/Excel exports retain all names. Bank breakdowns count each selection separately; a multi-bank record can therefore contribute to multiple bank groups. Reports retain historical name snapshots.

DISBURSE is now an independent employee follow-up label. Neither Add nor Edit shows Verified disbursed loan or the optional CRM-link chooser. The Follow-up form and page request employee-only lookups (`include_crm=false`), so they do not fetch verified loans or customer/lead choices. No loan reference or verified-disbursement check is required. Existing configured DISBURSE colors continue to apply. The two built-in date statuses, custom status management/colors, rejection reasons, remarks, dates and assignment remain functional.

Follow-up validation no longer checks customer identity against Leads/Customers, infers a lead from a mobile number, derives customer data from CRM, or requires a loan. New non-null lead/case links are rejected. New records store null lead/case references. Save/edit only writes the daily record and its existing history, plus option/audit records when explicitly managing options. Tests confirm no writes to Leads, Customers, Applications, workflows, status history or financial counters.

Existing historical references are retained without migration/unlinking. Their live lead/case ownership checks remain for authorization and reassignment safety; historical reads/lists may consult those references for scope. They do not populate new follow-up choices or cause new linking. Legacy edits preserve the reference metadata while customer/bank content remains the saved daily snapshot. This is a backward-compatibility authorization path, not an automatic linking feature.

Loan Progress Tracking keeps its existing CRM lookups via `include_crm=true`, annotation editing, actual financial totals and loan visibility rules. Its standard imports still create progress annotations rather than follow-ups. The older legacy action-import path that would create loan-linked follow-up records now fails with an actionable independent-entry message. No independent Leads or Loan Management implementation was modified.

## Files

New backend files:

- `backend/app/features/daily_operations/bank_options.py`: bank schemas, shared option service specialization, selection validation, legacy projection and indexes.
- `backend/app/features/daily_operations/bank_migration.py`: additive, retry-safe conversion.
- `scripts/migrate_daily_followup_banks.py`: dry-run-first migration command.

Modified backend files, all inside Daily Operations:

- `status_options.py`: reusable collection/audit attributes so banks share existing permissions, duplicate handling, optimistic edits and audit implementation; status behavior remains intact.
- `schemas.py`: optional bank array plus legacy scalar support, removed loan requirement for DISBURSE.
- `service.py`: independent saves, bank snapshot validation/projection, compatible historical authorization, multi-bank filtering/breakdowns and index setup.
- `entries.py`: employee-only lookups by default; optional CRM lookups retained for Progress.
- `router.py`: bank APIs and lookup parameter.
- `transfers.py`: bank validation at preview/commit, removal of new-link import dependency.

New frontend files:

- `frontend/src/features/daily_operations/BankMultiSelect.tsx`.
- `frontend/src/features/daily_operations/bankOptions.ts`.
- `frontend/src/features/daily_operations/BankMultiSelect.test.tsx`.

Modified frontend files:

- `RecordForm.tsx`: shared bank control, independent DISBURSE, removed Follow-up CRM linking; preserves Progress form behavior.
- `DailyOperationsPage.tsx`: all bank names, bounded display/tooltip, history formatting, area-specific employee lookup cache.
- `api.ts`: explicit `include_crm` query parameter.
- `SimpleEntry.test.tsx` and `FollowUpStatusField.test.tsx`: existing form regression fixtures use the new selector.

Tests/evidence:

- New `tests/api/test_daily_multi_bank.py`, `test_daily_bank_mongo.py`, `test_daily_bank_browser.py`.
- Updated relevant tests in `test_daily_operations.py`, `test_daily_simple_entry.py`, `test_daily_status_options.py` for the expressly changed independent behavior. Legacy ownership/reassignment tests seed historical links explicitly; new creation cannot create those links.
- New `scripts/daily-banks-ui-check.mjs`; existing status/simple-entry browser scripts updated to select banks through the shared control.
- New evidence under `docs/screenshots/daily-multi-bank-2026-11-12/` and `docs/screenshots/daily-simple-entry-2026-11-12/`.

No authentication, session, RBAC foundation, invoice, global routing, dependency or environment files changed. Earlier evidence files are retained as historical artifacts.

## API and database

New API endpoints under `/api/v1/daily-operations`:

| Method | Route | Input |
| --- | --- | --- |
| GET | `/bank-options` | Active options; `include_archived=true` includes history/management entries |
| POST | `/bank-options` | `{name}` |
| PATCH | `/bank-options/{id}` | `{name, version}` |
| POST | `/bank-options/{id}/archive` | `{version}` |
| POST | `/bank-options/{id}/restore` | `{version}` |

Follow-up POST/PATCH accept `banks`, for example:

```json
{"banks":[{"option_id":"aaaaaaaaaaaaaaaaaaaaaaaa"},{"option_id":"bbbbbbbbbbbbbbbbbbbbbbbb"}]}
```

All other required follow-up fields remain required. New selection labels are loaded by the server, not accepted as authoritative client snapshots. An existing choice retains its saved snapshot. A no-ID snapshot can only be retained from the current record; it cannot be invented through the new array API. Legacy clients/CSV templates may still submit a scalar `bank`; the server stores it as a one-element snapshot array. Such compatibility entries do not automatically create bank options; they remain readable and can be edited, or an authorized user can add a shared option explicitly. CSV/Excel report exports include every selected name; the legacy import template remains a single-bank string interface, not a multi-bank report round-trip format.

New collection: `daily_followup_bank_options`, using the same server company singleton, normalization, version checks, soft archive, creator/updater metadata and shared audit conventions as Follow-up Status. IDs are stable across renames. No hard delete endpoint exists. Duplicate active names are prevented by a partial unique `(company_id, normalized_name)` index. A `(company_id, is_active, name)` index supports lookups. New follow-up indexes cover `(banks.option_id, date DESC)` and `(banks.name, date DESC)`. Existing indexes remain in place.

The shared option implementation internally retains its stable `value` metadata, but bank records reference the option ID rather than the status identifier. Bank options do not carry status color/order behavior.

## Permissions and isolation

Owners and active employees use the existing Daily Follow-up View permission to list options. Management additionally requires existing Create or Edit permission, as in the current custom-status workflow. No new role or owner approval is introduced. All endpoints use existing active-user authentication; server-side checks reject inactive/profileless employees and non-staff roles. Existing daily record assignment and owner-only Delete remain enforced.

The approved database is the company boundary. The backend supplies company_id=`default`, corresponding to the existing company-settings singleton; client-supplied company/actor fields are rejected. The system does not support multiple authenticated tenants sharing one database. Defensive company predicates reject foreign-tagged options, and a real MongoDB check proves an option ID from another database cannot be selected. This preserves the existing single-company architecture without claiming a tenant resolver that the CRM does not have.

Bank option actions use the shared append-only audit writer with the `followup_bank_option_created/updated/archived/restored` event prefix, actor and before/after metadata. Follow-up changes retain existing per-record history. Audit writes follow the existing separate-write convention; a rare audit failure after commit requires refresh/review before retrying.

## Legacy conversion and migration results

Read-time projection wraps a legacy single `bank` string as one selection without touching storage. A comma in a historical bank string is preserved literally; the conversion never guesses that it represents multiple banks. This allows existing records to load/edit even before physical conversion.

The explicit migration defaults to dry-run. Apply scans only follow-up rows missing/null `banks`, resolves/creates a deterministic shared option for the historical name, and adds one `{option_id, name}` selection. Original scalar bank values, history, version, dates, assignments, customer data, loan type, status and references remain unchanged. Existing archived bank options are not reactivated. A compare-and-update on original ID/version/bank/missing array prevents overwriting a concurrent edit; conflicts are counted for review/retry. Reruns skip completed arrays. A summary is written to the existing audit log when rows are converted.

Real local MongoDB migration checks: two synthetic legacy records were eligible; dry-run converted zero and left both documents exactly unchanged; apply converted two using one deduplicated bank option; a second apply converted zero. Every original field/history entry remained identical and the original string, including whitespace/comma, was retained. Unit/API coverage also verifies legacy read-through and successful save after migration. No production migration or real customer data was inspected or changed, so no production conversion count is claimed.

Empty/non-string historical bank values are counted and left untouched for review. Concurrent conflicts are reported without guessing or deleting data. Take a target backup and inspect dry-run results before approving apply.

## Executed validation

- **263 backend/API/regression/real-MongoDB tests passed**, including Daily Operations, status management, attendance automation/navigation, multi-bank selection, migration/concurrency, Leads, Loan Management visibility/redesign and the workflow pipeline. The final combined run used two test workers and completed in 237.91 seconds. Existing MongoMock datetime deprecation warnings remain; pytest also reported a Windows temporary-directory cleanup permission warning after tests passed.
- **55 frontend tests passed** across five Daily Operations files, covering multi-select/search/chips, custom management, archived snapshots, Add/Edit independent DISBURSE, existing status colors, table/export availability, navigation and existing operations.
- **Two actual-backend browser tests passed**, each at 1440px and 390px. The bank journey covers three selections, remove/reselect, sharing across employee sessions, rename/archive, historical retention, editing, DISBURSE with no loan, configured row color, History, search/filter/CSV download, owner/employee actions, refresh and mobile overflow. The existing status-color journey also passed after integration.
- The existing synthetic simple-entry browser script passed **four owner/employee desktop/mobile scenarios**, preserving progress annotation and other daily workflows.
- Frontend production build/TypeScript and focused Daily Operations ESLint passed; the existing large-bundle warning remains. New bank option/migration modules pass strict mypy. Checking the whole Daily Operations package reports the existing six errors in five unchanged imported dependency files (customer field validation/service, auth service, loan-management service and leads service), with no new Daily Operations errors.
- Ruff and changed Python formatting checks passed.

Browser users are synthetic, pre-authenticated API-test sessions in separate contexts, and the backend runs against a random disposable loopback MongoDB namespace. Login-form acceptance, production testing, all unrelated CRM modules and repository-wide static cleanliness are not claimed. No dependencies were installed.

Reproduce from repository root (PowerShell):

```powershell
$env:DEBUG='false'
$env:AFS_INVOICE_TEST_MONGO_URI='mongodb://127.0.0.1:27017/'
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_daily_operations.py tests/api/test_daily_simple_entry.py tests/api/test_daily_status_options.py tests/api/test_daily_status_mongo.py tests/api/test_daily_automation_hardening.py tests/api/test_daily_update_navigation.py tests/api/test_daily_multi_bank.py tests/api/test_daily_bank_mongo.py tests/api/test_leads.py tests/api/test_loan_management_visibility.py tests/api/test_loan_management_redesign.py tests/api/test_workflow.py -q -n 2 --tb=short
npm --prefix frontend test -- src/features/daily_operations
npm --prefix frontend run build
# Separate terminal for browser checks:
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5175 --strictPort
$env:AFS_DAILY_BROWSER_CHECK='1'
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_daily_bank_browser.py tests/api/test_daily_status_browser.py -q -s
frontend/node_modules/.cache/voice-node22/node.exe scripts/daily-simple-entry-ui-check.mjs
```

## Release and rollback instructions (provided only)

Release matching backend/frontend to staging first, using the existing static-artifact and systemd release process. New bank indexes are installed by the existing daily catalog initialization; no follow-up backfill runs automatically at startup. Bank options are Daily-only and do not replace a Loan Management field or schema.

After selecting the explicitly approved target environment/configuration and taking a backup, from its backend directory:

```sh
.venv/bin/python ../scripts/migrate_daily_followup_banks.py
# Inspect eligible/empty/conflicts. Run only after explicit target approval:
.venv/bin/python ../scripts/migrate_daily_followup_banks.py --apply
```

Dry-run performs no database writes. Apply installs the bank indexes then performs additive conversion. Inspect conflicts/empty values and rerun safely after review. Verify two employee sessions, archived banks, independent DISBURSE, CSV/Excel names and historical authorization in staging before production release.

Rollback must retain arrays, scalar compatibility values, option documents and all history/audit entries. The original bank string is preserved by migration, but after users make new multi-bank edits it intentionally represents all current selections. Older binaries require a loan for DISBURSE and may reject long joined bank strings or independent records. Use a forward fix or compatibility backend/frontend release; do not blindly restore an older binary, clear the bank arrays, invent loan links or overwrite the database from an old backup. The additive migration needs no destructive rollback to preserve data.

Known limitations: company isolation remains by database, not a shared-database membership model. Cross-device option visibility uses bounded polling/focus refresh. Old CSV imports support one literal bank name; multi-bank report exports are not an import template. Records with invalid/empty historical banks need operator review rather than invented names. Legacy links remain only for historical metadata and existing authorization, not new linking. Production rollout/migration and fresh-login UI acceptance remain unperformed.
