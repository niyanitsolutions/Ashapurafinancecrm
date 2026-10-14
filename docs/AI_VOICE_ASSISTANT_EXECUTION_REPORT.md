# Production-readiness continuation: execution evidence

14 October 2026. Local checkout main, starting HEAD f3edf7d. Earlier uncommitted
voice work was preserved. No commit, production migration, deployment, real call,
paid service or approved speech service activation occurred.

## Changes actually implemented

Campaigns now have persisted creator-scoped records, strict schemas, customer
authorization, safe CSV audience imports, idempotent import receipts, 10,000-recipient
limit, timezone/DST utilities, consent/withdrawal and suppression attestations,
current eligibility previews, state transitions, worker reservations/recovery,
pause/cancel/emergency stop and processing counts. The frontend Campaigns and
Compliance tabs now use these backend operations rather than static placeholders.
All processing is dry-run; no fixed IVR, manual dialer or live dispatch was added.

Sensitive advisor edits no longer fall back to general insurance application-edit
permission. Legitimate advisor/legacy recruitment grants remain supported. The
insurance assignment regression now checks the existing advisor/staff distinction
and additionally verifies advisor preservation across staff reassignments.
Five existing Ruff errors were fixed with import ordering and ClassVar annotations.

## Workstream status

| Workstream | Implemented / automated evidence | Still required |
|---|---|---|
| 1 Campaigns and callbacks | Dry-run campaign management, scoped imports, consent/suppression, scheduling, fenced processing and UI; focused tests passed | Confirmed callback workflow, real consent verification, cross-campaign contact reservations, live dispatch outbox/reconciliation/backoff, approved compliance policy and staging |
| 2 Caller identity and tools | Existing CRM auth/customer scope remains enforced; no protected live tool enabled | Verified caller assurance, approved authoritative payment source, typed allowlisted tool orchestration, confirmed idempotent ticket/callback effects and acceptance scenario A |
| 3 Training and releases | Previous safe TXT/CSV/DOCX/XLSX import, lexical evidence evaluations, approved article snapshots/rollback remain tested | Isolated PDF/scanner/OCR, approved embeddings, semantic retrieval and immutable behavior/configuration release lifecycle; scenario D incomplete |
| 4 Live voice | Previous provider-neutral audio contract and offline dynamic engine/Smartflo validation-only tests preserved | Actual provider sandbox/trunk, approved STT/TTS, live capture, independent outage fallback, real agent availability/transfer; scenarios A/C/E not staging verified |
| 5 Hardening | Ruff clean, changed-module mypy clean, full backend and Node 22 frontend regressions passed; advisor authorization and runtime-format corrections | Whole-app mypy repair, container execution, actual capacity/restore/failure tests and operational sign-off |

All five workstreams remain **partial**. None is production enabled or fully
staging verified. The overall product is **not production ready**. Missing internal
implementation above is distinct from missing external credentials/infrastructure.

## Requested load profile and acceptance scope

User selected **10 concurrent calls and 10,000 campaign recipients** as the initial
staging profile. This is neither measured capacity nor a latency/service-level
commitment. Local tests exercise the 10,000-recipient boundary and ten competing
dry-run workers against one recipient, with exactly one completed reservation.
They do not reproduce ten audio calls, carrier behavior, Mongo throughput or a
10,000-call campaign. The large boundary fixture bypasses mongomock's quadratic
unique-index fixture construction; separate duplicate/concurrency tests retain
indexes. Production indexes are unchanged.

Before real staging load: provision isolated non-production dependencies, approved
speech and consent policy, synthetic/test recipients, provider-approved test numbers,
verified callback authentication and legal traffic authorization. Instrument actual
call concurrency, audio buffer depth, interruption/cancellation latency, model/STT/TTS
latencies, failure rates, duplicates, memory/CPU, queue age and recovery. Owner must
approve numerical latency/error budgets; no budgets were inferred from the load reply.
Run restart, expired lease, revoked permissions, suppression changes, provider timeouts,
disk-full, speech outage and transfer-failure scenarios. Live tests remain blocked.

## Verification commands and results

Run backend commands from backend, with DEBUG=false (PowerShell: `$env:DEBUG='false'`).

```powershell
.\.venv\Scripts\python.exe -m pytest --rootdir=.. -c pyproject.toml ../tests/api/test_voice_campaigns.py ../tests/api/test_voice_assistant.py ../tests/api/test_voice_platform.py ../tests/api/test_voice_smartflo.py ../tests/api/test_agency_business_notifications.py -q --tb=short
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app/features/voice_assistant app/main.py app/worker/tasks/voice_assistant.py app/worker/worker_settings.py --follow-imports=silent
.\.venv\Scripts\mypy.exe app --follow-imports=silent
.\.venv\Scripts\python.exe -m pip check
```

- Expanded focused backend: **73 passed**, 104 deprecation warnings, 43.34 seconds.
- Final expanded focused backend after edge hardening: **78 passed**, 104
  deprecation warnings, 45.49 seconds, using the same focused command above.
  Repository-wide Ruff and changed-module strict mypy (29 files) also passed again.
- Campaign subset: **8 passed** before adding two HTTP authorization tests; both
  subsequently passed in the 73-test run.
- Repository-wide Ruff: passed; changed-module strict mypy: **29 files passed**.
- Whole-app mypy: **116 errors in 11 files**; invoice/stub and existing CRM typing
  failures remain. No broad type suppression was introduced.
- pip check: no broken requirements.
- Initial current baseline: 71 passed, two CRM failures; advisor permission defect
  fixed, assignment expectation updated to the existing documented contract with
  stronger advisor-preservation assertions. Subsequent assignment evidence follows.
  The separate assignment/advisor regression command passed **13 tests**:
  `python -m pytest --rootdir=.. -c pyproject.toml ../tests/api/test_assignment_consistency.py ../tests/api/test_agency_business_notifications.py -q --tb=short`.

Frontend commands from frontend:

```powershell
npm run lint
npm run build
npm exec vitest run src/features/voice_assistant
npm exec vitest run --maxWorkers=2
npm audit --omit=dev
```

- Focused frontend: **20 passed across 5 files**, including three campaign tests.
- Full frontend first run: **324 passed, one insurance form test timed out** under
  concurrent local test load. Full rerun with two workers: **325 passed across 65
  files**. Assertions/timeouts were not weakened to pass the retry.
- Build passed with the existing large-chunk warning. Lint: zero errors, ten
  existing warnings.
- Build also passed using checksum-verified official **Node v22.23.3**, downloaded
  to ignored workspace node_modules/.cache/voice-node22. The host default Node
  v18.17.1 was not changed. The first Node 22 full run had **322 passed, three failed**
  due to an ICU date-separator change in the existing loan top-up popup. Its date
  display now preserves the established DD-Mon-YYYY style across both runtimes.
  The unchanged affected tests passed **12/12**; the subsequent full Node 22 run
  passed **325 tests across 65 files**. Node 22 build and lint also passed (same
  existing chunk/lint warnings).
- Online production npm advisory audit: **zero vulnerabilities**. This does not
  constitute a complete application security review or Python advisory scan.
- Compose config --quiet passed; Docker daemon was absent, so no container build,
  Nginx runtime test or staging deployment passed. Docker client also reported
  restricted access to its user configuration file.

Fresh full backend regression: **1,244 passed**, 179 deprecation warnings, 569.57
seconds, four isolated pytest workers. This run completed before the final narrowly
scoped upload/import/scheduling/canonical-ID edge fixes; those are verified by the
subsequent expanded focused run. Historical full-backend results in the implementation
plan are retained separately. No staging acceptance scenario A-E has been completed against real
external services. Scenario B's dry-run subset is covered locally; remaining carrier
steps are blocked. No external service was successfully connected in this batch.

Fresh complete backend regression uses an explicit ../tests path. A diagnostic
invocation omitting that path collected no tests after rootdir relocation and was
not considered successful. CI now fails on no collection, instead of accepting
pytest exit 5. pytest-xdist 3.8.0 is a dev-only dependency for isolated parallel
regression workers; production dependencies are unchanged. The initial serial
whole-suite run was stopped to restart with four isolated workers; partial progress
is not a successful whole-suite result.

Final review strengthens import expiry fencing and upload bounds for malformed or
uppercase path IDs; canonical campaign IDs prevent split recipient scopes. Future
schedules no longer preview as currently eligible. The concurrent-reservation test
now holds the first worker with an explicit barrier while nine competitors attempt
to reserve its recipient, instead of relying on mock I/O to yield. No real-call
concurrency result is implied.

```powershell
# From backend after installing .[dev]; local mock services only:
.\.venv\Scripts\python.exe -m pytest --rootdir=.. -c pyproject.toml ../tests -n 4 -q --tb=short --maxfail=3
# From frontend, deployment-runtime verification using the local verified cache:
.\node_modules\.cache\voice-node22\node.exe node_modules/vitest/vitest.mjs run --maxWorkers=2
```

## Files, migration, deployment and rollback

New campaign backend files: campaign_schemas.py, campaign_service.py,
campaign_router.py and scheduling.py. Updated main/catalog/upload limits, ARQ task
and schedule, Nginx bounded import route. Frontend adds CampaignPanel,
ContactPolicyPanel, campaign tests and typed API operations; VoiceAssistantPage
mounts the actual controls. Tests add test_voice_campaigns.py and strengthen the
assignment contract. Permission repair is in recruitment/dependencies.py; static
repairs are in customer/loan/referral/workflow files.
TopUpSchedulingModal.tsx preserves its existing date separator under Node 22's ICU
data; existing date assertions remain unchanged. ProviderConnectionsPanel includes
the official legacy token-expiry notice; its five tests and Node 22 build passed
after that notice was added. pyproject.toml adds pytest-xdist only to dev extras.

Use the existing build/deployment procedure only in an authorized staging
environment. Deploy API and worker from the same reviewed revision, with frontend
assets rebuilt; verify additive startup catalog/index registration and grant campaign
View/Create/Edit/Import only to intended staff. Sidebar entry still uses Calls View;
Owner remains unrestricted. No environment variable can bypass blocked live modes.
See OPERATIONS.md for existing private artifact and provider configuration. Never
register guessed webhook URLs: retain documented Smartflo routes and validation-only
mode until real authentication/reachability checks pass.

Before any authorized staging rollout, snapshot Mongo and private artifact keys/data,
record deployed revision, run the checks above, confirm worker heartbeat and execute
dry-run preview/restart tests. Rollback API/worker/frontend together to the reviewed
previous image/revision; pause campaign processing first. Additive campaign data may
remain for audit, but do not delete policies or recordings. A rollback to code without
the campaign worker stops evaluations; it does not authorize call dispatch. Verify
artifact decryption and existing CRM flows after rollback. Restore rehearsal and
real carrier reconciliation remain unverified.

## Priorities preventing production readiness

1. Implement verified identity and authoritative financial tools; no EMI answers may
   be derived from offers or unverified caller-ID.
2. Complete confirmed callback/ticket workflows and live-safe dispatch reconciliation.
3. Implement scanned isolated PDF/OCR, approved semantic index and governed behavior
   releases while preserving current article publications.
4. Provision and verify actual telephony/speech/agent/fallback services, webhook
   authentication and capture consent; keep activation blocked until then.
5. Resolve global typing/regression gates, test containers, measure the requested load,
   rehearse recovery/rollback and obtain owner security/privacy/compliance approval.

Provider reference remains the official Smartflo documentation:
https://docs.smartflo.tatatelebusiness.com/docs/ . Provider integration details and
specific supported endpoints/events are recorded in SMARTFLO_VOICE_AUDIT.md.
