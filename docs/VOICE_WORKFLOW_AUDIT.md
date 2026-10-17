# Voice workflow audit and implementation — 16 October 2026

Baseline: clean `6ffa4e8`. Inspected current voice frontend/routes/services/models,
RBAC, encryption, indexes, ARQ tasks, Leads/case follow-ups, reminders/tasks and tests.
This is a focused workflow audit, not a claim that every CRM source file was read.
Decision 001 still defers multi-tenancy; preserve existing single-company scopes.

| Screen / path | Actual status before this continuation |
|---|---|
| Voice Dashboard / Analytics | Simulated or mocked call metrics; implemented persisted local processing counts, incomplete live metrics |
| Live / Incoming / Outgoing / History | Simulated or mocked lifecycle; real native calls blocked by external dependencies and missing control/media implementation |
| Knowledge | Implemented and locally verified reviewed publications/retrieval; local dynamic model implementation not target-server verified |
| Recordings / Transcripts | Implemented imported encrypted artifacts; live capture/STT blocked |
| Voice Studio | Missing live voice-selection runtime; optional local speech profiles exist in Settings |
| Campaigns | Implemented and locally verified dry-run eligibility/leases/imports; real dispatch missing |
| Routing | Simulated owner/employee-first state machine; real ringing/transfer missing |
| Schedules | Implemented timezone/DST helpers and simulation hours; durable confirmed callbacks missing |
| Compliance | Implemented scoped consent/suppression attestations; operator/legal approval not established |
| Settings | Implemented persisted controls, jobs, emergency state and hard activation denial; actual media draining missing |
| Provider Connections | Implemented encrypted read-only ARI probes/optional Smartflo validation; actual trunk/media blocked |
| Leads / Loan / Insurance voice actions | Missing callback integration; existing scoped record services and append-only notes/tasks available |
| Customer financial enquiries | Missing voice-session identity binding; portal authentication alone is not telephone caller verification |

Chosen minimal extension: durable confirmed callback requests linked to existing CRM
entities, stored idempotently as managed Tasks in the existing task/reminder system. Existing
manual next-follow-up dates and historical notes must remain untouched. ARQ performs
bounded recovery and due-time eligibility checks, never a second scheduler.
Cancel/reschedule/confirm use versions and append history; a date never authorizes
a telephone call. Existing live gates remain closed. Staff-captured customer
requests are labelled attestations, not authenticated AI/customer evidence.

Deployment correction: the user's current paths are `~/Ashapurafinancecrm/backend`,
`~/afscrm-venv`, `~/Ashapurafinancecrm/frontend`, with services `afs-crm-backend` and
`afs-crm-arq-worker`. These supersede historical PDF examples for operator guidance;
actual server configuration/hardware has not been inspected and must be verified
before any authorized rollout. No production changes or calls are authorized here.

## Classification after this continuation

These labels describe specific capabilities, not blanket page readiness.
"Implemented and verified" means the stated local tests passed; it never means
telecom, real MongoDB, installed speech models or production were tested.

| Capability | Classification | Evidence / remaining dependency |
|---|---|---|
| Scoped callback request, explicit time confirmation, reschedule, cancel, history | Implemented and verified | Actual application services/routes with in-memory Mongo substitute; frontend API mocks |
| Callback controls in Leads, Loan and Insurance | Implemented and verified | Type/build and frontend regression; representative Lead desktop/mobile synthetic browser capture |
| Existing Tasks integration, optimistic concurrency, idempotency, suppression checks | Implemented and verified | Callback and ordinary Task regression tests; real Mongo index/concurrency acceptance still needed |
| Native ARI settings/probes and local speech verification adapters | Implemented but not fully verified | Prior local adapter tests; actual server, installed engines and PBX not verified |
| Knowledge, recordings/transcripts, campaigns, schedules, settings | Partially implemented | Real local storage/review/import/dry-run/control workflows; no live conversation execution |
| Dashboard/live/incoming/outgoing/history/routing call execution | Simulated or mocked | Existing mock call lifecycle and owner-first simulation are not native ringing/transfer |
| Voice Studio live voice switching, native bidirectional media and call control | Missing | Requires application implementation plus verified native PBX version/contracts |
| Voice-session customer identity and protected loan/insurance tool execution | Missing | No financial status disclosure added; portal login does not authenticate a caller |
| Automatic extraction/clarification of spoken callback requests | Missing | Current capture is explicit staff attestation, not AI voice capture or natural-language date inference |
| Actual callback dispatch, live contact reservation, retry policy and call-outcome completion | Missing | Current ARQ only reviews durable Tasks and records blockers; calls placed remain zero |
| Approved trunk/number, installed models, measured server capacity, live end-to-end acceptance | Blocked by external dependencies or authorization | No approved connection, hardware inventory, speech deployment or live-call approval |
| Multi-tenant isolation | Missing | Architecture decision 001 defers multi-tenancy; existing single-company record scopes retained |

Execution trace: detail-page callback panel -> authenticated callback router ->
voice/Task permissions and existing entity scope -> single existing Task document
with atomic versioned state/history -> existing ARQ due review -> current account,
entity/customer, consent, suppression, hours and platform checks -> explicit
unimplemented-live-dispatch blockers. There is no telephony call from this path.

See [execution evidence](VOICE_CALLBACK_EXECUTION_REPORT.md) and
[operations/rollback](VOICE_CALLBACK_OPERATIONS.md). This closes the durable
callback bookkeeping gap; it does not close the missing live capabilities above.
