# Daily Update calendar and color corrections - 26 October 2026

## Verdict

**READY FOR OWNER RELEASE REVIEW.** Implementation and available automated/browser checks pass. This is not a PRODUCTION READY declaration: real MongoDB integration, representative-data acceptance, backup restoration and live release checks remain unverified. No production connection, repair, deployment, infrastructure change or service restart was performed.

The repository was clean when this correction began. Existing navigation, tabs, follow-up effective-status rules, customer/lead duplicate policy, authentication-family model, permission rules and source history were retained.

## Root causes

1. Daily duration already clipped intervals at midnight, but summary LOGIN TIME still selected the original family login. An overnight family therefore showed yesterday's timestamp in today's row.
2. History exposed the original authentication times without separately identifying the credited daily segment. This made a correctly clipped duration difficult to reconcile visually.
3. No canonical month parameter/default existed for the attendance API or visible filter.
4. Chrome testing exposed a rapid-filter race: Month could clone stale router parameters immediately after Employee name changed. The selected employee was then lost. Pending filter parameters are now retained until router transitions commit, including clear and pagination actions.
5. Existing palette level 50 was visibly too pale. Strengthening it also required preserving readable action-button text and focus outlines.
6. An interrupted timeout finalization could occur before a next-day summary was ensured. Required day keys are now ensured before the terminal compare-and-set write.

## Colors and accessibility

| Effective status | Row/cell background | Hover/focus | Foreground | Default / focus contrast |
|---|---|---|---|---|
| FOLLOW UP PENDING | #FCA5A5 | #F87171 | #450A0A | 8.51 / 5.84 |
| NEXT FOLLOW UP | #93C5FD | #60A5FA | #172554 | 8.15 / 5.78 |
| DISBURSE | #86EFAC | #4ADE80 | #052E16 | 10.62 / 8.55 |
| REJECTED WITH REASON | #FDE047 | #FACC15 | #422006 | 11.06 / 9.52 |

Ratios use the WCAG relative-luminance formula. Every direct table cell inherits the row background, including sticky actions. Ghost action text inherits the readable foreground, focus outlines are black, and destructive-button hover retains its white background. Status text remains visible. The existing server effective status and query invalidation/polling update the color without a browser refresh; terminal outcomes are unchanged.

Real Chrome checked all four cell backgrounds and text/action contrast >=4.5, keyboard focus, status polling, desktop and mobile layouts. There was no page-level horizontal overflow at 390px; wide tables retain their own horizontal scrolling. Navigation and all five Daily Update tabs were preserved.

## Calendar-day attendance model

The current repository standard, Settings.timezone default and timezone-only lines in .env.development/.local/.staging/.production/.example identify Asia/Kolkata. No timezone setting was changed, and no running production configuration was queried. The backend continues to use the configured business-zone helpers, stores source instants in UTC, and returns business_timezone and as_of metadata. India remains the approved frontend display convention documented in docs/TIMEZONE.md.

Each day is a half-open interval **[local midnight, next local midnight)**. This represents the whole local calendar day without subtracting a millisecond or losing the boundary instant. Each midnight is independently converted to UTC, including DST-aware configured zones. The existing attendance_days collection remains the only daily summary store; existing sessions and session_corrections remain the source authority.

Uniqueness remains `(user_id,date)` plus deterministic `_id=user_id:YYYY-MM-DD`, scoped to the current company's MongoDB database. This repository has no tenant_id field or multi-company shared-collection implementation; no new tenant model or visibility expansion was invented. Existing canonical employee/user relationships and Employee self-scope remain enforced. A new `(date DESC,user_id)` index supports company-wide monthly scans, while the existing user/date unique index supports employee queries.

Summary LOGIN TIME now uses the earliest **segment_start_at** for that date. A carried-in session begins its next day's attendance at midnight, never at yesterday's authentication login. Original authentication/corrected session times stay intact in history. LOGOUT TIME uses the latest actual finalized end occurring within the day; a midnight segment boundary is not represented as a fictional authentication logout.

History adds segment_start_at, segment_end_at, segment_status and continues_from_previous_day alongside its existing original login/logout, reason, correction version and credited duration. The UI labels Daily segment separately from Actual login / Actual logout. Corrections still edit the real family times, retain their audit history and require the existing Owner authorization/version checks.

For 26 Oct 23:30 -> 27 Oct 00:30:

- 26 Oct: LOGIN TIME 23:30, segment [23:30,24:00), 1800 seconds, day_completed. No fictional actual logout is inserted.
- 27 Oct: LOGIN TIME 00:00, segment [00:00,00:30), LOGOUT TIME 00:30, 1800 seconds.
- One authentication family is retained. No login, refresh or revocation is caused by midnight.

An end exactly at midnight does not create an extra following-day attendance key. A legitimate zero-elapsed login at midnight still has its own day's row. Active status overrides completed/expired sibling sessions on the current day; completed prior-day carry-in segments show day_completed, and a latest inactivity end shows timed_out. Historical actual times remain available for audit.

## Duration and inactivity

Eligible duration remains the union of authoritative intervals per employee/day, so gaps are excluded and overlapping devices are counted once. Daily segments and the union retain fractional seconds instead of truncating each side of midnight; whole-second results remain integers for compatibility. Display remains whole hours/minutes. Exact source timestamps are retained, negative intervals are excluded and a 0.5s + 0.5s split still accounts for 1s. The 60m + 30m + 60m example remains 9000s / 2h 30m. Active values continue to refresh every 30 seconds without background polling extending inactivity.

The existing ten-minute policy was preserved: last accepted authorized activity + ten minutes is the eligible timeout end. The grace period counts toward eligible session time, as in the prior implementation/report. It is not proof of productive work or an exact observation of browser closure. Owner payroll-policy acceptance is not inferred from technical verification.

Trusted visible interactions, explicit activity requests, passive refresh/poll exclusion, family-bound access checks, manual logout, refresh reuse/revocation and tab synchronization remain unchanged. Timeout now ensures all day keys spanned by the last known activity and its cutoff before its idempotent terminal write; a retry cannot append another terminal event. This bounded range is at most ten minutes. Complete historical gaps are handled by reconciliation rather than replaying years of history on every authenticated request.

New summary creation timestamps reflect the actual server write time rather than the historical segment time. A uniqueness collision reuses the actual existing employee/date row, including a legacy ID, instead of fabricating a relationship to a missing canonical key.

## Month filter and export

- A visible native Month input appears on Employee Login & Logout, beside the existing employee control and More filters. Other tabs do not acquire a Month control or receive attendance month parameters.
- The backend defaults an omitted month to the current configured business month and returns the effective YYYY-MM value; the frontend does not guess it from the viewer's browser clock.
- Explicit month selection persists in the URL through navigation/reload and resets pagination while preserving Employee name and other filters. Clearing filters returns to the server default.
- Validation rejects malformed/out-of-range months. Month start is inclusive and next-month start exclusive on canonical summary date strings. Existing From/To constraints intersect that month; they cannot widen it.
- Pagination, counts and CSV/XLSX export call the same scoped backend service. Employee/user parameters cannot broaden an Employee's self-scope. Empty results return the effective month/timezone metadata.
- Existing export permissions and the 500-row export bound remain. Narrow by employee/date if a company-wide month exceeds that bound.

## Attendance-only historical reconciliation

Use `scripts/reconcile_attendance_calendar_days.py`, not the previous combined identity migration, for this targeted release. It requires an explicit URI/database and defaults to read-only dry run. It never connects implicitly using a production .env target.

The report includes before/after counts for summaries, raw sessions and corrections; expected source days, projected summary count, planned/actual inserts; overnight/carry-in and stale-active families; missing logouts; duplicate token events; stale stored date/duration fields; unattributed summaries; and bounded ID-only findings/issues. No phone numbers, names, raw tokens or token IDs are printed. Detail samples are capped at 200; counts cover the full scan, and review can proceed in batches with another dry run.

Original session rows and manual correction timestamps, reasons, versions and history are never overwritten or deleted. Missing derived correction user bindings are filled only from a single canonical family, using a version/time compare-and-set and an atomic reconciliation_history event. Existing nonempty contradictory bindings block apply. Repeating the process does not append duplicate metadata events. Hidden-session visibility markers are respected when attributing days. Existing obsolete derived login/duration fields are identified and retained; the corrected projection ignores them. Unattributed metadata is retained for review. The process reuses the same eligible session window and day boundaries as runtime, and only materializes missing metadata keys/additive indexes when sources are unambiguous. It is idempotent. Ambiguous identities, conflicting family timestamps, missing finalized ends, orphan corrections, duplicate summaries/events and excessive source spans block apply with an explicit BLOCKED report/exit status 2. It never chooses which duplicate to delete or merges history. Source spans over 3660 dates require manual review as an operational bound, not a payroll policy.

Synthetic dry-run/apply/repeat tests preserve raw documents/corrections exactly, recover two overnight keys, exercise duplicate/ambiguous refusal and report stale stored fields. Real historical data was not accessed; no findings about production records are claimed.

## Verification

All backend test invocations used `$env:PYTHONPATH='backend'; $env:DEBUG='false'` and `backend/.venv/Scripts/python.exe`, with explicit `-c backend/pyproject.toml`. The DEBUG override is needed because this host otherwise supplies an incompatible value. Frontend browser tooling uses the existing cached Node 22 runtime; system Node 18 cannot run the installed Playwright version.

| Check | Status | Actual evidence |
|---|---|---|
| Combined calendar, prior hardening, Daily Update and auth suites | PASS | 139 tests, 108 warnings |
| Additional CRM/duplicate/import/dashboard/report regression | PASS | 258 tests |
| Full frontend suite | PASS | 394 tests in 77 files |
| Final targeted frontend after contrast changes | PASS | 35 Daily Operations tests |
| Final new calendar/reconciliation checks | PASS | 33 passed after final reconciliation guards; 63 passed in final calendar + previous-hardening run |
| Chrome Owner/Employee at 1440px and 390px | PASS | Four scenarios, real components, intercepted synthetic API; results.json and eight PNGs plus filtered CSV fixtures |
| Frontend TypeScript / production build | PASS | tsc -b and vite build; existing large-bundle warning remains |
| Frontend ESLint | PASS | Zero errors, 10 existing warnings |
| Backend Ruff | PASS | backend/app, new reconciliation CLI and new tests |
| Changed/new backend module typing | PASS | Five affected modules/CLI passed strict mypy; no new typing errors |
| Full backend mypy | FAIL - pre-existing | Current 116 errors in 11 files / 396 sources; clean-HEAD shadow comparison 116 in 11 / 394 sources; no new error messages |
| New Python formatting | PASS | Ruff formatting/checks on calendar, reconciliation, attendance, lifecycle, CLI and new tests |
| Real MongoDB integration / physical index acceptance | BLOCKED | Docker CLI exists; default local docker_engine pipe/daemon is absent, config access also reports denied. No real-database success is claimed |
| Production-compatible historical reconciliation | BLOCKED | Requires an Owner-authorized isolated copy and real MongoDB |
| Backup / restore rehearsal, failover and production load | NOT RUN | Requires isolated operational infrastructure and representative data |
| Production deployment / live worker validation | NOT RUN | Not authorized and not attempted |
| Whitespace / unrelated-work preservation | PASS | git diff --check; initial workspace clean; generated build cache restored |

Combined backend arguments:

```text
-m pytest -c backend/pyproject.toml tests/api/test_attendance_calendar_release.py tests/api/test_daily_automation_hardening.py tests/api/test_daily_operations.py tests/api/test_daily_simple_entry.py tests/api/test_daily_update_navigation.py tests/api/test_auth.py -q -n 4 --disable-warnings --maxfail=4 --tb=short
```

Final focused backend arguments: `-m pytest -c backend/pyproject.toml tests/api/test_attendance_calendar_release.py tests/api/test_daily_automation_hardening.py -q -n 4 --disable-warnings --maxfail=2 --tb=short` (63 passed). After final source-validation guards, `-m pytest -c backend/pyproject.toml tests/api/test_attendance_calendar_release.py -q --disable-warnings --maxfail=2 --tb=short` passed all 33 tests; strict mypy on reconciliation and its CLI also passed. The final Ruff format check passed all six checked Python files.

Additional regression arguments:

```text
-m pytest -c backend/pyproject.toml tests/api/test_leads.py tests/api/test_customer.py tests/api/test_bulk_import.py tests/api/test_lead_capture.py tests/api/test_reporting.py tests/api/test_dashboard.py tests/api/test_timezone.py tests/api/test_insurance_manual_lead.py tests/api/test_loan_management_visibility.py -q -n 4 --disable-warnings --maxfail=4 --tb=short
```

Frontend commands from frontend/: cached `node_modules/.cache/voice-node22/node.exe` with `node_modules/vitest/vitest.mjs run --maxWorkers=2 --reporter=dot`, `node_modules/typescript/bin/tsc -b`, `node_modules/vite/bin/vite.js build`, and `node_modules/eslint/bin/eslint.js .`. Browser command from root: `frontend/node_modules/.cache/voice-node22/node.exe scripts/attendance-calendar-ui-check.mjs`, using an isolated Vite server on 127.0.0.1:5187. External browser requests were aborted. The owned local preview was stopped after verification.

Early regression execution caught and fixed forwarding month to Loan Progress. New API fixtures were corrected to satisfy real Employee required/unique fields and include the authenticated fixture's actual attendance day in expected counts. Browser checks exposed and verified the rapid-filter fix; focus assertions account for the Employee's permitted single action and wait for the CSS transition. No assertions, permissions, source history or existing timeouts were removed to force a pass. Existing jsdom canvas and test error-path logs remain visible.

## Release acceptance gates

| Gate | Status |
|---|---|
| Implementation complete | PASS |
| Relevant available automated tests | PASS |
| Actual database integration | BLOCKED |
| Representative reconciliation / migration | BLOCKED |
| Database uniqueness/index definitions and mock behavior | PASS; real MongoDB BLOCKED |
| Timezone / midnight / precise duration logic | PASS |
| Existing timeout / Owner and Employee isolation | PASS in isolated tests; live acceptance NOT RUN |
| Relevant CRM regression | PASS |
| Backup/recovery rehearsal | NOT RUN |
| Configuration and release/recovery instructions | PASS - documented |
| Owner review and production authorization | BLOCKED until Owner release decision |

## Safe migration, deployment and recovery instructions

1. Obtain Owner authorization for any production actions. First use an isolated MongoDB 7 copy and Redis/worker setup matching deployment. Confirm actual runtime Settings.timezone is Asia/Kolkata for this company and clocks are synchronized. Do not change the timezone to conceal historical errors.
2. Back up sessions, session_corrections, attendance_days, visibility/audit records and index definitions using the existing backup procedure. Record document counts. Rehearse restore into a separate database; confirm source timestamps and manual corrections survive exactly.
3. Freeze writers on the isolated copy. Run `python scripts/reconcile_attendance_calendar_days.py --uri <isolated-uri> --database <isolated-db>` and securely retain the JSON report. Review all ambiguous findings; blocked apply never resolves conflicts by deletion. Check before/after counts even in dry run.
4. With a clean report, run the same command with `--apply`. Rerun it to verify zero additional inserts and unchanged source counts. Validate the user/date unique index and new month index on real MongoDB, query plans, representative volumes, simultaneous logins/timeouts and corrected-date histories. Additive steps can remain after an interrupted apply; rerun safely rather than resetting data.
5. Run desktop/mobile acceptance against the isolated real backend and verify CSV/XLSX contents match month and Employee scope. Confirm the existing ARQ expiry worker cadence, server rejection after the timeout cutoff and no passive heartbeat extension. Complete backup restoration and operational/failover acceptance.
6. Only after reviewing those results request explicit Owner production-migration/deployment authorization. Release API/frontend together so the month default/metadata and clipped summary semantics agree. Do not re-run the unrelated combined identity migration as part of this focused correction.

Prefer forward recovery: keep all raw history/manual corrections and repeat additive key reconciliation after correcting the source ambiguity through approved workflows. A code rollback can restore the previous view while retaining new fields/indexes; it would restore the known prior-day display defect, so use only as an Owner-approved emergency measure. Do not delete metadata keys, duplicate records or indexes merely to roll back. Any selective cleanup needs the pre-release inventory, a verified backup, stopped writers and explicit Owner authorization.

No technical test establishes productive work or approves a payroll policy. The existing inactivity allowance remains unchanged. Real-database, representative-data, restore and live release gates prevent a PRODUCTION READY verdict.

## Files changed in this correction

- `backend/app/features/auth/indexes.py`
- `backend/app/features/auth/session_lifecycle.py`
- `backend/app/features/daily_operations/attendance.py`
- `backend/app/features/daily_operations/calendar.py`
- `backend/app/features/daily_operations/reconciliation.py`
- `backend/app/features/daily_operations/router.py`
- `backend/app/features/daily_operations/views.py`
- `docs/DAILY_AUTOMATION_ATTENDANCE_IDENTITY_2026_10_26.md`
- `docs/DAILY_CALENDAR_RELEASE_FIX_2026_10_26.md`
- `docs/screenshots/attendance-calendar-2026-10-26/employee-1440-colors.png`
- `docs/screenshots/attendance-calendar-2026-10-26/employee-1440-month.png`
- `docs/screenshots/attendance-calendar-2026-10-26/employee-1440-september.csv`
- `docs/screenshots/attendance-calendar-2026-10-26/employee-390-colors.png`
- `docs/screenshots/attendance-calendar-2026-10-26/employee-390-month.png`
- `docs/screenshots/attendance-calendar-2026-10-26/employee-390-september.csv`
- `docs/screenshots/attendance-calendar-2026-10-26/owner-1440-colors.png`
- `docs/screenshots/attendance-calendar-2026-10-26/owner-1440-month.png`
- `docs/screenshots/attendance-calendar-2026-10-26/owner-1440-september.csv`
- `docs/screenshots/attendance-calendar-2026-10-26/owner-390-colors.png`
- `docs/screenshots/attendance-calendar-2026-10-26/owner-390-month.png`
- `docs/screenshots/attendance-calendar-2026-10-26/owner-390-september.csv`
- `docs/screenshots/attendance-calendar-2026-10-26/results.json`
- `frontend/src/features/daily_operations/DailyOperations.test.tsx`
- `frontend/src/features/daily_operations/DailyOperationsPage.tsx`
- `frontend/src/features/daily_operations/api.ts`
- `scripts/attendance-calendar-ui-check.mjs`
- `scripts/reconcile_attendance_calendar_days.py`
- `tests/api/test_attendance_calendar_release.py`
- `tests/api/test_daily_automation_hardening.py`
