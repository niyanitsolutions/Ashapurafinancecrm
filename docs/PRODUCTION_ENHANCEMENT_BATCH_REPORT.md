# Production enhancement batch report

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
