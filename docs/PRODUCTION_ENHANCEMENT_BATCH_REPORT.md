# Production enhancement batch report

25 November 2026 ? local implementation only. No deployment, production database access, production reconciliation, real SMS, production account creation or external integration configuration changes were performed.

## Implemented behavior

**Document Collection:** Single-application rows expose the existing View/Update/Owner Delete actions directly. Only multi-application customers expand, with an application-count tag. Their summary identifies the Customer rather than duplicating one application's identity. Expanded rows have individual actions and no repeated header. Shared explicit column widths and a horizontal scroll container keep the layout stable under filters. Expansion retains child pagination while collapsed. Existing search, URL filters, group paging, assignment, confirmations and Bin services remain in use.

**Daily Updates:** Current Customer/Application/Lead references resolve display names without rewriting stored snapshots. Conflicting, broken or ambiguous relationships receive review warnings. Exact name/mobile matching preserves punctuation, whitespace-normalizes and case-folds names, and normalizes accepted Indian mobile formats. New activities reuse an authorized exact Customer, never create or merge Customers, and preserve all Applications. Partial matches require an Owner decision. Actor-bound receipts, a new partial unique activity index, client submission locking and explicit separate-activity reasons prevent accidental duplicates while preserving legitimate dates and histories.

The Owner gets a bounded read-only reconciliation preview, verified candidate approval and reversible per-record linking. Live fingerprints and versions reject stale decisions. Link/rollback plus audit commit in a transaction. Rollback restores the prior reference fields, including field absence, while appending history. Source Application ownership is never rewritten. No historical corrections were applied outside disposable tests.

**Document passwords:** The existing encrypted storage and dedicated read endpoint now support separately authorized reveal. Customer view, active staff status, the explicit password permission and current Application assignment all apply. The endpoint rate-limits, audits IDs/timestamp without secrets and returns no-store responses. Staff controls mask by default; Hide, blur, navigation, permission loss and a 30-second timer clear values. Stale responses are discarded. Normal APIs remain secret-free.

**Customer registration:** Failed PIN login retains safe uniform errors and offers a neutral registration popup. The Customer registration link now opens `/register`, fixing the pre-existing link to the Owner setup page. The PIN login endpoint is excluded from session-refresh retries, so wrong credentials do not dismiss the popup as an expired session. Only verified OTP ownership permits an account-not-found message. Full name, optional email, matching PIN and consent are validated. Existing accounts cannot receive registration authorization. Account/profile/proof/audit creation remains transactional with existing unique indexes and Argon2 PIN hashing. Registration no longer attaches historical Leads by mobile alone. Known historical Customer identities require ownership review instead of a duplicate profile or automatic attachment.

## API and database changes

- Existing POST/PATCH Daily Follow-up APIs gain optional submission/review fields. New manual creation checks exact identity and same-day activity conflicts. Identical request retries return the existing accessible record; changed payloads cannot reuse a committed key.
- Owner-only GET `/daily-operations/identity-review/preview`, POST `/daily-operations/identity-review/{id}/link`, and POST `/daily-operations/identity-review/{id}/rollback`. Preview paging caps at 100 records, candidate sets cap at 200 and truncated sets cannot apply. Preview is registered before generic dynamic routes.
- Existing GET document-password endpoint returns plaintext only under its dedicated authorization boundary. Global security middleware normalizes its response to `Cache-Control: no-store`; `Pragma: no-cache` is also set.
- Existing registration requests now require `full_name` and strict true `terms_accepted`. OTP verification can return `next_action` after ownership proof. Existing-account proofs are consumed without registration authorization; PIN completion rejects registration proofs.
- New partial unique `daily_follow_ups.activity_key` index applies only to active keyed rows. Existing `import_key` and working-key indexes are retained. Internal receipt/activity fingerprints are omitted from ordinary responses and history projections. Domain-separated HMACs use the existing encryption key, falling back to the existing JWT key in installations without a configured encryption key.
- No new collections, tenant architecture, production backfill, identifier regeneration, file rewrite or permission reset.

## Security and production approvals

The separate catalog resource is `customer:document_passwords`, action `view`, with no parent grant. Fresh seed defines it without granting it. Existing installations require an Owner to create the definition through existing permission administration and deliberately grant selected roles. Ordinary Customer edit or module-wide grants must not imply reveal. Existing assignment restrictions and Bin dependencies remain authoritative.

Production deployment, new role grants, any historical link/merge approval and backup/restore operations remain Owner-controlled. Legacy Customer profile ownership review uses existing verified account/secure-link processes; this batch intentionally provides no public mobile-only attachment or bulk Customer merge.

## Reconciliation evidence

Only disposable fixture data was assessed. The bounded preview fixture returned two exact safe candidates on its first two-record page and correctly reported another page. The preview caused no writes. Real replica-set tests exercised concurrent identical submissions, one-record linking, stale-preview rejection and rollback while preserving original remarks, Application count and append-only audit/history. Browser fixtures resolved blank snapshot names from current profiles and retained the blank original snapshots after three edits. No production preview totals are claimed.

## Validation

| Check | Result |
|---|---|
| Broad related backend regression run | 145 passed; two old fixture expectations conflicted with the newly required identity/activity review rules |
| Corrected backend expectations and focused identity/transaction checks | 11 passed, including both corrected fixtures |
| Final identity, null-name, reference consistency, idempotency and real replica-set rollback checks | 10 passed |
| Existing Document Collection, search, lifecycle and Bin regression modules | 27 passed; sibling Application and shared Customer preserved through delete/restore |
| Real local API/database browser journeys | Staff and customer journeys passed at 390, 768 and 1366 pixels; 2 browser tests passed, then the staff test passed again after final table refinement |
| Complete frontend suite | 515 passed, 0 failed (final serial run) |
| Additional frontend security/registration/table tests | 16 passed before final full-suite verification |
| TypeScript and production build | Passed via `npm --prefix frontend run build`; existing bundle-size warning remains |
| ESLint | 0 errors, 8 existing fast-refresh warnings |
| Ruff | All changed/new Python source and test files pass; new files fully formatted and changed existing ranges formatted |
| Focused strict mypy | 2 affected identity helper files pass |
| Full mypy versus clean HEAD shadow baseline | 117 current / 117 baseline; zero introduced diagnostics |
| Whitespace/diff checks | Passed |

The first backend run also caught an unsupported mock aggregation conversion and legacy password-read expectations. The conversion was removed and the requested permission-driven reveal behavior was tested explicitly. Browser testing found and corrected generic-route shadowing, inappropriate refresh handling for invalid PIN credentials, and the Customer registration link leading to Owner setup. No Owner setup implementation was changed.

One parallel full frontend run reported two timing-sensitive failures in the unchanged `AddInsuranceLeadModal` tests while other validation was running. The earlier full frontend run passed all 510 then-present tests; the final suite includes five additional security tests. The final serial rerun passed all 515 tests, without changing the unrelated insurance implementation or tests. Earlier failures are retained in local diagnostic logs rather than suppressed.

Browser screenshots and JSON evidence are in the artifact folders listed below. Browser tests block external calls and use only disposable loopback MongoDB databases and mocked Airtel responses. The owned temporary replica-set instance and frontend preview are stopped after validation; the pre-existing local MongoDB instance is left running.

## Deployment instructions ? not executed

1. Obtain Owner approval for the reviewed commit and coordinated backend/frontend deployment. Confirm replica-set transaction support and take a verified, access-controlled database backup.
2. Deploy compatible backend and frontend artifacts together. The normal Daily Operations catalog/index installation adds the partial activity index; it excludes historical unkeyed rows. Do not backfill keys, merge profiles or reset grants automatically.
3. Create the dedicated root password permission if absent, and grant it only to selected authorized roles. Verify active staff, Customer view, assignment denial, audit and cache headers before enabling Employee reveal.
4. Verify registration and PIN recovery in staging with mocked SMS. Production SMS/OTP testing requires separate explicit Owner authorization; existing Airtel/DLT settings remain unchanged.
5. Generate bounded read-only reconciliation previews in production only under authorized access. Review and approve individual historical links separately, after a backup. Repair inconsistent authoritative source records through their existing workflows.

## Rollback

Deploy matching prior backend/frontend artifacts together after Owner review; do not reset PIN hashes, sessions, Customer IDs, Application IDs, files or histories. Retain audit events and newly captured consent/name data. Remove/revoke the new password grant if access must be withdrawn; the old service fails closed on reveal. The partial activity index may remain safely installed because older unkeyed rows do not participate. Dropping it or rotating the HMAC data key requires a separate duplicate-preservation plan. For reviewed historical links, use the Owner rollback action only while the link remains the latest unchanged edit; otherwise inspect later history and restore selected references from the approved backup. No automatic database-wide restore or customer merge reversal is performed.

## Limits

- Full repository mypy has pre-existing failures; baseline comparison and new-module checks are reported separately.
- Existing build chunk-size and fast-refresh warnings remain documented.
- Old unkeyed historical activities are checked before new primary creation, but older application versions do not participate in the new unique constraint. Do not mix incompatible backend versions.
- Legacy records with broken references remain flagged for source repair. Read-time name resolution does not perform a historical name/index backfill; older searches continue to use persisted searchable values where reference mirrors are absent.
- Existing encrypted passwords can be revealed; absent or previously unstored values cannot be recovered. No document-type password settings were changed.
- Preview counts are bounded page counts, not a production-wide merge assessment. Bulk Customer merging and production historical repairs remain outside automatic execution.

## Changed files

- `backend/app/features/auth/pin_service.py`
- `backend/app/features/customer/router.py`
- `backend/app/features/customer/schemas.py`
- `backend/app/features/customer/service.py`
- `backend/app/features/daily_operations/identity.py`
- `backend/app/features/daily_operations/router.py`
- `backend/app/features/daily_operations/schemas.py`
- `backend/app/features/daily_operations/service.py`
- `backend/app/shared/customer_identity.py`
- `docs/CUSTOMER_REGISTRATION_FLOW.md`
- `docs/DAILY_UPDATE_IDENTITY_AND_DUPLICATE_RULES.md`
- `docs/DOCUMENT_PASSWORD_ACCESS_SECURITY.md`
- `docs/PRODUCTION_ENHANCEMENT_BATCH_REPORT.md`
- `frontend/src/features/auth/components/PinAuthPanel.tsx`
- `frontend/src/features/auth/pages/LoginPage.test.tsx`
- `frontend/src/features/auth/pinApi.ts`
- `frontend/src/features/customer/api.ts`
- `frontend/src/features/customer/components/DocumentPassword.test.tsx`
- `frontend/src/features/customer/components/DocumentPassword.tsx`
- `frontend/src/features/customer/pages/RegisterPage.test.tsx`
- `frontend/src/features/customer/pages/RegisterPage.tsx`
- `frontend/src/features/customer/pages/StaffApplicationDetailsPage.test.tsx`
- `frontend/src/features/customer/pages/StaffApplicationDetailsPage.tsx`
- `frontend/src/features/customer/validation.ts`
- `frontend/src/features/daily_operations/DailyOperationsPage.tsx`
- `frontend/src/features/daily_operations/IdentityReview.tsx`
- `frontend/src/features/daily_operations/RecordForm.tsx`
- `frontend/src/features/leads/pages/DocumentCollectionPage.test.tsx`
- `frontend/src/features/leads/pages/DocumentCollectionPage.tsx`
- `frontend/src/features/leads/pages/LeadListPage.test.tsx`
- `frontend/src/shared/api/client.pin.test.ts`
- `frontend/src/shared/api/client.ts`
- `scripts/customer-pin-ui-check.mjs`
- `scripts/document-collection-correction-ui-check.mjs`
- `scripts/seed.py`
- `tests/api/test_customer_documents.py`
- `tests/api/test_customer_pin_registration.py`
- `tests/api/test_daily_multi_bank.py`
- `tests/api/test_daily_operations.py`
- `tests/api/test_daily_reeligible.py`
- `tests/api/test_document_collection_correction_browser.py`
- `tests/api/test_enterprise_crm.py`
- `tests/api/test_production_batch_identity.py`

Browser artifacts: `docs/screenshots/production-enhancement-batch/` and its `otp/` subdirectory contain the screenshots and machine-readable journey results for 390, 768 and 1366 pixels. No screenshots include revealed document passwords or OTPs.
