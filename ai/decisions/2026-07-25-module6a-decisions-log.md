# 2026-07-25 — Module 6A Decisions Log

One policy decision preceded this module; six architecture decisions were made within it. Full text and rationale in the canonical location:

- 039 — Freeze policy reconfirmed to explicitly include Dashboard Framework, before Module 6 (Lead Management) began
- 040 — A Lead carries its own contact info (`full_name`/`mobile`/`email`) directly — no Customer record exists yet to link to; that's Module 6B's job
- 041 — Duplicate detection flags (`duplicate_of_lead_ids`, matched on `mobile`) but never blocks Lead creation
- 042 — Timeline = merged Activities + Notes, lead-scoped (`features/leads/`) — not the shared, still-reserved `features/timeline` module
- 043 — No public/unauthenticated lead-capture webhook this round — every Lead is created via the authenticated API; real Website/Meta ingestion is future Integrations-module work
- 044 — Dashboard's `today_leads`/`assigned_leads` widgets wired to real data; `pending_followups` stays a placeholder (needs Module 6D's follow-up concept) — verified end-to-end, not just unit-tested
- 045 — Lead read/write gated entirely by `leads:leads`; Create/Edit's Source/Product dropdowns depend on Settings' own separate permissions — a real, documented usability consequence, not silently worked around

Full text: `docs/decisions/DECISIONS.md`. See also `ai/reviews/2026-07-25-module6a-lead-foundation.md` and `docs/api/API.md` (Lead Management section).

**Lead Foundation (Module 6A) is now frozen** — decisions 040–045 stand as the sub-module's final architecture unless explicitly reopened. Module 6B (Customer Application Flow) builds on top of it — converting a Lead — rather than modifying its models, engine, or APIs.
