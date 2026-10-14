# Advanced voice batch API and migration notes

All paths are under the configured API prefix (default `/api/v1/voice-assistant`).
JSON uses the existing `ApiResponse` envelope. These are actual registered CRM
routes, not third-party telephony endpoint names. Authentication is the existing
bearer session; scopes remain company-wide knowledge and creator-private calls.
Owner bypass and existing permission engine behavior are preserved.

## Campaign eligibility extensions (14 October continuation)

These routes never call a telephony adapter. Test/production campaign modes return
403, regardless of submitted credentials. Dry-run decisions are persisted data,
not synthetic carrier outcomes. Actor scope reuses existing Customer View and
application assignment rules. Owner manages policy attestations separately.

| Route | Authorization / contract |
|---|---|
| `GET /campaigns?page=1` | campaigns View; 25 rows, creator scope for employees |
| `POST /campaigns` | campaigns Create; strict CampaignInput, dry_run only |
| `PUT /campaigns/{id}` | campaigns Edit; current version, editable state; active import/worker leases prevent editing |
| `POST /campaigns/{id}/actions` | campaigns Edit; version plus validate/start/pause/resume/cancel/archive; start/resume mean dry-run processing only |
| `GET /campaigns/{id}/recipients?page=1` | campaigns View; customer scope checked again, lease tokens excluded |
| `POST /campaigns/{id}/recipients` | campaigns Import; current version, unique idempotency key and up to 500 existing customer references |
| `POST /campaigns/{id}/recipients/import` | campaigns Import; CSV multipart file/version/idempotency_key; 5 MB, 500 rows per batch; exact customer_id and optional timezone columns |
| `POST /campaigns/{id}/preview?page=1` | campaigns View; current eligibility, calls_placed=0 |
| `GET /contact-policies/{customer_id}` | Owner; existing customer required |
| `PUT /contact-policies/consent` | Owner; purpose-specific grant/withdrawal, expiry with offset and evidence reference; operator attestation only |
| `PUT /contact-policies/suppression` | Owner; global or campaign scope, CAS version and reason |
| `POST /campaign-controls/emergency` | Owner; stopped plus reason; pauses running/ready campaigns; clearing does not resume campaigns |

CampaignInput additionally accepts scheduled_at (offset required), timezone,
calling_start/end, holidays, dst_fold, maximum_attempts and frequency_hours.
The first UI batch exposes name/purpose/objective/timezone; advanced scheduling
fields currently require the API. Same-day windows only; nonexistent local DST
times are rejected and ambiguous callback conversion requires an explicit fold.
10,000 unique recipients is a configured limit, not a measured capacity claim.

Additive collections: voice_campaigns, voice_campaign_recipients,
voice_campaign_imports, voice_contact_consents, voice_contact_suppressions,
voice_contact_policy_events, voice_campaign_controls. Startup creates recipient,
import and contact-policy unique indexes plus processing indexes. Existing data is
preserved; no automatic employee grants. Existing installations with conflicting
duplicates require operator-reviewed repair before index creation; never drop
production indexes to make a migration succeed.

Worker process_voice_campaign_previews runs every 15 seconds, up to four campaigns
and 50 recipients each per sweep. Reservations have 30-second leases, unique
tokens, retry bounds and expiry fences. This is dry-run recovery, not idempotent
live carrier dispatch. CSV imports use a separate 120-second campaign lease and
durable receipts; retry interrupted imports with the same key and identical data.
Completed imports are replayed; changed data using the same key is rejected.
Rejected capacity imports do not leave an unrecoverable pending receipt.

Policy changes retain the latest 100 history entries atomically on the policy
record and append separate audit/events. Long-term event retention and independent
consent verification are outstanding operational requirements. No SMS preference
is treated as voice consent. Dry-run evaluation never updates last_contact_at.

## Training extensions (continued)

| Route | Permission and contract |
|---|---|
| `POST /knowledge/import` | knowledge Create; multipart `file`, `title`, `language`; 5 MB, TXT/CSV/DOCX/XLSX only; returns draft with source metadata; 5 requests/minute |
| `POST /knowledge/{id}/evaluations` | knowledge Edit; `{version, cases:[{question,required_facts,expect_evidence}]}`; 1–20 bounded cases; persisted literal evidence checks; 10/minute |
| `GET /knowledge/{id}/evaluations` | knowledge View; latest 10 authorized reports, no secret/provider response |
| `POST /knowledge/{id}/actions` | knowledge Approve; existing actions plus `rollback_published`, with current `version` and retained `target_version` |

Imported documents require a passing, fingerprint-matching evaluation with a
positive evidence case before review-state publication. Negative-only suites cannot
authorize release. Reports explicitly say semantic groundedness/injection resistance
are not evaluated. Manual article publication remains backward compatible with the
existing review/approve process. Rollback-to-draft never activates unapproved content.
`rollback_published` activates only retained approved snapshots; expired publications
are rejected. Editing preserves the active snapshot; archiving withdraws it.

No HTTP URL ingestion, PDF/OCR, malware scanner, semantic embedding or model-weight
training is enabled. Original uploaded bytes are not retained. UI content is escaped
text; source instructions do not override immutable conversation policy.

## Recording artifact extensions

| Route | Permission and contract |
|---|---|
| `GET /recordings` | recordings View; `page`, `status`, `call_id`, timezone-aware `since`/exclusive `until`; 25/page; storage/live-capture status |
| `POST /recordings/import` | recordings Create; multipart `file`, `call_id`, `idempotency_key`, `consent_reference`, `retention_days` 1–365; WAV ≤20 MB; call must be ended and accessible; 5/minute |
| `GET /recordings/{id}/audio` | recordings View plus call access; rechecks expiry/status/integrity; authenticated WAV bytes with `private,no-store`, optional single byte Range (206/416) |
| `GET /recordings/{id}/audio?download=true` | also recordings Download; never a public or token-bearing URL |
| `PUT /recordings/{id}/transcript` | recordings Edit; current version, language, recognizer label, ≤500 time-ordered segments/50,000 characters within actual audio duration |
| `GET /recordings/{id}/transcript` | recordings View and accessible unexpired artifact; decrypted recognized segments, explicit operator-supplied provenance; no generated summary |
| `POST /recordings/{id}/recover?version=N` | recordings Edit; only failed/interrupted unexpired import; valid durable encrypted artifact required; active processing lease blocks recovery |
| `DELETE /recordings/{id}?version=N` | recordings Delete; current version; playback disabled first, artifact/derivative deletion verified; failures remain pending for worker retry |

Import key scope is importing user plus key. A changed call/audio/consent/retention
request with the same key conflicts. A replay returns persisted status (which may
still be pending/failed), never fabricated completion. Display duration comes from
validated audio, not browser inputs. `origin=imported_artifact` and call provider
remain visible, so a recording attached to a simulation cannot masquerade as a
captured real call. Consent evidence is operator-attested, not legal certification.

Storage is disabled without `VOICE_RECORDINGS_DIR`. Encrypted artifacts are outside
Mongo/static roots; playback authenticates through the existing token/refresh client
and uses ephemeral browser blob URLs. URLs are revoked when the detail unmounts.
Transcript text is encrypted in the same parent mutation; metadata list responses
use an allowlist and never expose ciphertext, hashes, keys, paths or transcript text.

## Additive data changes and rollback

Existing `voice_knowledge` gains optional source metadata, publication snapshot and
up to 20 retained approved publications. Existing revision history still retains
20 entries. Legacy records are readable without bulk conversion; first revision
preserves an existing approved release. `voice_knowledge_evaluations` gains the
article/time index and bounded evidence reports.

New `voice_recordings` holds call-linked metadata, processing status, actual WAV
metadata, retention, version and bounded encrypted transcript derivatives.
Indexes: unique `(owner_user_id,idempotency_key)`, `(call_id,created_at)`,
`(call_owner_user_id,created_at)` and `(status,expires_at)`. There is intentionally
**no TTL index on recordings**: deleting metadata before file removal would orphan
private artifacts. The retention worker verifies deletion first and leaves an audit
tombstone. No duplicate call/customer/tenant collection is introduced.

`voice_worker_health` gains the `recordings` heartbeat/failure row. Shared audit logs
record artifact import/access/download/transcript/deletion/recovery by record ID;
audio/text/credentials/paths do not enter ordinary audit metadata. Existing catalog
gains the recordings resource with View/Create/Edit/Download/Delete, without grants.
Normal startup and targeted catalog script ensure additive indexes/catalog.

Rollback: disable new imports, preserve metadata/encrypted artifacts/keys, revert
package/frontend and restart API/worker. Do not drop collections/optional fields.
Maintain a compatible cleanup job until retained artifacts expire; rolling back to
older workers otherwise stops retention. Legacy code cannot display approved
publication snapshots while an article is draft, so rollback may change retrieval
availability; review before release. Refer to the operations runbook for private
volume, key/backup retention and actual activation prerequisites.
