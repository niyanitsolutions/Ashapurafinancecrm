# Human / AI takeover — supported contracts and blocked topology

15 November 2026. Existing CRM mock transfers remain simulations. The new Airtel
codec can encode documented fallback requests offline; **real same-call takeover
and return-to-AI are not implemented or verified**.

The supplied guide pp19–20 documents outbound `clear`, playback marks and
`terminate` reasons: 1 hangup, 2 agent fallback, 3 particular DID with E.164 number.
It does not document a human-to-AI return command or the persistent bridge needed
to retain the same customer leg. No invented REST transfer endpoint is added.

## Required future live sequence

1. Validate employee RBAC and scoped call ownership, current consent, release and
   emergency state. A model proposal cannot authorize a transfer.
2. CAS the trusted session to transfer-pending. Reuse existing generation fencing
   to cancel STT/model/TTS work and prevent stale audio after the decision.
3. Send clear and classify flushed mark echoes as cleared. Stop AI output before
   requesting the provider's agreed fallback. Request submission is not completion.
4. Apply the agreed provider confirmation and timeout/reconciliation contract to
   commit human ownership. Stream stop alone cannot prove the human answered or
   the customer call ended. On ambiguous outcome, keep ownership unresolved and
   suppress AI output; do not risk dual speakers.
5. Return to AI only with an account-confirmed persistent bridge and verified media
   reattachment contract. Establish a newly authorized media generation, preserve
   only permitted conversation context, then confirm AI ownership. Without that
   topology the UI must report unsupported, not simulate success.

Proposed ownership states for the future live controller: `AI_ACTIVE`,
`AI_TO_HUMAN_PENDING`, `HUMAN_ACTIVE`, `HUMAN_TO_AI_PENDING`, `OWNERSHIP_UNRESOLVED`,
`CALL_ENDED`. These are a design, **not shipped live state transitions**. Existing
lowercase mock states are preserved; no fake provider ownership records are created.

Human-first routing and a ten-second timeout must be agreed and configured in the
provider call flow. A React timer cannot supply provider routing, particularly
during a CRM/server outage. Provider-side failure routing must work when the CRM
is unreachable; the guide says failed WSS handshakes are not retried.

Acceptance requires real provider tests for answer/reject/no-answer, concurrent
takeover requests, stale TTS after interruption, human busy/failure, outage before
and after transfer, customer hangup on either leg, duplicate/reordered callbacks,
permission/consent revocation and return-to-AI on the **same customer call**. None
was executed here. Local clear/mark/hold/termination and existing dynamic-core
generation-fencing tests do not replace those tests.
