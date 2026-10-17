# AI Voice Assistant implementation and evidence — 17 October 2026

## A. Executive status

**Overall: NOT COMPLETE. Production: NOT PRODUCTION READY.**

Baseline branch `main`, HEAD `6ffa4e82eda0a6465460acf6d068c6c99fc354c7` plus the
pre-existing uncommitted work and changes described here. No commit, release
publication, staging approval or production activation was performed. Final source
identity is recorded in `voice-hardening-source-manifest-2026-10-17.json` with digest
`6e72ab5a9e083a3e4dcdf57247fc6d0e2f05a8f617e3b1949095363da5f8bb5a`;
this identifies an uncommitted source tree, not an approved runtime release. There is
**no exact staging-approved release**. A source hash manifest records preservation
of the pre-existing non-secret files in `voice-hardening-baseline-2026-10-17.json`.

The Owner selected **option 8: continue locally**. No installation, remote host
connection, infrastructure purchase, production migration, service restart,
firewall change or real telephone call was authorized or performed. Self-hosted
Asterisk is the preferred candidate, not a verified deployed PBX. See
[runtime options](VOICE_RUNTIME_ACCESS_OPTIONS.md) and
[self-hosted staging/verification contract](VOICE_SELF_HOSTED_STAGING_CONTRACT.md).

External blockers: actual isolated Linux/Mongo/Redis/PBX environment; installed
licensed pinned model/speech assets; approved caller factors/disclosure fields;
test endpoints and later authorized telephone-network connectivity. There are also
**unfinished implementation requirements**, detailed below. These are not merely
missing credentials and are not represented as complete by negative tests.

## B. Requirement traceability and implementation checklist

Paths below use V=`backend/app/features/voice_assistant`, T=`tests/api`,
U=`frontend/src/features/voice_assistant`. PASS applies only to the named local
behavior. Requirements with missing implementation are FAIL; externally unavailable
acceptance is BLOCKED. No phase is certified by a local test count.

| ID | Implemented behavior and references | Local evidence / remaining requirement | Status |
|---|---|---|---|
| R0.1 / G01 | `V/dynamic_audio.py:_generate/_current/interrupt` uses shared `proposal_policy`, requires host authorization, rechecks before synthesis/frames/marks, fences obsolete generations, clears media on denial, bounds takeover wait | `test_voice_streaming_safety.py` covers unbound/denied/protected/unclassified output, revocation at model/synthesis/frame boundaries and noncooperative cancellation. Actual native session/stop/publication binding and approved financial-source/model acceptance are not implemented | FAIL |
| R0.1 / G02 | `V/intent_policy.py` only allows reviewed non-disclosing clarification questions or complete approved public excerpts; v2 policy and implementation hash | `test_voice_intent_policy.py` rejects arbitrary assertions and appended injection despite valid unclear classification. Public factual text must match a complete cited approved excerpt; unsupported paraphrases, qualifier omission and arbitrary assertions are denied. Actual approved-source financial quality/model evaluation remains BLOCKED | BLOCKED |
| R0.2 / G05 | `recording_service.save_transcript` atomically retains encrypted prior correction versions; bounded count/size rejects overflow without trimming; deletion unsets all ciphertext revisions | `test_voice_platform.py:test_real_artifact_encrypted_playback_range_transcript_delete` proves correction preservation, no public ciphertext, deletion. Settings/knowledge/platform/number/contact histories still have capped snapshots | FAIL |
| R0.2 / G07 | `callback_service.sweep` closes ineligible requests, releases active slot, preserves history; scans expired requests for suppression; `resolve_owner` adds terminal-only Owner closure without deleted-parent access | Callback lifecycle tests cover parent delete/purge, creator/supervisor revocation, actual customer-binding mutation, customer deletion, expiry/DNC, duplicate resolution, denied adoption/staff resolution. Actual Mongo races remain blocked | BLOCKED |
| R0.2 / G08 | Task CAS embeds event receipt identity and `audit_pending`; `audit/reconcile_audit` insert stable deterministic audit IDs and clear pending only at observed Task version; create replay repairs receipts | Fault-injected create after domain commit, replay and concurrent repair tests. Legacy events without receipt IDs are not fabricated. Other multi-write domains and future external-call outbox remain unfinished | FAIL |
| R0.3 / G09 | Existing unconditional live denial retained; offline streaming host guard and generation fencing added; local utterance pipeline rechecks authorization after synthesis | No live call drain, unified native runtime stop or accepted rollback exists | FAIL |
| R1.1 | Existing Asterisk read-only probes, deployment inventory and preferred Asterisk 22 LTS candidate evaluated in self-hosted contract | No verified host/PBX/trunk, usable local Docker daemon or WSL inventory. Owner chose local-only work | BLOCKED |
| R1.2 | Existing mock-only models and live-entry rejection preserved | Native session/control/event reducer/media integration still unimplemented; installing credentials cannot supply it | FAIL |
| R1.3 | Local utterance adapter and hardened offline streaming engine retained as separate scopes | Actual bidirectional streaming STT/TTS/native media adapters and authorized staging evidence absent | FAIL |
| R2.1 | Existing staff auth/record scopes inspected; protected proposals continue `customer_verified=false`, `execution_allowed=false`; local-first portal-confirmation proposal documented | No approved caller factor/disclosure policy, call-bound verifier, customer tool broker or governed verified memory | BLOCKED |
| R2.2 | Existing canonical managed Tasks improved; Owner resolution integrated into existing Tasks page | Actual callback reservation/dispatch, contact-window composition, native transfer and provider reconciliation missing | FAIL |
| R2.3 | `POLICY_DIGEST` added to model/speech evidence fingerprints; suite v2 includes assertion-in-clarification regression cases | Composite release manifests/approvals/pins and accepted languages remain absent | FAIL |
| R3.1 | Isolated staging additive index runner/checker plus mock conflict/restart harness | Real Mongo/Redis/Linux/PBX recovery, backup restore, live release/migration rollback and capacity acceptance unavailable | BLOCKED |
| R3.2 / G10 | `VoiceService.dashboard` explicitly filters mock source and bounded creation cohort; publishes provenance, freshness and both average denominators; includes closed-ineligible callback counts | `test_voice_metric_provenance.py` calculates expected fixture results independently. Real event metrics, measured capacity/alerts and detailed health alignment remain unfinished | FAIL |
| R4.1 / G15 | No unproved duplicate modules removed; same `proposal_policy` now guards all three conversation paths; existing CRM services/Tasks preserved | Full maintenance/consolidation gate depends on accepted runtime and complete regression evidence | BLOCKED |
| W4.1 inbound | No public carrier/media ingress added; all live entries denied | Entire actual inbound ring/answer/media/verified identity/outcome workflow absent | FAIL |
| W4.2 outbound | Canonical Task lifecycle, consent-purpose checks and safe closure tested | No real dispatch/attempt/outcome integration | FAIL |
| W4.3 conversation | Shared typed proposal policy and cancellation fencing implemented in offline stream; existing console rechecks preserved | Unrestricted paraphrases are withheld; actual media/identity/tool session integration and approved financial-source quality missing | FAIL |
| W4.4 handoff | Offline interruption/takeover cannot publish obsolete audio; mock handoff remains labelled simulation | Native destination/bridge/agent acceptance/failure fallback unimplemented | FAIL |
| W4.5 tools/memory | Protected tools remain denied; encrypted transcript correction provenance retained | Approved factor/fields and verified customer memory/tool authorization unavailable | BLOCKED |
| W4.6 analytics | Mock metrics, callback bookkeeping and artifacts remain separate, with explicit denominators and unavailable live values | No observed real connection/delivery events, latency/capacity/alert acceptance | FAIL |

## C. Phase exit gates

Remaining audit cross-references: G06 maps to R2.3; G11 to R2.2/5.1
(purpose fixed, full contact-window composition still missing); G12 to R1.2/R2.2
(reserved settings still have no real executor); G13 to R1.1/R3.1 (target assets and
runtime unknown); G14 to R3.1/5.10 (staging migration mechanics only); G16 to R3.2
(capacity unmeasured). G17 now has an actual customer-binding mutation in
`test_lost_authority_closes_and_releases_contact_slot`, not merely the old test
name; real dispatch/database races remain unverified. No original finding is waived.

| Phase | Exit decision and evidence |
|---|---|
| 0 | **FAIL** — local policy/callback/audit safety improved and tested; accepted model/financial-source quality, all-domain reconstructable revisions and unified runtime stop/rollback remain incomplete |
| 1 | **FAIL** — real native call/media implementation absent; target-runtime acceptance **BLOCKED** |
| 2 | **FAIL** — callback bookkeeping works; real dispatch/transfer/releases missing; approved caller/disclosure policy **BLOCKED** |
| 3 | **BLOCKED** — no actual Linux/Mongo/PBX/models/restore/capacity environment; local harness does not satisfy this gate |
| 4 | **BLOCKED** — documentation updated with evidence boundaries; full maintainability gate cannot precede completed/accepted runtime |

## D. Ten critical details

| ID | Actual change / evidence | Remaining gate and status |
|---|---|---|
| 5.1 purpose | `ContactPolicyPanel` now defaults to exact `callback`; tests explicitly reject `service_callback`, marketing and missing consent for worker eligibility | Historical grants deliberately remain unchanged and require a fresh reviewed attestation. Local contract PASS; actual dispatch/architectural tenant acceptance BLOCKED |
| 5.2 expiry | Expired callbacks remain dispatch-ineligible; worker revisits for DNC/lifecycle; Owner Tasks resolution cancels with explicit reason/version; ordinary reschedule still clears confirmation | Local cancellation/expiry/repeat tests PASS; real Mongo expiry/worker race acceptance BLOCKED |
| 5.3 lifecycle | Missing/purged parent, revoked creator/supervisor, changed binding or inactive customer -> terminal `closed_ineligible`; no implicit ownership transfer; history retained | Local lifecycle/zero-call tests PASS; future real dispatch races BLOCKED |
| 5.4 idempotency/audit | Stable embedded receipt IDs, deterministic audit document IDs, replay/worker repair; pending flag cleared with version guard | Local repair tests PASS; general-domain receipts and external attempt reconciliation FAIL/unimplemented |
| 5.5 pinning | Automatic policy implementation digest now invalidates local model and speech evidence | Immutable composite release and in-progress call/job pins FAIL/unimplemented |
| 5.6 stop | Live activation remains denied; offline stream reauthorizes/fences/flushes; local utterance output withheld after post-synthesis revocation | Unified native stop/drain/media/tool/transfer/rollback acceptance FAIL/unimplemented |
| 5.7 delivery | No local synthesis, mock transition, Task completion or HTTP success relabelled as customer delivery | Native timestamped acceptance/connection/media/disconnect reducer FAIL/unimplemented |
| 5.8 language | No new language advertised or production-enabled | Actual per-language accents/currency/date/code-switching/STT/TTS/handoff acceptance BLOCKED |
| 5.9 analytics | Mock-only source predicate, creation bounds, source/timezone/as-of/denominator metadata, nonexclusive handled-count explanation and consistent 30s mock heartbeat | Local known-fixture aggregation PASS; actual native event/cohort/reconciliation/retention/alerting FAIL |
| 5.10 migrations | `V/staging_migration.py`, `scripts/voice_staging_indexes.py`: read-only default, isolated DB guard, explicit apply, checksum receipt, repeatability, partial-index recovery, duplicate conflict without deletion | Mock fresh/repeat/partial/conflict/checksum tests PASS; actual staging Mongo/index races and backup/restore BLOCKED |

## E. Preservation verification

| Preservation ID | Verification and boundary |
|---|---|
| 3.1 existing CRM | Existing React/FastAPI/Mongo architecture retained; no sidebar/navigation/theme edits; ordinary Task responses gain an additive version field. Full regression evidence below; no new visual screenshot certification |
| 3.2 user work/data | Baseline hashes, intentional-edit list and no missing files recorded. No blanket restore/destructive Git/data operation; no secret values copied into reports |
| 3.3 workflow order | Canonical managed Tasks/history and existing permission/scoping services reused; no alternate scheduler; mock/synthetic/imported/local speech/live remain distinct |
| 3.4 financial/security | Caller verification and protected execution still denied; exact approved public excerpts/reviewed clarifications only; no arbitrary model tool execution or added tenant architecture |
| 3.5 stop/rollback | All live gates retained; no activation/production action; rollback instructions require retained policy/Task guards. Actual native stop/drain and restore rehearsal BLOCKED |

Existing uncommitted modifications were inventoried before changes and retained.
No destructive Git operation, blanket restore, collection drop, production change,
model download, secret rotation, real call or paid action was performed. Sidebar,
theme/navigation files and unrelated CRM business modules were not edited by this
work. Existing callback Tasks/history remain canonical; new closure is administrative,
never a completed telephone call. Shared audit remains append-only; repair inserts
missing identified events and never overwrites a valid receipt.

The repository is single-company by existing architecture; no tenant IDs or
unreviewed tenant architecture were invented. Existing record/employee scope tests
remain required. Multi-tenant certification is not claimed. Financial tool execution
and caller verification remain denied. No production activation is authorized.

Hash comparison: **1,102 pre-existing non-secret files; 1,072 unchanged, 30 intentionally
edited, none missing**. All five original audit bodies are retained byte-for-byte
beneath current-state notices. The generated tracked tsbuildinfo file was restored
only after verifying its original baseline bytes matched HEAD. The detailed
comparison is `voice-hardening-preservation-2026-10-17.json`. No claim of
screenshot/pixel equivalence is made.

## F. Executed tests and limits

Environment: Windows developer workspace, existing Python venv and frontend
dependencies. API tests use mongomock/fakeredis, synthetic HTTP/speech and temporary
encrypted synthetic artifacts. They are not real Mongo, PBX, models or staging calls.

| Command / scope | Actually observed result |
|---|---|
| Initial targeted intent/smartflo/callback/platform tests | 76 passed, 103 warnings; before subsequent receipt/history additions |
| Extended callback/intent/streaming/policy/platform tests | 93 passed, 2 warnings |
| New staging-migration and metric fixture tests | 4 passed, 1 mock-database warning |
| Intermediate streaming/metric/migration tests | 13 passed, 1 warning; later noncooperative-adapter case verified in final voice run |
| Final full backend `pytest ..\tests --rootdir=.. -c pyproject.toml -p no:cacheprovider -q --tb=short -n 4` | **1,408 passed, 1 skipped, 569 warnings**, 671.68s; final source and fixtures |
| Final all `tests/api/test_voice_*.py`, `--rootdir=.. -c pyproject.toml -p no:cacheprovider -q --tb=short` | **238 passed, 1 skipped, 494 warnings**, 155.78s; Linux-only child cleanup skipped |
| `npm test -- --reporter=dot --maxWorkers=2` | **354 passed, 72 files**; final rerun 125.91s; synthetic jsdom/API contracts |
| `npm run build` | Passed, 409 modules; bundle-size warning remains |
| `npm run lint` | Passed with 10 existing warnings; no errors |
| `python -m ruff check --no-cache . ../scripts/voice_staging_indexes.py` from backend | Passed |
| Scoped mypy `--follow-imports=silent` on dynamic_audio, intent_policy, callback_service, recording_service, staging_migration, conversation | Passed: 6 source files including conversation.py; not a full-project type-check claim |
| `python -m pip check` | No broken requirements; not a vulnerability scan |
| Staging index CLI `--help` | Passed, no DB connection or mutation |
| `docker info`; `docker image ls` | Failed: unavailable daemon and config access denied; no database/container acceptance |
| `wsl --list --quiet` | Failed: access denied; no Linux installation inferred |
| SSH alias discovery | No user/system SSH config found; no host contacted |
| Linux speech child cleanup, actual engines/media, real MongoDB/Redis/PBX, restore/load/security advisory audit | BLOCKED / not executed; no claim of runtime or compliance certification |

Failures encountered and corrected: initial audit fault-injection monkeypatch did
not affect the mock collection, so the test was corrected to inject failure at the
post-domain audit boundary. Import sorting and migration-spec typing errors were
fixed. The first frontend run exposed missing Auth context in Task tests; a proper
Owner mock plus a new explicit-resolution UI test were added. A subsequent default-
concurrency frontend run had timeouts; the complete rerun with two workers passed
without weakened assertions or enlarged timeouts. An initial backend command without
explicit `..\tests` collected no tests; it is not counted as a pass. A sequential
full-backend run was interrupted and replaced by a two-worker run: **1 failed,
1,394 passed, 1 skipped**, 1,241.41s. Its sole failure used the old arbitrary
clarification fixture loaded before its correction; the corrected complete voice
suite passed. The new four-worker full run passed against the final source and fixtures: **1,408 passed, 1 skipped**.
The first full voice run also recorded **1 failed, 229 passed, 1 skipped** for that
same fixture; it is not counted as a successful run.

The public-output contract was deliberately tightened: a model dynamically selects a
relevant approved excerpt and cites it, but cannot invent new factual prose or omit
qualifications. This is not unrestricted generative conversation and is not certified
financial advice. Positive codec/policy fixtures now supply actual matching evidence;
the speech fixture uses a reviewed clarification and asserts its exact synthesis
input. Unsupported assertions remain negative tests rather than accepted outputs.

Warnings remain visible: dependency deprecations, jsdom canvas messages in unrelated
signature tests, intentionally exercised API errors, frontend lint and bundle size.

## G. Deployment, recovery and rollback preparation

No deployment was performed or approved. Before any staging rollout:

1. Review the full pre-existing worktree plus this diff. Obtain isolated staging
   infrastructure and backup/restore evidence. Never use development secrets/data.
2. Keep live gates closed. Preserve Mongo, private audio storage and managed
   encryption keys through the approved backup procedure. Never put their values
   in a report or command-line argument.
3. For isolated callback-index acceptance only, set `VOICE_STAGING_MONGO_URI` in the
   secure process environment and run `python scripts/voice_staging_indexes.py
   --database voice_staging_<approved-name>` read-only. With separate approval and
   restore evidence, add `--apply --backup-reference <non-secret-evidence-id>`.
   This is additive, repeatable and limited to callback indexes; it is not a full
   voice migration or a production migration command. Conflicts stop without data
   repair/deletion. Legacy `service_callback` consent is never mass-converted.
4. Verify actual unique/partial indexes and checksum receipts before starting
   callback review workers. Existing API startup index/catalog behavior remains;
   do not run seeding scripts as read-only inspection. Worker startup itself does
   not supply a verified database migration process.
5. Deploy API/frontend/worker together only through an approved procedure. New
   Task responses include version for Owner CAS resolution. Test ordinary CRM
   login/scopes/Tasks plus callback controls, expired/orphan closure, audit repair
   and private transcript correction/retention before accepting the rollout.
6. If callback audit fails after Task commit, do not create a new request/key.
   Replay the original create or let `reconcile_audit` project the existing embedded
   event. Closed Tasks remain eligible for pending audit repair. Historical events
   without a receipt stay historically unverified; do not fabricate missing events.
7. For rollback, retain the new output policy, managed Task guards and compatible
   receipt/history readers. Do not restore an unguarded speech/text path or delete
   additive fields/indexes/history. Disable affected testing components if a known
   compatible guarded artifact is unavailable. No approved rollback artifact exists
   yet, so production rollback rehearsal remains BLOCKED.
8. Emergency controls keep directions disabled. The platform emergency API and
   simulator disable retain their existing distinct scopes. There is no accepted
   real-call stop/drain procedure until a native runtime exists and passes testing.

Existing configuration names only: `VOICE_NATIVE_ALLOWED_ORIGINS`,
`VOICE_LOCAL_AI_ENABLED`, `VOICE_LOCAL_AI_URL`, `VOICE_LOCAL_AI_MODEL`,
`VOICE_LOCAL_AI_ALLOWED_ORIGINS`, `VOICE_RECORDINGS_DIR`, `VOICE_SPEECH_ROOT`,
`VOICE_SPEECH_PROFILES`, `VOICE_SPEECH_TIMEOUT_SECONDS`, `VOICE_SPEECH_THREADS`,
`VOICE_SPEECH_MEMORY_LIMIT_MB`, `MONGO_URI`, `MONGO_DB_NAME`, `REDIS_URL`,
`ENCRYPTION_KEY`, `JWT_SECRET_KEY`. The new isolated CLI uses
`VOICE_STAGING_MONGO_URI` only and does not load CRM environment files.

## H. Acceptance matrix and final readiness verdict

| Existing matrix group | Current evidence / target gate |
|---|---|
| A configuration | Existing Owner, secret, version and unconditional activation-denial tests retained; actual approved PBX/number BLOCKED |
| B calls | Existing mock lifecycle tests retained; actual inbound/outbound FAIL |
| C knowledge | Clarification assertions now denied; console/current-publication tests retained; complete-excerpt support tested; unrestricted paraphrases withheld; real financial/adversarial model acceptance BLOCKED |
| D speech | Offline stream shares policy/fences; actual installed Linux/media acceptance BLOCKED |
| E identity/tool | Structural denial retained; approved trusted caller/tool flow BLOCKED |
| F callback creation | Existing canonical Task/preview/confirmation/idempotency tests retained; actual voice-origin source binding FAIL |
| G callback recovery | New lifecycle/expiry/Owner resolution/receipt tests; actual DB/dispatch/cancel races BLOCKED |
| H consent/campaign | Exact callback contract and historical non-conversion tested; actual contact-window/network eligibility BLOCKED |
| I handoff | Old-turn/cancellation tests improved; actual bridge/acceptance/fallback FAIL |
| J artifacts/history | Encrypted correction retention/deletion tested; real capture and complete revision/archive policy BLOCKED |
| K analytics | Known mock fixtures and explicit provenance; real source events/capacity/alerts FAIL |
| L releases | Policy hash invalidation and hard denial retained; composite releases/pins/approved rollback FAIL |

Proven: the local behaviors and checks explicitly recorded above. Unproven: actual
call control, bidirectional media, trusted caller verification/tools, release
pinning, production emergency drain, real database/crash behavior, language quality,
backup restore and measured capacity. Production gates A–F are not passed.
**NOT COMPLETE. NOT PRODUCTION READY. Production activation is not authorized.**
