# Callback workflow execution report — 16 October 2026

Baseline: clean `6ffa4e8`. This continuation implements durable customer callback
requests in the existing CRM. It does **not** make the entire AI assistant production
ready. No server session, hardware measurement, model installation, telephone call,
production write, deployment, commit or push was performed.

The [pre-change workflow audit and current classifications](VOICE_WORKFLOW_AUDIT.md)
cover the voice screens and integration gaps. [Operations](VOICE_CALLBACK_OPERATIONS.md)
documents actual routes, permissions, storage, worker behavior and rollback limits.

## Implemented

- Lead, Loan and Insurance detail pages share a lazy-loaded callback manager with
  real authenticated backend requests. No new sidebar item or navigation change.
- Existing Task records now support optional managed callback metadata. Original
  customer preference, local time, timezone, DST occurrence and change history are
  retained. Existing module follow-up dates and ordinary Task behavior are preserved.
- Explicit confirmation, rescheduling, cancellation and readiness recheck use
  optimistic versions and atomic state/history updates. No manual call completion.
- Canonical record IDs, current stage/record scopes, active employees/accounts,
  existing voice/Task permissions and safe response fields are enforced server-side.
- Idempotency and an active-contact unique index protect against repeated requests
  and cross-module duplicates. Test/production callback records are separated.
- Existing ARQ performs bounded due review and restart recovery. Missing consent,
  suppression, changed binding, inactive accounts, closed calling hours and disabled
  controls remain visible blockers. Expired unconfirmed requests require a new time.
- Owner do-not-call uses the existing global contact-policy API before cancellation;
  suppression survives a subsequent cancellation conflict.
- Existing Settings platform controls include callback automation, defaulting off
  for older records. Hard readiness gates explicitly include voice identity and
  actual live callback safety. No new positive activation path was added.
- Generic Task views show managed state and link to the existing entity detail page;
  generic update/complete cannot bypass callback history.

Implementation files: `callback_schemas.py`, `callback_service.py`,
`callback_router.py`, `CallbacksPanel.tsx`, `callbackApi.ts`; small integration changes
in existing reminders, startup/index registration, platform controls, worker and
the three detail pages. There is no new scheduler, follow-up collection, destructive
migration, secret field, environment variable or dependency change.

## Verification

Final full backend regression: **1,330 passed, 1 skipped**, 568 warnings,
845.24 seconds. The skip is the existing Linux-only speech process test on this
Windows workstation; Linux worker/media acceptance remains pending. Warnings are
existing Starlette/httpx, ARQ/Redis and mongomock deprecations. No regression failed.

| Check | Result and scope |
|---|---|
| New callback backend tests | 19 passed; real services/routes with mongomock, no real MongoDB/PBX/model |
| Full backend regression | 1,330 passed, 1 Linux-only skipped; local tests do not establish live telecom acceptance |
| Backend Ruff | Passed across backend |
| Scoped Linux mypy | Passed, 50 source files including voice/reminder changes and startup |
| Global mypy | 116 existing errors in 11 files, 374 checked; unrelated existing debt remains |
| Python dependency consistency | `pip check` passed; vulnerability matching remains offline as instructed |
| Frontend typecheck/build | Passed with Node 22.23.3; existing large-bundle warning remains |
| Frontend ESLint | Passed with existing Fast Refresh warnings |
| Frontend full regression | 349 tests passed across 70 files, including 6 callback tests; API mocks/synthetic data |
| Local Playwright | Lead detail callback manager at 1440px/390px; no page errors/document overflow |
| Sidebar comparison | Desktop 280px sidebar identical pixel-for-pixel to prior Lead capture |
| Server inventory script | Local Git Bash `bash -n` passed; actual host execution remains pending |

The frontend suite also emits existing jsdom canvas warnings in recruitment tests;
these tests passed. No real financial/customer record was used for browser evidence.
See [capture metadata](screenshots/voice-callbacks-2026-10-16/evidence.json),
[sidebar comparison](screenshots/voice-callbacks-2026-10-16/sidebar-comparison.json),
[desktop](screenshots/voice-callbacks-2026-10-16/lead-callbacks-1440.png) and
[mobile](screenshots/voice-callbacks-2026-10-16/lead-callbacks-390.png).
Loan/Insurance backend relationships are tested; their complete browser journeys,
keyboard/screen-reader journeys and real MongoDB index/concurrency behavior still
need staging acceptance. Simulated browser success does not verify live services.

New tests exercise request replay/conflict, cross-module active-contact uniqueness,
original preference/timezone/DST preservation, confirmation/rescheduling/cancellation,
version races, normal Task preservation, managed Task edit protection, due review,
unconfirmed expiry, suppression, revoked authorization, entity scopes, mock source
rejection, environment separation and recovery through the real ARQ task function.
UI tests verify lazy permission-aware loading, explicit confirmation, persistent
history, idempotent unchanged retries and do-not-call-before-cancellation ordering.

Commands used (from `backend`, existing virtual environment, `DEBUG=false`):

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy app/features/voice_assistant app/features/reminders/models.py app/features/reminders/schemas.py app/features/reminders/mappers.py app/features/reminders/service.py app/main.py --follow-imports=silent --platform linux
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest --rootdir=.. -c pyproject.toml ../tests -n 4 -q --tb=short --maxfail=3
```

Frontend commands used the existing cached Node 22 executable and local installed
tools: TypeScript `tsc -b --noEmit`, Vite production build, ESLint and Vitest
`run --maxWorkers=2`. No package lock was modified. The generated tracked TypeScript
build cache was restored to its baseline after validation. Browser reproduction is
`node scripts/voice-ui-capture.mjs callbacks` with the existing local Vite server,
cached Playwright and system Chrome; fixtures intercept API/external traffic.
`python scripts/compare-callback-sidebar.py` only compares screenshot pixels.
The local Vite process used for screenshots was stopped afterward. `git diff --check`
passed; sidebar/navigation/routes and dependency locks have no changes.

## Remaining implementation and acceptance

Real native PBX control, owner ringing/bridging/transfer and bidirectional media
are still missing. The current native adapter probes ARI; it does not make or
answer calls. Streaming STT/TTS, barge-in, live model sessions, protected customer
identity/tools, spoken callback extraction/clarification, live contact reservations,
retry policy and call-outcome completion are not implemented by this continuation.
Existing mock call screens and campaign dry runs remain simulations/dry runs.
The staff callback form is an ancillary CRM record workflow, not a manual call,
fixed IVR or a substitute for the requested live dynamic conversation runtime.

Actual server OS/CPU/RAM/disk/GPU/Docker/services have not been measured. No approved
trunk, provider/number or speech/model deployment is available. No real engine/media
or live test was run, and ten concurrent calls/10,000 campaign recipients remains
an unmeasured proposed staging target. Single-company record scopes are preserved;
multi-tenancy remains explicitly deferred, not silently implemented.

These are both missing application work and external acceptance requirements;
they cannot all be described as merely waiting for credentials. The safe result
is a tested callback foundation with truthful blockers, not a live-ready platform.
Calling and paid services remain disabled. Current user-supplied deployment paths
and a callback-compatible rollback procedure are in the operations guide. No
production activation or restart is authorized by this code change.
