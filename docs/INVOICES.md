# Invoice Management

Invoices use the existing single-company CRM. No tenant IDs, tenant switching,
authentication changes, customer duplicates or parallel permission system are introduced.

## User workflow

1. An owner configures Company Settings (name, address, phone, email and logo).
2. Open Settings → Invoice Settings for GSTIN, website, bank, prefix, starting-number
   floor, default GST/terms, signature image and optional QR configuration. Settings
   are owner-only, matching the existing Settings interface. Images retain aspect ratio.
3. Grant employees Invoices View/Create/Edit in the existing permission matrix.
   Create/Edit still require View, enforced by the existing permission engine.
4. Finance / Billing → Invoices supports search, date/status filtering, sorting and
   pagination. Create a draft, preview its A4 PDF, then issue it from the detail page.
5. Drafts can be edited. Issued/partially-paid invoices can be marked paid or cancelled.
   Paid/cancelled invoices cannot be changed. Cancellation requires a reason and keeps
   the original record. Duplicate creates a new numbered draft with current company
   settings, copied customer/items/tax configuration and today's IST dates.

Employees can access invoices for customers assigned through the existing Application
relationship. Manual company billing recipients are invoice snapshots, not a separate
customer database; only the creator and owners can access those invoices. Null customer
IDs on unsubmitted applications never grant access to other manual invoices. Owners
retain their existing unrestricted staff access. All record, PDF and mutation endpoints
apply the same record scope. Company bank information is only exposed through protected
invoice APIs/PDFs; general Company Settings responses do not gain bank fields.

## Storage and accounting

- `invoices` extends the CRM's `BaseDocument` and uses `BaseRepository` for insertion.
  It stores customer/company snapshots, calculated rows/totals/HSN groups, words,
  dates, creator, version, issue/cancellation metadata and immutable image references.
- `company_settings.invoice_config` extends the existing singleton. Logo remains its
  existing `logo_s3_key`. Signature PNGs use the existing S3 client/bucket with unique
  UUID object keys under `company/invoice-signature/`. Assets are not stored in Mongo.
  Issuing copies configured images into unique `invoice-assets/{id}/` keys so replacing
  source logo/signature objects cannot alter issued invoices. Total quantity is derived
  from stored items on read, rather than persisted independently.
- Existing `counters` / `generate_id` allocate an atomic global `INV` sequence.
  Prefix is configurable; starting number is a monotonically raised floor, never a
  reset. A unique `invoice_number` index provides a second safeguard. Numbers are
  stable across edits and status changes. Failed creations may leave sequence gaps.
- Python `Decimal` calculates each line's taxable value and rounds half up to paise.
  IGST is then rounded per line. Split GST rounds each CGST/SGST component separately.
  Invoice/HSN totals sum these rounded line values. HSN groups include both code and
  GST rate. Monetary BSON/API values are decimal strings, never binary floats.
- Frontend live calculations use scaled `BigInt` with the same rounding rules.
  Currency display preserves decimal strings even beyond JavaScript's safe integer
  range. Backend inputs reject submitted calculated totals and amount-in-words fields.
- Optimistic version/status checks prevent stale edits or issue/cancel races.
  Issued snapshots are not refreshed from later customer/company settings changes.
- Existing append-only `audit_logs` records create, edit, issue, status, duplicate,
  cancellation, PDF downloads, print requests and settings/signature changes. Print
  requests can be audited; completing a browser's native print dialog cannot.
- Invoice deletion is not exposed, including through the CRM Bin registry.

## API endpoints

All paths below use `/api/v1` (the existing configured API prefix).

| Method | Path | Access |
|---|---|---|
| GET / POST | `/invoices` | View / Create |
| GET / PUT | `/invoices/{id}` | View / Edit, record access |
| POST | `/invoices/{id}/duplicate` | Create, source record access |
| POST | `/invoices/{id}/status` | Edit, valid lifecycle/version |
| POST | `/invoices/{id}/cancel` | Edit, reason/version |
| GET | `/invoices/{id}/pdf?purpose=download\|print\|preview` | View, record access |
| GET | `/invoices/defaults` | View |
| GET | `/invoices/customers` | View, existing customer scope |
| POST | `/invoices/preview` | View, linked customer access |
| POST | `/invoices/preview/pdf` | View, linked customer access |
| GET / PUT | `/invoice-settings` | Owner |
| POST | `/invoice-settings/signature` | Owner, multipart PNG |

Creation/edit bodies follow `InvoiceInput`; status/cancellation writes require the
last-read `version`. Date filters use ISO dates. List responses contain `items`,
`total`, `page`, `page_size`, `total_pages` inside the standard API envelope.
PDF responses are binary, authenticated and sent with `Cache-Control: no-store` by
the existing security middleware. The shared frontend
client refreshes expired bearer tokens for PDF requests as it does for JSON requests.

## PDF and visual QA

`pdf.py` uses ReportLab vector text, embedded open-licensed Roboto fonts (including ₹),
bordered tables and A4 pages. It receives already calculated invoice data; it performs
no accounting. The form preview and detail view embed this same authenticated PDF.
Long item/HSN tables split with repeated column headings and numbered pages; the bank,
words, totals, QR and signature block stays together.

The supplied PDF was visually inspected before implementation. Its company header,
top-right logo, centered INVOICE title, billing/details arrangement, service table,
bank/words/totals strip, QR/signature footer and half-width HSN summary guide the layout.
The sample was rendered and visually inspected after alignment/typography corrections.
Browser-added timestamps, file title and local print URL in the source are not company
invoice content and are omitted. Output uses A4 instead of the source's US Letter.

QR defaults to disabled. Issuing generates either an informational invoice identifier
or a real UPI URI using configured payee details and the stored total. No payment data
is invented. QR content therefore varies from the reference. The comparison sample
uses `Invoice:9`, not the source's payment QR. Logo/signature clips in the sample are
test-only renderings from the user-supplied reference; they are never installed into
production settings or S3 automatically.

From the project root (PowerShell), reproduce the visual sample:

```powershell
$env:PYTHONPATH = 'backend'
backend/.venv/Scripts/python.exe scripts/render_invoice_sample.py --reference 'C:\Users\Lenovo\Downloads\AADIFIDELIS SOLUTIONS SEPTEMBER 2026.pdf' --output docs/invoices/sample-invoice.pdf
```

Requires backend dev dependencies. The script writes a PDF and rendered PNG(s), with
no database/S3 writes. [Sample PDF](invoices/sample-invoice.pdf) · [Rendered sample](invoices/sample-invoice-1.png).

## Database rollout

**No database migration required.** Existing documents remain compatible through
optional defaults. Normal backend startup idempotently creates invoice indexes and
adds the Invoices permission/nav catalog entries. It does not grant permissions,
seed business data, reset counters or rewrite existing records. An initial company
settings record is created through the existing Settings repository when needed.

## Deployment steps

For the production systemd layout documented in
`docs/deployment/AWS-Deployment-Documentation.pdf`, first deploy the reviewed source
release into `/opt/afs-crm`, back up Mongo using the existing procedure, then run:

```bash
cd /opt/afs-crm
backend/.venv/bin/python -m pip install ./backend
cd frontend
npm ci
npm run build
sudo systemctl restart afs-crm-backend afs-crm-worker
sudo systemctl reload nginx
curl --fail http://127.0.0.1:8000/api/v1/health
```

Keep the existing service environment and authentication configuration. Then complete
company/invoice settings, S3 access and explicit employee grants as described below.
No service-unit, Nginx or environment-file changes are required by this feature.

For a local or alternate existing deployment:

1. Back up the existing Mongo database using the normal deployment procedure.
2. Install updated backend dependencies in the service environment:
   `python -m pip install -e ./backend` (or rebuild the existing backend Docker image).
   PDF runtime dependencies are ReportLab, Pillow, qrcode and font-roboto; PyMuPDF is
   only a dev/visual-test dependency.
3. In `frontend`, run `npm ci` then `npm run build`. Publish `frontend/dist` using the
   existing web-server deployment process. No frontend dependencies were added.
4. Restart the existing FastAPI service so invoice indexes/catalog entries are ensured.
   For the repository's Docker stack, from the project root:
   `docker compose -f deployment/docker-compose.yml up -d --build backend frontend`.
   This compose file uses the project's development environment configuration; use
   your established production environment configuration for a production rollout.
5. Verify existing S3 configuration and IAM PutObject/GetObject access for company
   images and `invoice-assets/` snapshots (same-bucket copy needs source read and
   destination write). Configure Company/Invoice Settings and upload the actual logo/signature.
   Issuing requires company address, GSTIN and bank name/account/IFSC. No reference
   bank/payment settings are seeded automatically.
6. Grant employee invoice permissions explicitly. Refresh the signed-in UI to load
   the nav catalog, then smoke-test draft → preview → issue → download/print and
   restricted employee access with real Mongo/S3. No deployment was performed by this task.

## Validation commands

```powershell
$env:PYTHONPATH = 'backend'
$env:DEBUG = 'false'
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_invoices.py -q
backend/.venv/Scripts/ruff.exe check backend/app/features/invoices tests/api/test_invoices.py scripts/render_invoice_sample.py
Set-Location frontend
npm test
npm run typecheck
npm run lint
npm run build
```

The test harness uses mocked Mongo/Redis/S3; parallel numbering is exercised against
the mock database. Real Mongo concurrency and browser print-dialog completion need
deployment smoke checks. Statuses Paid/Partially Paid are staff-managed invoice labels;
this module does not add payment reconciliation or credit notes.

## Files changed

- New backend feature: `backend/app/features/invoices/{__init__,assets,calculations,models,pdf,repository,router,schemas,service}.py`.
- Backend integration: `backend/app/main.py`, `backend/app/features/system_settings/models.py`, `backend/pyproject.toml`.
- New frontend feature: `frontend/src/features/invoices/{api,calculations,calculations.test}.ts` and
  `{InvoiceListPage,InvoiceFormPage,InvoiceViewPage,InvoiceSettingsPage,Invoices.test}.tsx`.
- Frontend integration: `frontend/src/app/router.tsx`, `frontend/src/components/layout/navConfig.ts`,
  `frontend/src/features/employee/permissionMatrix.ts`, existing Settings hub/tabs and
  `frontend/src/shared/api/client.ts` (authenticated binary responses).
- Tests/visual QA: `tests/api/test_invoices.py`, `scripts/render_invoice_sample.py`,
  `docs/invoices/sample-invoice.pdf`, `docs/invoices/sample-invoice-1.png`.
- Documentation: this file and the appended decision 136 in `docs/decisions/DECISIONS.md`.

## Executed validation — 08-Oct-2026

- Final invoice backend run: **28 passed**. Includes decimal/split rounding, HSN groups,
  Indian words, validation, list/search, draft edits, numbering floor/parallel requests,
  duplicate, status/cancellation, stale versions, auth/RBAC, record scope/revocation,
  customer picker search beyond 100 records, PDF A4/pagination, QR payloads, PNG upload,
  image snapshots/replacement/failure and derived total quantity.
- Broader backend regression run: **1,160 passed, 2 failed**, with 72 existing Arq/Redis
  deprecation warnings. The two failures are listed below. The final expanded invoice
  suite was run separately after that broader run was collected.
- Full frontend suite: **305 passed across 60 files** using `npm test -- --maxWorkers=2`.
  Invoice UI/calculation tests account for 11 of those tests. A preceding default-worker
  run had a 5-second timeout in the unchanged insurance applicant form test; that file
  passed in isolation and the complete suite passed with two workers.
- `npm run typecheck`: passed. `npm run lint`: 0 errors, 10 warnings in existing files.
  `npm run build`: passed; Vite reports its large JavaScript chunk warning (about 1.2 MB
  before gzip). Unrelated warning cleanup/code splitting was not included.
- Ruff check of new backend/tests/visual script and changed backend integrations: passed.
  `git diff --check`: passed.
- Final sample PDF: **one A4 page**, rendered to PNG and visually inspected against the
  supplied reference. Multi-page item tables and split-tax PDFs were also exercised.

Unrelated backend failures, reproduced using the original `HEAD` versions of both
changed backend source files (`app.main` and `system_settings.models`), with every
other existing backend source file unchanged:

1. `test_advisor_business_owner_employee_and_unauthorized` expects 403 but receives 404.
2. `test_two_applications_same_customer_keep_independent_assignments` expects an employee
   assignment on an insurance case but receives `None`.

These were left unchanged because this task explicitly excludes Advisor/Insurance
behavior changes. Real AWS/S3 operations, Mongo concurrency and browser print dialogs
were not exercised against a deployed service. No production database or deployment
was modified.
