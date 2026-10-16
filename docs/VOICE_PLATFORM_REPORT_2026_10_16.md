# Self-hosted platform execution report — 16 October 2026

**Overall production readiness: BLOCKED.** This continuation adds functioning local
control/verification code, not a deployed telephone assistant. No production URL
session, server change, model download, PBX registration or real call occurred.
Python advisory scanning remains offline by user instruction.

## Baseline and preservation

Started clean at `942c63c`. Inspected current voice frontend/API, schemas, encryption,
permissions, Mongo indexes, ARQ/deployment and tests before changing files.
[The initial plan](VOICE_PLATFORM_PLAN_2026_10_16.md) preceded implementation.
Existing architecture/auth/session/Owner RBAC and sidebar remain intact. Decision
001 explicitly defers multi-tenancy: this is a single-company CRM, not a verified
multi-tenant platform. No partial tenant scheme or broad architecture rewrite added.

## Actual delivery

| Component | What works in code | What remains unverified/missing |
|---|---|---|
| Central controls | Persisted test/production settings, CAS changes, history and independent toggles; disables reach existing test paths | Live component runtimes are not installed |
| Native PBX | Existing encrypted read-only ARI probe retained and centrally gateable | No trunk provisioning, live ARI events/control, RTP/WebSocket media or actual version access |
| Numbers | Draft/review/suspend/disable plus reject/revoke; terminal revocation and safe rotation | Independent approval/identity/routing verification and positive verified lifecycle |
| STT | Local whisper.cpp executable adapter, asset hashes, bounded process, reference transcription match | No approved model installed or actual transcription measured here |
| TTS | Local Piper adapter, model/config hashes, actual WAV validation and encrypted private playback route | No voice/runtime installed or real synthesis measured; Python hash does not verify Piper package |
| Inference | Existing Ollama structured text adapter and expiry/config-bound checks; central disable enforced | Actual approved server/model/hardware test; endpoint/model config remains server-managed |
| Local audio pipeline | STT → validated structured inference → TTS with stage timing and per-stage authorization | Per-utterance loading, no warmed streaming/VAD/barge-in; no real model execution here |
| Background jobs | Durable explicit jobs, fixed admission slots, global lease, expiry/recovery, no automatic retry | Actual Linux/process limits and existing server resource contention require staging |
| Live switches/emergency | Owner-only direction disables and atomic emergency stop, no stale-version prerequisite | Positive activation and active-call draining/human fallback are not implemented |
| Dashboard | Existing truthful simulation/operational data preserved; Settings shows real persisted jobs/gates | Full live lifecycle/audio/error analytics remain unavailable |

Test and production **control records and job evidence are separated**. Legacy native
and Smartflo connection records and the Ollama environment are still shared
operator-managed configuration; this is not complete production/test credential or
infrastructure segregation. That migration and separately provisioned resources
remain prerequisites before positive live activation. No auto-switch to production.

Files: new `platform_schemas.py`, `platform_service.py`, `platform_router.py` provide
the control plane; `speech_runtime.py` / `speech_process.py` provide optional local
execution; `speech_jobs.py` and the existing ARQ task/settings provide persistent
verification; `local_pipeline.py` composes actual engine requests. Existing
native/self-hosted/Smartflo/test-console services honor central disables. Settings
adds `PlatformControlsPanel.tsx` / `platformApi.ts`, with genuine backend actions,
error/retry states, private audio and versioned edits. Native number UI adds reject/
revoke. Existing sidebar and ordinary CRM features were not redesigned in this batch.

Additive collections/indexes and API inventory, configuration, safe testing,
deployment and rollback are documented in
[VOICE_PLATFORM_OPERATIONS.md](VOICE_PLATFORM_OPERATIONS.md). Startup creates indexes;
no production migration or seed was run. No new mandatory Python/frontend runtime
dependency or model download was added.

## Acceptance ledger

| Requested definition of done | Status |
|---|---|
| Functional native configuration | Partial: encrypted existing PBX/endpoint configuration and read-only probes only |
| Genuine operator connectivity verification | BLOCKED: actual approved trunk/access and SIP/media implementation |
| Number authorization per call | All live calls denied; positive real authorization/routing not implemented |
| STT installed/loads/transcribes | Adapter implemented; actual installed-model test BLOCKED |
| TTS installed/generates playable audio | Adapter/decoder/private delivery implemented; actual engine test BLOCKED |
| Local model valid responses | Existing real request implementation; actual configured model BLOCKED |
| Real PBX audio pipeline | Local utterance pipeline implemented; PBX streaming bridge missing |
| Controlled inbound/outbound tests | BLOCKED: no approved telecom/test number/server access |
| Central install/configure/toggle | Actual test controls/jobs; installation explicitly directed to reviewed deployment operation |
| CRM live enable/disable | Disable implemented; positive enable BLOCKED, not a completed feature |
| Activation gates | Backend fail-closed and audited; positive all-gates-pass path unimplemented |
| Emergency stop | Durable new-direction block tested; real active-call drain unimplemented |
| Existing CRM/access/sidebar | Preserved; regression evidence below; no multi-tenant claim |
| Tests/builds | Results recorded below; CI engines and HTTP use labelled substitutes |
| Deployment/rollback | Documented; not executed |

## Verification

Before edits: **52 backend tests passed**, 62 warnings, 81.77 seconds
(`test_voice_native`, `test_voice_self_hosted`, `test_voice_platform`).
Intermediate focused run: **57 backend tests passed**, 349 warnings, 46.89 seconds.
Focused frontend: **13 passed / 3 files** before final emergency usability refinements.
Full frontend: **342 passed / 69 files**, 179.10 seconds. TypeScript and production
build passed; bundle-size warning remains. ESLint: **0 errors, 10 existing warnings**.
After final emergency usability changes: **8 focused platform tests passed**,
including stopping while another Settings request is pending.
Full backend regression: **1,308 passed, 1 skipped**, 568 warnings, 766.66 seconds.
After that run, targeted hardening preserved lexical retrieval on inference disable,
added append-only audit metadata, strengthened Unicode/WAV validation and added
Linux worker-death cleanup. Final affected-voice regression: **141 passed,
1 Linux-only skipped**, 496 warnings, 31.25 seconds. The final frontend build
also passed after the emergency-control refinement. No failing regression remains
in these executed tests; actual Linux/model/PBX acceptance is still outstanding.
Whole-backend Ruff and dependency consistency passed; scoped Linux-target mypy
passed **43 files**. Whole-application mypy still reports **116 existing errors in
11 other files** (371 checked); it is not globally type-clean.

Commands from `backend`, with `DEBUG=false`:

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app/features/voice_assistant app/main.py --follow-imports=silent --platform linux
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest --rootdir=.. -c pyproject.toml ../tests -n 4 -q --tb=short --maxfail=3
$voiceTestFiles = @(Get-ChildItem -LiteralPath '../tests/api' -Filter 'test_voice*.py' -File | ForEach-Object { $_.FullName })
.\.venv\Scripts\python.exe -m pytest --rootdir=.. -c pyproject.toml @voiceTestFiles -n 4 -q --tb=short --maxfail=3
```

The first focused retry used an unexpanded PowerShell wildcard and collected no
tests; it was corrected to explicit enumerated file arguments above. No empty
collection was counted as a pass.

From `frontend`, using the existing ignored verified Node 22.23.3 executable:

```powershell
& '.\node_modules\.cache\voice-node22\node.exe' node_modules/typescript/bin/tsc -b
& '.\node_modules\.cache\voice-node22\node.exe' node_modules/vite/bin/vite.js build
& '.\node_modules\.cache\voice-node22\node.exe' node_modules/eslint/bin/eslint.js .
& '.\node_modules\.cache\voice-node22\node.exe' node_modules/vitest/vitest.mjs run --maxWorkers=2 --reporter=dot
```

Engine subprocesses are substituted in Windows automated tests, using synthetic
model/binary/reference fixtures. HTTP inference uses `httpx.MockTransport`. WAV
parsing, checksum verification, encryption, state/queue logic and API authorization
are exercised directly. Mongo is mongomock, not a deployed Mongo/Redis/PBX test.
A POSIX resource/deadline test is explicitly skipped on Windows and must run on
the Linux deployment/CI runner. No mocked pass satisfies a live activation gate.

Browser: approved local Playwright, actual frontend routes with **synthetic API
fixtures**, desktop 1440px/mobile 390px. Initial navigation timeout was corrected
by waiting for the rendered Settings heading rather than network-idle polling.
Both captures have no page error/document overflow. Evidence:
[desktop](screenshots/voice-platform-2026-10-16/platform-settings-1440.png),
[mobile](screenshots/voice-platform-2026-10-16/platform-settings-390.png),
[machine-readable capture](screenshots/voice-platform-2026-10-16/evidence.json).
They establish layout only, not backend or model success.
The desktop sidebar crop also matches the prior approved capture pixel-for-pixel:
[comparison](screenshots/voice-platform-2026-10-16/sidebar-comparison.json).

## Remaining requirements

Existing approved server access is required for actual hardware/service inventory;
no connection name or credentials were available. No hardware/model recommendation
or ten-call capacity is inferred from deployment examples. Native trunk/provider,
operator-approved numbers/caller ID, supported Asterisk version/modules, routing and
network details remain pending. Keep credentials in the normal secure server
configuration channel, never chat or logs.

Internal work still includes native call control/media, warmed streaming speech,
silence/barge-in, transfer/drain/reconciliation, complete independent environment
configuration, trusted authorization verifiers, per-call policy/concurrency
reservations, idempotent real dispatch and full live analytics. Compliance/operator
review, licensed model/language approval, actual speech/audio tests, approved
controlled calls and measured ten-call/10,000-recipient staging follow those changes.
Software flags or entered references cannot substitute for these requirements.
