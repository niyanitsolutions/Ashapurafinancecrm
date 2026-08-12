# 2026-07-25 — Module 5 Decisions Log

One policy decision preceded this module; seven architecture decisions were made within it. Full text and rationale in the canonical location:

- 031 — Unified freeze policy: Foundation, Authentication, User & Employee Management, Access Control, and Settings are all frozen under one rule (no architectural changes, only bug/security fixes) — the first explicit freeze statement for Foundation itself
- 032 — Widget/nav permission gates reference future modules by naming convention; forward-compatible with zero code changes once those modules seed their own catalog entries — verified end-to-end in tests
- 033 — Nav item gating mirrors how the target route is ACTUALLY protected (`owner_only` vs. `require_permission`), not a generic permission check — caught during design, not after
- 034 — Real server-side logout wired into Profile Menu, consuming Module 1's previously-unused `/auth/logout` — zero lines changed under `features/auth/`
- 035 — `AppShell` wraps every authenticated route via `<Outlet/>`; existing Module 2–4 pages are not rewritten, accepting a minor stacked-header redundancy
- 036 — Refresh Interval is one shared poll at the shortest visible widget's interval, not N independent polling loops
- 037 — Widget/NavItem catalogs are seeded once, not Owner-CRUD-able — each entry needs real backend code to mean anything
- 038 — Only 3 of 13 widgets compute real data (Recent Activities, Department Summary, Employee Summary); the other 10 honestly report `available: false` rather than a fabricated number

Full text: `docs/decisions/DECISIONS.md`. See also `ai/reviews/2026-07-25-module5-dashboard-framework.md`, `docs/PERMISSIONS.md`, and `docs/UI_UX.md` (updated to describe the real Sidebar/Topbar/AppShell implementation).

**Dashboard Framework is now frozen** — decisions 032–038 stand as the module's final architecture unless explicitly reopened. Future modules (Lead Management onward) add their own nav item + wire any relevant widget as part of their own build, rather than modifying this module's engine, models, or APIs.
