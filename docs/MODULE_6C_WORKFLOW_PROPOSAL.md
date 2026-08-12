# Module 6C — Loan & Insurance Pipeline: Workflow Proposal

**Status: implemented and frozen.** This document is preserved as the original planning artifact. Two items below were superseded during implementation and its subsequent business review — see `docs/decisions/DECISIONS.md` #054–#064 and `docs/WORKFLOWS.md` for what actually shipped: **§2 (Insurance Workflow)** was a draft, explicitly flagged for confirmation (§7, item 3) — the user later finalized a different, corrected sequence (decision 064: Medical Verification/Additional Documents as two separate optional stages, Policy Generation split from Policy Issued). **§7's open questions** were resolved before coding began (unified `application_workflows` collection, two rejection exits, no rollback, real `require_permission` gating) and are recorded as decisions 054/055/056/059 respectively; a fifth capability, **On Hold / Resume**, was added afterward as an Optional Status on both pipelines (decision 064) and is not described anywhere below.

~~Status: awaiting approval. No implementation code has been written for this module. Nothing below is committed architecture — it is a proposal for review, per the explicit instruction: "produce a Workflow Proposal instead of writing code immediately... Once you approve the workflow, then Claude should implement Module 6C."~~

This document covers: the Loan Workflow, a separate Insurance Workflow, State Transition Rules (allowed next statuses / required documents / required permissions / notifications / audit entries per status), Database (collections + relationships only), APIs (endpoint list only), and UI (screen list only) — no schemas-as-code, no request/response bodies, no implementation.

---

## 0. Relationship to frozen modules (nothing here modifies them)

- **`Application`/`ApplicationDocument` (Module 6B, frozen)** are not modified. `Application.status` stays exactly `draft`/`submitted` forever — 6C's real pipeline lives in **new**, 6C-owned collections that reverse-point at `Application` by `application_id`, the same pattern Module 6B itself used to point at Module 6A's frozen `Lead` (`Customer.converted_from_lead_id`, decision 048).
- A **Case** (new concept) is created automatically the moment an `Application` transitions `draft → submitted` — one `LoanCase` for `product_category="loan"`, one `InsuranceCase` for `product_category="insurance"`. There is no manual "create case" action; submission *is* the trigger.
- This is the first module to give real substance to two feature folders that have been reserved-but-empty since Foundation: **`workflow_engine`** (configurable state machine — decision 005) and **`event_engine`** (pub/sub for side effects — decision 005). Both were explicitly earmarked for "the first feature with a non-trivial state machine" (decision 005's own impact note) — 6A and 6B both deliberately kept their status fields trivial (`new` only; `draft`/`submitted` only) specifically so this module would be the one to build the real engine, not each product pipeline hand-rolling its own.
- **`loan_management`** and **`insurance_management`** (also reserved-but-empty) become real: each owns its own Case model + product-specific fields/actions, while `workflow_engine` owns the transition rules as *data* (status list, allowed-next, required permission, required documents, notification key — one row per status) and the *generic* code that validates and executes any transition. Same "engine is code, catalog is data" split as `PermissionEngine`/`Permission` (Access Control) and the Dynamic Form Engine (6B) — a new product type (e.g. a future BNPL or Gold Loan) becomes a config row, not new branching code.

---

## 1. Loan Workflow

Per the brief's own stage list, adopted as the spine:

```
New Customer
   ↓
Documents Pending
   ↓
Credit Evaluation
   ↓
Offer Acceptance
   ↓
Additional Documents
   ↓
eSign / NACH / KYC
   ↓
Final Evaluation
   ↓
Rejected  OR  Send for Disbursement
                    ↓
                Disbursed
```

| # | Status (key) | Meaning |
|---|---|---|
| 1 | `new_customer` | Case auto-created the instant the Loan Application is submitted. No manual entry action. |
| 2 | `documents_pending` | Case-specific processing documents (beyond the 6B application's own required set) are requested and awaited. |
| 3 | `credit_evaluation` | Assigned Employee/underwriter records a credit assessment (score, remarks, approve/reject decision). No live bureau integration exists yet — recorded manually, same honest-placeholder posture as every other unbuilt external integration in this project (decision 038's pattern). |
| 4 | `offer_acceptance` | A loan offer (amount/tenure/rate) is issued; Customer accepts or declines it themselves (self-service, mirrors 6B's Customer-driven actions). |
| 5 | `additional_documents` | Post-offer documents (e.g. bank statements, collateral papers) requested and awaited. |
| 6 | `esign_nach_kyc` | Final agreement e-sign, NACH mandate, and KYC re-verification. No live e-sign/NACH/eKYC provider integration exists yet — recorded as staff-confirmed checklist items, same placeholder posture as #3. |
| 7 | `final_evaluation` | Final compliance/quality check before the disbursement decision. |
| 8 | `rejected` | Terminal. |
| 9 | `send_for_disbursement` | Approved; awaiting the actual funds transfer to be recorded. |
| 10 | `disbursed` | Terminal. |

**Proposed refinement flagged for approval:** the brief's diagram shows only one rejection branch, after Final Evaluation. Real lending also rejects earlier (failed credit evaluation). The table below proposes **two rejection exits — after Credit Evaluation and after Final Evaluation** — rather than forcing every doomed application through the full pipeline. If you'd rather match the diagram literally (rejection only possible at the very end), say so and this collapses to one exit point.

## 2. Insurance Workflow (separate lifecycle)

The brief asks for "a separate lifecycle, because insurance processing differs from loans" without specifying exact stages. Proposed, based on decision 004's own framing ("Insurance's lifecycle — proposal, medical, policy issuance"):

```
New Customer
   ↓
Documents Pending
   ↓
Underwriting
   ↓
Medical Examination   (conditional — not every product requires it)
   ↓
Premium Acceptance
   ↓
Policy Issuance
   ↓
Rejected  OR  Active
```

| # | Status (key) | Meaning |
|---|---|---|
| 1 | `new_customer` | Case auto-created on Insurance Application submission. |
| 2 | `documents_pending` | KYC + proposal-form supporting documents awaited. |
| 3 | `underwriting` | Risk assessment (insurance's analogue of credit evaluation) — sum insured vs. risk profile, manually recorded. |
| 4 | `medical_examination` | **Conditional**, driven by a per-product config flag (`InsuranceProduct.requires_medical`, a small addition to Module 4's already-existing product catalog — additive, not a change to any frozen field) — e.g. Health/Life above a sum-insured threshold; many Health/Life products and most General Insurance skip this entirely. If not required, the case moves straight from Underwriting to Premium Acceptance. |
| 5 | `premium_acceptance` | Premium quote issued; Customer accepts or declines (self-service, same as Loan's Offer Acceptance). |
| 6 | `policy_issuance` | Policy document generated/uploaded, policy number recorded. |
| 7 | `rejected` | Terminal. |
| 8 | `active` | Terminal (for this pipeline — post-issuance servicing/renewals/claims are explicitly out of scope, a future module). |

**Please confirm or amend this proposed lifecycle** — unlike the Loan stages, these were not dictated verbatim in the brief.

---

## 3. State Transition Rules

"Required Permission" assumes **switching Module 6C to real `require_permission(module, resource, action)` gating** (Access Control, Module 3) instead of continuing 6B's plain-role-check pattern (decision 050). That decision was justified there because Employee visibility was purely inherent/assignment-scoped with no delegation to model. Here, distinct capabilities (who may evaluate credit vs. who may do final evaluation vs. who may disburse) are exactly the kind of granular, Owner-delegable grant Access Control exists for — the same reasoning that made Module 4 (Settings) the first real consumer of `require_permission`. **Flagged for your confirmation** since it's a deliberate reversal of 6B's own decision 050, not an oversight.

Every transition, on both pipelines, writes one entry to the existing shared `audit_logs` collection (append-only, `shared/audit_log.py` — no schema change) and publishes one event on the new `event_engine` bus. A subscriber inside 6C consumes that event to (a) write the audit entry and (b) enqueue a notification **only if** a matching, non-empty row already exists in Module 4's `notification_templates` — otherwise it's an honest no-op, since real Notification Management (channel delivery) is still its own unbuilt future module. This mirrors exactly how Dashboard's still-unbuilt widgets honestly return `available: false` (decision 038) rather than faking data.

### Loan Case

| Status | Allowed next | Required documents | Required permission | Notification event | Audit event |
|---|---|---|---|---|---|
| New Customer | Documents Pending | — (auto-transition once case-required doc list is set) | *(system-created; no manual action)* | `loan_case.created` → Customer: "Your loan application is being processed" | `LOAN_CASE_CREATED` |
| Documents Pending | Credit Evaluation | All requested document types (`case_document_requests`) fulfilled | `loan_management:cases:manage_documents` | `loan_case.documents_verified` → Customer | `LOAN_CASE_DOCUMENTS_VERIFIED` |
| Credit Evaluation | Offer Acceptance, **Rejected** | — (evaluation is data entry: score/remarks/decision) | `loan_management:cases:evaluate` | `loan_case.offer_ready` or `loan_case.rejected` → Customer | `LOAN_CASE_CREDIT_EVALUATED` |
| Offer Acceptance | Additional Documents, **Rejected** (on decline) | — | Customer self-service (accept/decline own offer) | `loan_case.offer_accepted`/`loan_case.offer_declined` → assigned Employee | `LOAN_CASE_OFFER_ACCEPTED` / `LOAN_CASE_OFFER_DECLINED` |
| Additional Documents | eSign/NACH/KYC | All newly-requested document types fulfilled | `loan_management:cases:manage_documents` | `loan_case.additional_docs_verified` → Customer | `LOAN_CASE_ADDITIONAL_DOCS_VERIFIED` |
| eSign/NACH/KYC | Final Evaluation | — (3-item staff-confirmed checklist: eSign, NACH, KYC) | `loan_management:cases:process_esign` | `loan_case.esign_nach_kyc_completed` → Customer + assigned Employee | `LOAN_CASE_ESIGN_NACH_KYC_COMPLETED` |
| Final Evaluation | Send for Disbursement, **Rejected** | — | `loan_management:cases:final_evaluate` (Owner or a senior Employee grant — not every Employee) | `loan_case.approved`/`loan_case.rejected` → Customer | `LOAN_CASE_FINAL_EVALUATED` |
| Send for Disbursement | Disbursed | — | `loan_management:cases:disburse` | `loan_case.disbursement_initiated` → Customer | `LOAN_CASE_SENT_FOR_DISBURSEMENT` |
| Disbursed | *(terminal)* | — | `loan_management:cases:disburse` (records amount/date/reference) | `loan_case.disbursed` → Customer + assigned Employee | `LOAN_CASE_DISBURSED` |
| Rejected | *(terminal)* | — | reachable from Credit Evaluation or Final Evaluation only (proposed — see §1) | `loan_case.rejected` → Customer (with reason) | `LOAN_CASE_REJECTED` |

### Insurance Case

| Status | Allowed next | Required documents | Required permission | Notification event | Audit event |
|---|---|---|---|---|---|
| New Customer | Documents Pending | — | *(system-created)* | `insurance_case.created` → Customer | `INSURANCE_CASE_CREATED` |
| Documents Pending | Underwriting | All requested document types fulfilled | `insurance_management:cases:manage_documents` | `insurance_case.documents_verified` → Customer | `INSURANCE_CASE_DOCUMENTS_VERIFIED` |
| Underwriting | Medical Examination (if `requires_medical`) else Premium Acceptance, **Rejected** | — | `insurance_management:cases:evaluate` | `insurance_case.underwritten` → Customer | `INSURANCE_CASE_UNDERWRITTEN` |
| Medical Examination | Premium Acceptance, **Rejected** | — (staff-recorded outcome; no diagnostic-lab integration) | `insurance_management:cases:evaluate` | `insurance_case.medical_scheduled`/`insurance_case.medical_completed` → Customer | `INSURANCE_CASE_MEDICAL_COMPLETED` |
| Premium Acceptance | Policy Issuance, **Rejected** (on decline) | — | Customer self-service (accept/decline own premium quote) | `insurance_case.premium_accepted`/`insurance_case.premium_declined` → assigned Employee | `INSURANCE_CASE_PREMIUM_ACCEPTED` / `_DECLINED` |
| Policy Issuance | Active | Policy document uploaded (reuses `document_types`, e.g. a new "Policy Document" entry via Module 4's own open create endpoint — no code change) | `insurance_management:cases:issue_policy` | `insurance_case.policy_issued` → Customer | `INSURANCE_CASE_POLICY_ISSUED` |
| Active | *(terminal for this pipeline)* | — | — | — | — |
| Rejected | *(terminal)* | — | reachable from Underwriting or Medical Examination | `insurance_case.rejected` → Customer (with reason) | `INSURANCE_CASE_REJECTED` |

---

## 4. Database — collections and relationships only

**New collections:**

- **`loan_cases`** — one per submitted Loan `Application`. Fields (names only, no types/code): case code (own `AFS-LOAN-000001`-style sequence via the existing `id_generator.py`), current status, credit score/remarks, offered amount/tenure/rate, offer decision, disbursed amount/date/reference, rejection reason, timestamps.
- **`insurance_cases`** — parallel structure: sum insured, premium amount, medical-required flag/outcome, policy number, rejection reason, timestamps.
- **`case_document_requests`** — one shared collection (not duplicated per pipeline) for "this document type is now required at this stage of this case," discriminated by a `case_type` field (`loan`/`insurance`). Tracks: which document type, which stage requested it, fulfilled or not, and (once fulfilled) which uploaded document satisfies it.
- **`workflow_definitions`** (owned by `workflow_engine`) — one row per `(case_type, status_key)`: label, sequence, allowed-next status list, required permission key, required-document-stage flag, notification event key. This is the *data* half of "engine is code, catalog is data" — adding a future case type (or amending Insurance's proposed stages after your review) is a data change here, not new branching code.
- **`event_engine` has no collection of its own** — it is a pure in-process publish/subscribe dispatch layer (function calls, not persisted state); every side effect it triggers lands in an *existing* collection (`audit_logs`) or an *existing* mechanism (the Arq worker queue for notifications), so nothing new is persisted purely for event routing.

**Reused, unmodified:** `applications`, `application_documents` (both Module 6B, frozen), `customers`, `users`, `document_types`, `insurance_products` (gains one new optional field, `requires_medical`, via Module 4's existing open create/update endpoints — additive, not a change to a frozen field), `audit_logs`, `notification_templates`.

**Relationships:**

- `loan_cases.application_id` → `applications._id` (1:1; only ever created for `product_category="loan"`)
- `insurance_cases.application_id` → `applications._id` (1:1; only ever created for `product_category="insurance"`)
- `loan_cases.customer_id` / `insurance_cases.customer_id` → `customers._id` (denormalized for query convenience, same as `Application.customer_id` already is)
- `loan_cases.assigned_to` / `insurance_cases.assigned_to` → `users._id` (Employee). **Proposed:** inherits the Application's `assigned_to` at case-creation time, but is independently reassignable by the Owner afterward (a specialist for credit evaluation may differ from whoever handled initial intake) — **flagged for confirmation**, since 6B treats Application assignment as the single source of truth today.
- `case_document_requests.case_id` → `loan_cases._id` or `insurance_cases._id` (per its own `case_type`); `.document_type_id` → `document_types._id`; `.fulfilled_by_document_id` → `application_documents._id` (nullable until fulfilled — the actual file still lives in 6B's own `application_documents`, keyed by the same `application_id`, so no new file-storage plumbing is needed).
- `workflow_definitions` — keyed by `(case_type, status_key)`, no foreign key; conceptually scoped per `product_category` (loan vs. insurance) rather than per specific product (Personal Loan vs. Business Loan don't get different transition rules by default). **Flagged for confirmation** if per-specific-product granularity is actually wanted later — the schema supports adding a `product_id` scope column without breaking the coarser default.

---

## 5. APIs — endpoints only, no implementation

Case creation has **no direct create endpoint** — a case is auto-created by an internal `event_engine` subscriber the moment `Application.status` becomes `submitted` for a matching `product_category`.

### Loan Cases — staff (Owner/Employee, `require_permission("loan_management", "cases", ...)`)

- `GET /loan-cases` — list, filters: `status`, `assigned_to`, `unassigned_only`, `customer_id`, `product_id` (mirrors 6B's own `unassigned_only` pattern, decision 053)
- `GET /loan-cases/{id}`
- `GET /loan-cases/{id}/timeline` — merged status-history + notes, same shape as Module 6A's Timeline (decision 042)
- `POST /loan-cases/{id}/assign`
- `POST /loan-cases/{id}/request-documents`
- `POST /loan-cases/{id}/documents/verify`
- `POST /loan-cases/{id}/credit-evaluation`
- `POST /loan-cases/{id}/offer`
- `POST /loan-cases/{id}/esign-nach-kyc/complete`
- `POST /loan-cases/{id}/final-evaluation`
- `POST /loan-cases/{id}/disburse`
- `POST /loan-cases/{id}/reject`

### Loan Cases — Customer (self-service)

- `GET /loan-cases/mine`, `GET /loan-cases/mine/{id}` — read-only case status/progress (kept separate from 6B's own `GET /applications/me`, so nothing in `customer/router.py`'s response shape changes)
- `POST /loan-cases/{id}/offer/accept`, `POST /loan-cases/{id}/offer/decline`
- `POST /loan-cases/{id}/documents/upload-url`, `POST /loan-cases/{id}/documents` — new 6C-owned endpoints that still write into 6B's existing `application_documents` collection (reendered against the same `application_id`), so 6B's own document endpoints/router are never touched

### Insurance Cases — same shape, mirrored

- `GET /insurance-cases`, `GET /insurance-cases/{id}`, `GET /insurance-cases/{id}/timeline`
- `POST /insurance-cases/{id}/assign`, `/request-documents`, `/documents/verify`
- `POST /insurance-cases/{id}/underwriting`
- `POST /insurance-cases/{id}/medical-examination/schedule`, `/medical-examination/complete`
- `POST /insurance-cases/{id}/premium/accept`, `/premium/decline` (Customer)
- `POST /insurance-cases/{id}/policy/issue`
- `POST /insurance-cases/{id}/reject`
- `GET /insurance-cases/mine`, `GET /insurance-cases/mine/{id}` (Customer)
- `POST /insurance-cases/{id}/documents/upload-url`, `/documents` (Customer)

---

## 6. UI — screens only, no implementation

**Owner/Employee:**
- Loan Case List (filters: status, assigned to me / unassigned, product)
- Loan Case Details — status timeline + a single action panel whose contents change based on the case's current status (a Credit Evaluation form only appears while the case is in that status, an Offer form only while in Offer Acceptance, etc.)
- Insurance Case List
- Insurance Case Details (same pattern)

**Customer:**
- Case Status page — linked from 6B's existing Application list/detail (a new page, not an edit to 6B's own `ApplicationDetail`/list pages) showing the current stage and a read-only timeline
- Offer Review page (Loan) / Premium Review page (Insurance) — accept/decline
- Additional Documents Upload page (case-scoped, separate from 6B's own application-level upload page)

**Dashboard (Module 5, frozen — wired the same way 6A wired its own widgets in decision 044, no engine change):**
- "Disbursed" and "Rejected" widgets (already-reserved names per decision 038) get wired to real data for the first time.
- "Revenue" *may* also be wirable (sum of `disbursed_amount`) — flagged as a nice-to-have, not required for 6C's core scope.

---

## 7. Open questions — please confirm or amend before implementation begins

1. **Access model:** switch 6C to real `require_permission(...)` gating (recommended, §3) instead of continuing 6B's plain-role-check pattern?
2. **Rejection exits:** two exit points (after Credit Evaluation *and* after Final Evaluation for Loan; after Underwriting *and* after Medical Examination for Insurance) as proposed, or literally only the single exit point shown in your diagram?
3. **Insurance lifecycle stages** (§2) — not dictated in the brief; please confirm, amend, or replace.
4. **Case assignment independence** — can the Owner reassign a Case to a different Employee than whoever the Application was originally assigned to, or must they always stay in lockstep?
5. **Credit evaluation / eSign-NACH-KYC / medical examination** are all staff-recorded manual steps in this proposal (no live bureau/e-sign/NACH/diagnostic-lab integration exists in this project yet) — acceptable as the v1 scope, consistent with how every other unbuilt external integration has been handled here?
6. **Single offer vs. iterative negotiation** — one offer/premium quote per case (accept or decline only), or should counter-offers/revisions be supported?
7. **`case_document_requests`** — one shared collection with a `case_type` discriminator (as proposed) vs. two separate collections?

---

**No Module 6C implementation will begin until this proposal is reviewed and approved.**
