# Style Guide

## Backend (Python)

- Follow the layering in `docs/architecture/ARCHITECTURE.md` — no business logic in `router.py`, no direct Mongo calls outside `repository.py`.
- Type-annotate everything; `mypy --strict` is the target (currently non-fatal in CI until feature modules land — see `.github/workflows/lint.yml`).
- Format/lint with `ruff` (config in `backend/pyproject.toml`).
- Comments explain *why*, not *what* — no docstrings restating the function name in prose. A comment referencing a non-obvious constraint (e.g. "OTP hashing is HMAC not bcrypt because it's high-frequency") is good; a comment saying "this function creates a user" is not.
- No bare `except:` — catch specific exceptions, raise `AppError` subclasses (`backend/app/core/exceptions.py`) so failures reach the client through the standard envelope.
- Secrets only via environment variables (`app/config/settings.py`), never hardcoded, never committed (see `.gitignore`).

## Frontend (TypeScript/React)

- Feature-based: a feature's components, hooks, and API calls live inside its own `features/<name>/` folder. Shared, feature-agnostic UI goes in `components/`.
- All API calls go through `shared/api/client.ts` — no raw `fetch` in components.
- Forms: React Hook Form + Zod schemas for validation, not manual `useState` validation.
- Server state (anything from the API): TanStack Query. Local UI-only state: `useState`/`useReducer`. Don't put server data in a global client-state store.
- Type-check with `tsc --noEmit` (`npm run typecheck`), lint with the flat ESLint config (`frontend/eslint.config.js`).
- Theme values always come from `theme/*.ts` tokens (consumed by `tailwind.config.ts`) — no hardcoded hex colors in component files.

## Naming

See `docs/NAMING_CONVENTIONS.md`.

## Commits / PRs

One module's worth of change per PR where reasonably possible, matching the "work module by module, verify before proceeding" project rule — avoid bundling unrelated feature work with foundation/infra changes.
