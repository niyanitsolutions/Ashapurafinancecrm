# Unified assignment enhancement — 20 November 2026

## Assessment before implementation

Repository audit: `docs/PRD.md` and `REQUIREMENTS_TRACEABILITY.md` do not exist in this checkout. The available living requirements are `docs/REQUIREMENTS.md`; architecture decisions are `docs/decisions/DECISIONS.md`. Those, the previous unified implementation report, domain models, schema seed/apply scripts, services, RBAC, routes, workers and Leads table were inspected. Database scope remains one company per database (decision 001).

Customer.full_name is authoritative when established. Application.form_data uses schema-authored keys: the shipped Personal Loan field is `full_name_as_per_pan_card`; Business Loan uses `applicant_name_as_per_pan_card`. The earlier submitted-profile enrichment recognizes only exact `full_name`, so real seeded product answers are missed. Document Collection renders the placeholder profile unchanged and the loan half still performs customer lookups per ID. The fix must use explicit verified schema keys, preserve established identities/contact information and batch display resolution without changing old records on list reads.

AutoAssignment already has a shared atomic Mongo counter, record claim/lease, durable reservation/outbox and bounded worker recovery. It must be extended, not replaced. Draft lead-less loan Applications already appear in Document Collection, but assignment only runs on submission. Linked unassigned applications are excluded at that hook. Existing eligibility inspects raw role grants rather than effective permission decisions. Fresh Leads also hides the assigned employee column. These are local code findings; no production database or live intake was accessed.

Individual Lead assignment uses the leads:leads:assign permission and existing stage behavior; Application assignment is Owner-only and mirrors only loan-case employee ownership (insurance case assignees are Advisors). Bulk actions will preserve those boundaries and keep intake stages unchanged. Reassignment requires explicit confirmation. Selected records will be validated individually, fenced against concurrent assignment changes, audited and reported as assigned/skipped/failed. Only real Lead IDs enter existing delete actions; Application selections never enter the Lead Bin API.

Historical retry will be explicit, bounded and previewed. No deployment-time mass assignment, contact changes, deletion, authentication, Airtel, tenant or status-model changes are authorized.


## Implemented behavior

Document Collection resolves established Customer names first, then matching application answers using the verified `full_name`, `full_name_as_per_pan_card` and `applicant_name_as_per_pan_card` schema keys, then existing pending-profile names. Unavailable names display `Name unavailable`. Page-level batch queries replace per-customer queries. Customer/application user identity must match before profile/contact information is exposed. Reads do not mutate profiles. On submission, only placeholder names can be enriched; established names, mobile numbers and email addresses remain unchanged.

New unassigned Fresh Leads and draft Document Collection Applications now enter the existing shared round-robin engine at creation. The configured employee order, atomic counter, leases and durable outbox remain the assignment mechanism. Active employees are checked against effective module, child-stage and record-scope permissions, including denies. Empty/invalid pools do not consume a rotation slot. Disabled assignment leaves records unassigned. Explicit existing assignments are preserved. As requested, this supersedes the previous implicit employee-creator self-assignment rule for new records without an explicit assignee.

Fresh Leads now exposes Assigned To. Both tables support current-page selection, Clear Selection, employee selection, server preview and explicit confirmation. Reassignment requires a separate consent checkbox. Each record reports assigned/skipped/failed; failed/skipped selections remain available for review. Selection is disabled while data loads. Application IDs never reach Lead delete APIs. Existing styling, tabs and individual assignment behavior remain intact.

Bulk APIs are POST `/leads/bulk-assign` and `/applications/bulk-assign`; `/leads/bulk-assignees` lists eligible employees for the selected contexts. The existing Leads assign permission governs Fresh bulk assignment; Application bulk assignment remains Owner-only, matching individual assignment. Requests are bounded to 100 IDs. Preview metadata binds actor, selection, target employee and reassignment consent for ten minutes. Confirmation revalidates permissions, lifecycle, active employee, version and prior ownership. Compare-and-set writes and durable receipts/outbox prevent duplicate changes on replay. Partial failures remain visible rather than returning false success. Manual bulk does not advance the automatic rotation counter.

Application ownership synchronizes existing linked Lead and loan-case employee ownership through the existing outbox. It does not create another Lead or Application, move stages, or change insurance Advisor ownership. Concurrent mirror conflicts retain the saved assignment and pending outbox with an actionable result for review; they do not overwrite newer owners silently.

The Owner's unassigned intake queue now includes historical intake records. Both single-record and current-page retry first call POST `/leads/auto-assignment/bulk-retry` for preview, then require confirmation with the preview ID. Historical eligibility is enabled only for confirmed records. Deployment performs no backfill. Existing single-retry API remains compatible.

## Data and scope safety

Application has additive default-false `auto_assignment_eligible` and `assignment_pending` fields. New `assignment_previews` metadata has an expiry TTL index added through the existing index initializer. No destructive schema migration, business-record deletion, deduplication or automatic historical reassignment is required. Existing stable IDs and document references are retained. Single-company database scope remains unchanged.

Production data was not accessed or modified. Integrity assertions ran against owned disposable local Mongo databases: concurrent assignment and repeated confirmation preserved record counts, stable identities, contacts, document/version data and manual-bulk rotation position. Tests do not prove production data quality; the existing read-only preflight remains required before an approved rollout.

Authentication, sessions, Airtel/OTP, tenant architecture, employee management, attendance, Re-Eligible and customer registration were not changed. Existing Document Collection candidate limits (including the existing 1000-candidate cap) and profile-search behavior remain unchanged. Employee candidates are bounded to 1000. Unknown legacy name keys are not guessed; nested/co-applicant answers are not treated as customer identity.

## Validation

- Broad backend regression: **272 passed**, 26 warnings. Includes customer, leads, capture, document collection, assignment consistency and unified operations/submission suites.
- Final expanded affected backend regression: **69 passed**, 116 warnings, including real Mongo concurrency, unified operations/submission, daily operations and assignment consistency. This overlaps the broad suite; counts are not additive.
- Full frontend: **494 passed**, zero failed. Final affected frontend rerun is recorded below.
- Browser integration: **1 passed**, real local FastAPI + disposable Mongo and normal Owner login. Fresh/Application preview, confirmation, reassignment, names and cleared selection checked at **390, 768 and 1366 pixels**. Screenshots were inspected for mobile modal fit and desktop table rendering; no root horizontal overflow was detected. The existing table itself remains horizontally scrollable.
- Ruff: affected assignment/identity modules and new Python tests pass.
- TypeScript, ESLint, strict affected-file mypy and production build: final outcomes below. Existing lint fast-refresh warnings and bundle size advisory are reported, not hidden.

Browser evidence: [results](screenshots/assignment-enhancement-2026-11-20/results.json), [mobile preview](screenshots/assignment-enhancement-2026-11-20/applications-preview-390.png), [desktop assignment](screenshots/assignment-enhancement-2026-11-20/applications-assigned-1366.png). All screenshot data is synthetic. No real SMS, Meta API, production storage or other external delivery was exercised.

## Owner-approved deployment instructions (not executed)

These commands follow the repository's documented Ubuntu `/opt/afs-crm` layout and service names; the running server layout/environment was not inspected. Use the established backup procedure first. Supply the reviewed release commit and load the existing intended backend environment securely; do not print environment secrets. Stop if preflight reports duplicate keys or ambiguous links; do not merge/delete them automatically.

```bash
cd /opt/afs-crm
RELEASE_COMMIT='<reviewed-commit-sha>'
git status --short
# Proceed only with a clean checkout and an approved release.
git fetch origin
git checkout --detach "$RELEASE_COMMIT"
/opt/afs-crm/backend/.venv/bin/python /opt/afs-crm/scripts/audit_unified_crm.py
cd /opt/afs-crm/backend
.venv/bin/pip install .
cd /opt/afs-crm/frontend
npm ci
npm run build
sudo systemctl restart afs-crm-backend afs-crm-worker
sudo systemctl status afs-crm-backend afs-crm-worker --no-pager
sudo nginx -t && sudo systemctl reload nginx
```

Deploy backend and worker from the same release; serve the existing frontend `dist` directory using the established nginx configuration. No new dependency, queue or mass migration is introduced. Verify existing health checks and an approved synthetic/manual intake before enabling a previously disabled assignment pool. Review selected employees/order and use explicit preview/confirm for any historical retry. Rollback uses the previously approved commit/artifact and restarts both services; do not drop additive preview metadata or revert business assignments automatically.

## Changed files and preservation evidence

The complete source/test/report/evidence path inventory is [changed-files.txt](screenshots/assignment-enhancement-2026-11-20/changed-files.txt). [preservation.json](screenshots/assignment-enhancement-2026-11-20/preservation.json) records comparison to the clean starting commit. Historical evidence and generated TypeScript cache files are restored to that baseline. No production deployment or service restart was performed.


## Final verification outcomes

- Final affected frontend rerun: **23 tests, 6 files passed** after the single-record retry UI change.
- TypeScript `npm --prefix frontend run typecheck`: passed.
- Full frontend ESLint: **0 errors, 9 existing fast-refresh warnings in unchanged files**; no new changed-file warning.
- Final production build: passed, 451 modules; existing large-bundle advisory remains (main JS approximately 1.48 MB uncompressed).
- Ruff passed for the affected assignment/identity modules and new backend tests.
- Strict mypy's initial import-following run exposed five errors in unchanged field-validation/auth/employee/loan modules, plus one changed-file inference issue. The changed-file issue was corrected by separating input and validated candidate variable types. The final eight-file run uses `--follow-imports=silent` to report errors in the explicitly checked files; its result is recorded below. This is not a claim that the entire backend passes mypy.

- Final strict affected-file mypy (`--follow-imports=silent`): **success, 8 source files**.
- After the type-only correction, submitted-identity regression: **1 passed**; Ruff and `git diff --check` pass.
- Local frontend preview was stopped after validation. The pre-existing local Mongo service was left running.
