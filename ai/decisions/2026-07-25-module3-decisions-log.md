# 2026-07-25 — Module 3 Decisions Log

Five architecture decisions made this module, each with rationale in the canonical location:

- 020 — `roles` gets a real schema, superseding Foundation's placeholder seed (documented as the intended completion of that placeholder, not an unauthorized schema change)
- 021 — Permission key shape is `(module, resource, action)` with `module`/`resource` free-text (per explicit instruction, SaaS-scalability), not Foundation's existing `(feature, action)` helper — that helper stays untouched and unused
- 022 — Temporary Access / Geo Exception use a daily recurring date+time window, evaluated lazily at check time — an interpretation of the brief's 4 separate fields, not a confirmed spec
- 023 — Geo Exception is administrative record-keeping only — no enforcement engine exists yet to except from (geo-fencing's use case is still an open question)
- 024 — `PermissionEngine` reuses Module 2's `EmployeeRepository`/`require_owner` read-only; Module 2 is not retrofitted to use the new engine

Full text: `docs/decisions/DECISIONS.md`. See also `ai/reviews/2026-07-25-module3-access-control.md` and `docs/PERMISSIONS.md`.

**Role, Permission & Access Control is now frozen** — decisions 020–024 stand as the module's final architecture unless explicitly reopened. Future modules consume `require_permission(...)` to gate their own routes rather than modifying this module's engine, models, or APIs.
