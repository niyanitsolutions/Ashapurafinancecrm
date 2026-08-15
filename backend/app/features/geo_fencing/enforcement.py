"""Real geo-fencing enforcement — the piece `docs/KNOWN_LIMITATIONS.md` previously called
out as missing ("GeoException has no enforcement engine to except from"). Backend is
authoritative: the caller supplies coordinates, this function is the only thing that
decides whether the activity is allowed, and every outcome is audited. Never raises for an
activity with zero configured Geo Fences — geo-fencing is opt-in per activity (spec's own
rule), never a blanket restriction.

`GeoActivity.LEAD_CREATION`, `GeoActivity.DOCUMENT_COLLECTION`, and `GeoActivity.LOGIN`
are the only activities ever actually called with this function today (see router call
sites in leads/loan_management/insurance_management, and `AuthService.login`) —
`customer_visit`/`loan_application`/`insurance_application` are valid, storable
`allowed_activities` values with no real employee-initiated single action in this
codebase to attach enforcement to; see docs/GEO_FENCING.md.
"""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import ForbiddenError
from app.features.access_control.repository import GeoExceptionRepository
from app.features.auth.models import User
from app.features.employee.repository import EmployeeRepository
from app.features.geo_fencing.constants import AuditEvent
from app.features.geo_fencing.geomath import haversine_distance_meters
from app.features.geo_fencing.repository import GeoFenceRepository
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now, within_daily_window

_OWNER_ROLE = "owner"


async def enforce_geo_fence(
    db: AsyncIOMotorDatabase[Any], *, actor: User, activity: str, latitude: float | None, longitude: float | None
) -> None:
    if actor.role == _OWNER_ROLE:
        return  # Owner is a superuser everywhere else in this codebase; same convention here.

    employee = await EmployeeRepository(db).find_by_user_id(actor.require_id())
    if employee is None:
        # Unreachable in practice: require_permission already 403s a non-Owner caller with
        # no Employee record before this function is ever called. Defensive no-op rather
        # than a confusing 500 if that invariant is ever violated.
        return
    employee_id = employee.require_id()

    fences = await GeoFenceRepository(db).find_active_for_activity(activity)
    if not fences:
        return  # nothing configured for this activity — proceeds exactly as before this feature existed

    if latitude is None or longitude is None:
        await write_audit_log(
            db, event_type=AuditEvent.CHECK_DENIED, user_id=actor.require_id(),
            metadata={"employee_id": employee_id, "activity": activity, "reason": "missing_coordinates"},
        )
        raise ForbiddenError("Location is required for this action.")

    now = utc_now()
    exceptions = await GeoExceptionRepository(db).find_active_for_employee(employee_id, activity=activity)
    for exception in exceptions:
        if within_daily_window(exception.start_date, exception.end_date, exception.start_time, exception.end_time, now):
            await write_audit_log(
                db, event_type=AuditEvent.CHECK_ALLOWED, user_id=actor.require_id(),
                metadata={"employee_id": employee_id, "activity": activity, "via": "geo_exception", "geo_exception_id": exception.require_id()},
            )
            return

    for fence in fences:
        distance_meters = haversine_distance_meters(latitude, longitude, fence.latitude, fence.longitude)
        if distance_meters <= fence.radius_meters:
            await write_audit_log(
                db, event_type=AuditEvent.CHECK_ALLOWED, user_id=actor.require_id(),
                metadata={"employee_id": employee_id, "activity": activity, "via": "geo_fence", "geo_fence_id": fence.require_id()},
            )
            return

    await write_audit_log(
        db, event_type=AuditEvent.CHECK_DENIED, user_id=actor.require_id(),
        metadata={"employee_id": employee_id, "activity": activity, "reason": "outside_all_fences", "fences_checked": len(fences)},
    )
    raise ForbiddenError("You're outside the permitted work area for this action.")
