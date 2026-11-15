# Airtel VoiceBOT extension — test report

15 November 2026. Baseline HEAD `05ca74a`. No production deployment or live calls.
The supplied 22-page Airtel PDF was read before implementing its contracts.

## Completed checks

| Check | Observed result |
|---|---|
| Before changes: all voice API tests plus existing Airtel SMS configuration/transport | 272 passed, 1 Linux-only skipped; 250.37s |
| After new protocol/config/UI integration and simulation isolation: same set plus new Airtel Voice tests | 332 passed, 1 skipped; 215.85s |
| Latest Airtel Voice focused suite, including dependency-log suppression | 62 passed; 9.24s |
| Latest Airtel Voice plus unit/dashboard integration tests, with shared API test setup loaded | 94 passed; 10.65s |
| Full backend API final rerun, 4 pytest-xdist workers | **1,681 passed, 14 skipped**, 2,009 warnings; 766.77s |
| New Airtel panel plus existing Smartflo panel | 9 passed across 2 files |
| Full frontend final rerun, one worker | 457 passed across 85 files; 267.52s |
| TypeScript check and production Vite build | Passed; 437 modules, existing large-chunk advisory |
| Frontend ESLint | 0 errors, 10 existing warnings in unrelated shared/CRM files |
| Ruff changed/new backend modules and new tests | Passed |
| Full backend `ruff check .` | 4 existing import-order errors: 3 in unchanged employee/service.py, 1 in unchanged integrations/router.py |
| Targeted strict mypy on 8 new modules (`--follow-imports=silent`) | Passed; not a claim that repository-wide historical mypy errors are resolved |
| `git diff --check` | Passed; Windows line-ending notices only |

The final broad API run completed successfully after the fixture correction below.
Test counts from overlapping runs must not be added together as distinct coverage.
The 14 skips cover opt-in real database/browser infrastructure and platform-specific
tests; they are not verified integrations. Existing deprecation warnings remain
(Starlette test client, mongomock naive datetime/throw, ARQ Redis close).

## What these tests prove

- HMAC canonical bytes/date/digest/signature match an independent Node crypto
  fixture. Mutated body bytes change the digest. REST tests mock HTTP, check exact
  signed request bytes and documented paths, reject redirects/errors/oversized
  responses, and never retry a submitted call automatically.
- C2C defaults to denied until its origin is explicitly confirmed internally;
  no browser call action or live activation path is exposed. Unknown 2xx response
  bodies are not promoted into invented call IDs or answered states.
- The real Airtel codec handles handshake/start, both documented encoding/custom
  parameter variants, audio, DTMF, hold/unhold, marks, clear, stop and termination.
  Wrong identities, malformed/oversized envelopes, unknown marks and invalid audio
  are rejected. Clear-related mark echoes cannot be counted as played audio.
- G.711 conversion matches all 65,536 PCM16 inputs and all 256 μ-law codewords using
  Python3.12 `audioop` as an independent **test-only** oracle. Runtime conversion
  does not depend on that deprecated module. Resampling is not implied.
- Owner authorization, secret encryption/redaction, version conflicts, credential
  clearing and local evidence invalidation work with mocked Mongo/Redis. The UI
  blocks tests of unsaved credentials and clears secret inputs after successful save.
- Recording query tokens and transport headers are suppressed from current
  httpx/httpcore dependency logs in the Airtel request's async context; concurrent
  unrelated request logging and logging after errors remain functional.
- Mock call controls and reconciliation cannot transition a synthetic future
  Airtel-provider record. Existing callback/knowledge/recording/SMS suites passed
  within the voice/SMS regression set.
- Progressive 1/10/50/100/250/500 codec and overlapping dynamic-core tests check
  separate identities, retrieved evidence, histories, generated media and cleanup.
  Model/speech/authorization are fake. No real STT, inference, WSS transport,
  distributed admission, telephony or sustained latency/capacity is measured.

## Failures investigated during this run

The initial broad frontend run had 453 passes and 3 failures: two recording tests
used an artifact that expired on 14 November, and one insurance form exceeded the
default 5s timeout under parallel load. The insurance test passed in isolation.
Recording tests now fix `Date.now` to the fixture period, restore the spy after
each test and explicitly check that an expired artifact cannot open playback.
Playback behavior was preserved. The full final single-worker run passed 457 tests;
no timeout threshold was increased and no application safety check was removed.

The initial focused WSS denial test inadvertently entered full application startup
without the suite's mock database and failed database selection. It was corrected
to test the registered denial route without lifespan startup, as the existing
Smartflo denial test does. All focused tests subsequently passed.

The first parallel broad backend run stopped at 476 passed, 3 skipped and 1 failure
in `test_case_status_control::test_valid_insurance_status_update_persists_and_reflects_in_list`.
Its shared helper reused a portal customer's mobile with a different name, triggering
the existing customer identity guard (409). The helper now supplies the seeded
customer's real fixture name. Production identity checks were preserved. The full
rerun passed after this fixture correction; the earlier serial broad run was interrupted
and is not counted as completed regression evidence.

Running unit/dashboard integration tests alone initially lacked the API suite's
synthetic Settings defaults. Collecting the focused API tests alongside them loads
the existing shared test setup; that combined run passed 94 tests without source
changes to dashboard/settings code or connections to real infrastructure.

## Reproduction

Use `backend/.venv/Scripts/python.exe`, `DEBUG=false`, `PYTHONDONTWRITEBYTECODE=1`.
From backend, run pytest with `--rootdir=.. -c pyproject.toml -p no:cacheprovider`.
The focused suite is `../tests/api/test_voice_airtel.py`; the voice regression set
is all `../tests/api/test_voice_*.py` plus `test_airtel_configuration.py` and
`test_airtel_transport.py`. Tests use only synthetic credentials, mocked HTTP and
isolated fake data. No advisory inventory was sent to an external service.

The final full API regression command adds `-n 4` and targets `../tests/api`.
The supplemental combined check targets `../tests/api/test_voice_airtel.py`,
`../tests/unit` and `../tests/integration` together, loading the existing API test
environment defaults. Real Mongo/browser suites require their explicit opt-in
configuration and were not enabled.

From frontend, use the existing cached Node22 executable
`node_modules/.cache/voice-node22/node.exe` with `node_modules/vitest/vitest.mjs run
--maxWorkers=1`, TypeScript `tsc -b`, Vite build and ESLint. Generated tracked
TypeScript cache metadata is restored to its prior bytes after validation.

## Still untested or unimplemented

No actual server inventory, installed AI model, approved speech service, approved
Airtel account/trunk, auth handshake, reachable webhook, true incoming timeout,
real outbound conversation, human bridge/return-to-AI, recording ingestion,
authenticated event/CDR reducer, SFTP collector, distributed media admission or
500-real-conversation load test exists in this evidence. No Playwright screenshots
or real Mongo/Redis acceptance were produced in this phase. The supplied guide's
unresolved account-specific contracts are listed in the architecture/onboarding docs.

Release remains **NO-GO for live calls**. Offline tests and configured credentials
cannot substitute for those gates. Production-oriented foundations are partial
implementation, not a completed production voice platform.
