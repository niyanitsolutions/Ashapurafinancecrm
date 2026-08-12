# 2026-07-25 — Module 2 Decisions Log

Five architecture decisions made this module, each with rationale in the canonical location:

- 015 — Owner-adjacent Auth actions (Reset Password, Force Logout, session/history views) reuse existing Auth internals unmodified — zero changes to frozen `app/features/auth/`
- 016 — Employment status paired with login-blocking; `on_leave` is the one non-blocking exception (a judgment call, flagged)
- 017 — Employee accounts get an Owner-set initial password, not an OTP invite (no Auth changes needed)
- 018 — Bank account numbers encrypted at rest via Foundation's `security/encryption.py` — first real use of that primitive
- 019 — Departments/Designations/Branches: collections + seed data now, full management screens deferred to a future Settings (Master Data) module

Full text: `docs/decisions/DECISIONS.md`. See also `ai/reviews/2026-07-25-module2-user-employee-management.md` and `docs/AUTHENTICATION.md` (unchanged — confirms Module 2 didn't touch it).

**User & Employee Management is now frozen** — decisions 015–019 stand as the module's final architecture unless explicitly reopened.
