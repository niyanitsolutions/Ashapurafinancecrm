# Airtel IQ field mapping audit and corrections

Source: the account cURL supplied in the task, inspected 13 November 2026. No
additional authentication or response specification was assumed. The pre-change
audit and proposed files/corrections were presented in the conversation before edits.

## Findings before correction

All seven outgoing JSON keys were present and correctly named. Authorization was
already a separate HTTP header. Customer ID, sender, DLT IDs and message type mapped
correctly. The endpoint used POST with JSON headers through the backend only.
There were no missing cURL fields and no extra outgoing JSON fields.

The form nevertheless required Username and Password, although neither was consumed
by the adapter or established by the supplied cURL. These were unnecessary inputs,
not an implemented Basic authentication mechanism. The backend additionally accepted
an unused `message_id_field`. Existing saved values remain encrypted and accepted
for compatibility; none of these three settings is transmitted or used for auth.

Destination validation previously accepted a single-element numeric or object array;
the task's expected request specifies a string array. The existing response path,
success value and confirmation flag were CRM safeguards, not Airtel request fields.
No defaults for these response rules existed. HTTP success alone was insufficient:
the configured success value had to match with its exact JSON type.

OTP replacement already rendered the correct approved wording. Its internal
`##numeric##` notation differed from the latest brief's `{#numeric#}` notation.
The adapter lacked its own four-digit input guard. The ordinary Test Connection
action sent no SMS but its label could imply authentication testing. The edit form
rendered contract confirmation as free text rather than a confirmation selector.

## Applied corrections

- Removed unused username/password form fields. Saved values remain supported and
  fully masked; no existing config is deleted or migrated.
- Required exactly one string destination element containing the mobile placeholder.
  The configured mobile formatting remains explicit; no country prefix is assumed.
- Added adapter-level ASCII OTP/mobile input validation before network/persistence.
  Applied the existing config normalizer's returned defaults consistently.
- Aligned the internal approved-template placeholder with `{#numeric#}`. The rendered
  wording, sender and DLT IDs remain unchanged. Added an exact literal message test.
- Renamed Airtel-only local checks to **Validate Configuration (no SMS)**. They validate
  settings without declaring authentication or delivery successful. The explicit
  administrator-confirmed SMS test remains the only submission test.
- Added configuration guidance and corrected the Airtel edit confirmation selector.
  No request/response rule, messageType or auth scheme was invented.

Changes are confined to `frontend/src/features/integrations/providerFields.ts`,
integration list/details pages and Airtel configuration tests;
`backend/app/features/integrations/{airtel_iq,testers}.py`;
`backend/app/features/communication/airtel_iq.py`; Airtel transport tests and docs.
Customer-only OTP/PIN policy, account eligibility, expiry, attempts, resend, audit,
session issuance/revocation, RBAC and the existing single-company database scope
were preserved. Credentials continue using existing encrypted integration storage
and full Airtel masking. The browser never contacts Airtel directly.

## Final field mapping

| Frontend field / value source | Backend setting | Airtel destination / type |
|---|---|---|
| Provider | `provider=airtel_iq` | CRM adapter selection only |
| Configuration name | `name` | CRM metadata only |
| API Endpoint | `api_url` | Fixed approved POST URL; never a JSON field |
| Customer ID | `customer_id` | `customerId`: string |
| Authorization header value | `authorization_value` | `Authorization` header, verbatim Airtel-confirmed value |
| Sender ID (default ASHFNS) | `sender_id` | `sourceAddress`: string |
| DLT Template ID (default 1077151820081508033) | `dlt_template_id` | `dltTemplateId`: string |
| DLT Entity ID (default 1001474305342749488) | `entity_id` | `entityId`: string |
| Confirmed destinationAddress JSON array | `destination_template` | `destinationAddress`: one-element string array, rendered from registered mobile |
| Generated OTP (not a form field) | approved message constant + runtime OTP | `message`: string; resolved approved text |
| Message Type | `message_type` | `messageType`: Airtel-confirmed string |
| Confirmed response success field path | `success_field` | CRM response parser only; not transmitted |
| Confirmed success value | `success_value` | CRM exact typed response match only; not transmitted |
| Account-specific API contract confirmed | `contract_confirmed` | CRM sending/activation guard only |
| Enabled / Active | `is_enabled` / `is_active` | CRM provider selection only |
| Validate Configuration (no SMS) | existing test endpoint | Local validation only; no Airtel call |
| Explicit test mobile / send confirmation | admin test request | Runtime recipient and authorization for one test; not saved credentials |
| Username / Password | legacy `username` / `password` | Removed from form; stored legacy values unused |
| No form field | legacy `message_id_field` | Accepted for compatibility, unused |

`accept: application/json` and `content-type: application/json` are fixed transport
headers. No extra Airtel JSON properties are sent. Endpoint and approved DLT values
retain the existing approved defaults and validation restrictions.

The cURL's `Authorization: string` remains a placeholder, not an actual credential
scheme. Its `destinationAddress: "array"` is a schema hint, not the literal payload.
The task's expected string array is now enforced, but the required mobile format,
allowed messageType, authorization scheme and success schema still need account
confirmation. Sending fails closed until these explicit rules are present and
confirmed. A 2xx response matching those rules establishes submission acceptance,
not handset delivery; actual receipt still needs an authorized manual test.

No real SMS was sent and no live delivery or production readiness is claimed.

## Verification

85 backend regression tests passed across Airtel configuration/transport, customer
PIN, integration and communication tests. After the final adapter normalization
change, all 23 transport tests passed again. All 18 relevant frontend tests passed
across the focused runs. Type checking, strict mypy on the adapter/configuration,
Ruff and production build passed. ESLint reported zero errors and one existing
Fast Refresh export warning in IntegrationListPage. Vite retained its existing
large-bundle warning. All SMS transport tests used mocks; no production data,
credentials, cutover or deployment was used.
