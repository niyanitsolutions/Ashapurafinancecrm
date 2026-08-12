"""Module 4 — Settings (Master Data) routes. Every endpoint is gated with
`Depends(require_permission("system_settings", resource, action))` (Access Control,
Module 3) — the first module to actually consume that engine instead of a bespoke role
check (Owner bypasses it entirely, so behaves exactly like `require_owner` until an
Owner grants a role real permissions here). See docs/decisions/DECISIONS.md.

Departments/Designations/Branches keep their existing `GET`/`POST` on Module 2's own
router (`/departments`, `/designations`, `/branches`) — this router only adds the
`/{id}`, `/{id}/activate`, `/{id}/deactivate` paths Module 2 never had, so there's no
path collision and zero lines change under app/features/employee/.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.core.response import ApiResponse
from app.features.access_control.permission_engine import require_permission
from app.features.auth.models import User
from app.features.employee.schemas import BranchResponse, MasterDataResponse
from app.features.system_settings import mappers
from app.features.system_settings.dependencies import get_system_settings_service
from app.features.system_settings.schemas import (
    ApiSettingCreateRequest,
    ApiSettingResponse,
    ApiSettingUpdateRequest,
    BranchUpdateRequest,
    CompanySettingsResponse,
    ConfirmLogoRequest,
    LogoUploadUrlResponse,
    NamedMasterDataCreateRequest,
    NamedMasterDataResponse,
    NamedMasterDataUpdateRequest,
    NotificationTemplateCreateRequest,
    NotificationTemplateResponse,
    NotificationTemplateUpdateRequest,
    StatusMasterCreateRequest,
    StatusMasterResponse,
    StatusMasterUpdateRequest,
    UpdateCompanySettingsRequest,
)
from app.features.system_settings.service import SystemSettingsService

router = APIRouter(tags=["system-settings"])

ServiceDep = Annotated[SystemSettingsService, Depends(get_system_settings_service)]
_MODULE = "system_settings"


def _perm(resource: str, action: str) -> Any:
    return require_permission(_MODULE, resource, action)


# ---------------------------------------------------------------------- departments (edit/activate/deactivate only)


@router.patch("/departments/{department_id}")
async def update_department(
    department_id: str, payload: NamedMasterDataUpdateRequest, service: ServiceDep, actor: Annotated[User, _perm("departments", "edit")]
) -> ApiResponse[MasterDataResponse]:
    department = await service.update_department(department_id, payload, actor)
    return ApiResponse[MasterDataResponse].ok(mappers.department_to_response(department))


@router.patch("/departments/{department_id}/activate")
async def activate_department(
    department_id: str, service: ServiceDep, actor: Annotated[User, _perm("departments", "edit")]
) -> ApiResponse[MasterDataResponse]:
    department = await service.activate_department(department_id, actor)
    return ApiResponse[MasterDataResponse].ok(mappers.department_to_response(department))


@router.patch("/departments/{department_id}/deactivate")
async def deactivate_department(
    department_id: str, service: ServiceDep, actor: Annotated[User, _perm("departments", "edit")]
) -> ApiResponse[MasterDataResponse]:
    department = await service.deactivate_department(department_id, actor)
    return ApiResponse[MasterDataResponse].ok(mappers.department_to_response(department))


# ---------------------------------------------------------------------- designations (edit/activate/deactivate only)


@router.patch("/designations/{designation_id}")
async def update_designation(
    designation_id: str, payload: NamedMasterDataUpdateRequest, service: ServiceDep, actor: Annotated[User, _perm("designations", "edit")]
) -> ApiResponse[MasterDataResponse]:
    designation = await service.update_designation(designation_id, payload, actor)
    return ApiResponse[MasterDataResponse].ok(mappers.designation_to_response(designation))


@router.patch("/designations/{designation_id}/activate")
async def activate_designation(
    designation_id: str, service: ServiceDep, actor: Annotated[User, _perm("designations", "edit")]
) -> ApiResponse[MasterDataResponse]:
    designation = await service.activate_designation(designation_id, actor)
    return ApiResponse[MasterDataResponse].ok(mappers.designation_to_response(designation))


@router.patch("/designations/{designation_id}/deactivate")
async def deactivate_designation(
    designation_id: str, service: ServiceDep, actor: Annotated[User, _perm("designations", "edit")]
) -> ApiResponse[MasterDataResponse]:
    designation = await service.deactivate_designation(designation_id, actor)
    return ApiResponse[MasterDataResponse].ok(mappers.designation_to_response(designation))


# ---------------------------------------------------------------------- branches (edit/activate/deactivate only)


@router.patch("/branches/{branch_id}")
async def update_branch(
    branch_id: str, payload: BranchUpdateRequest, service: ServiceDep, actor: Annotated[User, _perm("branches", "edit")]
) -> ApiResponse[BranchResponse]:
    branch = await service.update_branch(branch_id, payload, actor)
    return ApiResponse[BranchResponse].ok(mappers.branch_to_response(branch))


@router.patch("/branches/{branch_id}/activate")
async def activate_branch(branch_id: str, service: ServiceDep, actor: Annotated[User, _perm("branches", "edit")]) -> ApiResponse[BranchResponse]:
    branch = await service.activate_branch(branch_id, actor)
    return ApiResponse[BranchResponse].ok(mappers.branch_to_response(branch))


@router.patch("/branches/{branch_id}/deactivate")
async def deactivate_branch(branch_id: str, service: ServiceDep, actor: Annotated[User, _perm("branches", "edit")]) -> ApiResponse[BranchResponse]:
    branch = await service.deactivate_branch(branch_id, actor)
    return ApiResponse[BranchResponse].ok(mappers.branch_to_response(branch))


# ---------------------------------------------------------------------- lead sources


@router.get("/lead-sources")
async def list_lead_sources(service: ServiceDep, actor: Annotated[User, _perm("lead_sources", "view")]) -> ApiResponse[list[NamedMasterDataResponse]]:
    items = await service.list_lead_sources()
    return ApiResponse[list[NamedMasterDataResponse]].ok([mappers.named_master_data_to_response(i) for i in items])


@router.post("/lead-sources")
async def create_lead_source(
    payload: NamedMasterDataCreateRequest, service: ServiceDep, actor: Annotated[User, _perm("lead_sources", "create")]
) -> ApiResponse[NamedMasterDataResponse]:
    item = await service.create_lead_source(payload, actor)
    return ApiResponse[NamedMasterDataResponse].ok(mappers.named_master_data_to_response(item))


@router.get("/lead-sources/{lead_source_id}")
async def get_lead_source(
    lead_source_id: str, service: ServiceDep, actor: Annotated[User, _perm("lead_sources", "view")]
) -> ApiResponse[NamedMasterDataResponse]:
    item = await service.get_lead_source(lead_source_id)
    return ApiResponse[NamedMasterDataResponse].ok(mappers.named_master_data_to_response(item))


@router.patch("/lead-sources/{lead_source_id}")
async def update_lead_source(
    lead_source_id: str, payload: NamedMasterDataUpdateRequest, service: ServiceDep, actor: Annotated[User, _perm("lead_sources", "edit")]
) -> ApiResponse[NamedMasterDataResponse]:
    item = await service.update_lead_source(lead_source_id, payload, actor)
    return ApiResponse[NamedMasterDataResponse].ok(mappers.named_master_data_to_response(item))


@router.patch("/lead-sources/{lead_source_id}/activate")
async def activate_lead_source(
    lead_source_id: str, service: ServiceDep, actor: Annotated[User, _perm("lead_sources", "edit")]
) -> ApiResponse[NamedMasterDataResponse]:
    item = await service.activate_lead_source(lead_source_id, actor)
    return ApiResponse[NamedMasterDataResponse].ok(mappers.named_master_data_to_response(item))


@router.patch("/lead-sources/{lead_source_id}/deactivate")
async def deactivate_lead_source(
    lead_source_id: str, service: ServiceDep, actor: Annotated[User, _perm("lead_sources", "edit")]
) -> ApiResponse[NamedMasterDataResponse]:
    item = await service.deactivate_lead_source(lead_source_id, actor)
    return ApiResponse[NamedMasterDataResponse].ok(mappers.named_master_data_to_response(item))


# ---------------------------------------------------------------------- loan products


@router.get("/loan-products")
async def list_loan_products(service: ServiceDep, actor: Annotated[User, _perm("loan_products", "view")]) -> ApiResponse[list[NamedMasterDataResponse]]:
    items = await service.list_loan_products()
    return ApiResponse[list[NamedMasterDataResponse]].ok([mappers.named_master_data_to_response(i) for i in items])


@router.post("/loan-products")
async def create_loan_product(
    payload: NamedMasterDataCreateRequest, service: ServiceDep, actor: Annotated[User, _perm("loan_products", "create")]
) -> ApiResponse[NamedMasterDataResponse]:
    item = await service.create_loan_product(payload, actor)
    return ApiResponse[NamedMasterDataResponse].ok(mappers.named_master_data_to_response(item))


@router.get("/loan-products/{loan_product_id}")
async def get_loan_product(
    loan_product_id: str, service: ServiceDep, actor: Annotated[User, _perm("loan_products", "view")]
) -> ApiResponse[NamedMasterDataResponse]:
    item = await service.get_loan_product(loan_product_id)
    return ApiResponse[NamedMasterDataResponse].ok(mappers.named_master_data_to_response(item))


@router.patch("/loan-products/{loan_product_id}")
async def update_loan_product(
    loan_product_id: str, payload: NamedMasterDataUpdateRequest, service: ServiceDep, actor: Annotated[User, _perm("loan_products", "edit")]
) -> ApiResponse[NamedMasterDataResponse]:
    item = await service.update_loan_product(loan_product_id, payload, actor)
    return ApiResponse[NamedMasterDataResponse].ok(mappers.named_master_data_to_response(item))


@router.patch("/loan-products/{loan_product_id}/activate")
async def activate_loan_product(
    loan_product_id: str, service: ServiceDep, actor: Annotated[User, _perm("loan_products", "edit")]
) -> ApiResponse[NamedMasterDataResponse]:
    item = await service.activate_loan_product(loan_product_id, actor)
    return ApiResponse[NamedMasterDataResponse].ok(mappers.named_master_data_to_response(item))


@router.patch("/loan-products/{loan_product_id}/deactivate")
async def deactivate_loan_product(
    loan_product_id: str, service: ServiceDep, actor: Annotated[User, _perm("loan_products", "edit")]
) -> ApiResponse[NamedMasterDataResponse]:
    item = await service.deactivate_loan_product(loan_product_id, actor)
    return ApiResponse[NamedMasterDataResponse].ok(mappers.named_master_data_to_response(item))


# ---------------------------------------------------------------------- insurance products


@router.get("/insurance-products")
async def list_insurance_products(
    service: ServiceDep, actor: Annotated[User, _perm("insurance_products", "view")]
) -> ApiResponse[list[NamedMasterDataResponse]]:
    items = await service.list_insurance_products()
    return ApiResponse[list[NamedMasterDataResponse]].ok([mappers.named_master_data_to_response(i) for i in items])


@router.post("/insurance-products")
async def create_insurance_product(
    payload: NamedMasterDataCreateRequest, service: ServiceDep, actor: Annotated[User, _perm("insurance_products", "create")]
) -> ApiResponse[NamedMasterDataResponse]:
    item = await service.create_insurance_product(payload, actor)
    return ApiResponse[NamedMasterDataResponse].ok(mappers.named_master_data_to_response(item))


@router.get("/insurance-products/{insurance_product_id}")
async def get_insurance_product(
    insurance_product_id: str, service: ServiceDep, actor: Annotated[User, _perm("insurance_products", "view")]
) -> ApiResponse[NamedMasterDataResponse]:
    item = await service.get_insurance_product(insurance_product_id)
    return ApiResponse[NamedMasterDataResponse].ok(mappers.named_master_data_to_response(item))


@router.patch("/insurance-products/{insurance_product_id}")
async def update_insurance_product(
    insurance_product_id: str, payload: NamedMasterDataUpdateRequest, service: ServiceDep, actor: Annotated[User, _perm("insurance_products", "edit")]
) -> ApiResponse[NamedMasterDataResponse]:
    item = await service.update_insurance_product(insurance_product_id, payload, actor)
    return ApiResponse[NamedMasterDataResponse].ok(mappers.named_master_data_to_response(item))


@router.patch("/insurance-products/{insurance_product_id}/activate")
async def activate_insurance_product(
    insurance_product_id: str, service: ServiceDep, actor: Annotated[User, _perm("insurance_products", "edit")]
) -> ApiResponse[NamedMasterDataResponse]:
    item = await service.activate_insurance_product(insurance_product_id, actor)
    return ApiResponse[NamedMasterDataResponse].ok(mappers.named_master_data_to_response(item))


@router.patch("/insurance-products/{insurance_product_id}/deactivate")
async def deactivate_insurance_product(
    insurance_product_id: str, service: ServiceDep, actor: Annotated[User, _perm("insurance_products", "edit")]
) -> ApiResponse[NamedMasterDataResponse]:
    item = await service.deactivate_insurance_product(insurance_product_id, actor)
    return ApiResponse[NamedMasterDataResponse].ok(mappers.named_master_data_to_response(item))


# ---------------------------------------------------------------------- document types


@router.get("/document-types")
async def list_document_types(service: ServiceDep, actor: Annotated[User, _perm("document_types", "view")]) -> ApiResponse[list[NamedMasterDataResponse]]:
    items = await service.list_document_types()
    return ApiResponse[list[NamedMasterDataResponse]].ok([mappers.named_master_data_to_response(i) for i in items])


@router.post("/document-types")
async def create_document_type(
    payload: NamedMasterDataCreateRequest, service: ServiceDep, actor: Annotated[User, _perm("document_types", "create")]
) -> ApiResponse[NamedMasterDataResponse]:
    item = await service.create_document_type(payload, actor)
    return ApiResponse[NamedMasterDataResponse].ok(mappers.named_master_data_to_response(item))


@router.get("/document-types/{document_type_id}")
async def get_document_type(
    document_type_id: str, service: ServiceDep, actor: Annotated[User, _perm("document_types", "view")]
) -> ApiResponse[NamedMasterDataResponse]:
    item = await service.get_document_type(document_type_id)
    return ApiResponse[NamedMasterDataResponse].ok(mappers.named_master_data_to_response(item))


@router.patch("/document-types/{document_type_id}")
async def update_document_type(
    document_type_id: str, payload: NamedMasterDataUpdateRequest, service: ServiceDep, actor: Annotated[User, _perm("document_types", "edit")]
) -> ApiResponse[NamedMasterDataResponse]:
    item = await service.update_document_type(document_type_id, payload, actor)
    return ApiResponse[NamedMasterDataResponse].ok(mappers.named_master_data_to_response(item))


@router.patch("/document-types/{document_type_id}/activate")
async def activate_document_type(
    document_type_id: str, service: ServiceDep, actor: Annotated[User, _perm("document_types", "edit")]
) -> ApiResponse[NamedMasterDataResponse]:
    item = await service.activate_document_type(document_type_id, actor)
    return ApiResponse[NamedMasterDataResponse].ok(mappers.named_master_data_to_response(item))


@router.patch("/document-types/{document_type_id}/deactivate")
async def deactivate_document_type(
    document_type_id: str, service: ServiceDep, actor: Annotated[User, _perm("document_types", "edit")]
) -> ApiResponse[NamedMasterDataResponse]:
    item = await service.deactivate_document_type(document_type_id, actor)
    return ApiResponse[NamedMasterDataResponse].ok(mappers.named_master_data_to_response(item))


# ---------------------------------------------------------------------- status masters


@router.get("/status-masters")
async def list_status_masters(
    service: ServiceDep, actor: Annotated[User, _perm("status_masters", "view")], category: str | None = None
) -> ApiResponse[list[StatusMasterResponse]]:
    items = await service.list_status_masters(category)
    return ApiResponse[list[StatusMasterResponse]].ok([mappers.status_master_to_response(i) for i in items])


@router.post("/status-masters")
async def create_status_master(
    payload: StatusMasterCreateRequest, service: ServiceDep, actor: Annotated[User, _perm("status_masters", "create")]
) -> ApiResponse[StatusMasterResponse]:
    item = await service.create_status_master(payload, actor)
    return ApiResponse[StatusMasterResponse].ok(mappers.status_master_to_response(item))


@router.get("/status-masters/{status_master_id}")
async def get_status_master(
    status_master_id: str, service: ServiceDep, actor: Annotated[User, _perm("status_masters", "view")]
) -> ApiResponse[StatusMasterResponse]:
    item = await service.get_status_master(status_master_id)
    return ApiResponse[StatusMasterResponse].ok(mappers.status_master_to_response(item))


@router.patch("/status-masters/{status_master_id}")
async def update_status_master(
    status_master_id: str, payload: StatusMasterUpdateRequest, service: ServiceDep, actor: Annotated[User, _perm("status_masters", "edit")]
) -> ApiResponse[StatusMasterResponse]:
    item = await service.update_status_master(status_master_id, payload, actor)
    return ApiResponse[StatusMasterResponse].ok(mappers.status_master_to_response(item))


@router.patch("/status-masters/{status_master_id}/activate")
async def activate_status_master(
    status_master_id: str, service: ServiceDep, actor: Annotated[User, _perm("status_masters", "edit")]
) -> ApiResponse[StatusMasterResponse]:
    item = await service.activate_status_master(status_master_id, actor)
    return ApiResponse[StatusMasterResponse].ok(mappers.status_master_to_response(item))


@router.patch("/status-masters/{status_master_id}/deactivate")
async def deactivate_status_master(
    status_master_id: str, service: ServiceDep, actor: Annotated[User, _perm("status_masters", "edit")]
) -> ApiResponse[StatusMasterResponse]:
    item = await service.deactivate_status_master(status_master_id, actor)
    return ApiResponse[StatusMasterResponse].ok(mappers.status_master_to_response(item))


# ---------------------------------------------------------------------- notification templates


@router.get("/notification-templates")
async def list_notification_templates(
    service: ServiceDep, actor: Annotated[User, _perm("notification_templates", "view")], channel: str | None = None
) -> ApiResponse[list[NotificationTemplateResponse]]:
    items = await service.list_notification_templates(channel)
    return ApiResponse[list[NotificationTemplateResponse]].ok([mappers.notification_template_to_response(i) for i in items])


@router.post("/notification-templates")
async def create_notification_template(
    payload: NotificationTemplateCreateRequest, service: ServiceDep, actor: Annotated[User, _perm("notification_templates", "create")]
) -> ApiResponse[NotificationTemplateResponse]:
    item = await service.create_notification_template(payload, actor)
    return ApiResponse[NotificationTemplateResponse].ok(mappers.notification_template_to_response(item))


@router.get("/notification-templates/{template_id}")
async def get_notification_template(
    template_id: str, service: ServiceDep, actor: Annotated[User, _perm("notification_templates", "view")]
) -> ApiResponse[NotificationTemplateResponse]:
    item = await service.get_notification_template(template_id)
    return ApiResponse[NotificationTemplateResponse].ok(mappers.notification_template_to_response(item))


@router.patch("/notification-templates/{template_id}")
async def update_notification_template(
    template_id: str, payload: NotificationTemplateUpdateRequest, service: ServiceDep, actor: Annotated[User, _perm("notification_templates", "edit")]
) -> ApiResponse[NotificationTemplateResponse]:
    item = await service.update_notification_template(template_id, payload, actor)
    return ApiResponse[NotificationTemplateResponse].ok(mappers.notification_template_to_response(item))


@router.patch("/notification-templates/{template_id}/activate")
async def activate_notification_template(
    template_id: str, service: ServiceDep, actor: Annotated[User, _perm("notification_templates", "edit")]
) -> ApiResponse[NotificationTemplateResponse]:
    item = await service.activate_notification_template(template_id, actor)
    return ApiResponse[NotificationTemplateResponse].ok(mappers.notification_template_to_response(item))


@router.patch("/notification-templates/{template_id}/deactivate")
async def deactivate_notification_template(
    template_id: str, service: ServiceDep, actor: Annotated[User, _perm("notification_templates", "edit")]
) -> ApiResponse[NotificationTemplateResponse]:
    item = await service.deactivate_notification_template(template_id, actor)
    return ApiResponse[NotificationTemplateResponse].ok(mappers.notification_template_to_response(item))


# ---------------------------------------------------------------------- API settings


@router.get("/api-settings")
async def list_api_settings(service: ServiceDep, actor: Annotated[User, _perm("api_settings", "view")]) -> ApiResponse[list[ApiSettingResponse]]:
    items = await service.list_api_settings()
    return ApiResponse[list[ApiSettingResponse]].ok([mappers.api_setting_to_response(i) for i in items])


@router.post("/api-settings")
async def create_api_setting(
    payload: ApiSettingCreateRequest, service: ServiceDep, actor: Annotated[User, _perm("api_settings", "create")]
) -> ApiResponse[ApiSettingResponse]:
    item = await service.create_api_setting(payload, actor)
    return ApiResponse[ApiSettingResponse].ok(mappers.api_setting_to_response(item))


@router.get("/api-settings/{setting_id}")
async def get_api_setting(setting_id: str, service: ServiceDep, actor: Annotated[User, _perm("api_settings", "view")]) -> ApiResponse[ApiSettingResponse]:
    item = await service.get_api_setting(setting_id)
    return ApiResponse[ApiSettingResponse].ok(mappers.api_setting_to_response(item))


@router.patch("/api-settings/{setting_id}")
async def update_api_setting(
    setting_id: str, payload: ApiSettingUpdateRequest, service: ServiceDep, actor: Annotated[User, _perm("api_settings", "edit")]
) -> ApiResponse[ApiSettingResponse]:
    item = await service.update_api_setting(setting_id, payload, actor)
    return ApiResponse[ApiSettingResponse].ok(mappers.api_setting_to_response(item))


@router.patch("/api-settings/{setting_id}/activate")
async def activate_api_setting(
    setting_id: str, service: ServiceDep, actor: Annotated[User, _perm("api_settings", "edit")]
) -> ApiResponse[ApiSettingResponse]:
    item = await service.activate_api_setting(setting_id, actor)
    return ApiResponse[ApiSettingResponse].ok(mappers.api_setting_to_response(item))


@router.patch("/api-settings/{setting_id}/deactivate")
async def deactivate_api_setting(
    setting_id: str, service: ServiceDep, actor: Annotated[User, _perm("api_settings", "edit")]
) -> ApiResponse[ApiSettingResponse]:
    item = await service.deactivate_api_setting(setting_id, actor)
    return ApiResponse[ApiSettingResponse].ok(mappers.api_setting_to_response(item))


# ---------------------------------------------------------------------- company settings (singleton)


@router.get("/company-settings")
async def get_company_settings(service: ServiceDep, actor: Annotated[User, _perm("company_settings", "view")]) -> ApiResponse[CompanySettingsResponse]:
    settings = await service.get_company_settings()
    return ApiResponse[CompanySettingsResponse].ok(mappers.company_settings_to_response(settings))


@router.patch("/company-settings")
async def update_company_settings(
    payload: UpdateCompanySettingsRequest, service: ServiceDep, actor: Annotated[User, _perm("company_settings", "edit")]
) -> ApiResponse[CompanySettingsResponse]:
    settings = await service.update_company_settings(payload, actor)
    return ApiResponse[CompanySettingsResponse].ok(mappers.company_settings_to_response(settings))


@router.post("/company-settings/logo/upload-url")
async def get_logo_upload_url(service: ServiceDep, actor: Annotated[User, _perm("company_settings", "edit")]) -> ApiResponse[LogoUploadUrlResponse]:
    url, s3_key = await service.get_logo_upload_url(actor)
    return ApiResponse[LogoUploadUrlResponse].ok(LogoUploadUrlResponse(upload_url=url, s3_key=s3_key))


@router.patch("/company-settings/logo")
async def confirm_logo(
    payload: ConfirmLogoRequest, service: ServiceDep, actor: Annotated[User, _perm("company_settings", "edit")]
) -> ApiResponse[CompanySettingsResponse]:
    settings = await service.confirm_logo(payload.s3_key, actor)
    return ApiResponse[CompanySettingsResponse].ok(mappers.company_settings_to_response(settings))
