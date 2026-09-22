# Insurance automatic Re-Eligibility

The existing execution path is:

`InsuranceCaseService.reject_case` → shared date helpers →
`insurance_details.re_eligible_date` → Arq `WorkerSettings.cron_jobs` →
`auto_transition_re_eligible_cases` → `WorkflowEngine.transition` →
normal status history/audit/event → Insurance list/count/detail APIs.

`re_eligible_date` is the existing UTC timestamp equivalent of the requirement's
`re_eligible_at`; no field rename or migration is introduced. The 3/6/12-month options
use calendar-month arithmetic, clamped at month-end. Custom dates become midnight in
the configured business timezone (IST), stored in UTC. `no` stores a null date and is
also explicitly excluded by the worker even if an inconsistent legacy row has a date.

Rejection is supported at Fresh Lead, Policy Document, Policy Login, Payment and
Re-Eligible. Policy Issued is terminal; On Hold must be resumed first; already Rejected
cannot be rejected again. These existing rules are unchanged. Once rejected, the
worker uses only current status, due timestamp, case type and the No exclusion—not
the originating stage, creator, employee assignment or Advisor assignment.

## Findings and fix

Code inspection confirmed that Insurance was already in `_RE_ELIGIBILITY_PIPELINES`.
The scheduler previously ran the job only at 02:15 once daily, with no startup run.
Starting the API/frontend alone never started this job; local documentation described
the worker as optional and omitted re-eligibility. An unavailable worker cannot perform
any automatic transition, and a newly started worker could wait until its next daily
slot. No production process status was inspected or inferred from these findings.

Additional execution defects were present:

- An absent Owner record caused a silent return for both pipelines.
- A failing Loan case/definition could abort the sweep before Insurance was reached.
- Each pipeline was limited to the first 1,000 due cases per daily run.
- Read-then-write transitions allowed overlapping workers/manual marking to duplicate
  history. There was no atomic status/schedule precondition.
- Insurance rejection and its date were separate writes, allowing a rejected case to
  be left without a schedule if the intervening work failed.

The existing job now runs at startup and every minute, streams the due backlog,
continues past individual case failures and reports failures in worker logs. Due cases
are processed with a null system actor, normal history, and explicit system/automatic
audit metadata. Compare-and-set protects status and the captured schedule; only the
winner writes transition history/audit and publishes the event. Insurance rejection
persists status and schedule in the same case update. History/audit still use the
existing workflow engine's separate collection writes; this change does not introduce
multi-document transactions or a durable event outbox.

Insurance counts already poll every 15 seconds. All Insurance case lists now opt in
to the shared list's 15-second refresh and focus refresh. They only read server results;
no frontend code changes a case's eligibility or status. Other list callers do not gain
polling unless they opt in.

## Runtime requirements after pulling the code

- **Migration: NO. Seed: NO** for an already configured current Policy Leads workflow.
  No schema, permission, assignment or status catalog changes are made.
- Run/restart the existing worker with the same MongoDB database and Redis configuration
  as the API: from the backend environment, its entry point is
  `arq app.worker.worker_settings.WorkerSettings`.
- The repository contains `deployment/docker-compose.yml` service **`worker`**, using
  that entry point, plus local launchers `scripts/dev/start-worker.ps1` and `.sh`.
  There is no repository systemd unit or OS crontab to enable. Do not assume a systemd
  service name. Use the supervisor actually configured in your deployment.
- For deployments using the supplied Compose file, rebuild/recreate the existing
  worker along with the API. The worker now has `restart: unless-stopped` and an Arq
  heartbeat health check. An unhealthy status is diagnostic; Compose does not itself
  restart an unhealthy but still running process. Note that the checked-in Compose file
  references `.env.development`; retain your deployment's actual production configuration.
- The process must remain running. Check its logs for `auto_transition_re_eligible_cases`
  and `Re-eligibility sweep: processed=… skipped=… failed=…`.
  `arq --check app.worker.worker_settings.WorkerSettings` checks the Redis heartbeat;
  it is not proof that every business job succeeded. Inspect the sweep logs too.
- Existing due rejected cases are selected on startup without manual editing.
  A case without a saved schedule is not assigned an invented one.
- The existing Insurance `rejected` definition must allow `re_eligible`, and the target
  definition must exist and be non-deleted. Current seed and insurance migration scripts
  already provide these. Missing definitions are now reported rather than silently
  starving the other pipeline. Do not rerun the old broad insurance redesign migration
  merely to repair one definition; it predates the Payment stage.

No production access, deployment, data edits, commits or pushes were performed for this fix.

## Manual verification

1. Confirm the updated API and existing worker use the intended environment. Confirm
   the worker heartbeat and a successful sweep log; record current Rejected/Re-Eligible counts.
2. For one case each in Policy Document, Policy Login and Payment, reject with a future
   Custom Date. The shortest supported date is tomorrow's business-calendar midnight.
   Also verify Fresh Lead and the 3/6/12-month options save the expected future date.
3. Before the stored due instant, verify Rejected status, presence in the Rejected list,
   absence from Re-Eligible, and the stored schedule. For No, verify a null schedule.
4. At/after the due instant, allow one worker polling interval plus the 15-second list
   refresh (and processing time). Verify Rejected decreases by one and Re-Eligible
   increases by one; the case disappears from Rejected and appears in Re-Eligible.
5. Open case details and Application History. Confirm `re_eligible`, exactly one
   `rejected → re_eligible` automatic history entry, a cleared date, and
   `re_eligibility_auto_transitioned=true`. Assignment and creator must be unchanged.
6. Leave the worker running through additional ticks. Verify no duplicate transition,
   history, notes or notifications. Verify the No case remains Rejected.
7. Verify an existing already-due case is picked up after worker startup without editing
   it. Verify a future case is untouched. Repeat one Loan schedule as a runtime regression.

## Local automated evidence

`tests/api/test_insurance_re_eligibility_automation.py` uses the actual registered Arq
cron, Arq's scheduler/queue dispatch and worker execution against fakeredis and
mongomock. Only Redis INFO diagnostics and the Windows-only signal compatibility issue
are adapted in the harness. This is executable scheduler coverage, not a live deployment
test or a claim that a production worker is running.

The suite covers every rejectable stage × 3/6/12/custom, before/due/expired dates,
No (including inconsistent stored dates), counts/lists/details, unchanged assignments,
system history/audit, repeated and overlapping execution, manual/worker races,
rescheduling/deletion races, failure isolation, absent Owner, Loan regression, and a
1,001-case startup backlog. The shared list tests cover polling, cleanup and unchanged
behavior for callers that do not opt in.

## Changed files for this fix

Insurance implementation:

- `backend/app/features/insurance_management/service.py`
- `frontend/src/features/insurance_management/pages/InsuranceCaseListPage.tsx`

Shared implementation and existing worker configuration:

- `backend/app/features/workflow_engine/engine.py`
- `backend/app/features/workflow_engine/repository.py`
- `backend/app/worker/tasks/reminders.py`
- `backend/app/worker/worker_settings.py`
- `frontend/src/components/pages/CaseListPage.tsx`
- `deployment/docker-compose.yml`

Tests and documentation:

- `tests/api/test_insurance_re_eligibility_automation.py` (new, 41 tests)
- `frontend/src/components/pages/CaseListPage.test.tsx` (two polling regressions and an asynchronous assertion correction)
- `docs/RUN_LOCAL.md`
- `docs/INSURANCE_RE_ELIGIBILITY.md` (this runbook)

No Loan-specific source files changed. The shared scheduler improvements also apply
to Loan; its existing scheduling arithmetic and business stages are unchanged. Earlier
uncommitted Dashboard work was left untouched by this task. Tracked TypeScript build-info
files were not modified.

## Verification results (local)

All 231 selected backend tests passed across the runs and targeted reruns:

| Coverage | Passed |
|---|---:|
| New automation suite, including shared Loan cases | 41 |
| Existing Insurance Policy Leads, enhancements, manual lead, visibility and definition tests | 102 |
| Existing Loan redesign, bank offers and visibility tests | 56 |
| Existing reminder and shared workflow tests | 32 |

The 1,001-case test exceeded the harness's initial 10-second limit; it passed with a
60-second harness limit. No production job timeout was increased. Arq emits a dependency
deprecation warning for Redis `close()` in worker cleanup.

Frontend verification covered 110 tests in the shared case-list and Insurance/Loan
areas, all passing across the initial run and targeted reruns. One existing asynchronous
assertion now waits for the data row; one form test timed out under concurrent load and
passed with two test workers. No unrelated form code was changed.

- TypeScript app and Vite-config checks: passed using `tsc -p ... --noEmit --incremental false`.
- ESLint: zero errors, 10 existing warnings across the workspace.
- Production frontend build: passed using `vite build` after TypeScript checks; existing
  large-bundle warning remains. No tracked build-info file was written.
- Backend Ruff on changed source/test files: passed.
- Mypy on the five changed backend source files (`--follow-imports=silent --no-incremental`): passed.
- Full `ruff check app`: six existing errors in unchanged Customer, Leads, Loan,
  Referral Partner and workflow constants files.
- Full `mypy app --no-incremental`: nine existing errors in seven unchanged Auth,
  Customer, Owner, Loan and Leads files. Those unrelated files were not changed.

Backend tests were run with process-local `DEBUG=false` because the shell environment
has an invalid `DEBUG=release`, and explicit `-c pyproject.toml` to load the project's
async-test configuration for tests outside the backend directory.
