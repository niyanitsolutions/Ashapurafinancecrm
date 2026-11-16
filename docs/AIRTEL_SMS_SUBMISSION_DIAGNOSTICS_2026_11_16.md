# Airtel SMS submission-failure investigation

16 November 2026. Local diagnostic fix only. No deployment, production database
read/write, credential-file access, or real SMS was performed.

## What is confirmed, and what is not

Confirmed code defect: communication/airtel_iq.request discarded Airtel's response
body by returning (status_code, None). submit stored the HTTP code in sms_submissions,
but the integration test-history model/response/UI did not carry it. Every non-200
or HTTP transport exception produced the same generic message. The CRM's 209 ms is
test orchestration time, not evidence of a particular rejection or timeout reason.

The inspected adapter already accepts HTTP 200 regardless of JSON body. There is no
JSON-success-path dependency here. Its Authorization and seven JSON field mappings
match the supplied account contract; no configuration values have been changed.
These conclusions concern inspected source and mocked requests, not a read of the
production Customer ID or credentials.

The actual production cause is UNDETERMINED pending the permitted metadata query.
No production MongoDB connector or established read-only connection was available
in this session. The Owner explicitly prohibited credential access, so credential
files, stored mobiles, OTPs and raw production bodies were not opened to establish
one. An unrelated connected Sites/D1 database tool is not access to this CRM MongoDB.
The previously discarded response body cannot be recovered from old CRM history.
Do not attribute the failure to Authorization, Customer ID, DLT or Airtel balance
without the actual status/provider evidence. The fix below corrects observability;
it is not proof that the provider rejection itself has been resolved.

## Exact read-only production query

This application uses MongoDB, so SQL is not applicable. In the established read-only
production mongosh session, with the CRM database already selected, execute:

```javascript
db.getCollection("sms_submissions")
  .find(
    { provider: "airtel_iq", status: { $in: ["rejected", "unknown"] } },
    { _id: 0, http_status: 1, status: 1, created_at: 1 }
  )
  .sort({ created_at: -1, _id: -1 })
  .limit(5)
  .maxTimeMS(5000)
  .toArray()
```

The query returns ONLY http_status, status and created_at; it does not retrieve
credentials, OTPs, destination numbers, payloads or response bodies, and changes
nothing. Its time limit bounds the operation. No connection URI or credential is
embedded. The caller should correlate timestamps with the failed CRM attempt;
latest records alone do not establish that every row belongs to that attempt.

Interpretation must remain evidence based:

- HTTP 401/403: inspect account authorization/access in Airtel's portal. Do not guess
  a different scheme or replace working values.
- HTTP 400/422: inspect actual provider validation details/portal before changing
  a payload field; HTTP status alone does not identify which field was rejected.
- HTTP 429: inspect throttling/quota; no automatic resend.
- HTTP 5xx: provider/gateway failure is possible; this does not prove bad credentials.
- Null/absent HTTP status with unknown: the older adapter did not distinguish
  timeout, connection and protocol exceptions. No definite rejection reason follows.
- HTTP 200 with a failed state would conflict with the inspected acceptance rule;
  inspect the deployed version and processing evidence rather than altering config.

No actual production result was provided during this implementation.

## Exact diagnostic fix

The transport retains a bounded in-memory response sample and a JSON-content-type
indicator. submit projects it into safe diagnostics before any persistence or API
return. The projection is not an Airtel error-schema parser: no field indicates
success; only actual HTTP 200 does. Empty/plain-text/malformed JSON and deeply nested
JSON cannot turn HTTP 200 into a failed submission.

Persisted and owner-visible fields:
- http_status: actual HTTP integer, or null when no response was obtained.
- outcome_type: http_200, http_non_200, timeout, connection_error,
  unexpected_response or transport_error.
- response_format: json, text, empty, malformed_json, truncated, unreadable or
  unavailable.
- response_excerpt: conservative, sanitized public projection, bounded to 2,000 chars.

Non-200 remains rejected. Transport errors remain unknown. Timeout, connection and
protocol/decoding failures are distinct without storing exception text. Errors show
the HTTP status and safe next steps; unknown outcomes explicitly require checking
Airtel IQ portal before another attempt. The original no-retry behavior and durable
provider/reference deduplication remain unchanged, including concurrent/repeated
calls and configuration edits.

IntegrationTestLog carries the optional diagnostics to its existing authorized
history response. The Airtel UI displays HTTP code/no HTTP response, category,
format and an expandable sanitized reply. Existing records have no diagnostics and
remain readable. Other providers' response logic and UI stay unchanged.

## Sanitization and security

Raw provider replies can echo the complete SMS, Customer ID, Authorization header,
recipient or personal data. A blacklist alone cannot safely retain arbitrary prose.
The sanitizer removes known configured/private values, suppresses request/header/
identity subtrees, all numbers, unknown keys and unknown words, and keeps only a
small public diagnostic vocabulary and harmless JSON structure. This intentionally
redacts unknown provider codes/prose rather than risking secret or personal-data
exposure. It preserves useful phrases such as invalid customer id or authentication
failed when those words actually occur, without interpreting an Airtel-specific
schema. Unknown content can be inspected only in the provider's authorized portal.

The in-memory sample is capped at 8 KiB plus a truncation indicator. HTTPX still
buffers its response as before; this is a diagnostic retention cap, not a new HTTP
stream-size guarantee. Nested structures and output lengths are bounded. Raw body
is excluded from the response wrapper's repr; no raw body or exception text is
logged, persisted or returned. The full request, generated OTP and credentials are
never diagnostic output. Existing encrypted settings, masking, owner permissions,
OTP protections and no-SMS validation are unchanged. No secret/config values,
endpoint, sender, DLT identifier, destination format or message wording were edited.

## Mapping verified without changing values

Existing POST construction remains:

| Wire field | Existing source |
| --- | --- |
| Authorization | saved encrypted authorization_value, verbatim; no added scheme |
| customerId | saved customer_id |
| entityId | saved verified entity_id |
| destinationAddress | existing single-recipient template, validated ten-digit number |
| messageType | saved message_type |
| sourceAddress | saved sender_id |
| dltTemplateId | saved dlt_template_id |
| message | approved message, actual generated OTP substituted once |

The fixed confirmed endpoint, POST method, accept/content-type headers, no redirects
and configured timeouts remain unchanged. Automated exact-mapping tests use synthetic
Customer IDs and OTPs, never production credentials or a real recipient.

## Files changed

- backend/app/features/communication/airtel_iq.py: bounded capture, outcome categories,
  safe persistence/return, HTTP-200 acceptance and no-retry deduplication retained.
- backend/app/features/communication/airtel_diagnostics.py: new conservative projection
  and safe standard-HTTP guidance, with no provider schema assumptions.
- backend/app/features/integrations/airtel_test.py: copy sanitized diagnostics to history.
- backend/app/features/integrations/models.py and schemas.py: optional diagnostic fields.
- backend/app/features/integrations/mappers.py: safe existing history API mapping.
- frontend/src/features/integrations/api.ts and pages/IntegrationDetailsPage.tsx:
  typed diagnostics and history display.
- tests/api/test_airtel_diagnostics.py: new transport/privacy regression tests.
- tests/api/test_airtel_transport.py and test_airtel_live_workflow.py: updated response
  expectations and actual history propagation coverage.
- frontend/src/features/integrations/AirtelDetails.test.tsx: diagnostic history coverage.
- this report.

## Verification

- Combined backend run: 122 passed, including transport/diagnostics, configuration,
  test OTP workflow, integration, customer PIN and ordinary OTP delivery suites.
- Frontend integration suites: 13 passed, including HTTP/category/redacted history.
- TypeScript production build passed; existing large-bundle advisory only.
- Targeted frontend ESLint passed with no errors or warnings.
- Strict mypy for adapter/diagnostics/test orchestration passed after the optional
  HTTP-code annotation correction. New Python source/test files formatted; Ruff checks
  passed. Final focused sanitizer run is recorded below.
- Mock responses cover HTTP 200 empty, plain, malformed/declared JSON and deeply
  nested JSON; 401/403/429/500/302; invalid status; timeouts; connection/protocol errors;
  echoed credentials/OTP/personal data; bounded oversized replies; duplicate suppression.

These are automated mocked results, not actual Airtel submissions or handset receipt.
No live failure status/body has been captured in this session.

## Deployment and next evidence

No production deployment or SMS is authorized by this task. After explicit Owner
approval, deploy matched backend/frontend artifacts through the existing release
process. The optional diagnostic object needs no new dependency, index, collection
or data migration. No historical raw body can be backfilled. Until that deployment,
production history will keep its old generic display.

First obtain the read-only metadata above; it requires no SMS. If further provider
body evidence is needed after deployment, a new explicit Owner-authorized test may
capture sanitized diagnostics. Do not send it automatically, and do not repeat an
ambiguous attempt without checking Airtel portal. Keep working configuration values
unchanged unless the resulting evidence justifies a specific correction.


Final focused adapter/diagnostic rerun: 43 passed, including excessive JSON nesting
without overriding HTTP 200. Final strict mypy passed for all three affected runtime
modules. Whitespace checks passed and generated TypeScript build metadata was restored.
No commit, push, deployment, production read/write or real SMS was performed. The
Owner's follow-up authorized only a three-field read of failed records; since no
read-only production access was available, the exact safe mongosh query was provided.
