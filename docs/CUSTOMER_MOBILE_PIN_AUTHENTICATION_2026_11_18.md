# Customer mobile + PIN authentication — 18 November 2026

Implemented locally only. No production deployment, production data migration, or real SMS was performed. The owner's reported successful Airtel test was accepted as context; automated verification used mocked Airtel responses exclusively.

## Existing architecture inspected

- `User` is the existing authentication identity, with a globally unique mobile within the existing company database. `Customer.user_id` links the customer profile to that identity. Database scope, roles and ownership remain unchanged.
- `AuthService` issues existing bearer access/refresh sessions and maintains session-family rotation/revocation. The customer PIN service already composed this service; it already implemented customer-only PIN login, first-time enrollment, Forgot PIN, durable OTP challenges, limits and PIN epochs.
- Registration previously collected name/password/address and invoked the older staff-invitation OTP flow, creating a pending User before ownership verification. It also offered a temporary registration-only verification bypass.
- Customer PIN OTP delivery already used the shared Airtel adapter and approved four-digit OTP message. Normal PIN login does not send SMS.
- `LoginPage` already separates Customer and Employee/Partner tabs. Owner/employee/partner password forms, session code and permissions were preserved.

## Registration and login changes

The existing `/register` page now contains only Mobile Number, optional Email Address, Create 4-Digit PIN and Confirm 4-Digit PIN, followed by Send OTP. Mobile requires exactly ten ASCII digits; both PINs require four ASCII digits and must match. PIN inputs are masked and separate from the SMS OTP input. Optional blank email is sent as null.

`POST /customer-registration/start` validates all registration fields before calling the shared `PinService.start` with the new `REGISTRATION` purpose. Registration PIN/email values are not persisted at this step. An enabled, active Airtel integration is required for delivery. HTTP 200 from Airtel means submission accepted; the UI says OTP submitted rather than claiming proven handset delivery. A failed/ambiguous submission is reported honestly and cannot create an account.

The existing `/auth/pin/verify` consumes the four-digit OTP and returns a short-lived, mobile-bound, purpose-bound completion authorization. No account exists yet. The UI then offers Complete Registration. The generic `/auth/pin/start` does not accept registration requests: registration must pass the full registration schema first.

`POST /customer-registration/complete` consumes that authorization and creates User, Customer, matching unlinked Lead relationships and the registration audit entry in one MongoDB transaction. Unique mobile and customer/user indexes prevent duplicates. A failed transaction rolls back the account and proof consumption. The customer record uses the neutral display label `Customer` because signup no longer requests a personal name; customers can update their profile through the existing profile screen. Existing Lead names, source, assignment and product values are preserved. No session is issued at registration completion. The UI shows success and redirects to the existing login page, retaining its secure-link return parameter.

The default customer login remains mobile + masked PIN only, using existing secure sessions and portal routing. Customer mobile validation now consistently accepts exactly ten digits without modifying stored numbers. Forgot PIN retains OTP verification followed by matching new PIN inputs, single-use authorization, PIN epoch increment and revocation of all previous sessions. Old PINs stop working. The existing separate password migration link is retained during enrollment mode so historical customers are not locked out.

The registration bypass route has been removed. The old `REGISTRATION_OTP_BYPASS` setting is retained only as inert environment compatibility; neither true nor false can bypass verified ownership. The older staff invitation/signup APIs remain for their authorized existing use and tests.

## Security and compatibility

- New registration, enrollment and reset PIN hashes use Argon2id through `argon2-cffi` 25.1. The dedicated PIN helper does not change password hashing for staff. Library API reference: [argon2-cffi PasswordHasher](https://argon2-cffi.readthedocs.io/en/stable/api.html).
- Existing bcrypt PIN hashes still verify and are replaced with Argon2id after successful PIN login. This hash-only upgrade does not reset credentials or change the PIN epoch. Actual PIN resets still increment the epoch and revoke existing authentication state.
- Existing password-based customers can select First-time verification / Create PIN, prove ownership through Airtel, and explicitly enroll a PIN. Their User/Customer IDs, data and historical relationships are retained. Password fallback remains available in enrollment mode for customers without a PIN. Once a customer explicitly enrolls, their password login is blocked by the existing customer PIN policy. No bulk credential replacement or automatic global PIN-only cutover is performed.
- Pending password accounts can use the same enrollment route. Disabled/deleted/non-customer accounts are not eligible for customer PIN enrollment/recovery.
- OTPs use the existing keyed hash at rest, expire after ten minutes and can be verified once. Completion authorization is stored hashed, expires after five minutes, and cannot be reused or used for another mobile/purpose.
- Existing limits remain: 60-second resend cooldown; five OTP sends per mobile per hour; ten PIN OTP starts per IP per ten minutes; five verification attempts per challenge plus IP limits. PIN login has IP/mobile limits and a five-attempt, fifteen-minute account lock. Reset/enrollment retains completion limits.
- PINs, OTPs and completion proofs are held only in transient browser state and are cleared on completion; they are not put in browser storage. Existing refresh-token persistence is unchanged. API validation responses omit submitted values. No live credentials, OTPs, PINs, request bodies or personal data were logged during implementation.
- Airtel credentials, API Connections, approved DLT identifiers/message content, employee/partner/owner authentication, RBAC, existing session management and company database scope are unchanged.

## Database requirements and migrations

No new customer identity collection, tenant architecture or bulk data migration was added. Existing User PIN fields, Customer optional email/profile fields, shared OTP challenge/limit collections and session collections are reused. Existing startup index initialization must run, including unique `users.mobile`, unique `customers.user_id`/customer code, challenge indexes and expiry indexes.

**Registration completion requires a transaction-capable MongoDB replica set or mongos.** There is deliberately no non-atomic standalone fallback. The checked-in Compose Mongo configuration already uses a replica set; the pre-existing local standalone server was left unchanged. Tests used a separate disposable loopback replica set on port 27028. Confirm production supports transactions before rollout. Do not convert a production MongoDB instance without its own approved infrastructure plan.

ID counters can have harmless gaps after failed/concurrent completion attempts. No existing customer documents or credentials are rewritten by deployment. Legacy hash upgrades happen only after a successful login with the correct PIN.

## Files modified

Production code:

- `backend/pyproject.toml`: Argon2 dependency.
- New `backend/app/security/pin.py`: customer PIN hashing/legacy verification.
- `backend/app/features/auth/pin_service.py`: registration purpose, shared verification and Argon2 PIN handling.
- `backend/app/features/auth/router.py`: ensure registration sends pass full detail validation.
- `backend/app/features/customer/{public_router,schemas,service}.py`: replace the old registration workflow and retire bypass.
- `backend/app/config/settings.py`: document the inert legacy bypass setting.
- `frontend/src/features/customer/{api,validation}.ts`, `pages/RegisterPage.tsx`: simplified staged registration.
- `frontend/src/features/auth/pinApi.ts`, `components/PinAuthPanel.tsx`: shared purpose typing and consistent customer mobile validation.

Tests/evidence:

- New `tests/api/test_customer_pin_registration.py`, `test_customer_pin_browser.py`, `customer_test_helpers.py` and `frontend/src/features/customer/pages/RegisterPage.test.tsx`.
- `test_pin_auth.py` covers Argon2 and legacy PIN upgrade. `test_registration_otp_bypass.py` now proves the removed bypass cannot verify mobile ownership.
- Existing customer, portal, document, workflow, assignment, bank-offer, messaging, schema, reminder and support regression setup now provisions historical password customers through the staff invitation API instead of calling the retired password self-registration contract. These changes are test setup only; those production modules were not modified.
- New `scripts/customer-pin-ui-check.mjs`; screenshots/results in `docs/screenshots/customer-pin-2026-11-18/`.

## Exact validation results

All commands below ran from the repository root unless stated otherwise. Backend tests use `DEBUG=false`. Real database tests use a random disposable database on a loopback test replica set, never the configured application/production database. Airtel HTTP requests are mocked.

```powershell
$env:DEBUG='false'
$env:AFS_PIN_TEST_MONGO_URI='mongodb://127.0.0.1:27028/?replicaSet=customerPinTest'
$env:AFS_CUSTOMER_PIN_BROWSER_CHECK='1'
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_customer_pin_registration.py tests/api/test_pin_auth.py tests/api/test_pin_mongo_integration.py tests/api/test_auth.py tests/api/test_registration_otp_bypass.py tests/api/test_customer_pin_browser.py -q -n 2 --tb=line
```

**56 passed**, 1264 existing mongomock UTC deprecation warnings, 152.30 seconds. Includes validation, optional email, actual shared mocked Airtel request construction, account absence before verification, Argon2, duplicate/single-use/mobile binding, expiry/resend, real transaction rollback/concurrent completion, Lead linkage preservation, rejection handling, normal PIN login, Forgot PIN/session invalidation, brute-force limits, staff role regressions and legacy PIN hash upgrade.

```powershell
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_customer.py tests/api/test_customer_portal_home.py tests/api/test_customer_portal_redesign.py tests/api/test_customer_documents.py tests/api/test_workflow.py -q -n 2 --tb=line
```

**106 passed**, 122.25 seconds.

```powershell
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_assignment_consistency.py tests/api/test_case_status_control.py tests/api/test_document_collection_lifecycle.py tests/api/test_insurance_policy_leads.py tests/api/test_loan_bank_offers.py tests/api/test_loan_management_redesign.py tests/api/test_loan_management_visibility.py tests/api/test_messaging.py tests/api/test_product_schema_engine.py tests/api/test_reminders.py tests/api/test_support.py tests/api/test_airtel_transport.py tests/api/test_airtel_diagnostics.py -q -n 2 --tb=line
```

**236 passed**, 302.84 seconds. Total: **398 backend checks passed**, including the browser test.

```powershell
npm --prefix frontend test -- src/features/customer/pages/RegisterPage.test.tsx src/features/auth
npm --prefix frontend run build
```

Frontend: **17 tests passed across four files**. TypeScript and Vite production build passed (439 modules, 22.04 seconds for Vite); existing large-bundle advisory remains. Targeted ESLint, Ruff, Node script syntax and `git diff --check` passed.

Targeted mypy passes for `security/pin.py`, `auth/pin_service.py`, customer `schemas.py` and `public_router.py`. Including the entire existing customer service reports one pre-existing nullable `pending.lead_id` argument in `complete_profile` (current line 528 vicinity; baseline line 558). This is outside the changed registration method; the baseline source reports the same error. It was not hidden with a cast or suppression, and no unrelated profile behavior was changed to silence it.

The browser check used the actual local React app, FastAPI API, transactional MongoDB and mocked Airtel HTTP, at **1440px desktop and 390px mobile**. Both passed four-field registration, optional email, OTP verification, success redirect, mobile/PIN login to `/portal`, Forgot PIN, old-PIN rejection, new-PIN login and preserved staff password tab. No runtime errors/page overflow. Screenshots were inspected. Mock OTPs were transferred privately between the Python fixture and browser, not returned by an API or printed in artifacts.

Initial testing identified the local standalone MongoDB limitation and obsolete password/bypass test assumptions; these were corrected by using an isolated replica-set fixture and explicit historical-account test setup. No security guard was disabled to make tests pass.

## Production deployment instructions — not executed

1. Review and approve the release through the established production process. Back up the database and confirm transaction support and current indexes first. Keep an existing owner/employee login available for operational verification. No blanket customer credential migration is required.
2. Rebuild both backend and web artifacts so the Argon2 dependency and frontend/backend registration contract change are released together. Commands corresponding to the checked-in Dockerfiles:

```powershell
docker build -f docker/backend/Dockerfile -t afs-crm-backend:customer-pin-20261118 .
docker build -f docker/nginx/Dockerfile -t afs-crm-web:customer-pin-20261118 .
```

3. Deploy those reviewed artifacts through the actual production release mechanism with the existing secure environment and encryption/JWT settings. This repository's Compose file selects development environments/frontend; it is not a verified production rollout command. Host/orchestrator/registry/restart details must come from the established production runbook, not invented here.
4. Confirm startup initializes the existing indexes. Confirm the current Airtel integration remains enabled/active with its verified configuration. Do not replace credentials or reconfigure DLT values. The old registration bypass setting is ignored; remove it from operator documentation when convenient.
5. Perform the separately authorized live customer test below. Do not enable global PIN-only cutover until every applicable existing customer has explicitly enrolled, using the existing owner-controlled gate.

Example read-only transaction-support preflight inside the approved backend environment (operator-run only; not executed against production here):

```python
import asyncio
from app.config.database import close_client, get_database

async def preflight():
    try:
        hello = await get_database().client.admin.command("hello")
        print({"transaction_topology": bool(hello.get("setName") or hello.get("msg") == "isdbgrid")})
    finally:
        await close_client()

asyncio.run(preflight())
```

A topology check is a prerequisite, not proof of write permissions or a substitute for deployment review. If standalone, do not roll out this registration change until transaction support is approved/provided.

## Manual customer acceptance test

Use only an owner-authorized test handset; this sends real SMS and was not performed here.

1. Open `/register` on desktop and mobile. Confirm only the four requested inputs. Check invalid mobile/PIN/mismatch/invalid email errors and that blank email is accepted.
2. Enter a previously unregistered ten-digit mobile and matching PINs. Send OTP once. Confirm no account exists yet and resend has a cooldown. Receive the approved AFS message on that handset.
3. Enter the SMS OTP, verify, then Complete Registration. Confirm success redirects to Customer Login. Check the verified User and linked Customer exist; email is optional, PIN is an Argon2id hash, no password has been assigned, and unrelated records are unchanged. Do not copy hashes, OTPs or PINs into reports.
4. Log in using mobile and PIN only. Confirm the portal opens and no SMS is requested. Log out and check an incorrect PIN fails.
5. Use Forgot PIN for that mobile. Receive and verify a new OTP, choose and confirm a different PIN, then return to login. Confirm old PIN and old sessions/refresh tokens fail while the new PIN works.
6. Try duplicate registration and reused/expired OTPs; confirm no duplicate or incomplete account is created. Confirm employee, partner and owner password login still work.
7. For a historical password customer, test the explicit First-time verification / Create PIN enrollment without modifying their profile/history. Confirm only that customer's credential mode changes after successful enrollment. Keep global cutover unchanged.

Remaining verification: production transaction capability, rollout, and a real customer OTP acceptance test remain operator/owner actions. Live SMS was not sent and production functionality is not claimed from mocks. The pre-existing customer-service mypy issue and bundle/deprecation warnings above remain documented.
