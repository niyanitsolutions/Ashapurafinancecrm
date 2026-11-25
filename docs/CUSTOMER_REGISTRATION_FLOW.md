# Customer registration flow

## Revised three-field account signup

The current Customer registration form contains only mobile number, four-digit PIN and PIN confirmation. Full name, email and the checkbox are absent. The same authenticated Customer login, recovery, session and OTP services remain in use; Employee, Partner and Owner sign-in is unchanged.

Start validates the three fields and uses the existing REGISTRATION challenge, Airtel adapter, cooldown, expiry and attempt/rate limits. Account existence is disclosed only after mobile ownership verification. Existing accounts receive no registration authorization. A valid, unused authorization is required to complete account creation; the PIN must differ from the OTP and is hashed by the existing Argon2 helper.

## Account and identity are separate

The existing Customer model requires a real full name. Registration therefore creates a valid verified Customer-role **User account**, consumes its proof and appends its security audit atomically. It does not create a Customer profile, allocate a Customer ID, invent a name/email, use a mobile as a name, or create an invalid placeholder identity. The existing portal already redirects accounts without a Customer profile to `/portal/profile/setup`; that existing flow collects real profile details after login and creates the valid Customer record there.

A private `users.registration_method = mobile_pin` marker distinguishes this signup path. Profile creation for that path does not bulk-claim historical Leads by mobile. Explicit secure-link/pending-application relationships continue through their existing ownership checks. Known historical Customer identities still require reviewed ownership before signup; they are never attached by mobile alone. No historical IDs or records are rewritten.

## Consent inspection

The previous batch introduced the checkbox, a required request boolean and an audit claim. No separate configurable consent policy, applicable legal document or independently enforced registration-consent requirement was found in the repository. The current user request removes that feature requirement. The revised endpoint does not fabricate consent or record `terms_accepted: true`; its audit records account signup and pending profile state. Owner setup and other portals' consent UI are unchanged. Any policy maintained outside the repository must be reconciled by the Owner before deployment; this implementation does not claim legal approval or silently assert acceptance.

## Compatibility and operation

The request contract now accepts only the three signup fields (plus authorization at completion). The only repository frontend consumer and its tests are updated. Deploy compatible frontend/backend versions together and refresh old registration pages. Existing accounts, Customer records, hashes and sessions remain valid. Transaction conflicts return a safe conflict; no automatic OTP/SMS retry is added.

All automated OTP delivery is mocked, with disposable loopback databases. No production deployment, production account creation, historical merge or real SMS is performed.
