# Document Collection UI, filters and search correction

## Assessment and root causes

The clean November 25 implementation was the starting point. Inspected DocumentCollectionPage, LeadListPage, the grouped aggregation/filter-options API, search service/DTO, QuickSearch, application/customer details, shared navigation context, router and static sidebar definitions, status catalogue, and existing tests.

- Grouped data was rendered as customer cards, rather than the previous AFS table. Group responses lacked a representative application summary for the table columns.
- Document Collection search lived in the Apply Filters form; typing alone never committed a server query.
- Assigned By used an assigning user's role as a fallback label. Automatic intake can record a customer as its technical actor, producing customer entries in an employee/user selector. The corrected selector resolves only actual staff identities; it does not rewrite assignment provenance.
- Direct applications have no Lead source ID. The old options query considered only joined Lead sources, missing stored submission provenance and authoritative configured sources.
- Follow-up status options returned stored values directly, including `custom:<id>`, without reading the shared status catalogue.
- Wrapped select labels included dynamically loaded option text in browser label matching. Explicit stable accessible labels and metadata loading/error handling remove that ambiguity.
- Global search supplied minimal labels/subtitles and legacy customer routes. The legacy list routes and application detail's default Back destination still led into disconnected list pages.

## UI correction

Document Collection is again an 11-column, horizontally scrollable table: selection, Application/Lead Code, Customer Name, Mobile, Source, Product, Assigned To, Application Status, Customer Account Status, Created On and Actions. Existing orange actions, typography, status badges, Bulk Upload and Create Lead are retained. Customer cards have been removed.

There is one parent row per customer group. The server chooses a deterministic representative application after sorting by submission, creation and ID. It supplies a whitelisted additive `primary` summary, not an unfiltered application document. Parent rows show the application count and latest submission, with Expand/Collapse in Actions. Expanded rows use an application table and retain independent 25-record pagination, code/View links, existing Lead Update or independent-application Move to Loan Management, document/history detail navigation, and authorized assignment/delete controls. Single-application groups expand too. Multi-application groups are selected through their individual application checkboxes; a parent checkbox does not silently select an unseen application set.

Group pagination remains server-side, default 200, with 10/25/50/100/200 choices. Actor scope and eligible lifecycle predicates still run before grouping, counts and pagination. No customer/application merge or lifecycle change was introduced.

## Filter corrections and API contract

Removed Assigned From, Assigned Until, Created Until and Employee Designation from the UI and the new page's allowed request keys. Old bookmarked parameters are excluded from new list requests. Legacy backend query parameters remain accepted for backwards compatibility; they are not sent by the corrected page.

Retained Assigned To, Assigned By, Product, Source, Branch, Follow-up Status/Employee, Bank/NBFC, Created From, Next Follow-up From/Until, Application Status, Documents, Customer Account Status, Product Category and Overdue. Independent dimensions continue to combine with AND.

- **Assigned By:** observed assigning IDs are resolved through staff-role Users and Employee/Owner profiles. Customers are excluded. Display names are preferred; a genuine legacy staff account without a profile name gets a role label, never a customer identity or raw ObjectId as its label.
- **Source:** existing Lead source references retain their IDs/names, and active configured Lead sources are available through the same Leads-level lookup boundary. Observed direct submission provenance is represented by `source_id=submission:<stored-value>`, for example `submission:customer_portal`. The server matches that exact stored provenance only on records without a Lead source. This is an API discriminator, not a new stored source or data update. Missing source data displays Not recorded/Source unavailable rather than a fabricated source.
- **Follow-up Status:** values stay unchanged in requests. Labels come from `daily_followup_status_options` for this database's existing company scope, including archived labels referenced by history. Built-in names supply readable fallbacks; an unresolved catalogue reference displays Unavailable follow-up status, never its internal token.
- **Follow-up Employee:** choices resolve the actual employees referenced by eligible follow-ups, rather than reusing a potentially different application-assignee pool.
- Metadata requests are bounded and read-only. Catalogue selectors are disabled while loading, report a separate error on failure, and have explicit accessible labels. Missing configuration labels get human-readable unavailable labels.

The grouped endpoint adds a validated `customer_id` focus filter and the `primary` summary. Expanded application projections add permitted customer/source/status display context. No existing collection or endpoint was removed.

## Live Document Collection search

Typing automatically commits search after 350 ms; Enter is unnecessary. The URL updates and page resets to one. Search covers current/verified-schema customer name, mobile, email, Customer ID, Application ID and Lead code using the existing scoped server query. Clearing restores the result set while retaining other applied criteria. Apply/Clear Filters remain available for advanced criteria. Removed parameters do not reappear in the payload.

List and application-expansion requests ignore responses after their effect is superseded or unmounted. Unit tests deliberately complete an old request after the current result and verify it cannot replace the newer data. Browser checks exercise live application/mobile search and clearing against the real local API.

## Global search and navigation

Results have explicit Customers, Applications, Leads and Employees sections, readable primary labels, and safely highlighted matching text using React elements rather than injected HTML. Customers show their business ID/mobile where permitted; Applications show code, resolved customer, product, status and assignee; Leads show code, name, mobile and status; Owner-only Employees show identifier/designation where available. Structured fields are additive to the existing label/subtitle/route contract.

The existing debounce, POST transport, stale-response guard, keyboard selection, loading/empty/error states and bounded pagination remain. Old results are cleared when a new query starts. Full PAN/Aadhaar, encrypted values, passwords, OTPs and submitted answers are absent from result projections. Owner-only exact PAN digest matching remains unchanged; no historical digest backfill was added.

Customer results and current-profile customer links target `/leads/document-collection?customer_id=<id>&expand=<id>`. That focus uses the same actor-scoped grouped API and automatically expands the matching customer. Applications retain the necessary `/applications/:applicationId` detail route with `from=document-collection` and validated customer context; Back returns to the corresponding group. Lead results still use legitimate Lead details. Employee details remain Owner-only.

Obsolete `/customers` and `/applications` list URLs redirect to Document Collection. Existing search/filter intent is retained, with legacy status/unassigned parameters translated into the new filter names. Their old list tab wrapper is no longer mounted. The sidebar already omitted the old Customers entry and was verified unchanged; Topbar/Quick Add have no stale list link. Internal Customer/Application details and backend endpoints remain for legitimate Loan/Insurance and other dependencies. Their new workflow links no longer send users back to obsolete lists.

## Preservation and limits

No production access, deployment, SMS, data repair, bulk update, customer merge, ID generation change, destructive migration or historical PAN backfill was performed. Assignment/follow-up history, optimistic profile edits, submitted answers, document/password security and versions, PAN/date validation, Bin authorization, ownership and lifecycle rules are preserved.

A focused customer group still shows only records eligible for Document Collection and visible to the actor. A customer whose authorized applications have all moved elsewhere can therefore have an empty focused intake view; this correction does not pull those applications backwards in their lifecycle or widen module permissions. Authorized individual application details remain reachable from global search and their owning workflows. Missing historical staff/catalogue/source names are reported honestly rather than inferred or repaired.

Existing substring-search/query-plan limitations and historical PAN records without a digest remain as documented in the November 25 report. No claim is made about live production latency, data quality or deployment state.

## Validation and evidence

Final exact outcomes and evidence paths are appended below. Tests use synthetic data and owned disposable loopback Mongo databases. The correction browser fixture explicitly compares all Application documents and its Customer before/after and verifies no Bin entry was created. The separate existing enterprise regression test exercises profile editing and deletion only inside its own disposable synthetic database.


### Exact final results

| Validation | Result |
| --- | --- |
| Full frontend suite | 509 passed, zero failed |
| Backend regression (Leads, Customers, Bin, assignment consistency, dashboard/search, enterprise and correction contracts) | 182 passed |
| Final correction contracts plus enterprise real-Mongo regression | 13 passed |
| New correction and existing enterprise browser integration | 2 passed; both at 390, 768 and 1366 pixels |
| TypeScript and production build | Passed; existing large-bundle advisory remains |
| ESLint | Zero errors, eight existing fast-refresh warnings |
| Ruff | Changed backend modules and new tests pass |
| Strict affected backend mypy | Three source files, zero errors |
| Whitespace / diff checks | Passed |

These backend runs overlap. The 13-test final run includes the new exact-PAN privacy regression. The correction browser proves live search without Enter, option-label correctness, AND filtering, grouping, individual application navigation, automatic customer expansion and obsolete-list redirects. Frontend tests additionally force out-of-order requests, verify debounce/page reset/clearing and application pagination, and test keyboard selection/highlighting and route preservation. Screenshots were inspected for table usability, filter layout and no root-page horizontal overflow; the tables intentionally scroll horizontally on constrained widths.

The existing browser helper was updated for context-bearing detail URLs and safe handling of navigation-canceled intercepted requests. Pending route handlers no longer block teardown. This is local test infrastructure, not an application retry policy or a change to any provider adapter.

### Screenshots

| Width | Table | Expanded applications | Advanced filters | Global search |
| --- | --- | --- | --- | --- |
| 390px | [Table](screenshots/document-collection-correction/table-390.png) | [Expanded](screenshots/document-collection-correction/expanded-390.png) | [Filters](screenshots/document-collection-correction/filters-390.png) | [Search](screenshots/document-collection-correction/global-search-390.png) |
| 768px | [Table](screenshots/document-collection-correction/table-768.png) | [Expanded](screenshots/document-collection-correction/expanded-768.png) | [Filters](screenshots/document-collection-correction/filters-768.png) | [Search](screenshots/document-collection-correction/global-search-768.png) |
| 1366px | [Table](screenshots/document-collection-correction/table-1366.png) | [Expanded](screenshots/document-collection-correction/expanded-1366.png) | [Filters](screenshots/document-collection-correction/filters-1366.png) | [Search](screenshots/document-collection-correction/global-search-1366.png) |

All data in this evidence is synthetic. See [browser results](screenshots/document-collection-correction/results.json), [validation](screenshots/document-collection-correction/validation.json), [preservation checks](screenshots/document-collection-correction/preservation.json) and [complete changed-file inventory](screenshots/document-collection-correction/changed-files.txt).

### Changed files

Backend changes are limited to `leads/document_collection.py` (summary/focus/options/source filtering), `search/service.py` (permitted result context/navigation), and `dashboard/schemas.py` (additive optional result fields). Frontend changes cover the Document Collection table/search, global result presentation/API types, legacy list redirects/router, current-customer/application detail links and shared return context. Existing and new unit/integration/browser tests follow those contracts. The linked inventory includes every path and screenshot. No production deployment, service restart or data migration was performed. Implementation is frozen after validation.
