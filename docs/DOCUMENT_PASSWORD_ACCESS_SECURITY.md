# Document password access security

The 25 November 2026 batch supersedes the former write-only document-password policy at the explicit request of the Owner. Existing encrypted values and document files are retained.

GET `/applications/{application_id}/documents/{document_id}/password` is the only plaintext read API. Owner access remains available. An Employee must have active staff status, Customer viewing access, the separately granted `customer:document_passwords:view` permission, and current assignment to that exact Application. The document must belong to that Application. Customers, partners, unrelated employees and ordinary Customer edit grants cannot reveal it.

The new permission catalog entry has no parent, so it does not inherit ordinary module-wide grants. Fresh installation seed defines it without granting it. On an existing installation the Owner must create the same catalog definition through the existing Permissions administration and grant it deliberately to selected roles or time-bound access. Do not attach it under a parent permission or run a blanket permission reset. No default Employee grants are added.

The endpoint rate-limits each actor to 20 successful/attempted stored-password reveals per minute after scope checks, using the existing durable PIN rate-limit collection and TTL. Each reveal writes an append-only `document_password_revealed` event with actor, Customer, Application, Document and Document Type IDs plus the audit timestamp. Plaintext is never included in that event. If the audit write fails, plaintext is not returned.

Successful responses include `Cache-Control: no-store` (the global security middleware normalizes the endpoint?s stricter private/no-store header) and `Pragma: no-cache`. Ordinary document and Application responses contain only the existing `has_password` flag; encryption and upload behavior remain unchanged.

The staff document card masks by default and fetches only on Show Password. Hide, document/application/user changes, permission loss, browser blur and visibility changes clear local state. Reveals also expire after 30 seconds. Generation checks discard responses that arrive after navigation or authorization changes. The frontend requests `cache: no-store`; passwords never enter query caches, browser storage, URLs or error text. Server rejection remains authoritative even if a previously fetched UI grant is stale.

Automated tests use fixture-only passwords, disposable databases and no real document objects. Browser screenshots are taken after Hide, never with revealed values. Owner approval of production role grants and deployment remains pending.
