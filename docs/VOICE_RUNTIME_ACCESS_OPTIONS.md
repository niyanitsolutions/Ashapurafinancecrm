# Runtime validation options for Owner selection

17 October 2026. No host connection, installation, purchase, firewall change,
production modification or infrastructure creation is authorized by this comparison.

Observed: no user/system SSH client configuration files were found; SSH, WSL and
Docker executables exist. `wsl --list --quiet` failed with access denied, so no
distribution is verified. Docker daemon pipe is unavailable. No remote staging
session or existing PBX was verified. Deployment guides contain assumed host
properties and historical paths, not current server inventory.

Recommendation: **option 8 immediately, with option 7 to discover infrastructure**.
For full staging acceptance, prefer option 2 if an isolated suitable host exists;
otherwise prepare option 4 for separate Owner approval. This recommendation does
not select or purchase hosting or telephone connectivity.

| Option | Benefit and validation support | Limits / security / prerequisites | Cost basis |
|---|---|---|---|
| 1. Approved SSH connection | Read-only inventory; full Asterisk/local AI acceptance possible on suitable Linux target | Owner names and approves host/key; no alias found; restrict access and keep keys out of reports | Existing hosting plus actual usage |
| 2. Existing staging server | Reuse isolated deployment; best existing option for full DB/PBX/AI recovery acceptance | Verify access, resources, versions, backups and separation from production | Incremental usage/storage; possible upgrade |
| 3. Existing approved Linux server | Can validate complete self-hosted stack with adequate resources | Separate test services/data/networks; shared production workload introduces contention; inspect only until changes authorized | Existing hosting, headroom and possible upgrade |
| 4. New self-hosted Linux staging | Clean isolation and reproducible DB/PBX/model experiments | Separate approval for cost, OS/image, hardware, region, admin access, backups and private network | New VM/physical host, storage, backup, power/bandwidth; GPU extra |
| 5. Existing WSL Ubuntu | Linux process/speech tests, isolated DB and internal SIP experiments | Enumeration currently denied; verify distro/hardware and networking; cannot establish production firewall/systemd/capacity equivalence | Existing workstation resources and electricity; no purchase assumed |
| 6. Docker staging | Repeatable isolated service topology and DB experiments | Not usable now; Owner approval needed to install/start/reconfigure; SIP/RTP networking and host limits require acceptance | Host resources; applicable license/support; no automatic purchase |
| 7. Manual inventory | Establish actual host/PBX/model facts without remote access | Owner runs reviewed commands, redacts output; report alone cannot verify call/audio/recovery acceptance | Operator time |
| 8. Continue without remote access | All independent repository fixes, mock/fake integration contracts, builds and regressions | Actual Linux/PBX/models/MongoDB races/restore/audio remain explicitly blocked | Current development environment; no new infrastructure |

## New-host planning envelope — estimates, not measured capacity

Start with Ubuntu Server 24.04 LTS compatibility evaluation; reuse a supported
existing OS only after inventory. For isolated PBX/CRM integration experiments,
budget approximately 4 vCPU, 8 GB RAM and 80 GB SSD. For initial small local model +
STT/TTS evaluation, provision or reuse a separate approximately 8-core, 32 GB RAM,
100+ GB SSD machine; select GPU/VRAM only after model/package and concurrent memory
measurements. These estimates do not certify real-time performance, ten calls or
production sizing. PBX and AI may need separate hosts. Ubuntu installation minima
are not application capacity estimates:
[Canonical requirements](https://github.com/canonical/ubuntu-server-documentation/blob/main/docs/reference/installation/system-requirements.md).

Illustrative compute cost anchor, checked against the provider's published June
2026 adjustment: European CX33 / CX43 monthly prices are €8.49 / €15.99 excluding
IPv4. Region, tax, availability, backup, storage, networking and GPU change cost;
these are not all-in voice budgets, India-region quotes or a provider selection.
Telephone-network interconnect and number charges are separate. On-premises
purchase/power and GPU costs require an actual configuration quote:
[official price table](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/).

After a separately approved option 4/5/6 setup: verify hardware/OS; create an
isolated account/network/storage; restrict admin access; provision separate
Mongo/Redis; back up and rehearse restore; install pinned approved Asterisk/modules;
configure only private test extensions; install licensed pinned local speech/model
assets; exercise internal calls and failures; then measure capacity. No public
trunk, number, port exposure or production activation is part of these steps.

## Manual non-secret inventory checklist

Run the reviewed [inventory script](../scripts/voice-server-inspect.sh) from an
existing authorized Linux session. Review output before sharing it. Supply:

- OS/version/architecture, CPU count/model, RAM/swap, available disk and GPU/VRAM.
- Whether the machine is production, staging or development, and workload headroom.
- Service names/states and package versions for CRM, Mongo, Redis, Nginx, Asterisk
  and local model/speech services; do not include service environment or command lines.
- Asterisk version and presence of PJSIP, ARI/Stasis, WebSocket media, codec and
  SRTP modules; no endpoint/customer lists or live channel details.
- Private network layout and approved traffic requirements, certificate status,
  clock synchronization, backup/restore evidence and storage encryption status.
- Presence/status of an authorized trunk or gateway, approved number/directions
  and test-only endpoints; omit numbers, account identifiers and credentials.
- Model/voice names, versions/hashes/licenses and measured readiness without prompts,
  customer audio, transcripts, secrets, private logs or configuration contents.

The Owner selected **option 8 — continue locally** during this session. Other
options remain unapproved; elapsed time or recommendations do not authorize them. The detailed
[self-hosted contract](VOICE_SELF_HOSTED_STAGING_CONTRACT.md) identifies the remaining
PBX, verification, media and telephone-network gates.
