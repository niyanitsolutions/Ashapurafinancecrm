# Airtel IQ SMS Basic Auth final fix — 18 November 2026

Implemented locally only. No deployment, production database change, or real SMS was performed. All provider calls in tests were mocked.

## Cause and implementation

The previous adapter deliberately blocked authentication because the earlier supplied contract did not specify how Username and Password authenticate. Its older transport used a manually saved Authorization value. The new owner-supplied Airtel employee/Postman confirmation specifies HTTP Basic Auth and supersedes that earlier uncertainty. The old API Entity ID was also incorrect. These are confirmed local implementation defects; a production delivery result cannot be inferred from local tests.

The existing adapter now passes saved Username and Password to `httpx.BasicAuth`. HTTPX generates Authorization; application code does not construct or store it. Customer ID remains the separate JSON `customerId`. No token endpoint, Bearer flow, or Airtel response schema was invented. Missing credentials still produce a useful error; the constant undocumented-authentication blocker is removed.

Exact POST mapping:

| Field | Value |
| --- | --- |
| URL | `https://iqsms.airtel.in/api/v1/send-prepaid-sms` |
| customerId | Saved Customer ID |
| destinationAddress | `[mobile]`, current validated ten-digit ASCII recipient |
| dltTemplateId | `1077151820081508033` |
| entityId | `1001474305342749488` (string) |
| messageType | `TRANSACTIONAL` |
| sourceAddress | `ASHFNS` |

The approved message wording is unchanged. Only its secure four-digit OTP is substituted. Customer OTP and explicit test OTP use the same adapter. Customer records are not modified. The owner supplies the explicit test recipient. No example recipient is saved or hardcoded. `destination_template`, retained as a backward-compatible configuration key, now stores `[]`; the actual outgoing array always contains the runtime recipient, never this empty mapping marker.

HTTP 200 means API submission accepted, regardless of response body shape; it does not prove handset delivery. Existing sanitized diagnostics retain HTTP status and distinguish non-200 (including 400, 401, 403, 429 and 5xx), timeout, connection failure and unexpected response. Unknown outcomes are not retried. Durable reference deduplication remains in place.

## Configuration upgrade and security

The UI loads the corrected Entity ID and readonly dynamic destination mapping. An existing configuration with obsolete mappings exposes **Apply confirmed SMS mappings**. Saving corrects the known old `AIR7316372024` ID and old curly-brace destination mappings, removes the obsolete manual Authorization value, preserves Customer ID/Username/Password and clears previous configuration/receipt proofs. New credentials typed before this action are included in the same save. Arbitrary invalid mappings are rejected rather than guessed.

An optional explicit migration provides the same known-value correction across existing Airtel SMS records. It defaults to dry-run, uses ciphertext compare-and-swap protection, skips other providers/deleted records, preserves encrypted credentials and enabled state, and clears active/verification state. It never sends SMS. Neither migration mode was run against a configured production database.

Encryption, masked write-only secrets, blank-field credential preservation, Primary Owner credential permissions and Password Show/Hide are preserved. Saved secrets never repopulate browser inputs. Provider response redaction includes credentials, mobile, OTP and message; tests exercise echoed Basic Authorization redaction. No credentials, OTPs or personal payloads were logged. Test OTP hashes, ten-minute expiry, wrong-attempt limits, single consumption and configuration-bound receipt verification remain unchanged. Activation requires a newly accepted explicit test and verified received OTP. Customer PIN cutover is separate and is not enabled by activation. No employee/partner/session/RBAC changes were made.

## Files changed

- Backend: `communication/airtel_iq.py`; integrations `airtel_iq.py`, `service.py`, `mappers.py`, `testers.py`; new `airtel_migration.py`.
- Frontend integrations: `providerFields.ts`, `configForm.ts`, `api.ts`, `pages/IntegrationDetailsPage.tsx`, `pages/IntegrationListPage.tsx` and configuration/details tests.
- New operator script: `scripts/migrate_airtel_basic_mapping.py`.
- Backend regressions: Airtel transport, configuration, previous authentication-block tests, diagnostics, live-workflow and browser fixtures; new migration test. The historical authentication-pending test filename remains, but tests exercise real credential readiness without bypass stubs.
- Browser scripts: `scripts/airtel-workflow-ui-check.mjs`, `scripts/airtel-credentials-ui-check.mjs` (result description updated).
- Evidence: `docs/screenshots/airtel-basic-auth-2026-11-18/` desktop/mobile screenshots and JSON results.

## Validation results

Backend regression command (PowerShell, repository root):

```powershell
$env:DEBUG='false'
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_airtel_transport.py tests/api/test_airtel_configuration.py tests/api/test_airtel_authentication_pending.py tests/api/test_airtel_live_workflow.py tests/api/test_airtel_diagnostics.py tests/api/test_airtel_basic_migration.py tests/api/test_pin_auth.py tests/api/test_otp_delivery.py tests/api/test_integrations.py tests/api/test_registration_otp_bypass.py -q -n 2 --tb=short
```

**146 passed**, 1406 existing mongomock UTC deprecation warnings, 147.68 seconds. Includes actual HTTPX Basic header generation through MockTransport, exact JSON mapping, distinct recipient arrays, encrypted/masked credentials, blank preservation, HTTP responses/malformed bodies/timeouts, duplicate suppression, OTP expiry/single use and migration dry-run/apply/idempotence. No authentication-readiness test bypass remains.

```powershell
npm --prefix frontend test -- src/features/integrations
npm --prefix frontend run build
backend/.venv/Scripts/python.exe -m mypy --config-file backend/pyproject.toml --follow-imports=silent backend/app/features/integrations/airtel_iq.py backend/app/features/communication/airtel_iq.py backend/app/features/integrations/airtel_migration.py
```

Frontend: **17 passed across four files**. Production build (`tsc -b && vite build`) passed; existing bundle-size advisory remains. Targeted mypy: **no issues in three files**. Targeted Ruff: **all checks passed**. Python compileall and `git diff --check` passed. Targeted ESLint from `frontend/`: zero errors, one existing Fast Refresh export warning in IntegrationListPage. The initial ESLint invocation from the repository root lacked the frontend config; rerunning from the correct directory passed.

Browser command (requires the local Vite server at port 5175 and isolated loopback MongoDB fixture):

```powershell
$env:DEBUG='false'
$env:AFS_AIRTEL_BROWSER_CHECK='1'
$env:AFS_INVOICE_TEST_MONGO_URI='mongodb://127.0.0.1:27017'
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_airtel_workflow_browser.py -q -s --tb=short
```

**1 passed**, six existing mongomock deprecation warnings, 41.77 seconds. Both **1440px desktop and 390px mobile** passed save/reload, readonly endpoint, correct mappings, local validation, contract confirmation, Enable, explicit mocked submission, OTP verification, activation and no automatic PIN cutover. No runtime errors or page overflow. Screenshots were inspected. This is simulated receipt proof, not real Airtel delivery.

## Production commands and remaining deployment information

No production rollout was executed. The repository's Compose file uses `.env.development` and a development frontend target; it is not a verified production deployment procedure. The actual production host/orchestrator/image registry/service names and release command are not established here. An exact production rollout command cannot responsibly be supplied without those details.

These exact artifact-build commands match the checked-in Dockerfiles (not executed as a deployment):

```powershell
docker build -f docker/backend/Dockerfile -t afs-crm-backend:airtel-basic-20261118 .
docker build -f docker/nginx/Dockerfile -t afs-crm-web:airtel-basic-20261118 .
```

After owner-approved rollout through the established production procedure, preferably use the Primary Owner UI mapping upgrade. For an approved bulk upgrade, from a checked-out repository with the intended database and encryption environment securely configured, these are the exact operator commands:

```powershell
$env:PYTHONPATH=(Resolve-Path backend).Path
# Read-only counters; inspect target first. Does not send SMS.
backend/.venv/Scripts/python.exe scripts/migrate_airtel_basic_mapping.py
# Only after approving the target/backup and dry-run result:
backend/.venv/Scripts/python.exe scripts/migrate_airtel_basic_mapping.py --apply
```

Do not paste credentials into shell commands. The migration script is not included in the backend image; do not assume a container script path exists. The application migration module is included with backend source. Unknown/arbitrary mapping values require explicit owner correction rather than automatic replacement.

## Manual test after owner-approved rollout

1. Primary Owner opens the existing Airtel integration. Apply corrected mappings if offered. Enter credentials only if missing/changing them; blank inputs preserve saved values. Save.
2. Run **Validate Configuration (no SMS)**. Confirm and save the Airtel contract. Enable the integration. These actions do not send SMS or prove authentication.
3. Enter the intended test handset's ten-digit number, explicitly authorize the test, and press **Send test SMS** once. This step requires owner authorization; it was not performed here.
4. Review sanitized history. HTTP 200 confirms submission only. For 401/403 inspect Airtel account credentials/permissions; for 429 inspect quota/throttling; for other non-200 inspect the sanitized response/portal. For an unknown outcome, check the portal before a new manual attempt; no automatic retry occurs.
5. Receive the OTP on that handset, enter it in the verification panel within ten minutes, then verify. Never copy OTPs into logs or documentation. Set Active becomes available only after receipt verification for the current configuration.
6. Confirm activation persists after reload. Leave customer PIN-only sign-in cutover unchanged unless separately authorized.

No undocumented authentication mechanism remains after the supplied Basic Auth confirmation. Actual credential validity, Airtel account/DLT acceptance, production egress and handset delivery still require the explicit live test above. Local mocks do not establish them.
