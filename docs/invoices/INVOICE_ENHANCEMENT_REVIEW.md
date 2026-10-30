# Invoice enhancement review

## A. Implementation summary

Incremental invoice-only changes add draft soft deletion with confirmation, linked replacement drafts with mandatory reasons, duplicate choices with a safe revision fallback, source references, and invoice history. Existing calculation, counter, PDF generator, access control, routes, filters and statuses remain in use. Nothing was deployed.

## B. Files changed

- `backend/app/features/invoices/models.py`: optional relationship, retry-key and embedded history fields; existing deletion metadata is reused.
- `backend/app/features/invoices/schemas.py`: validated deletion/copy inputs and optional creation retry key.
- `backend/app/features/invoices/repository.py`: partial unique indexes for retry keys and replacement source IDs.
- `backend/app/features/invoices/service.py`: soft deletion, dependency checks, version checks, replacement issue gate, settled guards, retry deduplication, source references and history.
- `backend/app/features/invoices/router.py`: deletion, replacement and history endpoints; optional duplicate request body.
- `backend/app/features/invoices/pdf.py`: source references for newly linked invoices; no reference content is added to historical invoices without the new fields.
- `frontend/src/features/invoices/api.ts`: typed workflow calls and optional creation retry key.
- `frontend/src/features/invoices/InvoiceWorkflow.tsx`: invoice-specific workflow modals, history and reference component using the existing shared Modal.
- `frontend/src/features/invoices/InvoiceListPage.tsx`: status/permission-aware actions and workflow entry points.
- `frontend/src/features/invoices/InvoiceViewPage.tsx`: workflow entry points and references; settled cancellation hidden.
- `frontend/src/features/invoices/InvoiceFormPage.tsx`: references and creation retry/double-submit protection.
- `frontend/src/features/invoices/Invoices.test.tsx`: existing regression tests plus confirmation, error handling, revision fallback, correction reason and settled-action coverage.
- `tests/api/test_invoices.py`: soft deletion, retained numbering, replacement issue gate, immutable source data/PDF content, dependencies, concurrent retries and access checks.
- `docs/invoices/INVOICE_ENHANCEMENT_REVIEW.md`: this review and release guidance.

## C. Database changes

Optional fields on existing invoice documents: `replacement_for`, `source_invoice_number`, `correction_reason`, `request_key`, `history`. Existing `duplicated_from`, `is_deleted`, `deleted_by`, `deleted_at` are reused. No new collection or backfill. Each new mutation appends a server-timestamped history event in the same atomic invoice update. Shared audit logging is retained; a shared-audit write failure cannot erase the invoice's embedded event.

Two partial unique indexes include string-valued fields only: `request_key` and `replacement_for`. Legacy documents and nulls are excluded. Replacement uniqueness includes deleted replacement drafts: only one replacement is allowed per original, including after draft deletion. Number uniqueness continues to include deleted and cancelled invoices. Concurrent retries can consume counter values but cannot reuse numbers.

Index creation is wired to the existing `ensure_invoice_indexes` startup mechanism. It runs on application startup when the owner deploys; no production startup or migration was executed during this work. Review index creation permissions and cost before rollout. No historical records need rewriting. Rollback can retain additive fields and indexes; do not remove historical events or reset counters. Rolling back application code also rolls back the new safety gates, so assess that risk before rollback.

## D. API changes

Existing base prefix: `/api/v1`.

- `DELETE /invoices/{id}`: `{version}`, requires existing invoice edit permission; soft-deletes drafts only.
- `POST /invoices/{id}/replacement`: `{request_key, reason}`, requires create permission and scoped source access. Issued/cancelled sources only. Never automatically cancels or issues.
- `GET /invoices/{id}/history`: requires view permission and scoped access; recorded events only, including legacy audit records.
- Existing `POST /invoices/{id}/duplicate` accepts an optional `{request_key}` body; bodyless clients remain compatible.
- Existing invoice creation accepts optional `request_key`; browser create/copy/replacement flows supply stable keys across retries. Legacy callers omitting a key retain prior behavior and are not retry-idempotent.
- Existing status endpoints reject cancellation of partially paid invoices. Paid invoices remain terminal. Replacement issue requires a cancelled original.

## E. UI changes

Draft deletion requires confirmation and retains backend errors on failure. Duplicate opens a modal offering new-number creation and revision. Revision explains that the current architecture lacks internal revision records and directs users to existing draft editing or a linked replacement with a new unique number. No same-number statutory copy is created. References appear in draft editing, invoice detail and newly linked PDFs. History uses the existing modal and shows stored actions, timestamps, user IDs, status changes, reasons and related numbers where recorded; missing legacy fields are not invented.

## F. Validation

- Backend invoice suite: 33 passed (`pytest -c backend/pyproject.toml tests/api/test_invoices.py -q`).
- Frontend invoice suite: 11 passed (`npm run test -- src/features/invoices/Invoices.test.tsx`).
- Frontend typecheck and production build passed. Vite reports the existing large bundle warning.
- Invoice ESLint and backend invoice/test Ruff passed.
- Strict mypy is not clean: it reports missing PDF library stubs, existing untyped invoice/PDF code and imported-module typing issues. It is not a release gate satisfied by this change. No unrelated typing code was modified.
- Initial test invocations failed due to inherited `DEBUG=release` and omission of the backend pytest configuration. Final backend runs used process-local `DEBUG=false` and the correct config; no environment file changed.
- Browser visual/mobile review and real MongoDB multi-process concurrency testing were not performed. API concurrency tests use the existing mock database infrastructure.

## G. Security and financial integrity

Every new endpoint uses existing authentication and invoice permissions, with existing owner/staff record scoping. Deletion uses edit permission rather than adding grants to the authorization architecture. Version/status predicates prevent stale mutations. Issued content remains draft-edit protected. No ordinary endpoint edits audit history. No hard deletion or number release occurs. Existing decimal GST calculations are reused and covered by regressions. Replacement uniqueness and a cancelled-original issue gate prevent two issued replacements against one source. Settled copy/replacement/cancellation operations are blocked because accounting adjustments are unsupported.

The application explicitly defers tenant IDs in its existing base model. This enhancement preserves its single-tenant/assignment scope; it does not claim multi-tenant isolation that the application lacks. History identifies users by stored user ID; legacy events without a recorded actor show that absence.

No payment/ledger models reference invoices in the current repository. Deletion checks invoice-to-invoice dependencies and preserves the entire soft-deleted document. Cross-document dependency checks are not transactional; concurrent copy creation can leave a retained reference to a soft-deleted draft, but no invoice or reference is hard-deleted.

## H. Production readiness and unsupported portions

Ready for owner code review and staging validation, subject to the checks below. Credit notes and internal revision snapshots are not implemented because the current system lacks the necessary accounting/revision model; the requested safe fallback is shown. Previous draft values are not reconstructed from legacy logs. Replacement creation is separate from cancellation. Existing cancellation remains operator-controlled; the system has no GST filing/e-invoice cancellation-window data and cannot independently certify legal eligibility. Accounting/legal confirmation of cancellation policy is required before production use of replacement issuance. This is not a certified statutory compliance workflow. Replacement drafts are blocked from issue while the original remains issued; when cancellation is legally unavailable, leave the replacement unissued and use an external approved accounting process.

Historical PDFs are generated on demand by the existing generator rather than stored as PDF binaries. Existing snapshots are retained, and the replacement test verifies the original's extracted PDF content remains unchanged before cancellation. Byte-for-byte PDF identity is not promised because rendering metadata can vary. Existing cancellation rendering continues to label a cancelled invoice.

## I. Deployment instructions (not executed)

Run validation from the repository root in PowerShell:

```powershell
$env:DEBUG = 'false' # only in the local test process/shell
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_invoices.py -q
backend/.venv/Scripts/python.exe -m ruff check backend/app/features/invoices tests/api/test_invoices.py
npm --prefix frontend run test -- src/features/invoices/Invoices.test.tsx
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Use the owner's established production release process after review. The checked-in compose file uses development environment configuration, so do not treat it as a production command. For a reviewed local/staging environment using that compose definition:

```powershell
docker compose -f deployment/docker-compose.yml build backend frontend
docker compose -f deployment/docker-compose.yml up -d backend frontend
```

Before any production rollout, back up MongoDB, review/apply the additive indexes through the established startup process, confirm cancellation policy, perform a real-Mongo concurrency check, and review desktop/mobile dialogs. Do not reset sequences or backfill historical numbers. No new environment variables or packages are needed.

## J. Scope confirmation

No unrelated application modules or files were intentionally modified.
