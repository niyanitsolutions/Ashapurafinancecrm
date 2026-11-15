# Ashapura Financial CRM — AI Voice Assistant handover for ChatGPT

Prepared: **15 November 2026**. Repository reviewed at HEAD `05ca74a` with a clean
working tree before this handover was added. This is a portable explanation of the
existing code, not a request to build another CRM. No credentials, customer records,
private recordings or environment values are included.

## Context to give ChatGPT

I have an existing Ashapura Financial CRM built with React/TypeScript and
Python/FastAPI, MongoDB, Redis and an ARQ worker. Its AI Voice Assistant is already
partly implemented. Please understand the following current capabilities before
suggesting changes. Preserve the existing architecture, sidebar, CRM stages,
permissions, customer records, callback Tasks and history. Do not propose a new
application, fixed IVR, predefined question-and-answer calling flow or manual-calling
replacement. My target is a dynamic self-hosted voice assistant with native,
provider-independent PBX/SIP as the primary direction and optional provider adapters.

**Important: the repository is not a completed live telephone assistant.** It has
real local CRM/administration/storage/safety functionality, simulated call behavior,
optional local model/speech verification and offline streaming contracts. Native
live call control/media, verified caller tools, real callback dispatch, real transfer,
governed customer memory and complete release management remain unimplemented.
Production calling is deliberately blocked server-side.

## 1. Original business requirements and current implementation

| Requirement | What exists now | What is not complete |
|---|---|---|
| Preserve the existing CRM | Existing services, routes, RBAC and shared Tasks reused; callback panels integrated into Leads, Loans and Insurance | No whole-system production certification implied |
| Owner/human-first incoming calls | Configurable simulated ring deadline, human-answer/rejection and AI fallback states | No actual Owner phone ringing, SIP ingress, route/availability service or real AI pickup |
| Automatic outgoing AI calls | Outgoing call simulator, dry-run campaign eligibility and durable callback requests | No real automatic dialing, attempt dispatcher or provider event-driven outcome |
| Dynamic AI conversation | Optional Ollama-compatible local model adapter, conversation history and reviewed public knowledge | No accepted live conversational audio; unrestricted generated factual paraphrases are withheld |
| Speech input/output | Configurable whisper.cpp STT and Piper TTS verification adapters, local utterance pipeline, offline streaming core | No installed-model acceptance or native bidirectional live speech integration |
| Intelligent follow-up | Explicit timezone/DST scheduling, English time preview, durable Task, confirmation/reschedule/cancel/history | No live spoken-request ingestion or eligible future telephone execution/retry |
| Customer status enquiries | Existing authoritative CRM records and staff scopes; protected model proposals are withheld | No call-bound customer identity verification or authorized AI status-read tool |
| Human escalation | Typed escalation proposals, simulated transfer and hardened offline interruption/generation controls | No real employee bridge/transfer, receiver context package or accepted takeover audio |
| Consent and contact restrictions | Owner voice-consent attestations, expiry, purpose, suppression and eligibility checks | Attestation is not independent legal/operator approval; no accepted live enforcement path |
| Recordings/transcripts | Actual private encrypted imported WAV storage, playback/download controls, imported transcript corrections/retention | No live recording or automatic live transcription capture |
| Analytics and monitoring | Explicit mock metrics, real callback/artifact bookkeeping, provenance and component test/heartbeat evidence | No actual caller delivery, real call quality/cost/latency or measured media capacity |
| Production safety | Versioned controls, emergency scopes, hard live denial, output guards and verification invalidation | No approved runtime/release, unified native stop/drain or production activation |

“Implemented” above means the named code path exists. It does not mean actual PBX,
installed speech models or the deployed environment have passed acceptance.

## 2. Existing interface

The AI Voice Assistant has these sections:

- Voice Dashboard
- Live Calls
- Incoming Calls
- Outgoing Calls
- Call History
- AI Assist / Knowledge
- Recordings & Transcripts
- Voice Studio
- Call Campaigns
- Call Routing
- Schedules & Business Hours
- Analytics & Reports
- Compliance & Consent
- Settings
- Provider Connections

Not every section is a completed feature. Live/Incoming/Outgoing/History operate on
mock call records. Voice Studio and Routing contain integration-required messaging.
Schedules has only partial UI; callback management is on the existing CRM detail
pages. Provider Connections distinguishes native PBX/number settings, local model
health and optional Smartflo configuration. The presence of a tab is not proof of
live execution.

## 3. Architecture and main source locations

| Area | Existing implementation |
|---|---|
| Voice backend | `backend/app/features/voice_assistant/` |
| Voice frontend | `frontend/src/features/voice_assistant/` |
| Core calls/knowledge/console | `service.py`, `router.py`, `models.py`, `schemas.py`, `repository.py` |
| Callback workflow | `callback_service.py`, `callback_router.py`, `callback_schemas.py`, `callback_time.py`, `scheduling.py` |
| Model and response policy | `conversation.py`, `intent_policy.py` |
| Local audio and offline stream | `local_pipeline.py`, `speech_runtime.py`, `speech_process.py`, `speech_jobs.py`, `dynamic_audio.py`, `media_contracts.py` |
| Native PBX configuration/probes | `native_config.py`, `native_service.py`, `native_adapter.py`, `native_router.py`, `number_schemas.py` |
| Optional provider | `smartflo_config.py`, `smartflo_service.py`, `smartflo_router.py`, `smartflo_media.py`; legacy offline Exotel contracts also exist |
| Recording/import/private files | `recording_service.py`, `recording_router.py`, `recording_storage.py`, `recording_schemas.py` |
| Campaigns/contact policy | `campaign_service.py`, `campaign_router.py`, `campaign_schemas.py` |
| Central controls and health | `platform_service.py`, `platform_router.py`, `platform_schemas.py`, `self_hosted_health.py`, `self_hosted_router.py` |
| Synthetic policy testing | `policy_studio.py` and frontend `PolicyStudio.tsx` |
| Existing worker | `backend/app/worker/worker_settings.py`, `tasks/voice_assistant.py` |
| Additive startup/staging indexes | `catalog.py`, `staging_migration.py`, `scripts/voice_catalog.py`, `scripts/voice_staging_indexes.py` |
| Automated tests | `tests/api/test_voice_*.py`, frontend voice component tests |

Backend filenames in this table are relative to the voice backend directory unless
an explicit path is shown. Existing Lead, Loan, Insurance, Customer, Reminder/Task,
Workflow, Auth and Permission services remain authoritative for business operations.

## 4. How call simulation currently works

1. Owner enables mock mode in existing Settings.
2. An authorized user creates an incoming/outgoing test session with a descriptive
   caller label and idempotency key. There is no dialable destination in this input.
3. Outgoing simulations also require a consent-reference string and permitted hours.
4. Simulator admission checks concurrent/daily/per-minute/monthly budgets.
5. A mock `ringing` record is persisted with deadline and timeline.
6. UI actions simulate human answer, rejection/fallback, transfer confirmation/failure
   and completion. ARQ reconciles expired mock deadlines.
7. State changes use version checks and history; metrics remain explicitly mock-only.

Existing states include `queued`, `ringing`, `ai_active`, `human_active`,
`transferring`, `completed`, `missed`, `failed`, `cancelled`. Not every declared
state means a real queue/provider operation exists. Answer time is stored separately.
The call model currently restricts its provider to `mock`.

**A mock active/completed call is not a real ringing, answered or completed call.**

## 5. AI knowledge, intent and financial-safety behavior

Knowledge supports draft, review, publication, archive and retained publication
restore. Imports support bounded TXT, CSV, DOCX and XLSX extraction with rejection
of dangerous/unsupported archive content. PDF, website ingestion, embeddings,
automatic training and fine-tuning are not supplied by this workflow.

Retrieval is lexical ranking of current approved public excerpts, filtered by
language/effective dates. It is not a customer-memory search or vector database.
The console sends bounded conversation context and retrieved public excerpts to an
optional operator-configured local model through the Ollama-compatible `/api/chat`
contract. No model is downloaded or selected automatically.

The model returns structured answer/citation/intent data. Supported intent labels:

- Loan status
- Insurance status
- Product information
- Missing documents
- Callback request
- Human request
- Complaint
- Wrong number
- Opt-out
- Payment/disbursement
- Unclear request

Intent and confidence are proposals, not authorization. The backend holds protected
case/payment/document responses because trusted caller verification and CRM tools
are absent. Model outputs cannot claim verified identity or execute arbitrary actions.
English priority opt-out/wrong-number/human signals can hold the console before
model generation; this does not silently record suppression or complete a handoff.

The current v2 output policy is deliberately restrictive:

- Public factual output must match a **complete cited approved excerpt** after
  whitespace normalization; unsupported paraphrases or appended assertions are held.
- Clarification output must be one of the small reviewed non-disclosing questions.
- Confidence, citation IDs and overlapping numbers alone are not enough.
- `customer_verified` and `execution_allowed` remain false in model policy results.
- Financial accuracy and live delivery are never declared verified by that policy.

Therefore the intended architecture is dynamic, but unrestricted natural-language
factual responses have not been implemented/accepted for live use. The clarification
safelist is a test-output safety restriction, not an implemented telephone IVR.

The console rechecks access, current configuration and publications after generation.
Changed/revoked context causes withholding or a superseded response. The current
offline streaming engine also uses shared policy, mandatory host authorization,
generation fencing, interruption and bounded cancellation. It remains **unregistered
for live calls**, and the real native authorization/session host is not implemented.
Policy source digest/schema/configuration fingerprints invalidate affected local
verification evidence when those inputs change.

## 6. What self-hosted speech currently supports

- Optional **whisper.cpp** CLI recognition with operator-managed model/executable
  hashes and approved reference WAV/expected transcript.
- Optional **Piper** CLI synthesis with pinned voice/config/executable references.
  Current Piper verification accepts English profiles only.
- A bounded local STT -> model -> policy -> TTS utterance pipeline.
- Explicit verification jobs with deadlines, ten queue slots, a shared CPU lease,
  configuration checks and encrypted expiring test audio.
- Linux child process resource limits and parent-death cleanup.
- Transport-neutral audio formats, bounded buffering and offline interruption tests.

These are adapters/contracts and local verification paths. They do not establish
that engines/models are installed, licensed, fast enough or accepted on the target
server. Per-utterance CLI loading is not a warmed real-time speech service. Piper
package/image integrity needs verification beyond hashing its Python executable.
No speech language has complete end-to-end production acceptance. Text language
codes do not mean multilingual speech is supported.

Generated local test audio is stored/reviewed locally; it is not delivered to an
actual telephone call by the current registered implementation.

## 7. Callback and CRM follow-up workflow

Callbacks extend the existing **Tasks** system rather than creating a second
scheduler or overwriting manual follow-up dates.

1. Open the callback manager on a Lead, Loan case or Insurance case.
2. Record the customer's preference and exact local date/time/timezone. A limited
   English preview can propose a time such as “tomorrow at 11 AM”. Missing times,
   “after 11 AM”, alternatives or ambiguous DST need clarification.
3. Applying a preview only fills the form. Explicit save creates the durable Task.
4. Existing voice/Task/entity permissions, assignment and active-account checks run.
5. The request begins `awaiting_confirmation`; explicit confirmation makes it
   `scheduled` as a bookkeeping state.
6. Reschedule resets confirmation and appends old/new time/provenance/history;
   cancellation closes the request without erasing it.
7. Existing ARQ polls due Tasks and revalidates account/supervisor/customer binding,
   purpose-specific consent, DNC, calling hours and platform settings.
8. Actual dispatch remains blocked; zero telephone calls are placed.

Implemented protections include request idempotency, input-hash comparison, one
active contact/environment uniqueness, versioned atomic state/date/history changes,
timezone/DST validation and no generic Task edit/complete bypass.

Later hardening adds `closed_ineligible` lifecycle closure for lost authority,
deleted parent/customer or changed binding, preserving history and releasing the
active slot. Expired unconfirmed requests remain dispatch-ineligible and can be
revisited for suppression/lifecycle review. Owner terminal resolution is available
through the existing Tasks workflow, including cases with an unreadable old parent;
it cancels, does not adopt authority or schedule another call.

Callback events include stable audit receipt identities. Embedded Task events can
repair missing shared audit entries after a partial write; concurrent repair uses
deterministic IDs/version guards. This is callback-specific recovery, not a universal
exactly-once outbox for all domains or actual provider actions.

Voice consent is separate from other communication preferences. Exact callback
purpose is `callback`; the UI now defaults correctly. Old purpose records are not
silently converted into consent. Global suppression is saved before selected callback
cancellation in the Owner UI and survives a cancellation conflict.

There is **no actual future-call claim/dial/retry/outcome engine** behind a scheduled
Task. Staff entry is an attestation, not a verified spoken customer instruction or
proof of identity/consent. A valid live originating-call binding is not yet available.

## 8. Telephony/provider capabilities

**Native PBX/SIP is primary.** The current Asterisk integration stores encrypted
ARI credentials, a server-allowlisted origin and an existing PJSIP endpoint name.
Its connection test performs only read-only ARI ping/endpoint probes. It does not
provision SIP trunks, originate calls, answer, bridge, transfer or connect audio.

Telephone-number records support E.164-style validation, direction/purpose, connection
link, Owner authorization references, configured hours and lifecycle actions such
as review/suspend/disable/revoke. A saved reference is not verified carrier approval.
Number activation always rejects until real runtime/approval requirements are met.
Asterisk is a preferred candidate, not proof of a deployed/verified PBX version.

**Smartflo is optional.** It has encrypted separate API/callback credentials,
read-only Users-scope API validation, JSON webhook mapping, constant-time Bearer
callback authentication, bounded payloads and deduplicated quarantined observations.
Callback observations never create/control a live call. Offline audio framing tests
exist. The audio resolver rejects and the live media WebSocket closes; no accepted
live stream or transfer exists. Public reachability and actual account header/media
capabilities need provider testing. No provider HMAC signature is invented.

Legacy Exotel code provides fail-closed live methods and offline protocol fixtures;
it is not a working alternative live provider. No telecom provider, approved SIP
trunk, number or deployed hardware capability should be assumed from these classes.

## 9. Recordings, transcripts and history

Existing functionality stores real **imported** permitted PCM WAV artifacts in
private encrypted storage, linked to an existing ended call. It validates file
format/size/integrity, supports authorized playback/ranges, separates download
permission, and handles interrupted imports, recovery, expiry and retention cleanup.
An imported artifact linked to a mock call does not prove live capture.

Transcripts are operator-supplied and explicitly marked unverified recognition.
Corrections now retain prior encrypted transcript revisions with provenance/version
information. Count/size overflow fails rather than silently trimming revisions.
Retention deletion removes all transcript ciphertext revisions and recording files
while preserving appropriate metadata/tombstones.

There is no automatic live call recorder, live transcript feed, generated verified
customer summary or governed customer 360 fact/correction memory. Other settings,
knowledge, number/contact and platform histories still include capped snapshots;
full immutable historical reconstruction is not complete across every subsystem.

## 10. Campaigns, analytics, testing and operations

**Campaigns:** real persisted dry-run objectives/audiences, authorized existing
customer IDs, CSV import limits/idempotency, eligibility decisions, consent/DNC/
hours checks, worker leases/fences, pause/resume/cancel and bounded reservation
recovery. “Completed campaign” means dry-run processing completed, not calls made.
Test/production campaign dispatch is not implemented.

**Analytics:** explicit mock provider/cohort filtering, timezone/as-of/source and
denominator metadata, average duration across all versus answered mock calls,
nonexclusive AI/human handled counts, separate callback states/overdue counts and
artifact counts. Unknown live delivery/cost/latency remains unavailable. A Task
administrative closure is not a completed telephone conversation.

**Testing studio:** synthetic fixed policy scenarios with versioned expected/actual
decisions, Owner access, immutable reports and idempotent runs. Knowledge evaluations
test lexical evidence separately. Local speech jobs test a different component
scope. None of these passes approves production calling.

**Operational controls:** test/production control records, testing component switches,
inbound/outbound/processing disable, emergency state, current-evidence checks and
worker heartbeats. These do not provide a positive live activation path. Test and
production settings/evidence are logically distinguished, but model assets, provider
credentials and several runtime resources are shared rather than fully isolated.

The existing ARQ worker reconciles mock call deadlines, callback readiness/audit,
campaign previews, speech verification and artifact recovery/retention. Normal CRM
reminder/Task workflows remain the existing services. There is no additional live
call scheduler hidden behind a heartbeat or queue.

Additive startup index/catalog helpers and an isolated staging-only callback index
inspection/application harness exist. They are not proof that actual target MongoDB
indexes/races/migrations/restore were accepted. No migration needs to run merely
to read or discuss this handover.

## 11. Security and architecture boundaries

- Existing active staff authentication, Owner administration, RBAC, employee/object
  scope and stage-specific permissions remain in force.
- Caller identity is **not** staff login or a matching telephone number.
- The model has no arbitrary database/status/underwriting action execution.
- Protected caller tools and financial decisions stay unavailable.
- Credentials are server-side encrypted/write-only; no secrets belong in chat,
  source code, ordinary logs or browser storage.
- Approved knowledge and user/model inputs are not trusted as execution authority.
- Current architecture is **single-company**. Multi-tenant isolation was explicitly
  deferred; do not claim SaaS tenant isolation or add tenant IDs casually.
- Emergency scopes differ between platform live directions, local testing and dry-run
  campaigns. Actual native active-call drain/takeover has not been implemented/accepted.
- Rollback must preserve Task/history/output-policy compatibility; no approved
  composite live release/rollback artifact or per-call release pin exists.

## 12. Twelve advanced features: concise status

| Feature | Current overall status |
|---|---|
| Live monitoring / agent assist | Mock polling/timeline only; actual monitoring and live transcript missing |
| Customer 360 memory | Existing CRM history and callback provenance; dedicated trusted voice memory missing |
| Intelligent follow-up | Durable Task lifecycle/preview/review/recovery implemented; real call execution missing |
| Smart human handoff | Simulation and offline safety contracts; real destination/bridge/takeover missing |
| Quality/performance analytics | Provenance-aware mock and bookkeeping metrics; real call/audio/cost/capacity unavailable |
| Intent / next-best action | Typed proposal/classification/policy mechanics implemented; no authorized model action execution or real-model quality certification |
| Multilingual conversation | Configurable text/profile language and limited English TTS verification; no production speech-language acceptance |
| Financial guardrails | Shared conservative output policy, protected-action denial and generation checks; accepted financial-source/model/identity pipeline incomplete |
| Conversation simulator/testing studio | Mock calls, lexical evaluations, synthetic policy reports and local verification jobs; full real voice simulator missing |
| CRM action tools | Staff callback/contact APIs exist; trusted voice-session AI tool broker missing |
| Self-hosted health/capacity | Probes, functional-test evidence, deadlines/leases/limits implemented; actual host/model/PBX/capacity acceptance unknown |
| Versioned releases / rollback | Component/publication versions and policy fingerprints exist; composite approvals/call pinning/live rollback missing |

## 13. Infrastructure and prerequisites still required

Before calling can be enabled, both missing implementation and external acceptance
must be completed:

1. Actual authorized Linux/staging access and measured OS, CPU/RAM/disk/GPU,
   container availability, services, networking, backups and workload headroom.
2. Verified PBX/version/contracts, approved trunk/number/directions and test contacts.
3. Approved licensed installed STT, inference and TTS services with measured budgets.
4. Implemented native call/event/media pipeline and actual audio delivery evidence.
5. Approved caller factor/disclosure policy, trusted verification session and scoped tools.
6. Real callback attempt/reservation/retry/outcome and actual human transfer/drain.
7. Immutable composite releases, safe in-flight configuration behavior and rollback.
8. Real MongoDB concurrency/index/crash, security, language/audio, backup restore,
   end-to-end and load acceptance, followed by explicit production authorization.

The requested **10 concurrent calls and 10,000 campaign recipients** are proposed
staging test targets, not measured or approved capacity. No server specification,
telecom provider, GPU or installed model should be invented. The last documented
infrastructure decision was to continue locally without approving remote setup,
installation, new hosting, real calls or paid activation.

## 14. Existing verification evidence and limits

The October 17 hardening execution report records:

- Full backend: **1,408 passed, 1 Linux-only skipped**.
- Voice backend subset: **238 passed, 1 skipped**.
- Frontend: **354 passed across 72 files**.
- Frontend production build passed; bundle-size warning remains.
- Lint passed with existing frontend warnings; scoped backend typing passed.
- Dependency consistency passed; this is not a vulnerability audit.

These are **historical recorded results**, not a fresh November 15 test run against
the current HEAD. This handover was prepared through source/report inspection;
tests, builds, remote services and models were not rerun. Most integration contracts
use mock Mongo/Redis, synthetic HTTP/speech and temporary synthetic artifacts.
Linux process behavior, real speech models, PBX/media, real MongoDB races and
production acceptance cannot be inferred from those counts. Python advisory matching
was requested to stay offline; do not send the technology inventory externally.

## 15. Important APIs and storage for follow-up discussion

Under the existing API prefix, normally `/api/v1/voice-assistant`:

- Calls: `/dashboard`, `/calls`, `/mock/calls`, `/mock/calls/{id}/actions`.
- Knowledge/text: `/knowledge`, article actions/evaluations/import, `/console`.
- Synthetic policy reports: `/console/evaluations`.
- Callbacks: `/callbacks`, `/callbacks/interpret-time`, `/{id}/actions`,
  `/{id}/history`, `/{id}/resolve-owner` beneath callbacks.
- Configuration: `/settings`, `/platform/{environment}` and component/test/emergency
  routes, `/self-hosted/status`, `/self-hosted/tests/text`.
- Connections/numbers: `/native/connections`, `/native/numbers` and their test/actions.
- Optional provider: `/smartflo/connection`, tests/events and validation webhooks;
  audio resolver/media remain blocked.
- Artifacts: `/recordings` import/playback/transcript/recover/delete.
- Dry runs/policies: `/campaigns`, recipients/import/preview/actions and
  `/contact-policies`, campaign emergency controls.

The actual router files define exact methods/permissions. These are CRM endpoints,
not proof of supported carrier operations.

Main storage groups: `voice_calls`; existing `tasks.voice_callback`; knowledge and
evaluation collections; synthetic policy reports; imported recordings/private files;
native connections/numbers/probe results; Smartflo connections/observations; contact
consent/suppression; dry-run campaigns/imports/recipients; platform controls; model
health; speech jobs/slots/leases; shared audit logs. Existing CRM entities remain
canonical. There is no duplicated customer database or real external-call outbox.

Server configuration names include `VOICE_NATIVE_ALLOWED_ORIGINS`,
`VOICE_LOCAL_AI_ENABLED`, `VOICE_LOCAL_AI_URL`, `VOICE_LOCAL_AI_MODEL`,
`VOICE_LOCAL_AI_ALLOWED_ORIGINS`, `VOICE_RECORDINGS_DIR`, `VOICE_SPEECH_ROOT`,
`VOICE_SPEECH_PROFILES`, `VOICE_SPEECH_TIMEOUT_SECONDS`, `VOICE_SPEECH_THREADS`,
`VOICE_SPEECH_MEMORY_LIMIT_MB`, and the existing Mongo/Redis/encryption/JWT settings.
The isolated staging CLI uses `VOICE_STAGING_MONGO_URI`. Do not paste values or
credentials into ChatGPT. Several server config getters are process-cached, so actual
environment changes require coordinated existing deployment/reload procedures.

## 16. Repository documents to consult if code access is provided

- `docs/VOICE_HARDENING_EXECUTION_2026_10_17.md` — later implementation and recorded tests.
- `docs/VOICE_SELF_HOSTED_STAGING_CONTRACT.md` — proposed staging contracts and unresolved acceptance.
- `docs/VOICE_RUNTIME_ACCESS_OPTIONS.md` — historical local-only decision and unapproved infrastructure options.
- `docs/AI_VOICE_ASSISTANT_COMPLETE_AS_BUILT.md` — broad architecture/API map; read its current-state notice before the historical body.
- `docs/AI_VOICE_ASSISTANT_GAP_ANALYSIS.md` — original audit findings plus later update notice; do not assume every original defect is still unfixed.
- `docs/AI_VOICE_ASSISTANT_CANONICAL_WORKFLOW.md` and `docs/AI_VOICE_ASSISTANT_IMPROVEMENT_ROADMAP.md` — current-versus-target workflow and dependency ordering, with update notices.
- `docs/AI_VOICE_ASSISTANT_TEST_AND_ACCEPTANCE_MATRIX.md` — test/evidence distinctions.

## Suggested request after sharing this handover

“Use the attached handover as context for my existing Ashapura Financial CRM AI
Voice Assistant. Explain what is implemented versus simulated, externally unverified
or still missing. Help prioritize the remaining work in dependency order while
preserving the existing code and CRM workflows. Do not assume a tab, configuration,
passing mock test or green health check proves live calling. If source is available,
verify it before claiming a feature is complete. Do not request secrets or recommend
automatic deployment, paid activation or real calls. Native PBX/SIP should remain
primary, Smartflo optional, and production calling must stay blocked until both
implementation and actual runtime/authorization acceptance are complete.”

**Final status: partially implemented, locally hardened framework; not a completed
or production-ready live AI Voice Assistant.**
