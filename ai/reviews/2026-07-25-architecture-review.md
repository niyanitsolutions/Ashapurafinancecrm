# 2026-07-25 — Foundation Architecture Review

Before any code was written, six gaps were flagged in the original brief and resolved with the user via targeted questions:

1. **Multi-tenancy** — `tenant_id` marked "future" in the brief; risk of expensive retrofit. User chose to defer to Phase 2 anyway (accepted the future-migration cost) — see decision 001.
2. **Background job engine** — missing from the stack entirely; the Reminder Engine needs one. Resolved: Arq — decision 002.
3. **Customer/Referral Partner auth** — ambiguous between the Employee workflow's "secure link" and the Customer workflow's "Register/Login." Resolved: two-tier — decision 003.
4. **Lead Status shape** — the given pipeline is loan-specific, doesn't fit Insurance. Resolved: configurable per product type — decision 004.
5. **API response envelope, MongoDB transactions/replica-set requirement** — flagged as foundational and needing to be settled before the first route, not decided by asking (no reasonable alternative) — folded directly into the scaffold.

The user then reviewed the resulting scaffold plan in two further rounds, requesting the full enterprise folder topology up front, human-readable IDs, split config, structured logging, a dedicated `security/` package, two new cross-cutting engines (`workflow_engine`, `event_engine`), reserved `search`/`timeline` modules, and explicit feature-folder naming — all incorporated; see decisions 005 and 006, and the final approved plan preserved in `ai/architecture/2026-07-25-foundation-scaffold-plan.md`.

Full canonical decision text: `docs/decisions/DECISIONS.md`.
