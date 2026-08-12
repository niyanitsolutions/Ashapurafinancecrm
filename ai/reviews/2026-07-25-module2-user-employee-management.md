# 2026-07-25 — Module 2: User & Employee Management

Delivered alongside a full Module 3 (RBAC) prompt and a roadmap change request in the same message. Per the module's own completion rule ("Do NOT begin Module 3"), only Module 2 was built — the roadmap change (inserting a Settings/Master Data module before Dashboard Framework) was applied to `docs/roadmap/TODO.md` since it's a low-risk sequencing update, not new scope.

The main design tension: two Owner Features (Reset Employee Password, Force Logout Employee) and two views (sessions, login history) need Authentication's data/behavior, but Authentication is frozen ("do not modify"). Resolved by reusing Auth's existing internals *unmodified* from Module 2's own service layer rather than requesting an exception:
- Reset Password calls `AuthService.forgot_password()` directly — already public, already role-agnostic, needed no changes.
- Force Logout and the session/history views use Auth's existing `SessionRepository`, whose inherited `find_many`/`update` (from `BaseRepository`) were already sufficient.

Zero lines changed under `app/features/auth/`. This is the same pattern used in Module 1 when it needed to distinguish "bug fix in frozen code" (touch it, document why) from "new capability" (don't touch it, compose around it) — here the answer was cleanly "compose around it."

A real bug surfaced during testing, not design: BSON has no date-only type, so `Employee.date_of_birth`/`joining_date` (typed `date`) failed at insert, not at validation. Fixed by storing `datetime` and converting at the service boundary, then documented as a general rule in `docs/database/DATABASE.md` — this will recur in any future module with a date field if not known in advance.

Two scope calls worth flagging: (1) employee document upload (PAN/Aadhaar/etc.) has a working backend but no frontend page, since neither the Owner Features list nor Employee Portal list named it as an action even though the data model clearly anticipates it — built the API, didn't invent a UI page outside the stated frontend scope. (2) `on_leave` not blocking login is a genuine guess (every other status blocks login; the brief didn't say either way for this one) — flagged explicitly rather than silently assumed to be equivalent to the others.

Verification: `ruff`/`mypy --strict` clean across 105 backend files, 40/40 tests passing (20 new + the original 20 from Module 1, all still green), frontend `tsc`/`eslint`/`build` clean.
