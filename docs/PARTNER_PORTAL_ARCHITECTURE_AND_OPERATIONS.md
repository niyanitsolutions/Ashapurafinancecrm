# Partner portal architecture and operations — 27 November 2026

This document describes the local implementation. It does not authorize deployment, production migration, live OTP/SMS, legal verification or payments through an external bank.

## Identity and authorization

One existing CRM database represents one company (decision 001). No tenant architecture was introduced. The existing mobile-unique `users` identity remains authoritative. Owner creates a primary Partner password account and associated `referral_partners` profile in one replica-set transaction, together with its audit receipt and internal notice. Passwords use the existing bcrypt policy; a generated temporary password sets the existing mandatory password-change flag. Passwords are never returned after creation or recorded in receipts. No invitation OTP is sent.

An explicit association can attach a missing Partner profile to an existing active primary Partner login without replacing its credentials. A mobile belonging to another role, a deleted identity or an existing Partner profile conflicts. There is no invented multi-role membership. Employees retain existing permission-scoped Partner list access; credentials, KYC review, rule changes and financial decisions remain Owner-only.

Partner APIs derive the profile from the authenticated User. KYC documents require Owner or the exact owning Partner. A temporary-password account must change its password first. A suspended Partner may read its retained history and manage security, but cannot edit onboarding, create links, draft or submit referrals. Referral eligibility requires account-active, approved KYC, activated Partner status, permitted active product and the current required agreement versions. Normal Customer, Employee and Owner authentication methods remain in use.

Manual referrals reuse a primary Customer identity/profile. A newly reserved Customer is pending, unverified and has no credentials. The existing OTP registration flow can activate only that exact pending reservation after ownership proof; it cannot claim an arbitrary historical account or replace credentials. Verification must refer to the same reserved User ID. Existing credentialed identities still receive the existing sign-in/recovery outcome. No new OTP transport was introduced.

## KYC and private storage

`partner_kyc_forms` stores immutable published versions. Identity, bank, Aadhaar format, house-dependent proof, selfie and signature controls cannot be removed, hidden or weakened. Owner can add/reorder/configure custom fields, validation, MIME/size limits, conditional display and required agreement versions. Existing submissions keep their form version. Reused documents are rechecked against that submission version's MIME/size rules; only applicable document parts are included in its immutable review snapshot. At least one available agreement must be published before onboarding can be submitted.

`partner_kyc_submissions` stores encrypted scalar values, the profile identity snapshot, exact form/agreement references, consent/acceptance timestamps and review history. PAN and bank account numbers are masked on normal reads. Owner reveal requires a reason and an access audit. Submitted/under-review/approved KYC is locked; a reviewed re-upload request or new required terms opens the appropriate revision. A name correction requests renewed identity review. Account activation is a separate Owner action after KYC approval. Upload tickets and confirmations also reject locked approved submissions. Starting an authorized revision marks KYC pending in the same transaction, blocking new referrals until review completes. Reused files must satisfy the newly pinned form MIME and size policy.

Upload tickets are random capabilities with hashed server records, a ten-minute expiry and single confirmation. Tickets bind Partner, User, field, part, MIME, exact byte size and form limits. Staging URLs require S3 AES256 headers. Confirmation checks actual bytes and uses the existing bounded PDF/password parser, then rejects active/embedded PDF content and strips image metadata. Final bytes are application-encrypted and stored with S3 encryption. PDF passwords remain transient, with no temporary files. A replacement creates an immutable version; rejection reasons and old objects remain in history. Each document is reviewed separately before overall approval. Document access is authenticated, audited and returned with `Cache-Control: no-store`.

The implementation does **not** claim Aadhaar, PAN, bank ownership, legal consent sufficiency or malware clearance by an external authority. A PDF is not official authentication. Storage must remain private; deployment requires an approved encryption key, private bucket/IAM/CORS and a staging-prefix expiry lifecycle. Mongo ticket TTL alone cannot delete S3 staging objects. File records carry a configured retention-review date, not an automatic legally authorized destruction date. Owner/privacy review must establish retention, legal holds and an approved deletion process before production use. Partner identities are protected from the generic Bin; suspension preserves the complete referral and financial history.

## Canonical referrals

`applications.referral_attribution` references the Partner and referral, source, original timestamp, mode, manual/link origin and AFS submission/review timestamps. Customer and Application identities, product forms, document upload, validation and case services are reused. Manual referrals always snapshot Partner review, even when that Partner's link mode is Direct to AFS. Partners explicitly review and submit saved information. Link mode is prospective and captured when the link is generated.

Referral links use random tokens, store a hash and encrypted retry copy, expire in at most 30 days and bind once to an authenticated Customer/Application. The token is carried in a URL fragment and submitted in the claim JSON body, avoiding ordinary URL/server referrer logs. Customer login/registration uses the existing return flow. Replay by the same Customer resumes the same Application; another Customer cannot claim it. Owner can revoke links without deleting applications or history.

Pending Partner review is excluded from Document Collection, lazy Loan Case creation and Daily linked movement. Only AFS submission makes the canonical Application eligible for existing reconciliation and assignment. Original attribution is locked against Customer/Partner edits. Owner correction requires version, reason and explicit acknowledgement of financial impact; before/after attribution is audited. Existing commission snapshots/payments remain with their original Partner. Further earnings with conflicting attribution create a review exception. Staff form corrections continue through the existing versioned, audited Application edit workflow.

Duplicate policy: the same Customer and product cannot receive another Partner referral while an application remains open. Creation serializes on the existing User identity and checks canonical applications/cases within the transaction. The generic conflict discloses no other Partner/customer/application details. A completed final disbursement, issued policy, rejection or closed case permits a new lifecycle. Existing applications are not deleted, merged or silently reassigned. Exact request retries return their original record. New referral requests requiring a business exception must first receive AFS duplicate review; there is no automatic attribution winner.

## Commission and payments

There is one active calculator, extending the existing ledger. Initial Loan commission runs inside the existing confirmed disbursement transaction. Additional actual tranches are recorded on the same Loan Case and reference immutable financial audit events. The first disbursement must explicitly declare additional tranches; cumulative disbursement cannot exceed the approved amount, references cannot repeat and dates cannot precede the prior event or exceed today's IST business date. Top-up waits for the final tranche and uses its date. Existing cases default to final; no historical events are fabricated.

Percentage earnings use Decimal, two-decimal monetary inputs and half-up rounding. The basis is the event's **actual disbursed amount**, never requested/sanctioned/undisbursed approval. A default rule can be overridden by Partner/product/category specificity and effective period. Overlapping equal-scope rules are rejected under a shared transaction guard. Updates create a new rule version; original earning snapshots are immutable. Active new rules require an effective start. Fixed contracts additionally require explicit confirmation and a per-case/per-event policy. Missing, ambiguous or invalid rules create visible `commission_exceptions` in the disbursement transaction, not a guessed amount.

The unique `commission_entries.case_id` index remains. Its original amount/base/rate/rule/source-event snapshot is retained. Additional earnings and authorized signed adjustments are immutable `commission_entry_events`; header additional/adjusted/paid/outstanding/reserved totals support balance checks. Exception resolution re-verifies the original persisted financial event and event amount, applies an eligible unambiguous rule for that date and records Owner authorization. The worker no longer creates historical Loan earnings. Existing confirmed Insurance policy commissions use the same calculator with their separate premium/policy trigger.

Approval, hold/resume, adjustments, direct partial payment and grouped reservations use replica-set transactions and version guards. New earnings require approval again. An adjustment places the balance on hold; an overpaid reversal creates a recovery balance. A commission reversal requires an actual authorized financial reversal event for that same Loan Case. There was no existing Loan reversal workflow to invent; an Owner adjustment cannot pretend one exists.

Initiated payments reserve approved available balances for one Partner across up to 100 entries. They do not count as paid. Confirmation requires an actual-payment acknowledgement, method, reference and non-future date; cancellation releases every reservation. Direct partial payments subtract existing reservations. Deterministic request receipts, natural payment-reference checks and a unique normalized payment key prevent duplicates. Financial conflicts return a refresh/review outcome; there is no automatic retry. CRM does not initiate a bank transfer. Partner history/exports omit Owner remarks. CSV statements reuse the existing report export/audit service.

## Reporting, notifications and dates

Owner and own-Partner dashboards read persisted canonical/financial data. Actual disbursement reporting unfolds event snapshots and counts each case once; a legacy persisted amount is a reporting fallback, never an earning backfill. Grouped payments allocate product-specific totals without treating reservations as paid. Owner referral reports filter by referral date, Partner, product, manual/link source, Application status, disbursement status and commission status. Report dates select referral cohorts; displayed financial totals are the retained lifetime totals for that cohort, with the original earning Partner identified separately after an attribution correction. Summaries are computed on the server. CSV export is authorized/audited and formula-safe.

Internal notices reuse the existing `notifications` inbox, not a new SMS/email engine. Account/KYC/referral/commission/payment actions notify the appropriate Partner and, for Partner/Customer events, Owners. Required-agreement notifications use bounded, idempotent existing checkpoints. External delivery and provider verification are not claimed. All business dates use IST boundaries and persisted UTC instants.

## Additive API surface

Existing `/referral-partners`, `/commission-rules`, `/commission-entries` and authentication APIs remain canonical.

| Scope | Routes, relative to `/api/v1` |
| --- | --- |
| Partner onboarding | `GET /partner-portal/kyc/configuration`; `GET/PUT /partner-portal/kyc`; `POST /partner-portal/kyc/submit` |
| Private files | `POST /partner-portal/kyc/uploads`; `POST /partner-portal/kyc/uploads/confirm`; `GET /partner-portal/documents/{id}` |
| Owner KYC | `GET/POST /partner-management/kyc/configuration`; `GET /partner-management/kyc/{partner}`; `POST .../review`, `.../reveal`; `POST /partner-management/documents/{id}/review`; agreement upload/confirm routes |
| Settings | `PUT /partner-management/{partner}/settings`; existing approve/deactivate actions |
| Canonical referrals | `GET/POST /partner-portal/referrals`; `GET/PUT .../{application}`; `POST .../{application}/submit`; `GET .../{application}/documents`; `GET /partner-portal/forms/{product}` |
| Secure links | `GET/POST /partner-portal/links`; Customer-only `POST /partner-referral/claim`; Owner `GET /partner-management/links`, `POST .../{link}/revoke` |
| Owner review/report | `GET /partner-management/referrals`; `PUT .../referrals/{application}/attribution`; `GET /partner-management/report` (`export=true` for CSV) |
| Finance | `POST /commission-entries/{entry}/payouts`, `.../decision`, `.../adjustments`; `GET/POST /partner-management/payments`; `POST .../payments/{id}/confirm`, `.../cancel`; Owner exception list/resolve; Owner/own-Partner `GET /commission-entries/{entry}/history` |
| Partner reports | `/partner-portal/metrics`, `/rules`, `/payouts`, `/payouts/statement`, `/commission-statement`; own existing commission entry list |
| Loan tranches | `POST /loan-cases/{case}/disbursements`, using existing Loan stage authorization |

KYC document history, referral/link/ledger/payment/exception lists are paginated. Reports are bounded to 10,000 rows and require narrower filters beyond that limit. Input form/document sizes are bounded. No unauthenticated document download route is introduced.

## Database rollout and rollback

New collections: `partner_kyc_forms`, `partner_kyc_submissions`, `partner_kyc_documents`, `partner_kyc_uploads`, `partner_referral_links`, `commission_entry_events`, `commission_payouts`, `commission_exceptions`. Existing Users, Partner, Application, Loan Case and commission records receive additive fields. Audit, notification and counter infrastructure is reused.

Indexes are declared in the existing Partner index initializer: unique profile User, form version, ticket hash, link token hash, Partner/request key, Application referral request key, financial event key, payment key and source/event exception pair; paginated Partner/date/status indexes; ticket TTL. The original unique commission Case index is unchanged. Original and additional earnings retain their actual financial dates and have an authorized paginated history view. Run the normal initializer only under the established controlled rollout. Inspect unique-index compatibility and replica-set support in staging first.

There is **no bulk data migration**: no credential reset, role conversion, KYC approval backfill, attribution reassignment, historical disbursement synthesis or commission recalculation. Existing primary identities remain authoritative. Existing Partners must complete reviewed KYC before new referrals. Existing Rules/earnings remain readable; unconfirmed legacy fixed-event policies create review exceptions for new events.

Before release, snapshot the database and encrypted object metadata, verify encryption-key continuity, exercise private S3/CORS/lifecycle settings in staging, publish legally approved agreements and verify the complete Owner/Partner/Customer journeys. None of these production operations has been performed locally.

Rollback must preserve the new collections, encrypted documents, keys and financial/event snapshots. Never drop new payment/earning records or reset original ledger totals to make old code run. Once new financial events exist, disable affected write surfaces and use a compatible forward correction; a blind rollback to the old payout/calculation worker would risk duplicate or incomplete accounting. Keep new Loan backfill behavior disabled. Review initiated reservations before any service change.
