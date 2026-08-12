# 2026-07-25 — Module 4 Decisions Log

Six architecture decisions made this module, each with rationale in the canonical location:

- 025 — Departments/Designations/Branches get Edit/Activate/Deactivate via composition over Module 2's existing repository classes — zero lines changed in Module 2
- 026 — Every Settings endpoint (read and write) is gated with `require_permission("system_settings", resource, action)` — the first real consumer of Access Control's engine
- 027 — `NamedMasterData` shared base + generic CRUD (service and frontend) for the four/six resources that are just name+description+status — this module's one deliberate exception to the "write it out explicitly" convention
- 028 — API Settings config is encrypted as one JSON blob, merged (not replaced) on update, never returned in plaintext — only configured key names are exposed
- 029 — Status Masters, Notification Templates, and API Settings ship with zero seeded example rows — their real content is unconfirmed business logic/credentials, not invented here
- 030 — Company Settings is a singleton located by a unique `singleton_key` marker field, not a hardcoded ObjectId — a reusable pattern for future singleton config collections

Full text: `docs/decisions/DECISIONS.md`. See also `ai/reviews/2026-07-25-module4-settings-master-data.md` and `docs/PERMISSIONS.md` (updated to describe Module 4 as the first real `require_permission` consumer).

**Settings (Master Data) is now frozen** — decisions 025–030 stand as the module's final architecture unless explicitly reopened. Future modules consume its master-data collections (read) and `require_permission("system_settings", ...)` rather than modifying its models, engine, or APIs.
