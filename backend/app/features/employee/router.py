from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response

from app.core.pagination import PageParams, page_params
from app.core.response import ApiResponse, ResponseMeta
from app.features.auth.models import Session
from app.features.employee import mappers
from app.features.employee.dependencies import CurrentUserDep, get_employee_service, require_owner
from app.features.employee.schemas import (
    ActivitySummaryResponse,
    BranchCreateRequest,
    BranchResponse,
    ConfirmDocumentRequest,
    ConfirmPhotoRequest,
    CreateEmployeeRequest,
    DocumentUploadUrlRequest,
    DocumentUploadUrlResponse,
    EmployeeActivityEntry,
    EmployeeDetailResponse,
    EmployeeDocumentOverviewItem,
    EmployeeDocumentResponse,
    EmployeeListItem,
    LoginHistoryEntry,
    MasterDataCreateRequest,
    MasterDataResponse,
    PhotoUploadUrlResponse,
    SelfUpdateEmployeeRequest,
    SessionSummary,
    UpdateEmployeeRequest,
)
from app.features.employee.service import EmployeeService

router = APIRouter(prefix="/employees", tags=["employees"])
master_data_router = APIRouter(tags=["master-data"])

EmployeeServiceDep = Annotated[EmployeeService, Depends(get_employee_service)]
PageParamsDep = Annotated[PageParams, Depends(page_params)]

# ---------------------------------------------------------------------- self-service ("me")
# Declared before "/{employee_id}" routes so "me" isn't swallowed as a path param.


@router.get("/me")
async def get_own_profile(service: EmployeeServiceDep, current_user: CurrentUserDep) -> ApiResponse[EmployeeDetailResponse]:
    employee = await service.get_own_employee(current_user)
    names = await service.resolve_master_data_names(employee)
    return ApiResponse[EmployeeDetailResponse].ok(mappers.to_detail(employee, *names))


@router.patch("/me")
async def update_own_profile(
    payload: SelfUpdateEmployeeRequest, service: EmployeeServiceDep, current_user: CurrentUserDep
) -> ApiResponse[EmployeeDetailResponse]:
    employee = await service.get_own_employee(current_user)
    updated = await service.self_update_employee(employee.require_id(), payload, current_user)
    names = await service.resolve_master_data_names(updated)
    return ApiResponse[EmployeeDetailResponse].ok(mappers.to_detail(updated, *names))


@router.post("/me/photo/upload-url")
async def get_own_photo_upload_url(
    service: EmployeeServiceDep, current_user: CurrentUserDep
) -> ApiResponse[PhotoUploadUrlResponse]:
    employee = await service.get_own_employee(current_user)
    url, s3_key = await service.get_photo_upload_url(employee.require_id(), current_user)
    return ApiResponse[PhotoUploadUrlResponse].ok(PhotoUploadUrlResponse(upload_url=url, s3_key=s3_key))


@router.patch("/me/photo")
async def confirm_own_photo(
    payload: ConfirmPhotoRequest, service: EmployeeServiceDep, current_user: CurrentUserDep
) -> ApiResponse[EmployeeDetailResponse]:
    employee = await service.get_own_employee(current_user)
    updated = await service.confirm_photo(employee.require_id(), payload.s3_key, current_user)
    names = await service.resolve_master_data_names(updated)
    return ApiResponse[EmployeeDetailResponse].ok(mappers.to_detail(updated, *names))


@router.get("/me/sessions")
async def get_own_sessions(service: EmployeeServiceDep, current_user: CurrentUserDep) -> ApiResponse[list[SessionSummary]]:
    employee = await service.get_own_employee(current_user)
    sessions = await service.list_employee_sessions(employee.require_id(), current_user)
    return ApiResponse[list[SessionSummary]].ok([_session_summary(s) for s in sessions])


@router.get("/me/login-history")
async def get_own_login_history(
    service: EmployeeServiceDep, current_user: CurrentUserDep
) -> ApiResponse[list[LoginHistoryEntry]]:
    employee = await service.get_own_employee(current_user)
    entries = await service.list_employee_login_history(employee.require_id(), current_user)
    return ApiResponse[list[LoginHistoryEntry]].ok([_login_history_entry(e) for e in entries])


# ---------------------------------------------------------------------- owner: list / export / create


@router.get("", dependencies=[Depends(require_owner)])
async def list_employees(
    service: EmployeeServiceDep,
    page: PageParamsDep,
    department_id: str | None = None,
    designation_id: str | None = None,
    branch_id: str | None = None,
    status: str | None = None,
) -> ApiResponse[list[EmployeeListItem]]:
    employees, total = await service.list_employees(
        search=page.search, department_id=department_id, designation_id=designation_id,
        branch_id=branch_id, status=status, skip=page.skip, limit=page.page_size, sort=page.sort,
    )
    dept_map, desig_map, branch_map = await service.get_master_data_maps(employees)
    items = [
        mappers.to_list_item(e, dept_map.get(e.department_id, ""), desig_map.get(e.designation_id, ""), branch_map.get(e.branch_id, ""))
        for e in employees
    ]
    return ApiResponse[list[EmployeeListItem]].ok(items, meta=ResponseMeta(pagination=page.build_meta(total)))


@router.get("/export", dependencies=[Depends(require_owner)])
async def export_employees(service: EmployeeServiceDep) -> Response:
    csv_content = await service.export_employees_csv()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=employees.csv"},
    )


@router.get("/documents", dependencies=[Depends(require_owner)])
async def list_all_employee_documents(
    service: EmployeeServiceDep, page: PageParamsDep, employee_id: str | None = None, document_type: str | None = None,
) -> ApiResponse[list[EmployeeDocumentOverviewItem]]:
    documents, name_map, total = await service.list_all_documents(
        employee_id=employee_id, document_type=document_type, skip=page.skip, limit=page.page_size, sort=page.sort or [("created_at", -1)],
    )
    items = [
        EmployeeDocumentOverviewItem(
            id=d.require_id(), employee_id=d.employee_id, employee_name=name_map.get(d.employee_id, ""),
            document_type=d.document_type, file_name=d.file_name, s3_key=d.s3_key, content_type=d.content_type, created_at=d.created_at,
        )
        for d in documents
    ]
    return ApiResponse[list[EmployeeDocumentOverviewItem]].ok(items, meta=ResponseMeta(pagination=page.build_meta(total)))


@router.get("/activity", dependencies=[Depends(require_owner)])
async def list_all_employee_activity(
    service: EmployeeServiceDep, page: PageParamsDep, employee_id: str | None = None, event_type: str | None = None,
    # Business (IST) calendar dates, as picked by the Owner in the date-range filter —
    # see EmployeeService.list_activity, which converts them to UTC instant bounds via
    # the shared app.utils.datetime.ist_date_range_to_utc_bounds (same helper the
    # reporting module's own date-range filters use).
    date_from: date | None = None, date_to: date | None = None,
) -> ApiResponse[list[EmployeeActivityEntry]]:
    entries, name_map, total = await service.list_activity(
        employee_id=employee_id, event_type=event_type, date_from=date_from, date_to=date_to, skip=page.skip, limit=page.page_size,
    )
    items = []
    for e in entries:
        entry_employee_id: str | None = e.get("_employee_id")
        items.append(
            EmployeeActivityEntry(
                event_type=e["event_type"], employee_id=entry_employee_id,
                employee_name=name_map.get(entry_employee_id) if entry_employee_id else None,
                ip_address=e.get("ip_address"), user_agent=e.get("user_agent"), metadata=e.get("metadata"), created_at=e["created_at"],
            )
        )
    return ApiResponse[list[EmployeeActivityEntry]].ok(items, meta=ResponseMeta(pagination=page.build_meta(total)))


@router.post("", dependencies=[Depends(require_owner)])
async def create_employee(
    payload: CreateEmployeeRequest, service: EmployeeServiceDep, current_user: CurrentUserDep
) -> ApiResponse[EmployeeDetailResponse]:
    employee = await service.create_employee(payload, current_user)
    names = await service.resolve_master_data_names(employee)
    return ApiResponse[EmployeeDetailResponse].ok(mappers.to_detail(employee, *names))


# ---------------------------------------------------------------------- owner: single-employee actions


@router.patch("/{employee_id}", dependencies=[Depends(require_owner)])
async def update_employee(
    employee_id: str, payload: UpdateEmployeeRequest, service: EmployeeServiceDep, current_user: CurrentUserDep
) -> ApiResponse[EmployeeDetailResponse]:
    employee = await service.update_employee(employee_id, payload, current_user)
    names = await service.resolve_master_data_names(employee)
    return ApiResponse[EmployeeDetailResponse].ok(mappers.to_detail(employee, *names))


@router.patch("/{employee_id}/activate", dependencies=[Depends(require_owner)])
async def activate_employee(employee_id: str, service: EmployeeServiceDep, current_user: CurrentUserDep) -> ApiResponse[EmployeeDetailResponse]:
    employee = await service.activate_employee(employee_id, current_user)
    names = await service.resolve_master_data_names(employee)
    return ApiResponse[EmployeeDetailResponse].ok(mappers.to_detail(employee, *names))


@router.patch("/{employee_id}/deactivate", dependencies=[Depends(require_owner)])
async def deactivate_employee(employee_id: str, service: EmployeeServiceDep, current_user: CurrentUserDep) -> ApiResponse[EmployeeDetailResponse]:
    employee = await service.deactivate_employee(employee_id, current_user)
    names = await service.resolve_master_data_names(employee)
    return ApiResponse[EmployeeDetailResponse].ok(mappers.to_detail(employee, *names))


@router.post("/{employee_id}/reset-password", dependencies=[Depends(require_owner)])
async def reset_employee_password(employee_id: str, service: EmployeeServiceDep, current_user: CurrentUserDep) -> ApiResponse[None]:
    await service.reset_employee_password(employee_id, current_user)
    return ApiResponse[None].ok()


@router.post("/{employee_id}/force-logout", dependencies=[Depends(require_owner)])
async def force_logout_employee(employee_id: str, service: EmployeeServiceDep, current_user: CurrentUserDep) -> ApiResponse[dict[str, int]]:
    count = await service.force_logout_employee(employee_id, current_user)
    return ApiResponse[dict[str, int]].ok({"sessions_revoked": count})


# ---------------------------------------------------------------------- view (owner: any: employee: self only, service-enforced)


@router.get("/{employee_id}")
async def get_employee(employee_id: str, service: EmployeeServiceDep, current_user: CurrentUserDep) -> ApiResponse[EmployeeDetailResponse]:
    employee = await service.get_employee(employee_id, current_user)
    names = await service.resolve_master_data_names(employee)
    return ApiResponse[EmployeeDetailResponse].ok(mappers.to_detail(employee, *names))


@router.get("/{employee_id}/sessions")
async def get_employee_sessions(employee_id: str, service: EmployeeServiceDep, current_user: CurrentUserDep) -> ApiResponse[list[SessionSummary]]:
    sessions = await service.list_employee_sessions(employee_id, current_user)
    return ApiResponse[list[SessionSummary]].ok([_session_summary(s) for s in sessions])


@router.get("/{employee_id}/login-history")
async def get_employee_login_history(
    employee_id: str, service: EmployeeServiceDep, current_user: CurrentUserDep
) -> ApiResponse[list[LoginHistoryEntry]]:
    entries = await service.list_employee_login_history(employee_id, current_user)
    return ApiResponse[list[LoginHistoryEntry]].ok([_login_history_entry(e) for e in entries])


@router.get("/{employee_id}/activity-summary")
async def get_employee_activity_summary(
    employee_id: str, service: EmployeeServiceDep, current_user: CurrentUserDep
) -> ApiResponse[ActivitySummaryResponse]:
    summary = await service.get_activity_summary(employee_id, current_user)
    return ApiResponse[ActivitySummaryResponse].ok(ActivitySummaryResponse(**summary))


# ---------------------------------------------------------------------- documents (owner-only, no frontend page yet)


@router.post("/{employee_id}/documents/upload-url", dependencies=[Depends(require_owner)])
async def get_document_upload_url(
    employee_id: str, payload: DocumentUploadUrlRequest, service: EmployeeServiceDep, current_user: CurrentUserDep
) -> ApiResponse[DocumentUploadUrlResponse]:
    url, s3_key = await service.get_document_upload_url(
        employee_id, payload.document_type, payload.file_name, current_user, payload.content_type
    )
    return ApiResponse[DocumentUploadUrlResponse].ok(DocumentUploadUrlResponse(upload_url=url, s3_key=s3_key))


@router.post("/{employee_id}/documents", dependencies=[Depends(require_owner)])
async def confirm_employee_document(
    employee_id: str, payload: ConfirmDocumentRequest, service: EmployeeServiceDep, current_user: CurrentUserDep
) -> ApiResponse[EmployeeDocumentResponse]:
    document = await service.confirm_employee_document(
        employee_id, payload.document_type, payload.file_name, payload.s3_key, payload.content_type, current_user
    )
    return ApiResponse[EmployeeDocumentResponse].ok(
        EmployeeDocumentResponse(
            id=document.require_id(), document_type=document.document_type, file_name=document.file_name,
            s3_key=document.s3_key, content_type=document.content_type, created_at=document.created_at,
        )
    )


@router.get("/{employee_id}/documents")
async def list_employee_documents(
    employee_id: str, service: EmployeeServiceDep, current_user: CurrentUserDep
) -> ApiResponse[list[EmployeeDocumentResponse]]:
    documents = await service.list_employee_documents(employee_id, current_user)
    return ApiResponse[list[EmployeeDocumentResponse]].ok(
        [
            EmployeeDocumentResponse(
                id=d.require_id(), document_type=d.document_type, file_name=d.file_name,
                s3_key=d.s3_key, content_type=d.content_type, created_at=d.created_at,
            )
            for d in documents
        ]
    )


# ---------------------------------------------------------------------- master data


@master_data_router.get("/departments", dependencies=[Depends(require_owner)])
async def list_departments(service: EmployeeServiceDep) -> ApiResponse[list[MasterDataResponse]]:
    departments = await service.list_departments()
    return ApiResponse[list[MasterDataResponse]].ok([mappers.department_to_response(d) for d in departments])


@master_data_router.post("/departments", dependencies=[Depends(require_owner)])
async def create_department(
    payload: MasterDataCreateRequest, service: EmployeeServiceDep, current_user: CurrentUserDep
) -> ApiResponse[MasterDataResponse]:
    department = await service.create_department(payload, current_user)
    return ApiResponse[MasterDataResponse].ok(mappers.department_to_response(department))


@master_data_router.get("/designations", dependencies=[Depends(require_owner)])
async def list_designations(service: EmployeeServiceDep) -> ApiResponse[list[MasterDataResponse]]:
    designations = await service.list_designations()
    return ApiResponse[list[MasterDataResponse]].ok([mappers.designation_to_response(d) for d in designations])


@master_data_router.post("/designations", dependencies=[Depends(require_owner)])
async def create_designation(
    payload: MasterDataCreateRequest, service: EmployeeServiceDep, current_user: CurrentUserDep
) -> ApiResponse[MasterDataResponse]:
    designation = await service.create_designation(payload, current_user)
    return ApiResponse[MasterDataResponse].ok(mappers.designation_to_response(designation))


@master_data_router.get("/branches", dependencies=[Depends(require_owner)])
async def list_branches(service: EmployeeServiceDep) -> ApiResponse[list[BranchResponse]]:
    branches = await service.list_branches()
    return ApiResponse[list[BranchResponse]].ok([mappers.branch_to_response(b) for b in branches])


@master_data_router.post("/branches", dependencies=[Depends(require_owner)])
async def create_branch(
    payload: BranchCreateRequest, service: EmployeeServiceDep, current_user: CurrentUserDep
) -> ApiResponse[BranchResponse]:
    branch = await service.create_branch(payload, current_user)
    return ApiResponse[BranchResponse].ok(mappers.branch_to_response(branch))


# ---------------------------------------------------------------------- shaping helpers


def _session_summary(session: Session) -> SessionSummary:
    return SessionSummary(
        id=session.require_id(),
        device=session.device,
        browser=session.browser,
        operating_system=session.operating_system,
        ip_address=session.ip_address,
        city=session.city,
        country=session.country,
        login_at=session.login_at,
        last_activity_at=session.last_activity_at,
        status=session.status,
    )


def _login_history_entry(doc: dict[str, Any]) -> LoginHistoryEntry:
    return LoginHistoryEntry(
        event_type=doc["event_type"],
        ip_address=doc.get("ip_address"),
        user_agent=doc.get("user_agent"),
        metadata=doc.get("metadata"),
        created_at=doc["created_at"],
    )
