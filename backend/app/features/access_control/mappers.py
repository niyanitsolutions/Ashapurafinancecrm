from app.features.access_control.models import (
    EmployeeRole,
    GeoException,
    Permission,
    Role,
    RolePermission,
    TemporaryAccess,
)
from app.features.access_control.schemas import (
    EmployeeRoleResponse,
    GeoExceptionResponse,
    PermissionResponse,
    RolePermissionResponse,
    RoleResponse,
    TemporaryAccessGrantResponse,
    TemporaryAccessResponse,
)


def role_to_response(role: Role) -> RoleResponse:
    return RoleResponse(
        id=role.require_id(), name=role.name, description=role.description,
        status=role.status, created_at=role.created_at, updated_at=role.updated_at,
    )


def permission_to_response(permission: Permission) -> PermissionResponse:
    return PermissionResponse(
        id=permission.require_id(), module=permission.module, resource=permission.resource,
        actions=permission.actions, label=permission.label,
    )


def role_permission_to_response(grant: RolePermission, permission: Permission) -> RolePermissionResponse:
    return RolePermissionResponse(
        id=grant.require_id(), role_id=grant.role_id, permission_id=grant.permission_id,
        module=permission.module, resource=permission.resource,
        granted_actions=grant.granted_actions, department_ids=grant.department_ids, branch_ids=grant.branch_ids,
    )


def employee_role_to_response(assignment: EmployeeRole, role: Role) -> EmployeeRoleResponse:
    return EmployeeRoleResponse(
        id=assignment.require_id(), employee_id=assignment.employee_id, role_id=assignment.role_id, role_name=role.name,
    )


def temporary_access_to_response(temp_access: TemporaryAccess, permissions_by_id: dict[str, Permission]) -> TemporaryAccessResponse:
    grants = []
    for grant in temp_access.grants:
        permission = permissions_by_id.get(grant.permission_id)
        grants.append(
            TemporaryAccessGrantResponse(
                permission_id=grant.permission_id,
                module=permission.module if permission else "",
                resource=permission.resource if permission else "",
                actions=grant.actions,
            )
        )
    return TemporaryAccessResponse(
        id=temp_access.require_id(), employee_id=temp_access.employee_id, grants=grants,
        start_date=temp_access.start_date.date(), end_date=temp_access.end_date.date(),
        start_time=temp_access.start_time, end_time=temp_access.end_time,
        reason=temp_access.reason, status=temp_access.status,
    )


def geo_exception_to_response(geo_exception: GeoException) -> GeoExceptionResponse:
    return GeoExceptionResponse(
        id=geo_exception.require_id(), employee_id=geo_exception.employee_id,
        latitude=geo_exception.allowed_location.latitude, longitude=geo_exception.allowed_location.longitude,
        radius_meters=geo_exception.radius_meters,
        start_date=geo_exception.start_date.date(), end_date=geo_exception.end_date.date(),
        start_time=geo_exception.start_time, end_time=geo_exception.end_time,
        reason=geo_exception.reason, status=geo_exception.status,
    )
