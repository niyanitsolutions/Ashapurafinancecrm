# Communication Engine (Module 9C)

Part of Module 9 — External Integrations, the third of 4 sub-modules (9A API Management → 9B Lead Capture → **9C Communication** → 9D Future Integrations), each depending on the previous.

## Scope

A centralized send engine — not a second notification system (Module 6D already owns in-app notifications/reminders) and not an integration system (Module 9A already owns provider credentials). Channels: WhatsApp, SMS, Email only. No Push Notifications, no marketing module. Originally shipped with no campaign builder, no bulk messaging, and no manual "send now" endpoint — Stage 3 of the Geo Fencing/Temporary Permissions/MSG91 request added exactly these three (see the dedicated Stage 3 section below), still scoped to WhatsApp/SMS/Email only.

## Architecture

```
Business Module (Leads / Customer / Workflow Engine / Reminders / Referral Partner Management)
        ↓  (via its own existing audit_logs entry — no direct call)
   Business-event poller  (CommunicationService.poll_business_events, Arq cron, every 2 min)
        ↓
   Communication Service — enqueue (renders an Owner-authored template)
        ↓
   Communication Queue  (pending → processing → sent/failed/retrying → exhausted)
        ↓
   Provider Adapter  (app/features/communication/adapters.py)
        ↓
   Provider  (Module 9A's active IntegrationConfig for the channel)
        ↓
   Communication History  (one row per queue item's terminal outcome, never overwritten to blank)
```

No business module is ever modified to call this engine directly (decision 104). The poller reads the exact same append-only `audit_logs` collection Module 6D's own notification engine already reads (decision 065) — a small, fixed set of 5 named business events, never a new event type.

## Business events consumed

| Business event | Audit `event_type` scanned | Recipient resolution |
|---|---|---|
| `lead_assigned` | `lead_assigned` (Leads) | The assigned Employee (`employee_id` in the audit metadata → `Employee.mobile`/`.email`) |
| `reminder_triggered` | `notification_created` (Reminders), filtered to `metadata.notification_type == "reminder_triggered"` | Whoever 6D's own Notification was created for (the audit log's `user_id`) — resolved via the user's own role (Employee/Customer/ReferralPartner/Owner) since email isn't stored on the shared `users` collection itself |
| `application_submitted` | `application_submitted` (Customer) | The Customer who owns the Application (`Application.user_id` → `Customer.find_by_user_id`) |
| `document_requested` | `workflow_documents_requested` (Workflow Engine, shared by Loan/Insurance) | The Customer on that case (`ApplicationWorkflow.customer_id`) |
| `commission_ready` | `commission_entry_created` (Referral Partner Management) | The Referral Partner (`entry_id` → `CommissionEntry.partner_id` → `ReferralPartner`) |

Each event fans out to every channel the recipient has a contact method for (mobile → WhatsApp + SMS, email → Email) — but only if an **active** template exists for that (business event's category, channel) pair; otherwise nothing is enqueued for that channel, silently, not an error. Enqueue is idempotent on `(business_event, entity_type, entity_id, channel)` — a poller re-run (or a case that later re-emits the same audit event) never creates a duplicate queue item. A per-business-event checkpoint (`communication_checkpoints`) means each poll run only scans genuinely new `audit_logs` rows, not the whole collection.

## Templates

Owner-authored only — ships with zero seeded rows, the same posture as Module 6D's own Notification Templates (decision 029). Nothing is actually sent for a given business event until the Owner creates a matching `CommunicationTemplate` (Channel + Category + Body, Subject for Email only). `variables` (the `{{name}}`-style placeholders the body references) is derived automatically from the body text, never hand-entered — see `app/features/communication/template_engine.py`. Rendering leaves an unrecognized `{{placeholder}}` untouched rather than raising, so one template author's typo can't take down the whole queue processor.

Categories: `otp`, `welcome`, `lead_assigned`, `reminder`, `application_submitted`, `document_request`, `commission_approved`. **`otp` is reserved only** — OTP delivery is never routed through this engine. Auth (Module 1) is frozen and OTP delivery must stay synchronous (a queued, polled send would arrive far too late to be useful); OTP keeps using its own existing, direct send path (decision 106). This is a deliberate scope exclusion, not an oversight.

## Provider Adapters

One function per channel behind a common interface (`DeliveryOutcome{success, provider_message_id, error, is_transient, response_time_ms}`, `app/features/communication/adapters.py`), reading Module 9A's active, encrypted `IntegrationConfig` for the channel (read-only — never re-implements credential storage):

- **WhatsApp / SMS** — a generic HTTP POST to the config's own `api_url` (Bearer auth). Same honest "no single fixed API contract" limitation 9A's own Test Connection already disclosed for these two open-ended, multi-provider channels (decision 105).
- **Email** — a real SMTP send (`smtplib`, STARTTLS + login if credentials are present) when the active config looks like SMTP (`host` present), otherwise a generic HTTP POST for an API-based provider.

Adding a future provider means adding one more adapter function and registering it in `ADAPTERS` — the queue processor never branches on provider identity, only on channel.

## Queue, retry, and delivery history

Every outgoing communication enters `communication_queue` — nothing is ever sent directly from a request handler. States: `pending → processing → sent/failed/retrying → exhausted` (`delivered` is reserved; no delivery-status webhook exists yet for any of the 3 channels, so nothing sets it or `delivered_at`). Two Arq cron jobs process it: pending items every minute, items due for retry every 5 minutes.

Retry policy (decision 108): only a **transient** failure (adapter-reported network/timeout/5xx-shaped error) retries, with exponential backoff (`5 min * 2^attempt`) up to `MAX_RETRY_ATTEMPTS = 5`, after which the item becomes `exhausted`. A **permanent** failure (e.g. no active integration configured, a clearly invalid recipient) goes straight to `failed` and is never retried automatically. The manual **Retry Action** (`POST /communication/queue/{id}/retry`, staff-only) re-attempts through the exact same send path (`CommunicationService._send_one`) a scheduled worker run would use — no separate code path.

`communication_history` holds one row per queue item's terminal outcome (created once, updated in place on a later transition — e.g. a manual retry that later succeeds) — never duplicated, never overwritten to a blank slate. `provider_delivery_logs` is the append-only record of every individual send *attempt* (distinct from history's one-row-per-final-outcome), the same "keep every attempt" posture as Module 9A's own `integration_test_logs` (decision 096).

## Reserved for the future

- **`communication_preferences`** — a model only (`CommunicationPreference`: `user_id`, `sms_enabled`/`whatsapp_enabled`/`email_enabled`), zero call sites. Per explicit instruction: "prepare for future support... do not implement UI yet." The queue processor does not check it before sending.
- ~~**`delivered` queue status / `delivered_at`**~~ Real as of Stage 2 for MSG91 SMS (see below) — set only by a genuine provider delivery-report webhook, never inferred from a successful send. Still reserved/unset for every other channel/provider (WhatsApp DLR, non-MSG91 SMS, any email provider).
- **`language`** on `CommunicationTemplate` — future-ready field, only `"en"` is ever used today.

## MSG91 (Stage 2 of the Geo Fencing/Temporary Permissions/MSG91 request)

MSG91 is configured through the exact same `integrations` (Module 9A) `IntegrationConfig` storage as every other provider — no new credential store, no schema change. See `docs/architecture/MODULES.md` and `docs/decisions/DECISIONS.md` #113–#116 for the full reasoning. Settings → Communication Providers is a dedicated frontend view over that same data, filtered to `provider == "msg91"`.

- **SMS** — real send via MSG91's Flow API v5 (`POST https://api.msg91.com/api/v5/flow/`), DLT-compliant (chosen over the older, non-templated `v2/sendsms` specifically because DLT registration requires routing through an approved template). Config: `auth_key`, `sender_id`, `flow_id` (the DLT-registered Flow/Template ID), `dlt_entity_id` (stored for reference — not part of the API call itself, per MSG91's own docs). This CRM's own `{{variable}}` order (`CommunicationTemplate.variables`) becomes the positional `VAR1`/`VAR2`/... order MSG91's Flow API expects.
- **WhatsApp** — real send via MSG91's template outbound API (`POST https://api.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/`). WhatsApp Business sends only a pre-approved *provider-side* template, never this CRM's own rendered body text — `CommunicationTemplate` gained 3 new optional fields (`provider_template_name`/`namespace`/`language`) to carry that; a WhatsApp send via MSG91 without them fails cleanly with "Message template is invalid or not approved." rather than guessing. Config: `auth_key`, `integrated_number`.
- **Email** — sends via the **existing, unmodified generic SMTP adapter** (`send_email`'s `host`-present branch). MSG91 issues standard SMTP relay credentials for transactional email (Owner obtains host/port/username/password from MSG91's own dashboard) — no MSG91-specific email code exists, by design, since there's no custom wire format to target (SMTP is a standard protocol). This was independently confirmed as a real MSG91 feature, not assumed.
- **Test Connection** — SMS/WhatsApp validate the `auth_key` via MSG91's balance-check endpoint (`GET https://api.msg91.com/api/balance.php?authkey=...&type=4`, the closest lightweight, non-business-action, authkey-validating call MSG91 offers — it has no dedicated health/whoami endpoint). Email reuses the existing, already-real SMTP connect+STARTTLS+login test, unchanged.
- **Delivery webhook** — `POST /communication/webhooks/msg91?secret=...`, a new public (no-JWT) route, verified by a shared secret (`webhook_secret`, Owner-chosen, stored on the MSG91 config, appended to the URL configured in MSG91's own dashboard) rather than a cryptographic signature — MSG91 does not document an HMAC webhook-signing scheme. Idempotent on `requestId` (→ `provider_message_id`): a duplicate or out-of-order callback is a safe no-op, and a `sent` item is only ever advanced to `delivered`/`failed` once (never regressed). Only the **SMS** delivery-report payload shape (`requestId`, `status` numeric code, `telNum`, `deliveryTime`) is confirmed against MSG91's own documentation; a WhatsApp DLR callback is not parsed by this endpoint yet — see `docs/KNOWN_LIMITATIONS.md`.
- **Error messages** — MSG91's raw error responses are mapped onto the spec's own required shapes ("Unable to authenticate with the communication provider.", "Provider rate limit reached. Message will be retried.", "Invalid recipient.", "Message template is invalid or not approved.") rather than ever surfacing a raw provider response/stack trace.
- **Not live-verified** — no real MSG91 account/credentials exist in this environment, consistent with every other provider in this codebase (Meta, SMTP, Google Maps). Every adapter/tester/webhook code path is real, working code, exercised only via mocked/monkeypatched responses in `tests/api/test_msg91.py` — never against MSG91's actual servers.

## Stage 3 — Bulk Messaging + CRM Record Linkage

### Generalized `send_now()`

The one pre-existing "send right now, not via the poller" path (used by the Secure Application Link "Share"/"Notify Customer" buttons) gained `entity_type`/`entity_id` (now required) and a `template_id` alternative to `category` (an Owner/staff member picking an exact template, not a business-event-driven category lookup). Returns `(success, queue_item_id, error_message)` instead of a bare `bool`, so a caller that needs the real failure reason (Send Message does; `notify_secure_link` still only needs the boolean) can show it. `notify_secure_link` (customer/service.py, the one pre-existing caller) now passes `entity_type="lead", entity_id=lead.require_id()` instead of the old fixed `"secure_link"` placeholder with no real id — a secure-link share now shows up in the Lead's own Messages panel.

### Individual "Send Message" (Lead / Customer)

`POST /communication/messages` / `GET /communication/messages?entity_type=&entity_id=`. The recipient address is **always** resolved server-side from the authorized Lead/Customer record itself — the request never carries a raw phone number/email, closing the "forged recipient" IDOR angle entirely. Authorization is two-layered, mirroring each frozen module's own existing rule instead of inventing a new one:

- **Lead** — `communication:send:create` (the feature-level gate) **and** the exact same assignment rule `LeadService.get_lead_scoped` already enforces (Owner bypasses; a non-Owner Employee must be the Lead's own `assigned_to`).
- **Customer** — `communication:send:create` **and** the exact same rule `CustomerService.get_customer_for_staff` already enforces (Owner bypasses; a non-Owner Employee must have an `Application` assigned to them for that Customer).

Both rules are independently re-implemented (not imported) inside `CommunicationService` — `customer.service` already imports `CommunicationService` (the secure-link flow), so importing `CustomerService`/`LeadService` back would risk a circular import. Documented as a "keep in sync manually" duplication, the same tradeoff this codebase already accepts elsewhere for a handful of small, stable invariants.

### Bulk Messaging

`POST /communication/bulk-messages` creates a `BulkMessageJob` — `recipient_ids` are resolved by the **caller** (the Bulk Messages composer reuses the existing, already-authorized `GET /leads`/`GET /customers` staff search endpoints; no new filter-query engine, no change to Leads/Customers) and deduplicated once at creation. The job itself is never sent synchronously: a worker-driven Arq cron (`process_bulk_message_jobs`, every minute) does the actual per-recipient enqueue in batches of `BULK_ENQUEUE_BATCH_SIZE` (100), persisting a resumable cursor (`next_index`) after every batch — a worker restart mid-job simply resumes from the last completed batch. Idempotency is the same `(business_event, entity_type, entity_id, channel)` dedup check `_enqueue` already uses for the business-event poller, scoped to the job via a synthetic `business_event=f"bulk:{job_id}"` — a re-processed batch (worker restart, or the same tick running twice) never double-enqueues. Once enqueued, every item flows through the **existing, unmodified** `process_pending_queue`/`process_retry_queue` cron jobs — bulk messages get the exact same retry/backoff/exhaustion behavior as every other message, no separate logic. A recipient with no contact method for the chosen channel (or a template deleted mid-job) is skipped, not a job-level failure — `BulkMessageJob.skipped_count` tracks this, `queued_count` tracks real enqueues, and live `sent`/`delivered`/`failed`/`pending` counts are computed on read from the queue/history, never stored redundantly on the job.

Bulk messaging is **not** per-recipient IDOR-scoped the way individual Send Message is — a "Selected Leads"/"Filtered Leads" campaign is inherently a cross-assignment, feature-level action, gated by `communication:bulk:create` alone (Owner bypasses; a delegated role needs this permission granted explicitly). This is a deliberate, documented choice, not an oversight — see `docs/decisions/DECISIONS.md`.

### CRM record linkage

Every message a Lead/Customer detail page's own "Messages" panel shows comes from `GET /communication/messages?entity_type=&entity_id=`, reading `communication_queue` directly (not `communication_history`, which only exists once an item reaches a terminal state — the panel needs to show `pending`/`processing` items too). The same IDOR scoping as sending applies to viewing.

## Permissions

`communication:templates` (view/create/edit — authoring), `communication:queue` (view/edit — Queue, Failed Messages, Retry Action), `communication:history` (view — Delivery History), `communication:send` (view/create — Stage 3's individual Send Message + a record's Messages panel), `communication:bulk` (view/create/edit — Stage 3's Bulk Messaging; edit covers cancel/retry-failed). MSG91 provider configuration itself is gated by `integrations:configs`, unchanged.

## Frontend

Message Center (`/communication`) now has four tabs: Template Management (WhatsApp templates now also carry an optional MSG91 provider-template name/namespace/language), Queue & Failed Messages (per-item Retry Now), Delivery History, and **Bulk Messages** (Stage 3 — compose a bulk send by searching/selecting Leads or Customers, view past jobs' progress, View Failed, Retry Failed, Cancel). Settings → Communication Providers (`/settings/communication-providers`) is the MSG91-specific configuration view described above. Lead and Customer detail pages each gained a "Send Message" header button and a "Messages" panel (both `frontend/src/features/communication/components/{SendMessageModal,MessagesPanel}.tsx`, reused as-is by both entity types).

## Known limitations / assumptions

- Recipient resolution and the fan-out-to-every-available-channel behavior (WhatsApp + SMS for a mobile number, Email if an address is on file) are this module's own design choice, not spelled out verbatim in the brief — documented here since it wasn't specified.
- A dangling reference in an old audit-log row (e.g. an Employee later deleted) is silently skipped by the poller, not retried or logged as a failure — there is nothing to send to.
- MSG91 WhatsApp delivery-report webhook field names were not independently confirmed against official documentation in this environment — the webhook endpoint currently only parses the (confirmed) SMS shape. A WhatsApp DLR callback using different field names is safely ignored (treated as a malformed/unrecognized payload), not mis-parsed.
- The MSG91 balance-check endpoint used for Test Connection's exact success/failure response body was not independently confirmed against a live account — classification is by HTTP status code only, the same conservative approach the pre-existing generic WhatsApp/SMS testers already use.
- See `docs/KNOWN_LIMITATIONS.md`'s Module 9C and Module 10 (MSG91) sections for the rest.
