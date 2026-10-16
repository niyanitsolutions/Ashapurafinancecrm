# Voice platform operations — 16 October 2026

This extends [the prior handover](SELF_HOSTED_VOICE_OPERATIONS.md). No production
service, model, PBX resource, routing or telephone call was changed. Read the
[continuation report](VOICE_PLATFORM_REPORT_2026_10_16.md) for exact acceptance
limits. Existing deployment service names and sidebar are preserved.

## Installation prerequisites

Actual server OS, CPU, RAM, disk, GPU/VRAM and service inventory are still unknown.
Use the existing approved server session and
[read-only inventory](../scripts/voice-server-inspect.sh) first. No usable SSH
profile exists here; the deployment PDFs contain placeholder access commands.
Do not infer hardware from the PDF's example instance. Obtain the existing
connection name through the normal secure administrative channel, never a password
or private key in chat. Do not deploy or select models before capacity and licenses
are reviewed. Ten concurrent real calls remains a staging target, not capacity.

This batch supports optional **Linux CPU verification** using operator-installed
whisper.cpp and Piper. It does not install either engine. The subprocess profile
is for bounded local tests/per-utterance execution, not a warmed streaming speech
service; model reload on each request can be too slow for live conversation.
English Piper verification is supported initially; other voices/languages require
an approved representative sample and further acceptance. No language quality or
financial pronunciation is automatically approved by a reference test.

Use a separately protected, unprivileged speech execution environment. Review
model/voice licenses separately from runtime licenses; Piper runtime is GPL-3.0.
Pin the actual whisper.cpp build, Python environment, Piper package/wheels and
voice assets through the existing approved release process. The configured Python
executable hash does **not** verify the Piper package contents. Record the runtime
version and independent package lock/image digest in the release evidence.
No arbitrary shell, pip command or download URL can be supplied through CRM.

Primary contracts inspected on this date:
[whisper.cpp CLI](https://github.com/ggml-org/whisper.cpp/tree/master/examples/cli),
[Piper CLI](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/CLI.md), and
[Asterisk media driver](https://docs.asterisk.org/Configuration/Channel-Drivers/WebSocket/).
The deployed Asterisk version/modules are unverified. Do not deploy a WebSocket
media route merely because newer Asterisk documentation describes one.

## Configure approved local speech assets

After explicit infrastructure/model approval, an operator installs the reviewed
engine build and licensed model files outside the application source tree. Supply
a synthetic reference WAV plus its approved expected words for STT; never use a
customer recording as the default health fixture. No large model is downloaded at
application or worker startup. Installation is an operator deployment operation,
not a UI button that changes an installed flag.

Set `VOICE_SPEECH_ROOT` to the absolute, operator-controlled model directory.
Assets are relative to this root; symlinks resolving outside it are rejected.
Protect binaries, models and manifests against writes by the CRM/worker account.
Set `VOICE_SPEECH_PROFILES` to a JSON object mapping short stable profile IDs to
the following **operator-supplied** fields:

| Field | Required meaning |
|---|---|
| `kind`, `engine` | `stt` / `whisper_cpp`, or `tts` / `piper` |
| `executable` | Absolute approved whisper-cli path, or speech Python interpreter for Piper |
| `executable_sha256` | Independently obtained expected SHA-256 of that executable |
| `model`, `model_sha256` | Root-relative installed model path and trusted expected SHA-256 |
| `language` | Two-letter approved language; initial Piper test requires `en` |
| `version` | Operator-declared reviewed runtime version; not automatic version detection |
| `license_reference` | Review record reference; supplying it is not legal approval |
| `sample`, `sample_sha256`, `expected_transcript` | STT only: approved relative 16 kHz mono signed-16 PCM WAV, trusted hash, expected text |
| `config_sha256` | Piper only: trusted hash of adjacent `{model}.json` |

Use checksums obtained from a trusted reviewed artifact/source. Hashing a file
after an unverified download is not proof of authenticity. Example local command
for comparison is `sha256sum /path/to/approved/asset`; do not invent checksum values.
Keep configuration in the existing secure server deployment mechanism, not source
control. No secret belongs in a profile. Empty defaults install nothing.

`VOICE_SPEECH_TIMEOUT_SECONDS=60`, `VOICE_SPEECH_THREADS=2`, and
`VOICE_SPEECH_MEMORY_LIMIT_MB=2048` are **policy ceilings, not measured server
recommendations**. Review them against actual available resources first. Model
files are bounded to 4 GiB, input WAV to 1 MB/15 seconds, generated WAV to 2 MB/15
seconds, transcript to 8 KB/2,000 characters, and synthesis text to 1,000 characters.
The child gets no inherited CRM secrets/proxy variables; shell execution is never
used. POSIX CPU/address-space/file-size/open-file/core limits, wall deadline,
temporary directory cleanup and process-group termination constrain execution.
The Linux launcher also requests a
[parent-death signal](https://man7.org/linux/man-pages/man2/PR_SET_PDEATHSIG.2const.html)
so a terminated worker does not leave its direct engine child running. Its behavior
and service-level descendant cleanup require Linux testing; do not use privileged
or capability-bearing engine executables.
These are not filesystem/network isolation or a complete security sandbox. Apply
reviewed worker/container service isolation, scratch quota and egress rules before
running third-party engines. Their actual POSIX behavior still needs Linux testing.

The existing Ollama settings (`VOICE_LOCAL_AI_*`) remain server-managed. No browser
endpoint can select an arbitrary inference URL or pull a model. Existing exact
origin allowlists and bounded structured-response validation remain in effect.
Local pipeline tests require actual configured inference, matching STT/TTS language
and approved server profiles. They use approved reference audio and a synthetic,
no-tools/no-customer context, not arbitrary uploaded recordings.

## CRM procedure

Open **AI Voice Assistant → Settings → Self-hosted platform controls** as Owner.
Choose **Test** first. Test and production control records, histories and speech
job selection are independent; changing one does not enable the other.

1. Enter a non-sensitive change reason. Select the operator-approved STT/TTS
   profiles, then enable each **for testing** and enable voice verification workers.
   Enable inference testing only after its operator-managed service is configured.
2. Run the STT reference transcription test and TTS synthesis test. Watch persisted
   jobs progress from queued/running to passed, failed, interrupted or expired.
   A passing synthesis yields a private playable WAV. Test audio is encrypted and
   expires after one hour; it is never included in list/status responses.
3. Run **Test local STT → AI → TTS audio**. Review measured stage latency and sample
   audio. This does not place a telephone call or establish real-time capacity.
4. Review backend gates. Evidence is bound to configuration/control versions and
   expires after 15 minutes for readiness. Any control change invalidates earlier
   evidence; finish configuration before requesting tests. A failed latest test
   cannot be replaced by an older successful result.
5. Disable any supported component without deleting its profile/configuration or
   history. Central test disables are enforced on speech jobs and existing PBX,
   Smartflo and inference test paths. CRM-wide background workers are not stopped;
   the voice worker toggle controls new voice verification use only.

Missing live media, live recording and human-transfer runtimes reject enablement.
No toggle claims installation. Inbound/outbound/processing activation remains
backend-denied even with forged client status or database eligibility flags.
There is no positive production activation implementation yet. Consequently no
Owner confirmation can currently make the system live.

**Emergency disable** requires no pretyped reason or stale UI version. It
atomically clears inbound/outbound/processing, sets emergency stop, increments the
control version and records actor/time/reason. It remains usable while another
Settings action is pending. It affects the selected environment. Repeat in the
other environment if both need stopping. There are no real active calls here;
draining, independent handoff and remote PBX cleanup still require implementation
and real acceptance before live calling can ever be enabled.

## Native number administration

Provider Connections retains native Asterisk read-only probes and optional
Smartflo. Configure an actual operator-provisioned PJSIP endpoint and approved
HTTPS ARI origin/account; a normal retail telecom account is not a SIP trunk.
Use the existing server allowlist and encrypted credential form, not credentials
in chat. A read-only probe never registers a trunk, changes routing or dials.
The current form references a PBX endpoint that the operator provisions separately;
CRM-driven trunk provisioning and live ARI control are not implemented.

Register an E.164 number draft, associate its native connection, direction, hours
and attestation references, then submit for review. Entered references are not
verified operator approval. Owner may reject, suspend or revoke with an audit
reason. Revocation is terminal in this implementation: ordinary edits/review cannot
restore it. Credential rotation preserves revoked/rejected/suspended/disabled
states. Verified caller identity, independent authorization evidence and actual
per-call authorization still need the live integration; every live call is denied.

## APIs and additive storage

All routes use the existing `/api/v1/voice-assistant/platform` prefix, authenticated
Owner dependency, response/error conventions and rate limits.

| Method/path | Effect |
|---|---|
| `GET /speech-profiles` | Safe catalogue; no executable/model paths or expected transcript returned |
| `GET /{test|production}` | Current controls, bounded audit history, backend gates |
| `PUT /{environment}/components/{component}` | Version-checked test permission/profile change; clears all live directions |
| `POST /{environment}/activation` | Disable a direction; enabling always denied pending real runtime |
| `POST /{environment}/emergency` | Version-independent atomic environment stop |
| `POST /{environment}/speech-tests/{profile_id}` | Explicit bounded durable speech job |
| `POST /{environment}/pipeline-tests` | Explicit local reference STT/inference/TTS job |
| `GET /{environment}/speech-tests?page=1` | Paginated safe results, 25 per page |
| `GET /{environment}/speech-tests/{id}/audio` | Owner-only environment-scoped non-cacheable WAV, unexpired passed jobs only |

New additive collections: `voice_platform_controls` (unique environment),
`voice_speech_jobs` (environment/date index and one-hour expiry),
`voice_speech_slots` (fixed ten-slot admission, token-fenced release), and
`voice_runtime_leases` (one global heavy speech verification). Controls retain 200
recent embedded audit entries atomically with state changes; denied activation uses
the existing audit log. Control changes/emergency stops and speech requests/results
also append safe metadata to the existing append-only audit log; truncating recent
display history does not remove those records. These supplemental audit writes
follow the atomic control change and are not a cross-collection transaction.
Speech job requests retain actor, timestamps and versions,
not raw transcripts or generated text. An interrupted job is never silently retried.
The existing ARQ cron polls explicit work; empty configuration does not run a model.

## Staging deployment and rollback

No destructive migration, seed, new authentication, sidebar item or mandatory cloud
service is added. Review additive indexes and Mongo/Redis compatibility first.
Back up the existing database, private artifacts and encryption keys through the
existing approved procedure. Deploy matching frontend/backend artifacts together
using the current pipeline and verified service names. Do not copy local `.env`
files or restart guessed units. Speech profiles stay empty until hardware/model
approval and an isolated worker deployment have been verified.

Build checks are in the report. After authorized staging deployment, confirm
ordinary CRM login/RBAC/leads/invoices, existing workers, separate environment
defaults, Owner-only controls, emergency stop and no outbound network/call side
effects. Then explicitly provision and run approved local model tests. Real PBX
tests require the actual installed version/interfaces, approved trunk and numbers,
reviewed network/RTP/TLS settings and separate explicit call authorization.

On regression use emergency disable, restore the previously approved application
artifact and environment through the existing rollback procedure, and restart only
confirmed existing units. Preserve additive records for investigation. Do not
delete business records, credentials or models as rollback. Older artifacts ignore
these new controls; their live calling was already unimplemented/disabled. Rerun
ordinary CRM and worker smoke tests and preserve evidence. No rollback or
deployment has been executed here.
