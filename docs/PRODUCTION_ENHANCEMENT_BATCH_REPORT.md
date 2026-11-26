# Production enhancement batch report

## 2026-11-26: unified identity, global search and Daily Follow-up

Local implementation of all five sections in the current brief. No production deployment, production data access/change, automatic historical merge, real SMS or OTP sending was performed. The existing single-company database scope remains unchanged. Local validation is complete with the baseline limitations and skipped checks recorded below; this document is not rollout approval.

### Implemented behavior

1. **Independent global/module search.** Global Application results no longer append customer_id; Customer results open the Customer details page. Full valid Indian mobile searches share canonical and +91 matching; foreign prefixes are not silently suffix-matched. Normal Application Back returns to Document Collection. Module modal Close preserves intentional module filters, page and page size. Explicit Customer focus links remain available in their existing workflows.
2. **Owner-reviewed Employee access.** Mobile inputs and User identities use the existing shared Indian mobile normalizer. All User insert paths check historical formatting and deleted identities before writing; existing canonical unique indexes arbitrate concurrent new writes. An existing Employee opens its existing profile; invalid/conflicting/unverified/deleted identities are refused. Verified active Customer/Partner identities with real profiles can receive explicit Owner-confirmed Employee access using the same User. Their primary role, profile and PIN/password hashes remain unchanged. A versioned User update, existing uniqueness indexes, Employee insert and audit commit atomically. No new automatic permission grant policy is added.
3. **One Application workspace.** Manual Add first searches existing identities and requires explicit Application selection. It reuses linked-follow-up, the existing RecordForm and append-only activity history. Matching identities cannot bypass an Application workspace by entering a different date or separate-activity reason. Application-linked historical activity keys use their workspace identity, keeping sibling Applications independent on the same date. Genuine new prospects remain standalone/unverified. Owner-reviewed Customer-only follow-ups remain possible when no Application exists.
4. **Historical Owner review.** Read-only previews now show original context, candidate identities, match reasons and Application choices. Linking preserves record ID, notes, dates, history and assignment, rejects incompatible source references or an existing Application workspace, and commits audit in the same transaction. Latest unchanged links can be undone. Reject/leave-standalone decisions do not rewrite records; explicit manual-review decisions mark review pending. A bounded read-only duplicate report installs no indexes and performs no merge.
5. **UI and role boundaries.** The list labels linked, standalone and pending-review records. Existing options, banks, dates, editing, Bin and linked source controls remain. Sessions carry one active_role; Customer sessions never gain Employee permissions after association. Refresh revalidates access. Employee self-service and permission-gated routes use that same role context. Added Employee deactivation leaves the primary account active. Customer/Partner sessions do not count as the added Employee's attendance. The Employee onboarding selector now fits the mobile card. Mandatory password-change inputs now have explicit IDs so their existing labels work for keyboard and browser automation.

### APIs and database changes

| API | Change |
| --- | --- |
| GET /employees/identity-preview | Owner-only safe account/profile summary; no credential hashes. |
| POST /employees | Optional explicit identity association fields: existing_user_id, identity_version, identity_confirmed, identity_reason; transactional create/associate. |
| POST /auth/login | Optional login_role=employee authenticates added Employee credentials; default primary-role sign-in remains. |
| POST /auth/refresh; GET /auth/profile; POST /auth/change-password | Preserve/validate active session role; Employee password changes leave primary credentials intact. |
| GET /daily-operations/follow-up-identities | Read-only permission/assignment-scoped identity choices. |
| POST /daily-operations/linked-follow-up | Existing canonical workspace reuse, historical-reference conflict checks, transactional creation/audit and exact Lead binding. |
| POST/PATCH /daily-operations/follow-ups | Existing APIs retained; server identity guards and transactional linked activity/history/audit. |
| GET /daily-operations/identity-review/preview | Enriched existing read-only reconciliation preview. |
| POST /daily-operations/identity-review/{id}/link and /rollback | Explicit Application choice, uniqueness/assignment checks and reversible versioned reference changes. |
| POST /daily-operations/identity-review/{id}/decision | Owner-only individual reject, leave standalone or mark manual review. |
| GET /daily-operations/identity-review/duplicates | Bounded read-only duplicate preflight, IDs and truncation flags only. |

No new collection or production index is introduced. Additive fields are users.employee_access, sessions.active_role and Daily Follow-up review metadata/history. Existing users.mobile, employees.user_id/email/employee_code and Daily working/import/activity key uniqueness remain authoritative. No mobile backfill, Customer merge, User role conversion, application ownership change or historical workspace consolidation runs automatically. Failed/concurrent creation can leave a reserved sequence gap without creating a duplicate Employee.

Authorization reuses the existing Owner gates, Employee permissions and live assignments. Access Control and Recruitment dependencies were updated because they previously loaded the primary User directly; they now honor the same authenticated session role. This changes role resolution, not permission grants. Canonical mobile compatibility lookup uses anchored normalization matching and refuses historical collisions. See CRM_IDENTITY_AND_FOLLOWUP_ARCHITECTURE.md for the full decision rules.

### Validation results

| Check | Result |
| --- | --- |
| Full frontend suite, final source | 523 passed; 0 failed; 0 skipped/pending. |
| Broad backend suite | 1,828 passed, 2 failed, 14 skipped. The two failures were the pagination fixture and concurrent-writer expectation described below; both pass in the final targeted rerun. This complete suite was not rerun afterward. |
| Final targeted backend regression | 139 passed, 1 new synthetic-fixture failure, 134 existing mongomock datetime warnings. Covers authentication, Employee/account management, registration, search, historical identity and Daily Updates. |
| Corrective complete follow-up rerun | 7 passed; 0 failed/skipped. Resolves the targeted run's missing synthetic import-key failure and verifies final Application-code projection and same-day sibling independence. All 140 distinct targeted cases therefore pass across these runs. |
| Real local API/browser | 1 passed in 80.15s; all journeys passed at 390, 768 and 1366 pixels. |
| TypeScript / production build | Passed on final frontend source; existing large-chunk warning remains. |
| ESLint | 0 errors, 8 existing fast-refresh warnings. |
| Ruff / formatting / whitespace | Passed for changed/new Python; changed ranges formatted in existing source, new files fully formatted; git diff --check passed. |
| Whole-app strict mypy baseline comparison | 117 existing errors before and after, 0 introduced; 446 current source files checked. Whole-app mypy is not green. |

The broad suite's 14 skipped cases are not counted as passes. Dedicated real replica-set tests and the separately enabled browser journey ran afterward on disposable loopback databases. Real integration coverage includes concurrent User/Employee association, primary Customer/Partner credential preservation, role-bound API/refresh/deactivation, audit-failure rollback, registration, canonical workspace reuse, explicit historical link/undo and independent sibling activity keys. The local w=1 test setting does not establish crash-recovery durability. No production verification is claimed.

Browser evidence includes retained module filters and browser Back/refresh, clean global navigation, two Application choices for one Customer, inline failed-save input retention and successful follow-up save, Owner Employee association, added Employee password login/mandatory password change/dashboard, and preserved Customer PIN portal login at all three widths. Synthetic database assertions confirm stable User/profile references, primary credential hashes, original activity history and untouched sibling/Customer facts. The failed intermediate browser artifact was removed after the final pass.

The unit suite's mongomock adapter accepts synthetic session arguments only. It deliberately does not model MongoDB locking, durability or rollback; no transaction guarantee is claimed from those mocks. Dedicated disposable loopback replica-set tests exercise real concurrency, audit-failure rollback, User/profile preservation, role-bound sessions and historical linking. Browser tests use a real local API, synthetic records and blocked external network access. The owned test replica used w=1 during the broad local checks to avoid per-write journal waits; this is not a production durability or crash-recovery test.

An exact Application-code chooser lookup omitted the Customer user_id projection, incorrectly marking valid relationships for review; the projection and regression assertion now cover that path. An initial browser fixture contained two rows for one Application and was correctly rejected by the new duplicate guard. It now uses one canonical workspace; a separate regression test retains the historical-duplicate rejection case. Browser verification also found the onboarding selector overflowing at 390px; the selector now fits the card. A pagination fixture copied one activity key across 204 rows; its synthetic prospects now have separate identities and valid keys, preserving the uniqueness assertion rather than dropping the index. The new sibling-Application regression fixture also supplies distinct historical import keys required by that same index. The concurrent workspace test accepts an explicit 409 from a losing writer before the winner commits, verifies exactly one record/audit, and verifies explicit post-commit reopening; no automatic retry was added.

### Performance and operating boundaries

Identity search and reconciliation are bounded and disclose truncation; they do not automatically select the first match. The identity chooser currently uses bounded per-result context lookups, so narrow exact-code searches are preferable on large datasets. Historical mobile compatibility matching may scan records until an independently approved cleanup is performed. Existing history limits and optimistic concurrency remain. No background backfill or unbounded frontend data load is added.

The legacy Owner SMS password-reset action is blocked for added Employee access: it targets primary-role recovery and must not reset a Customer/Partner credential. Signed-in Employee Change Password works. Forgotten-password recovery for added Employee access requires a separately reviewed role-specific workflow; no guessed SMS/OTP recovery flow is introduced. Existing primary Employee, Customer and Partner recovery remains unchanged.

### Deployment prerequisites and rollback

1. Obtain Owner approval and deploy matched frontend/backend artifacts after staging review and verified backups. No deployment was executed here.
2. Confirm replica-set transaction support and existing unique indexes. Transaction failure must not be replaced with nontransactional writes or skipped audit.
3. Run the Owner-only read-only duplicate preflight against production only when separately authorized. Review truncation and individual conflicts; no automatic historical cleanup is authorized.
4. Verify Customer/Partner primary login and credentials, added Employee password change and permissions, refresh, onboarding, deactivation, search/history navigation, manual/linked follow-ups and Owner link/undo in staging with mocked SMS.
5. Keep Airtel/DLT configuration and production environment unchanged. Do not send real OTP/SMS as part of automated validation.

Rollback matched artifacts together; retain User/profile IDs, primary credential hashes, Employee associations, histories, audit and existing uniqueness indexes. Older artifacts cannot authenticate the additive Employee membership; do not replace primary roles or create another User to compensate. Disabling added Employee access requires an explicit Owner action. Use latest-link undo only where its version/history checks permit; do not delete or copy history as a rollback shortcut. No destructive migration or new index removal is required.

### Changed files

- `backend/app/features/access_control/permission_engine.py`
- `backend/app/features/auth/dependencies.py`
- `backend/app/features/auth/models.py`
- `backend/app/features/auth/repository.py`
- `backend/app/features/auth/role_context.py`
- `backend/app/features/auth/router.py`
- `backend/app/features/auth/schemas.py`
- `backend/app/features/auth/service.py`
- `backend/app/features/customer/schemas.py`
- `backend/app/features/customer/service.py`
- `backend/app/features/daily_operations/attendance.py`
- `backend/app/features/daily_operations/duplicate_report.py`
- `backend/app/features/daily_operations/identity.py`
- `backend/app/features/daily_operations/linked.py`
- `backend/app/features/daily_operations/resolution.py`
- `backend/app/features/daily_operations/router.py`
- `backend/app/features/daily_operations/service.py`
- `backend/app/features/daily_operations/workspace_activity.py`
- `backend/app/features/employee/identity.py`
- `backend/app/features/employee/router.py`
- `backend/app/features/employee/schemas.py`
- `backend/app/features/employee/service.py`
- `backend/app/features/recruitment/dependencies.py`
- `backend/app/features/search/service.py`
- `backend/app/middleware/auth.py`
- `docs/CRM_IDENTITY_AND_FOLLOWUP_ARCHITECTURE.md`
- `docs/PRODUCTION_ENHANCEMENT_BATCH_REPORT.md`
- `frontend/src/features/auth/api.ts`
- `frontend/src/features/auth/components/LoginForm.tsx`
- `frontend/src/features/auth/pages/ForceChangePasswordPage.tsx`
- `frontend/src/features/daily_operations/DailyOperationsPage.tsx`
- `frontend/src/features/daily_operations/FollowUpIdentitySearch.test.tsx`
- `frontend/src/features/daily_operations/FollowUpIdentitySearch.tsx`
- `frontend/src/features/daily_operations/IdentityReview.tsx`
- `frontend/src/features/daily_operations/RecordForm.tsx`
- `frontend/src/features/daily_operations/SimpleEntry.test.tsx`
- `frontend/src/features/dashboard/components/QuickSearch.test.tsx`
- `frontend/src/features/employee/api.ts`
- `frontend/src/features/employee/pages/CreateEmployeePage.tsx`
- `frontend/src/features/leads/components/MoveApplicationToLoanManagementModal.tsx`
- `frontend/src/features/leads/components/UpdateStageModal.tsx`
- `frontend/src/features/leads/pages/DocumentCollectionPage.tsx`
- `scripts/document-collection-correction-ui-check.mjs`
- `tests/api/conftest.py`
- `tests/api/mongo_unit_transactions.py`
- `tests/api/test_daily_loan_options.py`
- `tests/api/test_daily_operations.py`
- `tests/api/test_document_collection_correction.py`
- `tests/api/test_document_collection_correction_browser.py`
- `tests/api/test_followup_resolution_batch.py`
- `tests/api/test_identity_access_batch.py`
- `tests/api/test_production_batch_identity.py`

Synthetic responsive browser evidence: `docs/screenshots/identity-followup-2026-11-26/` (screenshots plus structured results). Local verification logs are under ignored `scripts/dev/.local-run/identity-*` paths.

---

# Previous completed batch: Document Collection editing and registration (2026-11-25)


## Scope and execution boundary

This report covers the latest five-workstream Document Collection, application editing, navigation, inline follow-up and simplified-registration brief. Implementation and validation are local only. No production data, environment variables, Airtel credentials, DLT content, deployments or real SMS were changed or used. The existing single-company database scope remains in place.

## Implemented workstreams

### 1. Compact Document Collection

The existing table now uses the same inherited table font scale and heading weight as Fresh Leads, smaller vertical padding and status/action spacing, and shared explicit widths for root and child rows. Its minimum width is reduced from 1599 to 1403 pixels. Long source labels wrap within their cells. Compact visible headings retain full accessible names and tooltips. Shortened Delete text retains its application-specific accessible label and existing Bin confirmation. Secondary Lead actions remain under More; their APIs and permissions are unchanged.

Search, all advanced filters, Apply/Clear, page size, pagination, selection, single-row direct actions, grouping and child paging remain. Only multi-application customers expand, without repeating headings. Horizontal scrolling remains inside the table when the viewport requires it.

### 2. Schema-driven submitted application editing

Document Collection opens the existing staff application view inside its existing Modal primitive, retaining the list underneath. The separate current-profile card is absent in this context. Application Details now offers Edit Details under the existing Customer edit permission. The editor uses the application's saved `form_definition_id`, not the latest schema for its product, and reuses ProductSchemaForm, DynamicFormField, RepeatableGroupsForm and validation. All applicable saved-schema fields and repeatable sections render; hidden/unrecognized historical answers are read-only and retained.

Save sends only changed application answers, a version and a correction reason through the existing PATCH endpoint. Cancellation discards local edits without a request. Errors retain input and field errors; locking prevents duplicate submissions. The saved server response refreshes the application. List refresh is limited to changes that can affect its displayed applicant name; follow-up saves refresh their relevant group data.

Submitted answers are application snapshots, including submitted name/PAN/contact values. They do not update the shared Customer, sibling Applications, User mobile/PIN or official Loan/Insurance Case facts. Shared identity retains its existing separately authorized profile API and Owner-only verification-field rules. The Customer identity remains accessible through a link; it is not deleted or replaced.

Staff saves require active authenticated staff access, existing Customer edit/view grants, current Application assignment for Employees, and valid User/Customer/schema relationships. Unknown/protected fields, Mongo path/operator keys, invalid values, hidden edits and pending-profile changes are rejected. Types, dates, formats, bounds, static options, conditional visibility and repeatable groups are validated. Updates use a version/identity/status/assignment compare-and-set. Application change history encrypts before/after answers; the ordinary audit logs actor, IDs, field names, time and version without answer values. Update plus audit commit in one transaction; conflicts return 409 without automatic retries.

### 3. Return navigation

Application links no longer generate customer-specific filters. Normal Close/Back returns to the default Document Collection list, without customer_id or automatic expansion. Browser Back closes the application view and retains only previously intentional URL state. Existing explicit Customer-ID search/focus links still work. Legacy direct `/applications/{id}?from=document-collection` links remain supported and their Back control also returns to the normal list. Existing View Full Application links in Update dialogs open the same retained-list view and close the previous dialog.

### 4. Follow-up stays in Document Collection

Open Daily Follow-up in this context uses the existing server-linked workspace API and the existing RecordForm in a modal. Context comes from exact Application/Customer references; no matching or duplicate business logic is added. Opening/saving does not navigate to Daily Updates. Save failure keeps the modal and input intact; success closes the dialogs, refreshes relevant list data and shows a confirmation on Document Collection. Existing linked-workspace idempotency, assignment restrictions, validation and append-only history remain authoritative. Normal standalone Daily Update access and existing navigation-mode callers remain functional.

The shared Modal primitive now handles nesting depth, top-dialog focus/Escape and scroll restoration; parent-dialog re-renders still do not steal input focus. Existing dialog behavior is regression-tested.

### 5. Three-field registration

Registration displays mobile, PIN and confirmation only. OTP proof, expiry, cooldowns, attempt limits, Argon2 PIN hashing, duplicate-account protection and sessions are preserved. The existing mandatory real-name Customer model is not weakened. Signup atomically creates only the verified Customer-role User, consumes its proof and audits pending profile state; the established post-login profile setup creates a valid Customer after real details are supplied. No fabricated names/emails or incomplete Customer records are inserted.

The private signup marker prevents subsequent profile setup from linking historical Leads by mobile. Known historical identities still require ownership review. No consent is invented: the removed checkbox was a prior feature requirement, and no independent repository policy/legal-consent implementation was found. See `CUSTOMER_REGISTRATION_FLOW.md` for the inspected policy boundary and deployment caveat.

## APIs, persistence and permissions

- Existing PATCH `/applications/{id}` now supports authorized staff corrections using form_data/version/reason. Customer-owned draft autosave retains its existing behavior; customers cannot use staff editing to modify submitted applications. Extra protected request fields are rejected.
- Additive GET `/applications/{id}/form-definition` returns the exact saved schema after application access checks. It reuses existing form-definition mapping and document metadata resolution.
- Application detail responses include version. Encrypted `answer_history` is stored encrypted in the existing application document and omitted from normal DTOs. No new collection or database index is required.
- Signup requests now contain only mobile/pin/confirm_pin, plus authorization at completion. Existing registration consumers are updated. A private User signup marker is additive; existing accounts remain untouched.
- No new permission or default grant is introduced. Existing Customer edit/view, staff assignment, Daily Operations permissions, document password reveal permission and Bin restrictions remain in force.

## Validation evidence

All checks used synthetic data; SMS responses were mocked. No real SMS was sent.

| Check | Final result |
| --- | --- |
| Full frontend suite | 520 passed; no failed or skipped tests |
| Focused frontend checks after final UI refinements | 20 passed |
| Existing backend regression suite | 133 passed; 173 existing mongomock datetime deprecation warnings |
| Submitted application editing | 13 passed, including real local replica-set transactions and audit-failure rollback |
| Registration security and deferred profile creation | 16 passed |
| Staff browser journey | Passed at 390, 768 and 1366 pixels |
| Customer registration/login/reset browser journey | Passed at 390, 768 and 1366 pixels; zero fabricated Customer profiles |
| Frontend TypeScript and production build | Passed; existing bundle-size warning remains |
| ESLint | Zero errors; eight existing fast-refresh warnings |
| Ruff | Passed for modified/new Python source and tests; changed ranges formatted |
| New application editor mypy | Passed |
| Whole-app mypy baseline comparison | 117 existing errors before and after; zero introduced |

Browser checks covered filter/search preservation, explicit customer focus, normal and browser Back, edit Save/Cancel, nested follow-up saving, retained input after an injected 409, standalone Daily Updates, password visibility permission and reconciliation preview. Database assertions confirmed sibling and shared Customer records remained unchanged, application version/history advanced, identity references remained intact and Bin remained empty. Registration covered mobile/PIN-only signup, existing profile setup, login, Forgot PIN and unchanged staff sign-in tabs.

An initial browser locator conflict from duplicate accessible Source labels was corrected and the staff journey rerun successfully. An initial API test fixture lacked an authenticated Employee session; the fixture now logs in normally, and all 13 final application tests pass. No authentication checks were weakened. Screenshots and structured browser results are under `docs/screenshots/document-application-registration-improvements/`. Local verification logs are under ignored `scripts/dev/.local-run/next-batch-*` paths.

## Deployment prerequisites (not executed)

1. Owner approval of the reviewed changes and coordinated frontend/backend deployment. Registration's revised request contract requires both artifacts and refreshing old open registration pages; check external clients separately if any exist outside this repository.
2. Confirm MongoDB replica-set transaction support, already required by OTP registration. Application correction and its audit now also require a transaction. Take a verified, access-controlled backup before rollout.
3. Retain existing role grants; verify Employee view/edit and assignment restrictions in staging. No permission reset or automatic Employee grant is needed.
4. Confirm any consent obligation managed outside this repository before deployment. The implementation neither displays the removed checkbox nor records assumed consent.
5. Run staging smoke journeys using mocked SMS. Real OTP testing, production changes or deployment require separate Owner approval. Do not run historical merges, backfills or record rewrites.

## Rollback

Roll back matching frontend/backend artifacts together after Owner review; do not reset account hashes, sessions, Customer/Application IDs or files. Existing accounts remain valid. Retain encrypted application history and audit records. Preserve private signup markers so deferred profile setup continues to avoid historical mobile-only linking; an older backend must be patched/reviewed before resuming that path. Verified accounts created without a profile must continue through the existing profile-setup route; never generate placeholder Customer names to compensate. Application corrections can be reviewed against encrypted before/after history and approved backups; this batch does not automatically reverse business data or rewrite siblings. No new collection/index needs removal.

## Limitations and deliberate boundaries

Unknown or hidden historical answers remain read-only; applicable saved-schema fields are editable. Shared identity changes use the existing Customer workflow rather than implicit propagation from application snapshots. Existing standalone history is not migrated. No bulk repair or historical customer merge is included. Existing mypy and frontend warning baselines are reported separately from new checks. Transaction support and coordinated client rollout are prerequisites, not automatic production operations.

## Changed files

- `backend/app/features/customer/application_edit.py`
- `backend/app/features/customer/mappers.py`
- `backend/app/features/customer/router.py`
- `backend/app/features/customer/schemas.py`
- `backend/app/features/customer/service.py`
- `docs/CUSTOMER_REGISTRATION_FLOW.md`
- `docs/PRODUCTION_ENHANCEMENT_BATCH_REPORT.md`
- `frontend/src/components/forms/ProductSchemaForm.tsx`
- `frontend/src/components/overlays/Modal.test.tsx`
- `frontend/src/components/overlays/Modal.tsx`
- `frontend/src/features/customer/api.ts`
- `frontend/src/features/customer/components/DynamicFormField.tsx`
- `frontend/src/features/customer/components/SubmittedApplicationDetails.test.tsx`
- `frontend/src/features/customer/components/SubmittedApplicationDetails.tsx`
- `frontend/src/features/customer/pages/RegisterPage.test.tsx`
- `frontend/src/features/customer/pages/RegisterPage.tsx`
- `frontend/src/features/customer/pages/StaffApplicationDetailsPage.tsx`
- `frontend/src/features/customer/useProductSchema.ts`
- `frontend/src/features/customer/validation.ts`
- `frontend/src/features/daily_operations/OpenLinkedFollowUp.test.tsx`
- `frontend/src/features/daily_operations/OpenLinkedFollowUp.tsx`
- `frontend/src/features/daily_operations/RecordForm.tsx`
- `frontend/src/features/leads/components/MoveApplicationToLoanManagementModal.tsx`
- `frontend/src/features/leads/components/UpdateStageModal.tsx`
- `frontend/src/features/leads/pages/DocumentCollectionPage.test.tsx`
- `frontend/src/features/leads/pages/DocumentCollectionPage.tsx`
- `frontend/src/features/leads/pages/LeadListPage.test.tsx`
- `frontend/src/shared/navigationContext.test.tsx`
- `frontend/src/shared/navigationContext.ts`
- `scripts/customer-pin-ui-check.mjs`
- `scripts/document-collection-correction-ui-check.mjs`
- `tests/api/test_customer_pin_browser.py`
- `tests/api/test_customer_pin_registration.py`
- `tests/api/test_document_collection_correction_browser.py`
- `tests/api/test_submitted_application_edit.py`
- `docs/screenshots/document-application-registration-improvements/` (synthetic browser evidence).
