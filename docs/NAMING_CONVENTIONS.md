# Naming Conventions

## Feature Folders

Explicit and scope-anticipating, not literal-minimal — see decision 006. `loan_management` not `loan` (will hold Loan Settings, Loan Products, Loan Reports, Loan Analytics — not just loan records), `insurance_management` not `insurance`, `document_management` not `documents` (will hold customer docs, application docs, KYC, agreements, generated PDFs, templates), `notification_management` not `notifications`, `system_settings` not `settings`, `reporting` not `reports` (consolidates reports + analytics + KPIs + exports + scheduled reports), `audit` not `audit_logs` (will hold logs, activity, history, changes, login history — `audit_logs` is one collection inside it, not the whole module), `access_control` not `permissions` (will hold roles, departments, designations, delegation, not just permission flags).

Backend (`backend/app/features/<name>/`) and frontend (`frontend/src/features/<name>/`) use identical folder names for the same module — no translation layer between "what the API calls it" and "what the UI calls it."

## Collections

Plural, snake_case: `leads`, `loan_applications`, `referral_partners`. One collection = one noun; don't create `lead_details` alongside `leads` — that's an embedding-vs-referencing decision (see `docs/database/DATABASE.md`), not a naming one.

## Human-Readable IDs

`AFS-<PREFIX>-<6-digit sequence>`, e.g. `AFS-EMP-000001`. Prefixes are 3-4 uppercase letters (`EMP`, `CUS`, `LEAD`, `APP`, `REF`) defined in `backend/app/utils/id_generator.py:IdPrefix`. Add new prefixes there, not as ad-hoc strings elsewhere.

## Permission Keys

`"<feature>:<action>"`, lowercase, e.g. `"leads:assign"`, `"reports:export"`. Built via `backend/app/constants/permissions.py:permission_key`, not string-concatenated inline.

## Python

`snake_case` for functions/variables/modules, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants (see `backend/app/constants/`).

## TypeScript/React

`camelCase` for functions/variables, `PascalCase` for components and types, `UPPER_SNAKE_CASE` for constants. Component files match their default export's name (`AppShell.tsx` exports `AppShell`).

## Environment Variables

`UPPER_SNAKE_CASE`, matching the field name in `backend/app/config/settings.py` (e.g. `MONGO_URI` → `mongo_uri`). Frontend env vars are prefixed `VITE_` per Vite's requirement (e.g. `VITE_API_BASE_URL`).
