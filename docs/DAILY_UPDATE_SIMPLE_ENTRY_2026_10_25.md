# Daily Update simple entry

Baseline: clean main at `7f2fee9`; existing navigation/module and shared authorization,
forms, queries and histories inspected before editing. User explicitly authorizes default
employee access, name-based entry, progress Add/Edit, Owner-only Delete and simpler screens.

Plan: default scoped employee permissions in the existing engine; optional CRM linkage for
manual daily entries; name lookups and free-text names without creating identities; editable
daily loan-progress entries/annotations without mutating canonical loan approvals; audited
Owner-only removal from daily views; compact spreadsheet tables and quick forms; preserve
automated authentication timestamps. Test record isolation, validation, CRUD, transfer
regressions and actual desktop/mobile browser entry. No production actions are authorized.

## Implemented behavior

- Every active employee receives Daily Update navigation and own-record view, entry,
  edit, import and export access by default. Session history is view/export only.
  Other CRM module permissions are unchanged. Inactive employees receive no default.
- Employee name fields use a dropdown with manual text entry. No visible CRM employee
  ID is required. Manual names are labels, never new accounts or an access override.
  Employees remain scoped to their actual identity; Owners can assign active employees.
- Follow-ups and Loan Progress accept simple manual spreadsheet-style rows. Existing
  CRM leads/cases can be selected under optional details, using names and case labels.
- Loan Progress supports Add record and individual Edit. Linked progress updates are
  daily annotations; official loan stages, approvals and verified disbursements remain
  controlled by Loan Management. Manual amounts are excluded from verified loan totals.
- Follow-ups, progress and issues have per-record Edit/History. Only Owners see Delete;
  the server independently enforces this even when an employee role grants deletion.
  Deletion is version-checked and audited, and hides daily records without deleting
  actual CRM loans. Linked records use current assignment, including after reassignment.
- Session timestamps remain based on authentication events. Employees can request a
  correction through an issue. Owner corrections retain their existing audit flow;
  removing a daily session row does not delete or modify an authentication session.
- Pages show compact tables, Search and Employee name first. Additional filters,
  financial details, import mappings and optional CRM links are collapsed. CSV/Excel
  exports and preview-before-commit imports remain available.

## Persistence and safeguards

`daily_progress_entries` stores standalone rows or one annotation per linked case.
`daily_session_visibility` stores Owner-only daily-view tombstones. Existing follow-up
and issue collections retain versioned audit history. Index setup adds progress scope,
date, status and sparse unique import-key indexes using the existing startup mechanism.
No database setup or migration was executed against production.

Imports accept manual names and customer fields and retain optimistic versions,
idempotency fingerprints and explicit update confirmation. Legacy action-only progress
import fingerprints are checked to avoid importing those files twice. Phone numbers,
date order, finite nonnegative amounts, assignment and linked financial values are
validated on the server. Lookup and merge queries are bounded; large combined progress
results require narrower filters. Browser artifacts contain synthetic data only.

## Verification

- New backend safety suite: 16 passed, including cross-employee denial, reassignment,
  concurrent edits, manual/linked progress, transfer retries and Owner-only deletion.
- Existing targeted backend workflow suites: 82 passed.
- Focused frontend suites: 27 passed.
- Strict scoped Python typing: no issues in 12 source files. Backend lint and scoped
  formatting passed. Frontend lint has zero errors and 10 existing warnings.
- Production frontend build passed; existing large-bundle advisory remains.
- Local browser checks passed for Owner and Employee at 1440px and 390px: navigation,
  name/manual entry, follow-up and progress Add/Edit, deletion visibility/confirmation,
  correction requests and collapsed import controls. No browser page errors occurred.
  These use intercepted synthetic API responses; real authorization/persistence are
  separately covered by backend tests.

Browser evidence: [screenshots and scenario evidence](screenshots/daily-simple-entry-2026-10-25/).
Full backend regression: **1,467 passed, 1 skipped** (677 dependency deprecation
warnings). Repository-wide strict Python typing still reports the existing 116 errors
in 11 unchanged files; none are in Daily Operations or the permission engine.

Full frontend regression: **383 passed across 76 files**, using two workers. An
earlier concurrent run hit five-second timeouts in two unchanged insurance/voice tests;
both passed in the final full run without changing their tests or timeout limits.

## Scope and rollout

Backend changes are confined to Daily Operations and its explicit baseline in the
permission engine. Frontend changes are in the Daily Operations pages, forms, name
field and transfer centre. Tests and the synthetic browser script accompany them.
This report supersedes the earlier Daily Operations reports' grant-only employee
access and required linked-record entry descriptions.

Changes are local and have not been deployed. Production needs the updated backend
and frontend released together, with normal startup index/catalog setup, before
employees will see the new default navigation and workflow.
