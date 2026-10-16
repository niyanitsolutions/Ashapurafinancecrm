# Voice platform continuation — 16 October 2026

Baseline: clean `942c63c`. Existing architecture is React/React Query, FastAPI,
Motor/Mongo and Redis/ARQ, existing bearer authentication and Owner RBAC. Decision
001 defers multi-tenancy; do not claim tenant isolation or introduce a partial
tenant scheme. Sidebar, routes and business workflows remain intact.

Prior work supports encrypted Owner configuration, read-only ARI probes, Ollama
text checks, reviewed knowledge, imported audio and simulated/dry-run calls.
It does not implement native live control/media, installed speech or activation.
Actual server access, hardware, PBX version, approved trunk, models, test numbers
and operator approval are unavailable. No production action is authorized.

Implementation sequence:
1. Durable environment-separated component controls, readiness and emergency stop;
   optimistic concurrency, audit history, stale-evidence rejection and server gates.
2. Operator-catalogued local whisper.cpp/Piper execution, content-integrity checks,
   bounded subprocess tests and durable ARQ verification jobs. No automatic install
   or model download, arbitrary browser paths/commands or unapproved model choice.
3. Central Settings with real backend configuration/test/disable actions, distinct
   test/production state and explicit unmet prerequisites. Preserve existing panels.
4. Tests for permissions, isolation of environments, stale/racing configuration,
   subprocess bounds, actual WAV validation, worker recovery and UI states.
5. Document actual local results and deployment steps; retain blocked live media
   work until supported deployed PBX interfaces can be verified. No mock, text
   probe, process or entered reference can satisfy actual live acceptance.

Official interface references inspected: whisper.cpp CLI, Piper CLI and Asterisk
WebSocket channel documentation. Deployed Asterisk version is unknown; do not
assume its newer media driver exists. No server/hardware specification inferred
from the sample deployment guide. Python advisory audit stays offline as requested.
