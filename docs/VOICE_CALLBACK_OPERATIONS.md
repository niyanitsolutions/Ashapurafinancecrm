# Durable callback operations — 16 October 2026

17 October extension: [time-preview and test-console operations](VOICE_INTEGRATION_OPERATIONS_2026_10_17.md).
Previewing an English date fills no Task and places no call. Applying the preview
only fills the existing form; explicit save and confirmation still apply.

This continuation adds supervised callback requests to existing Leads, Loan and
Insurance detail pages and the existing Tasks system. No production deployment,
call, service restart, dependency installation or provider registration occurred.
Native SIP remains primary; Smartflo remains optional. Sidebar and route navigation
are unchanged. Read the [audit](VOICE_WORKFLOW_AUDIT.md) and
[execution report](VOICE_CALLBACK_EXECUTION_REPORT.md) before acceptance.

## Workflow and safety boundaries

Open **Schedule or review AI callbacks** on a scoped detail record. Select the
test/production record environment, supervisor, exact local time, IANA timezone and
brief customer preference. Ambiguous daylight-saving times require a specific
occurrence; nonexistent times are rejected. The system does not guess natural
language dates. Staff attestation does not establish telephone identity or consent.
Do not enter OTPs, credentials or financial details in free text.

The initial state is `awaiting_confirmation`. Explicit confirmation makes it
`scheduled`; rescheduling returns it to `awaiting_confirmation`. Due review records
`blocked` while live implementation/readiness is unavailable. An unconfirmed time
that passes becomes `confirmation_expired`; obtain a new explicit time and confirm.
Cancellation, suppression and the history safety limit close the request as
`cancelled`, `opted_out` or `closed_history_limit`. Administrative Task completion
in those paths does not mean a call completed. No positive call outcome exists in
this implementation. Every response reports zero calls placed.

Original preference, local time, timezone, DST occurrence, UTC date, actor and
subsequent reasons remain in append-only embedded history. History is paginated;
it is never trimmed to make room for new events. At 1,000 events only cancellation
or a final safety closure is permitted; obtain a reviewed new request afterward.
Manual CRM follow-up dates, historical notes and normal Tasks remain unchanged.
Managed Tasks reject generic edit/complete operations; use their callback controls.

The Owner's global voice do-not-call action uses the existing contact-policy API
before cancelling the selected request. These are separate documents, not a
cross-document transaction. If cancellation conflicts, suppression remains saved;
refresh and cancel through callback controls. Existing policy authorization applies.
Cancellation alone does not assert global suppression or revoke unrelated consent.

## Storage, authorization and worker

`tasks.voice_callback` is optional, embedded metadata on the existing Task, not a
second follow-up database. Additive startup indexes enforce idempotency per actor
and environment and one active request per authoritative contact and environment.
Unlinked Leads use a Lead key. They may record a request but cannot become eligible
for calling without an approved authoritative contact/consent binding. No customer
is silently created. Test and production callback records are distinct; this is
not a claim of physically separate provider infrastructure.

Voice calls view/create/edit, existing entity scope, Task permissions and active
accounts are enforced server-side. Staff supervise only themselves; Owner assignment
uses an active employee/account. Loan and Insurance permissions honor current-stage
resources where declared. History requires current record access. Customer preference
is not included in ordinary Task responses or audit metadata. Optional source-call
references require matching real customer and environment; mock calls are rejected.

State, date and history update together using a version compare-and-swap. Repeated
unchanged create requests reuse their idempotency key; changed payloads conflict.
Unique indexes prevent concurrent active requests across modules for one bound
contact. Real MongoDB index/race acceptance remains a staging check.

The existing ARQ worker reviews at seconds 10 and 40, including startup recovery,
up to 25 due records per pass. Unchanged blockers postpone review five minutes
without adding duplicate history. It rechecks record/account authorization,
customer binding/status, global suppression, unexpired callback consent, business
hours/holidays and platform controls. It never dispatches or retries a telephone
call. `retry_readiness` means review only. Live reservation/retry/outcome handling
is still unimplemented. Restarting a worker recovers persisted Tasks; there is no
second scheduler or in-memory-only callback queue.

The callbacks component appears in existing platform controls. Older records have
an effective default of disabled; reads do not rewrite their stored configuration.
Saving a request while this toggle is off does not enable automation or calls.
Existing hard activation gates also require identity and live callback safety.

Routes use the existing `/api/v1` prefix:

| Method | Route | Purpose |
|---|---|---|
| GET | `/voice-assistant/callbacks?entity_type=lead&entity_id=...&environment=test&page=1` | Scoped list/capabilities, 25 per page |
| POST | `/voice-assistant/callbacks` | Idempotent request, rate limited |
| POST | `/voice-assistant/callbacks/{id}/actions` | Versioned confirm/reschedule/cancel/retry_readiness, rate limited |
| GET | `/voice-assistant/callbacks/{id}/history?page=1` | Scoped history, 25 per page |

No new secrets, provider URL, environment variable or dependency is required for
this bookkeeping extension. Existing server-side secrets remain unchanged.

## Deployment and rollback — operator instructions only

Current **user-supplied** paths are `~/Ashapurafinancecrm/backend`,
`~/Ashapurafinancecrm/frontend` and venv `~/afscrm-venv`; services are
`afs-crm-backend` and `afs-crm-arq-worker`. Domain:
`https://afs.niyanitsolutions.com`. These override historical PDF examples, but
unit definitions, filesystem paths and hardware are not verified by this session.
Use the existing authenticated administrative connection, never credentials in chat.

Before an explicitly authorized rollout, run the existing read-only
[inventory](../scripts/voice-server-inspect.sh), inspect unit working directories
without printing environment secrets, and verify release provenance, clean worktree,
backups, storage and Mongo index permissions. Back up Mongo, existing configuration,
encryption keys and artifacts through the approved process; do not copy secrets to
this repository. Ten calls/10,000 recipients remains an unmeasured target.

The inventory's disk check now defaults to the user-supplied
`$HOME/Ashapurafinancecrm`; a verified different repository directory can be passed
as its first argument. This only selects a path for `df`, without reading secrets
or changing the host. The updated script has not been run on the actual server.

Operator checks, after paths and release have been reviewed:

```bash
cd ~/Ashapurafinancecrm
git status --short
git log -1 --oneline
source ~/afscrm-venv/bin/activate
cd backend
python -m pip check
cd ../frontend
node --version
npm run build
```

Stop on unexpected local edits or dependency/version differences. Use the existing
approved release/install process; do not reset/clean the server worktree. Node 22
was used for local verification. This continuation changes no dependency locks.
Only after deployment approval, unit/path verification and successful release checks:

```bash
sudo systemctl restart afs-crm-backend
sudo systemctl restart afs-crm-arq-worker
systemctl is-active afs-crm-backend afs-crm-arq-worker
```

Verify authenticated callback CRUD/history, an ordinary Task, index creation,
worker registration/recovery and unchanged CRM routes. Inspect logs with existing
redaction controls; never paste secrets or customer statements. Keep live gates and
emergency stop closed. Do not treat a frontend build or health endpoint as telecom
acceptance. Check due review without contacting a telephone number.

Rollback must preserve all callback Tasks, embedded history, policies and audit
records. **An older release ignores `voice_callback` and may allow generic Task
editing without preserving callback history. Retain the managed-Task guard in the
rollback artifact whenever callback data exists**, or use a separately reviewed
snapshot/quarantine procedure that preserves that data. Do not blindly downgrade
and then edit managed Tasks. Disable callback processing through existing controls
and retain emergency stop before any authorized rollback. Restore the reviewed
compatible backend/frontend/worker artifact through the existing release process;
do not delete indexes or callback records as cleanup. Verify normal Tasks, scoped
records and retained history after recovery. No rollback commands were executed.

Native control/media, real caller identity/tools, live spoken-time extraction,
streaming interruption, transfer, actual dispatch/retries and approved models remain
required application/infrastructure work. Actual capacity, licenses, telecom/number
authorization, consent and live end-to-end acceptance must all pass before calling.
