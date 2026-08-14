"""Index definitions for collections this module owns. Called once at app startup (see
main.py lifespan) — create_index is idempotent, safe to call every boot.
"""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import OperationFailure


async def ensure_access_control_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["roles"].create_index("name", unique=True)

    await db["permissions"].create_index([("module", 1), ("resource", 1)], unique=True)

    await db["role_permissions"].create_index("role_id")
    await db["role_permissions"].create_index("permission_id")
    # Partial, not full — AccessControlService.set_role_permissions's bulk-replace
    # soft-deletes a role's current grants (is_deleted=True) then inserts the new set;
    # re-granting the same (role_id, permission_id) pair — the normal case whenever a
    # role's permissions are edited a second time, e.g. Edit Employee's Business Modules
    # section — collides with the now-soft-deleted-but-still-present row under a full
    # unique index (DuplicateKeyError, surfaced to the client as a raw 500). Scoping the
    # constraint to only non-deleted rows is the same fix already applied to
    # `users` in auth/indexes.py for the identical reason. Drops the old, non-partial
    # index first — Mongo won't let create_index silently redefine an existing index's
    # options, and OperationFailure here just means it was already dropped/never existed.
    try:
        await db["role_permissions"].drop_index("role_id_1_permission_id_1")
    except OperationFailure:
        pass
    await db["role_permissions"].create_index(
        [("role_id", 1), ("permission_id", 1)], unique=True, partialFilterExpression={"is_deleted": False}
    )

    await db["employee_roles"].create_index("employee_id")
    await db["employee_roles"].create_index("role_id")
    # Same soft-delete-vs-unique-index issue as role_permissions above: AccessControlService
    # .remove_role soft-deletes the (employee_id, role_id) row rather than removing it, so
    # re-assigning the same role to the same employee later (assign_role) re-inserts the same
    # pair and would collide under a full unique index. Partial index, scoped to non-deleted
    # rows only — identical fix, same precedent (auth/indexes.py's `users.role`).
    try:
        await db["employee_roles"].drop_index("employee_id_1_role_id_1")
    except OperationFailure:
        pass
    await db["employee_roles"].create_index(
        [("employee_id", 1), ("role_id", 1)], unique=True, partialFilterExpression={"is_deleted": False}
    )

    await db["temporary_access"].create_index("employee_id")
    await db["temporary_access"].create_index("status")

    await db["geo_exceptions"].create_index("employee_id")
    await db["geo_exceptions"].create_index("status")
    await db["geo_exceptions"].create_index("geo_fence_id")
