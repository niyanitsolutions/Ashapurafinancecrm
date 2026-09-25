# Insurance Analytics implementation

## Scope

The Insurance Management `Analytics` tab is a read-only reporting layer. It creates no business, customer, advisor, product, or policy records and reuses existing detail routes for navigation.

## Implementation files

- Backend: `analytics_router.py`, `analytics_service.py`, `analytics_repository.py`, and `analytics_schemas.py`, registered from `app/main.py`.
- Frontend: `analyticsApi.ts` and `InsuranceAnalyticsPage.tsx`, registered in the app router and Insurance Management layout.
- Tests: `test_insurance_analytics.py`, `InsuranceAnalyticsPage.test.tsx`, and the updated Insurance Management layout test.

## Data sources and metric definitions

- Advisor Business Analytics reads `advisor_business`. `Total Business` is the number of non-deleted business records; `Business Premium` is the backend sum of `AdvisorBusiness.premium`; product counts group the existing free-text `product_name`. Date filtering uses the record's `created_at` (the date the business was added), not `policy_issue_date`.
- Policy Pipeline Analytics reads insurance rows from `application_workflows`. Pipeline counts group the canonical `InsuranceStatus.ALL` values. `Policy Leads` counts records; `Policy Issued` counts the `policy_issued` stage; `Recorded Policy Premium` sums `insurance_details.premium_amount`. Date filtering uses policy-lead `created_at`, except issued policies use the existing `insurance_details.policy_issue_date`; issued rows without that date are not guessed into a date-filtered period.
- Product Analytics groups policy leads by the canonical `product_id` and resolves names from `insurance_products`. It never uses advisor-business product text.
- Advisor and Date filters affect both datasets. Product and Stage filters affect only policy analytics, as stated in the UI. Money aggregation is server-side and normalized to two decimal places before serialization. Existing source fields remain floats; no storage conversion was introduced.

## APIs

- `GET /api/v1/insurance-analytics/overview`
- `GET /api/v1/insurance-analytics/advisors`
- `GET /api/v1/insurance-analytics/advisors/{advisor_id}`
- `GET /api/v1/insurance-analytics/products`
- `GET /api/v1/insurance-analytics/products/{product_id}`

All list/drill-down endpoints are paginated. Aggregation occurs in MongoDB; React never downloads entire policy/business datasets for calculation.

## Authorization and visibility

No new permission was added. Advisor analytics requires the existing `insurance_management:advisors:view` permission. Policy analytics evaluates the existing parent/stage `insurance_management:applications*:view` permissions and omits unauthorized stages. Employee policy queries reuse `InsuranceCaseService`'s authoritative creator/Application-assignee scope, including drill-down and user-supplied filter parameters. Policy-only employees receive Advisor filter options derived only from that same scoped result set. Owner retains the existing permission bypass. Advisor business visibility matches the existing Advisors APIs.

## Navigation and drill-down

- Pipeline cards open the existing stage-specific Policy Leads pages.
- Policy codes open the existing Insurance Case details page; customer names open the existing Customer details page.
- Advisor business rows open the existing Advisor details page, which remains the single business-detail implementation.

## Database and deployment

No schema, index, migration, seed, environment, or production configuration change is required. Existing indexes cover advisor-business advisor lookup, workflow case/status, and assignment lookups. Product/date-filtered analytics narrow the insurance workflow dataset before grouping; no speculative production index was added without query telemetry.

## Tests and limitations

Backend coverage verifies dataset separation, totals, filters/date boundaries, owner access, employee case scoping, unauthorized access, and drill-down records. Frontend coverage verifies the tab, sections, filters, loading/error UI, stage navigation, and both drill-downs.

Known limitation: advisor business stores product names as existing free text rather than canonical insurance product IDs, so the canonical Product filter intentionally does not alter Advisor Business Analytics. Existing monetary fields are floats; responses are rounded to currency precision, but changing storage to Decimal128 would require a separately reviewed migration.
