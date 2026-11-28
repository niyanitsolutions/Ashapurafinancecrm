# Partner Portal implementation report - 27 November 2026

## Delivery scope

Implemented locally in the existing AFS CRM. No deployment, production data/configuration change, live SMS/OTP, real documents or bank transfer was performed. Delivery validation results and remaining external readiness requirements are recorded below.

The original brief is the complete Partner Portal, KYC, referrals and commission batch. Existing Customer, Application, Loan Case, authentication, document, report, audit and notification services remain authoritative. Company scope remains the existing single-company database (decision 001). No new tenant resolver or duplicate CRM was introduced.

## Implemented workflows

| Area | Result |
| --- | --- |
| Owner accounts | Password and confirmation, visibility, temporary generation and required first-login change. Transactional mobile-unique User/profile/audit creation with stable request receipts; no OTP invitation. Existing active primary Partner identities can explicitly receive a missing profile without credential replacement. |
| Partner portal | Dashboard, Complete KYC, My Referrals, Add Customer, Generate Customer Link, Rules, Commissions, Payout History, Security, Notifications and logout within the existing authentication shell. Owner review/report tabs reuse the existing Partner navigation key; Employees retain only their existing permitted Partner list. |
| KYC configuration | Immutable published versions; protected identity/bank/conditional controls; custom fields, validation, ordering, required/hidden options, MIME/size restrictions, conditional proofs, interactive preview and agreement versions. |
| KYC submission | Prefilled identity, optional email, bank confirmation, conditional house/Aadhaar documents, selfie preview, upload/draw signature, explicit agreement reading/acceptance and consent. Encrypted drafts, completion indication, masked normal reads, authenticated version history and separate Owner document/overall decisions. Unsaved answers survive document uploads and views. |
| KYC security | Private signed encrypted staging, actual-byte validation, bounded PDF/password processing, active-content rejection, image metadata removal, application-encrypted final objects and S3 encryption. Transient PDF passwords, no temporary processing files, audited no-store reads and reasoned Owner sensitive-field reveal. Approved upload tickets and confirmations are locked. Starting an authorized revision makes KYC pending and blocks referrals until review. A new form cannot reuse an older approved file that violates its MIME/size policy. |
| Activation/lifecycle | Approved KYC and account activation are separate. Suspension blocks new drafts, links and submissions while retaining history. Name corrections require renewed identity review. Material agreement changes block activity until current versions are accepted and reviewed. |
| Manual referrals | Reuse canonical Customer/User identities and product forms/documents. Manual referrals always require Partner review, even under Direct to AFS. Save, preview and explicit saved-version submission feed existing Document Collection and reconciliation/assignment. |
| Customer links | Expiring, hashed, single-purpose tokens in URL fragments; encrypted retry copy; captured prospective mode; existing Customer login/registration return flow; same-Customer replay resumes the same Application. Owner revocation retains applications/history. |
| Customer identity | A narrowly flagged manual reservation can be activated through the existing verified registration proof and PIN flow using the exact same User/Customer/Application IDs. Existing credentials/roles are never replaced and a mobile-only historical claim is refused. |
| Attribution and duplicates | Open Customer/product applications require AFS duplicate review instead of a second referral or an automatic Partner winner. Creation serializes on the real identity. Customer/Partner attribution changes are blocked. Owner corrections require a version, reason and explicit acknowledgement of unchanged financial history, with before/after audit. |
| Commission rules | Existing rule collection with default/Partner overrides, products, effective periods, overlap prevention and new immutable versions. Active versions require a confirmed start. Fixed contracts require confirmation and explicit per-case/per-event policy. Category/trigger mismatches are rejected; Partner views show product names and the distinct Loan/Insurance earning basis. |
| Actual earnings | One calculator within the existing confirmed disbursement transaction. Actual disbursed amount only; Decimal calculation and half-up rounding. Missing/conflicting/invalid rules create explicit exceptions. Owner resolution verifies the original financial event and its date/amount. No historical Loan earning backfill. |
| Multiple tranches | Same Loan Case and original unique commission Case entry. Explicitly unfinished first disbursement, cumulative approved-amount cap, bounded event history, unique references, valid dates and final-tranche Top-up gating. Additional earnings are immutable referencing events with their own original rule/rate/date snapshots. |
| Financial review | Owner approval snapshots, holds/resume, signed adjustments and recovery balances. Reversals require a real authorized financial reversal event. Original commission amounts/rates remain unchanged. Owner/own-Partner earning history shows original and later tranche rates separately. |
| Payments | Atomic partial confirmed payments and grouped reservations for one Partner. Stable request receipts, normalized duplicate-reference prevention, balance/version checks, cancellation/release and actual-payment confirmation. Reservations never count as paid; no automatic financial retry or external transfer. |
| Reports | Persisted, scoped dashboards; distinct-case actual disbursements; allocated grouped payments; searchable Partner/product/date/status/source filters; Owner referral/product/Partner summaries and CSV export; own commission/payout statements. Original earning Partner remains identified after attribution correction. Internal Owner remarks stay out of Partner responses and statements. |
| Notifications | Existing internal inbox for account/KYC/referral/commission/payment actions, generic attributed-application status updates and bounded idempotent current-agreement notices. No external delivery or live provider verification is claimed. |

## Architecture and changed files

Detailed APIs, schema/index changes, privacy controls, date semantics, rollout and rollback are documented in [Partner architecture and operations](PARTNER_PORTAL_ARCHITECTURE_AND_OPERATIONS.md).

Core backend files are under `backend/app/features/referral_partner_management/`: account provisioning, KYC/artifact processing, canonical referrals, Owner management, the single finance calculator, payout reservations, reporting and internal notices. Existing Partner models/DTOs/mappers/repositories/routes/indexes are extended. The existing Loan financial commit and a referencing additional-disbursement service handle earnings in the transaction. Customer registration/submission/doc authorization, pending-referral list/movement gates, workflow inbox notices, shared storage signing and report export are the necessary integration points.

Frontend changes are confined to Partner pages/components/API/routing and the required existing Customer, Document Collection, Loan disbursement, Daily disbursement and Owner dashboard integration points. Existing shared form, table, modal, auth, permission and document components are reused. No new package was installed.

New regression sources:

- `tests/api/test_partner_portal_enhancement.py`: real disposable replica-set transactions, account uniqueness/idempotency/rollback, KYC versions/encryption/private files/conditions/re-upload, exact registration ownership proof, canonical referrals/link replay, duplicate policy, original/multiple disbursement earnings, exceptions, rate snapshots, partial/grouped payout concurrency/rollback/overpayment, adjustments, report/API isolation, attribution audit and agreement notices.
- `tests/api/test_partner_portal_browser.py` and `scripts/partner-portal-ui-check.mjs`: real local FastAPI/Chrome with synthetic private storage and disposable data; external HTTPS blocked.
- `frontend/src/features/referral_partner_management/pages/PartnerPortal.test.tsx`: accounts, KYC conditions/locking/unsaved state/private upload, referral return, monetary reservations/confirmation, valid searchable report options, earning rates and Owner/Employee navigation boundaries.
- Existing `test_referral_partner_management.py` preserves legacy Lead privacy/edit/history, rule snapshot, settlement and Employee/Owner authorization coverage. Fixtures now use the explicitly changed password/KYC workflow; historical Lead reads remain tested. Loan polling is checked not to manufacture historical earnings.

Requirements, traceability, architecture, API, database/collection and security documents were updated alongside this report.

## Validation evidence

| Check | Evidence |
| --- | --- |
| Affected backend regression | **447 passed**, covering Partner, Auth, Customer/PIN/documents, Loan visibility/redesign, Workflow, Reporting, Reminders, Bin, Leads, Daily Operations/handover and case-status controls. |
| Expanded final Partner backend | **39 passed**, including approved-upload locking, revision eligibility, file-policy reuse, category/trigger checks and own-rule metadata (final local run). |
| Full frontend | **544 passed in 105 files**, including Owner/Employee navigation and the final Partner UI regressions. |
| TypeScript / production build | **Passed** (`tsc -b` and Vite production build), including final navigation and rule presentation. Existing large-chunk warning remains. |
| ESLint | **0 errors**, the same **8 existing fast-refresh warnings**. |
| Ruff | **Passed** for every changed/new Python file. |
| Mypy | **117 errors in 12 existing files**, exactly matching the prior baseline after normalizing paths/line numbers: **no added or removed errors**. No unrelated typing cleanup was made. |
| Responsive browser | **33 screen/viewport checks passed** at **390/768/1366**, including KYC re-upload, activation, reviewed manual referral, link claim, real local disbursement, partial payment, report filters/navigation and own commission/payout statement downloads. The real local FastAPI/Chrome integration test passed in 85 seconds. |

Final logs are `partner-final-backend.log`, `partner-final-complete-frontend.log`, `partner-final-build.log`, `partner-final-lint.log`, `partner-final-mypy.log` and `partner-final-browser.log`. Raw local logs are in the ignored `scripts/dev/.local-run/partner-*.log` files. Synthetic screenshots/results are in `docs/screenshots/partner-portal-2026-11-27/`. Failed intermediate harness runs were corrected rather than counted as passes (test fixture discovery, private-storage CORS and the existing Mark Disbursed button label). Screenshot inspection also caught and corrected an actual Owner report picker exceeding the API's 100-row limit; Partner search and regression coverage now enforce that contract.

An optional **1,905-case repository-wide API sweep** was interrupted after it stopped reporting progress around 60%; it is **not** counted as a complete pass. The complete 447-case affected-module suite and final dedicated Partner suite provide the scoped regression evidence above. Skipped opt-in browser/provider tests are not counted as passes.

## Existing data and deployment safety

- No production migration, reset, identity merge, Role conversion, KYC approval migration, historical event synthesis or earning recalculation ran.
- The original unique `commission_entries.case_id` index remains. Original earning/base/rate/rule fields are immutable; additional earnings/adjustments use `commission_entry_events` and referencing header totals. Each earning has an actual source/event identity.
- New additive collections are versioned KYC forms/submissions/documents/tickets, referral links, commission events, payouts and exceptions. Existing audit, notifications and counters are reused. Indexes are declared in the existing initializer.
- Existing Partners must complete reviewed KYC before new referrals. Existing Loan Cases default to final disbursement. Primary Customer/Employee identities do not acquire an invented secondary Partner role; incompatible identities require an explicit architecture decision rather than a duplicate User.
- The generic Bin cannot delete Partner identities; suspension is the retained lifecycle. Customer/Application/financial/audit history is preserved.
- Do not blindly roll back to the old payout/Loan polling worker after new events/payments exist. Retain encrypted objects/keys and ledger/event/payout records; disable affected writes and apply a compatible forward correction. See the detailed rollback plan.

## External readiness and explicit limits

Owner/legal approval of agreement content, informed consent, KYC purpose/retention/legal holds, encryption-key continuity, private S3 IAM/CORS/lifecycle and a controlled staging rehearsal remain required before release. Mongo ticket TTL does not remove S3 objects; the staging-prefix lifecycle must be configured operationally. Retention is a review date, not an automatic legal destruction authority. No malware scanner, government identity verification or bank-ownership provider was found or claimed.

No existing Loan financial reversal workflow was invented. Commission reversal requires a real authorized reversal event; ordinary signed Owner adjustments remain separately audited and held for review. No historical Loan commissions were manufactured. Existing confirmed-policy Insurance processing continues through the same calculator.

Some non-transactional legacy workflow status notices are best-effort after the already committed status; a sanitized warning directs operations to its persisted audit if inbox delivery fails. Transactional financial status notices commit with their existing transaction. External SMS/email delivery remains outside this local validation.

No production deployment is authorized or performed by this report.
