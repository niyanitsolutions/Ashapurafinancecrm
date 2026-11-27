# Daily Follow-up, transfer, disbursement and Top-up enhancement

Local implementation completed; final verification on 2026-11-27. No deployment, production data access, real SMS or OTP. Company scope remains one CRM database, per decision 001 and the earlier accepted scope.

## Architecture inspected

The requested docs/PRD.md and docs/REQUIREMENTS_TRACEABILITY.md did not exist at task start. Inspected the existing docs/REQUIREMENTS.md (living SRS), docs/decisions/DECISIONS.md, docs/architecture/ARCHITECTURE.md, production enhancement report and CRM identity/follow-up architecture instead. A traceability table accompanies this batch. Authentication and identity architecture are unchanged.

The pre-existing Transfer Centre is CSV/XLSX import/export, not employee reassignment; it is retained. Employee handovers use a separate Transfer tab. Existing assigned_to fields remain authoritative. Exact Application, Loan Case and working-record assignments are synchronized in one transaction; no second owner field exists.

## Implementation and safety boundaries

- Explicit Move to Daily Follow-up preserves submitted Application identity, form answers, documents, verification, customer, assignment and lifecycle. The canonical workspace and movement audit/marker commit together. No verification gate, approval or loan creation occurs. Draft Applications still require customer submission. Moved Applications leave the Document Collection application pool without changing their lifecycle status.
- The existing working record is reused. Batch context enrichment exposes IDs, email, account/Application states, dates, original Loan Case financial and Top-up details. Full Application links reuse the existing view. Original follow-up history remains append-only.
- The common handover API supports existing Leads, Applications, Loan cases, Daily follow-ups and operational issues, with explicit assign grants and current ownership checks. Active receiver access plus view/edit permissions are revalidated; an Owner can assign to their own existing Owner identity. Max 50 selected / 200 related records; the entire batch and audit commit or roll back. All changes retain IDs and versions; request receipts prevent repeated events after retries. No automatic retry follows a write conflict.
- Related-graph reads and current queue context are batched. Immutable transfer events live in existing audit_logs; last_transfer is a display summary, never ownership authority. Every affected record has an event; the queue groups primary handovers by canonical workload to avoid duplicate Application/Case/workspace entries. Previous participants retain transfer history, not ordinary record editing.
- Shared Leads with multiple Applications, broken links, archived/conflicting workspaces and oversized related graphs are rejected for individual Owner review. No sibling is silently reassigned. This is an explicit supported-architecture limitation, not an automatic repair.
- Daily Disbursed requires approved amount, disbursed amount, date, reference and remarks. The same LoanCaseService and WorkflowEngine enforce the existing Send for Disbursement lifecycle and approved-offer amount. Case financials, status history, Daily status/history and audit commit in one transaction. Plain follow-up status changes cannot invent disbursement. Standalone historical manual status labels remain non-financial.
- Top-up reuses LoanCaseService.schedule_top_up, the same embedded case details, existing calendar-month rules and scheduling popup. Audit and chronological notes commit with the case; frontend request keys make retry idempotent. No second loan, financial collection or duplicate ledger is created.
- Dashboard reads persisted cases once for financial totals. Approved totals refer to approval on the same disbursed cohort. Daily activity and transfer cohorts use their own business dates; no manual operational amounts contribute to official financial totals.

## Permission / database changes

No new collection or identity/authentication changes. Additive Application movement metadata, last_transfer display summaries, existing audit metadata and request receipts. Daily follow-up assign is added to the existing permission catalog without default Employee grants. Existing stage and resource permissions remain authoritative. Replica-set transactions are mandatory; no fallback skips audit. Four additive, nonunique indexes support primary transfer sender/recipient queries and legacy string Application/Lead relationships: handover_from_employee_id, handover_to_employee_id, followup_applicationrelationship and followup_leadrelationship. Existing unique indexes remain intact. Transaction guard epochs contend with concurrent assignment changes. No historical assignment backfill is performed.

## Validation

- Relevant integrated backend suite: **116 passed**, including existing Daily, movement, workflow and Loan behavior. Final new-feature plus existing Top-up regression run after subsequent fixes: **39 passed**. Tests use disposable local replica-set MongoDB databases and verify transaction rollback, stale writes, retry receipts, transfer chains and financial consistency.
- Ruff on every changed/new Python file: **passed**.
- Frontend ESLint: **0 errors**, eight existing fast-refresh warnings.
- TypeScript compilation and production build: **passed**. Existing bundle-size warning remains.
- Full mypy check: **117 existing errors in 12 files**. Normalized file/message comparison against identity-mypy-reviewed.log reports **zero added or removed diagnostics**; the repository-wide type baseline remains unresolved.
- Full frontend Vitest suite: **529 passed**, zero failures or pending tests (handover-frontend-complete.json).
- Real Chrome journeys at **390, 768 and 1366 pixels passed** against local FastAPI and disposable replica-set MongoDB: movement, transfer, sender denial/history, receiver disbursement, shared Top-up and original Application context. Final persistence assertions verify exact case IDs, preserved documents/answers/customer identity and current ownership; **1 integrated browser test passed in 69.76 seconds**. Evidence: [browser results](screenshots/daily-handover-2026-11-26/results.json), with 18 screenshots in the same folder. No document-level horizontal overflow was observed.
- git diff --check: passed.

The final regression work corrected real HTTP serialization/version conflicts in Daily disbursement, retained mandatory Bank/NBFC selection, and made explicit disbursement dates and Top-up calendar-month calculations consistent in IST. No automated test sends SMS/OTP or accesses production.

## Deployment and rollback

Not deployed. Matched frontend/backend artifacts, Owner approval, backups and staging verification are required. Keep existing unique indexes and histories. Do not backfill movement or transfer events for historical assignments. Roll back matched artifacts together; retained additive data must not be deleted or converted into duplicate users/records. Reassignment back is a new audited transfer, never deletion of prior history. Financial reversals require the existing authorized business process, not a destructive rollback.

## Status

Implemented locally; verification results above. No external configuration is required. Owner approval, staging checks and production deployment are separate steps and have not been performed.

## API and integration map

| Method / path (under /api/v1) | Purpose |
| --- | --- |
| POST /daily-operations/applications/{id}/move | Submitted Application to canonical Daily workspace |
| GET /daily-operations/applications/{id}/workspace | Existing workspace and original context |
| POST /daily-operations/handovers/context | Batched visible record versions and transfer summaries |
| POST /daily-operations/handovers/receivers | Scoped active receiver eligibility |
| POST /daily-operations/handovers | Atomic selected graph transfer and retry receipt |
| GET /daily-operations/handovers | Filtered, paginated current work and participant history |
| GET /daily-operations/handovers/{collection}/{id}/history | Authorized chronological transfer history |
| POST /daily-operations/follow-ups/{id}/disburse | Existing Loan lifecycle plus Daily financial update |
| GET /dashboard/followup-metrics | Scoped persisted financial/activity metrics |

Existing Loan Top-up routes and service remain the scheduling authority. Existing CSV Transfer Centre remains separate. Eligibility checks honor stage-specific permission overrides rather than combining grants. Financial context is hidden when Loan view permission is absent. Source roots require assign; linked mirrors require edit. Recipients require view/edit across the affected graph.

## Performance and operational limits

Transfers select at most 50 roots and 200 related records. Relationship and display-name queries are batched; permission decisions are cached per distinct scope. Receiver candidates are searchable and bounded to 50. Transfer history returns at most 500 events with an explicit truncation indicator. Queue results are paginated, filterable and ordered by newest/oldest. Dashboard summaries are scoped, with bounded Employee summaries. These are functional/per-query bounds, not a production load benchmark.

A shared Lead with multiple Applications needs Owner relationship review before transfer. Inconsistent historical links are rejected rather than repaired automatically. Missing historical employee profiles display immutable IDs as fallback. The company boundary is the existing single-company database; this batch does not introduce tenant membership.

## Staging acceptance still required

Review effective Employee assign grants and recipient stage access; review query plans and index rollout on production-sized data; test matched artifacts against staging replica-set durability settings; verify backup/restore and Owner acceptance. Local tests do not certify production load or deployment. Existing mock-session tests remain useful for legacy behavior; real replica-set tests provide the transaction evidence for this batch.

## Changed files

- `backend/app/features/customer/models.py`
- `backend/app/features/customer/service.py`
- `backend/app/features/daily_operations/catalog.py`
- `backend/app/features/daily_operations/handover.py`
- `backend/app/features/daily_operations/linked.py`
- `backend/app/features/daily_operations/router.py`
- `backend/app/features/daily_operations/service.py`
- `backend/app/features/daily_operations/workspace_context.py`
- `backend/app/features/dashboard/followup_metrics.py`
- `backend/app/features/dashboard/router.py`
- `backend/app/features/leads/document_collection.py`
- `backend/app/features/leads/service.py`
- `backend/app/features/loan_management/financial_commit.py`
- `backend/app/features/loan_management/mappers.py`
- `backend/app/features/loan_management/schemas.py`
- `backend/app/features/loan_management/service.py`
- `backend/app/features/workflow_engine/engine.py`
- `backend/app/features/workflow_engine/models.py`
- `backend/app/shared/assignee_names.py`
- `docs/CRM_IDENTITY_AND_FOLLOWUP_ARCHITECTURE.md`
- `docs/DAILY_FOLLOWUP_TRANSFER_DISBURSEMENT_ENHANCEMENT_REPORT.md`
- `docs/REQUIREMENTS.md`
- `docs/REQUIREMENTS_TRACEABILITY.md`
- `frontend/src/app/router.tsx`
- `frontend/src/components/pages/CaseListPage.test.tsx`
- `frontend/src/components/pages/CaseListPage.tsx`
- `frontend/src/features/customer/pages/StaffApplicationDetailsPage.test.tsx`
- `frontend/src/features/customer/pages/StaffApplicationDetailsPage.tsx`
- `frontend/src/features/daily_operations/ApplicationOperationsContext.tsx`
- `frontend/src/features/daily_operations/DailyOperationsPage.tsx`
- `frontend/src/features/daily_operations/DailyTopUpPage.tsx`
- `frontend/src/features/daily_operations/DailyUpdateLayout.test.tsx`
- `frontend/src/features/daily_operations/HandoverQueue.tsx`
- `frontend/src/features/daily_operations/HandoverTools.test.tsx`
- `frontend/src/features/daily_operations/HandoverTools.tsx`
- `frontend/src/features/daily_operations/MoveToDailyFollowUp.tsx`
- `frontend/src/features/daily_operations/RecordForm.tsx`
- `frontend/src/features/daily_operations/navigation.ts`
- `frontend/src/features/dashboard/components/FollowUpMetrics.tsx`
- `frontend/src/features/dashboard/pages/DashboardPage.tsx`
- `frontend/src/features/leads/components/MoveApplicationToLoanManagementModal.test.tsx`
- `frontend/src/features/leads/components/MoveApplicationToLoanManagementModal.tsx`
- `frontend/src/features/leads/components/UpdateStageModal.tsx`
- `frontend/src/features/leads/pages/DocumentCollectionPage.test.tsx`
- `frontend/src/features/leads/pages/DocumentCollectionPage.tsx`
- `frontend/src/features/leads/pages/LeadListPage.test.tsx`
- `frontend/src/features/leads/pages/LeadListPage.tsx`
- `frontend/src/features/loan_management/api.ts`
- `frontend/src/features/loan_management/components/TopUpSchedulingModal.test.tsx`
- `frontend/src/features/loan_management/components/TopUpSchedulingModal.tsx`
- `frontend/src/features/loan_management/pages/DisbursementsPage.test.tsx`
- `frontend/src/features/loan_management/pages/DisbursementsPage.tsx`
- `frontend/src/features/loan_management/pages/LoanCaseDetailsPage.tsx`
- `frontend/src/features/loan_management/pages/TopUpLoanListPage.test.tsx`
- `scripts/daily-handover-ui-check.mjs`
- `tests/api/test_daily_handover_browser.py`
- `tests/api/test_daily_handover_enhancement.py`
- `tests/api/test_followup_resolution_batch.py`
