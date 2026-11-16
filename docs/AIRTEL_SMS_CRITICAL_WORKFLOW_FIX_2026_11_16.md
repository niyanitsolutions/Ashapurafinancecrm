# Airtel SMS endpoint, validation and test-OTP workflow fix

16 November 2026. Local implementation. No production deployment, configuration
write, live SMS, handset receipt or live OTP verification was performed.

## Root-cause investigation and limits

Traced API Connections create/edit state, API payloads, request schemas, encrypted
IntegrationConfig persistence, read/update serialization, provider validation and
transport request construction. No Customer ID-to-endpoint alias, positional swap,
numeric conversion or database field assignment was found. The actual storage key
is api_url; customer_id is a separate key inside the encrypted JSON object. The
existing backend rejects a numeric api_url, and the transport already posts to the
confirmed fixed Airtel HTTPS endpoint rather than trusting arbitrary UI text.

Confirmed frontend defects: edit state started empty and presented saved values
only as placeholders; fields lacked separate autofill names; API Endpoint remained
an editable plain-text field. This exposed the first text field to browser/password
manager autofill and made a displayed/autofilled value easy to confuse with saved
configuration. Dirty-field detection also considered every touched key, including
no-op/reverted edits, which could keep contract confirmation disabled. The
screenshots' autofill styling is consistent with that explanation, but screenshots
alone do not prove the numeric value was persisted. Production API/database values
were not inspected, so the exact origin of that production value remains unverified.
No claim is made that a backend mapping swap was reproduced.

Fix: hydrate public edit values from the saved API response, keep Customer ID and
Authorization blank/write-only, submit only meaningful changed keys, identify
inputs by provider/key, suppress credential autofill and make the confirmed endpoint
read-only. Its displayed value is read from the backend, not replaced by a frontend
constant. The backend supplies expected_endpoint separately. If a legacy record
really contains an invalid endpoint, Owner can explicitly Restore confirmed Airtel
endpoint and Save Changes; the backend validates and persists the repair without
replacing the saved Customer ID. There is no silent production rewrite.

Other confirmed workflow defects: no-SMS validation used a false connection-success
flag and looked like an SMS failure; confirmation relied on a generic last-test
timestamp instead of successful validation of these settings; no receipt OTP was
stored or verified; activation relied on successful submission alone. Those are
now separate, durable states and guards.

## Implementation

1. Configuration saved: existing encrypted configuration and masked API responses.
2. Configuration validated: no network request; explicit field errors for endpoint,
   Customer ID, sender, template/entity reference, Authorization availability,
   destination JSON, message type and confirmation format. Success returns kind
   configuration_validation and a clear no-SMS message. It does not update Last
   Success, Last Failure, authentication or delivery. A keyed fingerprint binds
   successful validation to the saved settings; a compare-and-set prevents a stale
   validation result from validating concurrently changed credentials.
3. Contract confirmed: explicit Owner selection after successful saved validation;
   confirmation persists after reload. Populate/save alone never confirms it.
4. Test submitted: Owner must explicitly enter a ten-digit test number and authorize
   sending; saved validation, confirmation and Enable are checked by the backend.
   The existing adapter sends the exact approved OTP body with saved encrypted
   credentials. HTTP 200 means accepted submission; non-200 means rejected;
   transport ambiguity means unknown, with portal-check instructions and no retry.
   Submission history includes its own kind and status; validation is not a send.
5. OTP verified: a test-only challenge uses the existing PIN/OTP service's keyed
   otp_digest and durable limit helpers, secure random four digits, ten-minute
   expiry and atomic single-use consumption. It is bound to Owner, config, current
   settings, latest test and requested mobile (stored as a keyed digest). No OTP,
   raw mobile or credential is returned or stored in plaintext. Five wrong attempts
   exhaust a challenge; verification also has an Owner-level rate limit. An expired,
   used, stale-settings, wrong-mobile or wrong-code challenge is rejected. This
   cannot create a customer auth session or enroll/change a PIN.
6. Active: requires current validation, confirmed contract, Enable, actual accepted
   test submission and verified test OTP. Activation uses a configuration snapshot
   compare-and-set so a settings change cannot race past verification. A new test
   starts inactive pending its verification. Settings changes invalidate validation,
   receipt proof and active state. No automatic PIN-only cutover occurs.

Added one prerequisite to the existing separately authorized customer PIN-only
cutover: a legacy active/submitted Airtel config without test receipt proof cannot
satisfy it. The cutover checkbox still requires independent Owner approval.
Customer password, employee/partner password login, normal OTP expiry/single-use,
rate limits, RBAC, sessions and company scope are otherwise unchanged.

The Airtel request contract remains the account-confirmed POST endpoint, exact
saved Authorization value (without Basic/Bearer), sender ASHFNS, template
1077151820081508033, entity reference AIR7316372024, one ten-digit recipient string,
TRANSACTIONAL and the exact approved message with only OTP substitution. Customer
ID is never guessed or defaulted. No error JSON/delivery-receipt schema is invented.

## Data additions and migration

IntegrationConfig gains validated timestamp/keyed fingerprint, test challenge ID,
last submission status and test-verified timestamp. API responses expose safe
workflow metadata and the confirmed endpoint, never the keyed fingerprint or OTP.
IntegrationTestLog gains kind and submission_status with backward-compatible
defaults. Old no-SMS history is labeled as configuration validation in the Airtel
UI when recognizable, without rewriting history.

New integration_airtel_test_otps collection holds only the keyed OTP/mobile digests,
challenge/config/Owner bindings, expiry, attempt count, submission state and used
flag. Existing integration-index setup adds an expires_at TTL index. Runtime checks
expiry directly, independent of asynchronous TTL deletion. No bulk migration,
credential rewrite or new environment setting is required. Existing saved
credentials remain encrypted with the existing key. Legacy configs have no new
validation/proof by default and must complete the new workflow before activation
or customer PIN-only cutover. An already-active legacy config is not silently
rewritten by this change; operators should disable it in the approved rollout window
before re-verification.

## Files changed

Backend:
- app/features/integrations/airtel_iq.py: consistency errors, fingerprint and guards.
- app/features/integrations/airtel_test.py: new test-only send/verify orchestration,
  reusing the existing adapter and OTP helpers.
- app/features/integrations/models.py, schemas.py, mappers.py: additive workflow,
  result kind and safe response mapping.
- app/features/integrations/service.py: validation/confirmation/enable/activation gates.
- app/features/integrations/router.py: existing send endpoint delegates to orchestration;
  adds airtel-verify-test-otp. Existing provider is retained.
- app/features/integrations/testers.py: local validation result, no provider call.
- app/features/integrations/indexes.py: challenge TTL.
- app/features/auth/router.py: one receipt-proof prerequisite on explicit cutover.

Frontend:
- src/features/integrations/configForm.ts: public hydration/changed-value/prerequisite helpers.
- src/features/integrations/api.ts: safe workflow/result types.
- src/features/integrations/pages/IntegrationDetailsPage.tsx: actual values, endpoint
  repair, confirmation, six states, precise disabled reasons and separate history.
- src/features/integrations/pages/IntegrationListPage.tsx: autofill-safe field identity;
  Airtel creation no longer silently runs a saved validation action.
- src/features/integrations/components/AirtelTestPanel.tsx: explicit send/OTP verify,
  blank test mobile on page load, no automatic resend or cutover.
- src/features/integrations/providerFields.ts: submission versus receipt guidance.

Tests/artifacts:
- tests/api/test_airtel_live_workflow.py (new).
- tests/api/test_airtel_configuration.py, tests/api/test_pin_auth.py (updated expectations).
- tests/api/test_airtel_workflow_browser.py and scripts/airtel-workflow-ui-check.mjs (new).
- frontend/src/features/integrations/AirtelDetails.test.tsx (new);
  AirtelConfiguration.test.tsx and components/AirtelTestPanel.test.tsx (updated).
- docs/screenshots/airtel-sms-workflow-2026-11-16/ and this report.

## Validation

- Combined backend regression: 118 passed across Airtel configuration/transport/new
  workflow, generic integrations, PIN auth, OTP delivery and registration bypass.
- Integration frontend suites: 12 passed, including endpoint save/reload isolation,
  readonly/autofill identifiers, confirmation, explicit send and received-code entry.
- Local actual FastAPI + isolated real MongoDB + Chrome journey: 1 passed, covering
  desktop 1440px and mobile 390px, refresh persistence, validate, confirm, enable,
  submit, verify and activate; no PIN cutover, page errors or horizontal overflow.
  Airtel was fully mocked. Test OTPs reached only an in-memory mock mailbox and
  the test driver's private input, never an API response or real handset.
- Browser artifacts record provider mocked/no SMS. Screenshots contain synthetic
  accounts and masked credentials, not production accounts.
- Strict mypy passed for the configuration and test orchestration modules.
- Targeted Python Ruff passed. Frontend lint has no errors and retains the existing
  Fast Refresh advisory in IntegrationListPage. Final build/focused checks below.

Distinct evidence: automated mocks prove construction/state handling; local
configuration validation proves internal consistency only; a real HTTP 200 would
prove API submission; actual handset receipt and successful real code verification
remain untested. No real Airtel submission/delivery claim is made.

## Controlled production procedure ? approval required

The attachment explicitly says not to deploy automatically and to wait for Owner
approval. Nothing below was executed:

1. Approve the reviewed release and arrange a safe configuration window. Back up
   encrypted integration settings and retain the existing encryption key. If a
   legacy Airtel config is active, disable it through the Owner UI before this
   re-verification window; avoid affecting other SMS providers or PIN/login policy.
2. Deploy matching backend/frontend artifacts via the existing production process.
   Start the backend with existing index setup to create the challenge TTL index.
   No new credentials, environment variable or scheduler is needed.
3. As Owner open the existing Airtel integration. Verify actual API Endpoint value
   after refresh. If a legacy malformed value is present, use Restore confirmed
   Airtel endpoint, Save, and refresh again. Leave Customer ID and Authorization
   edit inputs blank unless intentionally changing them; the saved values remain.
   Check the existing confirmed sender/template/entity/destination/message type.
4. Save required changes and run Validate Configuration (no SMS). Resolve each named
   field error. Explicitly select Confirmed with Airtel, Save, and refresh to prove
   persistence. Click Enable when the prerequisites are met.
5. The Owner must now explicitly enter their own test phone and authorize ONE test
   send. Do not copy a number from a screenshot, a prior session or a fixture.
   Click Send test SMS once. Do not send during migration, startup or background work.
6. Inspect the recorded result. HTTP 200 is accepted submission only. For rejected
   or unknown outcomes inspect Airtel IQ portal with safe timestamp/status/code
   diagnostics; do not guess another Customer ID/payload or automatically retry.
7. When the real SMS arrives, Owner enters the received code against that same test
   number within ten minutes and clicks Verify test OTP. Record actual receipt and
   verification separately from submission. Never paste the OTP or credentials into
   logs, chat, a ticket or this report.
8. Only after successful proof, Set Active. Refresh and confirm all six states. Do
   not enable customer PIN-only sign-in unless separately approved. Normal employee
   and partner authentication remains unchanged.

Live result: NOT RUN. Deployment approval, an explicitly Owner-entered phone/send
consent, actual Airtel HTTP response, real handset receipt and live OTP verification
are still pending. Production endpoint history cannot be diagnosed conclusively
without authorized read evidence; local mapping/persistence regressions pass.

Rollback: keep encrypted configuration, challenge/submission/audit history and
receipt metadata. Roll back matched application artifacts only. Disable Airtel
pending a forward fix rather than treating old HTTP-only activation as receipt
proof. Do not delete or replay uncertain submissions, rotate encryption keys or
change customer password/PIN policy as part of rollback.


Final checks: the focused workflow suite passed 9 tests, including concurrent
single-use verification and the legacy-active cutover guard. The production frontend
build and TypeScript checks passed (existing bundle-size advisory only). Ruff lint
passed; new Python modules/tests were formatted. The local browser server was stopped
and generated TypeScript build metadata restored. No commit, push, production
configuration mutation, deployment or real SMS was performed.
