# Customer Portal modernisation plan

Scope: existing AFS CRM, local implementation only. No production access, deployment or SMS. Customer presentation is isolated from staff/partner shells, shared controls, authentication services and Airtel.

## Inspected architecture

CustomerPortalLayout already separates `/portal` from AppShell and the partner shell. Customer pages share existing schema-driven forms, application/document APIs, notification/messaging/support systems and private upload storage. Registration and customer PIN sessions already exist. Lead-less loan applications already feed Leads → Document Collection; insurance has an existing separate case workflow which must be preserved. No new identity or application module is needed.

## Batch 1 — customer presentation

Add customer-scoped tokens, page/card/progress components and responsive navigation. Modernise dashboard using actual application summaries; preserve action-required loan banners. Use the customer page wrapper for applications, documents, profile, messages, notifications and support. Customer-only registration/link presentation may change; staff login layout and authentication services remain unchanged. Customer PIN visibility is a presentation control only.

## Batch 2 — unified journey

Keep product-defined wizard sections and existing autosave, validation, tab lock, document replacement and submission confirmation. Improve save/resume and details visibility without inventing financial fields. Preserve secure-link return paths and add resumed-profile return handling. Add backward-compatible source/activity metadata and idempotent submission with atomic compare-and-set, requiring no new transaction topology. Preserve staff-created application APIs and staff screens. Prove existing Document Collection visibility before changing its query; any addition must preserve assignment and category rules.

## Batch 3 — integrated validation

Run relevant customer, workflow, document/privacy, session, PIN and staff/partner regressions using mocked providers. Capture existing and updated customer screens at 360, 390, 768, 1024, 1366 and 1920 pixels. Check navigation, schema wizard, resume, secure-link redirect, document history, real API submission and Document Collection. Compare protected source files against the baseline to verify preservation. Run targeted lint, type checks and production build. Record exact results and any baseline failures, deployment prerequisites and manual acceptance steps in CUSTOMER_PORTAL_IMPLEMENTATION_REPORT.md.

## Boundaries and conflict resolution

No global CSS or shared staff control redesign. No Airtel/authentication backend changes. The existing login tabs and internal password surface remain intact; customer-only PIN visibility and presentation are isolated inside the customer panel. Registration continues to use the existing verified account creation and PIN session APIs. No real SMS is sent. Existing historical application sources remain `unknown` unless provable from records; no fabricated provenance or destructive backfill. Existing staff insurance processing remains unchanged even when customer submission metadata is exposed in Document Collection.

Completed batches are frozen except for verified defects found during integration.

## Local execution status

All three batches are complete locally and frozen. The six requested viewport checks, actual local API journeys, registration/PIN recovery, scoped regressions, lint, targeted type checks and production build pass. Known deployment dependencies and the existing development Strict Mode refresh behavior are recorded in [the consolidated report](CUSTOMER_PORTAL_IMPLEMENTATION_REPORT.md). No production deployment or real SMS/storage request was performed. Subsequent changes should address verified defects, not expand the redesign into protected staff/partner interfaces.
