# 500-conversation capacity plan

**Target: 500 independent conversations. Measured production/staging capacity:
unknown. No 500-real-call readiness claim.** The older 10-call profile is superseded
as a target, not retroactively reclassified as measured capacity.

## Executed synthetic scope

Progressive pytest profiles: 1, 10, 50, 100, 250 and 500 isolated Airtel codecs;
the same profiles also run the existing dynamic core with overlapping fake model
work, fake TTS, per-session retrieved excerpts and per-session history/media.
The model barrier ensures all sessions reach in-flight model work before release.
Assertions check identities, separate history/content/output and final cleanup.
These are deterministic isolation regressions, not real-time benchmark calls.
They do not open WSS connections, recognize audio, run model inference, pace audio,
measure a long-running stream, exercise Mongo/Redis distributed admission or use
an approved trunk. No first-token/voice latency, GPU, sustained throughput, carrier
quota or actual call success metric was measured.

## Known protocol arithmetic, not host sizing

At 8kHz mono μ-law, each direction is 8,000 raw bytes/sec/call. At 500 calls that
is 4MB/sec per direction, 8MB/sec duplex (64Mbps raw). Base64 turns each160-byte
frame into216 bytes. At50 frames/sec,500 calls and two directions this is10.8MB/sec
(86.4Mbps) of Base64 payload alone, excluding JSON, TLS, TCP and other CRM traffic.
The host must handle approximately25,000 inbound plus25,000 outbound media
messages/sec at full duplex. These are transport calculations, not evidence that
the current server or carrier can support that rate.

## Infrastructure and admission still required

Inventory the actual staging host: OS/kernel, CPU and quotas, RAM/headroom, free
disk/IOPS, GPU model/VRAM/driver, Docker availability, existing CRM/backend/worker
load, Mongo/Redis topology, reverse proxy and network limits. Existing local and
user-supplied deployment paths are not a remote inventory. Do not select a model,
GPU size or separate-server specification from invented hardware information.

The current per-utterance whisper.cpp/Piper verification jobs and their single-flight
gate are deliberately **not** a500-call engine. A separately accepted streaming
runtime is needed. Reuse CRM control/auth/data services; protect them from inference
and media overload. Decide whether inference/media need a separate host only after
measurements, with a specific recommendation tied to measured bottlenecks.

Implement distributed admission before accepting media: atomic global/provider/
runtime limits, expiring leases with fencing/renewal/reconciliation, bounded
per-call audio buffers and bounded task pools. Do not use process-local counters
to claim a cluster limit. Admission must fail before taking a call the system cannot
serve; an unlimited queue is not extra capacity. The new requested-concurrency
setting is metadata only and cannot increase existing operational limits.

## Real acceptance at each stage

At 1/10/50/100/250/500: establish approved test endpoints and carrier entitlement;
measure WSS admission failures, STT end-of-turn/accuracy, LLM first-token and
completion, TTS first-audio, end-to-end response and interruption latency, sustained
audio gaps, active-session count, CPU/RAM/GPU/VRAM, ingress/egress queue depth,
network, disconnect cleanup and worker/CRM health. Agree latency/error/resource
thresholds before testing; no unapproved SLA is implied. Run multi-minute real
dialogues, independent questions/context, multilingual profiles only for approved
models, takeover/outages, overload and recovery. Stop escalation on failed gates.

For each stage retain configuration/model/image digests, measured host inventory,
provider quotas, duration, p50/p95/p99 distributions and errors. High-volume
campaign mode in guide pp6–7 lacks real-time events/CDR; validate SFTP reconciliation
separately rather than equating campaign submissions with live conversations.
