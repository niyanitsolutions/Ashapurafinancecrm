"""An explicitly authenticated session has one role; memberships never union grants."""

from typing import Any

from app.core.exceptions import UnauthorizedError
from app.features.auth.models import User
from app.features.employee.constants import EmploymentStatus


async def effective_user(db: Any, user: User, role: str | None) -> User:
    if not role or role == user.role:
        return user
    access = user.employee_access
    if (
        role != "employee"
        or user.role not in {"customer", "referral_partner"}
        or not access
        or not access.get("enabled")
    ):
        raise UnauthorizedError("Employee access is unavailable. Contact the Owner.")
    employee = await db.employees.find_one(
        {
            "user_id": user.require_id(),
            "is_deleted": False,
            "status": {"$nin": list(EmploymentStatus.LOGIN_BLOCKED)},
        },
        {"_id": 1},
    )
    if not employee:
        raise UnauthorizedError("Employee access is unavailable. Contact the Owner.")
    return user.model_copy(
        update={
            "role": "employee",
            "password_hash": access.get("password_hash"),
            "must_change_password": bool(access.get("must_change_password", True)),
        }
    )
