"""Retry persisted internal HR inbox notifications; never external delivery."""

from typing import Any

from app.config.database import get_database
from app.features.employee.hr_notifications import retry_delivery


async def retry_employee_hr_notifications(_ctx: dict[str, Any]) -> dict[str, int]:
    db = get_database()
    from app.features.employee.hr_leave import project_approved_leave

    async for employee in db.employees.find(
        {
            "is_deleted": False,
            "hr_leave_requests": {
                "$elemMatch": {"status": "approved", "attendance_projection_pending": True}
            },
        }
    ).limit(100):
        await project_approved_leave(db, employee)
    return await retry_delivery(db)
