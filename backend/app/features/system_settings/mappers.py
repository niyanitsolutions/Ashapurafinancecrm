import json

from app.features.employee.models import Branch, Department, Designation
from app.features.employee.schemas import AddressSchema, BranchResponse, MasterDataResponse
from app.features.system_settings.models import (
    ApiSetting,
    CompanySettings,
    NamedMasterData,
    NotificationTemplate,
    StatusMaster,
)
from app.features.system_settings.schemas import (
    ApiSettingResponse,
    BusinessHourSchema,
    CompanySettingsResponse,
    NamedMasterDataResponse,
    NotificationTemplateResponse,
    StatusMasterResponse,
)
from app.security.encryption import decrypt


def named_master_data_to_response(doc: NamedMasterData) -> NamedMasterDataResponse:
    return NamedMasterDataResponse(
        id=doc.require_id(), name=doc.name, description=doc.description,
        status=doc.status, created_at=doc.created_at, updated_at=doc.updated_at,
    )


def department_to_response(department: Department) -> MasterDataResponse:
    return MasterDataResponse(id=department.require_id(), name=department.name, description=department.description, status=department.status)


def designation_to_response(designation: Designation) -> MasterDataResponse:
    return MasterDataResponse(id=designation.require_id(), name=designation.name, description=designation.description, status=designation.status)


def branch_to_response(branch: Branch) -> BranchResponse:
    address = AddressSchema(**branch.address.model_dump()) if branch.address else None
    return BranchResponse(id=branch.require_id(), name=branch.name, code=branch.code, address=address, phone=branch.phone, status=branch.status)


def status_master_to_response(doc: StatusMaster) -> StatusMasterResponse:
    return StatusMasterResponse(
        id=doc.require_id(), category=doc.category, name=doc.name,
        sequence=doc.sequence, description=doc.description, status=doc.status,
    )


def notification_template_to_response(doc: NotificationTemplate) -> NotificationTemplateResponse:
    return NotificationTemplateResponse(
        id=doc.require_id(), channel=doc.channel, key=doc.key, subject=doc.subject,
        body=doc.body, available_variables=doc.available_variables, status=doc.status,
    )


def api_setting_to_response(doc: ApiSetting) -> ApiSettingResponse:
    configured_keys = sorted(json.loads(decrypt(doc.config_encrypted)).keys()) if doc.config_encrypted else []
    return ApiSettingResponse(
        id=doc.require_id(), provider=doc.provider, label=doc.label, configured_keys=configured_keys,
        is_enabled=doc.is_enabled, status=doc.status, updated_at=doc.updated_at,
    )


def company_settings_to_response(doc: CompanySettings) -> CompanySettingsResponse:
    return CompanySettingsResponse(
        id=doc.require_id(), company_name=doc.company_name, logo_s3_key=doc.logo_s3_key,
        primary_color=doc.primary_color, secondary_color=doc.secondary_color,
        business_hours=[BusinessHourSchema(**h.model_dump()) for h in doc.business_hours],
        updated_at=doc.updated_at,
    )
