"""One-time backfill for the Employee Permission Matrix redesign.

Before this redesign, the frontend's Business Modules section (`SHARED_RESOURCES` in
frontend/src/features/employee/businessModules.ts) silently auto-granted full
`leads:leads` (view/create/edit/export) and `reminders:tasks` (view/create/edit) access
to any employee who had at least one Business Module (Loan Management / Insurance
Management) checked — with no way to control Leads/Tasks independently. That coupling
is now removed from the frontend (Leads and Tasks are their own independently
toggleable rows in the new Permission Matrix), which means an existing employee's
"personal" role — created via the old flow, holding only explicit Loan/Insurance
grants — would silently lose Leads/Tasks access the next time it's read as "current
effective permissions," even though nothing about their job changed.

This script finds every such role and explicitly adds the same Leads/Tasks grants they
already had implicitly, so existing employees see zero regression. It does NOT touch
roles that never had a Loan/Insurance grant (nothing to backfill) or that already have
an explicit Leads/Tasks grant (already migrated, or never needed it).

Idempotent: safe to run twice. The second run finds every eligible role already has a
`leads:leads`/`reminders:tasks` grant and skips it — a true no-op, not just "harmless
to repeat."

Safe against unknown production state: every step skips-and-logs rather than raising,
since this runs against a real, already-live database this environment cannot inspect
ahead of time.

Run from backend/:  python ../scripts/migrate_decouple_leads_tasks_grants.py
Run from repo root: python scripts/migrate_decouple_leads_tasks_grants.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config.database import get_database  # noqa: E402
from app.features.access_control.repository import (  # noqa: E402
    EmployeeRoleRepository,
    PermissionRepository,
    RolePermissionRepository,
    RoleRepository,
)
from app.features.access_control.schemas import RolePermissionGrantInput, SetRolePermissionsRequest  # noqa: E402
from app.features.access_control.service import AccessControlService  # noqa: E402
from app.features.auth.repository import UserRepository  # noqa: E402

# The only linkage that exists today between an Employee and the role Create/Edit
# Employee manages on their behalf — a literal string match, not a real foreign key.
# Same convention EditEmployeePage.tsx (AUTO_ROLE_DESCRIPTION) already relies on.
AUTO_ROLE_DESCRIPTION = "Created automatically from Add Employee"

_LEADS_ACTIONS = ["view", "create", "edit", "export"]
_TASKS_ACTIONS = ["view", "create", "edit"]


async def main() -> None:
    db = get_database()
    roles = RoleRepository(db)
    permissions = PermissionRepository(db)
    role_permissions = RolePermissionRepository(db)
    employee_roles = EmployeeRoleRepository(db)
    users = UserRepository(db)
    service = AccessControlService(db)

    print(f"Connected to database: {db.name!r}")

    owners = await users.find_many({"role": "owner"}, limit=1)
    if not owners:
        print("No Owner user found in this database — set_role_permissions requires an Owner actor for its audit log. Aborting, no changes made.")
        return
    owner_actor = owners[0]

    leads_permission = await permissions.find_by_module_resource("leads", "leads")
    tasks_permission = await permissions.find_by_module_resource("reminders", "tasks")
    if leads_permission is None or tasks_permission is None:
        print("Permission catalog is missing 'leads:leads' or 'reminders:tasks' — run seed_permission_catalog first. Aborting, no changes made.")
        return

    business_module_permission_ids = {p.require_id() for p in await permissions.find_by_module("loan_management")}
    business_module_permission_ids |= {p.require_id() for p in await permissions.find_by_module("insurance_management")}

    candidate_roles = await roles.find_many({"description": AUTO_ROLE_DESCRIPTION}, limit=5000)
    print(f"Found {len(candidate_roles)} auto-created 'Add Employee' role(s) to inspect.")

    migrated = 0
    skipped_no_assignment = 0
    skipped_no_business_module = 0
    skipped_already_migrated = 0

    for role in candidate_roles:
        role_id = role.require_id()

        if not await employee_roles.find_for_roles([role_id]):
            skipped_no_assignment += 1
            continue

        existing_grants = await role_permissions.find_for_role(role_id)
        existing_permission_ids = {g.permission_id for g in existing_grants}

        if leads_permission.require_id() in existing_permission_ids or tasks_permission.require_id() in existing_permission_ids:
            skipped_already_migrated += 1
            continue

        has_business_module_grant = any(
            g.permission_id in business_module_permission_ids and g.granted_actions for g in existing_grants
        )
        if not has_business_module_grant:
            skipped_no_business_module += 1
            continue

        # Full replace is how set_role_permissions works (it soft-deletes every existing
        # grant for the role and inserts only what's passed) — so the payload must carry
        # the role's current grants forward untouched, plus the two new ones, never just
        # the two new ones alone.
        grants = [
            RolePermissionGrantInput(
                permission_id=g.permission_id,
                granted_actions=g.granted_actions,
                department_ids=g.department_ids,
                branch_ids=g.branch_ids,
            )
            for g in existing_grants
        ]
        grants.append(RolePermissionGrantInput(permission_id=leads_permission.require_id(), granted_actions=_LEADS_ACTIONS))
        grants.append(RolePermissionGrantInput(permission_id=tasks_permission.require_id(), granted_actions=_TASKS_ACTIONS))

        await service.set_role_permissions(role_id, SetRolePermissionsRequest(grants=grants), owner_actor)
        migrated += 1
        print(f"  migrated role_id={role_id!r} name={role.name!r}")

    print(
        f"\nDone. migrated={migrated}  "
        f"already-migrated={skipped_already_migrated}  "
        f"no-loan/insurance-grant-to-backfill-from={skipped_no_business_module}  "
        f"no-employee-assigned={skipped_no_assignment}"
    )


if __name__ == "__main__":
    asyncio.run(main())
