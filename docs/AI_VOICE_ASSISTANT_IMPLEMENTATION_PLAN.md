# Advanced voice implementation plan and progress

## Production-readiness continuation (current request)

The checkout is `main`, HEAD `f3edf7d`; earlier voice upgrades remain uncommitted
and are preserved. The local repository is the implementation source for the
requested Ashapurafinancecrm project. This continuation verifies all five
workstreams independently; historical results below are not new baseline results.

| Workstream | Current verified code/gap | Implementation and acceptance dependency |
|---|---|---|
| Campaigns/callbacks | Campaign eligibility backend/UI implemented; callbacks and live dispatch missing | Persisted customer-scoped audience, consent/suppression attestations, timezone/DST checks, dry-run decisions, lifecycle/emergency stop and fenced dry-run reservations; real dispatch blocked until approved transport/compliance and operator enablement |
| Caller identity/tools | No caller assurance or authoritative loan-payment ledger | Reuse customer/application access rules; create assurance/payment adapter contracts and fail-closed gateway, idempotent confirmed callbacks; never accept caller-ID as assurance or infer EMI payment from offers |
| Training/releases | Four import formats, evidence evaluation and approved publication snapshots | Add governed immutable behavior-release snapshots; PDF/OCR/scanner and embeddings require isolated parser/approved engines and resources; preserve current release/retrieval workflows |
| Live voice | Provider-neutral framing/buffering, Smartflo validation-only callbacks, imported artifacts | No approved PBX/trunk/STT/TTS/identity service/agent queue. Keep public media and paid/live calls disabled. Actual capture/handoff and scenarios A/C/E need staging infrastructure |
| Hardening | Focused checks previously passed; global checks had baseline issues | Reproduce test/static failures, fix without broad rewrites/weakening tests, verify actual Node/container environment, rerun frozen regression and document measured load-test scope |

Initial inspection confirms insurance `case.assigned_to` is an Advisor; staff
assignment is `Application.assigned_to` (see current insurance service authorization
comments). The older regression expectation must not cause employee IDs to overwrite
advisor IDs. Advisor secret editing must remain distinct from business-edit grants.
Current continuation fixes that advisor permission boundary. Its separate
assignment/advisor regression run passes 13 tests, including stronger checks that
changing staff preserves the assigned advisor. The campaign/voice/provider focused
run passes 73 tests. The detailed current ledger and remaining work are in
[AI_VOICE_ASSISTANT_EXECUTION_REPORT.md](AI_VOICE_ASSISTANT_EXECUTION_REPORT.md).
Final verification: full backend 1,244 passed; after final scoped edge hardening,
78 focused tests passed. Full Node 22 frontend 325 passed; global Ruff passed;
29 changed-module mypy files passed. Whole-app mypy still reports 116 errors.
Compliance-owner and traffic/SLO approval are not available; code cannot certify
Indian privacy/DND/outbound obligations or production capacity from local fixtures.

14 October 2026. Preserve previous Smartflo work, existing data/auth/RBAC and
single-company architecture. Live voice is explicitly blocked: no approved speech
service, no provisioned/verified carrier or independent fallback.

| Phase | Task and dependency | Status |
|---|---|---|
| 1 Audit | Verify existing UI/API/model/worker/deployment; trace every major feature | Complete; see audit |
| 2 Architecture | Independent media/AI boundaries, self-hosted engine evaluation, safe recording storage | Complete for this batch; no PBX installed |
| 3 Core | Remove Smartflo dependency from dynamic core; bounded audio backpressure; explicit readiness | Implemented and adapter-tested; PCM/mu-law formats declared separately |
| 4 Knowledge | Safe TXT/CSV/DOCX/XLSX import, provenance, preserved published release, evaluation, reviewed rollback | Implemented and tested; evaluation is lexical evidence, not semantic certification |
| 4 Knowledge dependencies | PDF isolated parser/scanner, URL allowlist, embeddings/hybrid index, behavior release/evaluated LLM | Pending dependencies/additional implementation |
| 5 Recordings | Encrypted private artifact storage, WAV validation, authenticated playback/download, transcript linkage, deletion/retention worker, UI | Implemented and tested with real temporary encrypted files and imported test artifacts |
| 5 Live capture | Actual PBX/media capture, consent policy, two-sided timestamps, approved real transcription | Blocked infrastructure and approvals |
| 6 Campaigns | Persisted eligibility/suppression, preview, campaign lifecycle and audience imports | Implemented for dry-run evaluation; confirmed callback tasks, live dispatch outbox and agent availability/handoff remain missing |
| 7 Hardening | Security/races/cancellation/retention/evaluation tests, type/lint/build, runbook | Focused checks passed; whole-CRM baseline issues remain below |
| 7 Live acceptance | Carrier interoperability, storage/restore, model quality, speech latency, load and outage failover | Blocked real infrastructure |

## Compatibility and schema notes

Extend existing `voice_knowledge` and reuse `voice_calls`, `audit_logs`, shared
encryption and permission engine. Additive optional fields only; no destructive
schema conversion, no production seeds, no grants automatically assigned. A
recording artifact is a derivative linked to an existing call, not a new call model.
Legacy knowledge remains readable; approved publication snapshots are introduced
without requiring a bulk migration. Never create fake completed artifacts.

## Verification ledger

Previous Smartflo batch: 88 focused backend tests, 313 frontend tests on retry,
build/Ruff/mypy passed; 10 existing frontend lint warnings. These are historical
results, not verification of the advanced batch. Tests use mock Mongo/Redis/provider responses; no real customer
calls, approved model, carrier, production storage or production deployment tested.

Current advanced batch:

- Focused backend: **110 passed**, including 22 advanced-platform tests, existing
  voice/Smartflo/Exotel, access-control and dashboard regressions.
- Final full frontend after React Router patch: **322 passed across 64 files**;
  feature subset: **17 passed**. Build passed; lint zero errors/10 existing warnings.
- Whole backend run while implementation was in progress: **1225 passed, 4 failed**.
  Two known unchanged CRM failures remain: advisor password authorization expects
  403 but gets 404; insurance application assignment expects an employee but gets
  None. The two voice failures used an older imported Smartflo class while the new
  audio-format contract was being written; both passed in the subsequent clean
  110-test run. The entire backend suite was not rerun after this clean focused run.
- Initial combined navigation tests exposed module-autouse fixture leakage when
  collecting files outside pytest's root directory; module-level explicit fixture
  markers fixed it. Navigation/security regressions pass without changing their tests.
- Whole-app Ruff found five existing errors in unchanged customer, loan,
  referral-partner and workflow files. Whole-app strict mypy found existing
  invoice/stub/customer/auth/owner/loan/lead issues: **116 errors in 11 unchanged
  files**. Changed-file Ruff passed, and strict mypy passed **26 files** covering
  the voice module, workers, encryption and application entrypoint. Do not report
  the global gates as green.
- `pip check` passed. Production `npm audit --omit=dev` initially found the React
  Router advisory; pin updated from 7.18.1 to 7.18.4, with a minimal lockfile change
  and install scripts disabled. Repeat audit: **zero reported vulnerabilities**.
  The [advisory](https://github.com/advisories/GHSA-qwww-vcr4-c8h2) concerns RSC APIs,
  which this SPA does not use. This is not an exhaustive supply-chain certification.
- Compose `config --quiet` passed; Docker credential-file access emitted a local
  warning. Containers/PBX/Nginx were not built/run. Local Node 18.17.1 emitted engine
  warnings; production Docker/CI already target Node 22. Verify a Node 22 container
  build before release. No host-wide Node installation was modified.

Exact commands (from `backend`, with `$env:DEBUG='false'`):

```powershell
.\.venv\Scripts\python.exe -m pytest -c pyproject.toml ../tests/api/test_voice_platform.py ../tests/api/test_voice_assistant.py ../tests/api/test_voice_exotel.py ../tests/api/test_voice_smartflo.py ../tests/api/test_access_control.py ../tests/api/test_dashboard.py -q --tb=line
.\.venv\Scripts\python.exe -m pytest -c pyproject.toml -q --tb=line
.\.venv\Scripts\python.exe -m ruff check app/features/voice_assistant app/worker/tasks/voice_assistant.py app/worker/worker_settings.py app/security/encryption.py app/main.py ../tests/api/test_voice_platform.py ../tests/api/test_voice_assistant.py
.\.venv\Scripts\python.exe -m mypy app/features/voice_assistant app/worker/tasks/voice_assistant.py app/worker/worker_settings.py app/security/encryption.py app/main.py --follow-imports=silent
.\.venv\Scripts\python.exe -m ruff check app --output-format concise
.\.venv\Scripts\python.exe -m mypy app --follow-imports=silent
.\.venv\Scripts\python.exe -m pip check
```

From `frontend`: `npm run build`, `npm run lint`,
`npm test -- --maxWorkers=2 --reporter=dot`,
`npm test -- --run src/features/voice_assistant --maxWorkers=2 --reporter=dot`,
`npm audit --omit=dev --json --cache node_modules/.cache/npm-audit`.
From repository root: `docker compose -f deployment/docker-compose.yml config --quiet`.

## Exact next implementation batches

1. Campaigns: extend existing CRM contacts with permission-scoped audience import,
   explicit consent/suppression, eligibility preview, timezone windows, attempt and
   budget limits; persist paused drafts, recipient attempts/outcomes and durable
   dispatch reservations. Add campaign permissions and ARQ recovery. Dispatch stays
   unavailable until transport approval; previews never call customers.
2. CRM tools: identify authoritative EMI/payment integration; implement verified
   caller assurance, existing-resource access checks and confirmed/idempotent
   callback/support/follow-up tools. Never infer payment status from loan offers.
3. Knowledge: resource-isolated PDF/OCR parser, scanner adapter, approved URL/SSRF
   policy, semantic embedding adapter/index using evaluated Mongo capabilities,
   scalable retrieval, versioned behavior releases and model-quality/injection
   regression workbench. The current deterministic evaluator is only evidence matching.
4. Operations: select/provision PBX/SBC/trunk and speech resources; implement durable
   confirmed call commands, authenticated reserved media, VAD/language/silence,
   actual handoff/agent availability and independent outage recovery.
5. Capture/intelligence: consent-gated two-sided capture, real STT worker, searchable
   authorized transcripts/redaction, reviewed summaries/intent/knowledge gaps,
   object-storage adapter if needed, backup deletion/DR and production load tests.
6. Resolve the unchanged whole-CRM test/type/lint issues in their own reviewable
   changes, then run a clean immutable full regression and all five live acceptance
   scenarios. All seven phases are **not complete** and live production readiness
   is **not certified**.
