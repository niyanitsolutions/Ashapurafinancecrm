# Issued invoice same-number revisions and reissue

## Outcome and root cause

The new Edit -> Edit & Reissue path keeps one invoice ID and its existing official number. It does not call creation, duplication, replacement creation or the number allocator. Changes first become a pending proposal; an explicit owner approval applies a new effective revision atomically while retaining earlier snapshots.

The unwanted new number came from the previous replacement workflow: `duplicate(..., replacement=True)` called invoice creation, which called the existing global INV allocator. A suffix such as `100000014` reflects that allocator's counter/configured minimum, not a revision identifier. Production counter/configuration values were not inspected, so this report does not claim which production setting produced that exact suffix. No counter was reset or renumbered.

The earlier enhancement report is actually at `docs/invoices/INVOICE_ENHANCEMENT_REVIEW.md`; the requested root-level variant does not exist. That report, `docs/INVOICE_CORRECTION_DELETION_NUMBERING_FIX.md`, `docs/INVOICES.md`, the invoice implementation and `scripts/migrate_invoice_number_reuse.py` were inspected. Existing numbered replacement records remain intact.

## Files changed

| Existing file | Purpose |
|---|---|
| `backend/app/features/invoices/models.py` | Effective revision pointer, immutable snapshot array, pending proposal and reissue timestamp |
| `backend/app/features/invoices/schemas.py` | Default-disabled policy, approval metadata and validated proposal/reissue inputs |
| `backend/app/features/invoices/revisions.py` (new) | Same-identity proposal/approval lifecycle, snapshot access and storage-size guard |
| `backend/app/features/invoices/service.py` | Capture original at first issue, revision audit reasons, owner-only issued cancellation/archive and lightweight list projections |
| `backend/app/features/invoices/router.py` | Policy approval handling, revision/history/PDF APIs and controlled issued Delete |
| `frontend/src/features/invoices/api.ts` | Typed policy, revision, approval, historical PDF and issued archive calls |
| `frontend/src/features/invoices/InvoiceListPage.tsx` | Status/permission-based View/Edit/Delete/Archive actions |
| `frontend/src/features/invoices/InvoiceWorkflow.tsx` | Issued edit confirmation, policy gate and controlled issued Delete confirmation |
| `frontend/src/features/invoices/InvoiceFormPage.tsx` | Same-number revision mode, reason, saved proposal, approval and original issue information |
| `frontend/src/features/invoices/InvoiceViewPage.tsx` | Current revision, proposal review, controlled actions and fresh-PDF printing |
| `frontend/src/features/invoices/InvoiceRevisionHistory.tsx` (new) | Current/historical revision metadata and explicit historical downloads |
| `frontend/src/features/invoices/InvoiceSettingsPage.tsx` | Owner policy activation, required reason and recorded approval identity/time |
| `frontend/src/features/invoices/Invoices.test.tsx` | New workflow tests, legacy compatibility coverage and fresh print regression |
| `tests/api/test_invoice_revisions.py` (new) | Policy, immutability, same-number lifecycle, concurrency, permissions and history tests |
| `tests/api/test_invoice_mongo_integration.py` | Real MongoDB revision and approval concurrency with unchanged counters/indexes |
| `scripts/invoice-workflows-ui-check.mjs` | Updated desktop/mobile synthetic-fixture browser acceptance flow |

Added evidence: `docs/screenshots/invoice-same-number-reissue/revision-1440.png`, `revision-390.png`, and `results.json`. This report is `docs/INVOICE_SAME_NUMBER_REISSUE.md`.

No global routing, authentication, session, permission catalog, tenant architecture or unrelated CRM module was modified. The calculator, PDF layout generator, numbering helper, repository index definitions and deployed numbering migration are unchanged.

## Schema and migration requirements

The existing invoice document gains optional/defaulted fields:

- `effective_revision` (default 1; meaningful for issued records).
- `revisions`: immutable effective snapshots with revision number, previous reference, reason, actor/timestamps, changed fields, owner approval and reissue metadata.
- `revision_proposal`: editable, non-effective proposal with its own ID, base effective revision, full calculated snapshot, reason and requester metadata.
- `reissued_at`: most recent reissue time. Original `issued_at` remains unchanged.

`company_settings.invoice_config` gains `same_number_reissue_enabled` (default false), `same_number_policy_reason`, and server-controlled policy approver identity/time. Existing databases default to disabled without a backfill. The owner must explicitly enable and explain the policy through Invoice Settings.

No new collection, index or migration is required. Revision snapshots and the effective pointer are stored together in the existing invoice document, allowing one optimistic compare-and-update to commit them without a cross-document transaction. A 12 MiB preflight limit blocks further changes before MongoDB's document size limit; it never truncates old history. Snapshot bodies are excluded from invoice list database projections.

The deployed number-reuse indexes and `scripts/migrate_invoice_number_reuse.py` must remain in place. Do not rerun its rollback or change the counter for this feature. Real-Mongo tests verify index definitions and sequence values remain unchanged across reissue.

## Revision lifecycle

1. Authorized staff select Edit on an issued invoice. The confirmation shows its number, customer, status, issued warning, retained-number explanation and accounting/statutory restriction.
2. The existing edit route opens with `?mode=revision`, displaying a read-only number, current effective revision, original issue information, correction reason and approval state.
3. Save Revision Proposal validates supported business inputs and recalculates with the existing authoritative decimal GST calculator. It updates a proposal inside the same invoice document, not another invoice. Original effective data and PDF remain unchanged.
4. Reopening loads the saved proposal. Repeated saves retain identity and update the current optimistic version. Unsaved changes disable approval until saved.
5. An owner reviews the saved proposal and supplies a separate approval reason. Approval verifies the policy again, invoice status, proposal ID, base revision and current version.
6. One atomic invoice update appends the corrected snapshot and moves the effective pointer to revision N+1. The ID, number, original issue timestamp and company/bank/image snapshots remain unchanged. Current PDFs now use the effective corrected content.
7. Old snapshots and PDFs are accessible through revision history. Historical download filenames include a revision suffix; the statutory number printed inside each PDF stays unchanged.

Newly issued invoices capture revision 1 when first issued. Older issued invoices without revision arrays capture their existing persisted issued state before the first proposal is written. These records are marked as historical captures; the application does not invent previously missing historical versions, actors, PDFs or timestamps. Read-only legacy fallback uses available persisted data until an original snapshot is stored.

Supported customer, dates, items, quantities, rates, GST, supply and terms fields use the existing schemas. No new discount model or financial formula was invented. Original company/bank/image snapshots are preserved rather than refreshed from current settings. Proposal previews are explicitly DRAFT, use the same number and frozen company snapshot, and do not allocate a number.

## Permissions and accounting policy

- Existing invoice View permission and existing record scope protect current/history/snapshot/PDF reads.
- Existing Edit permission and record scope permit issued revision proposals. Direct ordinary PUT remains draft-only.
- Existing owner authorization is required both to enable the policy and to approve/reissue an individual proposal. Owners also save a proposal before separately approving it.
- Policy approver identity/time are set by the backend; submitted values cannot spoof them.
- Issued Delete is owner-controlled archive, with a mandatory reason. It does not physically remove the invoice, revisions, PDFs, number or financial state. It is not legal cancellation.
- The older generic archive and cancellation APIs also require an owner for issued invoices, preventing staff from bypassing the new approval UI. Draft and cancelled-record operations retain their existing appropriate rules.
- Settled, cancelled and archived records cannot enter same-number revision mode. Archived records expose only View in list actions.

No separate RBAC architecture or grants were added. Existing owner/employee assignment scope is reused. The application remains its existing single-company/assignment-scoped system; this work does not claim new multi-tenant isolation.

Enabling the policy is an accounting-owner assertion that the operation is permitted; it is not an automated GST/legal determination. If a credit note, debit note or formal replacement is required, keep the gate disabled for same-number work and use the approved accounting process. Credit/debit notes and government submissions are not implemented.

## Legacy corrections

Existing `replacement_for` records, numbers, drafts, source references, PDFs and history are not converted, merged, renumbered or deleted. Legacy drafts remain editable through their existing invoice ID. Legacy replacement APIs remain compatible for explicit old clients, but the new issued Edit path never invokes them.

An active legacy correction against the original blocks a new same-number proposal with a clear message. The owner must review that existing workflow. A never-issued legacy draft can use the existing audited deletion policy if it is intentionally abandoned; finalized records cannot be discarded. The system does not automatically resolve accounting relationships between legacy and new workflows.

Ordinary Duplicate remains an independent new-draft action from invoice detail. It does not become a revision. Its obsolete internal-revision alternative was removed from that modal to avoid confusing duplication with Edit & Reissue.

## PDF and printing

The existing PDF layout generator is reused. The current PDF endpoint renders the current effective canonical content. Historical endpoints render stored snapshots with their original company/customer/GST/bank/image data. Historical revision downloads are explicitly labelled internally and by filename.

Print now fetches the latest PDF and loads it into a dedicated print iframe. It no longer fetches a new document but prints the previously displayed iframe. A component regression checks that the print frame receives the freshly fetched blob. Native printer completion cannot be confirmed by the application.

PDFs are generated on demand as before; this release does not add binary PDF archival storage. Existing snapshots preserve rendering inputs, and tests compare original/current extracted PDF content. Byte-identical output across render metadata or future PDF-library versions is not promised.

## Validation results

| Check | Result |
|---|---|
| Existing invoice API tests | 44 passed |
| New same-number revision API tests | 8 passed |
| Real local MongoDB integration tests | 4 passed |
| Combined invoice/API/Mongo run | 56 passed |
| Access-control, system-settings and timezone backend regressions | 65 passed |
| Invoice frontend tests | 21 passed |
| Shared Modal and permission-hook regressions | 4 passed |
| TypeScript typecheck | Passed |
| Invoice ESLint | Passed |
| Ruff and touched Python formatting | Passed |
| Frontend production build | Passed; existing bundle-size warning |
| Desktop/mobile browser checks | Passed at 1440px and 390px using synthetic API fixtures |
| Strict mypy on invoice package/imports | Not clean: 112 errors in 8 files |

The previously recorded strict-mypy baseline was 115 errors. Remaining failures include existing untyped PDF/schema/router code, missing PDF-library stubs and imported-module issues; strict Python typing is not claimed to pass. No unrelated code was changed to suppress those failures.

Real MongoDB tests use explicitly enabled loopback URIs and random synthetic test databases, removed on completion. They verify proposal and approval races converge to one effective change, the original snapshot stays unchanged, no second invoice is inserted, and counters/indexes are unchanged. Browser tests use real Chromium interactions with synthetic API responses, not a live backend or production records. They separately cover draft editing/reuse, independent duplication, same-number proposal saves/resume, owner reissue, historical history, download/print requests and employee restrictions.

No production acceptance testing, production database inspection, production migration, deployment, external GST certification or physical printer completion test was performed. No emails, customer messages or external financial actions were sent.

## Known limits and operational notes

- The feature is disabled until the owner enables it; every reissue still requires owner approval and a reason.
- Storage is bounded by the invoice document size guard. Hitting the limit blocks new revisions and requires an approved longer-term archival design; historical records are not dropped.
- One pending proposal is retained per invoice. Successful proposal-save events are audited, while immutable effective snapshots are appended on approval. Superseded unapproved proposal bodies are not represented as issued revisions.
- Shared audit logging follows the atomic invoice update. If that secondary log write fails, the embedded event and snapshot may already be saved. Reload current state after a timeout; optimistic checks prevent duplicate effective revisions.
- Original issue snapshots for legacy records can only preserve data actually available at capture time. Missing historical binary PDFs cannot be reconstructed with guaranteed byte identity.
- Unsaved forms do not reserve invoice numbers. Same-number proposals and reissues never invoke the number allocator. Draft tail-number reuse behavior remains unchanged.
- Owner policy approval does not validate filing windows or statutory eligibility automatically.

## Staging deployment instructions (provided only; not executed)

Use the existing Ubuntu release process, verified staging environment and a database backup. No new environment variables, packages or migration are required. Retain the deployed number-reuse migration and indexes.

```bash
cd ~/Ashapurafinancecrm
# Install the reviewed release using the existing release procedure.
npm --prefix frontend run build
sudo systemctl restart afs-crm-backend afs-crm-arq-worker
sudo systemctl status afs-crm-backend afs-crm-arq-worker --no-pager
```

Keep the new gate disabled during initial smoke checks. In staging Invoice Settings, an accounting owner may enable it with a synthetic test approval reason. Issue a synthetic invoice, save a proposal, approve/reissue it, and verify ID/number/counter stability, old/current PDFs, staff permissions, archive behavior and draft tail reuse.

Local checks (PowerShell, from repository root):

```powershell
$env:DEBUG='false'
$env:AFS_INVOICE_TEST_MONGO_URI='mongodb://127.0.0.1:27017/'
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_invoice_revisions.py tests/api/test_invoices.py tests/api/test_invoice_mongo_integration.py -q
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/api/test_access_control.py tests/api/test_system_settings.py tests/api/test_timezone.py -q
npm --prefix frontend run test -- src/features/invoices/Invoices.test.tsx src/components/overlays/Modal.test.tsx src/features/access_control/usePermissions.test.tsx
npm --prefix frontend run typecheck
npm --prefix frontend run build
# With Vite running locally on 127.0.0.1:5175:
frontend/node_modules/.cache/voice-node22/node.exe scripts/invoice-workflows-ui-check.mjs
```

## Production deployment instructions (provided only; not executed)

After owner code review, staging acceptance and database/object-storage backup, release the same reviewed artifact through the existing production process. Build the frontend and restart `afs-crm-backend` / `afs-crm-arq-worker` using the existing systemd procedure above. There is no new migration command for this release. Do not rerun or roll back the number-reuse index migration as part of this change.

Leave same-number reissue disabled until the accounting owner independently confirms statutory eligibility and explicitly approves the policy in production Invoice Settings. Confirm the recorded owner identity/time and test permissions before allowing real proposals. Enabling policy is a deliberate owner action, not an automatic deployment step.

## Rollback and recovery

Disable the policy first to block new proposals/reissues; this does not undo already approved effective revisions. Preserve all snapshots and approval history and take a backup before a recovery release.

Prefer a forward fix or a compatibility release that retains history access. Older binaries may reject the new keys in `invoice_config` because their schema forbids extras, so blindly rolling back the executable is unsafe even if the policy is disabled. A rollback must first provide a reviewed compatibility path for these additive fields; no script here deletes policy metadata or financial history to force an old build to start.

Do not reset counters, remove revision arrays, delete numbered invoices, or roll back the deployed reuse indexes. If an approved correction must itself be corrected, use another reviewed same-number revision when permitted. Never restore an older snapshot by silently overwriting the canonical document. Follow the established backup/recovery process for a disaster restore; no production recovery action is automated here.

No unrelated application modules or files were intentionally modified.
