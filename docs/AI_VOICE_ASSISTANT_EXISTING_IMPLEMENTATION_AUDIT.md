# Airtel VoiceBOT extension — existing implementation audit

15 November 2026. Baseline HEAD `05ca74a`. Prior untracked handover is preserved;
the user supplied `docs/reference/airtel_iq_voicebot_integration_guide_v1.0.0_may_2026.pdf`
during inspection. Its **22 pages were read**; it is the authoritative protocol
reference, not another provider's similarly named streaming protocol. No existing
CRM source has been changed at this audit checkpoint.

## Existing architecture and actual flow

React/TypeScript voice screens call FastAPI voice routers. Mongo stores mock calls,
approved knowledge, canonical callback Tasks, private recording metadata, provider
settings and test evidence. Existing Redis/ARQ handles bounded verification/review
jobs; it is not a live audio queue. The shared dynamic core has per-instance history,
bounded buffering/interruptions, shared response policy and mandatory host authorization.
Native ARI is read-only; Smartflo is optional validation-only; Exotel is offline.
Whisper.cpp/Piper are optional Linux utterance adapters, not accepted 500-call streaming
services. Live activation remains denied. See existing hardening report for original
implementation boundaries; current code was inspected rather than inferred from tabs.

Existing Airtel code is **SMS/OTP**, under integrations/communication, with separate
configuration and tests. It is not VoiceBOT HMAC authentication and will be preserved.

Relevant inspection: voice `models/service/router/repository/catalog`, native/Smartflo
adapters and routers, callback/recording/contact/speech/platform services, dynamic_audio,
media_contracts, existing integration config/encryption/RBAC; React VoiceAssistantPage,
CallsPanel, provider/controls/API clients; main router registration; worker cron;
existing voice, Airtel SMS/OTP and UI test fixtures. Existing audited CRM record scopes,
single-company architecture and model financial restrictions remain unchanged.

## Baseline tests actually executed

All existing `tests/api/test_voice_*.py` plus `test_airtel_configuration.py` and
`test_airtel_transport.py`: **272 passed, 1 Linux-only skipped**, 494 warnings,
250.37 seconds. Existing venv, `DEBUG=false`, bytecode/cache disabled. These use
mock Mongo/Redis/HTTP/speech and synthetic artifacts, not provider/model acceptance.
No real call, remote server, SMS, paid action or production data was used.

## Gaps and backward-compatible insertion points

| Requirement | Baseline / required change |
|---|---|
| Airtel VoiceBOT config | Missing; reuse existing voice Provider Connections, provider settings collection, encryption and Owner controls. Do not reuse SMS secrets |
| HMAC / C2C / recording | Missing; implement exact PDF pp9–12 canonical bytes/signature and documented URLs; no invented read-only authentication test |
| Airtel media | Missing; add codec with PDF pp14–20 connected/start/media/dtmf/stop/callState/mark and outbound media/mark/clear/terminate; no Smartflo sequenceNumber assumption |
| Audio conversion | Existing media formats/buffers; add bounded raw G.711 conversions independent of provider transport, preserving old codecs |
| Session/lifecycle | Mock calls only; any real provider state must be segregated from mock reconciliation/actions and metrics; metadata must not expose tokens or audio |
| Human/AI takeover | Offline generation fencing exists; actual human topology/return-to-AI unverified. Never confirm HUMAN or AI ownership on a submitted request alone |
| 500 concurrency | Existing speech verification intentionally serial; add isolated-session/load harness and capacity/admission design. A fake/connection-only run is not end-to-end capacity proof |
| Events/CDR | No Airtel VoiceBOT ingestion/reducer; authenticated minimal observations, correlation/dedupe and SFTP path need distinct scopes, not fake call updates |

Existing callbacks/CRM scopes, approved knowledge, output policy, transcript revisions,
artifact retention and old UI/API contracts must remain working. In particular,
generic mock controls/worker must never manipulate future Airtel records.

## Confirmations the PDF explicitly leaves incomplete

- WSS authentication is bilateral: Bearer/mTLS/signed parameters are choices, not
  an automatically agreed credential scheme (p14). Public IP ranges come from onboarding.
- Human-first ten-second routing is an Airtel-controlled call-flow requirement;
  no CRM timer or documented return-human-to-same-stream command supplies it.
- Callback request fields differ between p11's snake_case description and camelCase
  table; sample event says `Removed`, not the preceding named-event list, and lacks
  a documented unique event/call correlation contract. Do not silently guess.
- CDR sample fields are explicitly illustrative and require confirmation (p13).
  High-volume campaigns lack real-time events/CDR (pp6–7); SFTP layout/auth/correlation
  must be agreed. A stream stop after fallback does not prove the customer hung up.
- Click-to-call gives a relative endpoint but no complete success/ID response
  contract. Recording table calls token a body field but curl uses query token
  (p12); do not log credential-bearing URLs or assume redirects are safe.
- The guide documents 160-byte inbound frames and 20–40ms output. Output can use
  160-byte/20ms frames consistently. Mark echoes after clear must be recorded as
  cleared, not successful playback (p20).

## Implementation order

1. Exact pure signing, request/message validation, playback/clear semantics and audio
   conversion; targeted fixtures and independent known-answer tests.
2. Encrypted VoiceBOT configuration and real backend/UI state, explicitly separated
   from SMS; actual registered CRM URLs, no secret readback and no automatic activation.
3. Session/admission/ownership/event infrastructure and integration into existing
   scoped call views, with supported operations distinguished from unconfirmed topology.
4. Progressive isolated synthetic load tests and existing regressions; actual
   provider, AI/media, incoming timeout, return-to-AI and 500-session acceptance remain
   blocked until infrastructure/account/topology evidence is provided.

This is an implementation checkpoint, not a claim that all later steps already work.
Final outcomes and remaining acceptance are recorded in the new test/onboarding docs.

## Feature status after this extension

| Existing requirement / screen | Actual implementation and limits |
|---|---|
| Dashboard, incoming, outgoing, live calls, history | Functional scoped simulation and mock reconciliation; no actual telephone calls or real provider history |
| Knowledge and review | Real persisted approval/publication/import/evaluation workflows; current approved excerpts feed optional model context |
| Dynamic conversation | Real per-instance orchestration/interruptions/safety checks; optional local text model; live audio host missing. Factual responses currently require an entire cited approved excerpt; arbitrary model paraphrases and protected disclosures remain denied |
| Recordings | Real encrypted imported WAV workflow, scoped access/retention/corrections/revision preservation; automatic carrier recording import and live capture missing |
| Speech/voices | Optional Linux utterance jobs for configured whisper.cpp/Piper, not installed/verified here; English Piper verification scope only; no claimed multilingual live readiness or approved cloning |
| Campaigns | Persisted authoring/import/dry-run and policy gates; recipient simulation is not outbound calling |
| Routing, schedules, studio | Saved policies, verification and simulation; no real carrier routing or live customer-leg bridge |
| Analytics | Existing mock/dry-run/test metrics; no provider-verified real-call analytics |
| Compliance | Real consent/DNC/review controls and fail-closed execution; no inferred legal calling/recording authorization |
| Callback Tasks | Real idempotent scoped canonical Tasks, explicit confirmation, due review and terminal-owner resolution; automatic live callback dispatch blocked |
| Settings/emergency controls | Real saved test/prod controls and local jobs; live activation hard-denied; no real active-call drain |
| Native PBX and telephone numbers | Saved encrypted configuration and optional read-only ARI probe; no native live media/control/trunk approval |
| Smartflo | Optional read-only API probe, authenticated validation observations and offline media contract; live unavailable |
| Exotel | Offline compatibility contract and disabled live methods |
| Airtel SMS/OTP | Existing separate integration preserved; not evidence of VoiceBOT authentication or entitlement |
| Airtel VoiceBOT (new) | Owner-only encrypted settings/UI, exact HMAC, bounded REST primitives, offline media/control codec and raw G.711 conversion. Registered media/callback routes reject live traffic |
| Human ↔ AI | Existing mock transfer and generation fencing; documented Airtel fallback messages encoded offline; confirmed same-call takeover/return missing |
| 500 concurrent conversations | Progressive synthetic isolated-codec and overlapping dynamic-core tests only; real runtime/admission/provider capacity unverified |

No protected financial tool was enabled, no fixed IVR was added, and no existing
working knowledge/callback/recording/SMS flow was replaced. Source changes and
their test results are listed in the architecture and test reports. Larger live
host, authenticated event reduction, SFTP collection and provider-confirmed
ownership transitions remain explicit work, not “implemented” because URLs exist.

## Related implementation and acceptance reports

- [Architecture, registered routes, encrypted settings and remaining phases](AIRTEL_IQ_INTEGRATION_ARCHITECTURE.md)
- [Exact WebSocket/media contracts and conversion limits](AIRTEL_IQ_WEBSOCKET_PROTOCOL_IMPLEMENTATION.md)
- [Human/AI takeover and unsupported return topology](AI_HUMAN_TAKEOVER_WORKFLOW.md)
- [500-conversation target, synthetic scope and real capacity acceptance](AI_VOICE_ASSISTANT_500_CONCURRENT_CALLS_CAPACITY_PLAN.md)
- [Executed tests, corrections, skips and limitations](AI_VOICE_ASSISTANT_TEST_REPORT.md)
- [Provider onboarding and production release gates](AIRTEL_IQ_PRODUCTION_ONBOARDING_CHECKLIST.md)
