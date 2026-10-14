# Advanced voice assistant implementation audit

Audit date: 14 October 2026. This audit was written before the advanced-platform
batch. It verifies the working tree, including the previous uncommitted Smartflo
batch; it does not assume deployed servers contain that code. The detailed provider
contracts remain in [SMARTFLO_VOICE_AUDIT.md](SMARTFLO_VOICE_AUDIT.md).

## Evidence and boundaries

Inspected React routes, panels, API clients, FastAPI routes/services/models,
Mongo indexes, permission catalog/engine, shared auth/audit/encryption/storage,
ARQ settings/tasks, API/frontend tests, Compose/Docker/Nginx and environment
configuration. `VoiceService` owns simulated calls, knowledge and settings;
`SmartfloService` owns quarantined callbacks and encrypted provider configuration.
`dynamic_audio.py` has no public live driver. Calls cannot become real by enabling
mock mode. `docs/decisions/DECISIONS.md` decision 001 explicitly describes the
single-company database: there is no authenticated tenant context to reuse.
Do not present creator scoping as SaaS tenant isolation. A future multi-company
deployment requires a coordinated identity/database migration before activation.

Classification: verified = locally tested functionality, partial = some real
implementation, mock = simulator/UI-only, missing = no implementation, blocked =
requires external infrastructure/configuration/approval. Local tests are not live
carrier, storage, speech-quality or production-load acceptance.

| Requirement group | Before this batch | Evidence, gap and acceptance criterion |
|---|---|---|
| Command center: active/queued/direction/outcomes/transfers/duration | Mock data, real persistence | `service.dashboard`, `CallsPanel`; counts come from simulated records. Preserve explicit mock labels; unavailable latency/speech/recording health must not become invented metrics. |
| Command center: filters, worker/media/AI health, recent failures | Partial | 10-second polling, worker heartbeat, status/direction pagination exist; date/campaign/agent/language filters and subsystem health incomplete. Acceptance: bounded queries, authorized counts, truthful unavailable states. |
| Inbound/outbound/routing/answer/reject/end | Mock | `CallSession`, `TRANSITIONS`, admission lock, `/mock/calls`; no carrier interface registered. Acceptance: signed/authenticated events and confirmed commands from a provisioned transport. |
| Hold/resume, SIP registration, media recovery, emergency termination | Missing/blocked | SIP/RTP engine, trunk, NAT/firewall/codec configuration and authoritative command reconciliation needed. No browser can label a request as connected. |
| Transfer/handoff/context/timeout | Partial/mock | State transitions and deadline worker exist only for simulations; actual agent availability, transfer confirmation and independent outage fallback unverified. |
| Idempotency/events/retries/duration limits | Partial | CAS transitions, mock admission/rate/budget controls, callback unique keys/TTL; no durable live command outbox or reconciliation worker. Test races/restart/late terminal events before live. |
| STT/TTS/language/VAD/echo/no-input/turn detection | Blocked | No approved speech/AI service (explicit user instruction); no inference resources verified. Native 8 kHz mu-law protocol fixtures are not speech models. |
| Dynamic context/RAG/cancellation/safety | Partial | Optional loopback local text model; dynamic async engine uses context and clear/cancel with bounded turns/duration. Media contracts are provider-neutral; Smartflo codec is isolated. No approved speech engine, speech/financial-quality benchmark or sensitive live CRM tools. |
| Training file/URL/CRM ingestion | Missing | Only manual articles. Need bounded safe parsing, source metadata and explicit scan status. Arbitrary URL fetching is excluded until approved URL/SSRF policy exists. |
| Normalization/hash/chunks/lexical retrieval | Partial | Existing hash/chunks, published-only/date/language filters, 500-document scan; no embeddings/vector/hybrid index or scalable reindex worker. Mongo remains authoritative; no new vector DB justified now. |
| Training review/version/expiry/rollback | Partial | Draft/review/published/archive, 20 revisions, CAS; editing a published article immediately removes old content from retrieval. Need approved release preservation and publication history; legacy records must remain readable. |
| Training evaluation/groundedness/poisoning/regression | Missing | Text console exposes citations, not an evaluation suite. Need persisted deterministic retrieval tests with required facts and pinned release fingerprints. Such checks cannot certify semantic groundedness. |
| Behavior identity/tone/language/limits/policy/tools/model | Partial | Owner settings version and 20 revisions; immutable adapter safety. No staged behavior release, model/voice registry, tool grants or approved AI adapters. |
| Record capture/two sides/consent/storage/artifact validation | Missing/blocked | `recording_status=disabled`, no audio artifacts. Shared S3 exists but private bucket policy/encryption/retention not verified. Need functional authorized imported-artifact library separately from blocked live capture. |
| Recording list/player/seek/speed/download/expiry/deletion | Missing | No routes/library. Acceptance: validate real WAV, keep bytes outside Mongo/web root, encrypt, authenticated playback, audit and delete derivatives; no fabricated audio/call duration. |
| Transcripts/timestamps/speakers/confidence/search/redaction | Missing/blocked | Real STT unavailable. Accept explicit provenance for imported recognized segments; never generate a fake transcript; summaries must remain separate. |
| Summaries/intent/outcomes/knowledge gaps | Missing | Generated test answers are not actual call summaries. Requires real transcript and evaluated inference; no arbitrary customer account facts. |
| Campaign audience/consent/suppression/windows/preview/dispatch | Partial; live dispatch blocked | Current continuation adds persisted customer-scoped recipients, consent/suppression attestations, timezone/DST checks, durable dry-run leases and eligibility previews, lifecycle controls and real Campaigns/Compliance panels. Confirmed callbacks and actual carrier dispatch remain missing. See execution report for current evidence. |
| Callback request/timezone/confirmation/idempotency | Missing | No caller-verified tool or confirmed natural-time scheduling. Need existing task workflow integration, clear ambiguity and window policy. |
| CRM customer/loan/EMI/ticket/follow-up tools | Missing/blocked | Existing CRM services retained; a loan offer's EMI amount is not an authoritative payment ledger. No caller identity assurance. Never fabricate a payment lookup from offer data. |
| Provider configuration/rotation/API test/callback logs | Locally verified, externally unverified | Smartflo Owner settings, Fernet, read-only Users probe, authenticated validation-only inbox. No invented HMAC; actual header delivery/sandbox still required. |
| Independent telephony/AI adapters/self-hosted infrastructure | Partial | Protocols exist, no installed live engine. Evaluate Asterisk ARI/external media vs FreeSWITCH ESL; separate PBX from web app, no fake SIP server. |
| Security/auth/RBAC/sessions/customer scope/secrets | Partial | Existing bearer auth and permission engine reused. Knowledge company-wide; simulated calls creator-scoped. Recording-specific permissions, uploads, redaction and artifact audit need implementation. Multi-tenant checks are not possible without tenant architecture. |
| Readiness/worker/recovery/limits/tracing/dead letters | Partial | ARQ cron/health, CAS, request rate limiting; no live media health, inference resources/load tests, recording cleanup or long-ingestion jobs. |
| Backups/DR/security dependency checks/deployment | Partial | Existing deployment scaffold; live restore, throughput, carrier outage and new private-artifact storage require operator testing. No production changes authorized. |

## Five acceptance scenarios

1. EMI reconciliation: blocked by caller verification, authoritative payment
   integration and telephony/speech. Knowledge retrieval alone cannot pass it.
2. Outgoing callback: dry-run eligibility implemented; blocked by verified dispatch and
   confirmed callback tool. No real traffic is allowed in this batch.
3. Interruption/change of intent: local cancellation/media framing tests exist;
   actual VAD, recognition and upstream clear latency require real media tests.
4. Recording review: implement real imported-artifact playback, provenance,
   authorization, seeking and transcript linkage. Live capture still requires
   PBX/media, consent and privacy approval. Imported artifacts are labelled.
5. Knowledge revision/evaluate/publish/rollback: implement document draft import,
   evidence evaluation, preserved prior publication, explicit reviewed publication
   and rollback with provenance. Semantic answer-quality gate remains unverified.

## Batch acceptance and unresolved scope

The plan and final exact verification results are in
[AI_VOICE_ASSISTANT_IMPLEMENTATION_PLAN.md](AI_VOICE_ASSISTANT_IMPLEMENTATION_PLAN.md).
Every requirement above is tracked; unimplemented workflows stay explicitly
unavailable. This is a coherent implementation batch, not a claim that all seven
phases or all five live acceptance scenarios are complete.

## Verified changes after this audit

Document imports now support bounded TXT/CSV/DOCX/XLSX extraction into draft
articles with upload provenance and explicit `not_scanned` status. Evaluation is
persisted against a fingerprint of the article contents/language/dates/title;
required fact matching and at least one positive evidence case are required to
release imported documents. Editing preserves the last approved publication;
archiving removes it. Retained approved publications can be explicitly activated,
with version checks and audits. Full history content is not repeated in list API
responses. PDF/OCR, semantic indexing, URL ingestion, model-quality evaluation
and versioned behavior release remain incomplete, not quietly substituted.

`RecordingsPanel` and recording API now support actual imported PCM WAV artifacts,
Fernet-encrypted private files, durable-write/readback/hash verification,
authenticated whole/range playback, separate download permission, UTC date/status/
call filters, native player speed/seek/volume, and transcript-segment seeking.
Transcript import carries explicit unverified recognition provenance and encrypted
storage; no synthetic transcript or summary is generated. CAS deletion disables
playback first, removes artifacts/transcript ciphertext and retains minimal audit
metadata. ARQ handles expiry, interrupted-import recovery and deletion retries.
Tests exercise real temporary files, corruption, missing storage, write/delete
failure, expiry, RBAC, cross-creator access and recovery. Live capture, actual STT,
searchable/redacted transcript workflow and object storage remain pending.

The dynamic core no longer imports Smartflo. It uses negotiated audio-format/media
ports with independent recognizer/synthesizer composition, bounded ingress,
explicit overload termination, per-format framing/silence, and immutable policy.
Offline tests cover both PCM and Smartflo mu-law; no live engine is registered.
Command center adds persisted authorized processing counts and truthful unavailable
subsystem states. No latency, cost or registration metrics are invented.

The recording permission catalog is additive and never auto-granted. Compose shares
private storage between API/worker; Nginx upload limits and pre-spooling ASGI bounds
are implemented. Docker/CI use the frontend lockfile; CI includes frontend tests
and backend test-file triggers. React Router was patched to 7.18.4 and the production
dependency audit reports zero advisories. Whole-CRM existing regression/static
issues and unverified live infrastructure still prevent production certification.
