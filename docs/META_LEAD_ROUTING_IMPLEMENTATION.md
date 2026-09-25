# Meta Lead Routing implementation

## Scope and architecture

The existing Meta OAuth, Page subscription, callback URL, HMAC verification, Graph API retrieval, selected-form filter, webhook acknowledgement, capture failures, and duplicate receipts are unchanged. Routing now occurs after Graph retrieval and before destination creation:

`form_id -> active meta_lead_routings rule -> default product or normalized question answer -> validated active product -> configured destination`

The legacy `capture_sources.default_product_category/default_product_id` fields are preserved but are no longer read as a runtime fallback for Meta leads.

## Database changes

- Additive `meta_lead_routings` collection. No existing leads or source rows are changed.
- Unique index on `meta_form_id` plus lookup index on `meta_form_id/status/is_deleted`.
- `capture_receipts` remains backward compatible. New optional `destination_module` and `destination_record_id` fields let the same idempotency mechanism cover Insurance Policy Leads; old rows still validate as Leads receipts.
- `CaptureFailure` accepts precise routing reasons and the `needs_routing_configuration` state.
- No destructive or mandatory schema migration.

## API changes

- `GET /api/v1/lead-capture/meta-routings`
- `POST /api/v1/lead-capture/meta-routings/sync`
- `POST /api/v1/lead-capture/meta-routings/{form_id}` (create; duplicate Form ID returns 409)
- `PUT /api/v1/lead-capture/meta-routings/{form_id}` (save/update)
- `PATCH /api/v1/lead-capture/meta-routings/{form_id}/status`

All endpoints reuse `lead_capture:sources` RBAC and existing authentication.

## Routing behavior

- Default mode uses the form rule's product ID.
- Customer-answer mode matches one configured Meta field key/question. Matching trims, folds case, and normalizes punctuation/spacing; it does not use fuzzy matching.
- Answers use explicit answer-to-product-ID mappings with the same safe normalization.
- Loan products must be active Loan products and route to `Leads -> Fresh Leads` through `LeadService.create_lead`.
- Insurance products and their Insurance Category must be active. They route through `InsuranceCaseService.create_manual_case` to `Insurance Management -> Policy Leads -> Fresh Leads`; no general Lead row is created.
- Missing forms/questions/answers/mappings, inactive products, mismatches, and invalid destinations are acknowledged with HTTP 200, preserved as capture failures, and never guessed or defaulted.
- Retrieved `field_data` is retained in the restricted capture failure document for a later admin retry and is not logged.

## Admin UI

`Settings -> Lead Sources -> Meta` now shows per-form routing cards with Sync Forms, immutable Form ID display, active/inactive/unconfigured state, category-dependent active products, default/customer-answer modes, observed-question suggestions, answer mappings, fixed valid destinations, and activation controls. The former global Meta Personal Loan mapping editor is removed.

## Deployment

1. Back up MongoDB and record the current application version.
2. Deploy the code to staging and run the automated checks listed below.
3. With production's current code still serving traffic, run `python scripts/migrate_meta_form_routing.py`. It creates explicit routes only for forms already connected at that moment, using the preserved legacy default. It never overwrites a route and never assigns a default to a future form.
4. Review `meta_lead_routings` in the CRM UI. Configure any intentionally multi-product or Insurance forms and verify every currently selected form is active.
5. Deploy backend instances. Startup creates the additive indexes.
6. Deploy the frontend.
7. Use controlled payloads, then Meta's Testing Tool where it supplies a retrievable lead ID. Do not run a paid ad merely for deployment verification.
8. Monitor capture failures for `needs_routing_configuration` and the safe routing reason codes.

## Rollback

1. Roll back frontend and backend application artifacts to the prior version. The old version ignores the additive collection/receipt fields.
2. Leave `capture_sources` legacy defaults intact; the prior backend resumes its prior behavior.
3. Optional database cleanup: run `python scripts/migrate_meta_form_routing.py --rollback`. It removes only untouched version-1 rows created by the migration; admin-edited routes are preserved.
4. Additive indexes/collections may safely remain. No existing Lead, Application, Policy Lead, receipt, or source row needs restoration.

## Verification results

- Backend broad regression: 161 passed across lead capture, Meta routing, manual Insurance Policy Leads, and general Leads suites.
- Final focused backend rerun after the last routing refinements: 33 passed.
- New routing suite: single-product Personal/Business/Home, multi-product Personal/Business/Home, normalized question punctuation, missing question, missing answer, unknown answer, inactive product, Insurance Policy Lead destination, and duplicate Form ID.
- Frontend Meta routing tests: 3 passed.
- Frontend TypeScript check: passed.
- Frontend production build: passed (existing large-bundle warning only).
- Ruff on changed backend/scripts/tests: passed.

## Remaining operational risks

- A production form omitted from the pre-deployment migration/review will be held safely instead of imported until configured. This is intentional to prevent silent Personal Loan misclassification.
- Insurance routing requires an active Product Schema, matching the existing manual Insurance creation rules. A product without one produces a captured failure rather than a partial Policy Lead.
- Meta question keys are controlled by Meta/form configuration. After editing a form question, review its route; unknown keys/answers fail safely.
