"""Explicit Owner association, never identity conversion or credential replacement."""

from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError, OperationFailure

from app.core.exceptions import ConflictError, ForbiddenError
from app.features.auth.models import User
from app.features.employee.models import Employee
from app.shared.audit_log import AuditLog
from app.shared.customer_identity import mobile_match_pattern, normalize_mobile
from app.utils.datetime import utc_now


async def preview(db: Any, mobile: str, actor: User) -> dict[str, Any]:
    if actor.role != "owner":
        raise ForbiddenError("Owner identity review is required.")
    mobile = normalize_mobile(mobile)
    rows = (
        await db.users.find({"mobile": {"$regex": mobile_match_pattern(mobile)}})
        .limit(2)
        .to_list(2)
    )
    if not rows:
        return {"state": "new", "mobile": mobile}
    if len(rows) != 1:
        return {
            "state": "conflict",
            "message": "Conflicting historical identities require Owner review. No account was attached.",
        }
    user = rows[0]
    employee = await db.employees.find_one(
        {"user_id": str(user["_id"])}, {"employee_code": 1, "display_name": 1, "is_deleted": 1}
    )
    customer = await db.customers.find_one(
        {"user_id": str(user["_id"]), "is_deleted": False}, {"customer_code": 1, "full_name": 1}
    )
    partner = await db.referral_partners.find_one(
        {"user_id": str(user["_id"]), "is_deleted": False}, {"partner_code": 1, "full_name": 1}
    )
    eligible = (
        user.get("role") in {"customer", "referral_partner"}
        and user.get("is_mobile_verified")
        and user.get("status") == "active"
        and not user.get("is_deleted")
        and not employee
        and not user.get("employee_access")
    )
    return {
        "state": "employee" if employee else "existing",
        "user_id": str(user["_id"]),
        "version": user.get("version", 1),
        "account_type": user.get("role"),
        "mobile": mobile,
        "status": "deleted" if user.get("is_deleted") else user.get("status"),
        "customer_id": str(customer["_id"]) if customer else None,
        "customer_code": (customer or {}).get("customer_code"),
        "partner_id": str(partner["_id"]) if partner else None,
        "partner_code": (partner or {}).get("partner_code"),
        "employee_id": str(employee["_id"]) if employee else None,
        "employee_code": (employee or {}).get("employee_code"),
        "display_name": (employee or customer or partner or {}).get("display_name")
        or (customer or partner or {}).get("full_name"),
        "can_add_employee": bool(
            eligible and (customer if user.get("role") == "customer" else partner)
        ),
    }


async def resolve_existing(db: Any, payload: Any, owner: User) -> User | None:
    info = await preview(db, payload.mobile, owner)
    if info["state"] == "new":
        if payload.existing_user_id:
            raise ConflictError("Identity changed. Review the mobile number again.")
        return None
    if info["state"] == "employee":
        raise ConflictError(
            f"Employee {info.get('employee_code') or ''} already exists. Open the existing Employee profile."
        )
    if not info.get("can_add_employee"):
        raise ConflictError(
            "Existing identity cannot be attached safely. Review the existing account or correct the mobile number."
        )
    if (
        not payload.identity_confirmed
        or len(payload.identity_reason.strip()) < 5
        or payload.existing_user_id != info["user_id"]
        or payload.identity_version != info["version"]
    ):
        raise ConflictError(
            f"This mobile number is already registered as {info['account_type']}. Explicit Owner identity confirmation is required to add Employee access."
        )
    if not ObjectId.is_valid(info["user_id"]):
        raise ConflictError(
            "Existing identity storage requires Owner review; no account was attached."
        )
    row = await db.users.find_one({"_id": ObjectId(info["user_id"])})
    if not row:
        raise ConflictError(
            "Existing identity storage requires Owner review; no account was attached."
        )
    return User.model_validate(row)


async def commit_employee(
    db: Any, payload: Any, owner: User, new_user: User, existing: User | None, employee: Employee
) -> Employee:
    uid = ObjectId(employee.user_id)
    eid = ObjectId()
    doc = employee.model_dump(by_alias=True, exclude={"id"})
    doc.update(
        _id=eid,
        onboarding={
            "mode": payload.onboarding_mode,
            "status": "incomplete",
            "version": 0,
            "history": [],
        },
    )
    audit = AuditLog(
        event_type="employee_access_added" if existing else "employee_created",
        user_id=owner.require_id(),
        metadata={
            "employee_id": str(eid),
            "employee_code": employee.employee_code,
            "user_id": str(uid),
            "preserved_primary_role": existing.role if existing else None,
            "reason": payload.identity_reason if existing else None,
        },
    )
    try:
        async with await db.client.start_session() as session, session.start_transaction():
            if existing:
                result = await db.users.update_one(
                    {
                        "_id": uid,
                        "version": existing.version,
                        "role": existing.role,
                        "status": "active",
                        "is_mobile_verified": True,
                        "is_deleted": False,
                        "employee_access": None,
                    },
                    {
                        "$set": {
                            "employee_access": {
                                "enabled": payload.onboarding_mode != "owner_complete",
                                "password_hash": new_user.password_hash,
                                "must_change_password": True,
                                "granted_by": owner.require_id(),
                                "granted_at": utc_now(),
                            },
                            "updated_at": utc_now(),
                        },
                        "$inc": {"version": 1},
                    },
                    session=session,
                )
                if not result.modified_count:
                    raise ConflictError(
                        "Identity changed. Review again before adding Employee access."
                    )
            else:
                from app.features.auth.repository import UserRepository

                await UserRepository(db).require_available_mobile(new_user.mobile, session=session)
                await db.users.insert_one(
                    {**new_user.model_dump(by_alias=True, exclude={"id"}), "_id": uid},
                    session=session,
                )
            await db.employees.insert_one(doc, session=session)
            await db.audit_logs.insert_one(
                audit.model_dump(by_alias=True, exclude={"id"}), session=session
            )
    except DuplicateKeyError:
        raise ConflictError(
            "An account or Employee already exists. Refresh identity review; no duplicate was created."
        ) from None
    except OperationFailure as exc:
        if exc.code == 112 or exc.has_error_label("TransientTransactionError"):
            raise ConflictError("Concurrent identity change. Refresh and review again.") from None
        raise
    return Employee.model_validate(doc)
