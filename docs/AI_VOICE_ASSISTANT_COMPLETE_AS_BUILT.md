> **Implementation update ? 17 October 2026: NOT COMPLETE / NOT PRODUCTION READY.**
> Current implementation adds shared policy enforcement and mandatory host authorization to the unregistered streaming engine, generation fencing, bounded takeover, post-synthesis local reauthorization, callback lifecycle closure and Owner resolution in Tasks, recoverable embedded callback audit receipts, encrypted transcript correction history, policy implementation fingerprints, metric provenance and a staging-only index harness. Public factual output is restricted to complete approved cited excerpts; unsupported paraphrases and arbitrary clarification assertions are withheld. Native calls/media, trusted caller tools/memory and composite releases remain unimplemented.
> See [current implementation, traceability and execution evidence](VOICE_HARDENING_EXECUTION_2026_10_17.md) and [self-hosted staging contract](VOICE_SELF_HOSTED_STAGING_CONTRACT.md).
> The original audit below is retained verbatim as historical baseline evidence; its statements about unchanged source, findings, test counts and pending implementation approval describe that earlier audit, not this worktree.

> Final local verification: **1,408 backend passed / 1 Linux-only skip; 354 frontend passed; build passed**. These are local/mock/synthetic results, not PBX, installed-model or staging acceptance. See the execution report for commands, warnings, earlier failures and remaining gates.

---

# AI Voice Assistant — complete as-built audit

Audit date: **17 October 2026**. Repository HEAD: `6ffa4e8`; this audit includes the
existing uncommitted callback/intent/policy-studio extensions. It does not describe
HEAD alone. Application source, tests, configuration, dependencies, data and existing
reports were not edited. The five documents linked below are the audit deliverables.

- [Gap analysis and finding IDs](AI_VOICE_ASSISTANT_GAP_ANALYSIS.md)
- [Canonical current and target workflows](AI_VOICE_ASSISTANT_CANONICAL_WORKFLOW.md)
- [Dependency-ordered roadmap](AI_VOICE_ASSISTANT_IMPROVEMENT_ROADMAP.md)
- [Tests and acceptance matrix](AI_VOICE_ASSISTANT_TEST_AND_ACCEPTANCE_MATRIX.md)

## 1. Executive summary and evidence boundaries

**Not production-ready.** This is a working CRM extension with simulated calls,
reviewed knowledge, optional local inference/speech verification, encrypted imported
audio, durable callback bookkeeping, campaign eligibility previews and administrative
readiness controls. It has no registered native live call-control/media implementation,
trusted telephone-caller identity session, customer-facing CRM tool broker or real
callback dispatcher. Credentials or a successful health probe cannot fill those gaps.

This audit executed the existing voice backend suites: **198 passed, 1 skipped**,
493 warnings, 96.20 seconds. The skip requires Linux. Services/routes are exercised
against in-memory Mongo/Redis substitutes, fake model HTTP and fake speech executables;
private-storage tests use temporary synthetic artifacts. No real call, model download,
provider request, production record or deployed-server inspection occurred. A separate
pure policy probe confirmed a content-validation limitation described as G02 below.

Prior full-suite/build results remain historical evidence, not checks rerun here.
Earlier reports were checked against source rather than treated as authoritative.
All installed/deployed configuration, hardware capacity and actual provider/model
acceptance are **unknown**. No secrets, environment values or private artifacts were
read into this report. Architecture decision 001 explicitly defers multi-tenancy.

## 2. Repository and architecture map

Path abbreviations used throughout these documents:

| Key | Actual directory / responsibility |
|---|---|
| V | [`backend/app/features/voice_assistant`](../backend/app/features/voice_assistant): voice services, routes, schemas and adapter contracts |
| U | [`frontend/src/features/voice_assistant`](../frontend/src/features/voice_assistant): screens, API clients and component tests |
| T | [`tests/api`](../tests/api): backend tests and `conftest.py` dependency overrides |
| W | [`backend/app/worker`](../backend/app/worker): existing ARQ cron worker |
| CRM | `backend/app/features/{leads,customer,loan_management,insurance_management,reminders,workflow_engine}` |

`backend/app/main.py:lifespan/create_app` registers the routers, upload-envelope
middleware and additive startup indexes/catalog. `scripts/voice_catalog.py:main`
is a mutating administrative catalog/index entrypoint, **not an audit command**.
`V/catalog.py:seed_voice_catalog` uses insert-only catalog/navigation writes and
does not assign employee grants. Existing manual `scripts/migrate_*.py` migrations
also exist; voice does not have a separate numbered migration runner.

React uses the existing shared Bearer API client and React Query. API access tokens
are held in module memory; refresh behavior follows existing CRM session architecture
(`frontend/src/shared/api/client.ts`), not a new voice session. Mongo holds business
state; Redis supplies existing sessions/rate limiting/ARQ. Private recording files
use the existing managed encryption key. Speech subprocesses and optional Ollama
HTTP are separate from telephony. No PBX/media service is supplied by this module.

## 3. Frontend inventory and actual behavior

`U/VoiceAssistantPage.tsx` registers 15 section links under existing
`/voice-assistant` and `/voice-assistant/:section` routes in
`frontend/src/app/router.tsx`. The CRM sidebar is not a new voice runtime control.
Both voice route entries are wrapped in existing `RequirePermission` for calls:view;
section APIs/panels then enforce their own knowledge/recording/campaign permissions.
A knowledge-only grant does not by itself grant navigation into this page.

| Section / component | What the actual frontend does |
|---|---|
| Dashboard; Analytics / `VoiceAssistantPage` | Same dashboard endpoint, ten-second refresh, simulated call metrics and separate operational counters |
| Live; Incoming; Outgoing; History / `CallsPanel` | List/detail polling at five/three seconds; explicitly simulated creation and answer/transfer/end actions; no microphone, softphone or live transcript |
| AI Assist / `KnowledgePanel`, `TrainingWorkbench` | Draft/edit/review/publish/restore articles, safe-format imports, lexical evaluations, optional local text console |
| Policy tests / `PolicyStudio` inside Knowledge | Owner-only lazy loading and explicit synthetic policy-suite execution; no model/customer/provider access |
| Recordings / `RecordingsPanel` | Import/play/download/delete/recover permitted WAV artifacts and import/view transcripts; no call capture |
| Campaigns / `CampaignPanel` | Dry-run create/actions, audience CSV import and first-page eligibility preview; campaign emergency pause |
| Compliance / `ContactPolicyPanel` | Owner contact consent/suppression attestations and activation blockers |
| Settings / `SettingsPanel`, `PlatformControlsPanel` | Simulator settings plus environment-specific component testing and hard-blocked live activation |
| Provider Connections / `ProviderConnectionsScreen` | Native connection/number panel, local-model health panel, optional Smartflo panel |
| Voice Studio | Integration-required message; no implemented live voice-selection/cloning/upload workflow |
| Routing | Message directing users to simulated call transitions; no PBX destinations/employee notification runtime |
| Schedules | Integration message; actual callback forms live on CRM detail pages, campaign schedules in dry-run service, hours in settings |

`CallbacksPanel` is embedded on `LeadDetailsPage`, `LoanCaseDetailsPage` and
`InsuranceCaseDetailsPage`. It loads only when opened and uses backend capabilities.
`CallbackTimePreview` interprets a request only on click; applying a value only fills
the form. `TaskListPage` links managed Tasks back to these records and hides generic
completion. These detail pages do **not** initiate an actual AI call or display a
canonical customer-linked live call history.

## 4. Settings and actual enforcement

| Configuration | UI/API/storage | Enforcer, real effect and limitations |
|---|---|---|
| Simulator mode | Settings; GET/PUT `/voice-assistant/settings`; `voice_settings` singleton | `VoiceService.create_mock_call/act/sweep`: only `disabled`/`mock`; cannot enable live calling |
| Ring/fallback/transfer/duration | Same settings, `ring_seconds`, `ai_fallback`, `transfer_seconds`, `max_duration_seconds` | Persisted simulation deadlines; primary employee is metadata, not a real ring destination. Existing active simulations consult current settings, not a pinned release |
| Simulator capacity/budgets | Concurrent/daily/monthly/per-minute fields | Admission lease and checks in `create_mock_call`; not measured native-call capacity |
| Retry/queue settings | `VoiceSettings.retry_limit/retry_interval_seconds/queue_timeout_seconds/max_queue_length` | Persisted API fields; no call executor consumes them. Do not confuse with hard-coded speech verification queue or campaign reservation attempts |
| Voice hours/timezone/holidays | Settings API; partial UI coverage | Outgoing simulations and callback due review use these; same-day windows. Holidays and primary-employee/retry settings lack equivalent complete editing in `SettingsPanel` |
| Platform environment and components | `PlatformControlsPanel`; `/platform/{environment}`; `voice_platform_controls` unique environment | `PlatformService.component` allows testing, resets all live directions and emergency state. Media/recording/transfer enablement is rejected. Absent old components get an in-memory disabled fallback |
| Inbound/outbound/processing | Platform activation endpoint | `PlatformService.activation` has no positive enable branch, even with a forged passing DB flag or confirmation. `VoiceService.require_live` and `PlatformService.require_live` independently reject live work |
| Emergency stop | Environment platform emergency; separate campaign emergency; simulator mode | Different scopes. Platform sets directions false, increments version and stop flag without stale-version requirement; does not disable component testing. Campaign pause affects dry runs. Simulator mode disabled ends/reconciles mock calls. No real active-call drain |
| Native PBX | Native panel; `/native/connections`; encrypted credentials in `voice_native_connections` | `NativeVoiceService.test_connection` requires test permission and server origin allowlist; `AsteriskReadOnlyAdapter.probe` only GETs ARI ping and a PJSIP endpoint. No SIP trunk provisioning, dial, answer, bridge or transfer |
| Number registration | Native panel; `/native/numbers`; `voice_phone_numbers` | E.164-style validation, immutable number, Owner references and lifecycle. Approval references are attestations. All activation attempts denied; `inbound_route=dynamic_ai` does not configure owner-first PBX routing |
| Optional Smartflo | Provider panel; `/smartflo/connection`; `voice_provider_connections` singleton | Encrypted separate API/callback tokens; fixed code-defined API origin, Users read-only test; validation-only callbacks. One shared configuration, not test/production-separated credentials |
| Text inference | Provider/local-health panel; server `ConversationConfig` | Optional Ollama `/api/chat`, origin allowlist, bounds/deadlines/schema. Model identity/URL are operator-managed, not installed by UI; cache is process-local |
| STT/TTS | Platform profile selection; server `SpeechConfig`; `voice_speech_jobs` | Operator-approved whisper.cpp/Piper profiles, hashes and licenses; actual execution Linux-only. Piper verification currently English-only. Profile existence is not installation or language acceptance |
| Callback automation | Platform callbacks component; existing Task form | Toggle is evaluated during readiness review; neither it nor a confirmed Task permits dialing. Requests may be recorded while automation is disabled |
| Consent | Compliance/callback controls; `voice_contact_consents/suppressions` | Owner attestations; callback worker requires exact purpose `callback`; UI default is `service_callback`, requiring explicit correction. SMS preference is not voice consent |
| Recording/transcription | Recording import parameters and private server directory | Per-import consent reference/retention, encrypted artifact/transcript, permissions and expiry; no live recording toggle can enable capture |
| Caller verification, live release/model version, human fallback route | No working caller-session/release/real transfer configuration | Intent proposals are not execution; no telephone-factor flow, approved financial tool or composite release activation exists |

`PlatformService.record` inserts default disabled controls when an environment is
first read; GET platform status is therefore not entirely side-effect-free. Before
controls exist, `require_component_testing` preserves legacy server-enabled local
testing. Once a control exists, its component disable is authoritative. Server
configuration getters (`get_conversation_config/get_speech_config/get_native_config/
get_recording_config`, encryption `_fernet`) are cached per process; environment
changes require coordinated process reload. No values were inspected during audit.

Environment variable **names**, not deployed values: `VOICE_LOCAL_AI_ENABLED`,
`VOICE_LOCAL_AI_URL`, `VOICE_LOCAL_AI_MODEL`, `VOICE_LOCAL_AI_ALLOWED_ORIGINS`,
`VOICE_NATIVE_ALLOWED_ORIGINS`, `VOICE_RECORDINGS_DIR`, `VOICE_SPEECH_ROOT`,
`VOICE_SPEECH_PROFILES`, `VOICE_SPEECH_TIMEOUT_SECONDS`, `VOICE_SPEECH_THREADS`,
`VOICE_SPEECH_MEMORY_LIMIT_MB`, plus existing CRM `ENCRYPTION_KEY`, `JWT_SECRET_KEY`,
Mongo/Redis/session/proxy settings. Profiles contain paths, hashes, language, declared
version/license and approved STT sample/expected text. They are not browser commands.

## 5. Inbound workflow: current simulation, not actual ingress

`CallSession.provider` is restricted to `mock`. `MockCallInput` accepts a descriptive
label, direction, idempotency key and optional consent reference, **no destination
telephone number**. A simulation begins `ringing` with a deadline from settings.
An authorized creator/Owner can simulate human answer; timeout/reject chooses
`ai_active` if fallback is enabled or `missed` otherwise. No audio is connected.

```mermaid
sequenceDiagram
    participant UI as Incoming Calls UI
    participant API as mock/calls + VoiceService
    participant DB as voice_calls
    participant ARQ as reconcile_mock_voice_calls
    UI->>API: Create incoming simulation
    API->>DB: Admission checks; insert ringing + deadline
    alt Staff simulates answer before deadline
        UI->>API: answer with current version
        API->>DB: CAS human_active, answered_at, timeline
    else Deadline or rejection
        ARQ->>API: sweep expired sessions
        API->>DB: CAS ai_active or missed
    end
    Note over API,DB: No real incoming event, owner phone ring or media session
```

Owner-first **timing/fallback concepts** are simulated; actual Owner/assigned-person
ringing is not implemented. `primary_employee_id` is saved in the call, but view/edit
scope is creator/Owner, not the assigned employee. No verified number ingress,
busy destination, human availability or carrier outage fallback exists. Smartflo
observations are quarantined, not an alternate call-creation path.

## 6. Outbound workflow

Lead/Loan/Insurance detail pages create scoped managed callback Tasks; they do not
call `dial`. Outgoing Calls separately creates a simulation. It requires mock mode,
a consent-reference string and current permitted hours, then checks simulator
capacity/budgets and inserts `ringing`. It does not resolve a customer or independently
verify the reference. Campaign workers evaluate authorized customers but never dial.

```mermaid
sequenceDiagram
    participant CRM as CRM detail / callback UI
    participant CB as CallbackService
    participant Task as tasks
    participant Sim as Outgoing Calls simulator
    participant Voice as VoiceService
    participant Calls as voice_calls
    CRM->>CB: Staff callback request for scoped entity
    CB->>Task: Durable awaiting_confirmation Task
    Note over CB,Task: Future telephone dispatch is unimplemented
    Sim->>Voice: Separate outgoing mock request
    Voice->>Voice: Mock mode, hours, reference, budgets
    Voice->>Calls: Separate mock ringing record
    Note over Task,Calls: No callback dispatcher connects these paths; no CRM status update
```

The simulator stores `voice_calls`, not Tasks. There is no
integrated outbound CRM -> provider attempt -> ringing -> audio -> terminal event
pipeline. Live endpoints always reject. Admission, state and audit records are not
evidence that a customer was contacted.

## 7. Dynamic conversation and speech

`VoiceService.console` retrieves only public approved knowledge, uses optional
`LocalConversationAdapter.respond`, rechecks account/knowledge permission, component
enablement, settings/model configuration and current excerpts after generation, then
applies `intent_policy.proposal_policy`. Failure fallback also rechecks access and
current excerpts. English priority opt-out/wrong-number/human signals return a safety
hold before model execution. No suppression or escalation is silently executed.

```mermaid
sequenceDiagram
    participant UI as Knowledge text console
    participant S as VoiceService.console
    participant K as Published knowledge
    participant M as Optional local model
    participant P as proposal_policy
    UI->>S: Question, bounded browser history, language
    S->>K: Lexical retrieval of current approved excerpts
    alt Model enabled for testing
        S->>M: Structured answer + intent request
        M-->>S: Untrusted response, citations, intent/confidence
        S->>S: Recheck access/configuration/publications
        S->>P: Validate proposal and next action
        P-->>S: Allow public/clarification text or withhold
    else Model absent
        S-->>UI: Retrieval candidates; response null
    end
    S-->>UI: Text or withheld/superseded result, never caller-delivered audio
```

Knowledge retrieval uses normalized overlapping chunks, lexical token overlap and a
500-document scan limit, returning at most five excerpts in requested text language
and effective-date window (`VoiceService.retrieve`). It is not vector search or a
customer 360 memory. Imported TXT/CSV/DOCX/XLSX use bounded safe extraction; no PDF,
website crawling, malware scanner, embedding service or fine-tuning pipeline exists
(`knowledge_import.extract_document/extract_spreadsheet`, `TrainingWorkbench`).

`LocalUtterancePipeline.respond` accepts a bounded reference WAV, transcribes via
whisper.cpp, calls the model, applies the same proposal policy, then invokes Piper
and validates output WAV. It checks supplied authorization between stages. The only
registered use is a synthetic `SpeechJobs` pipeline with no customer sources, no
live media and no caller delivery. Evidence records timings/intent/escalation, not
raw transcript/answer. `SpeechJobs` checks configuration again before retaining
encrypted test output. Generated speech remains a local artifact.

`DynamicAudioConversation` is a **different, unregistered** streaming orchestration
contract with bounded turns/deadlines, codec framing and cancellation/clear messages.
Its callers found are tests; `_generate` does not apply `proposal_policy` or the
console's account/publication rechecks. Its model/speech ports have no installed
native streaming implementations. It must not be promoted as already hardened live
conversation code (G01). Exotel/Smartflo codecs are offline framing fixtures, not SIP.

`GeneratedAnswer.intent` is optional for backward-compatible parsing; missing intent
is withheld by registered console/local utterance policy. Confidence is model-reported,
not calibrated. Public citations and numeric token checks do not prove financial
semantic correctness. The `unclear`/`clarify` branch permits uncertain text without a
content entailment check (G02). No speech language is accepted end-to-end; Piper's
current English-only verification and text language dropdown must not imply otherwise.

## 8. Caller verification and financial status

Staff authentication (`get_current_active_user` / `require_permission`) is real.
`PermissionEngine` retains Owner superuser behavior, staff role grants, hierarchy
and existing scope rules. It is not telephone-caller authentication. CRM mobile
validation uses Indian ten-digit strings (`utils/validation.py:is_valid_mobile`);
customer/lead association uses existing exact mobile matching. Number registration
uses a separate E.164-style pattern. No voice-specific normalized lookup/factor,
attempt counter, verified session or per-caller field projection exists.

```mermaid
sequenceDiagram
    participant Staff as Authenticated staff console
    participant AI as Optional model proposal
    participant Policy as Backend policy
    participant CRM as Protected CRM records
    Staff->>AI: Synthetic status question
    AI->>Policy: loan_status / request_verification
    Policy-->>Staff: customer_verified=false; response withheld; execution=false
    Note over Policy,CRM: No verified caller session or protected CRM tool lookup occurs
```

The portal/OTP/secure-link account workflows are separate existing CRM features;
they do not bind an incoming call to the customer. Protected loan, insurance,
payment and document proposals are held, but this is not a finished verification
workflow. Wrong factors cannot be tested against a non-existent voice verifier.

## 9. Callback lifecycle

`callback_time.interpret_time` is a conservative English preview using server time,
explicit timezone and exact date/time; missing times/ranges/alternatives/DST overlap
need clarification. It creates no Task. Existing `scheduling.local_to_utc` rejects
gaps/ambiguous times unless fold is explicit in the actual request form.

`CallbackService.create` checks active actor, voice/Task permissions, actual entity
view/edit scope, active supervisor/account and canonical relationship IDs. Staff
supervise themselves; Owner may select an employee. Customer input, timezone/local
date/fold and UTC due time are stored in the existing Task's `voice_callback` metadata.
No existing next-follow-up date is overwritten and no customer is auto-created.
Optional source call requires a non-mock, matching customer/environment; current
mock-only CallSessions cannot supply such a valid originating live call.

```mermaid
sequenceDiagram
    participant UI as Scoped CRM callback form
    participant C as CallbackService
    participant DB as Existing tasks + contact policies
    participant W as Existing ARQ callback review
    UI->>C: Preview explicit date (optional)
    C-->>UI: Proposed/clarification; persisted=false
    UI->>C: Save request with idempotency key
    C->>DB: Unique active contact/environment Task, awaiting_confirmation
    UI->>C: Confirm exact time + current version
    C->>DB: CAS scheduled, append history
    W->>C: Review due records, bounded batch
    C->>DB: Recheck staff/entity/customer, consent, DNC, hours, controls
    C->>DB: CAS blocked / opted_out / confirmation_expired
    Note over C,W: No phone attempt, contact reservation or delivery retry
```

The persisted Task **is** the durable scheduling source; ARQ polls it. There is no
second callback scheduler. Confirm -> `scheduled` is bookkeeping, not dispatcher
acceptance. Reschedule -> `awaiting_confirmation`; cancellation -> inactive
`cancelled`; suppression at review -> inactive `opted_out`. Closing marks Task
completed administratively, never a completed call. Unconfirmed overdue requests
become active `confirmation_expired` and leave the worker's scan until manual action.
At history safety limit review closes as `closed_history_limit`; history is not
trimmed. Recheck means readiness, not a retry telephone call. All calls placed = 0.

Creation idempotency is unique by creator/environment/key plus input hash; a partial
unique index enforces one active contact/environment across modules. Atomic Task
CAS combines due/state/history. Unchanged blockers only move the next review time.
Worker batches 25 due records and postpones repeat review five minutes. Original
creator authorization remains required; adoption after account/parent lifecycle
changes is not a complete recovery workflow (G07).

## 10. CRM actions and history

Real actions here are authenticated staff callback CRUD/history and existing Owner
consent/suppression operations. `CallbacksPanel` saves global suppression **before**
selected callback cancellation; these writes are not a transaction. Cancellation
conflict does not undo suppression. Normal `RemindersService.update_task/complete_task`
reject managed callback Tasks. Ordinary Task responses expose managed state, not raw
customer preference (`reminders/mappers.py:task_to_response`).

Entity access delegates to `LeadService.get_lead_scoped`, `LoanCaseService.get_case`
and `InsuranceCaseService.get_case`, with additional stage resource permissions.
Insurance employee visibility follows creator/linked Application assignment; its
case `assigned_to` is an Advisor and must not be reused as employee authorization.
`CustomerService.get_customer_for_staff` applies existing customer assignment rules.
No AI action writes lead/case stages, underwriting decisions, rates or policy terms.
Typed action proposals have `execution_allowed=false`; no AI tool registry executes
notes, document requests, status retrieval or arbitrary DB commands.

Existing CRM notes and callback history are retained in their original services;
there is no general verified-fact/correction/memory service. Mock calls do not carry
canonical customer/entity linkage. Recordings inherit the owning call's scope rather
than creating a parallel customer history. Parent record deletion/purge can strand
active callbacks because callback edits require the parent to remain readable (G07).

## 11. Human handoff

```mermaid
sequenceDiagram
    participant UI as Mock call controls
    participant S as VoiceService.act
    participant DB as voice_calls
    participant W as Deadline worker
    UI->>S: transfer (ai_active, version)
    S->>DB: CAS transferring, pending outcome, deadline
    alt UI simulates confirmation
        UI->>S: transfer_confirmed
        S->>DB: CAS human_active, confirmed
    else UI failure or deadline
        W->>S: sweep transferring deadline
        S->>DB: ai_active or completed; timed_out/failed outcome
    end
    Note over UI,DB: No PBX transfer request, destination ring or real human audio
```

Actual receiving employee/team availability, authorized context package, AI audio
suppression on takeover and transfer failure callback creation remain missing.
Current mock transfer confirmation is an operator action, not provider proof.

## 12. Metrics, monitoring and health

`VoiceService.dashboard` sources simulated metrics only from `voice_calls` and
declares `data_mode=mock_only`. Today is creation since configured local midnight;
`active` instead counts all nonterminal rows. `average_seconds` divides total stored
duration by **all** calls created today, including unanswered. AI/human-handled flags
are non-exclusive visits to those timeline states, not resolution outcomes.
Transfers count the simulated `confirmed` field. Cost is unavailable.

Owner callback counters count current states of Tasks created today per environment;
overdue counts active past-due requests across all creation dates. They do not count
attempts/completed phone calls. `live_callback_completions`, media latency and live
queue depth are null. Knowledge/artifact counts represent storage states only.
Multiple count queries/scans and pagination patterns are not a measured load result.

Worker heartbeat `default` proves mock reconciliation recently ran (dashboard 90s,
platform gate 30s); callback heartbeat proves readiness review (90s); recording
heartbeat threshold is seven minutes. Campaign sweep has its own heartbeat. None
proves speech, all workers, live media or capacity. `/api/v1/health` checks Mongo and
Redis, not the voice pipeline. Native probe proves only read-only ARI/endpoint access;
Smartflo read-only Users success proves that scope only. Model health proves a
bounded synthetic structured-text response, not financial accuracy or valid intent.
Generic `adapters.readiness` and dashboard model labels remain largely static, so
they are not a unified view of configured providers/accepted test evidence (G10).

## 13. Test/production separation and release behavior

Platform controls, callback metadata and speech job evidence have environment keys.
Native connections/numbers, Smartflo credentials, knowledge publications, simulator
settings, local model URL, speech assets, runtime slots and global CPU lease are shared.
The self-hosted text console/health uses test controls. Campaign mode accepts only
dry runs. These are logical subsets, not fully isolated production infrastructure.

Console response metadata includes settings/publication/policy versions. Schema and
explicit policy-version changes alter inference evidence fingerprints; editing policy
logic without changing its version is not automatically detected. Knowledge has approved
publication restore and expiry checks; settings retain versioned snapshots. There
is no immutable composite release manifest, explicit release publication, per-call
pinning, live rollout or verified in-flight rollback. Some history snapshots are
bounded; old contents are not guaranteed reconstructable from audit IDs (G05/G06).

## 14. API routes and authorization inventory

All paths below are beneath existing configurable API prefix `/api/v1`, then
`/voice-assistant` unless otherwise shown. These are **registered CRM routes**, not
invented provider endpoints. `V/*router.py` supplies the exact signatures.

Permissions: C = `voice_assistant:calls`; K = `knowledge`; R = `recordings`;
P = `campaigns` in the same module. Owner uses existing superuser semantics.

| Route family | Registered methods/paths | Gate and additional behavior |
|---|---|---|
| Core / `router.py` | GET `/dashboard`, `/providers`, `/calls`, `/calls/{record_id}` | C:view; calls scoped to creator/Owner |
| Settings | GET/PUT `/settings` | Owner |
| Simulator | POST `/mock/calls`; POST `/mock/calls/{record_id}/actions` | C:create/edit; service call ownership and version/state checks |
| Knowledge | GET/POST `/knowledge`; PUT `/knowledge/{record_id}`; POST `/knowledge/import` | K:view/create/edit as appropriate |
| Knowledge governance | POST/GET `/knowledge/{record_id}/evaluations`; POST `/knowledge/{record_id}/actions` | K:edit/view/approve respectively |
| Console | POST `/console` | K:view; rate limit, bounded history, model output policy/rechecks |
| Policy studio | GET/POST `/console/evaluations` | Owner; synthetic-only |
| Legacy live gate | POST `/live/{feature}` (`inbound/outbound/recording/cloning`) | Owner; always rejects |
| Callbacks / `callback_router.py` | POST `/callbacks/interpret-time`; GET/POST `/callbacks`; POST `/callbacks/{record_id}/actions`; GET `/callbacks/{record_id}/history` | C:create/view/create/edit/view; CRUD adds Task permission, assignee and entity/stage scope; preview saves nothing |
| Campaigns / `campaign_router.py` | GET/POST `/campaigns`; PUT `/campaigns/{record_id}`; POST `/campaigns/{record_id}/actions`; GET/POST `/campaigns/{record_id}/recipients`; POST `/campaigns/{record_id}/recipients/import`; POST `/campaigns/{record_id}/preview` | P:view/create/edit/edit/view/import/import/view; owner scope and actual customer access |
| Contact policies | GET `/contact-policies/{customer_id}`; PUT `/contact-policies/consent`, `/contact-policies/suppression`; POST `/campaign-controls/emergency` | Owner; policy service rechecks Owner and scoped customer |
| Recordings / `recording_router.py` | GET `/recordings`; POST `/recordings/import`; GET `/recordings/{record_id}/audio`; PUT/GET `/recordings/{record_id}/transcript`; DELETE `/recordings/{record_id}`; POST `/recordings/{record_id}/recover` | R:view/create/view/edit/view/delete/edit; download adds R:download; service inherits owning call and expiry |
| Native / `native_router.py` | GET/POST `/native/connections`; PUT `/native/connections/{record_id}`; POST `/native/connections/{record_id}/test`; GET `/native/connections/{record_id}/events`; GET/POST `/native/numbers`; PUT `/native/numbers/{record_id}`; POST `/native/numbers/{record_id}/actions` | Owner throughout, also enforced by native service |
| Platform / `platform_router.py` | GET `/platform/speech-profiles`, `/platform/{environment}`; PUT `/platform/{environment}/components/{component}`; POST `/platform/{environment}/activation`, `/platform/{environment}/emergency`, `/platform/{environment}/speech-tests/{profile_id}`, `/platform/{environment}/pipeline-tests`; GET `/platform/{environment}/speech-tests`, `/platform/{environment}/speech-tests/{record_id}/audio` | Owner; environment validated; activation always denied |
| Local model / `self_hosted_router.py` | GET `/self-hosted/status`; POST `/self-hosted/tests/text` | Owner; test controls and operator config |
| Smartflo administration / `smartflo_router.py` | GET/PUT `/smartflo/connection`; POST `/smartflo/tests/connection`, `/smartflo/tests/webhook`, `/smartflo/tests/audio`; GET `/smartflo/events` | Owner; only API connection test sends bounded external read request |
| Smartflo observations | POST `/smartflo/webhooks/{channel}` (`incoming/answered/hangup`) | Saved separate Bearer callback token + validation-only mode; JSON mapping/bounds; observations only, not call transitions |
| Blocked Smartflo audio | POST `/smartflo/stream/resolve`; WS `/smartflo/media` | Resolver authenticates then rejects; WebSocket immediately closes 1013. No stream session minted |

API permission dependencies check active users. Service-layer permission enforcement
varies: callback/native/platform/policy services recheck many gates, core knowledge
methods rely on their protected router. A future tool broker must not bypass those
route-level permissions by calling a service with a self-asserted actor.

## 15. Database model, collection and index inventory

`BaseDocument` supplies version, actor/timestamps and soft-delete metadata; no
tenant_id is added. `VoiceRepository.update` uses `_id/version/is_deleted=false`
CAS and optional timeline append. Startup index functions live alongside services.

| Collections | Purpose / important indexes and relationships |
|---|---|
| `voice_calls` | `CallSession`, mock only; unique idempotency key, owner/date, status/deadline; no canonical customer/entity binding |
| `voice_admission` | Fixed simulator admission lease identity; no real call queue |
| `voice_settings`, `voice_worker_health` | Unique singleton keys; simulator config and independently named heartbeat records |
| `voice_knowledge` | `KnowledgeArticle`, draft/current publication/snapshots; status/language and active content-hash uniqueness |
| `voice_knowledge_evaluations` | Article/version/fingerprint lexical test evidence; article/date index |
| `voice_policy_evaluations` | Synthetic immutable reports; unique creator/suite/key and creation date; no automatic retention deletion |
| `tasks` | Existing `Task`, optional `voice_callback`; unique creator/environment/key (partial string), unique environment/contact (partial active), active/next-review, entity/date indexes plus original Task indexes |
| `voice_campaigns`, `voice_campaign_recipients` | Dry-run state and audience; owner/date/status/schedule; unique campaign/customer, status/lease |
| `voice_campaign_imports` | Unique campaign/import key and payload fingerprint; leased bounded import batches |
| `voice_campaign_controls` | Separate global dry-run emergency record |
| `voice_contact_consents`, `voice_contact_suppressions` | Unique customer/purpose and customer/scope; operator-attested current policies with capped embedded history |
| `voice_contact_policy_events` | Append policy version/action evidence, separate from current policy update |
| `voice_recordings` | Imported encrypted-file metadata, owning call ID/owner, retention/lease/version; unique owner/import key, call/date, inherited owner/date, state/expiry |
| `voice_native_connections`, `voice_phone_numbers`, `voice_native_tests` | Unique connection name, unique E.164 number, connection/state, probe connection/date; numbers reference existing connection |
| `voice_provider_connections`, `voice_provider_events` | Smartflo singleton provider, unique normalized-event dedupe key, provider/date and 30-day TTL observations |
| `voice_ai_health` | Config/schema/policy fingerprint unique; 30-day checked-at TTL; freshness is only 15 minutes |
| `voice_speech_jobs`, `voice_speech_slots`, `voice_runtime_leases` | Environment/date and expiry TTL; ten fixed queue slot identities, global CPU lease. Jobs expire after one hour, queue deadlines five minutes |
| `audit_logs` | Shared append-only writer with event/actor/ID metadata; no transaction with each domain write |
| Existing CRM collections | `leads`, `customers`, `users`, `employees`, `applications`, `application_workflows`, notes/status history and permission collections remain authoritative |

Indexes are ensured at startup, not verified against an actual target MongoDB here.
Tests use mongomock and cannot certify real partial-index, TTL, crash or distributed
transaction behavior. No deployed database records were queried or changed; the
executed tests create and query only their synthetic in-memory stores.

## 16. Workers, deadlines and recovery

`W/worker_settings.py:WorkerSettings.cron_jobs` registers existing voice jobs:

| Job wrapper in `W/tasks/voice_assistant.py` | Schedule / actual action |
|---|---|
| `review_voice_callbacks` | Seconds 10/40, startup; 25 due Task readiness checks, five-minute repeat interval, callback heartbeat; never dispatch |
| `verify_local_voice_speech` | Seconds 5/20/35/50, startup; explicit verification jobs only |
| `reconcile_mock_voice_calls` | Every five seconds, startup; up to 200 mock deadline transitions and heartbeat |
| `reconcile_voice_recordings` | Every five minutes, startup; up to 100 interrupted/expired artifacts, private-file deletion retries and heartbeat |
| `process_voice_campaign_previews` | Seconds 0/15/30/45, startup; at most four campaigns × 50 recipients, dry-run eligibility only |

Callbacks are persisted in Tasks, campaigns in their distinct dry-run records and
speech tests in their verification jobs; these are not competing live schedulers.
ARQ/Redis cron launches work, Mongo carries domain state. The worker startup configures
logging; API/catalog startup must provision voice indexes. No automatic model install
or download exists. Other CRM reminder jobs remain independent of voice dispatch.

Speech uses ten atomic slots and one global six-minute CPU lease, a five-minute
utterance budget and per-process bounds. Lost running jobs become `interrupted`,
queued deadline misses `expired`; no silent telephone retry. Disabled/reconfigured
components produce superseded/failed verification, not live readiness. Linux child
launcher applies resource limits and parent-death cleanup. It is not an OS network
sandbox; Piper package integrity still needs a reviewed package/image pin beyond
the Python executable hash (`speech_runtime.LocalSpeechRuntime.run`).

## 17. Error, audit, retention and emergency semantics

Malformed input fails validation; unauthorized scopes deny; stale versions return
conflict. Provider/model errors are minimized, not raw customer/provider payloads.
Public origin/allowlist and no-redirect checks constrain operator-selected network
tests. New upload middleware bounds request envelopes and local per-process admission;
this is not a distributed media capacity limit.

`middleware/logging.py:RequestLoggingMiddleware` records method/path/status/timing/
request ID rather than request bodies. `core/exceptions.py:validation_exception_handler`
omits raw input/context from field errors; unhandled exceptions still log a full
traceback server-side. Therefore this audit does not certify universal log redaction,
especially future DB/provider failures; actual private runtime logs were not opened.

Smartflo validation events are constant-time Bearer authenticated, deduplicated and
quarantined; no provider HMAC is implemented/assumed. Delivery/header support has not
been verified in an actual account. Test webhook persistence does not traverse a
public network or authenticate a delivered header. Out-of-order observations are
stored, not reconciled into active calls.

Private recordings are encrypted/checksummed, range-playable with separate download
permission and immediate expiry denial. Retention worker removes files and transcript
ciphertext while retaining a metadata tombstone. Imported transcripts are explicitly
unverified recognition; importing a replacement overwrites the previous ciphertext,
not an immutable transcript revision chain. Settings/knowledge retain 20 snapshots,
platform 200 history entries and number/contact embedded histories 100. Shared audit
is append-only but normally stores IDs/actions rather than complete old content.
Domain writes and audit insertion are separate operations; durable exactly-once
cross-document recovery is not implemented (G05/G08).

## 18. Infrastructure and operations evidence

`deployment/docker-compose.yml` contains Mongo/replica-set initialization, Redis,
backend, ARQ worker, frontend and Nginx, including a private recording volume.
`docker/backend/Dockerfile` supplies Python/backend, not Asterisk/Ollama/whisper/Piper
models. `docker/nginx/nginx.conf` serves the SPA, proxies API routes and has import
size exceptions; it has no accepted voice WebSocket transport/upgrade deployment.
`logging_config.configure_logging` configures rotating app/error/access/worker logs;
those runtime logs were not opened because they could contain private information.
`scripts/voice-server-inspect.sh` is a read-only inventory helper, not measured evidence.

No repository systemd unit files were located in the infrastructure inventory.
Prior user-supplied deployment paths/unit names remain operator guidance, not facts
verified on a server: `~/Ashapurafinancecrm/backend`, `~/Ashapurafinancecrm/frontend`,
`~/afscrm-venv`, `afs-crm-backend`, `afs-crm-arq-worker`. Existing operations documents
describe rollout/rollback; this audit ran none of those commands. Hardware, container
availability, actual unit definitions, network/TLS/trunk configuration and ten-call/
10,000-recipient capacity remain unknown. Python vulnerability matching stays offline.

## 19. Verification classification

See the test matrix for exact execution flags and test-to-workflow mapping. This
audit freshly ran all existing `test_voice_*.py` files without editing them, with
bytecode and pytest cache writes disabled. It did not run mutating catalog/migration
scripts, a live API, environment tests, frontend build/Vitest/browser captures,
provider/model tests or full-CRM regression. Prior 1,368/1 backend and 353 frontend
results are labelled historical in the matrix. The independent synthetic policy
probe is evidence of a limitation, not a new test added to the suite.

## 20. Production verdict

**Not production-ready because mandatory implementation and target verification
remain incomplete.** Reuse the existing scoped CRM, Task history, approved knowledge,
private artifacts and controls. First close policy-path/content gaps and establish
explicit runtime/identity contracts; then implement native calls/media, trusted
caller tools/memory, real handoff/dispatch and immutable releases. Only actual model,
PBX/audio, MongoDB/race, failure, consent, capacity and operator acceptance may justify
later activation. A mock `completed`, confirmed Task, green read probe or passing
synthetic suite cannot substitute for any of those gates. No roadmap change was
implemented during this audit.
