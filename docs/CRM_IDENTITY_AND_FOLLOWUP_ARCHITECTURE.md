# CRM identity and Daily Follow-up architecture

Updated 2026-11-26. Local implementation; production rollout is not authorized by this document.

## Identity and account scope

The existing deployment has one company per CRM database (decision 001). `users` remains the single authentication identity collection. Customer, Employee and Referral Partner profiles retain their existing `user_id` references and independent business data. No tenant resolver or second authentication identity was introduced.

`User.role` remains the primary role. The additive, private `employee_access` object supports Owner-approved Employee access for a verified, active Customer or Referral Partner who has the corresponding real profile. It contains an Employee password hash, enabled flag, mandatory-password-change flag and grant actor/time. This deliberately supports the requested Employee association; it is not a general-purpose role union. Customer PIN/password and Partner password hashes remain unchanged. Employee form values populate only the Employee profile.

Every session has one `active_role`. Added Employee access requires explicit Employee password authentication (`login_role: employee`) from the internal login form. Customer PIN authentication retains the Customer role. Permissions use the session role and existing Employee grants, never the union of profile roles. Legacy sessions without `active_role` retain their primary role. Refresh preserves the session role and revalidates membership/profile status; the server does not trust a client-supplied role to authorize an existing session. Login idempotency receipts are separated by User and role.

The ordinary and stage-aware permission dependencies resolve the same effective User as plain authenticated endpoints. Employee self-service also checks the active role. Deactivating added Employee access does not disable the primary Customer/Partner account. Attendance excludes Customer/Partner sessions from the added Employee's work session history, including legacy primary-role sessions.

## Mobile identity

The shared backend normalizer is `app.shared.customer_identity.normalize_mobile`. Its existing supported policy is Indian ten-digit mobile numbers starting 6–9, with optional `+91`, `0091` or twelve-digit `91` representation and permitted whitespace/parentheses/dots/hyphens. Other international prefixes and last-ten-digit suffix matching are rejected. New User models and Employee requests canonicalize through this function; identity lookups use its anchored matching expression to detect historical formatted variants without rewriting them.

The existing unique `users.mobile` index prevents concurrent canonical identities; existing unique `employees.user_id`, `employees.email` and `employees.employee_code` indexes prevent duplicate profiles. Deleted identities are not silently replaced by Employee creation. Historical normalized collisions require Owner review; no canonical-mobile backfill or merge runs automatically. Anchored compatibility lookups may scan historical data until an independently approved cleanup is performed.

## Employee creation rules

| Existing identity | Server decision |
| --- | --- |
| No User | Create canonical User and Employee with existing onboarding rules in one transaction. |
| Existing Employee, including archived profile | Conflict; show the existing Employee link rather than allocate another profile. |
| Verified active Customer/Partner with real profile | Owner reviews masked/safe identity details, confirms User ID/version and supplies a verification reason; create Employee and add independent Employee access atomically. |
| Unverified, disabled, deleted, missing profile, conflicting historical identities or unsupported primary role | Refuse association; correct the mobile number or resolve ownership separately. |

`GET /employees/identity-preview` is Owner-only and returns no credential hashes. Employee creation requires Owner authorization in the service as well as the route. A versioned conditional User update, unique indexes and a transaction protect concurrent requests. User/Employee writes and the creation/access audit commit together; failures do not leave a partial profile. Existing department/designation/branch validation and permission assignment remain authoritative. No new default grant policy is introduced.

Added Employee passwords can be changed through the existing signed-in Change Password endpoint using the active Employee session. Primary-role recovery remains separate; the legacy SMS password-recovery mechanism must not be repurposed to reset an existing Customer PIN or Partner password as an Employee credential.

## Search and navigation

Global search state remains private to QuickSearch; it does not populate module search or advanced filters. Global Application results use `/applications/{id}?from=document-collection`, without `customer_id` or `expand`. Global Customer results open `/customers/{id}`. Application Back returns to the normal Document Collection list. Direct URLs and refresh retain that contract.

Document Collection's own Application modal links carry only the module's existing URL state plus the selected Application. Closing removes the Application parameter and preserves intentional filters, page size and pagination; browser history restores the previous module URL. Explicit Customer focus links inside legitimate module workflows remain available and are distinct from global search navigation.

## Workspaces and activities

One authoritative Application relationship has one canonical linked workspace in `daily_follow_ups`, identified by the existing `working_key = application:{id}`. Lead-only workspaces retain the existing `lead:{id}` mechanism. A Lead with one exact Application resolves through that Application; multiple Applications require explicit selection. Two Applications belonging to one Customer always have independent workspaces and histories.

Opening a workspace reuses the existing linked-follow-up API, permission checks, live assignment checks, unique working/import keys and idempotent upsert. Creation and audit commit together. Binding a prior exact Lead workspace to its Application preserves its ID and history and commits its audit transactionally. A historical noncanonical record already referencing the Application blocks creation and requires Owner review; it is never silently merged.

Saving a linked workspace uses the existing RecordForm, validation, Bank/NBFC options, scheduling and append-only history. Each edit is an activity in that same record. Version checks prevent double submissions or lost updates. Workspace changes, history, audit and any Lead activity commit together. Conflict responses retain frontend input; ambiguous outcomes are not automatically retried.

## Manual Add and standalone records

Daily Update Add record starts with a read-only identity search by Customer name/mobile/code, Application code or Lead code. Results remain permission/assignment scoped and display separate Application choices, product, status, assignee and workspace availability. Selecting one uses the existing linked-workspace API; no first match is chosen automatically. Inconsistent identity references require Owner review.

Search must precede the standalone form. Server validation independently blocks existing exact identities and partial/ambiguous matches; a separate-activity reason cannot bypass an existing Application relationship. The existing Owner review reason and explicit Customer choice support a Customer without Applications, without fabricating an Application. An Owner can record a reviewed distinct identity under the existing rules.

Genuine new prospects remain standalone: no Customer/User/Application is fabricated, manual name/mobile remain unverified reference data, and creator/time and history are retained. The list labels Application-linked, Customer-linked, Lead-linked, Standalone/Unlinked and Pending Identity Review records. Existing editing, scheduling, custom options, history and Bin actions remain available.

## Historical Owner review

The existing reconciliation preview is extended with original record context, exact-reference and normalized name/mobile candidates, reasons and separate Application choices. Preview and duplicate reporting are read-only. Partial name/mobile matches are suggestions rather than authority to link.

Only an Owner can approve an individual versioned, fingerprinted link. The selected Application must belong to the verified Customer/User, agree with existing source references and preserve assignment. Another workspace for that Application blocks approval; histories are not copied or merged. Linking retains the original Daily Follow-up ID, notes, dates, creator and history; identity references, canonical workspace key and audit are committed transactionally.

Undo is available only for the latest unchanged link event and restores its prior references without deleting history. Reject/leave-standalone decisions record an audit without rewriting the record. Explicit manual-review decisions mark review pending with versioned history and audit. There is no bulk merge or automatic historical repair.

`GET /daily-operations/identity-review/duplicates` reports bounded Application duplicate groups and normalized User identity collisions using IDs, without installing indexes or changing records. Reports disclose truncation; they are not proof that a large database has been fully inspected. No production duplicate scan was performed during this implementation.

## Storage, transactions and rollout

No new collection or production unique index is required. Fields are additive (`users.employee_access`, `sessions.active_role`, record review state/history). Existing unique User, Employee and working/import-key indexes must remain installed. Transaction-capable MongoDB replica-set support is mandatory; there is no fallback that skips audit or performs partial writes. Write conflicts return a conflict for explicit refresh/review.

Deploy matching backend/frontend artifacts only after Owner approval, backups and staging validation. Run the read-only duplicate report before enabling the new workflow on historical data and individually resolve conflicts; do not run automatic merges or backfills. Verify original Customer/Partner login, Employee permissions, session refresh, onboarding and all follow-up paths in staging using mocked SMS. Production configuration and Airtel/DLT values are outside this batch.

Rollback must preserve original User/profile IDs, primary credentials, relationships, histories and audit. Legacy artifacts ignore the additive membership fields and cannot use added Employee login; do not convert primary roles to compensate. Disabling added Employee access is a separate authorized action. Restore matched artifacts together; reviewed links can be reversed through the latest-link undo workflow only when its safety checks pass. Do not drop existing uniqueness indexes or delete profiles as a rollback shortcut.

## Limits

Archived or conflicting historical workspaces require individual Owner resolution; the system does not combine them. Hidden/unassigned identities are not disclosed to Employees. Identity search is bounded and requires narrowing when truncated. Existing activity/history limits remain enforced. Added Employee passwords can be changed while signed in. The legacy Owner SMS-reset action is explicitly blocked for added Employee access because it targets primary-role recovery. Recovery of a forgotten added Employee password needs a separately reviewed, role-specific workflow; this batch does not guess an SMS/OTP recovery contract. Primary Customer/Partner recovery remains unchanged. External legal or consent policy, production migrations and deployment approval remain outside local implementation.

## Additional compatibility guards

All User insertion paths refuse existing deleted or historically formatted mobile identities before canonical insertion. New canonical writes remain protected by the existing unique mobile index; no backfill is performed. Global full-mobile search uses the same anchored Indian-mobile compatibility matching and does not treat a foreign prefix as an Indian suffix. Historical records linked to an Application retain their original ID/history and compute subsequent activity keys from their Application workspace, allowing sibling Applications to have independent same-day activities.
