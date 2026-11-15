# Airtel VoiceBOT onboarding and release gates

Current release decision: **NO-GO for live calls**. Configuration/offline contracts
are available; no activation API has been added. No calls, provider registration,
production deployment or model installation occurred.

## Provider contract to obtain securely

- App ID/API key and voice account entitlement, approved test numbers/caller ID,
  call-flow ID, quotas and callback delivery policy. Enter secrets only through the
  Owner-only CRM form, not chat, source, environment files or logs.
- Confirm C2C origin for the documented relative path and complete response/call-ID
  contract. Confirm whether C2C topology actually invokes the VoiceBOT; do not assume
  a two-party bridge is automatically a customer-to-AI call.
- Resolve callback field casing, stable event/call identifiers and ordering/retry
  semantics. The guide's `Removed` example and listed event names differ.
- Agree WSS/callback authentication and provider IP ranges. A guide's optional
  Bearer example does not establish an account agreement. Do not reuse REST HMAC
  as a guessed inbound signature scheme or place secrets in callback URLs.
- Confirm CDR required fields, units, correlation, authenticity and finality. Establish
  SFTP account/directory/file layout, schedule, encryption/host-key validation,
  duplicate-file handling and reconciliation. High-volume delivery differs from
  real-time calls.
- Confirm recording token placement/digest, binary format, availability/expiry,
  retention, permitted downloader and safe import policy. Never follow a recording
  URL from an untrusted callback with provider credentials.
- Agree human-first10s routing, fallback when CRM is down, transfer confirmation
  and persistent customer-leg bridge/return-to-AI. Obtain a supplementary contract
  if needed; no such return command exists in the supplied guide.

## Infrastructure and runtime gates

- Measure the actual staging host and existing workload; approve compatible local
  LLM/STT/TTS versions, licenses, model files and language/voice coverage. Offline
  Python advisory audit preference remains in force.
- Implement/review authenticated WSS hosting, TLS/proxy/IP handling, trusted session
  reservations, distributed fenced admission, bounded buffers, media conversion and
  pacing, interruption/revocation, crash cleanup and emergency controls.
- Implement authenticated idempotent correlated webhook/CDR processing. Reject or
  quarantine unbound data; never guess customer identity from caller number.
- Reuse CRM RBAC/object scopes, consent/DNC, approved knowledge/financial response
  policy, encrypted private recordings and canonical callback Tasks. Confirm legal
  calling/recording/AI-disclosure and business verification policies through the
  existing approval process; none is supplied by a telephony guide.

## Acceptance and explicit activation

- Verify credentials using an account-confirmed safe test; current CRM local
  validation is **not** provider authentication or reachability verification.
- Execute real inbound/outbound audio, interruptions, fallback, takeover/return,
  recording/CDR/SFTP, duplicate/reordered callbacks, failure/recovery and revocation
  tests against approved endpoints only.
- Complete progressive real1/10/50/100/250/500 conversation capacity acceptance with
  recorded metrics, not just open sockets or fake services. Obtain actual quotas.
- Run CRM regressions and stage additive data/index changes with backup/rollback.
  Keep SMS/native/Smartflo behavior intact; use isolated staging records/credentials.
- Review the measured evidence and rollback plan, obtain explicit user release
  approval, then implement/enable a bounded activation path. Present blocked routes
  to the provider only after their security/runtime gates pass.

Nothing on this checklist is inferred complete from a tab, configured secret, local
test or generated URL. Outstanding gates remain outstanding until evidence exists.
