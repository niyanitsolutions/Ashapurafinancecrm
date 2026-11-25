# Customer registration flow

## Safe login discovery

Customer mobile/PIN login retains uniform invalid-credential errors and the existing lock/session behavior. A failed credential attempt offers a neutral Create New Account popup without stating whether the number exists. No OTP is sent merely because login failed. The registration link pre-fills the entered mobile and retains a safe return destination.

The existing registration start endpoint validates full name, mobile, optional email, matching four-digit PIN and explicit terms consent. It uses the existing REGISTRATION OTP challenge, Airtel provider, resend cooldown, IP/mobile/account limits, expiry, attempt counters and single-use verification. Start returns the same shape for existing and unregistered accounts and does not create a User or Customer. There is no new SMS provider or DLT content.

Only after successful OTP ownership verification can the UI state ?Customer Account Not Found?. It offers explicit account creation. If the verified number already belongs to any account, verification consumes the challenge and returns the login action without registration authorization. This includes Employee/Partner accounts: public signup can never convert them to Customers. Ordinary PIN completion rejects REGISTRATION proofs, preventing a signup proof from resetting an existing PIN.

## Creation and existing identities

`POST /customer-registration/complete` requires a live single-use REGISTRATION authorization tied to the mobile, full name, optional email, matching PIN and terms consent. The PIN must differ from the OTP. It stores an Argon2 PIN hash through the existing helper, never a password or plaintext PIN. User, Customer, proof consumption and registration audit commit transactionally; no standalone fallback exists. Existing unique User mobile and Customer user/code indexes guard races. The audit records consent and its version.

The Customer profile starts with the supplied full name. Public signup no longer bulk-claims unlinked historical Leads by mobile. A pre-existing Customer mobile, including accepted Indian formatting, blocks creation after verified ownership and requests staff review. It never silently attaches an account or creates a second Customer alongside a known historical profile. Existing authoritative secure-link/profile ownership workflows remain available for reviewed identities; there is no new public merge API.

After commit the existing PIN login creates a session. If login cannot complete, the page shows registration success and asks for explicit login. Return destinations remain restricted to local paths. Registration details, OTP and proof are held only in component memory, never browser storage. Incorrect, expired, exhausted or reused codes cannot create an account. Existing customer recovery, employee/partner password login and Owner authentication are preserved.

## Operational boundaries

All OTP tests mock Airtel HTTP. No real SMS or production account is created. The existing Airtel activation/configuration requirements remain in force. Deploy locally reviewed backend and frontend together only after Owner approval, with replica-set transactions enabled. Existing encrypted credentials, DLT mappings, approved message content, PIN hashes and sessions are not migrated or reset by this batch.
