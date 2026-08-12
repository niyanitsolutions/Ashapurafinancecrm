# 2026-07-25 — Module 1: Authentication

Scope was tightly specified by the user (9 fixed endpoints, 4 frontend pages, explicit "do not build anything else" list) plus a new standing rule: stop and ask when a requirement is genuinely unclear or multiple valid architectural approaches exist, rather than inventing.

One blocking question was raised before implementation: the brief suggested HttpOnly cookies as an example auth-token strategy, which would have conflicted with the Foundation's already-frozen "pure Bearer JWT, no cookies" decision (`docs/api/API_STANDARDS.md`). Presented as an explicit choice (pure Bearer vs. a cookie/Bearer hybrid); pure Bearer was confirmed — see decision 008.

Several other design points were resolved by inference from the user's own stated constraints rather than re-asking, and documented as assumptions rather than silently decided:
- Owner/Employee get no self-signup (derived from the fixed API list having no signup endpoint for those roles, plus User Management being out of scope) — decision 007.
- `users` is one shared collection with a globally-unique `mobile`, avoiding an unspecified "multi-role phone number" rule.
- `reset-password` doubles as "Create Password" (same semantics, avoids a 10th endpoint).
- Customer/Referral Partner signup is open (not secure-link-gated) this module, since the link's target (a Lead) doesn't exist yet — flagged clearly in `docs/KNOWN_LIMITATIONS.md` rather than silently narrowing decision 003's scope.

Two real bugs in the already-approved Foundation surfaced while building against it for the first time (rather than deferred): `BaseDocument` had no usable `id` field (Pydantic v2 silently drops `_id`), and `rate_limit.py` bypassed dependency injection for its Redis client. Both fixed in place as decision 010 / a changelog fix entry, not treated as scope creep — using the Foundation for real is what exposed them.

Verification: `ruff`/`mypy --strict` clean on 94 backend source files; 15/15 API tests passing against mongomock+fakeredis (no live Docker services needed); frontend `tsc`/`eslint`/`vite build` all clean; dev-server smoke-tested. No browser-automation tool was available, so the actual click-through UX was not visually verified — noted explicitly in `docs/KNOWN_LIMITATIONS.md` rather than claimed as tested.
