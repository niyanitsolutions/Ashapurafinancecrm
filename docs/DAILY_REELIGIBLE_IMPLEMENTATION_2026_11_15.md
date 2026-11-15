# Daily Follow-up sorting and Re-Eligible implementation

Date: 15 November 2026. Local implementation only; no production deployment or data migration executed.

## Architecture inspected

The existing FastAPI daily_operations router uses FollowUpInput/FollowUpUpdate, a
Motor aggregation for scoped lists/counts, optimistic record versions, embedded
history, and shared CSV/Excel export/import. Records remain in daily_follow_ups.
StatusOptions provides built-in options plus custom IDs and saved name snapshots.
React DailyOperationsPage uses URL-backed filters, TanStack Query, shared tables,
RecordForm, scoped actions and 30-second follow-up refresh. The existing Arq
check_daily_operations_notifications callback already runs every minute and at
startup, and already reconciles follow-up statuses. No new scheduler was introduced.
Existing user changes in voice/Airtel files, main.py and unrelated tests were left alone.

## Sorting and interpretation

The prompt's main priority table and its testing section contradict one another
for On Hold versus Disburse. This implementation follows the main priority table:

1. FOLLOW UP PENDING
2. NEXT FOLLOW UP
3. CASE ON HOLD WITH REASON
4. DISBURSE
5. Re-Eligible waiting for its date
6. REJECTED WITH REASON

Unrecognized custom statuses remain supported and sort after Re-Eligible and before
Rejected. Sorting uses a database-computed priority before skip/limit in the existing
aggregation. The existing requested sort is secondary (default date descending),
with record ID as a deterministic tie-breaker. Search, employee/other filters,
counts and export operate on the selected workflow dataset. Existing open-status
business-date projection remains in place.

Existing dropdown options are not reordered or renamed. Missing On Hold and
Re-Eligible options are added after the original four built-ins by additive,
idempotent setup. Active custom options with matching names are preserved rather
than rewritten. Custom status IDs remain intact; their saved name snapshots are
recognized for workflow and priority rules. Both Re-Eligible and Re Eligible names
are supported, case-insensitively.

## Record lifecycle and data

New fields on the existing record:

- reeligible_date: existing India-local calendar-date storage convention, serialized
  as YYYY-MM-DD by the API; optional for other statuses, required for Re-Eligible.
- reeligible_state: waiting, ready or inactive.
- reeligible_transitioned_at: processing timestamp retained for traceability.

Selecting Re-Eligible stages waiting. A date already due is handled by the next
worker execution, including missed runs and service restart catch-up. A ready row
stays ready during ordinary edits with the same status/date. Changing its date
reschedules it; changing its status returns it to the normal list immediately.
The current eligibility date is retained when another status omits it, and earlier
values are kept in history. Old records without eligibility metadata remain in the
normal list. Old Re-Eligible records without dates require a date when edited;
no dates are invented and no old records are rewritten in bulk.

Worker processing selects at most 500 due waiting records per minute, including
all overdue dates. Compare-and-set matches record ID, version, status, date and
waiting state. One atomic update changes state, increments version, and appends
history with before/after workflow state, eligibility date, system actor,
automatic indicator, India business date and actual processing timestamp.
Concurrent edits or processors cannot duplicate the same transition. No customer
record is copied, deleted, reassigned or recreated. Larger backlogs drain over
subsequent executions. Browser visibility updates on refresh or the existing poll.

## Frontend and permissions

Re-Eligible is beside Export, with a return-to-normal button in the ready view.
The same search, employee filters, more filters, pagination, CSV/Excel export,
Edit, History and owner-only Delete are reused. The ready table shows date, loan
type, bank/NBFC, customer name/number, remarks, eligibility date, employee and
actions. The date is also visible in the normal table. Add/Edit displays a required
Re-Eligible Date only for that status. Backend validation also covers custom IDs
and import preview. History labels automatic transitions. Export menus close on
selection to avoid covering mobile navigation.

All existing PermissionEngine checks, live linked-record ownership checks,
assignment restrictions and optimistic versions remain. Workflow is an enum
filter, not an authorization bypass. Automatic processing needs no logged-in user.
No new external message, customer notification or permission grant was added.

## Files changed for this task

- backend/app/features/daily_operations/reeligible.py (new workflow/priority helper)
- backend/app/features/daily_operations/schemas.py (date validation)
- backend/app/features/daily_operations/service.py (save lifecycle, list priority/filter, index)
- backend/app/features/daily_operations/router.py (workflow list/export filter)
- backend/app/features/daily_operations/status_options.py (additive missing options)
- backend/app/features/daily_operations/transfers.py (date export/import/preview)
- backend/app/worker/tasks/daily_operations.py (reuse existing scheduled callback)
- frontend/src/features/daily_operations/DailyOperationsPage.tsx
- frontend/src/features/daily_operations/RecordForm.tsx
- frontend/src/features/daily_operations/BankMultiSelect.test.tsx
- tests/api/test_daily_status_options.py (expanded additive setup expectation)
- tests/api/test_daily_reeligible.py (new controlled API/worker tests)
- tests/api/test_daily_reeligible_browser.py (new isolated real API/Mongo/browser tests)
- scripts/daily-reeligible-ui-check.mjs (new browser journey)
- docs/screenshots/daily-reeligible-2026-11-15/ (synthetic browser evidence)
- this report

## Validation

- Main backend Daily Operations, Simple Entry, Status Options and new Re-Eligible
  suite: 68 passed.
- Additional automation-hardening, multi-bank, loan-options, navigation and
  Re-Eligible run: 55 passed (the four Re-Eligible tests overlap the first run).
- Frontend Daily Operations suites: 60 passed across five files.
- Actual FastAPI + isolated loopback MongoDB browser journey: 1 passed; desktop
  1440px and mobile 390px, real create/edit/export/history APIs, required-date
  validation, future waiting list, actual scheduled callback invoked twice under a
  controlled India-midnight clock, ready-only list and same-ID follow-up resumption.
- Separate real MongoDB concurrent transition/index test: 1 passed.
- Strict mypy for the new workflow module and modified worker callback passed.
- Additional lifecycle/authorization and effective business-date sorting checks were
  added after those runs. A final combined backend rerun is recorded below.
- Python Ruff and targeted frontend ESLint passed. Frontend production build passed
  with the existing large-bundle advisory; the build also passed TypeScript checks.
- Browser evidence: docs/screenshots/daily-reeligible-2026-11-15/results.json and PNGs.
  No production account or production data was used.

This proves the backend scheduling callback under controlled conditions; it is not
a claim that a production worker has been deployed or observed over a real midnight.
Initial test runs identified and corrected a shared progress-filter regression and
an export menu overlay on mobile; final reruns are recorded above.

## Deployment and rollback

Deploy backend, worker and frontend together using the existing deployment process.
Run existing startup index installation; it adds a non-unique compound index on
is_deleted, reeligible_state and reeligible_date. Existing status setup adds only
missing options and does not reset custom colors/order or rewrite historical rows.
Keep the existing Arq worker and its every-minute/startup daily callback running.
No extra scheduler, credentials, collection or destructive migration is needed.
Until that worker is running, due records remain waiting in the normal list.

Back up as usual before rollout. Roll back matching artifacts together. Preserve
all new record fields, history and option rows; do not delete or recreate customer
records. Older frontend versions cannot display the new workflow view, so prefer a
forward fix if ready records already exist. Retaining the additive non-unique index
is safe. No production action was performed by this implementation.


## Final review

Priority is calculated after the existing effective-status date projection, so an
overdue NEXT FOLLOW UP is sorted with FOLLOW UP PENDING even before its existing
status-reconciliation job persists that change. A dedicated cross-page regression
covers this ordering. Additional lifecycle coverage confirms editing a ready row
keeps it ready, changing the eligibility date returns it to waiting, and a different
employee cannot open it or delete it.

No unresolved implementation failure is known. Production Arq operation remains a
deployment verification step. The frontend bundle-size advisory and existing
mongomock UTC deprecation warnings remain unrelated to this enhancement.


Final combined backend rerun: **121 passed**, including all eight affected API
suites and the two final lifecycle/effective-priority regressions. Separate browser
and real MongoDB concurrency checks both passed. Final frontend production build
and TypeScript checks passed; 60 frontend tests passed. Targeted ESLint, Python
Ruff checks and formatting (nine files), mypy for workflow/task and git diff
whitespace checks passed. Generated TypeScript build metadata was restored; local
browser development server was stopped. No commit, push or deployment was performed.
