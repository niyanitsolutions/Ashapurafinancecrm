> **Implementation update ? 17 October 2026: NOT COMPLETE / NOT PRODUCTION READY.**
> G01 now has shared offline policy/authorization/fencing coverage. G02 arbitrary clarification assertions and unsupported public paraphrases are denied; public factual output must match a complete approved cited excerpt. Actual financial-source and adversarial model acceptance remains blocked. G05 transcript correction ciphertext is retained until artifact deletion, but other capped histories remain unresolved. G07 local lifecycle/Owner closure and G08 callback audit repair are implemented; actual Mongo races and other-domain receipts remain unresolved. G10 metric definitions and G11 callback purpose defaults are corrected within their documented scope. G03/G04/G06/G09/G12/G13/G14/G16 remain open in whole or in their outstanding runtime portions; no whole-phase completion is asserted.
> See [current implementation, traceability and execution evidence](VOICE_HARDENING_EXECUTION_2026_10_17.md) and [self-hosted staging contract](VOICE_SELF_HOSTED_STAGING_CONTRACT.md).
> The original audit below is retained verbatim as historical baseline evidence; its statements about unchanged source, findings, test counts and pending implementation approval describe that earlier audit, not this worktree.

> Final local verification: **1,408 backend passed / 1 Linux-only skip; 354 frontend passed; build passed**. These are local/mock/synthetic results, not PBX, installed-model or staging acceptance. See the execution report for commands, warnings, earlier failures and remaining gates.

---

# AI Voice Assistant — evidence-based gap analysis

17 October 2026; current worktree including prior uncommitted changes, HEAD `6ffa4e8`.
Audit only: no finding was fixed and no code/configuration was removed or edited.
See [as-built evidence, paths and API inventory](AI_VOICE_ASSISTANT_COMPLETE_AS_BUILT.md).
V/U/T/W retain the path abbreviations defined there. Scope is relevant voice/CRM
integration, not a penetration-test certification of every unrelated CRM feature.

## Severity and overall finding

- **P0:** no immediate exploitable live-call operation or confirmed production data
  disclosure was established. This is not proof of absence; no production system was accessed.
- **P1:** mandatory implementation/safety/runtime acceptance blockers before real calling.
- **P2:** demonstrated current workflow, history, observability or recovery gaps.
- **P3:** bounded cleanup/presentation opportunities after core correctness.

The system is **not production-ready**. Several local subsystems are implemented,
but a positive native telephone/media path does not exist. Neither blanket “missing”
nor blanket “implemented awaiting credentials” accurately describes the platform.

## All twelve advanced areas

| Area | Independently existing capabilities and exact anchors | Missing/partial, misleading or dependent parts | Improvement / acceptance |
|---|---|---|---|
| 1. Live monitoring and agent assist | U/CallsPanel -> V/router call routes -> VoiceService.scope/list_calls/call/act and voice_calls; polling and versioned mock timeline work | No native event reducer, live transcript, media-loss/silence/latency alarms, monitored real call or authorized takeover. Assigned employee metadata does not implement ringing/access | G01/G03; bind authenticated events and scoped call controls, test stale controls, interruption and actual provider failures |
| 2. Customer 360 memory | Existing CRM notes, scoped Lead/Loan/Insurance services, managed Task request/history, imported encrypted artifacts | No canonical real call/customer binding, verified fact store/corrections, scoped relevance retrieval, automatic summaries or caller-bound memory; transcripts are replaceable | G04/G05/G07; first trusted identity, then provenance/corrections and selective access without cloning customers |
| 3. Intelligent follow-up | V/callback_time, scheduling, CallbackService, existing tasks; W/review_voice_callbacks; U/CallbacksPanel/CallbackTimePreview | Preview is limited English grammar, not spoken extraction. Scheduled Task does not dial. No live reservation/attempt/retry/outcome worker. Parent/principal lifecycle can strand active requests | G03/G07/G11; preserve canonical Tasks, add real dispatcher only after eligible identity/transport and cancellation fencing |
| 4. Smart handoff | VoiceService.act/transition/sweep and CallsPanel simulate pending/confirmed/failed/timed-out transfers | No actual destination selection, availability, bridge, human context package, takeover/audio cancellation or failed-transfer callback workflow | G03/G04/G09; provider-confirmed outcomes and exclusive human/AI media ownership |
| 5. Analytics | VoiceService.dashboard distinguishes mock metrics, actual callback bookkeeping and artifact counts; Owner aggregate scope | No real attempts, delivered audio, resolved outcomes, cost, real latency or call-quality cohort. Some labels/static statuses differ from detailed probes | G10/G13; source-defined real events and denominators, timezone/report filters and measured aggregation plans |
| 6. Intent/next action | V/conversation.GeneratedAnswer/IntentProposal -> intent_policy -> console UI; policy suite persists expected/actual decisions | Model confidence uncalibrated; optional intent fails closed when absent, but valid unclear proposal text is not semantically validated; streaming path omits policy | G01/G02; adversarial real-model evaluation and common policy boundary before every output/action |
| 7. Multilingual | Text language fields, AudioFormat contracts, profile language/hash/version, whisper/Piper verification code | No accepted speech language, real switching/identifier/fallback service or mixed-language quality evidence. Piper verification only English. Dropdowns are not capabilities | G13; approved matching profiles, representative financial names/amounts and complete audio pipeline per language |
| 8. Financial guardrails | No model CRM tool execution; registered console/local pipeline hold protected intents, validate citations and some numeric tokens | Caller identity absent; classification and “uncertain clarification” do not establish output safety or semantic grounding; no actual-model injection/financial accuracy acceptance | G01/G02/G04; fail closed at disclosure/action boundaries, narrowly validated public answers and approved financial review |
| 9. Simulator/testing studio | Mock calls; KnowledgeEvaluation lexical reports; PolicyStudio synthetic proposal reports; SpeechJobs verification queue | Three deliberately distinct test scopes, not a full voice scenario engine. No actual accent/media/transfer/customer-verification test orchestration or publication gate | G06/G13; keep scopes explicit and build traceable scenario-to-real-runtime evidence |
| 10. CRM tools | Real staff callback and Owner contact-policy APIs; typed proposed_action allowlist has execution_allowed=false | No trusted voice tool/session broker, field projection, idempotent executed-action receipts or human approval. Some services assume router authorization | G04/G08; reuse scoped services through explicit server-authorized tools, not model IDs/claims |
| 11. Health/capacity | ARI/User read probes, structured text test, local speech evidence, bounded queues/leases and separate heartbeats | Real host/PBX unknown; health does not prove media/delivery/capacity; package/network isolation incomplete; no measured ten-call acceptance | G09/G10/G13/G14; actual inventory, isolated pinned services, per-stage evidence and load/failure acceptance |
| 12. Releases/rollback | Knowledge publications/evaluations/restore; settings snapshots; platform version/CAS; model/schema/policy fingerprints | No composite immutable test/production release, approval manifest, per-call version pin or live rollback. Shared infrastructure and capped histories | G05/G06/G08; preserve existing contracts and add immutable version references plus guarded activation/rollback |

## G01 — P1: policy enforcement differs between conversation engines

**Evidence:** V/service.py:VoiceService.console and V/local_pipeline.py:
LocalUtterancePipeline.respond invoke `proposal_policy`. V/dynamic_audio.py:
DynamicAudioConversation._generate validates text length/citation IDs, but proceeds
to synthesis without that policy or current account/publication/config rechecks.
Repository callers of the streaming engine are tests in `test_voice_smartflo.py`
and `test_voice_platform.py`; no live route instantiates it. It is not a current
remotely callable live bypass.

**Effect:** treating its existing interruption tests as proof of a safe live core
would introduce a different safety boundary. Keep it unregistered until policy,
trusted session authorization, publication pinning and turn/delivery fencing are
shared. Tests must show unsafe/stale/opted-out/cancelled output never reaches the
synthesizer or transport, including human takeover while synthesis is pending.

## G02 — P1: structured classification is not response-content proof

**Evidence:** V/intent_policy.py:proposal_policy permits `unclear` with confidence
at least 0.8, `proposed_action=clarify`, and `uncertain=true` without inspecting whether
the response actually asks a clarification or asserts financial facts. Citation/numeric
checks apply to the product-information branch. Audit ran a synthetic pure-function
probe: this branch returned response_allowed=true, execution_allowed=false and
customer_verified=false for arbitrary synthetic assertion text. No customer or model
was involved. Numeric-set consistency and valid source IDs also do not prove that
the cited fact supports the meaning of a public answer.

**Effect:** prompts and a model-selected enum cannot certify safe financial output.
Current console is a warned test tool; no live deployment/exploit was verified.
Require output content/semantic tests, stricter clarification constraints and actual
model adversarial evaluation before customer-facing speech. Do not solve this by
turning dynamic conversation into an unreviewed fixed-answer IVR.

## G03 — P1: native call, media and handoff execution are unimplemented

**Evidence:** V/models.py:CallSession permits provider `mock` only; V/native_adapter.py
implements read-only ARI probes. Smartflo resolver rejects and media socket closes;
Exotel live methods call `blocked`. Native number activation and PlatformService
activation always deny. No actual dial/answer/bridge/transfer adapter is registered.

**Effect:** inbound Owner-first ringing, outgoing CRM initiation, barge-in, live
monitoring, real completion and future callback execution cannot function. This is
missing code plus unverified telecom/PBX approval, not just credentials. Reuse the
adapter ports and states but add a documented version-bound native runtime with
authenticated events, reconciliation and bidirectional media. Verify actual PBX
events, timing, failure, transfer and delivered audio before enabling directions.

## G04 — P1: caller identity, protected tools and canonical memory are missing

**Evidence:** `customer_verified=false` and `execution_allowed=false` are unconditional
policy outputs. No voice-factor/session/attempt routes exist. MockCallInput has no
customer/entity binding; current source-call linkage for callbacks rejects all mock
calls. CRM phone validation/exact matching and staff/portal authentication are
separate workflows. Existing notes are not an identity-bound memory service.

**Effect:** protected status/documents/payment answers and voice-initiated writes
must remain unavailable. Obtain an approved verification-factor and disclosure policy,
then build scoped read/action tools and provenance-linked memory on existing records.
Do not add tenant architecture as an incidental fix: decision 001 explicitly defers it.
Tests must deny wrong/replayed/expired verification, cross-record binding and model
claims of verification, and retain corrected facts without rewriting originals.

## G05 — P2: not all history is immutable or reconstructable

**Evidence:** VoiceService.save_settings slices revisions to 20;
save_knowledge/knowledge_action retain 20 revisions/publications. PlatformService
change/emergency slice history to 200; NativeVoiceService.number_action retains 100;
CampaignService.save_contact_policy retains 100 embedded entries. RecordingService
save_transcript replaces transcript_ciphertext. Shared audit logs usually carry
IDs/actions rather than previous full content. Callback Task history is different:
it appends atomically and stops at a safety limit rather than trimming.

**Effect:** old prompt/knowledge/policy/number contents and transcript corrections
cannot necessarily be reconstructed from a version number or append-only audit ID.
Define retention explicitly; preserve full immutable revisions where required before
enforcing financial release/correction history. Test over-limit updates, transcript
correction, retention deletion and rollback without silently recovering deleted data.

## G06 — P1: environment separation and releases are only partial

**Evidence:** Platform controls/callbacks/jobs carry environment keys, but native
connections/numbers, Smartflo credentials, knowledge, simulator settings, local model
and speech assets are shared. Speech slots/global CPU lease are shared by design;
console/model health use test controls. No composite release manifest or call-pinned
version is created. Settings are read again for existing simulated transitions.
Policy logic is represented by a manually maintained POLICY_VERSION plus output
schema, not an automatic implementation-content hash; a logic-only edit without a
version bump would not itself invalidate old evidence.

**Effect:** “production” in a selector is not isolated credentials/queues/runtime or
a published release. Never activate from such a label. Add explicit immutable
component/publication references and compatibility checks after the real runtime
contract exists. Prove test data cannot reach real contacts, in-flight calls retain
their approved policy, revoked credentials/consent cannot be restored by rollback,
and shared capacity cannot become a cross-environment outage.

## G07 — P2: callback recovery does not cover parent/principal lifecycle

**Evidence:** CallbackService.record/action require the current parent via existing
CRM services. CRM Bin permits Lead/case deletion/purge; Tasks are not registered
as deletable Bin resources and are not those parents' owned children. Callback
worker denies lost parent/creator authorization but leaves the request active and
the unique contact slot occupied. Owner confirmation does not adopt the original
created_by principal. `confirmation_expired` stays active but is excluded from later
worker review; current UI can reschedule/cancel it while the parent remains readable.

**Effect:** a deleted parent or revoked creator can strand history/request slots;
expired requests need explicit operator resolution rather than automatic retries.
No cancelled record can currently dial because no dispatcher exists. Add a reviewed
domain-lifecycle cancellation/adoption mechanism retaining history and avoiding
scope leakage. Test parent delete/restore/purge, assignment/creator revocation,
expiry followed by DNC and duplicate contact creation. This is not permission to
delete callbacks or create a competing scheduler.

## G08 — P2 now, P1 prerequisite for live side effects: multi-write recovery

**Evidence:** callback Task CAS is atomic internally, then write_audit_log is separate.
Contact policy update and voice_contact_policy_events/audit insert are separate.
Domain changes can precede audit failure; idempotent replay may return an existing
record without recreating a missing audit receipt. Storage/DB deletion recovery
exists but no durable provider-action receipt/outbox is implemented. Callbacks have
no real provider side effect to reconcile yet.

**Effect:** do not claim cross-document exactly-once audit or post-provider crash
recovery from current CAS tests. Reuse embedded callback history; add a minimal
durable event/action receipt only where concrete external side effects require it.
Fault-inject audit/storage/DB failure after success and prove recoverable, truthful
outcomes before native call commands are introduced.

## G09 — P1 activation prerequisite: emergency scopes are not a unified stop

**Evidence:** PlatformService.emergency changes live directions/stop/version, not
component.enabled. `require_component_testing` checks only component enablement;
intentional local tests can still run while emergency_stopped=true. CampaignService
emergency pauses dry runs in another collection. Simulator mode is a third control.
The platform UI says it blocks “new AI handling”, which is broader than local-test
enforcement. Existing job version checks supersede evidence but do not implement real
call draining or independently transfer to a human during server outage.

**Effect:** keep the intentional distinction between test execution and live stop
explicit. Define and test a single mandatory live-entry/action/media stop contract;
compose existing scopes rather than deleting their APIs. Test races, stale clients,
active speech/transfer and rollback. No existing live call was shown to bypass a stop.

## G10 — P2: metrics and status sources need a clear unified interpretation

**Evidence:** `adapters.readiness` returns static not-configured values; dashboard
local model remains configured_not_verified even when detailed health has accepted
recent synthetic evidence. Dashboard speech approval labels differ from functional
test health intentionally, but UI does not fully explain the distinction. Same mock
heartbeat uses 90s in dashboard, 30s in platform. Active counts are all-time while
other mock metrics use today's creation cohort. AI/human-handled can overlap and
average duration includes unanswered rows. Real callback counts are separately labelled.

**Effect:** a user may confuse configuration, functional verification, approval and
capacity or compare unlike cohorts. Keep null for unavailable live metrics. Reuse
detailed status/evidence services, define source/cohort/freshness/denominator for
each metric and verify efficient queries, permissions and timezone boundaries.

## G11 — P2: contact-purpose and time-policy boundaries are inconsistent

**Evidence:** U/ContactPolicyPanel defaults to `service_callback`; CallbackService.sweep
requires exact purpose `callback`. Purpose remains editable, so an Owner can select
the correct value, but the UI default does not grant eligible callback consent.
Campaigns use their configured purpose and recipient timezone; callbacks use their
requested timezone for due conversion but the global voice timezone/window for
calling-hour checks. Number-specific windows are saved but never used for dispatch.

**Effect:** default consent may leave a request blocked; a future dispatcher must
define whose hours apply without silently changing established stored meaning.
Use a canonical purpose catalog/mapping with backward-compatible review and explicit
business/customer/number window composition. Test old purpose records, DST, changed
zones and holidays. No consent record should authorize unrelated marketing.

## G12 — P2: settings expose concepts without a consuming live workflow

**Evidence:** retry/queue fields are declared/persisted but have no call executor
reference. `primary_employee_id` only stamps call metadata. Number inbound_route
accepts only dynamic_ai and does not configure a PBX. Some backend fields lack UI
editors; Schedules/Routing display integration messages despite separate existing
callback/campaign scheduling code. Provider/model env configuration is process-cached.

**Effect:** users cannot equate saving a field with active enforcement. Keep these
contracts but label their scope; complete owner-first routing and actual retry policy
in the correct runtime rather than inventing a second scheduler. Document reload
requirements and coordinate API/worker configuration changes.

## G13 — P1: actual runtime, capacity and adversarial acceptance are absent

**Evidence:** speech execute refuses non-Linux; tests replace engine execution except
one Linux-only process test. Profiles pin executable/model/config/sample, but Piper
evidence explicitly says interpreter-only integrity with package pin required. Child
limits/minimal environment do not establish an OS network sandbox. No measured
target host/model/PBX/audio/load artifact exists in the repository evidence reviewed.

**Effect:** ten calls/10,000 recipients remains a target. Obtain actual inventory,
approved licensed/pinned package images and network isolation; run representative
models and per-language audio plus fault/load tests. Do not run installations or
real calls merely to make this audit look complete. Python vulnerability matching
remains offline; pip check is not security advisory coverage.

## G14 — P2: startup/index acceptance and worker provisioning need explicit checks

**Evidence:** main.lifespan ensures module indexes/catalog; standalone ARQ startup
only configures logging. `scripts/voice_catalog.py` reuses initialize_voice_module;
it is an administrative writer. Tests invoke index helpers on mongomock, not a
real MongoDB replica set. New callback partial uniqueness and lease behavior rely
on correct index provisioning before workers/admission are used.

**Effect:** deployment order must ensure indexes first, with no unrelated seed/reset.
Add repeatable migration evidence, index verification, staged duplicate/conflict
handling and rollback compatibility checks. Do not assume standalone worker boot
provisions its own constraints.

## G15 — P3: keep distinct test contracts, reduce genuine maintenance overlap later

**Evidence:** three evidence systems test different things: lexical article content,
synthetic policy mechanics and installed-engine verification. API modules share one
client, but split callback/platform/general types. Two speech adapter protocols
overlap structurally; Exotel and Smartflo formats/signatures differ. Static section
messages and legacy Exotel comments are not a reliable current provider inventory.

**Effect:** no proven duplicate live scheduler or duplicate registered endpoint was
found. Clarify labels and consolidate a common speech port only after callers/tests
and codec compatibility are verified; do not merge evidence records or remove
protocol fixtures merely because they have no public route.

## G16 — P2: bounded processing is not a measured scalability result

**Evidence:** dashboard/campaign list issue multiple per-state counts; lexical
retrieval scans up to 500 articles; campaign/recording/Task histories and lists have
fixed batch/page limits. Callback worker processes 25 and speech execution is global
single-flight. Existing indexes do not certify query plans or timeliness under load.

**Effect:** measure queues/DB query plans/worker lag before optimizing. A 10,000-row
audience import is not ten concurrent audio sessions. Add timestamped load evidence
and documented latency/lag budgets before claiming capacity; do not introduce another
broker/database without a demonstrated bottleneck.

## G17 — P2: test names and passing totals do not establish complete scenario coverage

`T/test_voice_callbacks.py:test_disabled_creator_and_changed_binding_fail_closed`
changes the creator account status and asserts that blocker; it does not mutate the
customer binding despite the name. Other current suites test real application logic
with in-memory stores, mock HTTP and fake speech execution. A green count therefore
does not prove changed-binding races, actual engines, PBX effects or real Mongo
uniqueness/TTL. Add explicit missing assertions and real-runtime stages later without
renaming mocks as integration acceptance. No test was modified by this audit.

## Consolidation / removal review — no deletions authorized or performed

| Classification | Component and current callers | Contract/history/compatibility implications |
|---|---|---|
| Keep as-is | Mock-only live gates, source/customer scope checks, private artifact guards, Task callback CAS; routers/UI/tests depend on them | Preserve while adding native runtime; never drop safety to show readiness |
| Keep but improve | Existing settings/knowledge/platform snapshots, health metrics, purpose UI and rollback docs | Existing stored versions and clients; require additive full-history migration, not truncation/removal |
| Complete existing implementation | Native adapter ports, caller identity/tools, callback worker, transfer and release workflow | Reuse states/services; new real events/attempts require migration/receipt and staging acceptance |
| Consolidate duplicate implementations | Candidate: overlapping streaming speech protocols in dynamic_audio/media_contracts | Tests and structural adapter contracts are callers; compare signatures and codec negotiation first. Not a claim of duplicate live execution |
| Deprecate after dependency verification | Possible legacy Exotel-only comments/contracts if product/provider scope is formally narrowed | Exotel has offline tests and no registered route; external Python/operational consumers are unknown. Do not remove its fixtures automatically |
| Candidate for removal, subject to approval | **None established** | Unused-looking settings/ports have documented future or compatibility roles; lack of a direct caller is insufficient |
| Unknown; more evidence required | Actual server units, external webhook registrations, operator scripts and approved package images | Repository search cannot establish deployed/external callers; validate on the real host/account before deprecation |

The roadmap resolves prerequisites in order. Every proposed source change requires
the user's later review and approval; this audit intentionally leaves these findings
visible rather than silently fixing them.
