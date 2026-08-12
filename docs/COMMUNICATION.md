# Communication Engine (Module 9C)

Part of Module 9 — External Integrations, the third of 4 sub-modules (9A API Management → 9B Lead Capture → **9C Communication** → 9D Future Integrations), each depending on the previous.

## Scope

A centralized send engine — not a second notification system (Module 6D already owns in-app notifications/reminders) and not an integration system (Module 9A already owns provider credentials). Channels: WhatsApp, SMS, Email only. No Push Notifications. No campaign builder, no bulk messaging, no marketing module, no "send now" endpoint.

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
- **`delivered` queue status / `delivered_at`** — fields exist, nothing sets them yet; would need a delivery-status webhook from a real provider.
- **`language`** on `CommunicationTemplate` — future-ready field, only `"en"` is ever used today.

## Permissions

Three narrow resources, each independently grantable: `communication:templates` (view/create/edit — authoring), `communication:queue` (view/edit — Queue, Failed Messages, and the Retry Action), `communication:history` (view — Delivery History).

## Frontend

One combined admin page (`/communication`): Template Management, Queue & Failed Messages (with per-item Retry Now), and Delivery History — three tabs, no campaign builder, no bulk messaging.

## Known limitations / assumptions

- Recipient resolution and the fan-out-to-every-available-channel behavior (WhatsApp + SMS for a mobile number, Email if an address is on file) are this module's own design choice, not spelled out verbatim in the brief — documented here since it wasn't specified.
- A dangling reference in an old audit-log row (e.g. an Employee later deleted) is silently skipped by the poller, not retried or logged as a failure — there is nothing to send to.
- See `docs/KNOWN_LIMITATIONS.md`'s Module 9C section for the rest.
