# 2026-07-25 — Foundation Scaffold Plan (as approved)

This is the plan approved by the user for the Phase 1 Foundation Scaffold, preserved verbatim for future reference. The live architecture description is `docs/architecture/ARCHITECTURE.md` — this file is the historical snapshot of what was proposed and agreed, kept so later architectural changes can be diffed against the original intent.

---

# AFS Financial CRM — Phase 1 Foundation Scaffold (Final)

## Context

Greenfield enterprise CRM for Ashapura Financial Services. Working directory was empty at session start. The user asked for an architecture review before implementation, and gave explicit "module by module, verify before proceeding" instructions. Four architecture decisions were resolved (see `docs/decisions/DECISIONS.md`): tenant_id deferred to Phase 2, Arq for background jobs, two-tier secure-link + account auth for Customer/Referral Partner, and per-product-type configurable Lead Status.

This plan went through two rounds of user review. Round 1 requested the full enterprise folder topology up front (even empty) plus human-readable IDs, split config, structured logging, a middleware layer, an external-integrations `services/` layer, per-stage env files, richer docs, per-service Docker layout, CI stubs, a fuller test directory, and an `ai/` archive folder. Round 2 (final verdict: "approve the scaffold") requested: more explicit/unambiguous feature-folder names, two new cross-cutting engines (`workflow_engine`, `event_engine`), two additional reserved feature folders (`search`, `timeline`), moving JWT/OTP/password code into a dedicated `security/` package, and five more reference docs. Both rounds are reflected in the actual scaffold as built — see `docs/architecture/MODULES.md` for the final feature list and `docs/architecture/ARCHITECTURE.md` for the structure as implemented.

No business logic or feature implementation happened in this pass — only structure, plus the small set of genuinely foundational utilities (ID generation, base document/repository, response envelope, config, logging, security primitives, middleware skeletons) every future feature would otherwise need retrofitted.

## Outcome

Implemented as planned. See `docs/changelog/CHANGELOG.md` for the "Added" list and `docs/roadmap/TODO.md` for what comes next (Authentication).
