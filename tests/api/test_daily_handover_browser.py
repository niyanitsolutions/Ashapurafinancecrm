# ruff: noqa: F811
"""Owner/Employee journeys against an owned local API and disposable real database."""

import asyncio
import json
import os
from pathlib import Path

import pytest
import uvicorn
from app.config.database import get_database
from app.features.workflow_engine.models import ApplicationWorkflow, LoanCaseDetails
from app.security.password import hash_password
from app.utils.datetime import utc_now
from bson import ObjectId
from test_case_status_control import _seed_workflow_definitions
from test_daily_handover_enhancement import environment  # noqa: F401
from test_pin_mongo_integration import pin_mongo  # noqa: F401
from test_unified_operations import insert


@pytest.mark.skipif(
    os.environ.get("AFS_HANDOVER_BROWSER") != "1", reason="Opt-in local browser"
)
async def test_daily_movement_transfer_disbursement_topup_responsive(
    environment, client
):
    db, owner, employees, customer, original = environment
    await db.users.update_one(
        {"_id": ObjectId(owner.id)},
        {"$set": {"password_hash": hash_password("InitialPass1!")}},
    )
    await _seed_workflow_definitions(db)
    from app.features.daily_operations.bank_options import BankOptions
    from app.features.daily_operations.service import DailyOperationsService

    await BankOptions(DailyOperationsService(db)).change(
        owner, name="Synthetic Browser Bank"
    )
    from app.features.access_control.models import Permission, RolePermission

    stage = Permission(
        module="loan_management",
        resource="applications.disbursed",
        parent_resource="applications",
        node_type="tab",
        actions=["view", "edit", "assign"],
    )
    stage_id = await insert(db, "permissions", stage)
    for employee, _user in employees:
        role = await db.employee_roles.find_one({"employee_id": employee.id})
        await insert(
            db,
            "role_permissions",
            RolePermission(
                role_id=role["role_id"],
                permission_id=stage_id,
                granted_actions=["view", "edit", "assign"],
            ),
        )
    fixture = {
        "owner_mobile": owner.mobile,
        "employees": [
            {"id": e.id, "mobile": u.mobile, "name": e.display_name}
            for e, u in employees
        ],
        "applications": {},
    }
    original_row = await db.applications.find_one({"_id": ObjectId(original.id)})
    # Existing Application-list reads ensure a case for every submitted Application.
    # Seed that pre-existing lifecycle explicitly before measuring duplicate prevention.
    from app.features.loan_management.service import LoanCaseService

    await LoanCaseService(db).ensure_case_for_application(original.id)
    baseline_case_ids = {
        row["_id"] async for row in db.application_workflows.find({}, {"_id": 1})
    }
    for width in [390, 768, 1366]:
        row = {
            **original_row,
            "_id": ObjectId(),
            "application_code": f"SYN-BROWSER-{width}",
        }
        await db.applications.insert_one(row)
        case = ApplicationWorkflow(
            case_code=f"SYN-LOAN-{width}",
            case_type="loan",
            application_id=str(row["_id"]),
            customer_id=customer.id,
            product_id=original.product_id,
            product_category="loan",
            assigned_to=employees[0][0].id,
            current_status="send_for_disbursement",
            loan_details=LoanCaseDetails(offered_amount=100000),
            moved_to_loan_management_at=utc_now(),
        )
        case.id = await insert(db, "application_workflows", case)
        fixture["applications"][str(width)] = {
            "id": str(row["_id"]),
            "code": row["application_code"],
            "case_id": case.id,
            "case_code": case.case_code,
        }
        await db.application_documents.insert_one(
            {
                "application_id": str(row["_id"]),
                "is_current": True,
                "verification_status": "pending",
                "document_type_id": str(ObjectId()),
                "document_status": "not_available",
                "is_deleted": False,
                "version": 1,
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
    app = client._transport.app
    app.dependency_overrides[get_database] = lambda: db
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=18774, log_level="error", lifespan="off"
        )
    )
    task = asyncio.create_task(server.serve())
    process = None
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.05)
        assert server.started
        root = Path(__file__).resolve().parents[2]
        process = await asyncio.create_subprocess_exec(
            str(root / "frontend/node_modules/.cache/voice-node22/node.exe"),
            str(root / "scripts/daily-handover-ui-check.mjs"),
            cwd=root,
            env={**os.environ, "AFS_HANDOVER_FIXTURE": json.dumps(fixture)},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await asyncio.wait_for(process.communicate(), 420)
        assert process.returncode == 0, output.decode(errors="replace")
        for data in fixture["applications"].values():
            current = await db.applications.find_one({"_id": ObjectId(data["id"])})
            assert (
                current["form_data"] == original_row["form_data"]
                and current["status"] == original_row["status"]
            )
            assert (
                current["customer_id"] == customer.id
                and current["assigned_to"] == employees[1][0].id
            )
            follow = await db.daily_follow_ups.find_one({"application_id": data["id"]})
            assert follow["status"] == "DISBURSE" and len(follow["history"]) >= 2
            assert await db.audit_logs.count_documents(
                {
                    "event_type": "crm_record_transferred",
                    "metadata.collection": "daily_follow_ups",
                    "metadata.record_id": str(follow["_id"]),
                    "metadata.to_employee_id": employees[1][0].id,
                }
            ) == 1
            case = await db.application_workflows.find_one(
                {"_id": ObjectId(data["case_id"])}
            )
            assert (
                case["loan_details"]["disbursed_amount"] == 90000
                and case["loan_details"]["top_up_period"] == "3_months"
            )
            assert (
                await db.application_documents.count_documents(
                    {"application_id": data["id"], "verification_status": "pending"}
                )
                == 1
            )
        assert await db.applications.count_documents({}) == 4
        expected_case_ids = baseline_case_ids | {
            ObjectId(data["case_id"]) for data in fixture["applications"].values()
        }
        assert {
            row["_id"] async for row in db.application_workflows.find({}, {"_id": 1})
        } == expected_case_ids
        assert await db.customers.count_documents({}) == 1
        print(output.decode(errors="replace"))
    finally:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        server.should_exit = True
        await task
