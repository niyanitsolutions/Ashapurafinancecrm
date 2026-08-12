# 2026-07-26 — Module 6B Decisions Log

Seven architecture decisions were made this module. Full text and rationale in the canonical location:

- 046 — Both onboarding flows reuse Auth's invitation-only signup unmodified, via a resolved `inviter` User per flow — zero lines changed under `app/features/auth/`
- 047 — Personal/Contact/Address/KYC lives on a fixed-schema Customer profile, not the dynamic form; collected at different points per flow (registration for Flow 2, inline `pending_profile` for Flow 1)
- 048 — `Customer.converted_from_lead_id` is the one reverse-pointer field; Module 6A's `Lead` is never modified
- 049 — Direct portal registration's technical inviter is any seeded Owner account — the one place requiring genuine judgment rather than a mechanical brief reading
- 050 — Staff (Owner + Employee) visibility for Customers/Applications uses plain role checks, not `require_permission` — a deliberate departure from the pattern every module since Settings has used, since the brief frames Employee access as inherent, not delegable
- 051 — Application form definitions are seeded, illustrative, and not Owner-manageable in this module
- 052 — "Generate Secure Link" has no entry point on Module 6A's frozen Lead Details page — reachable only by direct URL

Full text: `docs/decisions/DECISIONS.md`. See also `ai/reviews/2026-07-26-module6b-customer-onboarding.md` and `docs/CUSTOMER.md` (the new module-level reference doc covering business definitions, both flows, the auth-reuse strategy, and the dynamic form engine in full).

**Customer Onboarding & Application Flow is now frozen** — decisions 046–052 stand as the sub-module's final architecture unless explicitly reopened. Module 6C (Loan & Insurance Pipeline) builds the real status engine on top of `Application`/`ApplicationDocument` rather than modifying this sub-module's models, engine, or APIs.
