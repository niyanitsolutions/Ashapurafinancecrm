import sys
from pathlib import Path

from bson import ObjectId

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.migrate_permission_hierarchy import migrate


async def test_permission_hierarchy_migration_is_idempotent_and_preserves_grants(mock_db):
    recruitment_id = ObjectId()
    applications_id = ObjectId()
    role_id = str(ObjectId())
    await mock_db["permissions"].insert_one({
        "_id": recruitment_id,
        "module": "insurance_management",
        "resource": "recruitment",
        "actions": ["view", "create", "edit"],
        "label": "Recruitment Leads",
        "is_deleted": False,
    })
    await mock_db["role_permissions"].insert_one({
        "role_id": role_id,
        "permission_id": str(recruitment_id),
        "granted_actions": ["view", "create"],
        "department_ids": None,
        "branch_ids": None,
        "is_deleted": False,
    })
    await mock_db["permissions"].insert_one({
        "_id": applications_id,
        "module": "insurance_management",
        "resource": "applications",
        "actions": ["view", "edit", "assign"],
        "label": "Insurance Cases",
        "is_deleted": False,
    })
    legacy_role_id = str(ObjectId())
    await mock_db["role_permissions"].insert_one({
        "role_id": legacy_role_id,
        "permission_id": str(applications_id),
        "granted_actions": ["view", "edit"],
        "department_ids": None,
        "branch_ids": None,
        "is_deleted": False,
    })

    await migrate(mock_db)
    await migrate(mock_db)

    roots = await mock_db["permissions"].count_documents({
        "module": "insurance_management", "resource": "__module__", "is_deleted": False,
    })
    fresh_tabs = await mock_db["permissions"].count_documents({
        "module": "insurance_management", "resource": "recruitment.fresh", "is_deleted": False,
    })
    advisors = await mock_db["permissions"].find_one({
        "module": "insurance_management", "resource": "advisors", "is_deleted": False,
    })
    assert roots == 1
    assert fresh_tabs == 1
    assert advisors is not None

    original = await mock_db["role_permissions"].find_one({
        "role_id": role_id, "permission_id": str(recruitment_id), "is_deleted": False,
    })
    advisor_grants = await mock_db["role_permissions"].find({
        "role_id": role_id, "permission_id": str(advisors["_id"]), "is_deleted": False,
    }).to_list(length=10)
    assert original["granted_actions"] == ["view", "create"]
    assert len(advisor_grants) == 1
    assert advisor_grants[0]["granted_actions"] == ["view", "create"]

    migrated_application = await mock_db["role_permissions"].find_one({
        "role_id": legacy_role_id, "permission_id": str(applications_id), "is_deleted": False,
    })
    legacy_advisor = await mock_db["role_permissions"].find_one({
        "role_id": legacy_role_id, "permission_id": str(advisors["_id"]), "is_deleted": False,
    })
    legacy_recruitment = await mock_db["role_permissions"].find_one({
        "role_id": legacy_role_id, "permission_id": str(recruitment_id), "is_deleted": False,
    })
    assert set(migrated_application["granted_actions"]) == {"view", "create", "edit"}
    assert legacy_advisor["granted_actions"] == ["view"]
    assert legacy_recruitment["granted_actions"] == ["view"]
