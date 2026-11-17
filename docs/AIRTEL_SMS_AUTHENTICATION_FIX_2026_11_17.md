# Airtel SMS authentication credentials and pending-contract fix

17 November 2026. Implemented locally only. No deployment, production data access,
real SMS, handset receipt or live OTP verification was performed.

## Result and exact remaining blocker

Implemented the Primary Owner's secure Customer ID / Username / Password workflow.
The Owner subsequently confirmed that the portal's Authorization placeholder does
not explain how these credentials authenticate the prepaid endpoint, and explicitly
authorized completing storage while blocking submission and activation.

**No three-credential wire authentication mechanism is implemented or claimed.**
There is no guessed Basic/Bearer encoding, invented token endpoint, signing format,
refresh timer or environment setting. The default backend authentication_ready
returns false and cannot be enabled through owner input or a runtime configuration
flag. Saved credentials, a legacy Authorization value, Enable, or account-contract
confirmation cannot bypass it. A documented implementation is required before this
guard can truthfully allow requests.

The reported HTTP 401 indicates an authentication rejection, but its precise root
cause is not established. The known code gap was that Username and Password were
previously legacy-only values: not offered in the form and not consumed by the
adapter. Only a manually supplied Authorization value was sent. That is not evidence
of the correct mechanism for all three credentials. Claiming the 401 or real OTP
delivery is fixed would be unsupported.

## Sources and missing Airtel confirmation

Inspected current SMS adapter/configuration, field-mapping and earlier account
notes. Prior notes asserting a manual header do not establish the new requested
Customer ID/Username/Password mechanism. The local Airtel voicebot guide describes
a different voice API; its HMAC flow was not borrowed for SMS.

Checked Airtel's official public documentation pages:
- https://www.airtel.in/business/b2b/airtel-iq/api-docs/sms/overview
- https://www.airtel.in/business/b2b/airtel-iq/api-docs/sms/sms-utility

They returned a JavaScript application shell through the available research tools;
no authoritative authentication procedure for send-prepaid-sms could be verified.
Third-party instructions and a different send-sms endpoint were not treated as an
account-specific source. The Owner explicitly confirmed no exact instructions are
currently available. This is a missing confirmed contract, not proof Airtel lacks
any documentation elsewhere.

Ask Airtel for a redacted, account-applicable working request or official instructions
for POST https://iqsms.airtel.in/api/v1/send-prepaid-sms specifying:

1. Where Customer ID, Username and Password go (body/header/auth exchange).
2. Exact Authorization scheme/value construction and encoding/signing rules.
3. If tokens are used: exact token URL/method/fields, response fields, expiry,
   refresh rules and how authorization attaches to the SMS POST.
4. Required account/API permissions or provisioning for the prepaid endpoint.

Do not send live credentials through chat or commit them. After confirmation, wire
that documented mechanism into the existing adapter and rerun mocked and explicit
Owner-approved live verification. No operator can bypass the missing contract today.

## UI and security behavior

- Existing Airtel configuration now has Customer ID (text), Username (text), and
  Password (password with Show/Hide). Showing reveals only the currently typed new
  value; no saved credential is hydrated into an input.
- Reopening shows saved masked indicators and empty credential inputs. Non-secret
  settings still hydrate correctly; the endpoint stays read-only and independent.
- Blank or whitespace-only credential edits preserve saved values at both UI and
  backend layers. A new nonblank value replaces its existing encrypted value.
  Passwords are not trimmed into a different value.
- The old manually entered Authorization input/default was removed from the form.
  Existing legacy values remain encrypted/masked for compatibility; they cannot
  authorize a request or activate the integration while authentication is pending.
- Configuration create/update now reuse the existing database-backed
  require_primary_owner dependency. Existing legacy-owner treatment and company
  scope are preserved; Secondary Owners and staff cannot change Airtel settings.
- UI checks the existing /owner/me profile before enabling credential entry and
  rechecks on session identity/role changes. The backend remains authoritative.
- All three credentials use the existing encrypted config blob. Server-side merge
  and masking remain in the existing backend configuration service/mapper; no
  decrypted secret is returned to frontend. There is no browser persistence of
  Airtel credentials, no .env credential setup and no source-code credential editing.
- Updating actual settings clears the old local validation, contract confirmation,
  submission proof, receipt verification and active state using the existing flow.
  Empty credential edits do not cause that reset.

Local validation checks all three saved credentials and existing endpoint/DLT/mapping
rules. It sends no SMS, does not prove authentication and cannot create Last Success.
A successful local result explicitly says authentication is awaiting confirmation.
The UI displays why sending/activation are blocked, even if a legacy record has a
historical active flag. The test OTP screen, expiry/single-use/rate-limit logic,
audit history and sanitized HTTP/error diagnostics remain available for the eventual
documented mechanism. Authentication blocking happens before any SMS submission or
test challenge is created. Enabling a validated configuration alone grants no send.

Existing sender, DLT template/entity reference, ten-digit destination array,
TRANSACTIONAL message type, prepaid URL and exact approved message are unchanged.
No registrations/templates were created. Other SMS providers, employee/partner login,
customer accounts, sessions and password/PIN policies were not modified. In accordance
with the Owner's instruction, Airtel-dependent OTP sends remain unavailable until
Airtel confirms authentication; this does not disable existing accounts or change
their current login policy. No PIN-only cutover was executed.

## Files changed

Backend:
- backend/app/features/integrations/airtel_iq.py: three-credential local readiness,
  explicit pending-auth status, immutable runtime block and validation guards.
- backend/app/features/integrations/service.py: Primary Owner create/update checks,
  blank credential preservation, pending-auth activation rejection.
- backend/app/features/integrations/mappers.py: safe authentication status/message.
- backend/app/features/integrations/testers.py: local validation/pending-auth notice.
- backend/app/features/communication/airtel_iq.py: fail closed before provider I/O;
  existing transport/diagnostic code retained for documented future authentication.

Frontend:
- frontend/src/features/integrations/components/AirtelCredentialFields.tsx (new).
- frontend/src/features/integrations/providerFields.ts: three fields, no manual header.
- frontend/src/features/integrations/pages/IntegrationListPage.tsx and
  pages/IntegrationDetailsPage.tsx: secure field rendering, saved indicators/pending UI.
- frontend/src/features/integrations/configForm.ts and api.ts: credential keys and
  safe server-derived auth status; pending prerequisite before sending.

Tests/artifacts:
- tests/api/test_airtel_authentication_pending.py (new): real default fail-closed,
  encryption/masking, blank preservation/rotation and Primary Owner enforcement.
- frontend/src/features/integrations/components/AirtelCredentialFields.test.tsx (new).
- frontend/src/features/integrations/AirtelConfiguration.test.tsx and AirtelDetails.test.tsx.
- tests/api/test_airtel_transport.py, test_airtel_configuration.py,
  test_airtel_diagnostics.py, test_airtel_live_workflow.py and test_airtel_workflow_browser.py:
  explicit test-only confirmed-auth fixture for historical transport/workflow coverage.
- tests/api/test_airtel_credentials_browser.py and scripts/airtel-credentials-ui-check.mjs
  (new default-runtime blocked browser coverage, with no authentication stub).
- docs/screenshots/airtel-credentials-2026-11-17/ and this report.

## Data and migration

No new collection, schema migration or dependency. Username and Password were already
accepted sensitive keys; the existing encrypted storage/masking is reused. Legacy
Authorization data is retained, not deleted or rewritten. Derived auth status is
not a writable setting or an environment flag. There is no automatic production
credential migration or change to customer login policy.

## Tests and actual evidence

- Broad backend regression: 141 passed across configuration, transport, diagnostics,
  test OTP, generic integrations, normal OTP/PIN and registration-bypass suites.
- Latest default-runtime pending-auth suite: 4 passed (includes legacy saved-header
  non-bypass added after the broad run).
- Frontend integration suites: 16 passed; customer/username text, password show/hide,
  masked reload, blank edits, role gating and pending send/activation covered.
- Actual local FastAPI + isolated real MongoDB + Chrome: 1 browser test passed at
  1440px and 390px, exercising three-field update/save/reload, password reveal/hide,
  masked indicators, endpoint preservation, validation and disabled send/activation.
  The provider callable was forbidden; SMS submission and test-OTP collection counts
  remained zero. No test phone received anything. Screenshots use synthetic accounts.
- Strict mypy passed for the modified adapter/configuration modules. Ruff passed.
- Frontend build/typecheck passed. Existing bundle-size and Fast Refresh advisories
  are unrelated; introduced component warning was removed by separating constants.

Important test distinction: historical HTTP 200/400/401/403/429/5xx, timeout, duplicate,
redaction and receipt-flow tests use an explicitly named TEST-ONLY auth-confirmation
stub to exercise those independent components. It is not a real Airtel mechanism and
cannot be configured in production. Default blocking tests and the new browser test
use the actual unmodified false guard and prove no network call is possible. Mocked
results do not demonstrate authentication, live submission or handset delivery.

## Commands and production status

Exact local verification commands (no credentials or real SMS):

```powershell
$env:DEBUG='false'
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_airtel_authentication_pending.py tests/api/test_airtel_configuration.py tests/api/test_airtel_transport.py tests/api/test_airtel_diagnostics.py tests/api/test_airtel_live_workflow.py tests/api/test_integrations.py tests/api/test_pin_auth.py tests/api/test_otp_delivery.py tests/api/test_registration_otp_bypass.py -q -n 2 --tb=short
npm --prefix frontend test -- src/features/integrations
npm --prefix frontend run build
```

Exact artifact-build commands derived from repository Dockerfiles, for a future
reviewed release (not executed, and not themselves production rollout commands):

```powershell
docker build -f docker/backend/Dockerfile -t afs-crm-backend:airtel-credentials-20261117 .
docker build -f docker/nginx/Dockerfile -t afs-crm-web:airtel-credentials-20261117 .
```

An exact production host rollout command cannot be established from this repository:
RUN_LOCAL.md explicitly excludes the AWS/CI-CD deployment pipeline, and the checked-in
Compose file references development env files and a dev frontend target. Do not
substitute that as a production command or invent SSH hosts, unit names or overrides.
Use the approved production pipeline/runbook after separate authorization. No
integration-specific environment update is necessary. Rollout would intentionally
block Airtel sends until the missing authentication mechanism is implemented; review
that impact before any future deployment.

## Owner steps

For the local/reviewed credential UI (and later only after approved deployment):

1. Sign in as Primary Owner; open the EXISTING Airtel SMS config in API Connections.
2. Preserve saved Customer ID or enter its replacement, then enter portal Username
   and Password. Use Show/Hide only to inspect a newly typed password.
3. Save Changes. Reopen/refresh: all three inputs must be empty, with Saved indicators;
   endpoint and confirmed DLT settings must remain unchanged. Blank edits retain secrets.
4. Run Validate Configuration (no SMS); resolve missing field errors. Local success
   is not successful authentication. Do not change Authorization schemes to experiment.
5. Obtain the redacted Airtel authentication instructions listed above. Submission
   and activation remain blocked until that documented mechanism is implemented.
6. After that implementation, its tests and separate deployment approval, explicitly
   enter the Owner's intended test mobile, authorize ONE OTP send, and inspect the
   actual HTTP result. For unknown outcomes check Airtel portal before another attempt.
7. Only actual handset receipt and correct code entry within ten minutes may mark
   receipt verified. Then Set Active; PIN-only cutover remains a separate approved
   operation after customer enrollment. No live steps 6/7 were performed here.

Live authentication: NOT VERIFIED. HTTP 401 root cause: NOT ESTABLISHED beyond the
known missing mechanism. Real OTP submission/receipt/verification: NOT RUN. Production
success: NOT CLAIMED. No production deployment, credential mutation or real SMS occurred.


Final results: additional HTTP-400 diagnostic regression passed (1 selected test),
final frontend build/typecheck passed, Python lint/format checks passed, and targeted
frontend lint has zero errors with only the pre-existing Fast Refresh advisory.
The new default-runtime browser used no auth-confirmation stub and verified zero
SMS submissions and zero test challenges. Local browser server was stopped and
TypeScript build cache restored. No commit, push, deployment or real SMS was performed.
