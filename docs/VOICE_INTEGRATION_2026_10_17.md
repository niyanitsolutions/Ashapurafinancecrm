# Workflow-preserving voice integration — 17 October 2026

## Baseline audit and ordered plan (before edits)

The 16 October callback work is present as uncommitted changes, including its
services, UI, tests, screenshots and operations documents. It is preserved; this
continuation does not restore, stage or commit it. Existing single-company scopes
remain unchanged (decision 001 defers multi-tenancy). No target-server access,
approved speech deployment, trunk or verification-factor policy is available.

| Requested area | Actual baseline | Insertion point / dependency |
|---|---|---|
| 1. Live monitoring / agent assist | Simulated call state/timeline and controls; no actual PBX control/media | Real authenticated PBX events before any live state or transcript claim |
| 2. Customer memory | Existing scoped CRM records, notes, callbacks and imported recordings; no verified voice identity or shared conversation-memory service | Identity and scoped record binding before protected retrieval; no copying all customer data into prompts |
| 3. Follow-up scheduling | Durable managed Tasks, confirmation/CAS/history/readiness worker; no spoken-time interpretation or live dispatch | Explicit time clarification before existing callback create; never silently create from interpretation |
| 4. Human handoff | Existing mock transitions/transfer confirmation only | Verified PBX bridge/transfer events; no success on request submission |
| 5. Analytics | Simulation-only call dashboard; persisted artifact counts; live metrics unavailable | Preserve mock metrics; append separately scoped real workflow counters |
| 6. Intent / next action | Structured answer/citations; no typed intent policy | Dynamic model output -> independent deterministic authorization policy -> response/action proposal |
| 7. Multilingual | Text language and pinned speech profiles, no accepted speech language | Profile/model and representative end-to-end audio acceptance; text code is not speech validation |
| 8. Financial safety | Prompt policy, public knowledge, no model CRM tools; no protected caller tools | Validate typed intent and citations, deny protected actions/disclosure without verified identity |
| 9. Simulator | Mock calls, lexical article evaluation, local speech verification jobs | Existing text console plus isolated synthetic policy regression; no provider/CRM execution |
| 10. CRM tools | Staff callback APIs exist; model explicitly has no tools | Typed action proposals remain non-executable until trusted session identity/action authorization exists |
| 11. Health/recovery | Component probes, expiring speech jobs, platform gates and emergency stop | Existing dashboard/ARQ; no claimed live draining or hardware capacity |
| 12. Releases/rollback | Versioned settings, knowledge publications/evaluations, platform evidence, no complete call-pinned release | Preserve current version contracts; actual live release activation remains blocked |

Canonical path: staff/Owner authentication -> existing permission/resource scope ->
knowledge retrieval or managed Task -> optional local text/speech adapter -> validated
proposal and safety decision -> explicit staff-controlled CRM APIs. Simulated calls
remain the existing `queued/ringing/ai_active/human_active/transferring` state machine
and existing terminal states. No real native adapter is registered. Customer phone
matching is not verification. Call metrics cannot be inferred from local processing.

Plan: (1) typed intent/next-action policy in the existing dynamic model and console,
with the same guard before local speech synthesis; (2) conservative date clarification
integrated into existing callback form; (3) versioned, synthetic policy regression
inside existing knowledge console; (4) scoped callback operational counters in the
existing dashboard; (5) targeted then broad tests and updated acceptance/rollback.
No new call state, duplicated scheduler, provider API, permission grant or live path.

External and implementation blockers are distinct. Native call control/media,
authenticated caller identity/tools, live transfer/dispatch, real memory ingestion
and call-pinned releases still require implementation; a credential alone does not
complete them. Actual model/PBX/audio/server testing requires approved infrastructure.

## Canonical existing state and dependency map

| Stage | Actual source / state | Side effect, authorization and failure behavior |
|---|---|---|
| 1. CRM association | Existing Lead, Customer and ApplicationWorkflow services; callback `entity()` delegates to scoped Lead/Loan/Insurance services | No customer clone or lifecycle/status update; missing/forbidden record denies access |
| 2. Eligibility | Existing voice consent/suppression records, timezone helpers and callback/campaign services | Staff attestation does not verify caller identity; denial never becomes a dial attempt |
| 3. Readiness | `PlatformService`, native read-only ARI probes, local text/speech verification jobs | Connection, endpoint, number approval, model request and live audio are separate; all live activation remains denied |
| 4. Routing | `VoiceService.create_mock_call/act/sweep` and `CallSession.TRANSITIONS` | Creator/Owner scope, version CAS, mock capacity/deadlines; never a native call |
| 5. Speech | `SpeechJobs` -> `LocalUtterancePipeline` -> local speech/model adapters | Existing leased bounded queue, current-component checks and timeouts; no delivered-to-caller claim |
| 6. Identity | No trusted telephone identity session | Matching phone/staff login cannot authorize caller-specific financial disclosure |
| 7. Intent/action | Optional local model -> typed proposal -> independent policy | Policy holds protected/unsupported proposals; no database tool or arbitrary action execution |
| 8. Escalation | Existing simulated `transferring` -> confirmation/failure paths | Request submission is not a successful human connection; no real fallback ringing implemented |
| 9. Callback | Existing managed `tasks.voice_callback`, callback service and ARQ readiness review | Atomic due/state/history updates; confirmation, permissions, consent, suppression and current binding rechecked; no dispatcher |
| 10. Completion/history | Existing mock call terminal timeline and imported encrypted artifacts | `completed/missed/failed/cancelled` remain actual mock states; imported artifacts do not prove live capture |
| 11. Analytics/audit | Existing scoped dashboard, worker-health collection and append audit | Simulation, local artifacts, real callback bookkeeping and unavailable live metrics remain distinguishable |
| 12. Administration | Owner settings versions, knowledge draft/review/publication, platform testing and emergency controls | Test success never activates production; composite releases and active-call draining remain missing |

Existing call transitions: `queued -> ringing/cancelled/failed`;
`ringing -> human_active/ai_active/missed/completed/failed`;
`ai_active -> transferring/completed/failed`;
`human_active -> completed/failed`;
`transferring -> human_active/ai_active/completed/failed`. Terminal states do not
transition again. There is no invented `answered` status: answering uses the existing
active states and `answered_at` timestamp. All are still simulated calls.

Managed callback flow: `awaiting_confirmation -> scheduled` only with explicit
confirmation; any permitted reschedule returns to `awaiting_confirmation`. Overdue
unconfirmed time becomes `confirmation_expired`. Due confirmed requests become
`blocked` while live execution is unavailable. `cancelled`, `opted_out` and
`closed_history_limit` release the active slot without erasing history. Administrative
Task completion in those terminal paths does not mean a successful telephone call.
CAS conflicts require refresh; unchanged blocker reviews do not duplicate history.
