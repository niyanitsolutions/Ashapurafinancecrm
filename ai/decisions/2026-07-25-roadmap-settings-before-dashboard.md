# 2026-07-25 — Roadmap change: Settings (Master Data) inserted before Dashboard

The user proposed reordering the module sequence to insert a "Settings (Master Data)" module between Access Control and Dashboard Framework, reasoning that Employee Management, Permissions, Dashboard, and Lead Management all depend on configurable master data (departments, designations, branches, lead sources, product types, status masters, notification templates) — building those masters first avoids hardcoding and rework later, and fits the long-term goal of a configurable SaaS platform.

Accepted and reflected in `docs/roadmap/TODO.md`. Also resolves a scope question for Module 2 (User & Employee Management): departments/designations/branches collections and seed data are created now (Employee records need to reference them), but full CRUD *management screens* for those entities are deferred to the future Settings module rather than built ad-hoc inside Employee Management.
