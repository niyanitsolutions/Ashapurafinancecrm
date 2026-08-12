from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import OperationFailure


async def ensure_customer_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["customers"].create_index("customer_code", unique=True)
    await db["customers"].create_index("user_id", unique=True)
    await db["customers"].create_index("converted_from_lead_id")

    await db["applications"].create_index("application_code", unique=True)
    await db["applications"].create_index("user_id")
    await db["applications"].create_index("customer_id")
    await db["applications"].create_index("lead_id")
    await db["applications"].create_index("assigned_to")
    await db["applications"].create_index("status")

    await db["application_documents"].create_index("application_id")

    # Partial, not full — the schema versioning design (Ask #6) deliberately keeps
    # multiple rows alive per product at once (DRAFT + ARCHIVED + the live ACTIVE one,
    # see ApplicationFormDefinitionRepository.find_all_versions_by_product); a full
    # unique index on (product_category, product_id) would make CustomerService
    # .create_new_version's insert of a second, still-DRAFT row for an already-frozen
    # product collide with the untouched prior version (DuplicateKeyError -> 500) the
    # very first time a schema is ever versioned. Scoping to status="active" both
    # avoids that (a DRAFT insert never matches the filter) and enforces the real
    # invariant that actually needs a constraint — at most one live schema per
    # product — which publish_form_definition's archive-then-activate two-step update
    # doesn't otherwise guarantee atomically against a concurrent publish.
    try:
        await db["application_form_definitions"].drop_index("product_category_1_product_id_1")
    except OperationFailure:
        pass
    await db["application_form_definitions"].create_index(
        [("product_category", 1), ("product_id", 1)],
        unique=True,
        partialFilterExpression={"status": "active", "is_deleted": False},
    )

    await _retire_pre_redesign_secure_links(db)
    await db["secure_links"].create_index("secure_code", unique=True)
    await db["secure_links"].create_index("lead_id")


async def _retire_pre_redesign_secure_links(db: AsyncIOMotorDatabase[Any]) -> None:
    """One-time, idempotent cleanup for the JWT -> secure_code redesign (see
    `SecureLink`'s docstring in models.py). Documents written under the old
    `token_jti`-based schema have no `secure_code`, so `SecureLink.model_validate`
    raises on every read that touches them — crashing the Lead Details secure-link
    card and Generate Link for any lead with one of these leftover rows.

    A soft-delete (the app's usual way to retire a record) isn't enough here: it
    would leave the fieldless document in the collection, and a plain unique index
    on `secure_code` still enforces uniqueness across soft-deleted rows too — two
    such rows both have no `secure_code` (Mongo treats a missing field as null for
    indexing), so the index build below would fail with a duplicate-key error on
    `{secure_code: null}` even after soft-deleting them. These rows predate the
    redesign entirely (no code path reads `token_jti`, and the model's own
    docstring says no JWT should be stored again), so unlike a real, once-valid
    secure link there is nothing about them worth preserving — they are removed
    outright. Matches nothing (no-op) once they're gone.
    """
    await db["secure_links"].delete_many({"secure_code": {"$exists": False}})

    try:
        await db["secure_links"].drop_index("token_jti_1")
    except OperationFailure:
        pass  # already absent — fresh DB, or already dropped on a prior startup
