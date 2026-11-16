# Airtel IQ SMS confirmed-contract update

Date: 16 November 2026. Implemented locally. No deployment, real SMS, live account
validation or handset delivery verification was performed.

## Existing architecture and scope

Updated the existing communication/airtel_iq adapter, integrations/airtel_iq
configuration validation, encrypted IntegrationConfig service, existing no-SMS
validation and owner-confirmed test-SMS endpoint. API Connections remains the
configuration source; no environment variable, second integration, external browser
request, OTP/PIN/authentication architecture, rate-limit or tenant change was added.
The existing single-company database scope and permission engine remain in use.
Airtel-specific mutations and tests additionally require the Owner; delegated
integration permissions for other providers retain their existing behavior.

## Confirmed request contract

Source: account-specific Airtel confirmation supplied in the task attachment.
The supplied entity reference is used explicitly, rather than the different DLT
registration ID. No live Airtel portal lookup was performed.

- POST https://iqsms.airtel.in/api/v1/send-prepaid-sms
- Headers: Accept: application/json and Content-Type: application/json; Authorization
  uses the saved value ASHFNS exactly, without Basic/Bearer. Runtime reads the
  encrypted saved credential, with no backend authentication fallback.
- customerId: the account owner's saved Customer ID, never a synthetic default.
- destinationAddress: one string in a JSON array, the validated 10-digit mobile;
  country-prefix templates are not accepted.
- sourceAddress: ASHFNS; messageType: TRANSACTIONAL.
- dltTemplateId: 1077151820081508033; entityId: AIR7316372024.
- message: Your OTP for mobile verification with Ashapura Financial Services is
  {OTP}. It is valid for 10 minutes. Do not share this OTP with anyone.
  Only {OTP} is replaced with the existing generated four ASCII digits. The actual
  sent string has the original approved spacing, wording and punctuation.

HTTP 200 alone records accepted API submission. Empty, non-JSON or unexpected
JSON bodies do not prevent accepting a 200. Response bodies are discarded; no
Airtel error or delivery JSON schema is invented. Other HTTP statuses record an
unsuccessful submission. HTTP transport errors/timeouts record unknown. No
automatic retry occurs. Deduplication uses a stable provider/reference hash that
also prevents resending the same reference after a configuration edit. The
existing accepted status means submission, never confirmed handset delivery.

## API Connections and validation

The existing fields show the approved endpoint/sender/template, corrected entity
reference, ASHFNS Authorization default, ten-digit destination template and uppercase
message type. Authorization and Customer ID remain password inputs and fully masked
on saved API responses. There is no runtime Customer ID default. The invented JSON
success path/value inputs were removed for Airtel; legacy saved keys remain accepted
but unused. Other SMS providers' field sets and response logic are unchanged.

New configurations cannot be marked contract-confirmed on creation. Save first,
run Validate Configuration (no SMS) against the saved settings, then confirm on
the details page. Required fields and saved secret availability are checked.
Changing settings clears confirmation, validation and previous submission health,
and deactivates the edited configuration. Confirmation cannot be combined with
credential changes. Draft validation does not satisfy the saved-config gate.

No-SMS validation never contacts Airtel. Its existing connection-success boolean
remains false because no connection/submission was proved; explanatory text reports
local configuration consistency. It does not mark an SMS failure, manufacture a
successful-send timestamp, or overwrite a prior real submission health result.
Activation still requires the separate explicit test submission. Test SMS requires
Owner permissions, an explicitly entered mobile and send confirmation, and the
existing rate limit. The test panel is hidden from other roles. Customer PIN-only
cutover behavior was not changed or executed.

## Security checks

Encrypted-at-rest configuration, full provider-secret masking and masked-edit
preservation remain. Logs/audit/submission records do not store the Customer ID,
Authorization header, OTP, full mobile or full request/response body. Submission
records contain a masked destination and status/timing/HTTP code only. Provider
exceptions return sanitized messages and recommend checking the Airtel portal.
SSRF prevention retains the fixed HTTPS endpoint; redirects are disabled. OTP
expiry (10 minutes), single-use, brute-force protection, rate limits and employee/
partner password login remain unchanged. No real SMS was sent in automated tests.

## Files changed

- backend/app/features/communication/airtel_iq.py
- backend/app/features/integrations/airtel_iq.py
- backend/app/features/integrations/service.py
- backend/app/features/integrations/router.py
- backend/app/features/integrations/testers.py
- frontend/src/features/integrations/providerFields.ts
- frontend/src/features/integrations/pages/IntegrationListPage.tsx
- frontend/src/features/integrations/pages/IntegrationDetailsPage.tsx
- frontend/src/features/integrations/components/AirtelTestPanel.tsx
- frontend/src/features/integrations/AirtelConfiguration.test.tsx
- frontend/src/features/integrations/components/AirtelTestPanel.test.tsx
- tests/api/test_airtel_transport.py
- tests/api/test_airtel_configuration.py
- this report

## Tests and remaining uncertainties

Broad backend regression: 107 passed across Airtel configuration/transport,
integrations, OTP delivery, customer PIN authentication and registration bypass.
Latest focused Airtel backend run: 42 passed, including the subsequent no-SMS
health semantics, confirmation gate and owner enforcement, malformed/prefixed
recipients, exact POST/body/header/message, HTTP 200 without JSON success rules,
non-200s, connection failures, ambiguous timeouts, concurrent duplicate suppression,
configuration edits, encryption/masking and rejection of the registration ID.
These runs overlap; they are not additive independent test counts.

Strict mypy passed for the adapter/configuration modules; targeted Ruff passed.
Frontend test/build/lint final results are recorded below. Existing frontend bundle
size and Fast Refresh advisory warnings are unrelated to this update.

Mocked tests prove local construction and handling only. Airtel has supplied no
confirmed error JSON schema or handset-delivery receipt contract. A successful live
HTTP 200 would prove API submission only; phone receipt needs separate confirmation.
No delivery or live account claim is made here.

## Production deployment steps (instructions only, not executed)

1. Back up the existing encrypted integration configuration using the normal database
   backup process. Retain the existing encryption key. Schedule a configuration window
   if Airtel is already active: old registration-ID settings now fail closed until
   corrected. Do not trigger OTP retries or new customer PIN cutover during rollout.
2. Deploy the matching backend and frontend artifacts with the existing production
   deployment pipeline. Restart API instances and any existing processes that load
   the adapter. There are no new dependencies, environment variables, collections,
   indexes or destructive migrations. Do not use the development Compose deployment
   as a production deployment command.
3. As Owner, open API Connections and edit the existing Airtel SMS configuration.
   Retain the current Customer ID by leaving its write-only edit input blank. Set
   endpoint/sender/template/entity/message type/destination to the contract above;
   enter ASHFNS in Authorization. Do not enter the registration ID as entityId.
4. Save with contract confirmation off. Run Validate Configuration (no SMS). This
   performs no network send and does not prove an Airtel submission. Correct any
   local consistency error. Then enable the account-contract confirmation and save
   that confirmation separately, without changing other fields.
5. Enable the configuration using the existing control. STOP before test sending
   unless the Owner explicitly authorizes the send. With that approval, enter the
   test phone number, tick send authorization and click Send test SMS once.
6. If the result is HTTP-200 accepted, check the Airtel IQ portal and separately
   verify receipt on that test phone. For non-200 or unknown/timeouts, inspect the
   portal; do not automatically retry ambiguous submissions. Do not replay old
   pre-upgrade ambiguous submission references after changing configuration.
7. Only after the approved test, use the existing Make Active action. Keep existing
   OTP limits and PIN/authentication settings unchanged. Successful submission and
   confirmed receipt must be documented separately by the operator.

Rollback: restore matching application artifacts through the standard pipeline and
retain encrypted settings/backups. Do not delete OTP challenges or submission
history, do not rotate the encryption key, and do not auto-retry uncertain sends.
The previous adapter's registration-ID/JSON-success assumptions are incompatible
with the confirmed contract; prefer disabling Airtel pending a forward fix rather
than treating old configuration as valid. Other providers are not migrated.


Final frontend results: 8 tests passed across both integration suites; production
build and TypeScript checks passed. Targeted ESLint: zero errors, one pre-existing
Fast Refresh warning in IntegrationListPage. Ruff passed for all seven affected
Python source/test files; the adapter, configuration and focused tests were formatted.
Generated TypeScript build metadata was restored. No commit, push, deployment,
production configuration write, real SMS or PIN cutover was performed.
