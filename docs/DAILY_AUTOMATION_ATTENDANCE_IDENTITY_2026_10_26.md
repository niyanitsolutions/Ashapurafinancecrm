# Daily follow-up, attendance and identity hardening ? 26 October 2026

## Executive summary and verdict

IMPLEMENTATION COMPLETE ? READY FOR OWNER RELEASE REVIEW.

The existing FastAPI/Motor/MongoDB and React implementation was extended. Follow-ups use server-derived business-date status, attendance uses one employee/date summary over retained authentication families, access and refresh requests enforce ten-minute inactivity, and customer/lead creation uses normalized identity checks with an explicit uniqueness migration.

This is **not a production-readiness certification**. Real MongoDB acceptance, production-compatible data inspection, restore rehearsal, advisory scanning and live worker verification remain release gates. No production connection, migration, deployment, restart or infrastructure change was performed. The workspace was clean at inspection; no existing user changes were discarded.

## Follow-up behavior

- The configured `Settings.timezone` and existing business-calendar helpers are authoritative (default Asia/Kolkata). Stored instants remain UTC.
- An open case due on or before the business date displays FOLLOW UP PENDING; a later due date displays NEXT FOLLOW UP. The list pipeline derives status **before** status filters, counts, sorting and pagination. List serialization uses the same captured time as the pipeline.
- Existing exports call the same list service. Detail/create/edit responses also derive the effective status. DISBURSE and REJECTED WITH REASON remain terminal under date automation.
- The existing authorized, version-checked edit workflow explicitly reopens a terminal record. Active edits require a date and next action; rejected edits require a reason; disbursement still requires verified canonical loan data. No missing-date policy was invented: new active records must have a date; legacy undated rows retain their stored status pending review.
- The existing ARQ daily-operations job now runs every minute. It reconciles up to 500 changed follow-ups per run, using status/date/version compare-and-set and an atomic embedded history event. Repeated/concurrent runs do not append the same transition. A backlog delays persisted audit reconciliation, but cannot delay effective API status.
- History records `source=manual` or `source=automatic`, actor (null for automation), timestamp and before/after values. Existing remarks/history and notification deduplication remain intact.

| Status | Full-row treatment | Default text/background contrast |
|---|---|---|
| FOLLOW UP PENDING | red-50 / red-950 | 14.76:1 |
| NEXT FOLLOW UP | blue-50 / blue-950 | 13.50:1 |
| DISBURSE | green-50 / green-950 | 14.24:1 |
| REJECTED WITH REASON | yellow-50 / yellow-950 | 14.09:1 |

Ratios were calculated using the WCAG relative-luminance formula and Tailwind default colors. Hover/focus use the corresponding 100 background; sticky action cells inherit the row color. Status text remains visible. DOM tests verify each entire row class. Live browser visual/keyboard acceptance was NOT RUN.

## Attendance schema and duration

`attendance_days` contains a deterministic `_id=user_id:YYYY-MM-DD`, canonical authenticated `user_id`, business `date` and creation timestamp. A unique `(user_id,date)` index supplies additional database enforcement. Existing employee profiles uniquely relate to users; browser-supplied employee names/IDs cannot create attendance identities.

The existing `sessions` collection remains the authentication and session-history authority. One original login family can have several refresh-token rows; rotation descendants keep the original login timestamp and family ID. New rows carry `attendance_day_id`; no refresh-token row is counted as another human login. Existing raw rows are retained. Session end reasons distinguish manual_logout, inactivity_timeout, session_revoked and administrative_revocation. Existing owner corrections remain separate, versioned, audited records and show administrative_correction. Unknown historical reasons display legacy_unspecified.

Daily summary fields are projections over those retained records: first original login, latest completed logout occurring on that date, active status, and accumulated exact seconds. The history action shows each family, its original times, status, credited seconds and end reason; permitted Owners can correct individual sessions. Employees remain scoped to their own permitted history. The existing Owner-only correction policy was preserved; no new manager role or visibility was invented.

Durations are the union of valid session intervals, clipped to business-day boundaries. Gaps do not count; overlapping tabs/devices count once. Completed intervals plus active elapsed time are derived at the server snapshot, never added repeatedly to a counter. Negative intervals contribute zero. Rounding occurs after accumulation to whole seconds; the UI displays whole hours/minutes and refreshes every 30 seconds. The 60 + 30 + 60 minute example yields 9000 seconds / 2h 30m. Day-boundary and daylight-saving instant calculations are covered by tests. An ongoing family retains its true original login in history; its daily credited duration is clipped, without inventing another login/logout timestamp at midnight.

Corrections that move time to another date create the corresponding summary keys and remain discoverable by corrected date. Days whose intervals were all hidden or moved retain an explicit no_visible_sessions summary with zero credited duration. Existing per-family visibility markers still exclude hidden history without deleting authentication records. Daily exports now contain daily-summary IDs and totals; correction-import templates continue to address **family IDs**, and are intentionally distinct from summary exports.

The summary list paginates before fetching history, batches family/correction reads and limits a page to 10,000 families. It requests narrower filters if that bound is exceeded. Real-volume query plans and latency remain unverified.

## Authentication, inactivity and retries

Access JWTs now carry the login family as `sid`. Protected dependencies verify that the family belongs to the subject, has an active unexpired row and has no terminal revoked/logged-out row. Old access tokens without `sid` require refresh or reauthentication. Refresh rotation preserves inactivity time and uses an atomic claim; token refresh and background reads never count as human activity. Terminal family checks also reject a child inserted during a revocation race.

`POST /auth/activity` is authenticated. The browser sends it at most once per 30 seconds after trusted, visible interaction, and on explicit Continue Session. There is no repeating idle heartbeat. Tabs share family activity over BroadcastChannel. Before a browser idle timer logs out, it performs a read-only server check so an active sibling tab is not expired. A stale client timeout request cannot terminate an active family. Separate devices have separate families and inactivity clocks.

The authoritative end for inactivity is last accepted server activity + ten minutes. A request at/after that boundary is rejected and the stale row finalized with compare-and-set. The worker also finalizes up to 500 expired rows per minute; worker downtime cannot grant an expired token access. The cutoff includes the inactivity allowance and is **not proof of the precise time work stopped**. Browser close, sleep, missed heartbeat and network loss require no unload signal: they stop accepted activity and reach that cutoff. The worker also scrubs up to 500 encrypted login receipts older than two minutes per run.

A UUID `Idempotency-Key` on login deduplicates concurrent/retried submissions after normal password/geofence validation. The key is hashed with the authenticated user identity; a partial unique session index elects one insert. Its response receipt is encrypted with the existing encryption facility and replayable for two minutes only while the original session is active and unrotated. The frontend supplies a new key for each login attempt. API clients must reuse the same key when retrying that attempt; a login without a key represents a new login. No password or plaintext bearer token is logged/stored in the receipt. Rotation/revocation/expiry prevents receipt reuse.

## Duplicate policy and workflow integration

`shared/customer_identity.py` provides server normalization. India remains the existing account/lead country policy: ten-digit national, +91, 0091 and 91-prefixed forms normalize to the same ten digits; supported separators are removed; arbitrary letters and substring matches are rejected. Name matching uses Unicode NFKC, case folding, punctuation removal and collapsed spaces.

All nondeleted lead matches block another lead, **including rejected leads**. Authorized callers receive the existing ID/code/link and a material-name-conflict flag. Unauthorized callers receive a generic conflict without record references. Same normalized name with another phone remains allowed and flags up to 20 visible candidates for review. The normalized name field is indexed and backfilled by the migration. No automatic identity merging occurs.

Manual leads, referral creation, bulk lead imports and website/Meta intake continue through the shared LeadService. Capture and insurance manual schemas now use the shared normalizer. Existing customer profiles also block a new lead for that phone; staff should create an application for the existing customer. Profile creation reuses the canonical account/customer, handles duplicate-key races safely, and retains existing lead-to-customer linking. Manual insurance creation reuses an existing customer and flags differing customer names; concurrent account creation returns a safe conflict rather than a duplicate account. Application uniqueness was **not** imposed: multiple applications remain supported.

Daily Follow-up entries never create a customer or lead. A typed phone/name matching a visible loan lead links through its authorized canonical lead workflow; materially differing names require review. Existing customers can be linked through their authorized loan case, now selectable alongside leads. If a typed known customer requires a loan link, the server asks for that link. Standalone manual operational rows, including the existing international-phone policy, remain operational records rather than uncontrolled customer creation.

## Constraints, migration and legacy records

`scripts/migrate_daily_attendance_identity.py` requires an explicit URI and database. Without `--apply` it only reports noncanonical identities, normalized duplicate groups and ambiguous families, using IDs rather than phone/name/token values. It inspects all nondeleted leads/customers, all family histories, missing end/activity information and inconsistent family login/user identities. It does not choose a duplicate survivor or infer missing original timestamps.

Apply refuses the entire operation when the report contains unresolved conflicts. On a clean target it adds `identity_mobile_unique` partial unique indexes to `leads.mobile` and `customers.mobile` for nondeleted records, across all stages. It keeps the old active-only lead index, adds normalized-name metadata, creates attendance/auth indexes, attaches canonical users to existing correction records and backfills daily keys from original families/corrections. MongoDB 7 is the repository deployment baseline. No application collection receives customer-level uniqueness.

Additional indexes cover active session/activity cutoff, user/login, login timestamp, unique string-valued login-request key, employee/date summary and user/correction time ranges. The migration reuses the new additive auth-index installer, without invoking unrelated historical index-removal code.

Legacy-data findings: synthetic normalized conflicts and ambiguous-data refusal were verified. **No live-data findings are claimed.** Historical production-compatible data inspection is BLOCKED until the owner provides an authorized isolated copy. Records marked deleted remain retained under the existing soft-delete policy. The repository is currently single-company and has no tenant_id in BaseDocument; existing role/ownership isolation is preserved, and multi-tenant certification is NOT RUN.

## Verification evidence

Commands below ran from the repository root unless marked frontend. Backend runs used `$env:PYTHONPATH='backend'; $env:DEBUG='false'` and `backend/.venv/Scripts/python.exe`; the explicit configuration is `-c backend/pyproject.toml`. DEBUG overrides an incompatible host environment value, and the configuration enables the repository's async test mode.

| Check | Result | Evidence |
|---|---|---|
| Broad backend regression | PASS | 407 passed, 108 warnings; command below |
| Latest capture/import/manual-insurance/daily regression | PASS | 127 passed, 108 warnings; command below |
| Final date/migration/attendance regression | PASS | 63 passed, 90 warnings; hardening + daily_operations |
| Final authentication/retry/history regression | PASS | 53 passed; hardening + auth after the last race/history fixes |
| Full frontend suite | PASS | `npm test -- --maxWorkers=2`: 391 passed in 77 files |
| Frontend production build and typing | PASS | `npm run build`; initial `npm run typecheck` also passed |
| Frontend lint | PASS | `npm run lint`: zero errors, 10 existing warnings |
| Backend lint | PASS | Ruff over backend/app, migration and new hardening tests |
| New-module typing | PASS | mypy over session_lifecycle, attendance, follow_status, customer_identity and migration |
| Full backend typing | FAIL (baseline) | 116 errors in 11 files, 394 checked; clean HEAD shadow-file comparison produced the identical 116 errors |
| New Python files formatting | PASS | Ruff format check on the new modules, migration and hardening tests |
| Dependency compatibility | PASS | `python -m pip check`: no broken requirements |
| Dependency advisory scan | BLOCKED | `npm audit --json`: registry HTTPS connection denied with EACCES; Python external advisory scan NOT RUN |
| Real MongoDB migration/concurrency acceptance | BLOCKED | Docker CLI exists, but local docker_engine daemon/pipe is unavailable; tests use mongomock_motor/fakeredis |
| Static row contrast and status labels | PASS | Ratios above and four DOM row mappings |
| Real browser/keyboard accessibility review | NOT RUN | No screenshot/browser acceptance claimed |
| Load, failover, backup/restore rehearsal | NOT RUN | Requires isolated realistic infrastructure/data |
| Live worker schedule/monitoring/release checks | NOT RUN | No infrastructure change authorized |
| Full unrelated backend test suite | NOT RUN | Relevant suites were selected explicitly; no claim that all repository backend tests ran |
| Whitespace/diff validation | PASS | `git diff --check` |

Broad backend command (pytest arguments):

```text
-m pytest -c backend/pyproject.toml tests/api/test_daily_automation_hardening.py tests/api/test_daily_operations.py tests/api/test_daily_simple_entry.py tests/api/test_daily_update_navigation.py tests/api/test_auth.py tests/api/test_leads.py tests/api/test_customer.py tests/api/test_bulk_import.py tests/api/test_lead_capture.py tests/api/test_reporting.py tests/api/test_dashboard.py tests/api/test_timezone.py tests/api/test_employee.py tests/api/test_insurance_manual_lead.py tests/api/test_insurance_policy_leads.py tests/api/test_loan_management_visibility.py -q -n 4 --disable-warnings --maxfail=10
```

Final authentication command: `-m pytest -c backend/pyproject.toml tests/api/test_daily_automation_hardening.py tests/api/test_auth.py -q -n 4 --disable-warnings --maxfail=3`.

Final date/attendance command: `-m pytest -c backend/pyproject.toml tests/api/test_daily_automation_hardening.py tests/api/test_daily_operations.py -q -n 4 --disable-warnings --maxfail=3`.

Latest workflow regression command:

```text
-m pytest -c backend/pyproject.toml tests/api/test_daily_automation_hardening.py tests/api/test_daily_operations.py tests/api/test_daily_simple_entry.py tests/api/test_lead_capture.py tests/api/test_insurance_manual_lead.py -q -n 4 --disable-warnings --maxfail=3
```

An earlier frontend run with four workers timed out one extended insurance-form test; that file passed all eight tests alone, and the subsequent full two-worker run passed without changing its assertions or timeout. Existing tests permitting rejected-lead recreation and expecting family-level attendance rows were updated to assert the explicitly requested replacement policy. Initial backend invocation setup errors were corrected by specifying DEBUG and the repository pytest configuration; those invocations were not treated as test passes. Existing jsdom canvas warnings, test error-path logs and the frontend bundle-size warning remain visible.

## Release, backup and recovery

1. Obtain owner authorization for release actions. Provision an isolated MongoDB 7 replica-set copy and Redis/ARQ worker matching deployment, with synthetic or approved protected data. Verify server clock synchronization and configured business timezone.
2. Back up the target collections and indexes with the repository backup procedure, including sessions, corrections, identity data and encryption-key recovery material. Rehearse restoring into a separate database; confirm backup confidentiality and no secrets in report output.
3. With writes paused on the isolated target, run `python scripts/migrate_daily_attendance_identity.py --uri <isolated-uri> --database <isolated-db>` and save the report securely. Resolve flagged identities/ambiguous history through owner-reviewed remediation. Never delete or merge arbitrarily.
4. Re-run the report, then add `--apply` against that same isolated target. Verify unique indexes, preserved raw session counts/timestamps, corrected-date summaries, repeat execution, concurrent logins/creates, revoked-access rejection, midnight/DST clipping, legitimate repeated applications and scoped imports/exports. Rerun after a failure: writes/index creation are additive/idempotent, but a failed multi-step run can leave earlier additive steps installed.
5. Validate worker one-minute cadence and backlog drainage, duplicate notification suppression, database query plans and memory/latency under realistic load. Check orphaned token families and active/summary reconciliation after simulated failures. Verify supported browser tab synchronization and stale-tab handling.
6. Complete advisory scans on a network-enabled approved environment and decide disposition of baseline typing errors. Rehearse the deployment and recovery on the isolated copy. Only then request explicit owner authorization for production migration/deployment and execute the approved release process.

Prefer forward recovery: retain new collections/fields/indexes and rerun the idempotent migration after remediation. A code rollback must keep authentication family enforcement coherent across API/frontend versions; do not silently restore weaker revocation behavior. Existing raw sessions/corrections/identity records were not deleted, so the previous view can be reconstructed from the backup/source records. Retain strict identity indexes on rollback unless the owner explicitly approves returning to the older duplicate policy. Any targeted removal of derived fields/collections/indexes must be based on the captured pre-release inventory, after stopping writers and with owner approval; no destructive rollback script is provided.

## Outstanding release gates

Real-database atomicity and index behavior, an authorized legacy-data report, realistic performance/failover, backup restoration, advisory scans, browser acceptance and deployed worker health remain unverified. Index installation/backfill must complete before enabling the new view on historical data. Full backend typing remains a pre-existing repository failure and requires an owner disposition. These gates prevent a PRODUCTION READY verdict; they do not authorize any production action.

## Actual files changed

- `backend/app/features/auth/dependencies.py`
- `backend/app/features/auth/indexes.py`
- `backend/app/features/auth/models.py`
- `backend/app/features/auth/repository.py`
- `backend/app/features/auth/router.py`
- `backend/app/features/auth/service.py`
- `backend/app/features/auth/session_lifecycle.py`
- `backend/app/features/customer/schemas.py`
- `backend/app/features/customer/service.py`
- `backend/app/features/daily_operations/attendance.py`
- `backend/app/features/daily_operations/follow_status.py`
- `backend/app/features/daily_operations/router.py`
- `backend/app/features/daily_operations/schemas.py`
- `backend/app/features/daily_operations/service.py`
- `backend/app/features/daily_operations/views.py`
- `backend/app/features/employee/service.py`
- `backend/app/features/insurance_management/schemas.py`
- `backend/app/features/lead_capture/parsers.py`
- `backend/app/features/leads/indexes.py`
- `backend/app/features/leads/models.py`
- `backend/app/features/leads/repository.py`
- `backend/app/features/leads/schemas.py`
- `backend/app/features/leads/service.py`
- `backend/app/middleware/auth.py`
- `backend/app/shared/customer_identity.py`
- `backend/app/worker/tasks/daily_operations.py`
- `backend/app/worker/worker_settings.py`
- `docs/DAILY_AUTOMATION_ATTENDANCE_IDENTITY_2026_10_26.md`
- `frontend/src/features/auth/api.ts`
- `frontend/src/features/auth/components/SessionGuard.tsx`
- `frontend/src/features/auth/useIdleTimeout.test.ts`
- `frontend/src/features/auth/useIdleTimeout.ts`
- `frontend/src/features/daily_operations/DailyOperations.test.tsx`
- `frontend/src/features/daily_operations/DailyOperationsPage.tsx`
- `frontend/src/features/daily_operations/RecordForm.tsx`
- `frontend/src/features/leads/pages/CreateLeadPage.tsx`
- `scripts/migrate_daily_attendance_identity.py`
- `tests/api/test_daily_automation_hardening.py`
- `tests/api/test_daily_operations.py`
- `tests/api/test_lead_capture.py`
- `tests/api/test_leads.py`
