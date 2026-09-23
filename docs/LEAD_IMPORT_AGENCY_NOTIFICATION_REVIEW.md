# Local implementation review — Leads, Agency Code and notifications

Date: 23 September 2026. Work is local and uncommitted. This report supplements, rather than replaces, `INSURANCE_COORDINATED_CHANGE_REVIEW.md`.

## 1. Changes delivered

- Removed Agent Code from the Agency Code table, shared Agency/Advisor edit form, and the linked Advisor detail display. Historical values remain in storage and the existing generic Advisor API for compatibility. Agency Code, password masking/reveal, joining date, Type and Status remain available.
- Authorized Insurance employees can use Advisor Existing Business **Add** through the same form, endpoint and service as Owners.
- Notification destinations now come from existing entity type/ID metadata, with exact Lead, Insurance case, application, support ticket and task destinations. Legacy notifications retain a safe inbox fallback.
- Added one reusable CSV/XLSX upload dialog to General Leads and Insurance Fresh Leads, including sample Excel, authoritative preview, errors, confirmation, partial results and retry protection.

## 2. Backend and API changes

The new feature is `backend/app/features/bulk_import/`. All endpoints use the existing API envelope and active-user/permission checks.

| Endpoint under `/api/v1` | Purpose |
| --- | --- |
| `GET /bulk-import/{kind}/sample` | Generate an XLSX workbook; return filename and base64 content in the normal JSON envelope. |
| `POST /bulk-import/{kind}/preview` | Accept a multipart `file`, parse and validate without creating business records. |
| `POST /bulk-import/{kind}/confirm` | Accept `batch_id` and optional location coordinates; process at most 25 eligible rows per request. |

`kind` is restricted to `leads` or `insurance`. Preview and confirmation return total, valid, invalid, duplicate, imported, failed and processing counts, row numbers, original parsed values, error messages and batch state. The stored creation payload is not returned to the browser or accepted back from it.

Existing Lead validation was extracted into `validate_create_lead`; both manual creation and import use it. Assignment recipient validation is also shared, and now happens before a manually created Lead is inserted. Insurance preview reuses product/category validation and the customer/form-definition preflight used by manual Insurance creation. Existing record creation, code generation, audit, notes, account handling and workflow services remain authoritative.

No existing API route or request field was removed. The Advisor business POST has a broader, explicitly checked existing permission alternative. Support creation supplies an optional ticket reference to its existing notification/task side effect.

## 3. Frontend changes

`BulkUploadModal` is shared by both lists and uses existing Modal, Button, ErrorBanner and authenticated API components. The API client omits the JSON Content-Type header only for FormData so the browser supplies the multipart boundary; its authentication and refresh behavior are unchanged.

The dialog supports file selection, sample download, validation/loading errors, record details, counts, row errors, downloadable CSV error reports, explicit import confirmation and final/partial results. Cancel and repeat submission are disabled during an operation. Lists/counts refresh after confirmed groups. A single confirmation drives all groups of 25 automatically; a network failure leaves completed groups visible and safely resumable.

No browser-only validation is trusted. The frontend checks extension, empty files and 5 MB size; the backend repeats file checks and validates every row.

## 4. Permissions

| Operation | Existing permission used |
| --- | --- |
| General Lead sample / preview / confirm | `leads:leads:create` |
| General Lead imported Assign To | Additionally `leads:leads:assign` |
| Insurance sample / preview / confirm | `insurance_management:applications:edit`, matching manual creation |
| Advisor Existing Business Add | Existing Insurance read access plus either `insurance_management:applications:edit` or legacy `insurance_management:recruitment:edit` |

Owners retain the existing permission-engine override. Employees without the applicable grants receive backend 403 responses. Batch ownership and import kind are checked independently of endpoint permission. No new permission catalog, global RBAC behavior, role grant, seed or migration was introduced. Advisor password reveal and Agency/Advisor editing keep their stricter existing Recruitment edit gate.

## 5. Notification routing and authorization

One shared `notificationDestination` helper is used by the staff bell, customer bell and notification list. It never derives a route from a title or message. IDs are URL-encoded and destinations come from a fixed route map.

| Entity | Staff destination |
| --- | --- |
| `lead` | `/leads/:id` |
| `insurance_case` | `/insurance-cases/:id` |
| `loan_case` | Existing `/loan-cases/:id` route; no Loan code changed |
| `application` | `/applications/:id` |
| `customer` | `/customers/:id` |
| `support_ticket` | `/support-tickets?ticket=:id`, opening the authorized ticket detail |
| `task` | `/tasks?task=:id`, opening a detail dialog through the existing scoped API |
| `advisor`, `recruitment_lead` | Existing Insurance Management detail routes |
| Missing/unknown reference | `/notifications` |

Customer application notifications retain the Document Center destination. Customer support references select the matching record from the customer's own ticket list. Other customer references fall back to `/portal/alerts`.

New support notifications reference the persisted Support Ticket, including the assigned-employee task notification path. Existing notifications are not rewritten. Read/unread, archive, dismissal, filters and inbox ownership are preserved. A reference does not grant record access: the existing destination APIs still enforce their permissions and record scope. Denied task/ticket detail requests show a safe error.

## 6. Import architecture, duplicates and partial success

1. Parse the uploaded file in a worker thread.
2. Resolve supported reference names/IDs and validate against the actual creation schemas and shared preflight methods.
3. Store the preview in the existing Redis infrastructure, bound to actor, kind and a SHA-256 fingerprint of parsed rows. Workbook ZIP timestamps do not affect identity.
4. Wait for explicit user confirmation. Preview never invokes record creation.
5. Recheck endpoint permission, batch ownership, current business validation and General Lead geofencing before creation. Assignment permission is checked for every applicable row.
6. Acquire the batch lock, reread its current state, record write intent and invoke the existing creation service for each row.
7. Save every row outcome. After 25 rows, release only a fully checkpointed group for continuation; the UI automatically requests the next group.

General Leads keep their existing company-wide active-mobile duplicate rule. Rejected historical matches remain governed by the existing service. Repeated valid mobiles within an uploaded General Lead file are reported as duplicates. Duplicate errors do not reveal another lead's ID/code. Insurance permits multiple applications for an existing customer, exactly as manual Insurance creation does; it does not invent a mobile uniqueness policy.

An identical parsed batch submitted by the same actor cannot be replayed for 24 hours while its Redis state remains available. Completed results are returned on retries. Known completed groups can resume only their remaining rows. An interrupted in-progress row is not automatically retried because the existing creation service may already have performed some writes. Failed/uncertain rows explicitly instruct the operator to check existing records. This is partial-success processing, **not an all-or-nothing transaction**.

## 7. File handling, validation and sample workbook

- CSV: UTF-8/UTF-8 BOM, Python's strict CSV parser. Binary/NUL data and malformed input are rejected.
- XLSX: `openpyxl` with `defusedxml`, read-only, no formula evaluation, external links disabled. XML and ZIP errors become safe validation messages.
- XLS and macro-enabled formats are unsupported. No legacy XLS parser was added.
- Maximum 5 MB upload, 500 records, 10,000 characters per cell, 2,000 ZIP entries and 25 MB declared expanded workbook content.
- Reject encrypted archives, VBA/external-link entries, unsupported columns, duplicate headers and excessive sparse worksheet coordinates, including distant empty rows.
- Formula prefixes (`=`, `+`, `-`, `@`) and unsupported control characters produce explicit row errors. They are not silently stripped. Sample cells are written as text; downloaded CSV error values are also protected against formula injection.
- Required fields, mobile/email, dates, numbers and Insurance profile bounds use the actual creation schemas. Dates accept `YYYY-MM-DD`, `DD-MM-YYYY` and native Excel dates. Non-finite numeric values are rejected.
- General Lead source/product and Insurance category/product use current reference data; ambiguous names require an ID. Insurance validates category/product membership, active category, configured form definition and customer eligibility. Gender accepts `male`, `female`, `other`.
- Blank physical records remain visible as invalid rows. No invalid row is silently dropped.

The workbook contains **Leads**, **Instructions** and **Lookups** sheets. Its column mapping is generated from the current Lead or manual Insurance Pydantic model, using readable labels. The example uses actual catalog names when available. Only the first sheet is imported.

General Lead columns include Full Name, Mobile, Email, Lead Source, Product Category, Product, Remarks, City, Preferred Loan Amount, Salary In Hand, Next Follow Up Date, Comments and Assign To. Browser coordinates and the optional structured `product_form_data` payload are excluded from the simple spreadsheet format.

Insurance includes the current scalar applicant fields: name, mobiles, email, gender, age, profession, annual income, remarks, category, product, height, weight, parents, education, company, designation and nominee details. Initial stage/rejection/re-eligibility controls are excluded: imports create Fresh Leads through the existing workflow.

## 8. Test and check results

Commands were run locally. Backend commands used `backend/.venv`, `DEBUG=false` for test processes, `-c pyproject.toml`, mocked MongoDB and fakeredis. No production database or storage service was contacted.

| Check | Result |
| --- | --- |
| Backend regression: Leads, Recruitment Advisors, Support, Reminders, Insurance coordinated changes, Insurance employee visibility, initial bulk and Agency/notification tests | **220 passed** in 319.27s |
| Final combined bulk + manual Insurance + Agency/business/notification suites after fingerprint correction | **54 passed** in 59.46s |
| Final bulk suite including CSV formula-prefix checks | **29 passed** in 50.15s |
| Frontend Insurance, Recruitment, Leads list, bulk upload, reminders, staff/customer bells, task and support detail suites, `--maxWorkers=2` | **122 passed**, 27 files, in 37.94s |
| Final Advisor detail regression after removing the linked Agent Code display | **7 passed** in 626ms test time |
| `npm.cmd run typecheck` | **Passed**, exit 0 |
| `npm.cmd run build` | **Passed**, exit 0; 381 modules; Vite 9.69s on the final frontend build |
| ESLint on every changed/new TS/TSX file | **Passed**, exit 0 |
| Ruff on new import files, new tests and other changed backend files except CustomerService | **Passed** |
| Ruff formatting check on new backend feature/tests | **Passed**, six files formatted |
| Ruff on changed CustomerService | One pre-existing `RUF012` at `_CASE_NEXT_ACTION` (line 2057 after changes) |
| Mypy import feature plus its transitive dependencies | No error in new import files; six pre-existing errors in existing dependencies, listed below |
| `git diff --check` | **Passed**; only repository line-ending notices |

Backend regression command:

```text
python -m pytest -c pyproject.toml ../tests/api/test_bulk_import.py ../tests/api/test_agency_business_notifications.py ../tests/api/test_leads.py ../tests/api/test_recruitment_advisors.py ../tests/api/test_support.py ../tests/api/test_reminders.py ../tests/api/test_insurance_coordinated_changes.py ../tests/api/test_insurance_employee_visibility.py -q --tb=short
```

Final combined backend command:

```text
python -m pytest -c pyproject.toml ../tests/api/test_bulk_import.py ../tests/api/test_insurance_manual_lead.py ../tests/api/test_agency_business_notifications.py -q --tb=short
```

Frontend regression command:

```text
npm.cmd test -- src/features/insurance_management src/features/bulk_import src/features/reminders src/features/recruitment src/features/support/pages/SupportTicketListPage.test.tsx src/features/dashboard/components/NotificationBell.test.tsx src/features/customer/components/CustomerNotificationBell.test.tsx src/features/leads/pages/LeadListPage.test.tsx --maxWorkers=2
```

These runs overlap; their test counts should not be added as independent tests. Coverage includes CSV/XLSX for both kinds, samples, no-write preview, explicit confirmation, invalid type/content/size, schema/row errors, formula and sparse-workbook rejection, normal creation effects, duplicate and partial results, chunk continuation, retry protection, actor/kind binding, expiration, blocked in-progress batches, employee import authorization, assignment authorization, historical Agent Code preservation, Agency fields/password behavior, Owner/employee business access and notification navigation/denied access.

## 9. Existing failures, corrected failures and limitations

Existing Mypy findings remain in unchanged logic:

- `customer/field_validation.py:52,54`: `Any` returned as `bool`.
- `auth/service.py:196`: `Any` returned as `str`.
- `loan_management/service.py:418`: optional workflow assignment.
- `customer/service.py:558`: optional ID supplied to repository update.
- `leads/service.py:1049`: pre-existing eligible-assignee sort-key tuple annotation mismatch. The same tuple/annotation is present in HEAD.

The CustomerService mutable class-default lint finding is also present in HEAD. These unrelated issues were not suppressed or altered, and the full backend static-check result is **not clean**.

During development, the broad frontend run had one existing extended-applicant test hit its five-second timeout under higher concurrency. It passed unchanged with two workers, and the final 122-test run passed. Existing jsdom canvas-not-implemented messages and deliberately exercised error-path console messages remain. The production build retains its existing chunk-size warning (main bundle approximately 1.16 MB uncompressed).

A new retry regression initially failed because recreated XLSX files had different ZIP timestamps. This was fixed by fingerprinting parsed rows, and the combined 54-test backend run then passed. An early oversized-file parametrization generated an excessively long test ID; explicit IDs fixed that test harness issue. No failing test was deleted or disabled.

Security and operational boundaries:

- Batch previews contain customer data in the existing Redis store for up to 24 hours after their latest checkpoint. They are actor-bound and are not logged. Loss/eviction of Redis state ends this batch retry guarantee; it is not a permanent database idempotency ledger.
- The existing manual creation services are not transactional. An unexpected failure can leave some service writes in place; this is why uncertain rows are reported and never automatically replayed.
- General Lead duplicate checking remains the existing application-level business rule. The current repository does not provide a unique active-mobile database index; concurrent separate manual/import requests can retain that pre-existing race. No new uniqueness index or historical-data cleanup was silently introduced.
- There was no real-browser or live-infrastructure smoke test. Component/API tests and the production build passed; manual browser checks below remain for the user's review.

## 10. Manual verification

1. Open Recruitment → Agency Code. Check the eight requested columns, no Agent Code in the list/edit/linked detail, masked password/eye behavior, joining date, Type and Status. Edit Agency Code, password and joining date; verify the record reloads correctly.
2. As Owner, add Existing Business to an Advisor. Repeat with an employee holding Insurance applications view/edit but no Recruitment edit. A view-only or ungranted employee must lack Add and receive a direct API 403. Verify business validation still rejects invalid inputs.
3. Click Lead, Insurance, Support and Task notifications in the bell/list. Confirm the exact record opens and unread state changes. Check legacy inbox fallback, archive, dismissal and filters. Try a restricted reference: the destination must deny access.
4. Download both sample workbooks. Inspect the Instructions/Lookups tabs and replace the example row with local test customer data.
5. Upload CSV and XLSX in General Leads. Include valid rows, an invalid mobile/email/date, a missing required value and duplicate mobiles. Check preview counts/errors and download the error report. Verify no record exists before confirmation.
6. Confirm and check normal Lead details, Fresh/Assigned counts, comments, follow-up, assignment notification and existing edit/bin behavior. Upload the same parsed rows again and verify no replay.
7. Repeat in Insurance Fresh Leads, including a category/product mismatch and invalid gender. Verify ordinary AFS Insurance codes, customer/application/workflow records and normal stage/document gates. Existing-customer repeat applications should follow manual behavior.
8. Try more than 25 valid records: confirm once, watch the groups complete, and verify each row appears once. Simulate a network interruption between groups and reopen the same file to inspect/resume known remaining rows.
9. Try unsupported XLS/XLSM, oversized, empty, malformed and formula-containing files. Verify safe errors and an operable dialog after failures.
10. Verify geofenced General Lead creation with an authorized employee, and revoke an employee's create/edit permission between preview and confirmation to check backend rejection.

## 11. Change boundaries

No production access performed.

No commit/push performed.

No migration required. Existing document structures and historical data are preserved; batch state uses the existing Redis infrastructure.

No seed required.

No .env changes.

No deployment commands, SSH, Nginx changes or Loan Management file changes. No authentication/session/tenant/global RBAC architecture changes. Dependency declarations add `openpyxl>=3.1.5,<4` and `defusedxml>=0.7.1,<1`; the locally installed versions used for checks were 3.1.5 and 0.7.1. Temporary editing scripts and build metadata changes were removed from the delivered diff.

## 12. Exact files changed

The complete local change inventory follows.

- backend/app/features/bulk_import/__init__.py
- backend/app/features/bulk_import/files.py
- backend/app/features/bulk_import/router.py
- backend/app/features/bulk_import/service.py
- backend/app/features/customer/service.py
- backend/app/features/insurance_management/service.py
- backend/app/features/leads/service.py
- backend/app/features/recruitment/advisor_router.py
- backend/app/features/recruitment/dependencies.py
- backend/app/features/reminders/service.py
- backend/app/features/support/service.py
- backend/app/main.py
- backend/pyproject.toml
- docs/LEAD_IMPORT_AGENCY_NOTIFICATION_REVIEW.md
- frontend/src/features/bulk_import/BulkUploadModal.test.tsx
- frontend/src/features/bulk_import/BulkUploadModal.tsx
- frontend/src/features/customer/components/CustomerNotificationBell.tsx
- frontend/src/features/customer/pages/SupportPage.tsx
- frontend/src/features/dashboard/components/NotificationBell.test.tsx
- frontend/src/features/dashboard/components/NotificationBell.tsx
- frontend/src/features/insurance_management/pages/InsuranceCaseListPage.test.tsx
- frontend/src/features/insurance_management/pages/InsuranceCaseListPage.tsx
- frontend/src/features/leads/pages/LeadListPage.test.tsx
- frontend/src/features/leads/pages/LeadListPage.tsx
- frontend/src/features/recruitment/components/EditAdvisorModal.test.tsx
- frontend/src/features/recruitment/components/EditAdvisorModal.tsx
- frontend/src/features/recruitment/pages/AdvisorDetailsPage.test.tsx
- frontend/src/features/recruitment/pages/AdvisorDetailsPage.tsx
- frontend/src/features/recruitment/pages/AgencyCodeListPage.test.tsx
- frontend/src/features/recruitment/pages/AgencyCodeListPage.tsx
- frontend/src/features/reminders/api.ts
- frontend/src/features/reminders/notificationDestination.test.ts
- frontend/src/features/reminders/notificationDestination.ts
- frontend/src/features/reminders/pages/NotificationListPage.test.tsx
- frontend/src/features/reminders/pages/NotificationListPage.tsx
- frontend/src/features/reminders/pages/TaskListPage.test.tsx
- frontend/src/features/reminders/pages/TaskListPage.tsx
- frontend/src/features/support/api.ts
- frontend/src/features/support/pages/SupportTicketListPage.test.tsx
- frontend/src/features/support/pages/SupportTicketListPage.tsx
- frontend/src/shared/api/client.ts
- tests/api/test_agency_business_notifications.py
- tests/api/test_bulk_import.py
