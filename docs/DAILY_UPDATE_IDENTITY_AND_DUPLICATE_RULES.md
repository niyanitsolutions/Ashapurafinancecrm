# Daily Update identity and duplicate rules

Implemented locally on 25 November 2026. Database scope is the existing single-company CRM database. No production reconciliation has been executed.

## Identity resolution

Daily Follow-ups resolve exact stored Application, Lead, Case and Customer references. Current Customer names take precedence when the Customer/User relationship is valid. A schema-approved application name and then the linked Lead name provide fallbacks. Missing, conflicting, deleted or invalid references produce an Owner-review warning. Historical names, remarks and embedded history remain stored; read-time enrichment does not backfill records.

Exact matching trims names, collapses whitespace and case-folds. Punctuation and meaningful characters are preserved. `A-B` and `A B` are different names. Indian mobiles accept permitted spaces, parentheses, dots and hyphens, and +91/0091/91 prefixes; the comparison value is ten digits starting with 6?9. Existing international historical entries remain readable; new manual identity matching requires a valid Indian number.

Both normalized name AND mobile must match a unique authoritative Customer. A new manual follow-up reuses that Customer without creating another profile or modifying any Application. Employees can reuse only Customers reachable through their current assigned Applications. Partial or ambiguous matches fail with a review warning. An Owner can document a verified candidate link or a distinct-person decision with a reason. No fuzzy matching, application merging or mobile-only account attachment occurs.

## Activity idempotency

The existing POST `/daily-operations/follow-ups` accepts `idempotency_key`, `separate_activity_reason`, `identity_review_reason` and `review_customer_id`. The frontend holds one random submission key for the form lifetime and guards concurrent clicks. The existing `import_key` unique index stores an actor-bound receipt; an identical retry returns the same accessible record. Reusing a committed key with different details is rejected.

A separate partial unique `activity_key` index protects new active manual activities by canonical Customer (or exact independent name/mobile), IST date and activity slot. The primary slot permits one ordinary entry per date. A legitimate separate same-day activity requires an explicit reason and stable submission key. Different dates remain independent. Existing historical entries are also checked before a new primary entry. Deleted rows stay deleted on receipt replay. Updates retain version checks and append history; collisions return a conflict instead of overwriting another record. Import receipts and CRM-linked working keys retain their existing behavior.

The index includes only new keyed rows and performs no historical key backfill. Multiple legitimate historical activities are preserved. Historical rows without keys are checked before insertion, but their simultaneous modification by older application versions is not covered by the new unique constraint: deploy compatible backend/frontend together.

## Owner historical review

- GET `/daily-operations/identity-review/preview?limit=50&after=<cursor>`: read-only, stable ID cursor, maximum 100 rows. Counts are page-local. Reports missing names, valid links, exact/partial candidates and relationship problems. Candidate results cap at 200 and mark truncation.
- POST `/daily-operations/identity-review/{id}/link`: requires Owner, current version, preview fingerprint, verified candidate Customer ID, reason and `confirmed: true`. Revalidates live candidates and source relationships. It cannot merge Customers or change Application ownership.
- POST `/daily-operations/identity-review/{id}/rollback`: requires Owner, current version, the latest link event ID, reason and explicit confirmation. Restores only the latest unchanged identity link, retaining both history events. Later edits require fresh manual review.

The Daily Updates Owner UI exposes preview, candidate review, approval and undo. Both writes require MongoDB transactions and append an audit entry atomically; unsupported standalone deployments fail closed. No apply occurs merely by opening or paging the preview. Broken source records must be repaired in their authoritative module; this facility never rewrites Applications or deletes Customers.

Before any production approval, take and verify a restricted database backup, review every candidate and capture the preview. Rollback changes links only, never deletes business history. Wider historical Customer merges and bulk name backfills remain separate Owner-approved work.
