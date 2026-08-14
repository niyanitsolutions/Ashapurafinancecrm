"""Module 4 — Settings (Master Data) business logic. No permission checks happen here —
authorization is enforced entirely at the router layer via
`Depends(require_permission("system_settings", resource, action))` (Access Control,
Module 3). This is the first module built *after* Access Control, so it's the first to
actually consume `require_permission` instead of a bespoke role check — see
docs/decisions/DECISIONS.md.

Departments/Designations/Branches are Module 2's own collections (frozen) — this module
adds Edit/Activate/Deactivate for them by composing over Module 2's existing repository
classes (their inherited `update`/generic CRUD), the same read+write reuse pattern
Module 2 itself used against Auth's SessionRepository. Zero lines changed under
app/features/employee/.
"""

import json
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import ConflictError, NotFoundError
from app.features.auth.models import User
from app.features.employee.models import Address, Branch, Department, Designation
from app.features.employee.repository import (
    BranchRepository,
    DepartmentRepository,
    DesignationRepository,
)
from app.features.system_settings.constants import AuditEvent, MasterDataStatus
from app.features.system_settings.models import (
    ApiSetting,
    CompanySettings,
    DocumentType,
    InsuranceProduct,
    LeadSource,
    LoanProduct,
    NamedMasterData,
    NotificationTemplate,
    StatusMaster,
)
from app.features.system_settings.repository import (
    ApiSettingRepository,
    CompanySettingsRepository,
    DocumentTypeRepository,
    InsuranceProductRepository,
    LeadSourceRepository,
    LoanProductRepository,
    NotificationTemplateRepository,
    StatusMasterRepository,
)
from app.features.system_settings.schemas import (
    ApiSettingCreateRequest,
    ApiSettingUpdateRequest,
    BranchUpdateRequest,
    NamedMasterDataCreateRequest,
    NamedMasterDataUpdateRequest,
    NotificationTemplateCreateRequest,
    NotificationTemplateUpdateRequest,
    StatusMasterCreateRequest,
    StatusMasterUpdateRequest,
    UpdateCompanySettingsRequest,
)
from app.security.encryption import decrypt, encrypt
from app.services.storage.client import generate_presigned_upload_url
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now

_UPLOAD_URL_EXPIRE_SECONDS = 300


class SystemSettingsService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self._db = db
        # Module 2's own repositories, reused directly — see module docstring.
        self._departments = DepartmentRepository(db)
        self._designations = DesignationRepository(db)
        self._branches = BranchRepository(db)

        self._lead_sources = LeadSourceRepository(db)
        self._loan_products = LoanProductRepository(db)
        self._insurance_products = InsuranceProductRepository(db)
        self._document_types = DocumentTypeRepository(db)
        self._status_masters = StatusMasterRepository(db)
        self._notification_templates = NotificationTemplateRepository(db)
        self._api_settings = ApiSettingRepository(db)
        self._company_settings = CompanySettingsRepository(db)

    # ================================================================== generic named master data
    # Shared logic for Lead Sources / Loan Products / Insurance Products / Document Types
    # (all name+description+status) — see models.py:NamedMasterData.

    async def _list_named(self, repo: Any) -> list[NamedMasterData]:
        return await repo.find_many({}, limit=500, sort=[("name", 1)])  # type: ignore[no-any-return]

    async def _get_named(self, repo: Any, doc_id: str) -> NamedMasterData:
        doc = await repo.find_by_id(doc_id)
        if doc is None:
            raise NotFoundError("Not found.")
        return doc  # type: ignore[no-any-return]

    async def _create_named(self, repo: Any, payload: NamedMasterDataCreateRequest, actor: User, *, resource: str) -> NamedMasterData:
        if await repo.find_by_name(payload.name):
            raise ConflictError(f"'{payload.name}' already exists.")
        doc = repo.model(name=payload.name, description=payload.description, created_by=actor.require_id())
        doc_id = await repo.insert(doc)
        await write_audit_log(
            self._db, event_type=AuditEvent.master_data(resource, "created"), user_id=actor.require_id(), metadata={"id": doc_id, "name": payload.name}
        )
        return await repo.find_by_id(doc_id) or doc  # type: ignore[no-any-return]

    async def _update_named(self, repo: Any, doc_id: str, payload: NamedMasterDataUpdateRequest, actor: User, *, resource: str) -> NamedMasterData:
        doc = await self._get_named(repo, doc_id)
        updates: dict[str, Any] = {}
        if payload.name is not None and payload.name != doc.name:
            if await repo.find_by_name(payload.name, exclude_id=doc_id):
                raise ConflictError(f"'{payload.name}' already exists.")
            updates["name"] = payload.name
        if payload.description is not None:
            updates["description"] = payload.description
        if not updates:
            return doc
        updated = await repo.update(doc_id, updates, updated_by=actor.require_id())
        await write_audit_log(
            self._db, event_type=AuditEvent.master_data(resource, "updated"), user_id=actor.require_id(), metadata={"id": doc_id, "fields": list(updates.keys())}
        )
        return updated or doc

    async def _set_status_named(self, repo: Any, doc_id: str, status_value: str, action: str, actor: User, *, resource: str) -> NamedMasterData:
        await self._get_named(repo, doc_id)
        updated = await repo.update(doc_id, {"status": status_value}, updated_by=actor.require_id())
        if updated is None:
            raise NotFoundError("Not found.")
        await write_audit_log(self._db, event_type=AuditEvent.master_data(resource, action), user_id=actor.require_id(), metadata={"id": doc_id})
        return updated  # type: ignore[no-any-return]

    # ---- Lead Sources

    async def list_lead_sources(self) -> list[LeadSource]:
        return await self._list_named(self._lead_sources)  # type: ignore[return-value]

    async def create_lead_source(self, payload: NamedMasterDataCreateRequest, actor: User) -> LeadSource:
        return await self._create_named(self._lead_sources, payload, actor, resource="lead_sources")  # type: ignore[return-value]

    async def get_lead_source(self, lead_source_id: str) -> LeadSource:
        return await self._get_named(self._lead_sources, lead_source_id)  # type: ignore[return-value]

    async def update_lead_source(self, lead_source_id: str, payload: NamedMasterDataUpdateRequest, actor: User) -> LeadSource:
        return await self._update_named(self._lead_sources, lead_source_id, payload, actor, resource="lead_sources")  # type: ignore[return-value]

    async def activate_lead_source(self, lead_source_id: str, actor: User) -> LeadSource:
        return await self._set_status_named(self._lead_sources, lead_source_id, MasterDataStatus.ACTIVE, "activated", actor, resource="lead_sources")  # type: ignore[return-value]

    async def deactivate_lead_source(self, lead_source_id: str, actor: User) -> LeadSource:
        return await self._set_status_named(self._lead_sources, lead_source_id, MasterDataStatus.INACTIVE, "deactivated", actor, resource="lead_sources")  # type: ignore[return-value]

    # ---- Loan Products

    async def list_loan_products(self) -> list[LoanProduct]:
        return await self._list_named(self._loan_products)  # type: ignore[return-value]

    async def create_loan_product(self, payload: NamedMasterDataCreateRequest, actor: User) -> LoanProduct:
        return await self._create_named(self._loan_products, payload, actor, resource="loan_products")  # type: ignore[return-value]

    async def get_loan_product(self, loan_product_id: str) -> LoanProduct:
        return await self._get_named(self._loan_products, loan_product_id)  # type: ignore[return-value]

    async def update_loan_product(self, loan_product_id: str, payload: NamedMasterDataUpdateRequest, actor: User) -> LoanProduct:
        return await self._update_named(self._loan_products, loan_product_id, payload, actor, resource="loan_products")  # type: ignore[return-value]

    async def activate_loan_product(self, loan_product_id: str, actor: User) -> LoanProduct:
        return await self._set_status_named(self._loan_products, loan_product_id, MasterDataStatus.ACTIVE, "activated", actor, resource="loan_products")  # type: ignore[return-value]

    async def deactivate_loan_product(self, loan_product_id: str, actor: User) -> LoanProduct:
        return await self._set_status_named(self._loan_products, loan_product_id, MasterDataStatus.INACTIVE, "deactivated", actor, resource="loan_products")  # type: ignore[return-value]

    # ---- Insurance Products

    async def list_insurance_products(self) -> list[InsuranceProduct]:
        return await self._list_named(self._insurance_products)  # type: ignore[return-value]

    async def create_insurance_product(self, payload: NamedMasterDataCreateRequest, actor: User) -> InsuranceProduct:
        return await self._create_named(self._insurance_products, payload, actor, resource="insurance_products")  # type: ignore[return-value]

    async def get_insurance_product(self, insurance_product_id: str) -> InsuranceProduct:
        return await self._get_named(self._insurance_products, insurance_product_id)  # type: ignore[return-value]

    async def update_insurance_product(self, insurance_product_id: str, payload: NamedMasterDataUpdateRequest, actor: User) -> InsuranceProduct:
        return await self._update_named(self._insurance_products, insurance_product_id, payload, actor, resource="insurance_products")  # type: ignore[return-value]

    async def activate_insurance_product(self, insurance_product_id: str, actor: User) -> InsuranceProduct:
        return await self._set_status_named(self._insurance_products, insurance_product_id, MasterDataStatus.ACTIVE, "activated", actor, resource="insurance_products")  # type: ignore[return-value]

    async def deactivate_insurance_product(self, insurance_product_id: str, actor: User) -> InsuranceProduct:
        return await self._set_status_named(self._insurance_products, insurance_product_id, MasterDataStatus.INACTIVE, "deactivated", actor, resource="insurance_products")  # type: ignore[return-value]

    # ---- Document Types

    async def list_document_types(self) -> list[DocumentType]:
        return await self._list_named(self._document_types)  # type: ignore[return-value]

    async def create_document_type(self, payload: NamedMasterDataCreateRequest, actor: User) -> DocumentType:
        return await self._create_named(self._document_types, payload, actor, resource="document_types")  # type: ignore[return-value]

    async def get_document_type(self, document_type_id: str) -> DocumentType:
        return await self._get_named(self._document_types, document_type_id)  # type: ignore[return-value]

    async def update_document_type(self, document_type_id: str, payload: NamedMasterDataUpdateRequest, actor: User) -> DocumentType:
        return await self._update_named(self._document_types, document_type_id, payload, actor, resource="document_types")  # type: ignore[return-value]

    async def activate_document_type(self, document_type_id: str, actor: User) -> DocumentType:
        return await self._set_status_named(self._document_types, document_type_id, MasterDataStatus.ACTIVE, "activated", actor, resource="document_types")  # type: ignore[return-value]

    async def deactivate_document_type(self, document_type_id: str, actor: User) -> DocumentType:
        return await self._set_status_named(self._document_types, document_type_id, MasterDataStatus.INACTIVE, "deactivated", actor, resource="document_types")  # type: ignore[return-value]

    # ================================================================== departments / designations / branches
    # List/Create already exist in Module 2 (`EmployeeService`) — this module adds
    # Edit/Activate/Deactivate only, composing over the same frozen repository classes.

    async def update_department(self, department_id: str, payload: NamedMasterDataUpdateRequest, actor: User) -> Department:
        dept = await self._departments.find_by_id(department_id)
        if dept is None:
            raise NotFoundError("Department not found.")
        updates: dict[str, Any] = {}
        if payload.name is not None and payload.name != dept.name:
            existing = await self._departments.find_by_name(payload.name)
            if existing and existing.require_id() != department_id:
                raise ConflictError(f"Department '{payload.name}' already exists.")
            updates["name"] = payload.name
        if payload.description is not None:
            updates["description"] = payload.description
        if not updates:
            return dept
        updated = await self._departments.update(department_id, updates, updated_by=actor.require_id())
        await write_audit_log(
            self._db, event_type=AuditEvent.master_data("departments", "updated"), user_id=actor.require_id(), metadata={"id": department_id}
        )
        return updated or dept

    async def _set_department_status(self, department_id: str, status_value: str, action: str, actor: User) -> Department:
        if await self._departments.find_by_id(department_id) is None:
            raise NotFoundError("Department not found.")
        updated = await self._departments.update(department_id, {"status": status_value}, updated_by=actor.require_id())
        if updated is None:
            raise NotFoundError("Department not found.")
        await write_audit_log(self._db, event_type=AuditEvent.master_data("departments", action), user_id=actor.require_id(), metadata={"id": department_id})
        return updated

    async def activate_department(self, department_id: str, actor: User) -> Department:
        return await self._set_department_status(department_id, MasterDataStatus.ACTIVE, "activated", actor)

    async def deactivate_department(self, department_id: str, actor: User) -> Department:
        return await self._set_department_status(department_id, MasterDataStatus.INACTIVE, "deactivated", actor)

    async def update_designation(self, designation_id: str, payload: NamedMasterDataUpdateRequest, actor: User) -> Designation:
        designation = await self._designations.find_by_id(designation_id)
        if designation is None:
            raise NotFoundError("Designation not found.")
        updates: dict[str, Any] = {}
        if payload.name is not None and payload.name != designation.name:
            existing = await self._designations.find_by_name(payload.name)
            if existing and existing.require_id() != designation_id:
                raise ConflictError(f"Designation '{payload.name}' already exists.")
            updates["name"] = payload.name
        if payload.description is not None:
            updates["description"] = payload.description
        if not updates:
            return designation
        updated = await self._designations.update(designation_id, updates, updated_by=actor.require_id())
        await write_audit_log(
            self._db, event_type=AuditEvent.master_data("designations", "updated"), user_id=actor.require_id(), metadata={"id": designation_id}
        )
        return updated or designation

    async def _set_designation_status(self, designation_id: str, status_value: str, action: str, actor: User) -> Designation:
        if await self._designations.find_by_id(designation_id) is None:
            raise NotFoundError("Designation not found.")
        updated = await self._designations.update(designation_id, {"status": status_value}, updated_by=actor.require_id())
        if updated is None:
            raise NotFoundError("Designation not found.")
        await write_audit_log(self._db, event_type=AuditEvent.master_data("designations", action), user_id=actor.require_id(), metadata={"id": designation_id})
        return updated

    async def activate_designation(self, designation_id: str, actor: User) -> Designation:
        return await self._set_designation_status(designation_id, MasterDataStatus.ACTIVE, "activated", actor)

    async def deactivate_designation(self, designation_id: str, actor: User) -> Designation:
        return await self._set_designation_status(designation_id, MasterDataStatus.INACTIVE, "deactivated", actor)

    async def update_branch(self, branch_id: str, payload: BranchUpdateRequest, actor: User) -> Branch:
        branch = await self._branches.find_by_id(branch_id)
        if branch is None:
            raise NotFoundError("Branch not found.")
        updates: dict[str, Any] = {}
        if payload.code is not None and payload.code != branch.code:
            existing = await self._branches.find_by_code(payload.code)
            if existing and existing.require_id() != branch_id:
                raise ConflictError(f"Branch code '{payload.code}' already exists.")
            updates["code"] = payload.code
        if payload.name is not None:
            updates["name"] = payload.name
        if payload.phone is not None:
            updates["phone"] = payload.phone
        if payload.address is not None:
            updates["address"] = Address(**payload.address.model_dump()).model_dump()
        if not updates:
            return branch
        updated = await self._branches.update(branch_id, updates, updated_by=actor.require_id())
        await write_audit_log(self._db, event_type=AuditEvent.master_data("branches", "updated"), user_id=actor.require_id(), metadata={"id": branch_id})
        return updated or branch

    async def _set_branch_status(self, branch_id: str, status_value: str, action: str, actor: User) -> Branch:
        if await self._branches.find_by_id(branch_id) is None:
            raise NotFoundError("Branch not found.")
        updated = await self._branches.update(branch_id, {"status": status_value}, updated_by=actor.require_id())
        if updated is None:
            raise NotFoundError("Branch not found.")
        await write_audit_log(self._db, event_type=AuditEvent.master_data("branches", action), user_id=actor.require_id(), metadata={"id": branch_id})
        return updated

    async def activate_branch(self, branch_id: str, actor: User) -> Branch:
        return await self._set_branch_status(branch_id, MasterDataStatus.ACTIVE, "activated", actor)

    async def deactivate_branch(self, branch_id: str, actor: User) -> Branch:
        return await self._set_branch_status(branch_id, MasterDataStatus.INACTIVE, "deactivated", actor)

    # ================================================================== status masters

    async def list_status_masters(self, category: str | None) -> list[StatusMaster]:
        filters = {"category": category} if category else {}
        return await self._status_masters.find_many(filters, limit=500, sort=[("category", 1), ("sequence", 1)])

    async def get_status_master(self, status_master_id: str) -> StatusMaster:
        doc = await self._status_masters.find_by_id(status_master_id)
        if doc is None:
            raise NotFoundError("Status master not found.")
        return doc

    async def create_status_master(self, payload: StatusMasterCreateRequest, actor: User) -> StatusMaster:
        if await self._status_masters.find_by_category_and_name(payload.category, payload.name):
            raise ConflictError(f"Status '{payload.name}' already exists in category '{payload.category}'.")
        doc = StatusMaster(
            category=payload.category, name=payload.name, sequence=payload.sequence,
            description=payload.description, created_by=actor.require_id(),
        )
        doc_id = await self._status_masters.insert(doc)
        await write_audit_log(
            self._db, event_type=AuditEvent.master_data("status_masters", "created"), user_id=actor.require_id(),
            metadata={"id": doc_id, "category": payload.category, "name": payload.name},
        )
        return await self._status_masters.find_by_id(doc_id) or doc

    async def update_status_master(self, status_master_id: str, payload: StatusMasterUpdateRequest, actor: User) -> StatusMaster:
        doc = await self.get_status_master(status_master_id)
        updates: dict[str, Any] = {}
        if payload.name is not None and payload.name != doc.name:
            existing = await self._status_masters.find_by_category_and_name(doc.category, payload.name, exclude_id=status_master_id)
            if existing:
                raise ConflictError(f"Status '{payload.name}' already exists in category '{doc.category}'.")
            updates["name"] = payload.name
        if payload.sequence is not None:
            updates["sequence"] = payload.sequence
        if payload.description is not None:
            updates["description"] = payload.description
        if not updates:
            return doc
        updated = await self._status_masters.update(status_master_id, updates, updated_by=actor.require_id())
        await write_audit_log(
            self._db, event_type=AuditEvent.master_data("status_masters", "updated"), user_id=actor.require_id(), metadata={"id": status_master_id}
        )
        return updated or doc

    async def _set_status_master_status(self, status_master_id: str, status_value: str, action: str, actor: User) -> StatusMaster:
        await self.get_status_master(status_master_id)
        updated = await self._status_masters.update(status_master_id, {"status": status_value}, updated_by=actor.require_id())
        if updated is None:
            raise NotFoundError("Status master not found.")
        await write_audit_log(self._db, event_type=AuditEvent.master_data("status_masters", action), user_id=actor.require_id(), metadata={"id": status_master_id})
        return updated

    async def activate_status_master(self, status_master_id: str, actor: User) -> StatusMaster:
        return await self._set_status_master_status(status_master_id, MasterDataStatus.ACTIVE, "activated", actor)

    async def deactivate_status_master(self, status_master_id: str, actor: User) -> StatusMaster:
        return await self._set_status_master_status(status_master_id, MasterDataStatus.INACTIVE, "deactivated", actor)

    # ================================================================== notification templates

    async def list_notification_templates(self, channel: str | None) -> list[NotificationTemplate]:
        filters = {"channel": channel} if channel else {}
        return await self._notification_templates.find_many(filters, limit=500, sort=[("channel", 1), ("key", 1)])

    async def get_notification_template(self, template_id: str) -> NotificationTemplate:
        doc = await self._notification_templates.find_by_id(template_id)
        if doc is None:
            raise NotFoundError("Notification template not found.")
        return doc

    async def create_notification_template(self, payload: NotificationTemplateCreateRequest, actor: User) -> NotificationTemplate:
        if await self._notification_templates.find_by_channel_and_key(payload.channel, payload.key):
            raise ConflictError(f"Template '{payload.key}' already exists for channel '{payload.channel}'.")
        doc = NotificationTemplate(
            channel=payload.channel, key=payload.key, subject=payload.subject, body=payload.body,
            available_variables=payload.available_variables, created_by=actor.require_id(),
        )
        doc_id = await self._notification_templates.insert(doc)
        await write_audit_log(
            self._db, event_type=AuditEvent.master_data("notification_templates", "created"), user_id=actor.require_id(),
            metadata={"id": doc_id, "channel": payload.channel, "key": payload.key},
        )
        return await self._notification_templates.find_by_id(doc_id) or doc

    async def update_notification_template(self, template_id: str, payload: NotificationTemplateUpdateRequest, actor: User) -> NotificationTemplate:
        doc = await self.get_notification_template(template_id)
        updates: dict[str, Any] = {}
        if payload.subject is not None:
            updates["subject"] = payload.subject
        if payload.body is not None:
            updates["body"] = payload.body
        if payload.available_variables is not None:
            updates["available_variables"] = payload.available_variables
        if not updates:
            return doc
        updated = await self._notification_templates.update(template_id, updates, updated_by=actor.require_id())
        await write_audit_log(
            self._db, event_type=AuditEvent.master_data("notification_templates", "updated"), user_id=actor.require_id(), metadata={"id": template_id}
        )
        return updated or doc

    async def _set_notification_template_status(self, template_id: str, status_value: str, action: str, actor: User) -> NotificationTemplate:
        await self.get_notification_template(template_id)
        updated = await self._notification_templates.update(template_id, {"status": status_value}, updated_by=actor.require_id())
        if updated is None:
            raise NotFoundError("Notification template not found.")
        await write_audit_log(self._db, event_type=AuditEvent.master_data("notification_templates", action), user_id=actor.require_id(), metadata={"id": template_id})
        return updated

    async def activate_notification_template(self, template_id: str, actor: User) -> NotificationTemplate:
        return await self._set_notification_template_status(template_id, MasterDataStatus.ACTIVE, "activated", actor)

    async def deactivate_notification_template(self, template_id: str, actor: User) -> NotificationTemplate:
        return await self._set_notification_template_status(template_id, MasterDataStatus.INACTIVE, "deactivated", actor)

    # ================================================================== API settings
    # `config` is merged (not replaced wholesale) on update so the Owner can change one
    # key without resupplying every other secret — the blob is never returned in
    # plaintext, only its key names (see mappers.py).

    async def list_api_settings(self) -> list[ApiSetting]:
        return await self._api_settings.find_many({}, limit=500, sort=[("provider", 1), ("label", 1)])

    async def get_api_setting(self, setting_id: str) -> ApiSetting:
        doc = await self._api_settings.find_by_id(setting_id)
        if doc is None:
            raise NotFoundError("API setting not found.")
        return doc

    async def create_api_setting(self, payload: ApiSettingCreateRequest, actor: User) -> ApiSetting:
        if await self._api_settings.find_by_provider_and_label(payload.provider, payload.label):
            raise ConflictError(f"'{payload.label}' already exists for provider '{payload.provider}'.")
        doc = ApiSetting(
            provider=payload.provider, label=payload.label, config_encrypted=encrypt(json.dumps(payload.config)),
            is_enabled=payload.is_enabled, created_by=actor.require_id(),
        )
        doc_id = await self._api_settings.insert(doc)
        await write_audit_log(
            self._db, event_type=AuditEvent.master_data("api_settings", "created"), user_id=actor.require_id(),
            metadata={"id": doc_id, "provider": payload.provider, "label": payload.label},
        )
        return await self._api_settings.find_by_id(doc_id) or doc

    async def update_api_setting(self, setting_id: str, payload: ApiSettingUpdateRequest, actor: User) -> ApiSetting:
        doc = await self.get_api_setting(setting_id)
        updates: dict[str, Any] = {}
        if payload.label is not None and payload.label != doc.label:
            existing = await self._api_settings.find_by_provider_and_label(doc.provider, payload.label, exclude_id=setting_id)
            if existing:
                raise ConflictError(f"'{payload.label}' already exists for provider '{doc.provider}'.")
            updates["label"] = payload.label
        if payload.config is not None:
            current = json.loads(decrypt(doc.config_encrypted)) if doc.config_encrypted else {}
            current.update(payload.config)
            updates["config_encrypted"] = encrypt(json.dumps(current))
        if payload.is_enabled is not None:
            updates["is_enabled"] = payload.is_enabled
        if not updates:
            return doc
        updated = await self._api_settings.update(setting_id, updates, updated_by=actor.require_id())
        await write_audit_log(
            self._db, event_type=AuditEvent.master_data("api_settings", "updated"), user_id=actor.require_id(), metadata={"id": setting_id}
        )
        return updated or doc

    async def _set_api_setting_status(self, setting_id: str, status_value: str, action: str, actor: User) -> ApiSetting:
        await self.get_api_setting(setting_id)
        updated = await self._api_settings.update(setting_id, {"status": status_value}, updated_by=actor.require_id())
        if updated is None:
            raise NotFoundError("API setting not found.")
        await write_audit_log(self._db, event_type=AuditEvent.master_data("api_settings", action), user_id=actor.require_id(), metadata={"id": setting_id})
        return updated

    async def activate_api_setting(self, setting_id: str, actor: User) -> ApiSetting:
        return await self._set_api_setting_status(setting_id, MasterDataStatus.ACTIVE, "activated", actor)

    async def deactivate_api_setting(self, setting_id: str, actor: User) -> ApiSetting:
        return await self._set_api_setting_status(setting_id, MasterDataStatus.INACTIVE, "deactivated", actor)

    # ================================================================== company settings (singleton)

    async def get_company_settings(self) -> CompanySettings:
        return await self._company_settings.get_or_create()

    async def update_company_settings(self, payload: UpdateCompanySettingsRequest, actor: User) -> CompanySettings:
        current = await self._company_settings.get_or_create()
        updates: dict[str, Any] = {}
        if payload.company_name is not None:
            updates["company_name"] = payload.company_name
        if payload.primary_color is not None:
            updates["primary_color"] = payload.primary_color
        if payload.secondary_color is not None:
            updates["secondary_color"] = payload.secondary_color
        if payload.business_hours is not None:
            updates["business_hours"] = [h.model_dump() for h in payload.business_hours]
        if payload.contact_email is not None:
            updates["contact_email"] = payload.contact_email
        if payload.contact_phone is not None:
            updates["contact_phone"] = payload.contact_phone
        if payload.address is not None:
            updates["address"] = payload.address.model_dump()
        if not updates:
            return current
        updated = await self._company_settings.update(current.require_id(), updates, updated_by=actor.require_id())
        await write_audit_log(self._db, event_type=AuditEvent.COMPANY_SETTINGS_UPDATED, user_id=actor.require_id(), metadata={"fields": list(updates.keys())})
        return updated or current

    async def get_logo_upload_url(self, actor: User) -> tuple[str, str]:
        s3_key = f"company/logo/{utc_now().timestamp():.0f}.png"
        url = generate_presigned_upload_url(s3_key, expires_in=_UPLOAD_URL_EXPIRE_SECONDS, content_type="image/png")
        return url, s3_key

    async def confirm_logo(self, s3_key: str, actor: User) -> CompanySettings:
        current = await self._company_settings.get_or_create()
        updated = await self._company_settings.update(current.require_id(), {"logo_s3_key": s3_key}, updated_by=actor.require_id())
        await write_audit_log(self._db, event_type=AuditEvent.COMPANY_LOGO_UPDATED, user_id=actor.require_id())
        return updated or current
