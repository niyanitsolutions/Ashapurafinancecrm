from typing import Any

from app.features.access_control.constants import AccessGrantStatus
from app.features.access_control.models import (
    EmployeeRole,
    GeoException,
    Permission,
    Role,
    RolePermission,
    TemporaryAccess,
)
from app.shared.base_repository import BaseRepository


class RoleRepository(BaseRepository[Role]):
    collection_name = "roles"
    model = Role

    async def find_by_name(self, name: str, *, exclude_id: str | None = None) -> Role | None:
        query: dict[str, Any] = {"name": name, "is_deleted": False}
        if exclude_id:
            from app.utils.helpers import to_object_id

            query["_id"] = {"$ne": to_object_id(exclude_id)}
        doc = await self.collection.find_one(query)
        return self.model.model_validate(doc) if doc else None


class PermissionRepository(BaseRepository[Permission]):
    collection_name = "permissions"
    model = Permission

    async def find_by_module_resource(self, module: str, resource: str) -> Permission | None:
        doc = await self.collection.find_one({"module": module, "resource": resource, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None

    async def find_by_module(self, module: str) -> list[Permission]:
        """Every catalog entry under `module`, regardless of `resource` — used to answer
        "does this role have any access to this module at all" (see
        LeadService._employees_with_module_access), the same "module access" concept
        PermissionEngine.get_accessible_modules already computes per-user."""
        return await self.find_many({"module": module}, limit=500)


class RolePermissionRepository(BaseRepository[RolePermission]):
    collection_name = "role_permissions"
    model = RolePermission

    async def find_for_role(self, role_id: str) -> list[RolePermission]:
        return await self.find_many({"role_id": role_id}, limit=1000)

    async def find_for_roles(self, role_ids: list[str]) -> list[RolePermission]:
        return await self.find_many({"role_id": {"$in": role_ids}}, limit=5000)

    async def find_for_permission(self, permission_id: str) -> list[RolePermission]:
        return await self.find_many({"permission_id": permission_id}, limit=1000)

    async def delete_for_role_permission(self, role_id: str, permission_id: str) -> None:
        await self.collection.delete_many({"role_id": role_id, "permission_id": permission_id})


class EmployeeRoleRepository(BaseRepository[EmployeeRole]):
    collection_name = "employee_roles"
    model = EmployeeRole

    async def find_for_employee(self, employee_id: str) -> list[EmployeeRole]:
        return await self.find_many({"employee_id": employee_id}, limit=100)

    async def find_for_roles(self, role_ids: list[str]) -> list[EmployeeRole]:
        return await self.find_many({"role_id": {"$in": role_ids}}, limit=5000)

    async def find_one(self, employee_id: str, role_id: str) -> EmployeeRole | None:
        doc = await self.collection.find_one({"employee_id": employee_id, "role_id": role_id, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None


class TemporaryAccessRepository(BaseRepository[TemporaryAccess]):
    collection_name = "temporary_access"
    model = TemporaryAccess

    async def find_active_for_employee(self, employee_id: str) -> list[TemporaryAccess]:
        return await self.find_many({"employee_id": employee_id, "status": AccessGrantStatus.ACTIVE}, limit=100)


class GeoExceptionRepository(BaseRepository[GeoException]):
    collection_name = "geo_exceptions"
    model = GeoException

    async def find_active_for_employee(self, employee_id: str) -> list[GeoException]:
        return await self.find_many({"employee_id": employee_id, "status": AccessGrantStatus.ACTIVE}, limit=100)

    async def find_active_by_fence_id(self, geo_fence_id: str) -> list[GeoException]:
        return await self.find_many({"geo_fence_id": geo_fence_id, "status": AccessGrantStatus.ACTIVE}, limit=100)
