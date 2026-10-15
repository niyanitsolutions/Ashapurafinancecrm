# Self-hosted voice and CRM design continuation

15 October 2026. Starting checkout: main, 165cbe5, clean. Preserve existing React
19/TypeScript/React Query, FastAPI/Motor/Mongo, Redis/ARQ, bearer auth, permission
engine, single-company scope, artifacts, knowledge publications and campaign data.
The previous execution report is historical evidence, not a new baseline result.

## Audit before changes

The shared UI already has tokens, Card, Button, FormField, DataTable, Modal,
SimplePageLayout and ModuleTabs. It uses orange gradients, elevated shadows and
larger type than the new information-density brief. Forms lack consistent error
associations. The sidebar uses its own approved layout and must retain its exact
appearance, widths, labels, icons, grouping, order, active state and behavior.
No sidebar file, navigation catalog or route authorization will be redesigned.

Voice core/media contracts are already independent of Smartflo. Smartflo settings
and validation-only callbacks work locally; calls remain simulations. Campaign
eligibility and imported artifacts are real persisted workflows, not live dispatch
or capture. No installed PBX, approved trunk, speech model, authoritative EMI
ledger or caller-assurance service is evidenced in this checkout. Compose contains
CRM/Mongo/Redis/worker/Nginx; no native PBX or speech container is installed.

## Controlled batches

1. Establish current tests and screenshot evidence using synthetic browser fixtures;
   inventory routes/pages and shared-component coverage, without production access.
2. Improve the shared content design system and accessibility while protecting the
   sidebar's original tokens and appearance. Review representative desktop/mobile
   pages and preserve tables, filters and business workflows.
3. Add Owner-only native connection/number administration, encrypted credentials,
   allowlisted read-only Asterisk ARI probes, durable test evidence and explicit
   activation blockers. Additive collections/indexes only; no live-control endpoints.
4. Add self-hosted service configuration/readiness as supported by actual installed
   services and documented APIs, never pass a socket/process check as speech readiness.
5. Run focused and broad regression; record exact current results, visual limits,
   deployment/rollback commands and remaining internal/external work.

## Feature ledger

| Area | Starting state | Acceptance dependency |
|---|---|---|
| Shared content UI | Partially implemented | Apply requested palette, density and accessible reusable components; preserve sidebar |
| Every route/page | Existing functionality implemented | Inventory every route; report coverage and page-specific work honestly |
| Native PBX control/media | Missing; infrastructure unavailable | Approved Linux PBX/trunk, network/security/version compatibility and actual media/control tests |
| Number administration | Missing | Persist numbers/connection settings, lifecycle and truthful gated verification |
| Self-hosted AI | Contracts/optional local text path; no approved speech | Licensed model/runtime and hardware approval, actual representative STT/TTS/LLM probes |
| Smartflo | Implemented locally; external verification blocked | Retain optional adapter and existing connection/callback/audio tests |
| Campaigns | Implemented and locally verified dry-run subset | Confirmed callbacks, real-safe dispatch/outbox and approved telecom/consent |
| Financial tools | Missing/blocked | Approved identity method and authoritative payment access |
| Training | Implemented file/publication subset | Isolated scanned PDF/OCR, semantic index and behavior releases remain required |
| Recording | Implemented imported artifacts; live capture blocked | Approved consent, actual two-sided media capture and real STT |
| Production readiness | Not verified | All mandatory acceptance, recovery, measured 10-call/10,000-recipient staging and owner approval |

No model, paid call, account, production seed, destructive migration or live
activation is authorized as a side effect of this continuation. The original
instruction to keep voice blocked without an approved speech service still applies.
Browser screenshot permission was granted in this conversation. Screenshot fixtures
are explicitly synthetic and cannot establish backend or real carrier functionality.

## Completed continuation

Implemented Owner-only native connection/number administration, encrypted
credential replacement, exact operator origin allowlists, bounded read-only
Asterisk probes, optimistic updates, durable probe history and explicit activation
blockers. Added actual config-bound Ollama structured text health probes, with
speech and live readiness explicitly false. Smartflo remains optional. No fixed
IVR, scripted question tree or manual dialer was added.

Shared content primitives now use the requested palette, density, focus states and
accessible field associations. Campaigns and invoice actions use the same system.
Sidebar files, labels, navigation permissions and routes are unchanged; before/after
desktop sidebar pixels match. [Visual evidence and limitations](CRM_VISUAL_REVIEW.md)
and [route inventory](CRM_ROUTE_INVENTORY.md) distinguish shared-component coverage
from individually inspected screens.

### Final local verification

| Check | Actual result |
|---|---|
| Full backend `pytest ../tests -n 4 -q --tb=short --maxfail=3` | **1,279 passed**, 242 warnings, 693.92 seconds |
| Focused voice regression | **105 passed**, 167 warnings |
| Backend `ruff check .` | Passed |
| `mypy app/features/voice_assistant app/main.py --follow-imports=silent` | Passed, 36 source files |
| Full backend mypy | **116 existing errors in 11 other files**; not a clean global typecheck |
| Backend `python -m pip check` | Passed; dependency consistency only |
| Full frontend Vitest | **335 passed**, 68 files, 124.64 seconds |
| Final focused frontend after style refinements | **77 passed**, 18 files |
| Frontend TypeScript/build | Passed; existing large bundle warning remains |
| Frontend ESLint | 0 errors, 10 existing warnings |
| `npm audit --omit=dev` | Zero reported production vulnerabilities at execution time |
| Python advisory lookup | **Offline by user instruction**: automatic approval review initially rejected package/version disclosure to OSV; user then selected keeping the audit offline. No request executed; no vulnerability-free claim |
| Compose configuration | Passed; Docker daemon unavailable locally, no image/runtime test |
| Browser snapshots | Eight captures, no page errors/document overflow; synthetic API fixtures |
| Real SIP/media/AI load and server capacity | Not tested; actual server access and services pending |

Backend command sequence, from `backend` with `DEBUG=false`:

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app/features/voice_assistant app/main.py --follow-imports=silent
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest --rootdir=.. -c pyproject.toml ../tests -n 4 -q --tb=short --maxfail=3
```

Frontend used the verified local Node 22.23.3 executable, without changing global
Node or package manifests. From `frontend`, invoke that executable with
`node_modules/typescript/bin/tsc -b`, `node_modules/vite/bin/vite.js build`,
`node_modules/eslint/bin/eslint.js .`, and
`node_modules/vitest/vitest.mjs run --maxWorkers=2`. Final focused run covered
components, leads, invoices and voice assistant. Screenshot replay requires the
ignored local Playwright dependency and Chrome described in the capture script;
it is a review harness, not an application dependency.

New native tests cover authorization, encryption/redaction, unsafe origins,
upstream authentication/status/response handling, draft uniqueness, forbidden
activation, stale versions/evidence and credential-rotation races. Self-hosted
tests use actual HTTP mock transports to exercise structured request/response,
response size/type bounds, expiry/model binding, safe errors and no-request-when-
disabled behavior. These prove local contracts, not an installed PBX or model.

### Explicit remaining work

The overall assistant is **not production ready**. Real native SIP/trunk
provisioning, Stasis/media transport, streaming STT/TTS/LLM integration and live
call control are missing. Positive activation is intentionally unavailable;
operator configuration and successful control probes cannot enable it yet.
Authoritative identity/payment tools, confirmed callbacks, live dispatch outbox/
reconciliation, independent outage handoff, PDF/OCR/semantic training and complete
behavior releases remain internal implementation work. Telecom/number approvals,
licensed speech choices, actual host measurements, consent policy and real staging
acceptance are external dependencies. Existing simulated calls and dry-run
campaigns retain those labels; no fake production capability was introduced.

The user requested inspection of the existing server before model selection.
Deployment references contain placeholders, not access details or actual inventory;
no SSH profile is configured here. The read-only inventory script and existing-
architecture deployment/rollback handover are in
[SELF_HOSTED_VOICE_OPERATIONS.md](SELF_HOSTED_VOICE_OPERATIONS.md). No new server,
GPU, provider, credential or production specification has been assumed.
