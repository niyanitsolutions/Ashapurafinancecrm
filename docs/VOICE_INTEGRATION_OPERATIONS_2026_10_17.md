# Voice safety and test-console operations — 17 October 2026

Read the [execution/acceptance report](VOICE_INTEGRATION_EXECUTION_2026_10_17.md)
and [previous callback handover](VOICE_CALLBACK_OPERATIONS.md). This is an additive
extension of existing callbacks, knowledge console, dashboard and ARQ. No new
telephony, media or active CRM tool endpoint exists. Live calling remains disabled.

## Configuration and endpoints

No new environment variable, dependency, credential or provider URL is introduced.
Optional local inference still uses existing server-managed `VOICE_LOCAL_AI_*`
configuration and approved origins; no model is installed or downloaded by this
release. Existing private speech assets/profiles remain required for local audio.
No speech language has acquired acceptance merely from this change.

All routes retain `/api/v1` (unless the existing deployment overrides its API prefix):

| Method / route | Authorization / behavior |
|---|---|
| POST `/voice-assistant/console` | Existing knowledge:view. Optional dynamic model with typed intent and independent policy. No CRM execution. Response may be withheld; read policy and warnings. |
| POST `/voice-assistant/callbacks/interpret-time` | Existing calls:create, rate 10. Input `request`, IANA `timezone`; server reference time. No record is saved. |
| GET `/voice-assistant/console/evaluations?page=1` | Owner-only; 10 immutable synthetic policy reports per page. |
| POST `/voice-assistant/console/evaluations` | Owner-only, rate 5. `suite_version=public-policy-suite-v1` and idempotency key of 16–100 safe characters. No user-supplied scenario, customer or environment accepted. |
| GET `/voice-assistant/dashboard` | Existing calls:view. Owner-only callback bookkeeping counters and readiness heartbeat appended under existing operational metrics. Simulated call metrics remain labelled. |

The policy studio is under existing AI Assist / Knowledge. Reports load only on
request; running the suite is another explicit action. Retry an interrupted run
with the same idempotency key. No synthetic report can approve/publish/activate a
release, access production credentials or place a call.

The callback manager remains on existing Lead/Loan/Insurance detail pages. A narrow
English preview accepts `tomorrow at 11 AM`, `next Monday at 09:00`, or an ISO date
with exact time. `tomorrow`, `next Monday`, `after 11 AM`, unsupported languages,
alternatives, invalid/past dates and DST overlaps ask for clarification. No day or
time is silently guessed. Select **Use proposed time in form** to copy only a
proposed value; then follow existing save and explicit confirmation. A preview is
not a scheduled job. Existing consent, suppression, scope and readiness gates apply.

## Evidence and recovery

Typed intent confidence is model-reported. Public answers need current citations;
numeric checks compare tokens against cited excerpts. This is not semantic or
financial accuracy certification. Protected loan/insurance/payment/document intents
remain blocked without a trusted voice identity/tool implementation. A staff login
does not authenticate a telephone caller. `execution_allowed` remains false.

The console returns `safety_hold` for priority contact/human signals without invoking
the model, and `superseded` when settings/model configuration or current retrieved
publications changed during generation. Retry only after review. Permission/account
revocation returns 403 even when model generation fails. Do not work around this.
`provider_unavailable` is a failed optional local model request, not live readiness.
Policy/schema changes invalidate existing local inference/pipeline verification;
run new functional tests after approved deployment. Old evidence remains in storage.

New `voice_policy_evaluations` holds synthetic reports only. It has no update/delete
API and no automatic expiry that deletes history. Existing startup initialization
adds two repeatable indexes: unique `(created_by, suite_version, idempotency_key)`
and descending `created_at`. No destructive migration or historical backfill is
needed. This follows the repository's existing additive startup-index pattern;
no separate versioned migration runner exists for this module. Real MongoDB
startup/index/race behavior still needs staging acceptance before rollout.

Existing callback ARQ updates `voice_worker_health` key `callbacks` only after a
successful readiness sweep. A stale/absent heartbeat is unknown; a recent heartbeat
proves a review completed, not dialing/media capacity. ARQ does not execute calls.
Repeated report/worker execution does not increment call-attempt or live-success
metrics. Request counters use configured timezone and preserve test/production
separation; definitions are in the execution report.

## Reviewed rollout and rollback — do not execute automatically

Current user-supplied paths (not independently verified host inventory): repository
`~/Ashapurafinancecrm`, backend `backend`, frontend `frontend`, venv `~/afscrm-venv`;
services `afs-crm-backend`, `afs-crm-arq-worker`; domain
`https://afs.niyanitsolutions.com`. Preserve all environment files and unit settings.

Before deployment approval: inspect the actual host with the existing read-only
inventory, verify unit working directories and release artifacts, back up Mongo,
encrypted recordings/artifacts and configuration/keys through the existing secure
procedure. Never print environment secrets, tokens or customer content. Verify a
clean server worktree; stop for unexpected local changes. Use existing reviewed
dependency installation/release steps. No lock/dependency changes are needed here.

After approval and verified paths, operator checks:

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

Local validation used Node 22. Only after release approval and successful checks:

```bash
sudo systemctl restart afs-crm-backend
sudo systemctl restart afs-crm-arq-worker
systemctl is-active afs-crm-backend afs-crm-arq-worker
curl --fail --silent --show-error https://afs.niyanitsolutions.com/api/v1/health
```

The existing health route checks Mongo/Redis; inspect its returned status, not only
HTTP status. It does not test media, model, provider, real calls or approval.
Verify authenticated Owner/staff route restrictions, repeatable index creation,
policy report replay, callback preview creating no Task, normal CRM Task behavior,
worker heartbeat and retained callback history. Run fresh local functional speech
tests only after assets/environment are reviewed; model/PBX testing remains separate.
Keep emergency stop and live directions disabled throughout these checks.

Rollback must use a reviewed artifact compatible with all retained callback Tasks.
Keep the managed Task edit/complete guard described in prior operations; older
generic Task handlers must not rewrite callback schedules without history. Preserve
synthetic reports, all histories, audits, keys, policies and artifacts. No collection
drop, index deletion, reset, clean or data truncation is required. Restore reviewed
compatible backend/frontend/worker artifacts through the existing release process;
retain emergency stop and do not restore revoked credentials or unsafe approvals.
Fresh verification is required after changing policy/schema/configuration. Neither
rollback nor service restart authorizes production calling. No commands above were
run on the server by this session.

A rollback artifact must also retain the text/TTS proposal-policy guard. If that
cannot be done, disable inference and STT/TTS verification components through the
existing Owner platform controls before the downgrade and keep them disabled until
the older path has been reviewed. Emergency stop alone blocks live directions; it
does not prohibit intentional local verification tests. Do not downgrade to an
unguarded generated-output path and then reuse old green health evidence. Cancel or
let existing bounded verification jobs observe the disabled controls before recovery.
