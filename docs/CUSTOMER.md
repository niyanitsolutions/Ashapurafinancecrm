# Customer Onboarding & Application Flow (Module 6B)

Implemented in `backend/app/features/customer/` + `frontend/src/features/customer/`. Full architecture rationale: `docs/decisions/DECISIONS.md` #046–#053. API reference: `docs/api/API.md`.

## Business Definitions

- **Lead** — a person interested in Ashapura Financial Services but not yet onboarded (Module 6A).
- **Customer** — a person who has completed registration, submitted the required application details and documents, and is now officially onboarded (this module).

This distinction is enforced structurally, not just by convention: a `Lead` (Module 6A) and a `Customer` (this module) are different collections with no shared identity — a Lead only becomes "linked" to a Customer at the moment of conversion (see below), and a Lead is never edited or deleted to represent that; the pointer lives on the `Customer` side (`converted_from_lead_id`, decision 048).

## Two Entry Flows

**Flow 1 — existing Lead:** Employee generates a secure, expiring link for a Lead (via a "Generate Secure Link" action on the Lead Details page, decision 052/053) → the Customer opens it, logs in or creates an account → the Application opens directly, already scoped to that Lead's product → they complete it, upload documents, and submit → **only then** does the Lead convert into a Customer.

**Flow 2 — direct portal:** Customer visits the portal directly → creates an account or logs in → completes their profile (Customer created immediately here) → chooses Loan or Insurance, then a specific product → the same Application form opens → they complete it, upload documents, and submit.

**Both flows merge into the exact same Application form/validation/submit logic once the form opens** — the only place they genuinely differ is *when* the Customer profile is created and *how* personal/KYC data is collected beforehand (see decision 047). No business logic is duplicated between them; `CustomerService` has exactly one `submit_application` code path for both.

## Authentication — 100% Reused from Module 1, Unmodified

There is no public self-service signup for any role (decision 011) — Module 1's `AuthService.send_otp` always requires an `inviter: User`. Module 6B never modifies Auth; it supplies a different, still-legitimate inviter per flow:

| Flow | `inviter` passed to `AuthService.send_otp` |
|---|---|
| 1 (secure link) | The Owner/Employee who generated the link (`SecureLink.created_by`) |
| 2 (direct portal) | Any seeded Owner account — a technical value only, satisfying Auth's frozen `send_otp` signature (decision 049); **never persisted as attribution** (decision 053) |

OTP verification, password creation ("Create Password"), and login all go through Auth's existing **public**, unmodified endpoints (`/auth/verify-otp`, `/auth/reset-password`, `/auth/login`) — the frontend hands off to Auth's own React pages via `react-router` state, without editing a single Auth file. A secure-link token in progress survives that hand-off via a `sessionStorage` bridge (`SecureLinkLandingPage.tsx` ↔ `app/HomeRedirect.tsx`).

**Never duplicate customers on the same verified mobile** is inherited for free from Auth's existing unique index on `users.mobile` (decision 007) — Module 6B adds no separate uniqueness logic of its own.

**A direct-portal registration is not linked to any Owner or Employee** (decision 053). `_any_owner()` is used purely as the technical value Auth's frozen `send_otp(inviter: User)` requires — immediately afterward, the newly-created pending `User` row's `created_by` is reset to `None`, matching `BaseDocument`'s own convention for "system-created, no human attribution." The workflow is: Customer Registration → Customer Account Created (unattributed) → Application Submitted → Application enters the **Unassigned Applications queue** → Owner reviews and assigns an Employee → Processing starts. The one residual trace of the technical Owner is the `OTP_SENT` audit-log entry (`audit_logs` is intentionally append-only, no update path) — accepted as a minor log artifact, not a data-model attribution.

## Customer Profile

- **Customer Number**: auto-generated, `AFS-CUS-000001` format (same `id_generator.py` used by every other module's codes).
- **Personal / Contact / Address / Basic KYC** live on a **fixed schema** (not the dynamic form engine below) — see decision 047 for exactly when each flow collects it.
- PAN and Aadhaar numbers are encrypted at rest (`security/encryption.py`, the same primitive Module 2 first used for bank account numbers) and only ever returned masked.
- **Profile Status**: `BaseDocument.status`, a simple active/inactive flag — no richer lifecycle was asked for.

## Application

- One Customer can hold multiple, fully independent Applications (Personal Loan today, Home Loan next year) — nothing is ever overwritten; each `Application` document stands alone.
- **Status is deliberately only `draft`/`submitted`** — no approval/rejection/workflow. That real pipeline is Module 6C's job entirely; this module doesn't invent any part of it.

## The Dynamic Form Engine

**The engine is code; the fields are data** — the same split every other data-driven part of this system uses (Access Control's `PermissionEngine`/`Permission` catalog, Dashboard's engine/widget catalog):

```
Load Product → Load ApplicationFormDefinition → Render fields generically → Validate required fields/documents → Submit
```

- `ApplicationFormDefinition` (one per `product_category`+`product_id`) holds `fields: [{key, label, field_type, required, options}]` — `field_type` is a small, fixed rendering vocabulary (`text`/`number`/`date`/`select`/`textarea`/`checkbox`) the frontend's `DynamicFormField` component switches on; the fields *themselves* are entirely data, added by seeding a new row, never by touching the renderer.
- **Only product-specific fields are dynamic.** Personal/Contact/Address/KYC are never part of a `FormFieldDefinition` list — see the Customer Profile section above.
- **Document requirements come from Settings, not a hardcoded list**: `required_document_type_ids` references Module 4's `document_types` catalog (PAN, Aadhaar, Bank Statement, Salary Slip, Property Documents — the last one added via Module 4's own still-open create endpoint, not a code change).
- **Future products reuse the same engine automatically** — adding a new Loan/Insurance product (Module 4) plus one new `ApplicationFormDefinition` row is the entire integration surface; nothing in `service.py` or the frontend's renderer needs to change.
- Form definitions are **seeded, not Owner-CRUD-able**, this round (decision 051) — the brief's own Owner-capability list for 6B doesn't include form authoring. The 5 seeded definitions (Personal/Business/Property Loan, Life, Health) use plausible, illustrative fields — **temporary development data, not part of the frozen architecture**, to be replaced later with Ashapura-approved field definitions without any change to the engine itself.

## Business Rules Recap

- A Lead remains a Lead until its Application is successfully submitted.
- **If** the Application originated from an existing Lead, that Lead converts into a Customer **after** successful submission (Flow 1).
- **If** the Application originated directly from the portal (no pre-existing Lead), the Customer is created **at registration**, and the Application itself is the internal record employees process from that point on (Flow 2) — no phantom Lead is invented for a Customer who was never a Lead.
- Never create duplicate Customers on the same verified mobile (inherited from Auth, see above).

## Owner / Employee / Customer Capabilities (exactly as scoped — nothing more)

- **Owner**: View Customers, View Applications, Search, Filter, **review the Unassigned Applications queue** (`unassigned_only` filter — decision 053), **Assign Employee**, View Documents.
- **Employee**: View *Assigned* Customers/Applications/Documents only — cannot approve, reject, or change any workflow (there isn't one yet). This scoping is enforced in the service layer unconditionally, not via an Access Control grant (decision 050 — the brief frames it as inherent, not delegable).
- **Customer**: Register, Login, View/Edit Profile, view Draft Applications, Continue a Draft, Submit, Upload Documents, view Submitted Applications. No status tracking yet — there's no status to track beyond draft/submitted.

## Known Gaps

See the Module 6B section of `docs/KNOWN_LIMITATIONS.md` for the full list (mobile-only duplicate matching inherited from 6A, no Owner form-builder UI, no Customers/Applications Sidebar nav items, the `OTP_SENT` audit-log's residual technical-Owner attribution, etc.).

## Freeze

Module 6B is approved and frozen, including three business-rule refinements adopted after user review (decision 053; amendments to decisions 049/051/052): direct-portal registrations are never attributed to an Owner/Employee and instead flow into an Owner-only "Unassigned Applications" queue; the "Generate Secure Link" action was added to Lead Details as an approved UX exception; and the seeded form definitions are explicitly temporary development data, not frozen architecture. Module 6C (Loan & Insurance Pipeline) is next, gated on a separate Workflow Proposal (no code) being reviewed and approved first.
