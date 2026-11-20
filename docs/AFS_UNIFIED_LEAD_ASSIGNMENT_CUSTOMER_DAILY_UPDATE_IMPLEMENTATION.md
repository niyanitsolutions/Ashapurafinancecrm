# Unified lead, assignment, customer and Daily Update implementation

Local implementation, 19 November 2026. No deployment, production database access, real Meta delivery or SMS submission was performed.

## Architecture and preserved workflows

The pre-implementation assessment is [AFS_UNIFIED_ARCHITECTURE_ASSESSMENT.md](AFS_UNIFIED_ARCHITECTURE_ASSESSMENT.md). MongoDB/Motor, existing User/Employee/Customer models, database-per-company scope (decision 001), permission engine, PIN/password authentication and session families remain in place.

Ordinary Meta captures and manual leads still create the existing Lead at `stage=fresh`. Automatic assignment writes ownership without advancing that stage. Explicit existing assignment actions retain their existing stage transitions. Fresh list and count queries include the narrowly marked automatic/creator-owned Fresh intake; a plain unassigned query without the Fresh stage remains a real unassigned query. Employees see their own assigned Fresh intake and their own unassigned drafts, with the existing broad-visibility permission respected.

Customer submissions still appear in Document Collection. Independent applications remain lead-less; secure-link applications retain their original lead/application IDs. No synthetic Lead is inserted for a portal application. Existing tabs, routes, ordering, bulk operations, exports, case transitions, document validation, attendance and Re-Eligible scheduling remain intact.

**Existing compatibility boundaries:** capture configuration also supports an insurance-policy destination. That existing destination and its advisor assignment model are preserved; the new employee rotation applies to ordinary Lead intake and eligible unassigned portal Applications, not to advisor IDs on insurance cases. Existing ordinary Lead creation rejects a repeat mobile/customer identity and directs staff to the existing record. That protection is retained; genuine separate opportunities use the existing multiple-Application flow. No fuzzy or phone-only merge was added.

## Customer identity

After successful submission, including a safe repeated submit, the service fills missing profile information from exact canonical top-level fields present in that application's stored schema: `full_name`, `email`, `date_of_birth`, `gender`, `address`. Each field is validated independently against the existing profile contract. Differently named or co-applicant fields are not guessed. An incompatible field is skipped without rejecting an otherwise valid submission.

The target must match both `customer_id` and `user_id`. The mobile number, authentication identity, PIN and existing profile values remain unchanged. Only blank/`Customer` names are automatically replaced; established names require the existing explicit profile update workflow. Conditional writes protect a concurrent profile edit. Each automatic field change stores its old/new value, actor, timestamp and application reference in private `customers.profile_history`; the audit entry records IDs and field names without the submitted body. These history fields are excluded from existing customer responses.

An exact linked Lead's placeholder name may be filled too; an established prospect name is preserved. Portal greetings now show “Name not provided” for the registration placeholder. Document Collection reads the existing Customer profile for lead-less applications; linked Daily Follow-up reads the live profile; operational dashboards resolve recent submitted applicants in a batch.

There is no historical bulk profile rewrite. Shared family mobiles and uncertain identities remain manual-review situations under the existing globally unique account-mobile policy.

## Owner-controlled assignment

The Owner-only `/settings/auto-assignment` screen offers enable/pause, ordered employee selection, current assigned-lead counts, paginated unassigned intake, explicit retry and assignment history with actor/employee names and source links. Existing manual lead and application reassignment screens are retained.

The default is disabled. Selection is limited to 100 employees; the picker lists up to 1,000 non-deleted employees. New selections require active employee and login accounts. Retained pool members who become inactive can be removed or left in a paused configuration; intake skips unavailable members. Product-module eligibility reuses the existing Lead assignment eligibility logic.

Eligible Owner-created/manual and ordinary captured leads use rotation when enabled. An employee's own newly created lead defaults to that employee and remains Fresh. An explicit assignment supplied through the existing form keeps its existing behavior. An unlinked portal submission is assigned only if unassigned, without an already assigned case. An application/lead with an existing assignment is not rotated again. Document upload does not invoke assignment.

### Concurrency and recovery

1. Persist the original business record before assignment.
2. Atomically claim that unassigned eligible record with a unique token and two-minute lease.
3. Atomically increment the shared settings sequence and select from the current eligible ordered pool. Persist the reservation on the original record.
4. Commit ownership only while the token still matches and the record remains unassigned. A manual assignment fences a delayed automatic writer.
5. Commit an assignment event outbox in that same record update; deliver deterministic-ID audit, timeline and internal notification records. Recovery can repeat delivery safely.

The sequence is shared across Lead/Application intake and is not reset when the pool changes. A reusable reservation keeps its position on retry while the employee remains eligible and in the pool. Removed/inactive members are replaced by a new reservation. Mongo atomic operations work on a standalone server; this engine introduces no replica-set requirement. A crash between counter allocation and reservation persistence can skip a sequence position. It cannot duplicate a position or lose the business record; strict gap-free rotation through process failure is not claimed.

Failures store only `assignment_unavailable`, retain destination/IDs, and notify Owners. The existing minute Daily Operations worker delivers outboxes and retries previously attempted pending assignment up to three attempts, in batches of 100 per collection. Expired leases are recoverable. Owners can explicitly retry after the automatic limit. Records created while rotation is paused remain visible in the queue for **explicit** retry; enabling rotation does not automatically redistribute that backlog or pre-release records.

Inactive-employee work remains assigned historically. A bounded, cursor-based scan alerts Owners rather than reassigning it. Inbox writes use deterministic IDs, including the relevant employee revision for inactive-work alerts. New unassigned intake while paused also generates an internal assignment-attention notification. No external messages or new scheduled jobs are introduced.

## Capture idempotency

The existing capture receipt remains authoritative for completed events. Ordinary Meta Lead creation additionally uses a server-derived SHA-256 intake key. A unique partial index and duplicate-key recovery return the same Lead under concurrent delivery or a retry after a missing receipt. Receipt persistence is an idempotent upsert. A different inquiry with a conflicting mobile is still sent through existing validation/review, not silently merged.

Configured insurance-policy capture keeps its existing idempotency and routing implementation. Real Meta transport was not exercised.

## Daily Follow-up integration

“Open Daily Follow-up” is added to the existing Lead and staff Application details. It opens or creates the existing `daily_follow_ups` working record and navigates to its edit dialog. The original Lead/Application link is displayed in that dialog. Customer and employee fields for this linked context are read-only; the server independently enforces the relationship and ownership.

`working_key` is based on the canonical, lowercase stable source ID, not a name or mobile. Repeat clicks use an atomic upsert and the existing unique `import_key`, plus the new unique partial `working_key` index. Duplicate opens do not add history. When a lead has one exact application, both entry points resolve to that application's workspace. An earlier lead-only workspace can be bound to its first exact application without replacing its ID/history. Multiple applications require choosing the intended application; separate genuine applications get separate records.

New linked rows retain `lead_id`, `application_id`, `customer_id` where known. Existing lead/case ownership joins are extended with indexed application/customer joins. Reassignment changes current access on reads and lists; a former employee loses access. Only projected public fields leave the service; joined documents, internal ObjectIds, profile history and credentials are excluded. Due notifications resolve the current application assignee too.

Every successful edit retains its existing version check and before/after Daily history. Linked edits also write an audit reference and, where a Lead exists, a Lead timeline event. Daily remarks and business values stay in the linked workspace rather than being copied into unrelated case fields. Opening a row does not change Lead/case status. Official status transitions and the Lead's separate calendar remain in their original permission-controlled workflows. The dashboard presents the two schedules separately so they are not counted as the same event.

Standalone Daily entries, all existing Daily Update tabs, Loan Progress Tracking, imports/exports, attendance and Re-Eligible workers are retained. New arbitrary CRM IDs remain rejected by the ordinary independent-row create API; the explicit linked action resolves and authorizes the source server-side.

## Dashboard changes and metric definitions

Existing cards/charts and financial calculations are retained. The additional operational section provides:

| Metric | Calculation and scope |
|---|---|
| Existing lead-tab badges | Existing `LeadService.get_tab_counts`, including the merged Document Collection rule; current stock, not creation-period counts |
| Lead workload | Database grouping of non-deleted Leads created in the selected dashboard period; current assignee and current stage; 20 employee groups per page |
| Follow-up priorities | Current permitted Lead schedules, overdue first, up to 10 source links; independent of lead creation date |
| Recent applications | Up to 10 submitted Applications created in the selected period; product filter and current assignment; actual profile names resolved in a batch |
| Submitted/draft applications | Actual Application counts within the same creation cohort; requires existing customer-view permission |
| Daily Follow-up workspace | Existing current normal-workspace list/count rules and employee scope, across dates/products; overdue uses existing open-status/past-due logic; up to 10 links |
| Assignment waiting/failures | Eligible unassigned records / attempted pending records, company-wide and Owner-only |
| Automatic assignments recorded | Durable `crm_auto_assigned` audit-event count; history, not a fabricated workload or financial figure |

Existing dashboard date/product-category/source filters are used. The new section adds Owner employee and Lead stage filters. Source and stage filters apply to Leads; applications use period/product/assignment, and Daily Follow-up uses its own existing rules. These boundaries are explained in the UI. Current tab badges intentionally remain identical to their existing source lists. All employee queries force the authenticated employee scope; a supplied employee ID cannot broaden it. Existing broad-visibility permissions still govern the existing tab counts.

Financial, disbursement, approval, conversion and document metrics continue to come from the existing widgets. No new “contacted”, “completed”, money or conversion figures are inferred from remarks or arbitrary custom labels.

## API additions

All paths below have the existing `/api/v1` prefix.

| API | Authorization / behavior |
|---|---|
| GET/PUT `/leads/auto-assignment` | Active Owner only; settings version required for save |
| GET `/leads/auto-assignment/pending?page=…` | Owner; combined server-paginated Lead/Application queue |
| POST `/leads/auto-assignment/retry/{leads|applications}/{id}` | Owner; original record only |
| GET `/leads/auto-assignment/history?page=…` | Owner; allowlisted audit metadata, batch-resolved actor/assignee names |
| POST `/daily-operations/linked-follow-up` | Existing Daily create and Lead view grants; source ownership, plus customer-view grant for an Application |
| GET `/dashboard/operations` | Existing staff authentication; Lead view required; additional customer/Daily sections permission-gated |

Registration, PIN, OTP, sessions and Airtel APIs are unchanged.

## Database changes and preflight

Additive metadata only: Lead intake key/assignment origin and eligibility; per-record sequence/reservation/lease/attempt/error/outbox fields; submitted profile history; linked Daily references and working key. `auto_assignment_settings` stores the single-company configuration/counter. `auto_assignment_scan_state` stores a recovery scan cursor. These are operational metadata, not parallel business entities.

New indexes:

* `leads.intake_key`: unique for string values only.
* Lead/Application `assignment_sequence`: unique for numeric values only; compound pending/assignee and eligibility/assignee/creation indexes; sparse outbox-sequence index; non-deleted creation/assignee index.
* `audit_logs(event_type, created_at descending)`.
* `daily_follow_ups.working_key`: unique for string values only; application/customer ObjectId relationship indexes.

Existing IDs, unique account rules, customer/application/document references and indexes are retained. No historical assignments, rows or statuses are bulk rewritten.

`scripts/audit_unified_crm.py` is **read-only**. It streams reference checks in batches of 200 and reports counts/at most 200 issue IDs, without names, mobiles, credentials or documents. It detects duplicate idempotency/working keys, orphan/mismatched Application references and legacy Daily links requiring review. It neither creates indexes nor repairs/merges data.

The representative local inconsistent fixture detected four reference problems and one duplicate creation key, with zero changes applied. Evidence: [preflight-synthetic.json](screenshots/unified-crm-2026-11-19/preflight-synthetic.json). This is synthetic data in a disposable loopback Mongo database. **No production reconciliation result is claimed.** Existing unmatched records must be reviewed by an Owner before any separately approved correction.

## Security safeguards

The existing company database resolver and session/RBAC architecture are unchanged. Cross-company isolation is the existing deployment/database boundary; a multi-company membership resolver was not introduced. Tests use isolated disposable databases and existing role/record checks, not a fabricated tenant model.

Owners alone configure/retry assignment. Employee IDs resolve server-side. Active login/employee and existing product access are checked before choosing an assignee. Ownership and lease-token predicates prevent another assignment from being overwritten. Ordinary employee/partner/Owner login and customer PIN authentication remain untouched. Customer identity is never resolved from a name match; registered mobile is never changed by application submission. Private document storage/signing remains unchanged.

Assignment errors use a fixed code; notification/audit outboxes contain IDs, timestamps and field names. No PIN, password, OTP, token, Airtel configuration, document content or full sensitive request is added to logs or responses. The private profile-change history contains only profile fields and is not exposed through the existing API mappers.

## Validation

* Broad relevant backend run: **443 passed**, 1,372 existing warnings, 1,105.25 seconds. Includes auth/PIN, customer, Lead/capture, dashboard, Daily, assignment, document-collection and workflow suites selected below. Opt-in browser/real-Mongo files and separate registration-migration files were excluded from that broad selection; real-Mongo/browser checks were executed explicitly.
* Full frontend suite: **489 passed**, no failed tests. Used two workers after a first run exposed missing permission mocks in existing staff-application tests and parallel-run errors. Those mocks were updated; no application behavior was weakened to satisfy tests.
* Focused new integration/real-Mongo suite: **17 passed**, 27.06 seconds. Final expanded run: **119 passed**, 90 existing warnings, 202.33 seconds, covering the new tests plus existing Reminders, Daily Operations/automation, assignment consistency and portal-modernisation tests. These runs overlap the broad regression suite; their counts are not distinct-test totals.
* Responsive real API/browser journey: **passed** at owner widths 390/768/1366 and employee width 1366; normal password login, owner pause/resume, source navigation, repeated working-record opening, scope/route restriction and horizontal overflow checks. Latest complete journey passed in 27.90 seconds; screenshots were refreshed after the final UI additions.
* Final targeted frontend run: **12 passed** across the new controls and existing staff-application navigation tests. Full frontend suite above remains the broader regression result.
* Targeted ESLint: zero errors or warnings. Ruff: all changed backend application files, new backend tests and preflight script passed. New Python modules/tests/script formatted with Ruff; surrounding legacy files were not reformatted wholesale. Strict mypy: **10 source files passed**. Final explicit TypeScript check and production build passed; Vite reports the existing bundle-size advisory (450 modules, 18.86-second final build).
* Preservation check against `68aeae675f115c7fa50e4dba2e83ec89adac9d20`: **159 protected tracked files unchanged**, including authentication, Airtel integration/communication, employee/security/geo modules, attendance/Re-Eligible logic, Lead tab/list definitions, database/repository boundary and financial dashboard providers. Evidence: [preservation.json](screenshots/unified-crm-2026-11-19/preservation.json).

Representative commands (PowerShell, repository root):

```powershell
$env:DEBUG='false'
$env:AFS_INVOICE_TEST_MONGO_URI='mongodb://127.0.0.1:27017'
$testPaths = @(rg --files tests/api | Where-Object {
  $_ -match 'test_(leads|lead_capture|customer|assignment_consistency|dashboard|daily_|document_collection|workflow|auth|pin)' -and
  $_ -notmatch 'browser|mongo|registration'
})
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml @testPaths tests/api/test_unified_operations.py tests/api/test_unified_submission.py tests/api/test_unified_mongo.py -q --disable-warnings
npm --prefix frontend test -- --maxWorkers=2
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Real-Mongo fixtures accept loopback only, create random disposable databases and remove only their own databases. Automated tests use synthetic identities/mocked provider/storage responses and do not send SMS. Browser uses a local production preview on 5175 and a local test API on 18772; remote HTTPS requests are blocked by its harness.

## Files and release status

Backend additions: `features/leads/{auto_assignment,assignment_routes,reconciliation}.py`, `features/customer/submitted_identity.py`, `features/daily_operations/linked.py`, `features/dashboard/operations.py`. Existing Lead model/service/repository/router/indexes, Customer submission service, Daily router/service/notifications, dashboard router, Reminders notification constants and the existing Daily worker entrypoint are integrated.

Frontend additions: `AutoAssignmentPage`, `OperationsMonitor`, `OpenLinkedFollowUp` and their tests. Existing settings navigation/router, dashboard composition, Lead/staff-Application details, linked Daily form/dialog, portal placeholder greeting and staff-Application test permissions are updated. The existing Leads layout/tab definitions and shared authentication/Airtel code are unchanged. Exact paths: [changed-files.txt](screenshots/unified-crm-2026-11-19/changed-files.txt).

Tests: `test_unified_operations.py`, `test_unified_submission.py`, `test_unified_mongo.py`, `test_unified_browser.py`, `scripts/unified-crm-ui-check.mjs`. Existing Fresh visibility tests now use the real `stage=fresh` query, reflecting the explicitly requested employee-creator assignment behavior. Full changed-path evidence accompanies this report.

## Production requirements — not executed

1. Owner reviews this local release and staging results. Back up the intended company database using the established operational process. Check the web and worker use the same release and intended database.
2. With that environment loaded, run the read-only preflight: `backend/.venv/Scripts/python.exe scripts/audit_unified_crm.py` (Linux deployment equivalent: `/opt/afs-crm/backend/.venv/bin/python /opt/afs-crm/scripts/audit_unified_crm.py`). Stop for any duplicate keys or ambiguous references; do not merge/delete them automatically.
3. Verify the additive indexes against a restored representative staging dataset. The existing application startup installs the new indexes through its existing Lead/Daily initializers. No manual backfill is required. Do not run unreviewed unrelated legacy migrations.
4. Build the frontend and install/restart the backend using the existing `/opt/afs-crm` deployment runbook. Restart **both** `afs-crm-backend` and `afs-crm-worker` on the same approved release. No new dependency, Redis queue, SMS setup or scheduled job is required.
5. Verify all seven existing Leads tabs, configured Meta destinations, an independent portal submission, a secure-link submission, documents, linked and standalone Daily entries, and Owner/employee scoping in staging. Real Meta transport and production storage require separate authorized verification.
6. Keep rotation disabled until the Owner selects employees, checks their active accounts/product access and enables it. Use explicit retry for the intended paused backlog. Do not reassign historical records in bulk.

Rollback should first pause assignment and retain the additive data/indexes. A compatible rollback must retain the new notification type and Fresh-intake visibility handling: an older strict notification enum cannot read new attention notifications, and older Fresh filtering omits newly assigned Fresh records (they still exist in Assigned). Do not blindly revert schema/data, clear real customer names or delete history. Use a reviewed compatible rollback or roll-forward fix.

## Remaining operational limits

No live integration or production behavior is certified by these local checks. The existing unique-mobile business policy and insurance advisor pipeline remain explicit compatibility boundaries. Schema keys outside the documented canonical identity keys need an explicit reviewed mapping, not a guessed transformation. The new Lead workload calculation is aggregated/paginated; existing tab-count internals and recommendation machinery retain their pre-existing implementation and scale characteristics. Automatic rotation can have skipped slots after a crash, and its retry/picker batch limits are intentional and described above.
