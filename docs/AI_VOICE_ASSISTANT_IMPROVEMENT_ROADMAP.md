> **Implementation update ? 17 October 2026: NOT COMPLETE / NOT PRODUCTION READY.**
> Implementation is authorized by the current request; earlier text requesting separate approval to begin source work is historical and superseded. Phase 0 has implemented/tested local safety and recovery changes but its exit gate is FAIL. Native runtime, trusted caller policy/tools, real dispatch/transfer, composite releases and target-runtime evidence remain required. The Owner requires self-hosted components and selected option 8 (continue locally); no infrastructure installation, production action or real call is authorized.
> See [current implementation, traceability and execution evidence](VOICE_HARDENING_EXECUTION_2026_10_17.md) and [self-hosted staging contract](VOICE_SELF_HOSTED_STAGING_CONTRACT.md).
> The original audit below is retained verbatim as historical baseline evidence; its statements about unchanged source, findings, test counts and pending implementation approval describe that earlier audit, not this worktree.

> Final local verification: **1,408 backend passed / 1 Linux-only skip; 354 frontend passed; build passed**. These are local/mock/synthetic results, not PBX, installed-model or staging acceptance. See the execution report for commands, warnings, earlier failures and remaining gates.

---

# AI Voice Assistant — workflow-preserving improvement roadmap

17 October 2026. **Recommendation only; no item has been implemented in this audit.**
Changes require the user's review and explicit implementation approval. Preserve
all current uncommitted work, CRM lifecycles, single-company scope/Owner semantics,
sidebar, credentials, existing APIs and history. Reuse the architecture documented
in [as-built](AI_VOICE_ASSISTANT_COMPLETE_AS_BUILT.md) and
[canonical workflow](AI_VOICE_ASSISTANT_CANONICAL_WORKFLOW.md).

Finding IDs refer to the [gap analysis](AI_VOICE_ASSISTANT_GAP_ANALYSIS.md). Each
phase is a dependency gate, not a delivery-date/cost estimate. No phase itself
authorizes telecom activation, installations, paid services or production deployment.
No immediate production P0 exploit was established; Phase 0 is the requested safety
and data-integrity prerequisite phase, not an inflated P0 severity classification.

## Phase 0 — Safety, data integrity and unsafe-operation blockers

### R0.1 — One reviewed output policy before every speech/text delivery

- **Reason:** G01/G02; registered console/local utterance guards and unregistered
  streaming core differ. A structurally valid clarification can contain an assertion.
- **Reuse / likely files:** V/intent_policy.py, conversation.py, service.py,
  local_pipeline.py, dynamic_audio.py; existing model schemas and approval retrieval.
- **Order:** agree public/clarification versus protected-response contract first;
  keep streaming unregistered until it shares the policy/session boundary.
- **Migration/compatibility:** additive output evidence/schema version, retain old
  callers' parsing contract but withhold unsafe/missing policy results. Invalidate
  verification fingerprints on change. Do not turn this into a fixed-answer IVR.
- **Security:** never let model confidence, intent, source IDs or identity flags
  grant disclosure/CRM execution. Gate current session/turn/config before delivery.
- **Tests:** synthetic assertion-in-clarification, uncited rates/terms, wrong citations,
  prompt injection, model outage and stale generation; prove synthesis/send not invoked.
- **Acceptance:** all registered and future streaming outputs pass the same reviewed
  server boundary; actual-model financial/injection acceptance is separately required.
- **External prerequisite:** approved financial response policy and approved model
  for semantic evaluation; unit-level mechanics do not need telecom access.
- **Regression risk:** high for answer availability/latency; retain explicit withheld
  states and current retrieval-only fallback rather than relaxing assertions.

### R0.2 — Preserve evidence and resolve managed Task lifecycle failures

- **Reason:** G05/G07/G08; capped history, replaceable transcripts, stranded callbacks
  and separate domain/audit writes undermine correction/rollback guarantees.
- **Reuse / files:** existing Task embedded callback history, RecordingService,
  VoiceService knowledge/settings, native/platform/contact histories, shared audit;
  CRM deletion/restore services and existing migration scripts.
- **Order:** define retention/provenance and recovery ownership; then add append-only
  revision/receipt references and parent/principal cancellation/adoption hooks.
- **Migration/compatibility:** additive backfill from retained snapshots only; mark
  older missing content unknown. Never fabricate lost revisions. Preserve all old
  records and version IDs; maintain rollback-compatible managed Task guards.
- **Security:** orphan closure/adoption must preserve minimum record access without
  revealing deleted customer data. DNC remains independent and cannot be bypassed.
- **Tests:** >20/100/200 updates, transcript correction, parent delete/restore/purge,
  creator deactivation/reassignment, expired request followed by DNC, audit-insert
  failure/replay and concurrent lifecycle transitions on real MongoDB as well as units.
- **Acceptance:** old known content stays traceable, no active unique slot becomes
  irrecoverable, and global audit/receipt gaps are reconciled without data deletion.
- **External prerequisite:** retention/legal and operator recovery policy; actual
  MongoDB staging permissions/backups before migration.
- **Regression risk:** high for data size/deletion behavior; stage with snapshot
  backup, bounded revision storage and reviewed non-destructive rollback.

### R0.3 — Explicit emergency and rollback compatibility contract

- **Reason:** G06/G09; platform live stop, local testing, campaign pause and simulator
  mode have different scopes. No real call drain exists.
- **Reuse / files:** PlatformService, CampaignService.emergency, VoiceService.sweep,
  SpeechJobs.current, U/PlatformControlsPanel, existing operations guides.
- **Order:** define which work is allowed in each state before adding any positive
  native command. Preserve intentional synthetic testing separately from live work.
- **Migration/compatibility:** keep existing emergency APIs; compose a shared live
  enforcement contract. Do not silently reinterpret old booleans or auto-enable on upgrade.
- **Security/tests:** stale clients, simultaneous disable/enable requests, pending
  generation/synthesis, transfer and rollback; assert no new restricted command or
  stale audio after stop. Verify active-call drain on actual PBX later.
- **Acceptance:** UI text matches server scope, old rollback cannot restore unguarded
  text/speech or mutable managed Tasks, and stop wins over stale configuration.
- **External prerequisite:** approved live-call drain/human fallback behavior and PBX
  capabilities; no blanket “kill all calls” assumption.
- **Regression risk:** medium/high; preserve useful bounded local diagnostics while
  making their non-live scope unmistakable.

## Phase 1 — Complete the existing core voice workflow

### R1.1 — Verify target runtime and telecom contract before selecting assets

- **Reason:** G03/G13/G14; no actual host/PBX/model/approved trunk evidence.
- **Reuse / files:** scripts/voice-server-inspect.sh, native probe/config/number
  services, current Docker/systemd handover and speech profile structures.
- **Dependencies:** reviewed administrative connection, actual OS/CPU/RAM/disk/GPU,
  deployed PBX version/modules, approved trunk/number/directions and licenses.
- **Migration/compatibility:** no assumed infrastructure change. Record measured
  evidence and select compatible services; preserve user-supplied paths/env/unit names.
- **Security:** exchange credentials only through existing secure server-side paths;
  use bounded read-only probes before authorizing real calls.
- **Tests/acceptance:** signed-off inventory and documented actual capabilities,
  network/TLS/origin rules and numeric capacity proposal based on measurements.
- **External prerequisite:** operator/telecom approval, real host access and model
  service choice. Ten calls/10,000 recipients remains a target until measured.
- **Regression risk:** low for read-only inventory; high for later deployment choices,
  therefore recommend a separate server/upgrade only after measurements justify it.

### R1.2 — Native event/control/media pipeline and real Owner-first inbound behavior

- **Reason:** G03/G12; mock ringing and read-only ARI are not call establishment.
- **Reuse / files:** TelephonyAdapter ports, NativeVoiceService/AsteriskReadOnlyAdapter,
  CallSession/VoiceRepository state/CAS, media_contracts, DynamicAudioConversation
  after R0.1, current API/router and workers.
- **Dependencies/order:** R0 safety and R1.1 verified version/contracts -> durable
  call reservation/action receipt -> authenticated event correlation/reducer ->
  actual ring/answer/media -> reconciled terminal outcomes. Implement Owner/assigned
  human-first timeout at the real routing layer before AI fallback.
- **Migration/compatibility:** additive actual-provider/customer/entity/number/release
  bindings and native state mapping; retain historical mock records and their meaning.
  New states need explicit mapping, not reuse of mock success as actual evidence.
- **Security:** authenticate every event/media session, enforce call-specific controls,
  capacity/stop/number authorization and stale-command fencing. No guessed carrier APIs.
- **Tests:** duplicate/reordered/missing events, no answer/busy, wrong identity,
  reconnect/drop, call control timeout and DB failure after provider acceptance.
- **Acceptance:** authorized test number rings, actual supported answer/media events
  establish one scoped session; no success on request acceptance alone. Owner-first
  duration and timeout/fallback demonstrated with timestamps.
- **External prerequisite:** approved test-call workflow, PBX/trunk/number/media access.
- **Regression risk:** high; leave live enablement unavailable until acceptance and
  preserve a compatible artifact/data rollback without destroying history.

### R1.3 — Connect verified speech/model services to actual bidirectional audio

- **Reason:** G01/G03/G13; current utterance tests reload local CLI models and retain
  WAV artifacts, without live streaming or delivery confirmation.
- **Reuse / files:** speech_runtime/speech_process, LocalConversationAdapter,
  LocalUtterancePipeline, media_contracts and common guarded dynamic core.
- **Dependencies/order:** matching codecs/sample rates and R1.2 session -> installed
  approved STT -> dynamic model/public knowledge -> R0 output guard -> TTS -> real
  delivery marks/acknowledgment and interruption fencing.
- **Migration/compatibility:** approved pinned profiles and versioned evidence;
  existing local verification remains useful and separately labelled.
- **Security:** isolated unprivileged runtime, network policy, package/image pins,
  secret-free child environment and per-stage deadlines/resource budgets.
- **Tests/acceptance:** actual STT/model/TTS, silence/audio loss, partial/final text,
  STT success/TTS failure, generated audio/delivery failure, barge-in and pending
  output after takeover/stop. A local WAV alone cannot pass acceptance.
- **External prerequisite:** installed licensed assets, measured compatible compute,
  approved speech/AI service and real media test authorization.
- **Regression risk:** high latency/resource/codec risk; preserve independent adapter
  replacement and bounded backpressure, without silently dropping protected output.

## Phase 2 — Complete advanced features at their dependency points

### R2.1 — Trusted caller verification, scoped CRM tools and conversation memory

- **Reason:** G04/G05; protected information and customer-specific operations cannot
  safely execute from staff authentication or a model's self-asserted customer ID.
- **Reuse / files:** existing customer/Lead/case services, notes/status history,
  callback APIs, PermissionEngine, typed intent/action contracts and private artifacts.
- **Dependencies/order:** approved factor/disclosure policy -> canonical call/customer
  binding -> trusted expiring/revocable session -> minimal field reads -> authorized
  tool actions/approval -> provenance summaries/facts/corrections and relevant memory.
- **Migration/compatibility:** additive links and provenance; keep original timestamps,
  corrected facts and notes. No duplicate Customer collection or incidental tenant migration.
- **Security:** strict tool schemas, object/field scope and current permission/consent
  checks on every action; no arbitrary database/status/underwriting operation.
- **Tests/acceptance:** wrong/replayed factors, phone ambiguity, cross-record access,
  revoked session/grants, injected IDs, corrected facts and minimum-context prompts;
  only verified caller's permitted fields disclosed, actions recorded once.
- **External prerequisite:** approved additional identity factor, retention/disclosure
  policy and representative authorized end-to-end test cases.
- **Regression risk:** high confidentiality/history risk; keep protected tools denied
  until both identity and field-level acceptance pass.

### R2.2 — Real callback dispatch and smart human handoff

- **Reason:** G03/G07/G08/G11; Tasks and dry-run leases do not execute eligible calls
  or prove a receiving human answered.
- **Reuse / files:** canonical CallbackService/tasks and ARQ wrapper, scheduling and
  contact policies; existing transfer states; native provider/action receipt from R1.
- **Dependencies/order:** resolve purposes/windows and lifecycle recovery -> atomic
  due claim + contact/capacity reservation -> immediate eligibility/stop recheck ->
  native attempt -> event-confirmed result -> bounded allowed retry/escalation.
- **Migration/compatibility:** add attempt/claim/fence references under existing Task
  rather than a competing scheduler. Keep existing administrative closure meaning and
  distinguish call outcome from task completion. Preserve all previous due dates.
- **Security:** cancellation/DNC/supersession must defeat stale claims; human handoff
  requires destination authorization and exclusive audio ownership, not request success.
- **Tests/acceptance:** two workers, restart after claim, cancel/opt-out mid-prepare,
  actual no-answer transfer, answered human takeover, eligible retry/backoff and
  prohibited retry. Exactly one permitted attempt per reservation; no cancelled call.
- **External prerequisite:** approved live purpose/retry/frequency rules, actual
  transfer mode/destinations and authorized test contacts.
- **Regression risk:** high duplicate-contact risk; retain unconditional live denial
  until the complete attempt/result/failure path is accepted.

### R2.3 — Composite releases and approved multilingual capability

- **Reason:** G06/G13; saved config/snapshots are not a published release and a text
  language code is not accepted speech support.
- **Reuse / files:** settings/publications, PlatformService evidence, inference and
  profile fingerprints, PolicyStudio/KnowledgeEvaluation/SpeechJobs evidence.
- **Dependencies/order:** immutable component/prompt/knowledge/action/policy/language
  references -> candidate evaluation -> explicit approved test publication -> per-call
  pin -> separately approved production selection/rollback.
- **Migration/compatibility:** additive release manifest/references without restoring
  secrets/permissions/consent from snapshots. Explicit shared-versus-isolated services;
  no automatic activation. Keep historical calls on their original versions.
- **Security/tests:** rollback during generation/calls, revoked credentials/policy,
  unsupported language claims, identifier/amount preservation, switching/fallback and
  mixed-language failures. Require representative end-to-end audio per enabled language.
- **Acceptance:** release evidence identifies what was actually tested and approved;
  unverified language/release cannot be selected for live operation; rollback remains safe.
- **External prerequisite:** model/voice licenses, language samples and human reviewers,
  approved test/production isolation and publication authority.
- **Regression risk:** high compatibility risk; retain mandatory current security/stop
  gates outside the restorable release content.

## Phase 3 — Reliability, monitoring, verification and operational hardening

### R3.1 — Real-runtime acceptance matrix, durable failure recovery and migrations

- **Reason:** G08/G13/G14/G17; current mock tests cannot certify DB/provider/audio
  behavior or all advertised failure cases.
- **Reuse / files:** T/test_voice_*.py, frontend component tests, W cron functions,
  existing catalog/index scripts and actual native test harness developed in R1/R2.
- **Dependencies:** complete runtime/action/release paths; approved staging with
  real MongoDB, PBX and pinned models; domain backup/recovery plan.
- **Migration/compatibility:** repeatable additive migration/index verification before
  workers, snapshot backups, no destructive reset/seed. Prove recovery after partial
  writes and restore old artifacts only when guards/data remain compatible.
- **Security/tests:** entire acceptance matrix including actual identity, duplicated/
  reordered events, worker death, storage outage, provider acceptance then DB failure,
  emergency and revoke; retain tests with honest real/fake boundaries.
- **Acceptance:** signed evidence per code/unit/security/model/PBX/audio/staging/
  production-approval gate, with missing/failed evidence stopping activation.
- **External prerequisite:** approved test calls and actual target environment. Keep
  Python advisory inventory offline using an approved local advisory dataset; report
  coverage/freshness rather than claiming pip check is a vulnerability audit.
- **Regression risk:** high operational risk; rehearse restore and validate normal
  Lead/Loan/Insurance/Task workflows before any release.

### R3.2 — Sourced analytics, health, capacity and alerting

- **Reason:** G10/G16; health granularity and metrics do not yet describe actual calls
  or establish ten simultaneous audio conversations.
- **Reuse / files:** VoiceService.dashboard, worker-health records, detailed native/
  local test evidence, existing reporting infrastructure, scopes and timezone helpers.
- **Dependencies:** trustworthy real attempt/media/transfer events and versioned
  session outcomes; definitions before aggregation/visual design.
- **Migration/compatibility:** keep existing mock metrics separated; additive metrics
  with source/cohort/denominator, null unavailable values and reconciled event identity.
- **Security:** report permissions/minimum data, redacted diagnostics and no raw
  transcript/customer data in general alerts or logs.
- **Tests/acceptance:** query plans and real staged load, timezone boundaries,
  dedup/reconnect/retry counting, queue wait/depth and model/media/worker failure alarms;
  compare requested 10 concurrent calls and 10,000 recipients against measured budgets.
- **External prerequisite:** agreed service-level/lag targets and sufficient measured
  hardware, not a fabricated instance specification.
- **Regression risk:** medium DB/query overhead; optimize only measured bottlenecks
  rather than introducing another broker, database or dashboard.

## Phase 4 — Optional optimization and cleanup

### R4.1 — Consolidate proven overlap and correct scope presentation

- **Reason:** G12/G15/G16; overlapping protocol types, static/stale messages and
  reserved settings can confuse maintenance/operations; no removal candidate is proven.
- **Reuse / files:** media_contracts/dynamic_audio protocol ports, U section messages,
  API types, detailed readiness services and existing provider fixtures.
- **Dependencies:** working accepted runtime and complete caller/contract inventory.
- **Migration/compatibility:** adapter compatibility layer before a common speech
  port; deprecate settings/routes only with approval, external client check and
  reversible versioned migration. Offline Exotel/Smartflo fixtures have test value.
- **Security/tests:** keep all negative capability/authorization tests; verify no
  unsafe fallback is introduced and no former fixture is mistaken for a live adapter.
- **Acceptance:** fewer contradictory labels/types without losing supported behavior,
  historical evidence, rollback compatibility or administrator choices.
- **External prerequisite:** business confirmation of retained providers/fields and
  deployment/external consumer inventory before any removal.
- **Regression risk:** medium; optional cleanup is last, not a prerequisite to rewrite
  the current application. No trendy feature or architectural replacement is proposed.

## Activation and handover gate

Only after all relevant prior acceptance criteria pass: explicitly review production
configuration, caller/consent policy, target-runtime evidence, monitoring, backup and
rollback artifacts, then separately approve activation. Deployment/restart/migration,
credential save or successful synthetic test must never activate calling. This audit
neither performs those steps nor requests credentials in chat.
