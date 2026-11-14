"""HR operations share employee identity and existing owner/self dependencies."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.response import ApiResponse
from app.features.employee.dependencies import CurrentUserDep, get_employee_service
from app.features.employee.hr_profile import HrProfiles, ProfileDecision, ProfileInput
from app.features.employee.service import EmployeeService

router = APIRouter(prefix="/hr", tags=["employee-hr"])
Service = Annotated[EmployeeService, Depends(get_employee_service)]


class Version(BaseModel):
    version: int = Field(ge=0)


@router.get("/{employee_id}/profile")
async def profile(
    employee_id: str, service: Service, actor: CurrentUserDep
) -> ApiResponse[dict[str, Any]]:
    hr = HrProfiles(service)
    return ApiResponse.ok(hr.public(await hr.employee(employee_id, actor)))


@router.put("/{employee_id}/profile")
async def save_profile(
    employee_id: str, payload: ProfileInput, service: Service, actor: CurrentUserDep
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse.ok(await HrProfiles(service).save(employee_id, payload, actor))


@router.post("/{employee_id}/profile/submit")
async def submit_profile(
    employee_id: str, payload: Version, service: Service, actor: CurrentUserDep
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse.ok(await HrProfiles(service).submit(employee_id, payload.version, actor))


@router.post("/{employee_id}/profile/review")
async def review_profile(
    employee_id: str, payload: ProfileDecision, service: Service, actor: CurrentUserDep
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse.ok(await HrProfiles(service).decide(employee_id, payload, actor))


from app.features.employee.hr_documents import (
    Category,
    ConfirmInput,
    DocumentDecision,
    HrDocuments,
    UploadInput,
)


@router.get("/{employee_id}/documents")
async def documents(
    employee_id: str, service: Service, actor: CurrentUserDep
) -> ApiResponse[dict[str, Any]]:
    hr = HrProfiles(service)
    return ApiResponse.ok(HrDocuments.public(await hr.employee(employee_id, actor)))


@router.post("/{employee_id}/documents/upload")
async def upload_document(
    employee_id: str, payload: UploadInput, service: Service, actor: CurrentUserDep
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse.ok(await HrDocuments(service).upload(employee_id, payload, actor))


@router.post("/{employee_id}/documents/confirm")
async def confirm_document(
    employee_id: str, payload: ConfirmInput, service: Service, actor: CurrentUserDep
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse.ok(await HrDocuments(service).confirm(employee_id, payload, actor))


@router.post("/{employee_id}/documents/{category}/review")
async def review_document(
    employee_id: str,
    category: Category,
    payload: DocumentDecision,
    service: Service,
    actor: CurrentUserDep,
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse.ok(await HrDocuments(service).review(employee_id, category, payload, actor))


@router.get("/{employee_id}/documents/{category}/{version}/{part}/download")
async def download_document(
    employee_id: str,
    category: Category,
    version: int,
    part: str,
    service: Service,
    actor: CurrentUserDep,
) -> ApiResponse[dict[str, str]]:
    return ApiResponse.ok(
        {"url": await HrDocuments(service).download(employee_id, category, version, part, actor)}
    )


from app.features.employee.hr_edits import EditDecision, HrEdits


@router.get("/{employee_id}/edit-requests")
async def edit_requests(
    employee_id: str, service: Service, actor: CurrentUserDep, page: int = 1, page_size: int = 20
) -> ApiResponse[dict[str, Any]]:
    from app.core.exceptions import ValidationError

    if page < 1 or not 1 <= page_size <= 200:
        raise ValidationError("Use valid pagination, maximum 200 records.")
    employee = await HrProfiles(service).employee(employee_id, actor)
    rows = list(reversed(employee.get("hr_edit_requests", [])))
    return ApiResponse.ok(
        {"items": rows[(page - 1) * page_size : page * page_size], "total": len(rows)}
    )


@router.post("/{employee_id}/edit-requests")
async def request_edit(
    employee_id: str, payload: ProfileInput, service: Service, actor: CurrentUserDep
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse.ok(await HrEdits(service).request(employee_id, payload, actor))


@router.post("/{employee_id}/edit-requests/{request_id}/review")
async def review_edit(
    employee_id: str,
    request_id: str,
    payload: EditDecision,
    service: Service,
    actor: CurrentUserDep,
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse.ok(await HrEdits(service).review(employee_id, request_id, payload, actor))


from app.features.employee.hr_edits import EditDecision as LeaveDecision
from app.features.employee.hr_leave import HrLeave, LeaveInput, LeaveTypeInput


@router.get("/leave-types")
async def leave_types(service: Service, actor: CurrentUserDep) -> ApiResponse[Any]:
    return ApiResponse.ok(await HrLeave(service).types(actor))


@router.post("/leave-types")
async def create_leave_type(
    payload: LeaveTypeInput, service: Service, actor: CurrentUserDep
) -> ApiResponse[Any]:
    return ApiResponse.ok(await HrLeave(service).save_type(payload, actor))


@router.put("/leave-types/{option_id}")
async def edit_leave_type(
    option_id: str, payload: LeaveTypeInput, service: Service, actor: CurrentUserDep
) -> ApiResponse[Any]:
    return ApiResponse.ok(await HrLeave(service).save_type(payload, actor, option_id))


@router.get("/{employee_id}/leaves")
async def leaves(
    employee_id: str,
    service: Service,
    actor: CurrentUserDep,
    year: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> ApiResponse[dict[str, Any]]:
    from app.core.exceptions import ValidationError
    from app.utils.datetime import to_ist, utc_now

    if page < 1 or not 1 <= page_size <= 200:
        raise ValidationError("Use valid pagination, maximum 200 records.")
    hr = HrLeave(service)
    employee = await hr.employee(employee_id, actor)
    selected = year or to_ist(utc_now()).year
    rows = [
        row
        for row in reversed(employee.get("hr_leave_requests", []))
        if row["start_date"][:4] == str(selected)
    ]
    policies = await hr.types(actor)
    balances = []
    for policy in policies:
        limit = policy.get("annual_calendar_day_limit")
        used = sum(
            row["calendar_days"]
            for row in rows
            if row["leave_type_id"] == policy["id"] and row["status"] in {"pending", "approved"}
        )
        balances.append(
            {
                "leave_type_id": policy["id"],
                "leave_type_name": policy["name"],
                "calendar_day_limit": limit,
                "reserved_days": used,
                "available_days": None if limit is None else max(0, limit - used),
                "year": selected,
            }
        )
    return ApiResponse.ok(
        {
            "items": rows[(page - 1) * page_size : page * page_size],
            "total": len(rows),
            "balances": balances,
        }
    )


@router.post("/{employee_id}/leaves")
async def apply_leave(
    employee_id: str, payload: LeaveInput, service: Service, actor: CurrentUserDep
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse.ok(await HrLeave(service).apply(employee_id, payload, actor))


@router.post("/{employee_id}/leaves/{request_id}/review")
async def review_leave(
    employee_id: str,
    request_id: str,
    payload: LeaveDecision,
    service: Service,
    actor: CurrentUserDep,
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse.ok(
        await HrLeave(service).decide_leave(
            employee_id, request_id, payload.decision, payload.reason, actor
        )
    )


@router.post("/{employee_id}/leaves/{request_id}/cancel")
async def cancel_leave(
    employee_id: str, request_id: str, service: Service, actor: CurrentUserDep
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse.ok(
        await HrLeave(service).decide_leave(
            employee_id, request_id, "cancelled", "Cancelled pending request", actor
        )
    )


from datetime import date

from fastapi import Query, Response

from app.features.employee.hr_reports import AttendancePolicy, HrReports


@router.get("/settings")
async def hr_settings(service: Service, actor: CurrentUserDep) -> ApiResponse[dict[str, Any]]:
    return ApiResponse.ok(await HrReports(service).policy(actor))


@router.put("/settings")
async def save_hr_settings(
    payload: AttendancePolicy, service: Service, actor: CurrentUserDep
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse.ok(await HrReports(service).save_policy(payload, actor))


@router.get("/reports/attendance")
async def attendance_report(
    service: Service,
    actor: CurrentUserDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    employee: str = "",
    employee_name: str = "",
    month: str | None = Query(None, pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$"),
    date_from: date | None = None,
    date_to: date | None = None,
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse.ok(
        await HrReports(service).attendance(
            actor,
            page=page,
            page_size=page_size,
            employee=employee,
            employee_name=employee_name,
            month=month,
            date_from=date_from,
            date_to=date_to,
        )
    )


@router.get("/reports/{section}")
async def hr_report(
    section: str,
    service: Service,
    actor: CurrentUserDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: str = Query("", max_length=200),
    status: str = "",
    employee_id: str = "",
    date_from: date | None = None,
    date_to: date | None = None,
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse.ok(
        await HrReports(service).report(
            section,
            actor,
            page=page,
            page_size=page_size,
            search=search,
            status=status,
            employee_id=employee_id,
            date_from=date_from,
            date_to=date_to,
        )
    )


@router.get("/reports/{section}/export")
async def export_hr_report(
    section: str,
    service: Service,
    actor: CurrentUserDep,
    search: str = Query("", max_length=200),
    status: str = "",
    employee_id: str = "",
    month: str | None = Query(None, pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$"),
    date_from: date | None = None,
    date_to: date | None = None,
) -> Response:
    import csv
    import io

    from app.core.exceptions import ForbiddenError, ValidationError
    from app.features.access_control.permission_engine import PermissionEngine
    from app.shared.audit_log import write_audit_log

    if not await PermissionEngine(service._db).has_permission(
        actor, module="employee_hr", resource="reports", action="export"
    ):
        raise ForbiddenError("Employee report export permission is required.")
    hr = HrReports(service)
    rows: list[dict[str, Any]] = []
    for page in range(1, 27):
        result = (
            await hr.attendance(
                actor,
                page=page,
                page_size=200,
                employee=employee_id,
                employee_name=search,
                month=month,
                date_from=date_from,
                date_to=date_to,
            )
            if section == "attendance"
            else await hr.report(
                section,
                actor,
                page=page,
                page_size=200,
                search=search,
                status=status,
                employee_id=employee_id,
                date_from=date_from,
                date_to=date_to,
            )
        )
        if result["total"] > 5000:
            raise ValidationError("Narrow the report filters before exporting more than 5000 rows.")
        if section == "attendance":
            rows.extend(
                {
                    key: row.get(key)
                    for key in (
                        "date",
                        "employee_id",
                        "employee_name",
                        "login_at",
                        "observed_logout_at",
                        "observed_session_seconds",
                        "needs_reconciliation",
                        "has_open_session",
                    )
                }
                | {
                    "approved_leave": ", ".join(
                        item["leave_type_name"] for item in row["approved_leave"]
                    )
                }
                for row in result["items"]
            )
        else:
            rows.extend(result["items"])
        if len(rows) >= result["total"]:
            break
    buffer = io.StringIO()
    columns = list(rows[0]) if rows else ["employee_id", "employee_name", "status"]
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()

    from app.features.employee.hr_reports import safe_csv_cell

    for row in rows:
        writer.writerow({key: safe_csv_cell(value) for key, value in row.items()})
    await write_audit_log(
        service._db,
        event_type="employee_report_exported",
        user_id=actor.require_id(),
        metadata={"section": section, "rows": len(rows)},
    )
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="employee-report.csv"'},
    )


class AccessReviewInput(Version):
    organization: dict[str, str]
    role_ids: list[str] = Field(default_factory=list, max_length=500)


@router.post("/{employee_id}/access-review")
async def review_employee_access(
    employee_id: str, payload: AccessReviewInput, service: Service, actor: CurrentUserDep
) -> ApiResponse[dict[str, Any]]:
    from app.core.exceptions import ConflictError
    from app.shared.audit_log import write_audit_log
    from app.utils.datetime import utc_now

    hr = HrProfiles(service)
    employee = await hr.employee(employee_id, actor, review=True)
    roles = sorted(
        [
            row["role_id"]
            async for row in service._db.employee_roles.find(
                {"employee_id": str(employee["_id"]), "is_deleted": False}
            )
        ]
    )
    organization = {key: employee[key] for key in ("department_id", "designation_id", "branch_id")}
    if sorted(payload.role_ids) != roles or payload.organization != organization:
        raise ConflictError(
            "The organization or assigned roles changed. Refresh the access review first."
        )

    review = {
        "role_ids": roles,
        "organization": {
            key: employee[key] for key in ("department_id", "designation_id", "branch_id")
        },
        "reviewed_by": actor.require_id(),
        "reviewed_at": utc_now(),
    }
    changed = await service._db.employees.update_one(
        {"_id": employee["_id"], "onboarding.version": payload.version, "is_deleted": False},
        {"$set": {"onboarding.access_review": review}, "$inc": {"onboarding.version": 1}},
    )
    if not changed.modified_count:
        raise ConflictError("Employee details changed. Refresh before confirming access.")
    await write_audit_log(
        service._db,
        event_type="employee_access_reviewed",
        user_id=actor.require_id(),
        metadata={"employee_id": str(employee["_id"]), "role_ids": roles},
    )
    return ApiResponse.ok(hr.public(await hr.employee(employee_id, actor)))
