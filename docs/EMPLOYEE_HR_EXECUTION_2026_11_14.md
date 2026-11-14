# Daily Update and Employee HR execution

## Batch 1: repository inspection

The application is React/TypeScript with TanStack Query and React Router, backed by
FastAPI, Motor/MongoDB and Redis. Existing company scope is one authenticated CRM
database per company (decision 001); company settings use the singleton `default`.
No client-supplied company selector or parallel tenant architecture will be added.

Reusable employee functionality lives in `backend/app/features/employee` and
`frontend/src/features/employee`: shared auth user identity, canonical employee/user
link, owner-only creation/account activation, department/designation/branch masters,
bank encryption, permission matrix assignment, self profile, uploads, owner document
overview, activity, sessions, login history and CSV directory export. Existing
account creation requires branch, joining date, employment type and an initial
password in addition to the fields listed in the new minimal workflow. Those
existing account/provisioning rules must be handled explicitly, not silently guessed.

Daily Operations has backend pagination, server-side search/filter/sort/count,
versioned shared bank and status catalogs, CAS updates/audit, staff-only access,
own-record authorization, import/export and historical snapshots. Follow-up
pagination is currently fixed at 20 in the UI and capped at 100 in its router.
`bank_options.py` extends `StatusOptions`; loan options should use that shared
normalization, uniqueness, archive, optimistic locking and permissions mechanism.

Auth already owns session-family lifecycle and `attendance_days`; Daily Operations
attendance/reconciliation reads canonical session data. Reuse these records rather
than adding a second clock-in system or counting refresh rows as new attendance.
Existing deterministic inactivity expiry is a session policy, not evidence of
productive/payable work. HR reconciliation must preserve the distinction between
observed logout, policy expiry and an unknown/missing OUT.

Existing gaps: separate onboarding/profile verification states; experience/fresher
rules; per-document verification and immutable versions; employee upload/reupload;
protected Aadhaar handling; approval-based profile edits; leave types/policies and
requests; HR reports and notification destinations. Existing self-edit writes
directly, so approved profiles require a request path. Existing document keys include
the supplied filename and lack independent review/version state; new upload tickets
must bind private randomized keys, employee, category, media type, size and version.

Reminders supplies the existing notification collection/inbox; audit_log supplies
security/history events; storage/client supplies private presigned S3 operations.
Existing access_control supplies PermissionEngine and owner-delegated permissions.
Employee routes currently use explicit owner/self checks; additional HR actions must
use the same backend engine and preserve owner-only review/no-self-approval.

## Incremental implementation plan

1. Inspection/report: this document; no data migration or production action.
2. Daily Update: default 200 (interpretation of “1–200”), choices 20/50/100/150/200,
   backend cap 200, URL-preserved paging/filtering and a shared loan-type catalog/UI.
3. Foundation: additive profile/experience/onboarding fields; preserve activation
   separately; owner-complete/account-only workflows with existing user provisioning,
   initial credentials, masters and permission matrix; self completion/review pages.
4. Documents: private upload intents, bounded type/size checks, existing scanner hook
   when available, authorized short-lived downloads, immutable version/review history,
   Aadhaar alternative PDF/images; process password transiently where supported and
   never echo/log it; review/reupload and completeness enforcement.
5. Edit requests: snapshot old/proposed allowed fields; version-checked owner decisions,
   no direct approved-profile overwrite; no employee delete action/API.
6. Attendance: project existing Daily Update/session sources using canonical identity,
   deduplicate families/events, retain history and reconciliation; configurable policy
   metadata without inventing payable hours, shifts, breaks or holidays.
7. Leave: explicitly configured types/policies, validated date ranges, overlapping
   request protection, owner decisions, self history/cancellation and attendance overlay.
8. Notifications/reports/navigation: existing inbox/audit, authorized paged HR reports
   and exports; all eleven requested sections backed by working features.
9. Validation: affected backend/frontend regressions, authorization/concurrency/storage
   tests, type/lint/build checks and local browser checks. Do not deploy or run a
   production migration. Record additive migration/rollback notes and infrastructure
   dependencies for each batch.

## Execution log

Batch 1 complete: inspected architecture and dependencies; identified reusable paths
and approval/storage gaps. No production records changed. Subsequent batch results
will be recorded here with concrete checks and remaining items.

Batch 2 implemented: bounded server pagination and URL-backed size selection;
LoanOptions extends existing BankOptions/StatusOptions and reuses the selector UI.
No hardcoded loan list, historical record rewrite or production migration. Startup
adds only the company/name active uniqueness and lookup indexes for the new catalog.
Existing records retain their string snapshots. Checks: 41 existing backend Daily
Update/bank tests passed, 2 new catalog/pagination tests passed, existing 55 frontend
Daily Update tests passed and the expanded selector suite passed 12 tests. Typecheck
passed. Production build verification is recorded after completion below.

Batch 2 production build passed (existing large-bundle warning only). New optional
Pagination.pageSizeOptions leaves unrelated list defaults unchanged. Loan catalog
uses this deployment's server-selected company key and existing staff option RBAC.

Batch 3 foundation implemented: canonical employee onboarding drafts, versioned
submission/review, experience and address validation, account-only versus inactive
owner-completed creation, completion banner and owner/self profile UI. Existing
employee backend regression initially passed all 26 tests; new focused foundation
checks passed all 3 tests. Verification status is separate from account activation.
No destructive migration. New profile fields live under employee.onboarding; legacy
records default to incomplete without being deactivated. Profile approval requires
all documents approved, and reviewed official data cannot use the old self-edit path.

Batch 4 implemented: private bounded upload intents, immutable final
object keys, actual PDF/image parsing, transient Aadhaar PDF decryption, combined
front/back Aadhaar versions, review/reupload/history/download authorization and
legacy upload delegation. PyMuPDF moved from dev to runtime dependencies. No malware
scanner exists in the inspected infrastructure; records explicitly say not_configured
and no clean-scan claim is made. Production needs the existing private S3 bucket/IAM,
PDF runtime dependency, optional external scanner and staging-object lifecycle rules.
No storage/network call was made by the automated tests; S3 is mocked.


## Completed implementation and verification

Batches 4?8 implemented: private document versions and owner decisions; official
profile changes through review requests; observed session attendance reports;
explicit leave policies, requests and calendar overlays; internal inbox events;
paged reports and authorized CSV exports; all eleven employee navigation sections.
Employee account-only creation retains access while onboarding is incomplete.
Owner-completed initial activation requires approved documents and a current
organization/role acknowledgement. Reverification does not reactivate an existing
account. The existing mobile, user identity and authentication architecture remain.

Employee state mutations append a durable embedded HR event outbox. The existing
worker retries inbox/audit delivery with event IDs and deterministic notification
IDs. Approved leave carries a separate retry marker until attendance projection
finishes; repeated projection adds no duplicate leave IDs or login sessions.
Historical documents remain immutable and accessible only through authorized,
short-lived download URLs. Legacy employee document upload endpoints now delegate
to the same validated intent flow.

Validation recorded on 2026-11-14:

- Latest combined employee baseline, HR profile/documents/edits/leave/attendance,
  and Daily loan catalog backend run: 40 passed. Two subsequent recovery/activation
  tests increased the focused HR profile suite to 5 passed.
- Focused leave suite including interrupted projection recovery: 4 passed.
- Earlier broad affected backend run: 104 passed (before final recovery refinements).
- Affected frontend suites: 75 passed. TypeScript typecheck passed.
- Strict mypy: all eight new HR backend modules/task passed.
- Production build passed; existing large JavaScript bundle warning remains.
- Local browser smoke check: passed real FastAPI with an isolated loopback MongoDB,
  employee and owner sessions, 1440px and 390px widths. Tested onboarding, leave,
  attendance, directory, onboarding report, edit requests, reports and settings;
  no browser runtime errors or horizontal page overflow. This is screen/navigation
  coverage, not a live S3 upload or a complete end-to-end approval journey.
- Browser artifacts: docs/screenshots/employee-hr-2026-11-14/results.json and PNGs.
  Synthetic test accounts only; no real customer/employee data.

## Additive data and rollout

No production deployment or production migration was executed. Use the existing
startup/index installation mechanism after deploying matching backend and frontend.
New collections: daily_loan_type_options, employee_upload_intents,
employee_leave_types and employee_hr_settings.
Employee documents gain onboarding, hr_documents, hr_edit_requests,
hr_leave_requests, hr_leave_reservations and hr_event_outbox. Existing employee
records default to incomplete profiles without being disabled or rewritten.
Existing string Loan Type snapshots remain valid, including archived labels.
Audit events gain metadata.hr_event_id and notification delivery snapshots; indexes
use partial filters to exclude legacy events without IDs. Retain original records.

Install runtime PyMuPDF from backend dependencies. Configure the existing private
S3 bucket, least-privilege PUT/GET/HEAD access, browser upload CORS and a lifecycle
rule for abandoned staging objects. Never expose public document ACLs. Keep the
existing worker running for HR inbox and attendance retries. No malware scanner
exists in the inspected infrastructure: metadata reports not_configured. No clean
scan or live storage verification is claimed. Add a scanner through a separately
verified infrastructure change when available.

Leave entitlements, shift windows, breaks, holidays and working weekdays are not
inferred. Owners configure explicit policies in Employee Settings. Calendar-day
limits are optional; attendance policy adjustment is shown only under explicitly
enabled rules and never calculates payroll. Unknown logout remains reconciliation
required rather than inventing an observed OUT time.

## Rollback

Back up employee collections and private objects before rollout. Roll back matching
application artifacts together. Do not delete employee onboarding/history/outbox,
leave decisions, audit events, new collections or private document objects during
rollback. Older application versions will not process HR outboxes or projection
markers; retain them for a subsequent forward deployment. The document upload
validation depends on the new backend: restrict old upload routes during rollback
rather than bypassing validation. Remove only newly added indexes if a verified
index incompatibility requires it; do not modify legacy indexes or records. No
historical loan status or invoice migration is part of this task.
