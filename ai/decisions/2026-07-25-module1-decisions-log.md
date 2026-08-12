# 2026-07-25 — Module 1 Decisions Log

Four architecture decisions made this module, each with rationale in the canonical location:

- 007 — Single shared `users` identity collection; no self-signup for Owner/Employee
- 008 — Pure Bearer JWT confirmed over cookies
- 009 — Refresh tokens are stateful (DB-backed sessions), access tokens stay stateless
- 010 — `BaseDocument` gains a real `id` field (Foundation bug fix)

Full text: `docs/decisions/DECISIONS.md`. See also `ai/reviews/2026-07-25-module1-authentication.md` for how ambiguity was handled this module.
