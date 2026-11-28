# Enhancement requirements traceability

This additive file traces the 2026-11-26 Daily Follow-up batch. Existing living requirements remain in REQUIREMENTS.md; architecture decisions remain in decisions/DECISIONS.md.

| Requirement | Implementation | Validation |
| --- | --- | --- |
| A: movement without verification gate | daily_operations/linked.py, MoveToDailyFollowUp | Real replica-set document-state/idempotency/rollback tests |
| B: original Application workspace and history | workspace_context.py, DailyOperationsPage, ApplicationOperationsContext | Original identities/documents preserved; append-only history |
| C-G: atomic authorized bulk handover and permanent history | handover.py, HandoverTools, HandoverQueue, existing module lists | Ownership chain, stale/concurrent/invalid receiver, audit-failure rollback |
| H: shared disbursement | LoanCaseService, financial_commit.py, WorkflowEngine transaction branch, RecordForm | Shared ledger/workspace, monetary validation, rollback and duplicate rejection |
| I: shared Top-up | existing schedule_top_up + transactional persistence, DailyTopUpPage | Same case, eligibility/note/request receipt |
| J: Dashboard | dashboard/followup_metrics.py, FollowUpMetrics | Persisted, scoped, date-filtered financial aggregation |
| K: server list filtering | existing lists; handover server aggregation/pagination | Permission-scoped record and history endpoints |

No deployment, automatic historical merge, production migration or live SMS is authorized by this document. Full results and limitations: DAILY_FOLLOWUP_TRANSFER_DISBURSEMENT_ENHANCEMENT_REPORT.md.


## Partner portal batch - 27 November 2026

| Requirement | Implementation | Evidence |
| --- | --- | --- |
| Owner password account, uniqueness, temporary password | accounts.py, existing User/auth, Partner list | Replica-set account/idempotency/duplicate-role/audit rollback tests; frontend account test |
| Protected configurable KYC, private docs, review/reupload | portal_models.py, kyc.py, artifacts.py, PartnerKycPage, PartnerManagementPage | Real Mongo PDF/image conditional KYC journeys; frontend conditional/lock/upload/unsaved-state tests |
| Canonical manual/link referrals and locked attribution | referrals.py, CustomerService, management.py, Document Collection | Identity reuse, token binding/replay, duplicate rejection, exact registration proof, API boundary/correction tests |
| Actual disbursement earnings, immutable versions and multiple tranches | existing financial_commit.py, finance.py, disbursement_events.py | Real Loan service financial transaction, three-tranche/rate snapshot and missing-rule resolution tests |
| Approvals, holds, corrections, partial/grouped payouts | finance.py, payouts.py, existing ledger UI, PartnerPayments | Overpayment/retry/reservation/mixed-Partner rollback/reference tests; frontend selection/acknowledgement tests |
| Scoped reporting, statements and notices | reporting.py, existing report exporter/notifications, Partner reports/pages | Own/Owner metrics/report and API isolation tests; responsive browser evidence in implementation report |

Scope, migration and outstanding external prerequisites: [architecture](PARTNER_PORTAL_ARCHITECTURE_AND_OPERATIONS.md). Final validation results belong to [implementation report](PARTNER_PORTAL_IMPLEMENTATION_REPORT.md); a test that did not run is not a pass.
