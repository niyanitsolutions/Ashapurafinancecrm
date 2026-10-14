# Voice operations and activation runbook

Current campaign scope and measured local evidence are in
[AI_VOICE_ASSISTANT_EXECUTION_REPORT.md](AI_VOICE_ASSISTANT_EXECUTION_REPORT.md).
Campaign workers evaluate eligibility every 15 seconds; they never dial.
The approved initial test profile is 10 concurrent calls/10,000 recipients, with
live staging still blocked. This profile is not measured capacity or a service-level
target. Campaign emergency-stop clearing requires Owner API access and a reason;
it does not resume paused campaigns. See the API notes for exact registered paths.

Live calling stays disabled. No approved speech/AI service or carrier verification
exists. Smartflo setup/test details are in `SMARTFLO_VOICE_AUDIT.md`. Never register
its deliberately blocked resolver/media endpoints as live provider flows.

The existing backend, Mongo, Redis and ARQ worker are required. The existing
worker reconciles simulations; artifact-retention tasks run on the
same worker. Monitor truthful heartbeats and failures, not inferred success from
an open port. Backend liveness alone cannot prove media/model readiness.

Production needs stable `ENCRYPTION_KEY`, strong JWT configuration, TLS, trusted
proxy addresses, Mongo backups and Redis/worker recovery. New private recording
directory is controlled by `VOICE_RECORDINGS_DIR` (empty disables imports). It must
be an absolute private path outside web/static roots; do not expose it through Nginx. Provision
encrypted persistent storage, owner-only directory permissions, capacity alarms,
backup encryption and tested restore. Filesystem records are not an object-store
verification. Horizontal API/worker instances require a shared private durable
volume or a separately implemented private object-storage adapter.

For SIP operation, provision an isolated Linux PBX/SBC and approved trunk/number,
limit SIP/RTP ports to known peers, secure ARI/ESL, configure codec negotiation,
TLS/SRTP where supported, and test real control/media/failover before activation.
Do not expose PBX admin interfaces publicly. Resource sizing requires representative
concurrent calls and measured inference/audio latency. No default fake registration.

Deploy reviewed source/package plus built frontend using existing runbook. Additive
indexes/catalog initialize at backend startup; targeted `scripts/voice_catalog.py`
does not grant users new permissions. Restart API and ARQ after changes. Verify
Owner navigation and grant specific voice resources through existing administration.
No production migration, restart or deployment is executed by this task.

Recovery: disable callback intake first if reverting the provider batch; stop
artifact writes during a rollback; preserve Mongo metadata, encrypted artifacts
and encryption keys; revert package/frontend; restart both processes. New optional
knowledge fields and derivative collections are additive and must not be dropped.
Test restored metadata against real stored hashes before marking recovery verified.

Required manual checks: private artifact persistence across restart, key restore,
deletion/retention, permission-denied playback, PBX outage, agent unavailable,
speech timeouts, barge-in latency, multilingual quality, suppression/calling windows,
identity assurance and all five master acceptance scenarios. Record measured
outcomes; local fixtures alone cannot approve production.

## Configuring the implemented artifact workflow

For Compose, set `VOICE_RECORDINGS_DIR=/var/lib/afs/voice-recordings` in the backend
environment file used by **both** API and worker. The additive `voice_recordings`
named volume is mounted at that path in both services. An empty variable keeps
audio imports disabled. For systemd, use a persistent private absolute path shared
by those processes and the same stable encryption key. No key or path is returned
to browsers. POSIX writes require owner-only directory permissions (0700), with
artifact files 0600; run API/worker as the same appropriate service account. Windows
requires independently verified private ACLs. Check ownership and backups first.

WAV bounds: 20 MB, 0.1–1,800 seconds, PCM 16-bit mono/stereo at 8/16/24/48 kHz.
No MP3, WAV compression or live capture. Knowledge bounds: 5 MB, 50,000 extracted
characters; OOXML expansion 10 MB/300 entries, XLSX 3 sheets/500 rows/32 columns.
TXT/CSV accept UTF-8 with optional BOM or BOM-marked UTF-16. Formula/macro,
external relationship, encrypted archive and embedded-object violations fail safely.
No OCR, PDF extraction, remote URL fetching, malware scanner or embeddings enabled.

API middleware limits multipart envelopes before spooling and admits at most two
voice imports per API process; upload routes have rate limits. Nginx uses 6 MB for
knowledge multipart and 21 MB for audio multipart; backend still enforces file
and actual streamed-envelope limits. Non-default API prefixes require matching
Nginx upload locations. Limit inference/media concurrency separately before live use.

The ARQ retention/recovery task runs every five minutes and at startup, processing
at most 100 records. Playback checks expiry immediately without waiting for the
worker. Interrupted imports with expired 120-second processing leases recover only
from hash-verified, decryptable valid audio; missing/corrupt files become failed.
Expired/deletion-pending artifacts are removed with their transcript ciphertext;
deletion failure remains pending and retries rather than claiming deletion. Monitor
`voice_worker_health` key `recordings` and dashboard cleanup failures. A completed
metadata row whose file disappeared returns a clear playback error; repair storage
or delete it, never substitute audio or silently report success.

Backup deletion policies, key rotation/re-encryption, replicated private storage,
capacity/restore, Linux permission verification and large-file performance
still need operator acceptance. Existing shared S3 is not selected here because
private bucket/encryption policy is unverified. A future object-store adapter must
check durability and access controls before any completed state.

Frontend production builds and CI use Node 22 and now install from the lockfile
with `npm ci`. The development host was Node 18.17.1 and emitted package-engine
warnings despite passing checks; verify the Node 22 image before release. React
Router is pinned to 7.18.4; no model/runtime service was installed.
