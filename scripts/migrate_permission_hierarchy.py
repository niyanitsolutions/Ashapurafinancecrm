"""Add hierarchical RBAC catalog metadata without changing effective legacy grants.

Idempotent and safe to rerun. It creates module roots and current tab nodes, links the
existing resource permissions beneath them, and marks modules enabled for roles that
already have a grant in that module. It does not assign module action defaults, so it
cannot broaden an existing employee's access. DO NOT run automatically during deploy.
"""

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config.database import get_database

ACTIONS = ["view", "create", "edit"]

CHILDREN: dict[tuple[str, str], tuple[str, str, list[tuple[str, str]]]] = {
    ("loan_management", "applications"): ("__module__", "page", [
        ("applications.new_customer", "Loan Cases / New Customer"),
        ("applications.credit_evaluation", "Credit Evaluation"),
        ("applications.offer_acceptance", "Offer Acceptance"),
        ("applications.additional_documents", "Additional Documents"),
        ("applications.rv_ov_ref", "RV / OV / Ref"),
        ("applications.esign_nach_kyc", "eSign / NACH / KYC"),
        ("applications.final_evaluation", "Final Evaluation"),
        ("applications.send_for_disbursement", "Send For Disbursement"),
        ("applications.disbursed", "Disbursed"),
        ("applications.on_hold", "On Hold"),
        ("applications.rejected", "Rejected"),
    ]),
    ("insurance_management", "applications"): ("__module__", "page", [
        ("applications.fresh_lead", "Fresh Leads"),
        ("applications.policy_document", "Policy Document"),
        ("applications.policy_login", "Policy Login"),
        ("applications.payment", "Payment"),
        ("applications.policy_issued", "Policy Issued"),
        ("applications.re_eligible", "Re-Eligible"),
        ("applications.rejected", "Rejected"),
        ("applications.on_hold", "On Hold"),
        ("applications.settings", "Settings"),
    ]),
    ("insurance_management", "recruitment"): ("__module__", "page", [
        ("recruitment.fresh", "Fresh Leads"),
        ("recruitment.bop", "BOP"),
        ("recruitment.doc_collection", "Doc Collection"),
        ("recruitment.exam_fee_status", "Exam Fee Status"),
        ("recruitment.examination", "Examination"),
        ("recruitment.re_examination", "Re-Examination"),
        ("recruitment.agency_code", "Agency Code"),
        ("recruitment.rejected", "Rejected"),
    ]),
}


async def migrate(db) -> None:
    permissions = db["permissions"]
    role_permissions = db["role_permissions"]
    now = datetime.now(UTC)
    modules = await permissions.distinct("module", {"is_deleted": False})

    for module in modules:
        await permissions.update_one(
            {"module": module, "resource": "__module__", "is_deleted": False},
            {"$set": {"node_type": "module", "parent_resource": None, "label": module.replace("_", " ").title()},
             "$setOnInsert": {"actions": ACTIONS, "created_at": now, "updated_at": now, "is_deleted": False, "version": 1}},
            upsert=True,
        )
        await permissions.update_many(
            {"module": module, "resource": {"$ne": "__module__"}, "is_deleted": False, "parent_resource": {"$exists": False}},
            {"$set": {"parent_resource": "__module__", "node_type": "page", "updated_at": now}},
        )

    for (module, resource), (parent, node_type, children) in CHILDREN.items():
        await permissions.update_one(
            {"module": module, "resource": resource, "is_deleted": False},
            {"$set": {"parent_resource": parent, "node_type": node_type, "updated_at": now},
             "$addToSet": {"actions": {"$each": ACTIONS}}},
        )
        for child_resource, label in children:
            await permissions.update_one(
                {"module": module, "resource": child_resource, "is_deleted": False},
                {"$set": {"parent_resource": resource, "node_type": "tab", "label": label},
                 "$setOnInsert": {"actions": ACTIONS, "created_at": now, "updated_at": now, "is_deleted": False, "version": 1}},
                upsert=True,
            )

    # Advisors are independently overridable while legacy recruitment grants are copied
    # exactly once so the split cannot remove existing Advisor access.
    await permissions.update_one(
        {"module": "insurance_management", "resource": "advisors", "is_deleted": False},
        {"$set": {"parent_resource": "__module__", "node_type": "page", "label": "Advisors"},
         "$setOnInsert": {"actions": ACTIONS, "created_at": now, "updated_at": now, "is_deleted": False, "version": 1}},
        upsert=True,
    )

    # A module switch is added for every role/module already in use, with no default
    # actions. Existing exact grants remain the source of access until an Owner chooses
    # module defaults in the new UI.
    catalog = await permissions.find({"is_deleted": False}).to_list(length=100_000)
    by_id = {str(row["_id"]): row for row in catalog}
    roots = {row["module"]: row for row in catalog if row.get("resource") == "__module__"}
    grants = await role_permissions.find({"is_deleted": False}).to_list(length=100_000)
    recruitment = next(row for row in catalog if row["module"] == "insurance_management" and row["resource"] == "recruitment")
    advisors = next(row for row in catalog if row["module"] == "insurance_management" and row["resource"] == "advisors")
    applications = next(
        (
            row for row in catalog
            if row["module"] == "insurance_management" and row["resource"] == "applications"
        ),
        None,
    )
    for grant in grants:
        # Manual Insurance creation historically required Edit. Convert that existing
        # capability to the new explicit Create action without granting it to view-only
        # roles. Explicit denies, if the script is rerun after rollout, still win.
        if (
            applications is not None
            and grant["permission_id"] == str(applications["_id"])
            and "edit" in grant.get("granted_actions", [])
        ):
            await role_permissions.update_one(
                {"_id": grant["_id"]},
                {"$addToSet": {"granted_actions": "create"}, "$set": {"updated_at": now}},
            )

        if grant["permission_id"] != str(recruitment["_id"]):
            # applications:view was also the legacy read gate for Recruitment and
            # Advisors. Preserve it by adding only View to those new independent pages.
            if (
                applications is None
                or grant["permission_id"] != str(applications["_id"])
                or "view" not in grant.get("granted_actions", [])
            ):
                continue
            for target in (recruitment, advisors):
                await role_permissions.update_one(
                    {"role_id": grant["role_id"], "permission_id": str(target["_id"]), "is_deleted": False},
                    {"$addToSet": {"granted_actions": "view"},
                     "$setOnInsert": {"denied_actions": [], "module_enabled": None,
                                      "department_ids": grant.get("department_ids"),
                                      "branch_ids": grant.get("branch_ids"),
                                      "created_by": grant.get("created_by"), "created_at": now,
                                      "updated_at": now, "is_deleted": False, "version": 1}},
                    upsert=True,
                )
            continue
        await role_permissions.update_one(
            {"role_id": grant["role_id"], "permission_id": str(advisors["_id"]), "is_deleted": False},
            {"$setOnInsert": {**{k: v for k, v in grant.items() if k not in {"_id", "permission_id"}},
                              "permission_id": str(advisors["_id"]), "created_at": now, "updated_at": now}},
            upsert=True,
        )
    used = {(grant["role_id"], by_id.get(grant["permission_id"], {}).get("module")) for grant in grants}
    for role_id, module in used:
        if not module or module not in roots:
            continue
        root_id = str(roots[module]["_id"])
        await role_permissions.update_one(
            {"role_id": role_id, "permission_id": root_id, "is_deleted": False},
            {"$setOnInsert": {"granted_actions": [], "denied_actions": [], "module_enabled": True,
                              "department_ids": None, "branch_ids": None, "created_by": None,
                              "created_at": now, "updated_at": now, "is_deleted": False, "version": 1}},
            upsert=True,
        )

    print("Permission hierarchy catalog prepared. Existing effective grants were preserved.")


async def main() -> None:
    await migrate(get_database())


if __name__ == "__main__":
    asyncio.run(main())
