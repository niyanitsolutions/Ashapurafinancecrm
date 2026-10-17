> **Implementation update ? 17 October 2026: NOT COMPLETE / NOT PRODUCTION READY.**
> The current test-to-requirement map, actual commands, failures corrected, final test evidence, external blocks and preservation comparison are in the implementation evidence report. New cases cover content-bearing clarification attacks, unbound streaming sessions, revocation during generation/synthesis/media frames, obsolete/noncooperative adapters, parent/creator/supervisor/customer lifecycle, actual binding mutation, expired DNC, Owner resolution, audit outage/replay/concurrent repair, encrypted corrections, metric source separation and additive staging-index recovery/conflicts. Mock database and fake media results are not staging acceptance.
> See [current implementation, traceability and execution evidence](VOICE_HARDENING_EXECUTION_2026_10_17.md) and [self-hosted staging contract](VOICE_SELF_HOSTED_STAGING_CONTRACT.md).
> The original audit below is retained verbatim as historical baseline evidence; its statements about unchanged source, findings, test counts and pending implementation approval describe that earlier audit, not this worktree.

> Final local verification: **1,408 backend passed / 1 Linux-only skip; 354 frontend passed; build passed**. These are local/mock/synthetic results, not PBX, installed-model or staging acceptance. See the execution report for commands, warnings, earlier failures and remaining gates.

---

# AI Voice Assistant — test and acceptance matrix

Audit date: 17 October 2026. This is an evidence/acceptance document, not new test
implementation. Sources/abbreviations: [as-built](AI_VOICE_ASSISTANT_COMPLETE_AS_BUILT.md).
Findings: [G01–G17](AI_VOICE_ASSISTANT_GAP_ANALYSIS.md). The audit leaves tests,
source, environment and deployment unchanged.

## 1. Checks actually executed in this audit

| Check | Exact scope / result | Evidence boundary |
|---|---|---|
| Working-tree inventory | `git status --short`, HEAD lookup, tracked/untracked file inventory | Prior uncommitted work present and preserved; not a deployment/release identity |
| Source inspection | Voice routers/services/models/config/worker/UI clients/components/test definitions and relevant CRM/auth/retention/infrastructure callers | Static code evidence, not actual stored/deployed configuration |
| Existing voice backend tests | All existing `tests/api/test_voice_*.py`: **198 passed, 1 skipped, 493 warnings**, 96.20 s | Mock Mongo/Redis, fake HTTP/engines and temporary synthetic artifacts; no carrier/model proof |
| Backend lint | `python -m ruff check --no-cache .` from backend: passed | No fixes/cache requested; not security or runtime verification |
| Dependency consistency | `python -m pip check`: no broken requirements | Not a vulnerability scan; advisory inventory remains offline |
| Pure synthetic policy probe | `proposal_policy` with high-confidence unclear/clarify, uncertain=true and arbitrary synthetic assertion: response_allowed=true, execution_allowed=false, customer_verified=false | Confirms G02 mechanically; no model/customer/call, no source change |
| Read-only source preservation comparison | SHA-256 comparison of pre-existing non-secret versioned/untracked files against pre-audit snapshot; final outcome recorded below | Does not inspect deployed files or ignored secrets; expected additions are only the five audit Markdown documents |
| Git whitespace check | `git diff --check` | Read-only; no staging/restoration/commit |

Executed test command, existing venv from `backend`:

```powershell
$env:DEBUG='false'
$env:PYTHONDONTWRITEBYTECODE='1'
$voiceAuditTests = Get-ChildItem -LiteralPath '..\tests\api' -Filter 'test_voice_*.py' | Select-Object -ExpandProperty FullName
.\.venv\Scripts\python.exe -m pytest --rootdir=.. -c pyproject.toml @voiceAuditTests -p no:cacheprovider -q --tb=short
```

These variables apply to the local check process only; no environment file was
edited. Cache/bytecode writes were disabled. Tests use existing `T/conftest.py`
ASGI dependency overrides with mongomock/fakeredis and synthetic authenticated
fixtures; no real production DB/Redis/session is used. Engine execution is replaced
except the Linux-only test, which was skipped on this Windows host. Temporary
private-storage fixtures are not customer recordings. No pytest assertions were
weakened and no failing case was skipped to obtain the result.

Warnings: existing Starlette/httpx deprecation and mongomock naive-UTC helper
deprecations; they did not fail this suite. The skipped test is
`test_voice_speech_runtime.py:test_real_posix_child_deadline_and_cleanup`, guarded
for actual Linux process/resource semantics. A passing fake-executable test cannot
replace it or an installed STT/TTS model test.

## 2. Inspected versus historical versus unexecuted evidence

| Evidence | Classification |
|---|---|
| T/test_voice_assistant.py | Freshly executed: mock lifecycle/budgets/ownership, knowledge/publications, console/model HTTP contracts |
| T/test_voice_callbacks.py and test_voice_callback_time.py | Freshly executed: real Task/scoped service logic with mock DB; scheduling interpretation, history/CAS/idempotency/negative dispatch; not actual future calls |
| T/test_voice_campaigns.py | Freshly executed: dry-run audience/consent/leases/recovery/capacity; no phone dispatch |
| T/test_voice_native.py | Freshly executed: Owner APIs, encrypted/write-only credentials, number lifecycle, origin/stale-proof contracts with fake HTTP |
| T/test_voice_smartflo.py and test_voice_exotel.py | Freshly executed: observation auth/dedupe, offline protocol and dynamic fake-audio/interruption contracts; actual provider untested |
| T/test_voice_platform.py and test_voice_platform_controls.py | Freshly executed: import/parser/private artifact/index-catalog/control/activation contracts; no live PBX |
| T/test_voice_self_hosted.py and test_voice_speech_runtime.py | Freshly executed: config/freshness/queue/profile/integrity/pipeline contracts; synthetic model HTTP/fake executables; one Linux skip |
| T/test_voice_intent_policy.py and test_voice_policy_studio.py | Freshly executed: proposal rejection/withholding, synthetic reports, permission/config/publication changes during text generation, Owner scopes |
| U/*.test.tsx | Inspected component/test boundaries and API types/callers; **not rerun** during this audit to avoid generated frontend caches/build artifacts |
| Prior complete backend 1,368 passed / 1 skipped, 568 warnings | Historical result in VOICE_INTEGRATION_EXECUTION_2026_10_17.md and prior tool evidence; not a fresh full-CRM audit run |
| Prior frontend 353 passed / 72 files, successful build/typecheck | Historical, not rerun; synthetic API/jsdom results do not validate carrier/audio |
| Prior scoped mypy 54 files clean; global 116 errors / 11 files / 377 files | Historical only; global type debt is not erased by scoped success |
| Previous Playwright synthetic screenshots/sidebar comparisons | Historical layout evidence only; no new screenshots, browser profile or images generated here |
| Target server, real Mongo/Redis, actual Linux deployment/installed models, PBX/carrier/media/audio | Not run; approved environment, assets and test access required |
| Vulnerability matching / model downloads / package installation / catalog or migration scripts | Not run; offline advisory constraint retained, no mutating production work authorized |

## 3. Workflow acceptance matrix

Each subsection states current expected behavior separately from the evidence
required for the intended real workflow. A blocked capability passes a negative
test, not the positive production capability gate.

### A. Configuration, number approval and activation

- **Preconditions/permission:** active Owner, existing app auth, current version;
  operator-configured origin allowlist before any read-only network probe.
- **Input:** save connection/number/component; request testing or live activation.
- **Expected states/records:** encrypted secret replacement clears prior proof,
  versioned controls/numbers and audit; component change forces live directions off.
  Activation remains denied and creates no call. Revoked number cannot be restored
  by editing or credential rotation.
- **Failures/idempotency:** malformed origin, missing/expired credentials, changed
  version or stale probe cannot approve; current CAS rejects conflicts.
- **Existing tests:** test_voice_native / platform_controls / self_hosted. Inspect
  actual target indexes and repeat initialization before relying on uniqueness.
- **Real acceptance:** approved number/trunk/directions, actual auth and media/model
  prerequisites, explicit release/activation authority; no auto-enable on restart.

### B. Simulated calls versus actual inbound/outbound

- **Preconditions/permission:** calls:create/view/edit, creator/Owner scope; mock mode;
  outgoing additionally needs reference and permitted hours.
- **Input:** label/direction/key, then versioned answer/reject/end/transfer actions.
- **Expected states/records:** mock ringing -> active/terminal with timestamps and
  timeline in voice_calls. Replay returns the same request or conflicts on payload
  mismatch; stale control cannot change a completed/different session.
- **Failures:** capacity/budget/lease/deadline/auth deny; no provider command or media.
- **Existing tests:** test_voice_assistant, CallsPanel/VoiceAssistantPage test sources.
- **Real acceptance:** authenticated provider attempt/event/session and canonical CRM
  binding; actual Owner-first ringing and duration, answer/media and terminal proof.
  Mock success is insufficient; actual native runtime is currently missing.

### C. Knowledge publication and dynamic text

- **Preconditions/permission:** knowledge view/create/edit/approve as appropriate;
  reviewed/current public content and explicitly configured optional local model.
- **Input:** draft/import/evaluation/publication, then question/history/language.
- **Expected states/records:** draft -> review -> published; edits return draft while
  retained publication can remain authoritative. Imported document publication needs
  passing current-fingerprint lexical evidence. Console returns retrieval-only,
  allowed text, safety_hold, superseded or safe unavailable result; no CRM execution.
- **Failures/idempotency:** duplicate active content conflicts; stale versions/date
  or permissions deny; invalid model/citations/shape withhold. Changed configuration/
  publication or revoked account during generation must not release old content.
- **Existing tests:** test_voice_assistant / platform / policy_studio. Fresh G02 probe
  establishes that structural passing does not prove semantic content validation.
- **Real acceptance:** real model inference, adversarial financial/identity/injection
  evaluation, current publication pinning and independent output review; actual speech
  delivery has an additional gate. Historical revisions need retention acceptance.

### D. Local speech verification and real audio

- **Preconditions/permission:** Owner, approved matching profile/asset hashes/sample,
  enabled testing/worker components, bounded available queue slots, Linux executor.
- **Input:** explicit STT/TTS/pipeline verification request; not customer audio ingestion.
- **Expected states/records:** queued -> running -> passed/failed/interrupted/expired/
  superseded in voice_speech_jobs; encrypted expiring audio/evidence only. Shared
  slot/CPU lease prevents simultaneous heavy verifications; reconfiguration invalidates
  proof. Policy withholding occurs before local TTS.
- **Failures/idempotency:** checksum/path/resource/deadline/queue/model failure denies
  success; lost job is not silently retried as a phone attempt. Repeated explicit
  test submissions may create separate bounded tests; they are not phone idempotency.
- **Existing tests:** test_voice_speech_runtime / self_hosted / intent_policy; one
  actual POSIX cleanup test skipped here.
- **Real acceptance:** pinned package/image including Piper package, resource/network
  isolation, real installed model responses, matching codec and confirmed bidirectional
  media/delivery; interruptions, silence, delivery loss and per-language quality.

### E. Caller verification and protected CRM tool

- **Preconditions/permission:** current code has staff authentication only. Target
  needs approved additional factor, trusted expiring caller/customer session and
  object/field/tool permission, not phone match or model-provided verification.
- **Input:** loan/insurance/payment/document question or proposed CRM action.
- **Expected current result:** response held, customer_verified=false,
  execution_allowed=false; no protected-record retrieval or AI data mutation.
- **Failures/idempotency:** arbitrary action/extra authority fields rejected;
  no actual voice verification/attempt/tool receipt implementation exists to test.
- **Existing tests:** test_voice_intent_policy and policy_studio for structural
  denial only. Existing CRM scope tests do not prove telephone identity.
- **Real acceptance:** wrong/replayed/expired/too-many factors, wrong customer,
  cross-record/role revocation, minimum fields, approval and exactly-once receipts;
  retain all customer corrections/provenance. Multi-tenant testing requires an
  approved architecture change, not fake tenant IDs added to this audit.

### F. Callback preview, creation and confirmation

- **Preconditions/permission:** preview calls:create; create additionally scoped
  entity view/edit, Task create, active supervisor/account and no known global DNC.
- **Input:** exact or ambiguous English preference, timezone, explicit date/time/fold,
  entity/assignee IDs and request key.
- **Expected states/records:** preview never persists. Explicit save creates canonical
  existing Task awaiting_confirmation with original input and time provenance; explicit
  confirmation -> scheduled. It is not a telephone job acceptance.
- **Failures/idempotency:** ambiguity/missing date/time/invalid/past/DST gap or overlap
  requires clarification; canonical IDs and current relationship required; exact replay
  returns same Task, changed payload/key or active contact conflict denies duplicates.
- **Existing tests:** test_voice_callback_time / callbacks and inspected U callback
  tests. Valid non-mock source-call linkage cannot currently be supplied by mock sessions.
- **Real acceptance:** spoken extraction/clarification and trusted source-session
  provenance must be demonstrated before voice automation may create/confirm requests.

### G. Callback reschedule, cancellation, review and future execution

- **Preconditions/permission:** current Task version and full callback edit/entity
  scope; due worker rechecks original creator/supervisor/customer and contact policy.
- **Input:** confirm/reschedule/cancel/retry_readiness or ARQ review.
- **Expected states/records:** state/date/history atomic; reschedule clears confirmation;
  cancel inactive; due results blocked/opted_out/confirmation_expired/history closure.
  Calls placed remain zero; unchanged blockers do not add duplicate history.
- **Failures/idempotency:** stale concurrent actions conflict, DNC prevents new/continued
  eligibility; readiness recheck is not dial retry. Parent deletion/creator revocation
  and expired active slots need the G07 recovery policy, currently incomplete.
- **Existing tests:** callback history/CAS/DNC/recovery tests. Changed-binding test
  coverage is weaker than one test name implies (G17); add an actual binding mutation
  test after implementation approval. Do not count it as already proved.
- **Real acceptance:** actual Mongo races, two due claimers, restart after claim,
  cancel/DNC while preparing native attempt, fenced contact reservation, bounded
  transient retries, actual terminal events and no call after cancel/supersession.

### H. Contact policy and campaign eligibility

- **Preconditions/permission:** Owner for attestations; campaigns permissions/owner
  scope plus actual customer access for audience. Real voice purpose is independent
  of other messaging consent.
- **Input:** versioned grant/withdraw/suppress, audience batch/key, start/pause/cancel.
- **Expected states/records:** current policy + bounded embedded history and separate
  event/audit; draft/ready/running -> evaluated recipient decisions -> completed
  dry-run campaign. No live contact. Global/campaign DNC and exact purpose govern
  eligibility; correct `service_callback` versus `callback` mismatch before future dispatch.
- **Failures/idempotency:** unique campaign/customer and import key/hash, leases and
  fencing; principal revocation/emergency pauses; bound reservation attempts. Frequency
  lookup is not proof that a real contact was recorded by a nonexistent caller.
- **Existing tests:** test_voice_campaigns and inspected Campaign/ContactPolicy UI.
- **Real acceptance:** actual consent legal policy, purpose/window composition,
  global contact reservation/outcomes and durable multi-write failure recovery.

### I. Human handoff / takeover

- **Preconditions/permission:** current simulated ai_active call and calls:edit/owner
  scope. Target also requires an approved authorized destination and real media session.
- **Input:** transfer, simulated confirmation/failure or worker timeout.
- **Expected current states/records:** transferring/pending -> human_active/confirmed
  or ai_active/completed with failed/timed_out, versioned timeline. No provider contacted.
- **Failures/idempotency:** stale/wrong-state action conflicts; no real takeover or
  failure callback tool executes. Dynamic fake-audio clear is not a human bridge.
- **Existing tests:** mock transfer tests and dynamic audio contract tests.
- **Real acceptance:** answered destination/provider proof, rejected/busy/no-answer,
  duplicate request fencing, context permissions and no AI audio after human takeover.

### J. Recording/transcript/history

- **Preconditions/permission:** allowed recording action and owning call; completed,
  unexpired verified artifact for playback/transcript; separate download permission.
- **Input:** permitted PCM WAV, import key, consent reference, retention; optional
  bounded ordered operator transcript; delete/recovery version.
- **Expected states/records:** pending -> completed only after private encrypted
  write/read verification; failure/recovery/deletion_pending/deleted tombstone and
  audit. Expiry denies access before file cleanup. Transcript provenance is unverified.
- **Failures/idempotency:** replay/key fingerprint, wrong scope/range/format, truncated
  data, storage corruption/unavailability, failed physical deletion and retention retry.
  Replacement transcript currently loses old ciphertext (G05), not a fact-correction pass.
- **Existing tests:** test_voice_platform private-storage/parser/retention/range tests;
  inspected RecordingsPanel tests. These use real temporary file encryption/IO with
  synthetic bytes, not production recording storage.
- **Real acceptance:** real capture consent and media storage, scoped download/revocation
  races, approved retention/corrections and storage/DB crash reconciliation.

### K. Metrics, health and capacity

- **Preconditions/permission:** calls:view for dashboard; Owner for aggregate callback
  bookkeeping/config/probes; recording/knowledge counts honor their permissions.
- **Input:** status/query/period and worker ticks; later real event metrics.
- **Expected records/results:** mock call cohorts/timestamps, actual request/artifact
  counts, independently scoped heartbeat/evidence and null unavailable live metrics.
  Callback/live completions are not inferred from administrative Task completion.
- **Failures/idempotency:** stale/down components remain unknown/failed; repeated
  observations/workers do not fabricate live attempts. Existing probes have narrower
  meaning than actual conversation readiness; G10 definitions need alignment.
- **Existing tests:** dashboard/policy_studio/self_hosted/native/control tests.
- **Real acceptance:** event dedupe/cohorts/query plans, actual queue/media/latency,
  timezone boundaries, effective stop, real workload and measured alert thresholds.
  Health route, mock heartbeat or 10,000 stored recipients is not capacity evidence.

### L. Releases, rollback and environment separation

- **Preconditions/permission:** existing Owner settings/controls and knowledge approval;
  target needs immutable verified release selection and explicit activation authority.
- **Input:** edits/publication restore/component changes/policy update or rollback.
- **Expected current records:** existing CAS versions/publications/fingerprints;
  superseded local evidence/output after change. No composite live release exists.
- **Failures/idempotency:** stale versions conflict; expired publication cannot be
  activated; all production live enables denied. Shared model/assets/credentials
  are not fully isolated test/production environments.
- **Existing tests:** knowledge approved rollback, stale credentials, settings/
  publication/account changes during generation, policy/schema evidence invalidation.
- **Real acceptance:** per-call pinned release, verified rollback mid-call, preserve
  old histories, do not restore revoked secret/consent/permissions, retained managed
  Task/output-policy guards or disabled affected paths; actual staging restore rehearsal.

## 4. Required failure-injection coverage register

| Scenario | Current evidence, limitation and required acceptance |
|---|---|
| Unauthorized production enable | Current Owner/API and hard-denial tests pass; positive activation requires real future acceptance |
| Cross-tenant/cross-record access | Existing single-company record/owner denial tests; no multi-tenant architecture to certify |
| Wrong customer factor | Typed protected response held; real factor/session and retry lockout absent |
| Opt-out while callback pending | Current suppression blocks creation/confirmation and due review; verify immediate live pre-command denial later |
| Cancel while worker prepares dial | Current Task CAS race/negative dispatch; actual prepare/claim/dial path absent |
| Two workers same callback | Current atomic Task transitions; actual contact claim and provider command fencing still required |
| Duplicate/out-of-order provider events | Smartflo observation dedupe/order contracts, no native call reducer; actual PBX reconciliation required |
| PBX reachable without audio | Probe reports media false; actual no-audio watchdog/fallback needs runtime |
| STT works, TTS fails | Fake local failure contracts; real engines and media safe outcome required |
| TTS generates but delivery fails | Local artifact never caller-delivered; actual delivery acknowledgment/failure path missing |
| AI proposes unauthorized decision | Structural arbitrary-action/authority/protected response denial; content loophole G02 remains |
| Prompt injection | Typed authority and invalid action rejection; semantic model resistance not certified |
| Human destination does not answer | Mock transfer timeout/failure; actual PBX behavior and permitted follow-up required |
| Scheduled request becomes ineligible | Current DNC/consent/account checks; actual binding mutation/race and final dispatch revalidation required |
| Model/knowledge rollback during call | Current text-generation staleness tests; actual call pinning and streaming guard absent |
| Emergency during work | Existing controls/job-version checks and preview pause; no real drain/takeover proof |
| Queue at capacity | Current speech slots/campaign import/mock budgets; actual media concurrency/backpressure acceptance absent |
| Worker restarts after claim | Current Task recovery, campaign preview lease, speech interruption; actual call attempt receipt/reconcile missing |
| DB fails after provider accepts | No real call action implemented; future durable receipt/reconcile/failure tests mandatory |
| Recording storage unavailable | Synthetic private storage write/corruption/retention tests pass; actual live capture/storage acceptance absent |
| Language claimed but speech fails | No language accepted; actual representative per-language full path required |
| Simulator attempts production access/call | Strict policy-studio input/Owner and no-side-effect tests; no actual credential/provider call in suite |
| Customer corrects prior fact | Callback time/history tests; general fact memory absent and transcripts replace content |
| Multiple callback time changes | Current reschedule/history/fold preservation; add parent/principal lifecycle cases |
| Human takes over during pending AI audio | Offline interruption contract only; real exclusive audio ownership/session fencing missing |

## 5. Completion gates and preservation verification

Each capability needs separate evidence for: code, unit tests, real DB integration,
security, installed model, PBX/provider, end-to-end audio, approved staging,
production configuration and explicit activation. A synthetic pass fills none of
the real-runtime approval cells. Missing functionality is not only awaiting credentials.

Preservation verified: **all 1,097 pre-existing non-secret tracked/untracked files in
the snapshot are byte-for-byte unchanged; none removed. Exactly the five requested
new audit Markdown files were added.** Secret/environment/key files were excluded
from hashing and were not edited. All relative links in these five documents resolve;
the as-built contains six current-path Mermaid sequence diagrams. No rendering-engine
verification is claimed. `git diff --check` passed.

No destructive Git command, source/test edit, existing report overwrite, migration,
catalog/seed, model install, production health request or real call was performed.
**Production verdict: not production-ready.** This audit is complete; roadmap
implementation awaits the user's explicit review and approval.
