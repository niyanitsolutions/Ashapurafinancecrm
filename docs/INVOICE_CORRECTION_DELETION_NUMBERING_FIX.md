# Invoice correction, deletion and numbering fix

This report supersedes the earlier invoice enhancement report where numbering and correction lifetime rules differ. Work is limited to invoice management and its validation. No production deployment, production migration or production invoice modification was performed.

## 1. Root causes

- Reopening a correction with a fresh request key attempted a new creation, then hit the lifetime `replacement_for` unique index. There was no source-based resume endpoint or resume UI.
- The inspected `PUT /invoices/{id}` already updated an existing document; it did not create one. The reported repeated-save duplication was not reproducible through that PUT path. The editor nevertheless exited after each save, and correction identity/resume behavior lacked explicit tests. Saves now stay in the correction editor, retain its ID/number, and advance the server version.
- Draft deletion permanently retained every number under the full unique index. The counter had no persisted reusable-tail claim.
- Issued/cancelled invoices had cancellation but no archive operation or archive list filter.
- The lifetime correction index also prevented a new active workflow after an abandoned correction draft was deleted.

## 2. Architecture inspected

React/TypeScript invoice list, form, view, workflow modals, API client, settings and routing; FastAPI invoice routes, schemas and services; MongoDB models/index registration and shared atomic counter; decimal GST calculations; PDF generation and immutable company/image snapshots; existing owner/employee permission and record-assignment scope; shared audit logs; invoice tests and the previous enhancement report. Global authentication, routing, navigation, styling, tenancy and other CRM modules are unchanged.

## 3. Exact existing files changed

| File | Purpose |
|---|---|
| `backend/app/features/invoices/models.py` | Optional archive/deletion metadata and reuse provenance |
| `backend/app/features/invoices/schemas.py` | Validated archive input and deletion reason |
| `backend/app/features/invoices/repository.py` | Preflight and replacement active-record indexes; startup never drops old indexes |
| `backend/app/features/invoices/service.py` | Resume/create correction, stable updates, archive, safe deletion/reuse, protected writes and history |
| `backend/app/features/invoices/router.py` | Correction lookup, delete eligibility, archive API and archived list filter |
| `frontend/src/features/invoices/api.ts` | Typed calls and response fields |
| `frontend/src/features/invoices/InvoiceWorkflow.tsx` | Resume/create states, eligibility-aware deletion, archive confirmation and history loading |
| `frontend/src/features/invoices/InvoiceFormPage.tsx` | Persistent correction saves, version updates, original status/reason and assigned identity |
| `frontend/src/features/invoices/InvoiceListPage.tsx` | Archive actions, archived filter, permissions and operation feedback |
| `frontend/src/features/invoices/InvoiceViewPage.tsx` | Archive action, read-only archive state, reuse provenance and feedback |
| `frontend/src/features/invoices/Invoices.test.tsx` | Resume, repeated save, archive and filter tests |
| `tests/api/test_invoices.py` | Correction, deletion, numbering, archive, security, concurrency and migration regressions |

## 4. Exact files added

- `backend/app/features/invoices/numbering.py`: invoice-only allocation and tail reuse using the existing `counters/INV` document.
- `scripts/migrate_invoice_number_reuse.py`: dry-run-first, explicitly targeted index migration and guarded rollback.
- `tests/api/test_invoice_mongo_integration.py`: opt-in real local MongoDB concurrency and migration tests.
- `scripts/invoice-workflows-ui-check.mjs`: desktop/mobile browser checks with isolated synthetic API fixtures.
- `docs/screenshots/invoice-workflow-fixes/correction-1440.png` and `correction-390.png`: synthetic browser evidence.
- `docs/screenshots/invoice-workflow-fixes/results.json`: browser check results.
- `docs/INVOICE_CORRECTION_DELETION_NUMBERING_FIX.md`: this report.

## 5. Schema changes

Optional invoice fields: `is_archived`, `archived_at`, `archived_by`, `archive_reason`, `deletion_reason`, `number_reused_from`. Existing `replacement_for`, `source_invoice_number`, `correction_reason`, version, deletion fields and embedded history are reused. `correction_resumed` and `source_status` are response context, not a new persisted workflow model.

The existing `counters/INV` document may contain one `reusable_invoice` candidate with sequence, prefix, tombstone ID and original number. No collection, framework, dependency or environment variable was added to application runtime. No backfill or historical financial rewrite is required.

## 6. MongoDB index changes

- New `invoice_number_reserved_unique`: unique `invoice_number` where `is_deleted=false`. Issued, cancelled and archived documents remain in this scope. Deleted draft tombstones retain their original numbers and IDs outside it.
- New `replacement_for_reserved_unique`: unique string `replacement_for` where `is_deleted=false`. This permits a new correction after an abandoned draft is deleted while retaining one nondeleted correction per source, including finalized/archived replacements.
- Existing request-key uniqueness remains unchanged.
- The reviewed migration removes legacy `invoice_number_1` and `replacement_for_1` only after their replacement guards exist. Startup adds guards but never drops existing indexes.

## 7. Migration requirements

The script defaults to inspection only and requires an explicit database name matching the configured target. It checks lifecycle metadata, protected soft-deleted records, duplicates in the target number/correction scopes, and known index definitions. It refuses conflicts without rewriting, merging or deleting invoice records. Unknown old guards keep reuse disabled rather than being silently dropped.

Run the migration with invoice writers stopped. It is idempotent, does not change counters or documents, and does not backfill historical tombstones into reusable candidates. Deletions completed before migration retain their prior reservation policy. No production migration was executed. Mock and real-Mongo migration tests use synthetic test databases only.

## 8. Correction behavior

Lookup is by original invoice ID, independently of browser request key. An existing active correction is resumed with its saved business fields and reason. Concurrent creation requests converge through the unique source index. Every Save Draft uses PUT against the same correction ID, recalculates through the existing calculator, preserves source links and assigned number, and updates its version. Stale/future-version writes fail clearly; unsaved form fields remain available.

A never-issued abandoned correction can be deleted; after the index migration, a new active correction can then be created without deleting its predecessor's tombstone. A finalized or archived replacement still reserves that source workflow and cannot be silently replaced by another independently effective invoice. Correct the finalized replacement through its own linked workflow if appropriate.

## 9. Draft deletion

Confirmation displays invoice, customer, status, optional deletion reason and a backend eligibility explanation. Eligibility is explicitly not a number reservation. Deletion is soft-only with actor, timestamp, reason and an atomic embedded event. Repeated deletion fails; ordinary get/list/PDF access excludes the tombstone. Existing invoice dependencies block deletion. The owner can read a deleted draft's history through the scoped history endpoint; ordinary employee reads remain blocked.

## 10. Issued/cancelled handling

Archive requires edit permission, current version and a nonblank reason. It only adds archive metadata; financial status, content, PDF inputs, number and accounting references remain intact. Active lists exclude archived records; the Archived invoices filter keeps them discoverable with read/download/print/history access. Archive also supports settled invoices without changing payment state. Archived records cannot change financial status. Archive is not legal cancellation, a credit note or statutory voiding.

## 11. Number reuse rules and concurrency

The counter never decreases. Deletion publishes a reusable candidate only if the never-issued draft is still at the counter's tail. Prefix, starting floor, lifecycle evidence and index readiness are checked. A conditional atomic counter operation consumes that candidate once, or allocates the next sequence and invalidates an older candidate. A durable claim is consumed even if insertion subsequently fails, so failure may create a gap but cannot give two requests the same claim. The unique index supplies the final active-record guard.

There is no scan or stack of old gaps. Issued/cancelled/archived/finalized numbers are not recycled. A later allocation, changed prefix or raised floor makes a stale tail unavailable. Existing company/prefix/global counter semantics remain unchanged; no tenant or financial-year numbering architecture was invented.

The form does not promise an unreserved pre-save number. It explains that the actual server allocation appears after Save Draft; the resulting invoice displays its assigned number and reuse provenance. This release does not add a separate pre-save number reservation UI. Eligibility and deletion notices therefore remain conditional until creation succeeds.

Claims persist across service/application restarts. A crash after deleting a draft but before publishing its claim conservatively retains a gap. Do not repair such gaps by decrementing the counter or scanning historical tombstones automatically.

## 12. Duplication

Ordinary duplication remains independent from correction. It copies supported business inputs, uses current dates, recalculates totals, creates a draft with an independently allocated number and records `duplicated_from`. It does not copy issue, cancellation, payment or replacement state. Stable request keys and submission locks protect accidental retries. Existing settled-invoice duplication restrictions remain in force.

## 13. Audit/history

Successful invoice updates append actor, server timestamp, status and reason in the same atomic write. Separate shared audit logging remains. Events distinguish correction creation, correction updates, correction finalization, duplication, archive, deletion and reuse. Reuse links new draft and tombstone by document ID so repeated historical draft numbers are not mistaken for the same record. Source history includes recorded related correction updates and finalization; missing historical events are not invented. Audit history has no ordinary update/delete endpoint.

## 14. Permissions and financial integrity

Every new endpoint reuses existing authenticated invoice permissions and owner/staff record scoping. Correction lookup/create requires both create and edit permission, matching its editable workflow. Deletion/archive requires edit; history requires view. Cross-assignment staff access is tested and blocked. This application explicitly defers tenant IDs; no claim of new multi-tenant isolation is made.

Issued content remains immutable. Replacement issue still requires the original to be cancelled through the existing supported process. Cancellation legal eligibility cannot be certified without the accounting/filing information this application lacks. Credit notes and automatic GST changes remain unsupported. Existing decimal/GST formulas, totals, currency formatting and PDF layout were not rewritten. No discount model was added where one does not already exist.

## 15. API changes

Base prefix remains `/api/v1`.

- `GET /invoices/{id}/correction`: active correction or null, with source access and create/edit checks.
- Existing `POST /invoices/{id}/replacement`: create-or-resume behavior, preserving old request shape.
- Existing `PUT /invoices/{id}`: stable correction update with current-version protection.
- `GET /invoices/{id}/delete-options`: provisional eligibility and explanation.
- Existing `DELETE /invoices/{id}`: optional reason; returns deletion outcome and conditional reuse information.
- `POST /invoices/{id}/archive`: version and mandatory reason.
- Existing `GET /invoices`: optional `archived` boolean, preserving other filters/sort/pagination.
- Existing history endpoint permits owner inspection of tombstone history and returns richer recorded relationships.

## 16. Frontend changes

Existing orange theme, layout, shared Modal, table and PDF preview remain. Corrections display original number/status/reason and new-versus-resumed state; saved versions remain in the same editor. Archive/deletion confirmations show effects and retain backend errors. List mutations refresh the current filters and show success feedback. Archive filtering is local to invoices. History loads when opened. Global components, routes and navigation were not modified.

## 17. Executed validation

Final results:

| Check | Result |
|---|---|
| Invoice API suite | 44 passed |
| Real local MongoDB integration suite | 3 passed |
| Combined final invoice/API/Mongo run | 47 passed |
| Access-control, system-settings and timezone backend regressions | 65 passed |
| Invoice frontend tests | 15 passed |
| Shared Modal and permission-hook frontend regressions | 4 passed |
| TypeScript typecheck | Passed |
| Invoice ESLint | Passed |
| Invoice/backend/migration/test Ruff | Passed |
| Frontend production build | Passed; existing large-bundle warning |
| Browser synthetic-fixture workflows | Passed at 1440px and 390px |
| Strict mypy on invoice package/imports | Not passed: 115 errors in 8 files; shadow baseline 116 |
| Diff whitespace/scope review | Passed |

Mypy failures concern existing untyped PDF/schema/router code, unavailable PDF-library stubs and imported-module type issues. The clean-typecheck claim applies only to TypeScript. No unrelated code was edited to hide these errors.

Real MongoDB checks use loopback only, randomized `afs_invoice_test_` namespaces and synthetic records; namespaces are removed after each test. They test 20 parallel allocations, one-time tail claims, simultaneous deletion/creation, source-based convergence of 15 correction requests, stale saves and migration/rollback guards. Browser checks use real Chromium UI interactions with synthetic API responses, independently of the real-Mongo tests. They do not claim end-to-end testing against a live application backend. Evidence is in `docs/screenshots/invoice-workflow-fixes/`.

Initial validation-only failures were corrected: an integration assertion used `status_code` instead of the application's `http_status`, a temporary test-file encoding issue prevented collection, and the default Node 18 could not run installed Playwright. The browser checks passed with the existing cached Node 22 runtime. No runtime dependency or production environment file was changed.

## 18. Not executed

No production acceptance test, production data inspection, production index migration or deployment. No combined live-backend browser acceptance run, physical printer output test or external GST/accounting certification. Multi-tenant numbering tests are inapplicable to the existing single-tenant/assignment architecture. Real-Mongo tests are opt-in and skip when their explicit local-test URI is absent; they were explicitly enabled for the reported run.

## 19. Known limitations

- Accounting owner must confirm whether unissued tail-number reuse is permitted for the configured invoice series before applying the migration in production.
- No guaranteed number is displayed before saving; adding pre-save reservations is outside this implementation.
- Shared audit writes follow invoice persistence. A shared-audit failure may return an error even though the embedded event and invoice already persisted; keyed creation retries retrieve the persisted record.
- Dependency checks and tombstone reuse history enrichment span documents without a transaction. Failures preserve evidence in the new invoice and may leave a gap or delayed secondary enrichment. Tombstones are never physically destroyed.
- Cancellation eligibility remains operator-controlled with existing accounting limitations. A replacement remains unissued while its original remains issued.
- Full unique indexes cannot be restored after actual draft reuse or multiple retired correction attempts without conflicting with preserved tombstones. See rollback restrictions below.

## 20. Staging deployment instructions (not executed)

Use the existing Ubuntu/systemd staging environment and its normal configured staging shell. Verify the database target and back up staging first. Do not use production environment files for these commands. Replace the example database name with the independently verified staging name.

```bash
cd ~/Ashapurafinancecrm
# Review code and load staging configuration through the established release process.
sudo systemctl stop afs-crm-backend afs-crm-arq-worker
backend/.venv/bin/python scripts/migrate_invoice_number_reuse.py --database afs_crm_staging
backend/.venv/bin/python scripts/migrate_invoice_number_reuse.py --database afs_crm_staging --apply
npm --prefix frontend run build
sudo systemctl start afs-crm-backend afs-crm-arq-worker
sudo systemctl status afs-crm-backend afs-crm-arq-worker --no-pager
```

Use the actual systemd virtualenv executable if that host uses a different path. Stop if preflight reports conflicts; do not remove records to force success. Verify archived visibility, repeated correction saves, PDF/print, permissions and number reuse with synthetic staging records before owner acceptance.

Local validation (PowerShell):

```powershell
$env:DEBUG='false'
$env:AFS_INVOICE_TEST_MONGO_URI='mongodb://127.0.0.1:27017/'
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_invoices.py tests/api/test_invoice_mongo_integration.py -q
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_access_control.py tests/api/test_system_settings.py tests/api/test_timezone.py -q
npm --prefix frontend run test -- src/features/invoices/Invoices.test.tsx src/components/overlays/Modal.test.tsx src/features/access_control/usePermissions.test.tsx
npm --prefix frontend run typecheck
npm --prefix frontend run build
# Start local Vite on 127.0.0.1:5175 before the synthetic browser check:
frontend/node_modules/.cache/voice-node22/node.exe scripts/invoice-workflows-ui-check.mjs
```

## 21. Rollback and recovery

Stop staging invoice writers first. Before any number reuse or multiple retired correction attempts, the migration supports an explicit dry-run and guarded rollback:

```bash
backend/.venv/bin/python scripts/migrate_invoice_number_reuse.py --database afs_crm_staging --rollback
backend/.venv/bin/python scripts/migrate_invoice_number_reuse.py --database afs_crm_staging --rollback --apply
```

It rebuilds the old guards before dropping replacements, and refuses incompatible historical duplicates. Never delete tombstones, renumber issued documents or reset sequences to make rollback pass. After reuse, prefer a reviewed roll-forward/compatibility release preserving the new indexes and history. An older release that recreates the all-record unique indexes is not a safe rollback target after reuse. Follow the established database backup/recovery process for a staging restore; no production recovery action is automated here.

No unrelated application modules or files were intentionally modified. The new scripts, tests, report and screenshots are directly required invoice validation/migration artifacts. Generated TypeScript build metadata and temporary validation logs are excluded from the final change.
