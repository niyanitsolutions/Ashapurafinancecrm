import re
from typing import Any

from app.features.employee.models import Branch, Department, Designation, Employee, EmployeeDocument
from app.shared.base_repository import BaseRepository

_SEARCH_FIELDS = ("employee_code", "first_name", "last_name", "email", "mobile")


class EmployeeRepository(BaseRepository[Employee]):
    collection_name = "employees"
    model = Employee

    async def find_by_user_id(self, user_id: str) -> Employee | None:
        doc = await self.collection.find_one({"user_id": user_id, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None

    async def find_by_email(self, email: str, *, exclude_id: str | None = None) -> Employee | None:
        query: dict[str, Any] = {"email": email, "is_deleted": False}
        if exclude_id:
            from app.utils.helpers import to_object_id

            query["_id"] = {"$ne": to_object_id(exclude_id)}
        doc = await self.collection.find_one(query)
        return self.model.model_validate(doc) if doc else None

    async def search_and_filter(
        self,
        *,
        search: str | None,
        department_id: str | None,
        designation_id: str | None,
        branch_id: str | None,
        status: str | None,
        skip: int,
        limit: int,
        sort: list[tuple[str, int]] | None,
    ) -> tuple[list[Employee], int]:
        query: dict[str, Any] = {"is_deleted": False}
        if department_id:
            query["department_id"] = department_id
        if designation_id:
            query["designation_id"] = designation_id
        if branch_id:
            query["branch_id"] = branch_id
        if status:
            query["status"] = status
        if search:
            pattern = re.compile(re.escape(search), re.IGNORECASE)
            query["$or"] = [{field: pattern} for field in _SEARCH_FIELDS]

        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        items = [self.model.model_validate(doc) async for doc in cursor]
        return items, total


class DepartmentRepository(BaseRepository[Department]):
    collection_name = "departments"
    model = Department

    async def find_by_name(self, name: str) -> Department | None:
        doc = await self.collection.find_one({"name": name, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None


class DesignationRepository(BaseRepository[Designation]):
    collection_name = "designations"
    model = Designation

    async def find_by_name(self, name: str) -> Designation | None:
        doc = await self.collection.find_one({"name": name, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None


class BranchRepository(BaseRepository[Branch]):
    collection_name = "branches"
    model = Branch

    async def find_by_code(self, code: str) -> Branch | None:
        doc = await self.collection.find_one({"code": code, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None


class EmployeeDocumentRepository(BaseRepository[EmployeeDocument]):
    collection_name = "employee_documents"
    model = EmployeeDocument
