# Self-hosted voice: operator handover

16 October correction: the user's deployment paths are
`~/Ashapurafinancecrm/backend`, `~/Ashapurafinancecrm/frontend`, venv
`~/afscrm-venv`, services `afs-crm-backend` / `afs-crm-arq-worker`.
These supersede the historical PDF examples below; actual host inventory remains
unverified. See [current callback handover and safe rollback](VOICE_CALLBACK_OPERATIONS.md).

15 October 2026. No server deployment, restart, model installation, telephone call,
provider registration or production migration was performed. This release adds
configuration and read-only probes; it does not supply a live PBX/media runtime.

## Actual host inspection comes first

The deployment PDFs describe Ubuntu 22.04/24.04, `/opt/afs-crm`, systemd backend and
worker services, and a suggested t3.medium minimum. These are guide assumptions,
**not measured properties of the deployed server**. No SSH configuration exists
on this workstation; the guide's SSH command uses placeholders. Actual OS, CPU,
RAM, available disk, GPU/VRAM, Docker and running services remain unverified.
The local Windows developer host and its unavailable Docker daemon cannot establish
production capacity. An existing approved connection name has been requested;
credentials must not be supplied in chat.

Run the reviewed, read-only [inventory script](../scripts/voice-server-inspect.sh)
on the actual host through the operator's existing authenticated server session:

```bash
bash /path/to/reviewed/voice-server-inspect.sh
```

It reads OS/CPU/memory/disk/GPU, Docker availability, known service state and
aggregate load. It does not read `.env`, process command lines, logs or container
environment variables. It does not install, restart, pull models or call APIs.
Missing commands/permission errors must remain explicit unknowns. Review output
before sharing infrastructure metadata. A short inventory is insufficient to
establish peak capacity: observe existing CRM/worker memory, CPU, disk and latency
through a representative workload period, then benchmark isolated candidate speech
services before co-location. Never benchmark ten voice sessions on production.

No model has been selected. If the actual host has only the guide's suggested
2 vCPU/4 GB, do not deploy a co-located ten-call LLM/STT/TTS/media stack there.
Keep the CRM intact and size a separate staging inference/media host from measured
model resident memory, peak KV cache, streaming concurrency, real-time factors,
VRAM and existing CRM headroom. Exact RAM/VRAM/storage purchasing advice remains
pending those measurements; no unmeasured recommendation is approved for deployment.

Candidate evaluation references, not installed dependencies: Ollama's documented
[structured chat API](https://docs.ollama.com/api/chat),
[faster-whisper](https://github.com/SYSTRAN/faster-whisper), and
[Piper](https://github.com/OHF-Voice/piper1-gpl). Review runtime, model and voice
licenses independently (Piper runtime is GPL-3.0); benchmark required languages,
digits, loan amounts and names with approved recordings. No automatic model pulls.

## Configuration and secrets

Retain the existing production configuration mechanism, encryption key management,
authentication, Mongo, Redis and ARQ deployment. Do not copy development `.env`
files to production. Back up Mongo, private artifacts and encryption keys through
the existing approved procedure before any authorized staging rollout.

| Setting | Safe default and meaning |
|---|---|
| `VOICE_NATIVE_ALLOWED_ORIGINS` | `[]`; operator-controlled exact JSON array of approved PBX origins; remote probes denied until configured |
| `VOICE_LOCAL_AI_ENABLED` | `false`; text adapter disabled |
| `VOICE_LOCAL_AI_URL` | `http://127.0.0.1:11434`; no model/service assumed present |
| `VOICE_LOCAL_AI_MODEL` | Empty; use an actually installed, approved model name |
| `VOICE_LOCAL_AI_ALLOWED_ORIGINS` | `[]`; mandatory for any non-loopback inference origin |

Use HTTPS outside loopback, trusted DNS and egress firewall controls; origin
validation is not DNS pinning. Restart the existing backend/worker only during an
authorized deployment after changing cached environment settings. Native ARI
username/password are entered over the authenticated HTTPS Owner UI and stored
encrypted with the existing server-side secret mechanism; responses expose only
credential presence. Use a dedicated read-only ARI account. Never expose ARI
directly to browsers or use SIP trunk passwords as ARI credentials.

## Implemented administration and probe contract

All routes below are relative to `/api/v1/voice-assistant`, require existing
authenticated Owner authorization, and return existing CRM response envelopes.
Connection and number edits/actions require current optimistic `version` values.

| CRM endpoint | Implemented behavior |
|---|---|
| `GET/POST /native/connections` | List/create encrypted connection drafts |
| `PUT /native/connections/{id}` | Edit/rotate/remove credentials; invalidate verification |
| `POST /native/connections/{id}/test` | Rate-limited, read-only ARI control probe |
| `GET /native/connections/{id}/events?page=1` | Owner-paginated minimal probe history |
| `GET/POST /native/numbers` | List/register E.164 number drafts |
| `PUT /native/numbers/{id}` | Edit association, purpose, hours and attestation references |
| `POST /native/numbers/{id}/actions` | Submit/review/suspend/disable; activation explicitly denied |
| `GET /self-hosted/status` | Config-bound text health evidence; speech not installed |
| `POST /self-hosted/tests/text` | Fixed synthetic structured text request, never customer data |

Native provider-independent architecture currently has an **Asterisk-specific
read-only control adapter**. Documented upstream requests are
`GET {approved_origin}/ari/asterisk/ping` and
`GET {approved_origin}/ari/endpoints/PJSIP/{configured_endpoint}` using server-side
Basic authentication. See official
[Asterisk server API](https://docs.asterisk.org/Asterisk_22_Documentation/API_Documentation/Asterisk_REST_Interface/Asterisk_REST_API/)
and [endpoint API](https://docs.asterisk.org/Asterisk_22_Documentation/API_Documentation/Asterisk_REST_Interface/Endpoints_REST_API/).
Successful ping plus online endpoint establishes control reachability only.
It does not prove SIP trunk registration, number ownership, inbound routing,
outbound permission, call completion, bidirectional audio or transfer.

No guessed native public webhook or media URL is registered. No SIP passwords,
trunk provisioning, Stasis event transport, external-media bridge, dial/answer/
hangup/transfer or RTP transport has been implemented in this batch. Those are
internal implementation work in addition to external telecom approval. Existing
Smartflo validation-only endpoints and authenticated duplicate-event handling are
preserved; refer to [its audit](SMARTFLO_VOICE_AUDIT.md) for their actual scope.

Evidence expires after 15 minutes and configuration changes invalidate it. A
concurrent credential change cannot be overwritten by an older probe. All upstream
responses are bounded, no redirects or environment proxies are used, and sensitive
upstream bodies are not exposed. Probe success cannot activate calling. Number
references are Owner attestations, not verified telecom approval. The current
`activate` action always returns a blocked response because live prerequisites are
unimplemented/unverified. **Completing CRM fields alone will not unlock calls.**

## Deployment and rollback

Use the existing deployment architecture; no new mandatory container or cloud
provider is introduced. Before release: review the diff and additive indexes on
`voice_native_connections`, `voice_phone_numbers`, `voice_native_tests` and
`voice_ai_health`; verify encrypted-secret key backup/restore; run staging tests
against the actual Mongo/Redis/server versions. No destructive migration or seed
is necessary. Ensure frontend and backend are deployed together through the
existing pipeline so the new panels do not target absent routes.

Build/check commands are recorded in [the evidence report](SELF_HOSTED_VOICE_UPGRADE.md).
Use the existing documented systemd units only after confirming which worker unit
exists; do not create or restart guessed units. Keep all live enable flags off.
If regression occurs, restore the previously approved application artifact and
environment, restart only the existing units through the existing deployment
procedure, and preserve additive collections for investigation. Do not delete
numbers, credentials or business records as rollback. Reverify ordinary CRM login,
leads, invoices, permissions, worker and readiness after rollout and rollback.

## Remaining acceptance gates

Before any live enablement, implement the real media/control and streaming speech
adapters, verified consent/authorization, dispatch reconciliation, interruption,
independent outage transfer, identity-bound authoritative financial tools and safe
callback workflow. Then test actual SIP inbound/outbound, number binding, DTMF
where applicable, two-sided audio/recording consent, language quality, barge-in,
silence/hold/voicemail, hangup/cancellation, provider retries/duplicates, reconnect,
credential rotation, worker death/recovery, emergency stop and human handoff.
Run approved staging load with **10 real concurrent calls and 10,000 recipients**,
measure latency/CPU/RAM/VRAM/queues/errors and retain evidence. This is a proposed
test target, not measured capacity. No live acceptance or production approval is
claimed by local mock-transport, synthetic browser or unit test results.
