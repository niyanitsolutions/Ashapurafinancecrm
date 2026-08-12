# 2026-07-25 — Module 1 Round 2 Decisions Log

Four more architecture decisions made in this hardening round, each with rationale in the canonical location:

- 011 — No public self-signup for any role; Customer/Referral Partner signup is invitation-only
- 012 — Refresh token client-side storage: `localStorage`, with rotation + reuse detection as the mitigation
- 013 — Refresh token family / reuse detection
- 014 — Login History enrichment: GeoIP stub, login method, failure reason

Full text: `docs/decisions/DECISIONS.md`. See also `ai/reviews/2026-07-25-module1-authentication-round2.md` for how this round's feedback was handled, and `docs/AUTHENTICATION.md` for the consolidated, current behavior.

**Authentication is now frozen** — decisions 007–014 stand as the module's final architecture unless explicitly reopened.
