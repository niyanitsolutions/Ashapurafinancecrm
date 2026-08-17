"""Employee & Master Data business logic. No permission engine here (Module 3) — just a
plain Owner-vs-self role check. Reuses Auth's existing repository/service classes for
session/password actions rather than adding capabilities to the frozen Auth module.
"""

import csv
import io
from datetime import UTC, date, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.constants.roles import EMPLOYEE, OWNER
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.features.auth.models import (
    ACCOUNT_STATUS_ACTIVE,
    ACCOUNT_STATUS_DISABLED,
    SESSION_STATUS_ACTIVE,
    SESSION_STATUS_REVOKED,
    User,
)
from app.features.auth.repository import SessionRepository, UserRepository
from app.features.auth.service import AuthService
from app.features.employee.constants import AuditEvent, EmploymentStatus
from app.features.employee.models import (
    Address,
    BankDetails,
    Branch,
    Department,
    Designation,
    EmergencyContact,
    Employee,
    EmployeeDocument,
)
from app.features.employee.repository import (
    BranchRepository,
    DepartmentRepository,
    DesignationRepository,
    EmployeeDocumentRepository,
    EmployeeRepository,
)
from app.features.employee.schemas import (
    BankDetailsInput,
    BranchCreateRequest,
    CreateEmployeeRequest,
    MasterDataCreateRequest,
    SelfUpdateEmployeeRequest,
    UpdateEmployeeRequest,
)
from app.security.encryption import decrypt, encrypt
from app.security.password import hash_password
from app.services.storage.client import generate_presigned_upload_url
from app.shared.audit_log import write_audit_log
from app.utils.datetime import ist_date_range_to_utc_bounds, utc_now
from app.utils.id_generator import IdPrefix, generate_id

_PHOTO_URL_EXPIRE_SECONDS = 300


def _date_to_datetime(value: date | None) -> datetime | None:
    """BSON has no date-only type — Employee stores datetime (midnight UTC); the API
    schemas speak plain `date`. See the note on Employee.date_of_birth in models.py."""
    if value is None:
        return None
    return _date_to_datetime_required(value)


def _date_to_datetime_required(value: date) -> datetime:
    return datetime(value.year, value.month, value.day, tzinfo=UTC)


class EmployeeService:
    def __init__(self, db: AsyncIOMotorDatabase[Any], redis: Redis) -> None:
        self._db = db
        self._redis = redis
        self._employees = EmployeeRepository(db)
        self._departments = DepartmentRepository(db)
        self._designations = DesignationRepository(db)
        self._branches = BranchRepository(db)
        self._documents = EmployeeDocumentRepository(db)
        self._users = UserRepository(db)
        self._sessions = SessionRepository(db)
        self._auth = AuthService(db, redis)

    # ---------------------------------------------------------------- master data

    async def list_departments(self) -> list[Department]:
        return await self._departments.find_many({}, limit=500, sort=[("name", 1)])

    async def create_department(self, payload: MasterDataCreateRequest, owner: User) -> Department:
        if await self._departments.find_by_name(payload.name):
            raise ConflictError(f"Department '{payload.name}' already exists.")
        dept = Department(name=payload.name, description=payload.description, created_by=owner.require_id())
        dept_id = await self._departments.insert(dept)
        await write_audit_log(self._db, event_type=AuditEvent.DEPARTMENT_CREATED, user_id=owner.require_id(), metadata={"department_id": dept_id})
        return await self._departments.find_by_id(dept_id) or dept

    async def list_designations(self) -> list[Designation]:
        return await self._designations.find_many({}, limit=500, sort=[("name", 1)])

    async def create_designation(self, payload: MasterDataCreateRequest, owner: User) -> Designation:
        if await self._designations.find_by_name(payload.name):
            raise ConflictError(f"Designation '{payload.name}' already exists.")
        designation = Designation(name=payload.name, description=payload.description, created_by=owner.require_id())
        designation_id = await self._designations.insert(designation)
        await write_audit_log(self._db, event_type=AuditEvent.DESIGNATION_CREATED, user_id=owner.require_id(), metadata={"designation_id": designation_id})
        return await self._designations.find_by_id(designation_id) or designation

    async def list_branches(self) -> list[Branch]:
        return await self._branches.find_many({}, limit=500, sort=[("name", 1)])

    async def create_branch(self, payload: BranchCreateRequest, owner: User) -> Branch:
        if await self._branches.find_by_code(payload.code):
            raise ConflictError(f"Branch code '{payload.code}' already exists.")
        address = Address(**payload.address.model_dump()) if payload.address else None
        branch = Branch(name=payload.name, code=payload.code, address=address, phone=payload.phone, created_by=owner.require_id())
        branch_id = await self._branches.insert(branch)
        await write_audit_log(self._db, event_type=AuditEvent.BRANCH_CREATED, user_id=owner.require_id(), metadata={"branch_id": branch_id})
        return await self._branches.find_by_id(branch_id) or branch

    async def _validate_master_data_refs(self, *, department_id: str, designation_id: str, branch_id: str) -> None:
        if await self._departments.find_by_id(department_id) is None:
            raise ValidationError("Unknown department_id.")
        if await self._designations.find_by_id(designation_id) is None:
            raise ValidationError("Unknown designation_id.")
        if await self._branches.find_by_id(branch_id) is None:
            raise ValidationError("Unknown branch_id.")

    # ---------------------------------------------------------------- create / update

    async def create_employee(self, payload: CreateEmployeeRequest, owner: User) -> Employee:
        if await self._users.find_by_mobile(payload.mobile) is not None:
            raise ConflictError("This mobile number is already registered.")
        if await self._employees.find_by_email(payload.email) is not None:
            raise ConflictError("This email is already registered.")
        await self._validate_master_data_refs(
            department_id=payload.department_id, designation_id=payload.designation_id, branch_id=payload.branch_id
        )
        if payload.reporting_manager_id and await self._employees.find_by_id(payload.reporting_manager_id) is None:
            raise ValidationError("Unknown reporting_manager_id.")

        # Employee accounts have no OTP-invite path (decision 007/011) — the Owner sets an
        # initial password directly and the account is active immediately. must_change_password
        # forces the Employee to set their own password on first login (Rule 3/9).
        user = User(
            mobile=payload.mobile,
            role=EMPLOYEE,
            status=ACCOUNT_STATUS_ACTIVE,
            password_hash=hash_password(payload.initial_password),
            is_mobile_verified=True,
            must_change_password=True,
            created_by=owner.require_id(),
        )
        user_id = await self._users.insert(user)

        employee_code = await generate_id(self._db, IdPrefix.EMPLOYEE)
        display_name = payload.display_name or f"{payload.first_name} {payload.last_name}"

        employee = Employee(
            user_id=user_id,
            employee_code=employee_code,
            first_name=payload.first_name,
            last_name=payload.last_name,
            display_name=display_name,
            gender=payload.gender,
            date_of_birth=_date_to_datetime(payload.date_of_birth),
            blood_group=payload.blood_group,
            mobile=payload.mobile,
            alternative_mobile=payload.alternative_mobile,
            email=payload.email,
            emergency_contact=EmergencyContact(**payload.emergency_contact.model_dump()) if payload.emergency_contact else None,
            current_address=Address(**payload.current_address.model_dump()) if payload.current_address else None,
            permanent_address=Address(**payload.permanent_address.model_dump()) if payload.permanent_address else None,
            department_id=payload.department_id,
            designation_id=payload.designation_id,
            branch_id=payload.branch_id,
            joining_date=_date_to_datetime_required(payload.joining_date),
            employment_type=payload.employment_type,
            reporting_manager_id=payload.reporting_manager_id,
            bank_details=self._encrypt_bank_details(payload.bank_details),
            status=EmploymentStatus.ACTIVE,
            product_ids=payload.product_ids,
            created_by=owner.require_id(),
        )
        employee_id = await self._employees.insert(employee)

        await write_audit_log(
            self._db,
            event_type=AuditEvent.EMPLOYEE_CREATED,
            user_id=owner.require_id(),
            metadata={"employee_id": employee_id, "employee_code": employee_code},
        )
        return await self._employees.find_by_id(employee_id) or employee

    async def update_employee(self, employee_id: str, payload: UpdateEmployeeRequest, owner: User) -> Employee:
        employee = await self._get_or_404(employee_id)
        updates: dict[str, Any] = {}

        if payload.email is not None and payload.email != employee.email:
            if await self._employees.find_by_email(payload.email, exclude_id=employee_id) is not None:
                raise ConflictError("This email is already registered.")
            updates["email"] = payload.email

        for field in (
            "first_name", "last_name", "display_name", "gender", "blood_group",
            "alternative_mobile", "employment_type", "reporting_manager_id",
        ):
            value = getattr(payload, field)
            if value is not None:
                updates[field] = value
        if payload.date_of_birth is not None:
            updates["date_of_birth"] = _date_to_datetime_required(payload.date_of_birth)
        if payload.joining_date is not None:
            updates["joining_date"] = _date_to_datetime_required(payload.joining_date)

        if payload.emergency_contact is not None:
            updates["emergency_contact"] = payload.emergency_contact.model_dump()
        if payload.current_address is not None:
            updates["current_address"] = payload.current_address.model_dump()
        if payload.permanent_address is not None:
            updates["permanent_address"] = payload.permanent_address.model_dump()
        if payload.bank_details is not None:
            updates["bank_details"] = self._encrypt_bank_details_required(payload.bank_details).model_dump()
        if payload.product_ids is not None:
            updates["product_ids"] = payload.product_ids

        if payload.department_id or payload.designation_id or payload.branch_id:
            await self._validate_master_data_refs(
                department_id=payload.department_id or employee.department_id,
                designation_id=payload.designation_id or employee.designation_id,
                branch_id=payload.branch_id or employee.branch_id,
            )
            for field in ("department_id", "designation_id", "branch_id"):
                value = getattr(payload, field)
                if value is not None:
                    updates[field] = value

        if payload.status is not None and payload.status != employee.status:
            updates["status"] = payload.status
            await self._sync_login_status(employee.user_id, payload.status)

        if not updates:
            return employee

        updated = await self._employees.update(employee_id, updates, updated_by=owner.require_id())
        await write_audit_log(
            self._db, event_type=AuditEvent.EMPLOYEE_UPDATED, user_id=owner.require_id(),
            metadata={"employee_id": employee_id, "fields": list(updates.keys())},
        )
        return updated or employee

    async def self_update_employee(self, employee_id: str, payload: SelfUpdateEmployeeRequest, actor: User) -> Employee:
        employee = await self._get_or_404(employee_id)
        self._ensure_self(employee, actor)

        updates: dict[str, Any] = {}
        for field in ("first_name", "last_name", "display_name", "gender", "date_of_birth", "blood_group", "alternative_mobile"):
            value = getattr(payload, field)
            if value is not None:
                updates[field] = value
        if payload.emergency_contact is not None:
            updates["emergency_contact"] = payload.emergency_contact.model_dump()
        if payload.current_address is not None:
            updates["current_address"] = payload.current_address.model_dump()
        if payload.permanent_address is not None:
            updates["permanent_address"] = payload.permanent_address.model_dump()

        if not updates:
            return employee

        updated = await self._employees.update(employee_id, updates, updated_by=actor.require_id())
        await write_audit_log(
            self._db, event_type=AuditEvent.EMPLOYEE_SELF_UPDATED, user_id=actor.require_id(),
            metadata={"employee_id": employee_id, "fields": list(updates.keys())},
        )
        return updated or employee

    async def activate_employee(self, employee_id: str, owner: User) -> Employee:
        employee = await self._get_or_404(employee_id)
        await self._sync_login_status(employee.user_id, EmploymentStatus.ACTIVE)
        updated = await self._employees.update(employee_id, {"status": EmploymentStatus.ACTIVE}, updated_by=owner.require_id())
        await write_audit_log(self._db, event_type=AuditEvent.EMPLOYEE_ACTIVATED, user_id=owner.require_id(), metadata={"employee_id": employee_id})
        return updated or employee

    async def deactivate_employee(self, employee_id: str, owner: User) -> Employee:
        employee = await self._get_or_404(employee_id)
        await self._sync_login_status(employee.user_id, EmploymentStatus.INACTIVE)
        updated = await self._employees.update(employee_id, {"status": EmploymentStatus.INACTIVE}, updated_by=owner.require_id())
        await write_audit_log(self._db, event_type=AuditEvent.EMPLOYEE_DEACTIVATED, user_id=owner.require_id(), metadata={"employee_id": employee_id})
        return updated or employee

    async def _sync_login_status(self, user_id: str, employment_status: str) -> None:
        """Pairs employment status with login access — see docs/KNOWN_LIMITATIONS.md for
        the ON_LEAVE-does-not-block-login judgment call."""
        new_account_status = ACCOUNT_STATUS_DISABLED if employment_status in EmploymentStatus.LOGIN_BLOCKED else ACCOUNT_STATUS_ACTIVE
        await self._users.update(user_id, {"status": new_account_status})

    # ---------------------------------------------------------------- read / list / export

    async def get_employee(self, employee_id: str, actor: User) -> Employee:
        employee = await self._get_or_404(employee_id)
        self._ensure_can_view(employee, actor)
        return employee

    async def get_own_employee(self, actor: User) -> Employee:
        employee = await self._employees.find_by_user_id(actor.require_id())
        if employee is None:
            raise NotFoundError("No employee profile found for this account.")
        return employee

    async def list_employees(
        self, *, search: str | None, department_id: str | None, designation_id: str | None,
        branch_id: str | None, status: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None,
    ) -> tuple[list[Employee], int]:
        return await self._employees.search_and_filter(
            search=search, department_id=department_id, designation_id=designation_id,
            branch_id=branch_id, status=status, skip=skip, limit=limit, sort=sort,
        )

    async def export_employees_csv(self) -> str:
        employees, _ = await self._employees.search_and_filter(
            search=None, department_id=None, designation_id=None, branch_id=None, status=None,
            skip=0, limit=10_000, sort=[("employee_code", 1)],
        )
        dept_map, desig_map, branch_map = await self.get_master_data_maps(employees)

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Employee Code", "First Name", "Last Name", "Email", "Mobile", "Department", "Designation", "Branch", "Status", "Joining Date"])
        for e in employees:
            writer.writerow([
                e.employee_code, e.first_name, e.last_name, e.email, e.mobile,
                dept_map.get(e.department_id, ""), desig_map.get(e.designation_id, ""),
                branch_map.get(e.branch_id, ""), e.status, e.joining_date.date().isoformat(),
            ])
        return buffer.getvalue()

    async def resolve_master_data_names(self, employee: Employee) -> tuple[str, str, str]:
        department = await self._departments.find_by_id(employee.department_id)
        designation = await self._designations.find_by_id(employee.designation_id)
        branch = await self._branches.find_by_id(employee.branch_id)
        return (
            department.name if department else "",
            designation.name if designation else "",
            branch.name if branch else "",
        )

    async def get_master_data_maps(self, employees: list[Employee]) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
        dept_ids = {e.department_id for e in employees}
        desig_ids = {e.designation_id for e in employees}
        branch_ids = {e.branch_id for e in employees}
        depts = await self._departments.find_many({}, limit=500)
        desigs = await self._designations.find_many({}, limit=500)
        branches = await self._branches.find_many({}, limit=500)
        dept_map = {d.require_id(): d.name for d in depts if d.require_id() in dept_ids}
        desig_map = {d.require_id(): d.name for d in desigs if d.require_id() in desig_ids}
        branch_map = {b.require_id(): b.name for b in branches if b.require_id() in branch_ids}
        return dept_map, desig_map, branch_map

    # ---------------------------------------------------------------- security actions (reuse Auth internals)

    async def reset_employee_password(self, employee_id: str, owner: User) -> None:
        """Triggers the existing public forgot-password flow for this employee's mobile —
        reuses AuthService unmodified rather than adding a new Auth capability."""
        employee = await self._get_or_404(employee_id)
        await self._auth.forgot_password(mobile=employee.mobile)
        await write_audit_log(
            self._db, event_type=AuditEvent.EMPLOYEE_PASSWORD_RESET_TRIGGERED, user_id=owner.require_id(),
            metadata={"employee_id": employee_id},
        )

    async def force_logout_employee(self, employee_id: str, owner: User) -> int:
        """Revokes every active session for this employee, using Auth's existing
        SessionRepository directly (its collection property + inherited find_many /
        update are already part of the frozen module's public surface)."""
        employee = await self._get_or_404(employee_id)
        active_sessions = await self._sessions.find_many({"user_id": employee.user_id, "status": SESSION_STATUS_ACTIVE}, limit=1000)
        for session in active_sessions:
            await self._sessions.update(session.require_id(), {"status": SESSION_STATUS_REVOKED, "logout_at": utc_now()})
        await write_audit_log(
            self._db, event_type=AuditEvent.EMPLOYEE_FORCE_LOGOUT, user_id=owner.require_id(),
            metadata={"employee_id": employee_id, "sessions_revoked": len(active_sessions)},
        )
        return len(active_sessions)

    async def list_employee_sessions(self, employee_id: str, actor: User) -> list[Any]:
        employee = await self._get_or_404(employee_id)
        self._ensure_can_view(employee, actor)
        return await self._sessions.find_many({"user_id": employee.user_id}, limit=100, sort=[("login_at", -1)])

    async def list_employee_login_history(self, employee_id: str, actor: User, limit: int = 50) -> list[dict[str, Any]]:
        employee = await self._get_or_404(employee_id)
        self._ensure_can_view(employee, actor)
        cursor = self._db["audit_logs"].find({"user_id": employee.user_id}).sort("created_at", -1).limit(limit)
        return [doc async for doc in cursor]

    async def get_activity_summary(self, employee_id: str, actor: User) -> dict[str, Any]:
        employee = await self._get_or_404(employee_id)
        self._ensure_can_view(employee, actor)

        user = await self._users.find_by_id(employee.user_id)
        login_count = await self._db["audit_logs"].count_documents({"user_id": employee.user_id, "event_type": "login"})
        failed_count = await self._db["audit_logs"].count_documents({"user_id": employee.user_id, "event_type": "failed_login"})
        last_login = await self._db["audit_logs"].find_one({"user_id": employee.user_id, "event_type": "login"}, sort=[("created_at", -1)])
        active_sessions = await self._sessions.find_many({"user_id": employee.user_id, "status": SESSION_STATUS_ACTIVE}, limit=1000)

        return {
            "total_logins": login_count,
            "failed_login_count": failed_count,
            "last_login_at": last_login["created_at"] if last_login else None,
            "active_session_count": len(active_sessions),
            "account_status": user.status if user else "unknown",
            "employment_status": employee.status,
        }

    # ---------------------------------------------------------------- photo

    async def get_photo_upload_url(self, employee_id: str, actor: User) -> tuple[str, str]:
        employee = await self._get_or_404(employee_id)
        self._ensure_self(employee, actor)
        s3_key = f"employee-photos/{employee.employee_code}/{utc_now().timestamp():.0f}.jpg"
        url = generate_presigned_upload_url(s3_key, expires_in=_PHOTO_URL_EXPIRE_SECONDS, content_type="image/jpeg")
        return url, s3_key

    async def confirm_photo(self, employee_id: str, s3_key: str, actor: User) -> Employee:
        employee = await self._get_or_404(employee_id)
        self._ensure_self(employee, actor)
        updated = await self._employees.update(employee_id, {"photo_s3_key": s3_key}, updated_by=actor.require_id())
        await write_audit_log(self._db, event_type=AuditEvent.EMPLOYEE_PHOTO_UPDATED, user_id=actor.require_id(), metadata={"employee_id": employee_id})
        return updated or employee

    # ---------------------------------------------------------------- documents
    # Owner-only, per the brief (neither Owner Features nor Employee Portal lists a
    # self-service document upload action — only the data model anticipates it). No
    # frontend page consumes this yet; see docs/KNOWN_LIMITATIONS.md.

    async def get_document_upload_url(self, employee_id: str, document_type: str, file_name: str, owner: User, content_type: str | None) -> tuple[str, str]:
        employee = await self._get_or_404(employee_id)
        s3_key = f"employee-documents/{employee.employee_code}/{document_type}/{file_name}"
        url = generate_presigned_upload_url(s3_key, expires_in=_PHOTO_URL_EXPIRE_SECONDS, content_type=content_type)
        return url, s3_key

    async def confirm_employee_document(
        self, employee_id: str, document_type: str, file_name: str, s3_key: str, content_type: str | None, owner: User
    ) -> EmployeeDocument:
        await self._get_or_404(employee_id)
        document = EmployeeDocument(
            employee_id=employee_id, document_type=document_type, file_name=file_name,
            s3_key=s3_key, content_type=content_type, created_by=owner.require_id(),
        )
        document_id = await self._documents.insert(document)
        return await self._documents.find_by_id(document_id) or document

    async def list_employee_documents(self, employee_id: str, actor: User) -> list[EmployeeDocument]:
        employee = await self._get_or_404(employee_id)
        self._ensure_can_view(employee, actor)
        return await self._documents.find_many({"employee_id": employee_id}, limit=100)

    # ---------------------------------------------------------------- cross-employee overviews (owner-only)

    async def list_all_documents(
        self, *, employee_id: str | None, document_type: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None
    ) -> tuple[list[EmployeeDocument], dict[str, str], int]:
        documents, total = await self._documents.search_and_filter(
            employee_id=employee_id, document_type=document_type, skip=skip, limit=limit, sort=sort
        )
        name_map = await self._resolve_employee_names({d.employee_id for d in documents})
        return documents, name_map, total

    async def list_activity(
        self, *, employee_id: str | None, event_type: str | None, date_from: date | None, date_to: date | None,
        skip: int, limit: int,
    ) -> tuple[list[dict[str, Any]], dict[str, str], int]:
        """Owner-only, company-wide counterpart of `list_employee_login_history` above —
        same `audit_logs` collection, same `user_id`-scoped query shape, just without a
        single employee pre-selected. When no `employee_id` filter is given, scopes to
        the bounded set of every employee's `user_id` (same batch-resolution precedent as
        `get_master_data_maps`) so this never accidentally surfaces Owner/Customer/
        Referral Partner audit events, which `list_employee_login_history` never risked
        since it always start from one known employee."""
        query: dict[str, Any] = {}
        if event_type:
            query["event_type"] = event_type
        # date_from/date_to are business (IST) calendar dates picked by the Owner —
        # converted to UTC instant bounds the same way the reporting module's own
        # date-range filters are (see docs/TIMEZONE.md).
        lower, upper = ist_date_range_to_utc_bounds(date_from, date_to)
        if lower is not None or upper is not None:
            query["created_at"] = {}
            if lower is not None:
                query["created_at"]["$gte"] = lower
            if upper is not None:
                query["created_at"]["$lt"] = upper

        if employee_id:
            employee = await self._get_or_404(employee_id)
            query["user_id"] = employee.user_id
            name_map = {employee_id: employee.display_name}
        else:
            employees = await self._employees.find_many({}, limit=1000)
            user_id_to_employee = {e.user_id: e for e in employees}
            query["user_id"] = {"$in": list(user_id_to_employee.keys())}
            name_map = {e.require_id(): e.display_name for e in employees}

        total = await self._db["audit_logs"].count_documents(query)
        cursor = self._db["audit_logs"].find(query).sort("created_at", -1).skip(skip).limit(limit)
        entries = [doc async for doc in cursor]

        if not employee_id:
            # Re-key the per-entry employee_id (not yet on `entries`) from user_id, so the
            # router can attach both employee_id/employee_name per row without a second query.
            user_id_to_employee_id = {uid: e.require_id() for uid, e in user_id_to_employee.items()}
            for entry in entries:
                entry["_employee_id"] = user_id_to_employee_id.get(entry.get("user_id"))
        else:
            for entry in entries:
                entry["_employee_id"] = employee_id

        return entries, name_map, total

    async def _resolve_employee_names(self, employee_ids: set[str]) -> dict[str, str]:
        if not employee_ids:
            return {}
        employees = await self._employees.find_many({}, limit=1000)
        return {e.require_id(): e.display_name for e in employees if e.require_id() in employee_ids}

    # ---------------------------------------------------------------- internals

    async def _get_or_404(self, employee_id: str) -> Employee:
        employee = await self._employees.find_by_id(employee_id)
        if employee is None:
            raise NotFoundError("Employee not found.")
        return employee

    def _ensure_can_view(self, employee: Employee, actor: User) -> None:
        if actor.role == OWNER:
            return
        self._ensure_self(employee, actor)

    def _ensure_self(self, employee: Employee, actor: User) -> None:
        if employee.user_id != actor.require_id():
            raise ForbiddenError("You can only access your own profile.")

    def _encrypt_bank_details(self, payload: BankDetailsInput | None) -> BankDetails | None:
        if payload is None:
            return None
        return self._encrypt_bank_details_required(payload)

    def _encrypt_bank_details_required(self, payload: BankDetailsInput) -> BankDetails:
        return BankDetails(
            account_holder_name=payload.account_holder_name,
            bank_name=payload.bank_name,
            branch_name=payload.branch_name,
            ifsc_code=payload.ifsc_code,
            account_number_encrypted=encrypt(payload.account_number),
        )

    @staticmethod
    def mask_account_number(encrypted: str) -> str:
        plaintext = decrypt(encrypted)
        return f"{'*' * max(0, len(plaintext) - 4)}{plaintext[-4:]}"
