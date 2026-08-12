from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.response import ApiResponse
from app.features.access_control import mappers
from app.features.access_control.dependencies import CurrentUserDep, get_access_control_service
from app.features.access_control.schemas import (
    AccessibleModulesResponse,
    AssignRoleRequest,
    CreateGeoExceptionRequest,
    CreatePermissionRequest,
    CreateRoleRequest,
    CreateTemporaryAccessRequest,
    EmployeeRoleResponse,
    GeoExceptionResponse,
    PermissionResponse,
    RolePermissionResponse,
    RoleResponse,
    SetRolePermissionsRequest,
    TemporaryAccessResponse,
    UpdateRoleRequest,
)
from app.features.access_control.service import AccessControlService

router = APIRouter(tags=["access-control"])

ServiceDep = Annotated[AccessControlService, Depends(get_access_control_service)]


class DuplicateRoleRequest(BaseModel):
    new_name: str


# ---------------------------------------------------------------------- roles


@router.post("/roles")
async def create_role(payload: CreateRoleRequest, service: ServiceDep, current_user: CurrentUserDep) -> ApiResponse[RoleResponse]:
    role = await service.create_role(payload, current_user)
    return ApiResponse[RoleResponse].ok(mappers.role_to_response(role))


@router.get("/roles")
async def list_roles(service: ServiceDep, current_user: CurrentUserDep) -> ApiResponse[list[RoleResponse]]:
    roles = await service.list_roles()
    return ApiResponse[list[RoleResponse]].ok([mappers.role_to_response(r) for r in roles])


@router.get("/roles/{role_id}")
async def get_role(role_id: str, service: ServiceDep, current_user: CurrentUserDep) -> ApiResponse[RoleResponse]:
    role = await service.get_role(role_id)
    return ApiResponse[RoleResponse].ok(mappers.role_to_response(role))


@router.patch("/roles/{role_id}")
async def update_role(role_id: str, payload: UpdateRoleRequest, service: ServiceDep, current_user: CurrentUserDep) -> ApiResponse[RoleResponse]:
    role = await service.update_role(role_id, payload, current_user)
    return ApiResponse[RoleResponse].ok(mappers.role_to_response(role))


@router.patch("/roles/{role_id}/activate")
async def activate_role(role_id: str, service: ServiceDep, current_user: CurrentUserDep) -> ApiResponse[RoleResponse]:
    role = await service.activate_role(role_id, current_user)
    return ApiResponse[RoleResponse].ok(mappers.role_to_response(role))


@router.patch("/roles/{role_id}/deactivate")
async def deactivate_role(role_id: str, service: ServiceDep, current_user: CurrentUserDep) -> ApiResponse[RoleResponse]:
    role = await service.deactivate_role(role_id, current_user)
    return ApiResponse[RoleResponse].ok(mappers.role_to_response(role))


@router.post("/roles/{role_id}/duplicate")
async def duplicate_role(
    role_id: str, payload: DuplicateRoleRequest, service: ServiceDep, current_user: CurrentUserDep
) -> ApiResponse[RoleResponse]:
    role = await service.duplicate_role(role_id, payload.new_name, current_user)
    return ApiResponse[RoleResponse].ok(mappers.role_to_response(role))


# ---------------------------------------------------------------------- permission matrix


@router.get("/roles/{role_id}/permissions")
async def get_role_permissions(role_id: str, service: ServiceDep, current_user: CurrentUserDep) -> ApiResponse[list[RolePermissionResponse]]:
    grants = await service.get_role_permissions(role_id)
    permissions = await service.list_permissions()
    permissions_by_id = {p.require_id(): p for p in permissions}
    return ApiResponse[list[RolePermissionResponse]].ok(
        [mappers.role_permission_to_response(g, permissions_by_id[g.permission_id]) for g in grants if g.permission_id in permissions_by_id]
    )


@router.put("/roles/{role_id}/permissions")
async def set_role_permissions(
    role_id: str, payload: SetRolePermissionsRequest, service: ServiceDep, current_user: CurrentUserDep
) -> ApiResponse[list[RolePermissionResponse]]:
    grants = await service.set_role_permissions(role_id, payload, current_user)
    permissions = await service.list_permissions()
    permissions_by_id = {p.require_id(): p for p in permissions}
    return ApiResponse[list[RolePermissionResponse]].ok(
        [mappers.role_permission_to_response(g, permissions_by_id[g.permission_id]) for g in grants if g.permission_id in permissions_by_id]
    )


# ---------------------------------------------------------------------- permission catalog


@router.get("/permissions")
async def list_permissions(service: ServiceDep, current_user: CurrentUserDep) -> ApiResponse[list[PermissionResponse]]:
    permissions = await service.list_permissions()
    return ApiResponse[list[PermissionResponse]].ok([mappers.permission_to_response(p) for p in permissions])


@router.post("/permissions")
async def create_permission(payload: CreatePermissionRequest, service: ServiceDep, current_user: CurrentUserDep) -> ApiResponse[PermissionResponse]:
    permission = await service.create_permission(payload, current_user)
    return ApiResponse[PermissionResponse].ok(mappers.permission_to_response(permission))


# ---------------------------------------------------------------------- employee <-> role assignment


@router.post("/roles/{role_id}/assign")
async def assign_role(
    role_id: str, payload: AssignRoleRequest, service: ServiceDep, current_user: CurrentUserDep
) -> ApiResponse[EmployeeRoleResponse]:
    assignment = await service.assign_role(role_id, payload.employee_id, current_user)
    role = await service.get_role(role_id)
    return ApiResponse[EmployeeRoleResponse].ok(mappers.employee_role_to_response(assignment, role))


@router.post("/roles/{role_id}/remove")
async def remove_role(role_id: str, payload: AssignRoleRequest, service: ServiceDep, current_user: CurrentUserDep) -> ApiResponse[None]:
    await service.remove_role(role_id, payload.employee_id, current_user)
    return ApiResponse[None].ok()


@router.get("/employees/{employee_id}/roles")
async def list_employee_roles(
    employee_id: str, service: ServiceDep, current_user: CurrentUserDep
) -> ApiResponse[list[EmployeeRoleResponse]]:
    assignments = await service.list_employee_roles(employee_id)
    roles = await service.list_roles()
    roles_by_id = {r.require_id(): r for r in roles}
    return ApiResponse[list[EmployeeRoleResponse]].ok(
        [mappers.employee_role_to_response(a, roles_by_id[a.role_id]) for a in assignments if a.role_id in roles_by_id]
    )


@router.get("/employees/{employee_id}/accessible-modules")
async def get_employee_accessible_modules(
    employee_id: str, service: ServiceDep, current_user: CurrentUserDep
) -> ApiResponse[AccessibleModulesResponse]:
    assignments = await service.list_employee_roles(employee_id)
    roles = await service.list_roles()
    roles_by_id = {r.require_id(): r for r in roles}
    role_ids = [a.role_id for a in assignments if a.role_id in roles_by_id]
    grants = []
    for role_id in role_ids:
        grants.extend(await service.get_role_permissions(role_id))
    permissions = await service.list_permissions()
    permissions_by_id = {p.require_id(): p for p in permissions}
    modules = sorted({permissions_by_id[g.permission_id].module for g in grants if g.granted_actions and g.permission_id in permissions_by_id})
    return ApiResponse[AccessibleModulesResponse].ok(AccessibleModulesResponse(modules=modules))


# ---------------------------------------------------------------------- temporary access


@router.post("/temporary-access")
async def create_temporary_access(
    payload: CreateTemporaryAccessRequest, service: ServiceDep, current_user: CurrentUserDep
) -> ApiResponse[TemporaryAccessResponse]:
    temp_access = await service.create_temporary_access(payload, current_user)
    permissions = await service.list_permissions()
    permissions_by_id = {p.require_id(): p for p in permissions}
    return ApiResponse[TemporaryAccessResponse].ok(mappers.temporary_access_to_response(temp_access, permissions_by_id))


@router.get("/temporary-access")
async def list_temporary_access(
    service: ServiceDep, current_user: CurrentUserDep, employee_id: str | None = None
) -> ApiResponse[list[TemporaryAccessResponse]]:
    items = await service.list_temporary_access(employee_id)
    permissions = await service.list_permissions()
    permissions_by_id = {p.require_id(): p for p in permissions}
    return ApiResponse[list[TemporaryAccessResponse]].ok([mappers.temporary_access_to_response(t, permissions_by_id) for t in items])


@router.post("/temporary-access/{temporary_access_id}/revoke")
async def revoke_temporary_access(
    temporary_access_id: str, service: ServiceDep, current_user: CurrentUserDep
) -> ApiResponse[TemporaryAccessResponse]:
    temp_access = await service.revoke_temporary_access(temporary_access_id, current_user)
    permissions = await service.list_permissions()
    permissions_by_id = {p.require_id(): p for p in permissions}
    return ApiResponse[TemporaryAccessResponse].ok(mappers.temporary_access_to_response(temp_access, permissions_by_id))


# ---------------------------------------------------------------------- geo exceptions


@router.post("/geo-exceptions")
async def create_geo_exception(
    payload: CreateGeoExceptionRequest, service: ServiceDep, current_user: CurrentUserDep
) -> ApiResponse[GeoExceptionResponse]:
    geo_exception = await service.create_geo_exception(payload, current_user)
    return ApiResponse[GeoExceptionResponse].ok(mappers.geo_exception_to_response(geo_exception))


@router.get("/geo-exceptions")
async def list_geo_exceptions(
    service: ServiceDep, current_user: CurrentUserDep, employee_id: str | None = None
) -> ApiResponse[list[GeoExceptionResponse]]:
    items = await service.list_geo_exceptions(employee_id)
    return ApiResponse[list[GeoExceptionResponse]].ok([mappers.geo_exception_to_response(g) for g in items])


@router.post("/geo-exceptions/{geo_exception_id}/revoke")
async def revoke_geo_exception(
    geo_exception_id: str, service: ServiceDep, current_user: CurrentUserDep
) -> ApiResponse[GeoExceptionResponse]:
    geo_exception = await service.revoke_geo_exception(geo_exception_id, current_user)
    return ApiResponse[GeoExceptionResponse].ok(mappers.geo_exception_to_response(geo_exception))
