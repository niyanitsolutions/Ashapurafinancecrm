# Airtel IQ and customer portal PIN authentication

Implementation report — 13 November 2026.

## Scope and architecture

PIN authentication applies **only to customers**. Owners, employees and referral
partners continue using the existing password login, password recovery, account
status, geofencing, RBAC and session flows. Both login tabs remain available;
Customer is the default tab. PIN enrollment, recovery, completion and login enforce
the customer role on the backend. Changing a customer's role invalidates an
outstanding PIN setup authorization.

The repository uses React/TypeScript/Vite, FastAPI, Motor/MongoDB and Redis. User
identity is shared across roles. The existing AuthService still creates and revokes
JWT/session families. PIN operations live inside that auth feature. Airtel uses
the existing API Connections catalog, encrypted integration config, permissions,
test history and audit logs. The database represents one company, as confirmed
by the user; no new tenant resolver or membership system was introduced.

The implementation stages were: inspect architecture; add encrypted Airtel draft
configuration; isolate the provider transport; add database-backed customer OTP
and PIN flows; add customer login/admin UI; test and document rollout. No production
migration, cutover, deployment or real SMS send was performed.

## Airtel contract: supplied versus unconfirmed

Supplied account example specifies POST
`https://iqsms.airtel.in/api/v1/send-prepaid-sms`, JSON request/response accept
headers and an Authorization header. The adapter sends exactly these body keys:
`customerId`, `destinationAddress`, `dltTemplateId`, `entityId`, `message`,
`messageType`, `sourceAddress`.

The approved fixed values are sender `ASHFNS`, template `1077151820081508033`,
entity `1001474305342749488`. The message is preserved exactly:

> Your OTP for mobile verification with Ashapura Financial Services is ##numeric##. It is valid for 10 minutes. Do not share this OTP with anyone.

Only the numeric placeholder is replaced with a cryptographically generated
four-digit OTP, preserving leading zeros.

**Unconfirmed:** actual Authorization scheme/value, destination array element
structure and mobile format, permitted messageType values and response schema.
No Basic/Bearer scheme, country prefix, message type or success code is assumed.
The dedicated adapter isolates these rules behind explicit encrypted configuration:

| Field | Purpose |
|---|---|
| Customer ID / Username / Password | Account credentials, fully masked after saving |
| Authorization header value | Exact complete value confirmed for this account; username/password are not automatically combined into a guessed scheme |
| Message Type | Explicit account-supported value |
| destinationAddress JSON array | Confirmed array structure containing exactly one `{{mobile}}` placeholder and one destination element; the placeholder receives the existing registered ten-digit mobile |
| Response success field path | Explicit dot-delimited field path; numeric segments can address array elements |
| Response success value | Explicit JSON string, integer or boolean, matched with its exact type |
| Account-specific API contract confirmed | Must be enabled before any transport call |

These fields have no operational defaults. Incomplete configuration fails closed.
The fixed endpoint and DLT identifiers cannot be redirected or changed through
configuration. Customer credentials remain in existing Fernet-encrypted storage;
production must retain its existing managed ENCRYPTION_KEY. No Airtel environment
variables or credentials in source/browser storage are needed.

Saving a draft or clicking ordinary Test Connection sends no SMS. After obtaining
the missing rules from Airtel, save them, enable the configuration, enter a test
mobile and explicitly confirm **Send test SMS**. Only a 2xx response with the exact
configured success value records acceptance and permits activation. Confirm actual
receipt on that test phone before treating SMS as live. Acceptance does not establish
delivery. Editing credentials/configuration clears the prior success and activation.
An in-flight test cannot apply its success to different saved credentials.

The adapter has bounded connect/write/read/pool timeouts, no redirects and no
automatic retries. Submission references plus configuration identify durable
duplicate-send records. Timeouts/ambiguous results remain unknown and are not
resent under the same reference. Records contain masked destination, status,
HTTP code and timing; never OTP, Authorization or raw request/response bodies.
The approved OTP template is deliberately unavailable as a generic message-center
SMS fallback. Existing legacy six-digit OTP and registration templates are not
silently converted to this four-digit customer login template.

## Customer flows and security

First-time registered customers choose verification, enter the SMS OTP, and choose
and confirm their own PIN. Verification alone returns a five-minute, single-use
authorization, never a normal session. Successful PIN completion uses the existing
session issuer. Normal customer login uses mobile and PIN without sending OTP.

Forgot PIN uses a separate purpose, the same generic initiation response for unknown,
ineligible and undelivered accounts, and a short-lived single-use authorization.
Reset replaces the bcrypt PIN hash, increments its version and revokes all existing
sessions. Session-family checks compare the PIN version, including across refresh,
so stale sessions and refresh races cannot retain access. Reset returns a success
message and requires login; it does not create a session.

PIN and OTP accept exactly four ASCII digits. PINs use the existing bcrypt salted
password hash. OTP hashes use HMAC with the existing server secret plus a random
challenge identifier. Raw codes, PINs and authorization tokens are never persisted
or echoed, including in development mode. The PIN must differ from the verified OTP;
reset also requires a PIN different from the old PIN.

MongoDB compare-and-set operations protect challenge resend, verification, proof
consumption and account PIN changes. Expiry is checked in queries rather than relying
on delayed TTL cleanup. New challenges invalidate earlier codes and authorizations.

| Control | Limit |
|---|---|
| OTP expiry / verification attempts | 10 minutes / 5 per challenge |
| OTP resend | 60 seconds between sends; 5 requests/hour/mobile and account |
| OTP initiation IP | 10 requests/10 minutes |
| OTP verification IP | 30 requests/10 minutes |
| PIN completion IP | 20 requests/10 minutes |
| PIN login | 20 requests/minute/IP; 10/15 minutes/mobile |
| Account PIN lock | 5 attempts, reserved atomically; 15-minute lock, then recovery |

Existing HTTP rate limiting also applies. Durable limits survive process restarts.
Forgot-PIN responses intentionally cannot disclose whether delivery succeeded for a
particular mobile. The UI explains that missing codes require retry or administrator
help without exposing account eligibility.

## API and additive schema changes

Under `/api/v1/auth/pin`: GET `policy`; POST `start`, `verify`, `complete`, `login`,
`cutover`. `start`/`verify` use `FIRST_TIME_LOGIN` or `FORGOT_PIN`; purpose is bound
to the stored challenge. `cutover` remains owner-only and affects customers only.
POST `/api/v1/integration-configs/{id}/airtel-test-sms` requires existing integration
edit permission, an enabled config, explicit send confirmation, mobile and request ID.

User fields: optional `pin_hash`, `pin_epoch` (default zero), `pin_updated_at`,
`mobile_verified_at`, `failed_pin_attempts`, `pin_locked_until`. Existing
`is_mobile_verified` is reused. Session `auth_epoch` defaults to zero for legacy rows
and is preserved on rotation.

New collections: `auth_pin_challenges`, `auth_pin_limits`, `sms_submissions`,
`auth_login_policy`. Normal startup adds unique challenge/authorization indexes,
challenge TTL cleanup, limit TTL cleanup and submission lookup indexes. Existing
user/password/session data is not dropped or bulk rewritten. Missing optional fields
remain compatible. MongoDB must support aggregation update pipelines (4.2+).

## Customer migration and operational rollout

1. Keep existing internal account login and provisioning unchanged. Review the
   change and existing managed encryption/JWT keys before deployment.
2. Obtain the missing account rules from Airtel and enter credentials through API
   Connections. Use an authorized test mobile, explicitly send, inspect acceptance
   and independently confirm receipt. No live verification has been done here.
3. Activate the tested Airtel config. Initial policy is `enrollment`; existing
   customers without PINs temporarily retain the clearly labeled migration password
   login so they are not silently locked out.
4. Have registered customers complete OTP verification and choose their PIN. Password
   login/recovery stops for each customer once their PIN is configured. PIN does not
   create new CRM identities or replace existing registration/profile provisioning.
5. After all active customers enroll, the owner can explicitly confirm **Enable
   customer PIN-only sign-in** in the Airtel configuration. Backend refuses while
   active customers remain unenrolled or Airtel is not tested and active. Staff
   enrollment is not required. Newly provisioned customers then use first-time PIN
   verification; customer passwords cannot establish sessions.
6. The cutover has no public reversal/password-fallback endpoint. Retain a working
   owner password login for administration, monitor submission failures and use
   existing account-management controls for disabled accounts.

No bulk migration script is required for the optional fields. Catalog/index creation
uses existing startup conventions; the policy change is a separate explicit action.
Do not run a production cutover merely to test this implementation.

## Files and verification

New backend files: `auth/pin_service.py`, `communication/airtel_iq.py`,
`integrations/airtel_iq.py` under `backend/app/features`.
Modified backend files: auth models/indexes/router/service/session_lifecycle;
communication adapters; integration indexes/mappers/router/schemas/service/testers;
`scripts/seed.py` (provider catalog only).

New frontend files: auth `pinApi.ts`, `components/PinAuthPanel.tsx` and its tests;
integration `components/AirtelTestPanel.tsx` and its tests, `AirtelConfiguration.test.tsx`.
Modified frontend files: LoginPage and tests; integration list/details/provider fields.
New API tests: `test_pin_auth.py`, `test_pin_mongo_integration.py`,
`test_airtel_transport.py`, `test_airtel_configuration.py`.

Tests use synthetic provider contract fixtures and mocked transport; these values
are **not** asserted to be valid Airtel account settings. Real MongoDB tests use only
an explicitly supplied loopback URI and a random disposable `afs_pin_test_*` database.
They cover concurrent resend/verification/completion/login and cleanup their own DB.
Other coverage includes role rejection and retained staff passwords, enrollment,
purpose/expiry/attempt limits, reset/session revocation, duplicate sends, exact
headers/body/template, timeout/rejection/malformed responses, masking, integration
RBAC, cutover gating, customer/internal tabs and explicit admin send confirmation.

Run the focused backend suite with `DEBUG=false` and optional
`AFS_PIN_TEST_MONGO_URI=mongodb://127.0.0.1:27017`; use
`python -m pytest -c backend/pyproject.toml tests/api/test_pin_auth.py tests/api/test_pin_mongo_integration.py tests/api/test_airtel_transport.py tests/api/test_airtel_configuration.py tests/api/test_auth.py tests/api/test_integrations.py tests/api/test_communication.py`.
Frontend: `npm --prefix frontend test -- src/features/auth src/features/integrations`
and `npm --prefix frontend run build`.

Live Airtel authentication, actual acceptance schema, real handset delivery and
production readiness remain unverified until the account-specific rules and real
test are supplied and completed by an authorized administrator.

Verification completed: 101 focused backend tests passed (including the real local MongoDB concurrency test); 18 frontend tests passed; frontend production build passed. Strict mypy passed for the five new/extended API modules. The build reports its existing large-bundle warning; no live SMS or deployment was performed.
