# Architecture

## Layers (Clean Architecture)

Every backend feature module follows the same layering, so business logic never lives in a route handler and never lives in the UI:

```
router.py     — Presentation: HTTP concerns only (parsing, status codes, calling the service)
service.py    — Business logic: the actual rules, orchestration, validation beyond shape
repository.py — Data access: Mongo queries, built on shared/base_repository.py
models.py     — Domain/persistence models (Pydantic, extends shared/base_document.py)
schemas.py    — Request/response DTOs (what the API actually accepts/returns)
```

The frontend mirrors this per feature: a `features/<name>/` folder holds its own components, hooks, and API calls — no feature reaches into another feature's internals; shared UI lives in `components/`, shared state/query logic in `shared/`.

## Backend Structure

```
backend/app/
├── main.py            — app factory: middleware, routers, exception handlers
├── config/            — env-driven settings, split by concern (database, redis, security, storage)
├── constants/          — stable keys (roles, permission-key format, API prefix, theme colors)
├── middleware/          — auth, logging, cors, rate_limit, request_id
├── security/            — jwt, otp, password, hashing, encryption, secure-link tokens
├── utils/                — generic helpers only (datetime, validation, id_generator, helpers)
├── shared/                — base_document, base_repository — used by every feature
├── core/                   — response envelope, pagination, exception→HTTP mapping
├── services/                — EXTERNAL integration clients (meta, whatsapp, sms, email, maps, storage) — not business features
├── features/                 — one folder per business module (see MODULES.md)
└── worker/                    — Arq worker entrypoint + scheduled/background tasks
```

`security/` is deliberately separate from `utils/` — see `docs/decisions/DECISIONS.md` if this distinction seems arbitrary: it isn't, JWT/OTP/password code is a security surface, not a grab-bag helper.

`services/` is deliberately separate from `features/` — integrations (WhatsApp, SMS, Meta leads, SMTP, Maps) are infrastructure the business features call, not business features themselves. Credentials/enable-per-provider are owner-managed via `system_settings` (test-connection UI), not hardcoded.

## Why MongoDB Embedding vs. Referencing

See `docs/database/DATABASE.md` for the concrete rule and examples.

## Why a Replica Set in Dev

Flows spanning multiple collections (e.g. lead status change + audit log + notification + task update) need multi-document transactions for atomicity. MongoDB only supports transactions on a replica set, even a single node — so `docker/mongodb/` runs one from day one rather than adding it under pressure later. See `backend/app/config/database.py:start_transaction`.

## Why Arq, not Celery

See decision 002 in `docs/decisions/DECISIONS.md`.

## Cross-Cutting Engines

`workflow_engine` and `event_engine` (both empty structure in this pass) exist so state transitions and side-effect fan-out are configured once, not duplicated per feature. See decision 005.

## Frontend Structure

```
frontend/src/
├── app/            — router, providers (TanStack Query client, etc.)
├── features/         — one folder per backend feature (empty this pass, names locked)
├── components/         — layout, cards, forms, tables, charts, dialogs, timeline, uploads, navigation
├── theme/                — design tokens (colors, spacing, typography, icons, radius, shadow, animation)
└── shared/api/             — typed fetch client wrapping the backend's response envelope
```

## Mobile Readiness

No server-rendered pages, no cookie-dependent auth flow — the API is pure JSON over `/api/v1/`, bearer-token authenticated. This is what lets the same FastAPI backend serve the future Flutter apps without redesign; only `frontend/` (React) vs `mobile/flutter/` (Flutter) differ, both consuming the identical API contract described in `docs/api/API_STANDARDS.md`.

## Deployment

`docker/<service>/Dockerfile` per service; `deployment/docker-compose.yml` composes them. No cloud-specific code anywhere in the app — the same containers run on AWS or GCP, differing only in the env file / secrets source supplied at deploy time.
