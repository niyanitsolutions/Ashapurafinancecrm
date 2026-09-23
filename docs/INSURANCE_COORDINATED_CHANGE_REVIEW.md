Insurance coordinated change review
===================================

Implemented locally for manual review. No production access, deployment, commit, push, real database mutation, migration, seed script, or environment-file change was performed. API tests use in-memory MongoDB/Redis and mocked storage checks.

Behavior and security
---------------------

1. Policy documents: PAN, Aadhaar, Address Proof, Bank Statement and Cancelled Cheque accept an optional password per document. Passport Size Photograph does not. Existing master/schema metadata remains in use, with centralized Insurance defaults resolved at read/upload time.
2. Storage reuses `app.security.encryption` (Fernet). The existing configuration supplies `ENCRYPTION_KEY`; its existing development fallback is unchanged. No new encryption system, dependency, or key was introduced.
3. The existing confirm API accepts both `password` and the alias `document_password`. Passwords are encrypted before persistence, excluded from normal document/case responses and audit metadata, and cleared on passwordless replacement. The existing authorized reveal API remains the only document-password decryption path.
4. Bank Statement and Cancelled Cheque form one required alternative group. Either verified document satisfies the Policy Login gate; neither fails. The UI shows a section-level requirement and two available choices. Submission and stage validation use the same Insurance rule. Existing schemas with only one of these types remain compatible; unrelated/custom schemas are not rewritten to add document types.
5. Applicable document cards offer Front & Back. The Insurance UI collects both files before starting the pair upload and sends one password for both. The backend retains separate existing side/version/review records, keeps the pair's password consistent, retires incompatible single/pair slots on replacement, and rejects incomplete pairs at completion gates. Draft side uploads remain possible through the existing per-file API; they cannot complete the stage.
6. Existing Preview, attachment Download, Verify, Reject, replacement, pending/verified/rejected states and historical URLs are reused. New Insurance uploads use distinct filenames to avoid overwriting same-named scans. Old single-file documents and missing password/date fields require no migration.
7. Agency Code columns are Name, Mobile, Agency Code, Agent Code, Password, Join Date, Type, Status, Actions. The existing single Agency Code column is retained. Password reveal uses the control extracted from Advisor Details and its edit-permission-gated API; values start masked and are discarded on Hide.
8. Advisor had no existing joining-date field. Optional `joining_date` now follows the Employee field name and IST-midnight storage convention. Join Date uses the existing CRM formatter. The shared edit modal has one Agency Code field and Joining Date; blank password preserves the saved credential, while a supplied password uses the existing hash/encryption behavior. Existing name display, QR/Non-QR, status and other fields are preserved.
9. Re-Eligible root cause: `move_case_to_stage` routed active cases through `reject_case`, which requires a rejection reason; the Move dialog submits only the target. The fix validates the existing graph's source-to-Rejected-to-Re-Eligible path, then performs one atomic engine transition without inventing a rejection. It preserves previous rejection data, clears the due date and automatic-transition flag, and keeps one engine history/audit event. Repeated moves are idempotent. Fresh Lead, Policy Document, Policy Login, Payment and Rejected are supported when the catalog permits their path. Policy Issued remains terminal; On Hold requires resuming first. The ARQ worker and its schedule logic are unchanged.
10. Advisor list Update opens the existing edit modal and PATCH API under the existing recruitment edit permission. Employee Update links appear for matched employees in Advisor/Agency lists and Advisor Details, and for assigned employees in the shared Recruitment/Advisor personal-information panel. They use the existing Employee form/API. That API is currently Owner-only, so these actions are Owner-only too; RBAC, sessions, authentication and tenant architecture are unchanged.
11. Recruitment and Advisor Delete use the existing Owner-only Bin API and confirmation dialog. Non-owners have no buttons and receive HTTP 403 from the API. Unpromoted recruitment records are recoverable in Bin; promoted recruitment records are protected. Advisors with policy/application/business references must be made Inactive instead. Advisors referenced by recruitment history remain recoverable in Bin beyond the usual purge date, protected by a purge guard. Child records and historical references are not orphaned.
12. Backend API changes extend existing document/schema and Advisor request/response models and register two resource keys in the existing Bin API. No duplicate document, Advisor, Employee or deletion API was introduced.

Validation
----------

| Check | Result |
| --- | --- |
| Existing Insurance policy/enhancement/ARQ, Advisor, customer-document, Bin and cleanup suites | 193 passed |
| Coordinated regression suite + manual Insurance leads + Insurance employee visibility + Employee suite | 87 passed (overlaps the coordinated suite below) |
| Final coordinated regression + Insurance policy suite | 46 passed, including 31 coordinated regression cases |
| Targeted frontend: Recruitment, customer components, Insurance and Bin | 135 passed across 24 files |
| TypeScript | Passed |
| Frontend production build | Passed; Vite warns about the existing large main bundle |
| Backend Ruff | One pre-existing RUF012 finding on `CustomerService._CASE_NEXT_ACTION`; new regression test file passes |
| Backend mypy | Five pre-existing errors in unchanged code, listed below |
| Diff whitespace check | Passed |

The first backend invocation encountered the shell's `DEBUG=release` value and then missed pytest's backend configuration. It was rerun with process-only `DEBUG=false` and explicit `-c pyproject.toml`; all reported passing runs use that configuration. No `.env` file was modified. An initial frontend run found missing permission mocks and legacy label expectations; the tests now cover the new permission dependency, and Loan labels remain unchanged. One parallel frontend run timed out; the bounded-worker rerun passed. No assertion was removed to conceal a failure.

Existing mypy findings: `customer/field_validation.py:52,54` and `auth/service.py:196` return Any; `loan_management/service.py:418` has an optional assignment mismatch; `customer/service.py:558` passes an optional ID. These lines are unchanged. Existing non-failing test output includes ARQ Redis-close deprecation warnings and jsdom's unimplemented canvas warning. Real storage/network uploads and browser visual inspection were not performed.

Tests added/extended cover optional passwords for all six document types, encryption and response/log/audit leakage, unauthorized retrieval, replacement, bank alternatives, single/two-sided completion, shared pair passwords, manual stage moves and history, joining date and blank-password preservation, Owner-only delete/restore and reference retention, Employee API denial, UI pair validation, exact Agency columns, edit-form date submission, Advisor Update visibility and Employee navigation.

Migration required: **NO**. Seed required: **NO**.

Manual verification using an existing non-production setup
--------------------------------------------------------

1. Open Policy Documents. Upload a protected document; test Preview/Download and existing authorized password retrieval. Replace it without a password and confirm the new file has no saved password.
2. Try Bank Statement alone, Cancelled Cheque alone, both, and neither. Verify required documents and confirm the Policy Login gate accepts only complete requirements.
3. Toggle Front & Back, select both scans (including same original filenames), upload, preview/download each side, reject/re-upload, and verify. Test an interrupted second upload and retry. Confirm an old single-file record still opens.
4. In Agency Code, check column order, masked/reveal/hide behavior and Join Date. Update QR and Non-QR advisors, including a blank password and a new password.
5. Move Policy Login and the other applicable stages to Re-Eligible without supplying a rejection reason. Check one new history entry and preserved rejection history. Confirm Policy Issued stays terminal.
6. As Owner, open the existing Employee editor from an applicable Advisor/Recruitment view. As a non-owner, confirm that action is absent.
7. Delete an eligible Recruitment record and Advisor, inspect Bin, then restore. Check that linked business/policy records block Advisor deletion and that non-owner direct delete requests are rejected.

Exact changed files
-------------------

Backend:

- `backend/app/features/bin/registry.py`
- `backend/app/features/bin/service.py`
- `backend/app/features/customer/mappers.py`
- `backend/app/features/customer/schemas.py`
- `backend/app/features/customer/service.py`
- `backend/app/features/insurance_management/document_rules.py` (new)
- `backend/app/features/insurance_management/service.py`
- `backend/app/features/recruitment/advisor_service.py`
- `backend/app/features/recruitment/mappers.py`
- `backend/app/features/recruitment/models.py`
- `backend/app/features/recruitment/schemas.py`

Frontend:

- `frontend/src/features/bin/useListDelete.tsx`
- `frontend/src/features/customer/api.ts`
- `frontend/src/features/customer/components/DocumentChecklist.tsx`
- `frontend/src/features/customer/components/InsuranceDocuments.test.tsx` (new)
- `frontend/src/features/insurance_management/api.ts`
- `frontend/src/features/insurance_management/pages/InsuranceCaseDetailsPage.tsx`
- `frontend/src/features/recruitment/api.ts`
- `frontend/src/features/recruitment/components/AdvisorEmployeeUpdate.tsx` (new)
- `frontend/src/features/recruitment/components/AdvisorEmployeeUpdate.test.tsx` (new)
- `frontend/src/features/recruitment/components/AdvisorPassword.tsx` (extracted)
- `frontend/src/features/recruitment/components/EditAdvisorModal.tsx`
- `frontend/src/features/recruitment/components/EditAdvisorModal.test.tsx`
- `frontend/src/features/recruitment/components/RecruitmentInfoPanels.tsx`
- `frontend/src/features/recruitment/pages/AdvisorDetailsPage.tsx`
- `frontend/src/features/recruitment/pages/AdvisorListPage.tsx`
- `frontend/src/features/recruitment/pages/AdvisorListPage.test.tsx`
- `frontend/src/features/recruitment/pages/AgencyCodeListPage.tsx`
- `frontend/src/features/recruitment/pages/AgencyCodeListPage.test.tsx`
- `frontend/src/features/recruitment/pages/RecruitmentListPage.tsx`

Regression/report:

- `tests/api/test_insurance_coordinated_changes.py` (new)
- `docs/INSURANCE_COORDINATED_CHANGE_REVIEW.md` (this report)

No Loan implementation, workflow catalog, authentication/session implementation, tenant architecture, dependency manifest, migration, seed or environment file changed. Shared document and Bin consumers were inspected and their relevant tests run.
