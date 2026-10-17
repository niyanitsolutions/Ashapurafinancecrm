# Voice integration execution — 17 October 2026

**Conclusion: Not production-ready.** This continuation completes specific safety,
date-preview and policy-regression units. It does not complete all twelve live
feature areas. Missing application work is distinguished from external acceptance.
No production deployment, restart, provider registration, model installation,
telephone call, commit or push occurred. Prior uncommitted callback work is retained.

## A. Existing workflow and integration order

The [audit and dependency map](VOICE_INTEGRATION_2026_10_17.md) was written before
implementation. The existing voice call state machine and simulation routes remain
unchanged. Authenticated staff use existing scoped CRM records and managed callback
Tasks. Optional local inference retrieves approved public knowledge. Local speech
jobs exercise isolated utterances, never a telephone media session. Platform controls
and emergency stop remain the existing hard live gate.

Inserted workflow:

1. Priority opt-out, wrong-number or human signals in the English text console cause
   an immediate safety hold without waiting for a model. This does not silently
   write a suppression or claim an escalation completed.
2. Approved public knowledge and conversation context reach the optional local model.
   Model output includes a typed intent, bounded confidence and proposed action.
3. Account/knowledge permission, inference enablement, settings/model configuration
   and current publication excerpts are rechecked after generation. Superseded
   outputs are discarded. Model-failure fallback also rechecks account permission
   and retrieves current sources; it cannot release previously authorized context
   after revocation.
4. Independent backend policy validates intent/action/citations. Protected case,
   payment and document requests require trusted caller verification and scoped
   tools, which do not exist yet. Their generated response is withheld. No model
   proposal can authorize a CRM action or claim caller verification.
5. Public answers require confidence >= 0.8, non-uncertain output, approved citation
   IDs and numeric consistency with cited excerpts. Unclassified/malformed/low
   confidence or inconsistent proposals are held. Generated clarification is allowed
   only as an uncertain clarification proposal, without a business action.
6. The same policy runs before local TTS. Withheld output cannot be synthesized.
   Local text/speech evidence fingerprints include policy version and answer schema,
   so old verification is not reused after those change.
7. Existing callback capture can preview a narrow English date expression using
   server time and the selected timezone. Ambiguity requires clarification. Applying
   a proposed date only fills the existing form; saving and confirming remain
   separate existing authenticated/versioned operations.

This remains a dynamic optional model path, not a fixed IVR or a predefined answer
catalog. The date grammar and synthetic tests are limited verification utilities,
not the live conversation runtime.

## B. Twelve-feature audit matrix

Test groups: **P** intent policy/service/speech tests; **T** callback time/API tests;
**S** persistent policy studio/API tests; **F** frontend tests/build; **R** full backend
regression. Exact final results appear in section E. All local DB tests use mongomock;
HTTP model fixtures and speech executables in unit tests are simulated.

| Area | Before | Changes / files | Verification | Remaining limitation |
|---|---|---|---|---|
| 1. Monitoring / agent assist | Mock state/timeline/control screens | Existing states preserved; no fabricated native events or live transcript | R; existing state/control tests | Native authenticated events, media diagnostics, takeover/termination still missing |
| 2. Customer memory | Scoped CRM notes/history and callback preference history | Preserved; no indiscriminate customer history injected into prompts | R; existing scope/callback tests | No identity-bound voice memory ingestion, structured facts/corrections, relevance/retention service |
| 3. Follow-up scheduler | Durable Task callback workflow, no interpretation | `callback_time.py`, callback router/schema/API, `CallbackTimePreview.tsx` | T/F; timezone/date/DST/ambiguity and explicit-apply tests | English preview only; no spoken-time extraction or real eligible dispatch/retries |
| 4. Human handoff | Simulation transfer request/confirm/failure | Human intent produces a non-executable escalation proposal; existing transfer semantics preserved | P/R | Actual PBX bridge/transfer, AI speech cancellation and receiver context not implemented |
| 5. Analytics | Simulation calls and imported/local processing counts | `service.py`: Owner-only real callback request/overdue counters, environment separated; live completions unavailable | S/F/R | No real call/audio/latency/cost/transfer outcomes or full historical report filters |
| 6. Intent / next action | Structured answer only | `intent_policy.py`, `conversation.py`, console UI: typed intent, confidence, limited entities, independent action mapping | P/S/F | No real model classification quality evaluation; confidence is model-reported, not calibrated |
| 7. Multilingual | Text codes / pinned speech profiles, no validated language | Existing profile restrictions preserved; no enabled language invented | R/F | No model-installed end-to-end language/accents/mixed-language acceptance |
| 8. Financial safety | Prompt instructions and no model tools | Server withholding, typed action allowlist, citation/numeric checks before text/TTS; identity remains false | P/S/R | Semantic factuality, coverage correctness and approved identity factors not verified; numeric checks are not entailment proof |
| 9. Simulator / studio | Mock calls / lexical article evaluations / local speech jobs | `policy_studio.py`, existing console routes, `PolicyStudio.tsx`: immutable built-in synthetic policy suite/reports, pagination, idempotency | S/F | Does not test a model, audio, accents, transfer, telecom or production credentials; no complete conversation simulator |
| 10. CRM tools | Staff callback APIs, no model tools | Typed non-executable action proposals; arbitrary actions and model identity flags rejected | P/S | Real trusted voice tool session/broker, field disclosure and human approval not implemented |
| 11. Health/recovery | Existing ARQ/probes/emergency/verification queue | Callback readiness heartbeat and scoped diagnostic counters; stale remains unknown | S/R | No real media loss detection, draining, capacity or native runtime failure acceptance |
| 12. Releases / rollback | Settings versions, knowledge publications, platform evidence | `speech_jobs.py` / `self_hosted_health.py`: policy+schema-bound evidence; console reports settings/publication/policy versions and discards superseded results | S/P/R | No immutable composite test/production release publication, call pinning or verified native live rollback |

The suite has 13 fixed synthetic proposal scenarios. They test policy mechanics,
not natural-language intent recognition. Its immutable stored reports include
suite/policy versions, synthetic inputs, expectations, actual decisions, author and
timestamp. They always report `activation_eligible=false`, no model/audio/telephony
test and zero CRM actions. A new report collection represents this distinct evidence;
it does not replace article evaluations or speech verification jobs.

## C. Workflow and state integrity

No call states or transfer success definitions changed. No new dialing/answering,
transfer, history-copying or positive activation endpoint exists. Original CRM and
callback history is retained. Existing callback Task CAS, idempotency, consent/DNC
and due-time checks remain authoritative; preview persistence is always false.
Concurrent duplicate policy test submissions are constrained by actor/suite/key.
Reports are append-only, with no edit/delete API. Failure does not authorize a call.

Analytics count Tasks, not worker executions or webhook deliveries. Today means
creation time from midnight in configured timezone to now; state is the request's
current state. Overdue means all currently active Tasks with due time before now,
regardless of creation date. These are administrative requests, not completed or
attempted calls. Test/production counters remain separate; aggregate access is Owner
only. Live callback completion is `null`, never falsely zero.

## D. Security and limitations

Existing auth/session/RBAC and single-company scopes are unchanged. Multi-tenancy
is deferred by architecture decision 001; cross-tenant isolation cannot be claimed.
Policy studio is Owner-only. Date preview requires existing calls:create and creates
no CRM records; subsequent create still enforces full entity/Task/voice permissions.
Model proposals cannot carry trusted customer identity, consent, roles or arbitrary
tools. Caller phone match remains insufficient proof. No customer-specific financial
data or protected tool result is supplied to the model by this continuation.

Public response permission does not certify financial meaning. Confidence is not
calibrated and numerical matching cannot establish that terms are applicable or
correct. Semantic hallucination/injection resistance and multilingual safety need
real model adversarial evaluation. Production remains blocked for these reasons.
Existing local-model origin allowlists, bounds, deadlines and server-side secrets
remain in force. Policy audit metadata contains IDs/versions, not user questions.
Studio fixtures contain only built-in synthetic content. Python advisory matching
remains offline as requested; `pip check` is dependency consistency, not an audit.

## E. Verification

Final full backend regression: **1,368 passed, 1 skipped**, 568 existing deprecation
warnings, 581.79 seconds. The skip is the existing Linux-only process test on this
Windows workstation; no test was newly skipped. Executed focused
checks: 86 backend passed/1 Linux-only skipped; later affected policy/health/
speech checks 50 passed/1 skipped; final policy-studio focused checks 10 passed.
Frontend focused: 13 passed across four files. Backend Ruff passed; scoped Linux
mypy passed across 54 source files; Python dependency consistency passed.
Frontend TypeScript passed. ESLint has zero errors/10 existing warnings. Production
build passed with the existing bundle-size warning. These are local checks only.

Full frontend regression: **353 passed across 72 files**, 167.55 seconds. Existing
jsdom canvas/unhappy-path logging remains. Global Linux mypy: **116 existing errors
in 11 files, 377 source files checked**; no new voice-module error is reported.

One initial test collection error used pytest's reserved `request` name; corrected
without skipping tests or weakening assertions. An early full backend run was
stopped to close permission-revocation behavior on model-failure fallback; it is
not counted as a passing regression. Runtime source is frozen for the final run.

Browser captures use synthetic intercepted API responses and system Chrome through
the previously approved local Playwright harness. They do not contact a provider
or real customer. Callback preview and policy studio were captured at 1440/390px
with no page errors/document overflow. See [metadata](screenshots/voice-integration-2026-10-17/evidence.json).
Actual local models, native PBX, telecom, full audio path, Linux process behavior,
actual MongoDB indexes/concurrency and the production environment were not tested.

The two desktop sidebar crops are pixel-identical to their previous Lead/Settings
captures: [comparison](screenshots/voice-integration-2026-10-17/sidebar-comparison.json).
Only the screenshot harness needed a scroll reset after element captures; no
sidebar/application layout change was made. Mobile detail captures were inspected:
[date preview](screenshots/voice-integration-2026-10-17/callback-time-390-detail.png),
[policy studio](screenshots/voice-integration-2026-10-17/policy-studio-390-detail.png).

## F. Acceptance blockers and evidence required

Requested failure scenarios are not all live-testable here. The following distinguishes
available contract/regression coverage from genuinely missing execution paths:

| Scenario | Available evidence / outstanding requirement |
|---|---|
| 1. Unauthorized activation | Existing platform/native/API permission tests; hard live denial |
| 2. Cross-tenant access | Existing cross-record/owner scope tests only; multi-tenancy is deferred, not tested |
| 3. Wrong identity factor | Protected proposal withholding tested; real verification factor/session absent |
| 4. Opt-out pending callback | Existing due-review suppression test and existing contact-policy API coverage |
| 5. Cancel during dial preparation | Callback CAS race tested; actual claim/dial path absent |
| 6. Two callback dial workers | Existing callback state CAS / campaign preview fences; no live callback executor to test |
| 7. Duplicate/reordered events | Existing Smartflo authenticated-event contract tests; no actual native PBX acceptance |
| 8. PBX reachable/no audio | Read-only probe explicitly cannot verify media; native media runtime absent |
| 9. STT success/TTS failure | Existing local speech failure/queue contracts; real installed-engine acceptance pending |
| 10. TTS audio/delivery failure | Local generated audio is never marked caller-delivered; real transport absent |
| 11. Unauthorized financial action | Typed proposal rejection and protected response withholding tested |
| 12. Prompt injection | Model authority/arbitrary-action rejection and injection-like date input tested; semantic model resistance unverified |
| 13. Transfer destination unanswered | Existing mock transfer timeout/failure only; actual PBX transfer absent |
| 14. Callback becomes ineligible | Existing DNC, consent, changed account/binding readiness checks; no actual dispatch |
| 15. Version changes in flight | New settings/publication/account revocation and schema/policy evidence invalidation tests; real calls absent |
| 16. Emergency during activity | Existing platform/preview/local-job controls and mock call tests; real active-call drain absent |
| 17. Queue at capacity | Existing campaign preview and speech verification limits; live media capacity unmeasured |
| 18. Restart after callback claim | Existing durable Task recovery; no live callback claim/attempt executor |
| 19. DB fails after provider action | No actual provider action implemented; durable reconciliation/outbox acceptance pending |
| 20. Recording storage fails | Existing private-storage corruption/write/recovery/retention tests; live capture absent |
| 21. Claimed language fails | No language accepted; actual representative speech-model tests pending |
| 22. Simulator production access/call | Strict Owner suite input rejects production/scenario injection; no model/provider/tool invoked; live gate tests remain |
| 23. Correction to stored customer fact | Callback preference/time history retained; general verified customer fact memory absent |
| 24. Multiple time changes | Existing callback reschedule/CAS/history plus new date/DST preview tests |
| 25. Human takeover while speech pending | Existing bounded mock audio/interruption contracts only; actual native takeover/AI audio cancellation absent |

All existing suites are included in the final regression; none of these descriptions
asserts real telecom/audio evidence from mocks. Missing scenarios remain acceptance
blockers rather than being replaced with tests that merely assert a flag is false.

1. Existing server inventory/access is unavailable: run the reviewed read-only
   inventory through the existing authorized session. Measure OS/CPU/RAM/disk/GPU,
   Docker, unit paths, load and available capacity before selecting models/hardware.
   Rechecked locally: SSH client is installed, but no named SSH configuration exists.
   No private key, credential, guessed host or server session was used.
2. No approved SIP trunk/number or verified PBX version/contracts: establish telecom
   authorization and actual deployed native control/media support before implementing
   and accepting dialing, event reconciliation, bridging, interruption and transfer.
3. No approved installed speech/model stack: pin licensed assets, verify isolated
   Linux runtime, deadlines/resource budgets and actual multilingual audio/latency.
4. No approved additional caller verification factor or identity session: define
   the policy, implement a trusted backend session and scoped tool broker before
   protected CRM status, memory or customer-specific actions.
5. Missing native application execution: implement real call control/media, contact
   reservation, dispatch/retry/outcome recovery, live suppression/stop/drain and
   human takeover. Require real duplicate/reordered/dropped-event and crash tests.
6. Missing immutable composite releases and pinned per-call configuration: implement
   publication/rollback compatibility and actual in-flight behavior. A policy test,
   saved setting or old functional request does not satisfy release approval.
7. Run real MongoDB migration/race/failure tests, storage outages and complete target
   end-to-end security/audio acceptance. Ten simultaneous calls/10,000 recipients is
   an unmeasured target, not capacity. Then obtain explicit production activation.

## G. Deployment and rollback

See [current deployment/rollback handover](VOICE_INTEGRATION_OPERATIONS_2026_10_17.md).
User-supplied backend/frontend paths, existing venv, domain and systemd unit names
are preserved. No environment file or dependency lock changed. No destructive
commands were executed. Callback-compatible rollback must retain managed Task
guards and all history; new synthetic reports need no destructive down migration.
Rollback also retains the text/speech policy guard, or inference and speech testing
must stay disabled; emergency stop is not a substitute for this compatibility check.

## H. Remaining work in dependency order

Measured host/PBX/provider/number and policy decisions -> pinned model/speech runtime
-> native call events/control/media -> trusted caller identity and scoped tools/
memory -> real dispatch, transfer and emergency handling -> call-pinned releases
and trustworthy analytics -> adversarial/real DB/target load/end-to-end acceptance
-> separately approved publication and activation. These remain outstanding; they
are not represented as implemented merely because a screen or contract exists.
