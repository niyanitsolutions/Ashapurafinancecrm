# Smartflo voice audit — 14 October 2026

## Current provider documentation recheck

Official API token, webhook and bi-directional streaming pages were rechecked on
14 October 2026. [API token documentation](https://docs.smartflo.tatatelebusiness.com/docs/api-token)
now describes a migration: tokens created before 9 August 2026 expire at the end
of 31 October 2026. Replace those credentials before that deadline. Portal tokens
have selectable 1/7/15/30/90-day expiry; API-generated tokens default to one hour.
Use the provider's actual recorded expiry in CRM configuration; do not infer the
creation date or expiry by inspecting an opaque token. New credentials invalidate
previous connection-test evidence; live activation remains blocked.

The [webhook page](https://docs.smartflo.tatatelebusiness.com/docs/webhook) describes
a Headers configuration control, but its wording also refers to response-body
values. Verify actual HTTP-header delivery in the account; never silently accept a
body token or omit callback authentication because of this ambiguity.
The [streaming protocol](https://docs.smartflo.tatatelebusiness.com/docs/bi-directional-audio-streaming-integration-document)
continues to specify mu-law/8 kHz, 100 ms incoming media delivery and outbound
160-byte multiples with media/mark/clear messages. Offline codec replay remains
distinct from account entitlement, endpoint reachability and real speech testing.

## Before-change evidence and feature status

Inspected the implementation report, feature router/service/models/schemas,
permission/catalog initialization, React panels/API bindings, ARQ deadline poll,
encryption utility, test fixtures, configuration and deployment runbook. Working
tree was clean. No production server or provider account was accessed.

| Feature | Actual status before upgrades | Evidence/dependency |
| --- | --- | --- |
| Navigation and access | Functional | Startup catalog; existing bearer/RBAC; Owner settings |
| Dashboard/history | Mocked | `voice_calls` stores only simulator sessions; paginated reads |
| Incoming/outgoing/handoff | Mocked | State transitions and deadlines; no telephone transport |
| Usage limits | Partial | Mock admission quotas; no durable paid dispatch reservations |
| Knowledge | Partial | Reviewed/versioned manual articles; lexical retrieval, no semantic index or file ingestion |
| Dynamic AI | Partial | Contextual local-model text adapter; no live STT/TTS, audio session or model quality verification |
| Provider Connections | Missing | Read-only hardcoded Exotel readiness, no credentials/test/settings |
| Webhooks/events | Missing | No provider ingress, signature/auth verification or event inbox |
| Voice Studio/recordings/campaigns | Missing | Explanatory tabs only, no functional backend workflows |
| Recovery | Partial | Mock ARQ recovery/heartbeat; no telecom reconciliation or independent fallback |
| Smartflo | Missing/blocked | No implementation or verified account access |

## Verified provider reference

Provider API origin is `https://api-smartflo.tatateleservices.com`.
Use server-side `Authorization: Bearer <API_TOKEN>`; tokens can have expiry,
IP restrictions and scopes. Do not ask users to paste account passwords into
ordinary settings. [API token documentation](https://docs.smartflo.tatatelebusiness.com/docs/api-token)

| Purpose | Documented endpoint | Implementation decision |
| --- | --- | --- |
| Read-only authentication/scope test | `GET /v1/users?limit=1` | Request only on explicit Owner test; discard personal response data |
| Future human escalation | `POST /v1/call/options` | No live operation now; identifiers/transfer behavior need sandbox verification |

Sources: [Fetch Multiple Users](https://docs.smartflo.tatatelebusiness.com/reference/fetch-multiple-users),
[Call Operations](https://docs.smartflo.tatatelebusiness.com/reference/v1calloptions).
The latter has inconsistent identifier requirements in its notes; confirm the
actual account contract before implementing paid call control. No manual dialing,
IVR menus, prerecorded answer selection or fixed conversation trees will be added.

Smartflo webhook triggers include `Call received on Server`, `Call answered by
Agent`, and `Call hangup (Missed or Answered)`. Payload keys are configured by
mapping documented variables; they are not universal provider event names.
Configure JSON POST and UTC ISO timestamps. Delivery can retry, so acknowledge
only after durable insertion and enforce a unique deduplication key.
[Webhook reference](https://docs.smartflo.tatatelebusiness.com/docs/webhook)

No HMAC signing algorithm/header was found in that reference. Its Headers section
is ambiguous about placement. A callback bearer secret is an explicit CRM security
requirement, not a claimed Smartflo signature. Confirm its delivery in the account
request preview; never put secrets in URL query parameters. If arbitrary HTTP
headers cannot be sent, keep ingress disabled and obtain a documented authenticated
gateway/provider arrangement.

Smartflo media uses camelCase identifiers, base64 G.711 mu-law mono at 8 kHz,
with stream lifecycle events and playback marks. Sending `clear` can flush playback
for interruption support; output frames need 160-byte alignment. Existing Exotel
PCM framing cannot be reused unchanged.
[Bidirectional media protocol](https://docs.smartflo.tatatelebusiness.com/docs/bi-directional-audio-streaming-integration-document)

Dynamic endpoint requests can carry custom authentication headers and mapped call
metadata. A working resolver must return only `success` and `wss_url` within the
provider's deadline. Returning an unavailable endpoint may terminate a call, so
do not register a resolver while the speech engine is missing.
[Dynamic endpoints](https://docs.smartflo.tatatelebusiness.com/docs/dynamic-and-static-websocket-options-in-the-voice-streaming-page)

## Controlled upgrade phases

1. Connection foundation: encrypted write-only credentials, fixed API origin,
   Owner-only configuration, safe read-only connection test, accurate readiness.
2. Observation: registered callback URLs, authenticated disabled/validation-only
   ingress, durable deduplicated event logs with retention; no call-state activation.
3. Audio foundation: Smartflo-specific protocol validation, offline interruption
   tests and a fail-closed WSS route. No fake audio-stream connection result.
4. Activation dependencies: verified sandbox/entitlements, deployed TLS/reachability,
   speech/model adapters, dynamic conversation/audio evaluation, reviewed consent
   and operational policies. These cannot be replaced by a checkbox or a codec test.

## Configuration and verification plan

Backend-managed fields: version; confirmed public HTTPS origin; API token
(write-only encrypted); separate callback token (write-only encrypted); callback
mode `disabled`/`validation_only`; token expiry; latest test result/time.
API origin is fixed to the documented provider host to prevent credential exfiltration.
Use existing `ENCRYPTION_KEY`, `FRONTEND_BASE_URL` and infrastructure settings;
credentials will not be committed to environment templates or browser storage.
No Smartflo secret environment variable is required by the planned database-backed
connection configuration. Existing optional `VOICE_LOCAL_AI_*` settings remain
text-console configuration, not live voice readiness.

Required automated tests: Owner versus employee access; secret encryption/redaction;
invalid URLs/expiry/version races; missing token; 401/403/429/5xx/timeouts/invalid
response handling; stale test invalidation; blocked live endpoints; callback auth,
oversized/malformed payloads, duplicate insertion and channel separation; retained
minimal metadata; stream identity/format/replay/stop/output/clear validation.
Frontend tests must distinguish configured, tested, failed and blocked states.

Required manual provider tests: least-privilege token/IP restrictions; actual callback
header/payload preview; external HTTPS delivery/retry; Smartflo voice-bot access;
WSS authentication; real STT/model/TTS exchanges; interruptions/latency; language
quality; transfer confirmation; outages and independent fallback. Connection-test
success proves only the tested read-only scope, not these capabilities.

## Implemented upgrades and actual status

| Upgrade | Current status |
| --- | --- |
| Provider configuration | Functional: Owner-only API/UI, encrypted write-only tokens, optimistic versioning, removal/rotation, expiry and stale-test status |
| Connection test | Functional read-only HTTP client; automated tests mock Smartflo responses; real account validation still pending |
| Callback ingestion | Functional authenticated JSON observation endpoint; disabled by default; validation-only records never dispatch calls |
| Event logs | Functional durable unique deduplication, pagination, minimal metadata and 30-day TTL; raw bodies/audio/recording URLs are not retained |
| Audio protocol | Functional offline Smartflo mu-law codec; identity/sequence/format/stop validation and output media/mark/clear |
| Dynamic conversation | Partial: asynchronous model/RAG/speech orchestration with context, cancellation, immutable safety, escalation flag and duration/turn bounds; speech/model tests use adapters |
| Public audio ingress | Deliberately blocked: WSS declines connections, resolver refuses success while verified speech adapters/reservations are missing |
| Real calls/campaigns/recordings/cloning | Disabled and still require additional implementation plus approvals; saving credentials does not unlock them |

No manual dialing API, IVR dialog menu or fixed business Q&A system was added.
Call lifecycle validation is transport state, not a scripted customer conversation.
Conversation memory holds generated text for context, not a verified spoken transcript.
The recognition/synthesis ports must be connected to approved real speech services,
with mu-law transcoding where required; the current codec does not supply STT/TTS.
There is no live Smartflo dialing/control adapter or per-call authenticated media
reservation yet. Audio time limits must eventually be coupled to confirmed provider
hangup, not assumed to end a telephone call simply because audio generation stops.

## Routes, credentials and callback configuration

Owner-only routes under `/api/v1/voice-assistant/smartflo`:

- `GET /connection`, `PUT /connection`: metadata and write-only secrets.
- `POST /tests/connection`: one bounded `GET /v1/users?limit=1`; redirects/proxy
  inheritance and automatic HTTP retries are disabled; provider user data is discarded.
- `POST /tests/webhook`: local secret-decryption/persistence diagnostic only.
- `POST /tests/audio`: local protocol diagnostic only.
- `GET /events?page=1`: retained observations, 25 rows per page.

Registered callback routes are `POST /webhooks/incoming`, `/webhooks/answered`,
and `/webhooks/hangup`. They require the separately configured
`Authorization: Bearer <callback token>` header and `callback_mode=validation_only`.
This is configurable callback authentication, not an invented provider signature.
JSON bodies must map `uuid` to `$uuid` and `start_stamp` to `$start_stamp` using
UTC ISO 8601 with offset; hangup also requires `call_status` mapped to `$call_status`.
Only `Answered` and `Missed` are accepted for that value. Other fields are rejected;
validate the exact account request preview rather than forwarding an assumed native
event envelope. Request bodies are bounded to 16 KiB. Insert failures must not be
acknowledged as received; provider behavior for non-2xx versus no response still
needs sandbox verification. Exact duplicates are acknowledged without new records.
Different channels and final outcomes remain distinct observations, including late
or out-of-order arrivals; they cannot reopen/modify simulated calls.

`POST /stream/resolve` and `WSS /media` are actual registered backend routes but
are **not operational stream endpoints**. The UI derives candidate URLs only after
an explicit public HTTPS origin is saved. DNS/TLS, callback header delivery and
provider access remain unverified. Do not register the resolver or WSS route now:
the resolver deliberately refuses a success payload and could cause call failure
if attached to a live provider flow prematurely.

New collections: `voice_provider_connections` (unique provider key, encrypted
credentials) and `voice_provider_events` (unique dedupe key, provider/time index,
UTC expiry TTL). Indexes are ensured on normal startup and by the targeted catalog
script. Existing call/knowledge data is not migrated. New dependencies: none.

No new Smartflo credential environment variable is required. Enter tokens through
the Owner connection form; never commit them. Existing production `ENCRYPTION_KEY`
must remain stable or credentials must be re-entered after key rotation. Public
origin is stored explicitly rather than inferred from browser/proxy headers or
assumed from `FRONTEND_BASE_URL`. `VOICE_LOCAL_AI_*` continues to configure the
optional local text model only. Confirm token expiry and least-privilege Users scope
in Smartflo before pressing the API test button; an old success becomes stale after
30 minutes and any settings change invalidates it.

## Verification and deployment

Current automated backend run: **88 passed**, covering Smartflo, existing voice,
access-control and dashboard suites. Feature Ruff and strict mypy passed. The
frontend build passed; lint had zero errors and 10 existing warnings. The 8 feature
frontend tests passed. Full frontend regression initially reported 312 passed and
one timeout in the unchanged extended-applicant insurance-form test. That test passed
in isolation; the complete retry with two workers passed **313 tests across 62 files**.
Test-library deprecation and bundle-size warnings
do not represent validated provider behavior. No actual Smartflo request with real
credentials, live socket, telephone call, model-quality benchmark or paid service
activation was performed. The whole backend regression suite was not rerun; its
historical results in the original report are not results of this upgrade.

Reproduce from `backend` on Windows:

```powershell
$env:DEBUG = 'false'
.\.venv\Scripts\python.exe -m pytest -c pyproject.toml ../tests/api/test_voice_smartflo.py ../tests/api/test_voice_assistant.py ../tests/api/test_voice_exotel.py ../tests/api/test_access_control.py ../tests/api/test_dashboard.py -q
.\.venv\Scripts\python.exe -m ruff check app/features/voice_assistant ../tests/api/test_voice_smartflo.py
.\.venv\Scripts\python.exe -m mypy app/features/voice_assistant --follow-imports=silent
```

From `frontend`: `npm run build`, `npm run lint`, `npm test -- --maxWorkers=2`.

For the documented server layout, after deploying the reviewed source revision:

```bash
cd /opt/afs-crm/backend
.venv/bin/pip install .
.venv/bin/python ../scripts/voice_catalog.py
cd ../frontend
npm ci
npm run build
sudo systemctl restart afs-crm-backend
```

Keep the existing ARQ worker running for mock deadlines; no live dispatch job is
added. No production migration/deployment was executed and no Nginx changes were
made. Roll back the source/package and frontend build, then restart the backend;
leave the additive collections intact for audit. Reset callback ingestion to
disabled before rollback if it had been configured. Do not register/change any
Smartflo provider flows during deployment of this development foundation.

Manual acceptance: save authorized least-privilege token; verify API test and expiry;
check actual provider callback header preview and authenticated external delivery;
verify duplicate/retry behavior and body mapping; separately obtain voice-bot
entitlements, select speech/model providers, implement signed/reserved media
sessions and validate natural follow-ups, unknown financial questions, barge-in,
languages, transfer confirmation and independently hosted outage fallback. These
remain prerequisites for the real-time voice acceptance test.

The user has not approved a speech/AI service. Live voice must remain blocked until
that decision and the required provider verification are complete.
