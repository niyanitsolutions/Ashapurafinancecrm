# Self-hosted voice staging contract — 17 October 2026

Status: **BLOCKED — NOT PRODUCTION READY**. This is a candidate design and acceptance
contract, not an installed PBX or an approved business verification policy.

The user requires self-hosted telephony and local/user-controlled AI, recognition,
synthesis and orchestration. Twilio, Exotel and Smartflo are not selected for this
work. Preserve existing disabled compatibility code and tests.

## Verified repository and workstation facts

- `native_adapter.AsteriskReadOnlyAdapter` only performs authenticated ARI read
  probes. It does not place, answer, bridge, transfer or terminate calls.
- `deployment/docker-compose.yml` supplies CRM, Mongo, Redis and workers; it has
  no PBX, SIP trunk, model server or speech-model installation.
- `scripts/voice-server-inspect.sh` can inventory an actual Linux host without
  reading secrets or changing services. Its presence is not evidence of execution.
- Existing operations documentation records user-supplied paths
  `~/Ashapurafinancecrm`, `~/afscrm-venv` and unit names `afs-crm-backend` /
  `afs-crm-arq-worker`; these are not independently verified host state.
- Local `docker info` / `docker image ls` failed: daemon pipe unavailable, with
  Docker configuration access denied. No container or database was started.
- No approved remote connection or target-host inventory has been supplied during
  this implementation. Actual PBX presence/version, hardware and connectivity are
  unknown. Do not reuse hypothetical infrastructure as verified infrastructure.

## Preferred candidate, subject to inventory

Evaluate Asterisk **22 LTS**, with a reviewed maintained patch at least **22.8.0**
for the proposed JSON media-control contract. Pin the exact tested package/image
digest in a future staging release; the lower bound is not a recommendation to
install an old patch. Existing compatible infrastructure should be reused after
inventory and contract tests.

Official documentation identifies 22 as LTS. Its WebSocket channel can exchange
binary media and control messages over TLS, handles framing for supported codecs,
and offers flow control and queued-media flushing. JSON controls and marks require
the documented version capabilities. PBX queue/mark events establish PBX processing,
not proof that a customer heard audio. Sources:
[versions](https://docs.asterisk.org/About-the-Project/Asterisk-Versions/),
[WebSocket protocol](https://docs.asterisk.org/Configuration/Channel-Drivers/WebSocket/).

Candidate components: PJSIP, ARI/Stasis, mixing bridge, `chan_websocket`, required
PCM codec/translation modules and SRTP. Probe actual modules/version before deciding
whether this contract is compatible; do not assume the read-only ARI account can
control channels. Keep probe and future restricted control credentials separate.

## Isolated staging setup and network contract

1. Inventory an operator-approved Linux staging host using the reviewed script.
   Record OS, package/module versions, CPU, RAM, disk, GPU, workload headroom,
   storage encryption, clock synchronization and service identities.
2. Use isolated Mongo/Redis, private audio storage, dedicated credentials and
   test-only CRM records. Block routes to production services and customer numbers.
3. First use two user-controlled SIP endpoints on a private network, with no
   registered telephone trunk and no public-number dialplan. This permits eventual
   internal call/media acceptance without contacting a customer.
4. Keep ARI/HTTP/WebSocket listeners private. Permit control/media traffic only
   between the PBX and designated orchestration service, with trusted certificates,
   authenticated sessions, origin restrictions and bounded connections.
5. Permit SIP only from the approved test endpoints. Select an explicit bounded
   UDP RTP range in the actual `rtp.conf`; allow only the associated endpoint/media
   addresses in the firewall. Do not assume default port ranges or open all UDP.
6. Test TLS signaling and SRTP where both peers support them. Certificates, NAT,
   advertised media addresses and symmetric media behavior need actual peer tests.
   TLS signaling alone does not encrypt RTP. Keep all unsupported combinations
   disabled. See [Asterisk network security](https://docs.asterisk.org/Deployment/Important-Security-Considerations/Network-Security/).
7. Restrict model/speech processes to local or user-controlled hosts. Install no
   model automatically. Pin approved executable/package/model/config hashes and
   licenses; measure utterance and streaming latency separately.
8. Future PSTN connectivity requires an authorized SIP trunk, telephone gateway or
   equivalent licensed network interconnect, approved number assignment and inbound/
   outbound permissions. This is an external dependency even with a self-hosted PBX.
   No supplier, credential, price, capacity or working trunk is assumed here.

## Required runtime implementation before a staging call

The following are still absent and must be implemented, not replaced by health
probes or this document: durable native call sessions and action receipts; ARI
event correlation/reconnect/reconciliation; Owner-first routing and verified human
destinations; authenticated per-call media sessions; streaming STT/TTS adapters;
exclusive audio ownership; admission control; cancellation and stop fencing; actual
callback dispatch and unknown-outcome reconciliation; release manifests and pins.

Reuse canonical Tasks and existing scopes. A provider timeout after acceptance
must enter unknown outcome and reconcile by stable channel/operation identity;
never blindly redial. Enforce stop/consent/permission immediately before each
command and media delivery. Clear queued audio on barge-in/takeover and reconcile
already accepted commands. Do not infer transfer success from request acceptance.

## Caller verification and disclosure proposal

Inspection: `auth.dependencies.get_current_active_user` authenticates an active CRM
user. Existing OTP flows cover signup/password recovery; those tickets are not
telephone identity factors. Existing SMS delivery may use an external service;
development OTP echo/logging must never serve as a caller-verification factor.
Customer records and phone matching provide linkage only. No existing business
policy approves a voice verification factor or a protected-field allowlist.

Proposed local-first factor for business review: a fresh, single-use confirmation
inside the authenticated customer portal, bound to the server-created call, exact
customer, purpose, policy version, expiry and challenge nonce. This needs independent
customer authentication and protection against session theft and relaying. It is
not approved or enabled by this proposal. An SMS OTP alternative would add an
external messaging dependency and needs separate approval; do not reuse signup or
password-reset tickets, caller ID, security trivia, staff login or an LLM assertion.

Before enabling any protected tool, configure and test: approved factors and
disclosure fields; purpose/consent; customer-to-call binding; short validity and
single use; bounded failed attempts and lockout; explicit consequential-action
confirmation; current record/role scope; revoke/stop races; minimal redacted audit
receipts; correction/deletion/retention rules. Every missing setting denies access.
Current `proposal_policy` continues returning `customer_verified=false` and
`execution_allowed=false`; no financial tool has been enabled.

## Evidence needed to close the block

Record exact host/PBX build/modules and release hashes, then run internal inbound/
outbound audio, Owner-first ringing, silence/loss, interruption, stop at each stage,
busy/no-answer transfer, worker/process death, reconnect, duplicate/out-of-order
events, timeout-after-acceptance, cancellation/DNC races and actual DB index races.
Measure multilingual quality and capacity using approved synthetic/test material.
Rehearse restore/rollback while retaining policy and managed-Task guards.

Only after those tests and approved verification/disclosure rules pass may separately
authorized telephone-network staging tests be scheduled. Production activation
requires a further explicit human approval. No call, installation, restart, firewall
change, trunk registration or production migration was performed here.
