# Lead Capture (Module 9B)

Part of Module 9 — External Integrations, the second of 4 sub-modules (9A API Management → **9B Lead Capture** → 9C Communication → 9D Future Integrations), each depending on the previous.

## Scope

Turning an inbound Website form submission, a Meta Lead Ads webhook notification, or a staff-triggered manual import into a real Module 6A `Lead` — never a new Lead-creation code path, never a change to Module 6A itself.

## The shared pipeline

```
Webhook / Form / Manual API
        ↓
   Provider-specific Parser  (parsers.py / meta_client.py)
        ↓
   Source Mapping  (capture_sources → lead_sources)
        ↓
   LeadService.create_lead()  (Module 6A, frozen, unmodified)
        ↓
   Timeline entry + idempotency receipt
```

One function, `LeadCaptureService._process_raw_payload`, is the pipeline itself — Website form, Meta webhook processing, and the retry queue all call it identically. A future capture source (Google Forms, Facebook, a partner API) needs only a new parser function; the pipeline, validation flow, and failure handling stay the same (decision 097).

## Capture sources

### Website Lead Capture

`POST /lead-capture/website` — public, rate-limited (20/min per IP). The request schema is deliberately lenient (all fields optional at the Pydantic level) so a malformed submission still reaches the service layer and gets logged as a `CaptureFailure`, rather than a bare, unrecorded HTTP 422 (per explicit instruction: "never lose inbound requests"). The service itself checks for required fields and a valid Indian mobile number, logging `missing_required_fields`/`invalid_data` before returning 422.

### Meta Lead Ads

A real, working webhook integration:

- `GET /lead-capture/webhooks/meta` — Meta's own verification handshake. Echoes `hub.challenge` back if `hub.verify_token` matches the active Meta `IntegrationConfig`'s `webhook_verify_token` (Module 9A).
- `POST /lead-capture/webhooks/meta` — the leadgen notification. Verifies `X-Hub-Signature-256` via HMAC-SHA256 (`hmac.compare_digest`, constant-time) against the active config's `webhook_secret`; 403 immediately on mismatch. Once verified, always returns 200 (Meta's own ack contract) regardless of per-entry outcomes.
- For each `leadgen_id` in the notification, a real, live call to Meta's Graph API (`GET /{leadgen_id}?fields=field_data`, using the config's `access_token`) retrieves the lead's actual field values — the webhook notification itself only carries a reference, not the data (decision 100).
- Idempotent: a `CaptureReceipt` (per `leadgen_id`) prevents a retried webhook delivery from creating a duplicate Lead (decision 101).
- Field name mapping (`meta_client.parse_field_data`) recognizes `full_name`/`name`, `phone_number`/`phone`, `email` — see `docs/KNOWN_LIMITATIONS.md` for what happens with non-standard form field names.
- Meta payloads carry no product information — `CaptureSource(key="meta_lead_ads").default_product_category`/`default_product_id` supplies it; unset, an incoming Meta lead is logged as `missing_required_fields`.

### Manual API

`POST /lead-capture/manual` — authenticated, `require_permission("lead_capture", "captures", "create")`. Strictly validated (no `CaptureFailure` on a bad request — the authenticated caller just fixes and resubmits). A single-lead, controlled-import endpoint, not a bulk/CSV importer.

## The system actor (no human in the loop)

Website and Meta captures have no authenticated human — but `LeadService.create_lead` requires a real, persisted `User`. `LeadCaptureService._system_actor()` fetches any real Owner (the same precedent Module 6B's `CustomerService._any_owner()` established for direct-portal registration, decision 053/098), and the resulting Lead's `created_by` is nulled out immediately afterward so it never looks like that Owner personally created it. The real provenance — which capture source, which external id — is recorded on the Lead's own Timeline via a new `LeadActivity(event_type="captured")` row (`event_type` is a free-form field on the frozen `LeadActivity` model, not a closed enum, so this needed no change to Module 6A).

## Capture Failures & the Retry Queue

Every capture that doesn't become a Lead is recorded in `capture_failures` — `duplicate`, `invalid_data`, `missing_required_fields`, or `api_error`. Only `api_error` (a transient/technical condition, e.g. Meta's Graph API being briefly unreachable) is retried automatically: a 15-minute Arq cron job (`retry_capture_failures`) re-attempts through the exact same shared pipeline, with exponential backoff (15 min × 2^attempt), giving up as `exhausted` after 5 attempts. The other three reasons are permanent — a human needs to fix the source data — and are logged as `ignored`, never retried automatically. A manual "Retry Now" (`POST /lead-capture/failures/{id}/retry`) is also available (decision 099).

## Source Mapping

`capture_sources` (seeded: `website_form` → "Website", `meta_lead_ads` → "Meta", `manual_api` → "Manual" — resolving Module 6A's own seeded Lead Source names) is Owner-remappable via `PATCH /lead-capture/sources/{key}`, never hardcoded (decision 102).

## Permissions

Three narrow resources, each independently grantable: `lead_capture:captures` (create — manual import), `lead_capture:sources` (view/edit — Source Mapping), `lead_capture:failures` (view/edit — Capture Failures + retry).

## Frontend

One combined admin page (`/lead-capture`): Source Mapping (per-channel product defaults), a Manual Capture form, and a Capture Failures table with a "Retry Now" action.

## Reserved for the future (decision 103)

Three additions folded in at the freeze review, all explicitly "reserve, don't implement now":

- **`webhook_events`** — a model only (`WebhookEvent`), zero call sites. Would record *every* inbound webhook event (not just failures) for future observability.
- **Lead Source Metadata** — `ParsedLead.source_metadata` passes through whatever campaign/ad set/ad/form identifiers a source's raw payload happens to carry (`parsers.py:extract_source_metadata`), recorded on the Lead's own Timeline. Never fabricated when a source doesn't supply one.
- **Website Form Version** — `WebsiteCaptureRequest.form_version` (plus `utm_source`/`utm_campaign`/`utm_medium`), fed into the same passthrough.

No Campaign/ROI reporting exists on top of this data yet — that would be a future Reports & Analytics addition.

## Known limitations / assumptions

See `docs/KNOWN_LIMITATIONS.md`'s Module 9B section.
