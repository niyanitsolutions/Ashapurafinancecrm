# External Integrations (Module 9)

Split into 4 sub-modules per explicit instruction, each depending on the previous — no sub-module starts until the previous one is explicitly approved:

```
Module 9A → API Management
    ↓
Module 9B → Lead Capture
    ↓
Module 9C → Communication
    ↓
Module 9D → Future Integrations
```

This document covers **9A only** (configuration/management). 9B (Lead Capture, `docs/LEAD_CAPTURE.md`) and 9C (Communication Engine, `docs/COMMUNICATION.md`) are built and consume this module's stored, encrypted `IntegrationConfig` read-only — neither modifies `features/integrations`. 9D is not yet built.

## 9A — API Management

**Scope, precisely:** the integration *management* platform — configuration storage, encryption, masking, Enable/Disable, Test Connection. **Not built here:** sending a WhatsApp message, fetching a Meta lead, sending an SMS, sending an email. Those are 9B/9C's job; they will read the configuration this module stores.

### Why a new module, not an extension of System Settings

Module 4's `system_settings.ApiSetting` already stores an encrypted config blob per `(provider, label)` — it was explicitly built with Meta/WhatsApp/SMS/SMTP/Maps credentials in mind (decision 028). But it's frozen, and it lacks concepts this module needs: an Active-per-type configuration, Test Connection with a result history, and Last Tested/Success/Failure tracking. The freeze policy (decision 031) disallows repurposing a frozen collection for a new meaning — so `features/integrations` is wholly new and additive (decision 091). `ApiSetting` itself is untouched.

### Data model

**`IntegrationProvider`** (seeded catalog, `integration_providers`) — which `(integration_type, provider)` pairs are known/offered:

| integration_type | provider | label |
|---|---|---|
| `meta` | `meta` | Meta (Facebook/Instagram) |
| `whatsapp` | `whatsapp_business_api` | WhatsApp Business API |
| `sms` | `generic_sms` | Generic SMS Provider |
| `email` | `smtp` | SMTP |
| `email` | `email_api` | Email API Provider |
| `maps` | `google_maps` | Google Maps |

Adding a future provider (e.g. a second WhatsApp provider) is one new seeded row — never a code change (decision 095).

**`IntegrationConfig`** (`integration_configs`) — a *named*, independently-credentialed instance:

- `integration_code` (`AFS-INTG-000001`), `integration_type`, `provider`, `name` ("Meta Production", "WhatsApp Test", ...)
- `config_encrypted` — the entire provider config dict, encrypted as one blob (`app.security.encryption`, unmodified)
- `is_enabled` — ready to use; `is_active` — the single config currently live for its `integration_type` (decision 092)
- `last_tested_at` / `last_success_at` / `last_failure_at` / `last_error_message`
- `health_status` — reserved, not implemented (decision 096): a future Healthy/Warning/Error operational view, derivable from the `last_success_at`/`last_failure_at` fields above. No code reads or writes it yet.

An Owner can create multiple named configs per type ("Meta Production", "Meta Sandbox") and switch which one is Active without deleting the others — useful for provider migration, testing, and future tenant-specific configuration.

**`IntegrationTestLog`** (`integration_test_logs`) — append-only history of every Test Connection attempt (`success`, `response_time_ms`, `error_message`, `tested_at`). Kept permanently by design (decision 096) — no TTL, no pruning, no delete endpoint — so questions like "why did Meta stop working," "when did SMTP last fail," or "how often is WhatsApp unavailable" stay answerable over time.

### Config fields per integration type (frontend-rendered, not server-schema-enforced)

The backend stores `config` as a flexible `dict[str, str]` — no per-provider schema is validated server-side (same philosophy as `ApiSetting`, decision 028: provider shape varies too much to hardcode). The frontend (`frontend/src/features/integrations/providerFields.ts`) renders the fields named in the brief:

| Type | Fields |
|---|---|
| Meta | App ID, App Secret*, Access Token*, Webhook Verify Token*, Webhook Secret* |
| WhatsApp | API URL, Access Token*, Phone Number ID, Business Account ID |
| SMS | API URL, API Key*, Sender ID |
| Email (SMTP) | Host, Port, Username, Password*, TLS/SSL, From Name, From Email |
| Email (API-based) | API Key*, API URL (optional), From Name, From Email |
| Google Maps | API Key*, Geofencing Enabled |

`*` = secret — encrypted, masked to its last 4 characters in every API response, never returned in full. A key is treated as secret purely by naming convention (`app/features/integrations/constants.py:is_secret_key` — contains "secret", "token", "key", or "password") — no schema needed, and every literal secret field above matches it.

### Test Connection

Never a business action — no message is sent, no lead is fetched (decision 094):

- **Meta** — a real, live, read-only call to the Graph API's `/me` endpoint.
- **Google Maps** — a real, live Geocode API call for a fixed test address.
- **WhatsApp / SMS / API-based Email** — a generic HTTP reachability check against the stored API URL (these are open-ended, multi-provider by design, so there's no fixed contract to authenticate against more deeply).
- **SMTP Email** — a real connection + `STARTTLS` (if enabled) + login handshake via Python's standard `smtplib`, then disconnects without sending any mail.

Every attempt updates the config's own `last_*` fields and appends an `IntegrationTestLog` row.

### Security

- Encryption: `app.security.encryption.encrypt`/`decrypt` — Fernet, key derived from `JWT_SECRET_KEY` (Foundation's own known placeholder-key limitation, unchanged by this module — see `docs/KNOWN_LIMITATIONS.md`).
- Masking: last-4-characters-visible, same convention as Employee's bank account masking (decision 018) — never the full secret, in any response, ever.
- Updating a config's `config` merges into the existing decrypted dict rather than replacing it — rotating one secret never requires resupplying the others.

### Permissions

Every endpoint is `require_permission("integrations", "configs", action)` — real, Owner-delegable Access Control, reusing the existing platform (not a bespoke role check). Actions: `view`, `create`, `edit`.

### API

See `docs/api/API.md`'s Module 9A section for the full endpoint list.

### Frontend

Exactly the 5 pieces scoped — no webhook setup screens:
- **Integration List** (`/integrations`) — grouped by type, with an Add Configuration form driven by the live provider catalog.
- **Integration Details** (`/integrations/:configId`) — status, Enable/Disable, Set Active, Test Connection, an edit form for the config fields, and test history.

### Known limitations / assumptions

See `docs/KNOWN_LIMITATIONS.md`'s Module 9A section.

### Consumers

- **9B (Lead Capture)** reads the active `meta` config (`access_token`, `webhook_verify_token`, `webhook_secret`) to verify and process the Meta Lead Ads webhook. See `docs/LEAD_CAPTURE.md`.
- **9C (Communication Engine)** reads the active `whatsapp`/`sms`/`email` config to actually send a queued message via its Provider Adapter (`app/features/communication/adapters.py`) — the first place these three config types are used for a real send, rather than only Test Connection. See `docs/COMMUNICATION.md`.
- **Communication Providers (Settings, Stage 2 of the Geo Fencing/MSG91 request)** is a dedicated frontend page (`/settings/communication-providers`) over this exact same `IntegrationConfig` storage/API, filtered to `provider == "msg91"` — not a new backend feature. `msg91` is now a seeded `IntegrationProvider` row for all 3 channels (`scripts/seed.py`). See `docs/COMMUNICATION.md`'s own MSG91 section.
