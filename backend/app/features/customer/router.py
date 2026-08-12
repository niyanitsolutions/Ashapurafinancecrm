from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.constants.roles import CUSTOMER, EMPLOYEE, OWNER
from app.core.exceptions import ForbiddenError
from app.core.pagination import PageParams, page_params
from app.core.response import ApiResponse, ResponseMeta
from app.features.access_control.permission_engine import require_permission
from app.features.auth.models import User
from app.features.customer import mappers
from app.features.customer.dependencies import (
    CurrentUserDep,
    get_customer_service,
    require_customer,
    require_owner,
    require_staff,
)
from app.features.customer.models import Application, SecureLink
from app.features.customer.schemas import (
    ApplicationDetailResponse,
    ApplicationDocumentResponse,
    ApplicationListItem,
    AssignApplicationRequest,
    CompleteProfileRequest,
    ConfirmDocumentRequest,
    CustomerListItem,
    CustomerResponse,
    DocumentUploadUrlRequest,
    DocumentUploadUrlResponse,
    FormDefinitionCreateRequest,
    FormDefinitionResponse,
    FormDefinitionUpdateRequest,
    FreezeFormDefinitionRequest,
    GenerateSecureLinkRequest,
    LogSecureLinkEventRequest,
    MessageItem,
    NotifySecureLinkRequest,
    PortalDashboardResponse,
    RaiseSupportRequestRequest,
    RejectDocumentRequest,
    SchemaAuditEntryResponse,
    SchemaCompareResponse,
    SecureLinkResponse,
    StartApplicationRequest,
    SubmitApplicationRequest,
    SupportRequestResponse,
    TimelineEntryResponse,
    UpdateApplicationRequest,
    UpdateProfileRequest,
)
from app.features.customer.service import CustomerService

router = APIRouter(tags=["customer"])

ServiceDep = Annotated[CustomerService, Depends(get_customer_service)]
PageParamsDep = Annotated[PageParams, Depends(page_params)]
CustomerDep = Annotated[User, Depends(require_customer)]
StaffDep = Annotated[User, Depends(require_staff)]
OwnerOnlyDep = Annotated[User, Depends(require_owner)]


def _schema_perm(action: str) -> Any:
    return require_permission("system_settings", "product_schema", action)


async def _resolve_form_definition_response(service: CustomerService, form_def: Any) -> FormDefinitionResponse:
    name_map = await service.resolve_document_type_name_map({d.document_type_id for d in form_def.required_documents})
    product_name = await service.resolve_product_name(form_def.product_category, form_def.product_id)
    return mappers.form_definition_to_response(form_def, name_map, product_name)


async def _resolve_application_response(service: CustomerService, application: Application) -> ApplicationDetailResponse:
    customer_map, product_map, employee_map = await service.resolve_names_for_applications([application])
    form_def = await service.get_form_definition_by_id(application.form_definition_id)
    progress_percent = service.compute_progress(form_def, application.form_data)
    return mappers.application_to_detail(
        application,
        customer_map.get(application.customer_id or "", None),
        product_map.get(application.product_id, ""),
        employee_map.get(application.assigned_to or "", None),
        progress_percent,
    )


# ---------------------------------------------------------------------- secure links (Lead-side, staff)


async def _resolve_secure_link_response(service: CustomerService, link: SecureLink) -> SecureLinkResponse:
    creator_name = await service.resolve_secure_link_creator_name(link.created_by)
    return mappers.secure_link_to_response(link, service.build_secure_link_url(link.secure_code), creator_name)


@router.post("/leads/{lead_id}/secure-links")
async def generate_secure_link(
    lead_id: str, payload: GenerateSecureLinkRequest, service: ServiceDep,
    current_user: Annotated[User, require_permission("leads", "leads", "edit")],
) -> ApiResponse[SecureLinkResponse]:
    link = await service.generate_secure_link(
        lead_id, current_user, expiry_minutes=payload.expiry_minutes, one_time_use=payload.one_time_use, notify_channels=payload.notify_channels,
    )
    result = await _resolve_secure_link_response(service, link)
    return ApiResponse[SecureLinkResponse].ok(result)


@router.get("/leads/{lead_id}/secure-link")
async def get_current_secure_link(
    lead_id: str, service: ServiceDep, current_user: Annotated[User, require_permission("leads", "leads", "view")],
) -> ApiResponse[SecureLinkResponse | None]:
    link = await service.get_current_secure_link(lead_id)
    result = await _resolve_secure_link_response(service, link) if link is not None else None
    return ApiResponse[SecureLinkResponse | None].ok(result)


@router.post("/secure-links/{link_id}/disable")
async def disable_secure_link(
    link_id: str, service: ServiceDep, current_user: Annotated[User, require_permission("leads", "leads", "edit")],
) -> ApiResponse[SecureLinkResponse]:
    link = await service.disable_secure_link(link_id, current_user)
    result = await _resolve_secure_link_response(service, link)
    return ApiResponse[SecureLinkResponse].ok(result)


@router.post("/secure-links/{link_id}/notify")
async def notify_secure_link(
    link_id: str, payload: NotifySecureLinkRequest, service: ServiceDep,
    current_user: Annotated[User, require_permission("leads", "leads", "edit")],
) -> ApiResponse[SecureLinkResponse]:
    link = await service.notify_secure_link(link_id, payload.channels, current_user)
    result = await _resolve_secure_link_response(service, link)
    return ApiResponse[SecureLinkResponse].ok(result)


@router.post("/secure-links/{link_id}/log-event")
async def log_secure_link_event(
    link_id: str, payload: LogSecureLinkEventRequest, service: ServiceDep,
    current_user: Annotated[User, require_permission("leads", "leads", "edit")],
) -> ApiResponse[None]:
    await service.log_secure_link_ui_event(link_id, payload.event_type, current_user)
    return ApiResponse[None].ok()


# ---------------------------------------------------------------------- secure links (Customer-side claim)


@router.post("/secure-links/{secure_code}/claim")
async def claim_secure_link(
    secure_code: str, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[ApplicationDetailResponse]:
    application = await service.claim_secure_link(secure_code, current_user)
    result = await _resolve_application_response(service, application)
    return ApiResponse[ApplicationDetailResponse].ok(result)


# ---------------------------------------------------------------------- customer profile (self-service)


@router.get("/customers/me")
async def get_own_profile(service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep) -> ApiResponse[CustomerResponse | None]:
    customer = await service.get_own_customer(current_user)
    return ApiResponse[CustomerResponse | None].ok(mappers.customer_to_response(customer) if customer else None)


@router.post("/customers/me")
async def complete_own_profile(
    payload: CompleteProfileRequest, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[CustomerResponse]:
    customer = await service.complete_profile(payload, current_user)
    return ApiResponse[CustomerResponse].ok(mappers.customer_to_response(customer))


@router.patch("/customers/me")
async def update_own_profile(
    payload: UpdateProfileRequest, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[CustomerResponse]:
    customer = await service.update_own_profile(payload, current_user)
    return ApiResponse[CustomerResponse].ok(mappers.customer_to_response(customer))


# ---------------------------------------------------------------------- Phase 5: Portal Home / Dashboard


@router.get("/customers/me/dashboard")
async def get_own_dashboard(service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep) -> ApiResponse[PortalDashboardResponse]:
    dashboard = await service.get_portal_dashboard(current_user)
    return ApiResponse[PortalDashboardResponse].ok(dashboard)


@router.get("/customers/me/messages")
async def list_own_messages(service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep) -> ApiResponse[list[MessageItem]]:
    messages = await service.list_own_messages(current_user)
    return ApiResponse[list[MessageItem]].ok(messages)


@router.post("/customers/me/support-requests")
async def raise_support_request(
    payload: RaiseSupportRequestRequest, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[SupportRequestResponse]:
    result = await service.raise_support_request(payload, current_user)
    return ApiResponse[SupportRequestResponse].ok(result)


# ---------------------------------------------------------------------- form definitions (shared read — every portal)
# Widened from Customer-only to any authenticated user (Owner/Employee/Customer/Referral
# Partner): the Product Schema Engine is one shared source read identically by Employee
# Create Lead, Referral Partner Add Lead, and the Customer Application flow — none of
# them get their own copy of the field list. Purely additive (broadens read access to
# non-sensitive schema metadata); existing Customer callers behave exactly as before.


@router.get("/application-form-definitions")
async def get_form_definition(
    service: ServiceDep, current_user: CurrentUserDep, product_category: str, product_id: str
) -> ApiResponse[FormDefinitionResponse]:
    form_def = await service.get_form_definition(product_category, product_id)
    result = await _resolve_form_definition_response(service, form_def)
    return ApiResponse[FormDefinitionResponse].ok(result)


# ---------------------------------------------------------------------- product schema authoring (Owner)


@router.get("/product-schemas")
async def list_product_schemas(service: ServiceDep, actor: Annotated[User, _schema_perm("view")]) -> ApiResponse[list[FormDefinitionResponse]]:
    form_defs = await service.list_form_definitions()
    items = [await _resolve_form_definition_response(service, f) for f in form_defs]
    return ApiResponse[list[FormDefinitionResponse]].ok(items)


# Governance round (asks #8/#9) — registered ahead of the `{form_definition_id}` route
# below: both are fixed literal path segments under `/product-schemas`, and FastAPI
# matches routes in registration order, so these would otherwise be swallowed by the
# `{form_definition_id}` catch-all (e.g. a request for "/product-schemas/compare" being
# parsed as form_definition_id="compare").


@router.get("/product-schemas/compare")
async def compare_product_schemas(
    product_category: str,
    product_id: str,
    schema_version_a: int,
    schema_version_b: int,
    service: ServiceDep,
    actor: Annotated[User, _schema_perm("view")],
) -> ApiResponse[SchemaCompareResponse]:
    result = await service.compare_form_definitions(product_category, product_id, schema_version_a, schema_version_b)
    return ApiResponse[SchemaCompareResponse].ok(result)


@router.get("/product-schemas/audit")
async def get_product_schema_audit(
    product_category: str, product_id: str, service: ServiceDep, actor: Annotated[User, _schema_perm("view")]
) -> ApiResponse[list[SchemaAuditEntryResponse]]:
    result = await service.list_schema_audit_entries(product_category, product_id)
    return ApiResponse[list[SchemaAuditEntryResponse]].ok(result)


@router.get("/product-schemas/{form_definition_id}")
async def get_product_schema(
    form_definition_id: str, service: ServiceDep, actor: Annotated[User, _schema_perm("view")]
) -> ApiResponse[FormDefinitionResponse]:
    form_def = await service.get_form_definition_by_id(form_definition_id)
    result = await _resolve_form_definition_response(service, form_def)
    return ApiResponse[FormDefinitionResponse].ok(result)


@router.post("/product-schemas")
async def create_product_schema(
    payload: FormDefinitionCreateRequest, service: ServiceDep, actor: Annotated[User, _schema_perm("create")]
) -> ApiResponse[FormDefinitionResponse]:
    form_def = await service.create_form_definition(payload, actor)
    result = await _resolve_form_definition_response(service, form_def)
    return ApiResponse[FormDefinitionResponse].ok(result)


@router.patch("/product-schemas/{form_definition_id}")
async def update_product_schema(
    form_definition_id: str, payload: FormDefinitionUpdateRequest, service: ServiceDep, actor: Annotated[User, _schema_perm("edit")]
) -> ApiResponse[FormDefinitionResponse]:
    form_def = await service.update_form_definition(form_definition_id, payload, actor)
    result = await _resolve_form_definition_response(service, form_def)
    return ApiResponse[FormDefinitionResponse].ok(result)


# Governance round (asks #6-#9) — freeze/version lifecycle, Compare, Audit History.
# Preview (ask #7) needs no endpoint of its own: the existing GET above already returns
# full detail for a DRAFT, which the frontend renders through the same components the
# real Customer Portal uses (see plan §6) — no server-side change required for it.


@router.post("/product-schemas/{form_definition_id}/freeze")
async def freeze_product_schema(
    form_definition_id: str, payload: FreezeFormDefinitionRequest, service: ServiceDep, actor: Annotated[User, _schema_perm("edit")]
) -> ApiResponse[FormDefinitionResponse]:
    form_def = await service.freeze_form_definition(form_definition_id, payload.confirmed_checklist, actor)
    result = await _resolve_form_definition_response(service, form_def)
    return ApiResponse[FormDefinitionResponse].ok(result)


@router.post("/product-schemas/{form_definition_id}/new-version")
async def create_product_schema_version(
    form_definition_id: str, service: ServiceDep, actor: Annotated[User, _schema_perm("edit")]
) -> ApiResponse[FormDefinitionResponse]:
    form_def = await service.create_new_version(form_definition_id, actor)
    result = await _resolve_form_definition_response(service, form_def)
    return ApiResponse[FormDefinitionResponse].ok(result)


@router.post("/product-schemas/{form_definition_id}/publish")
async def publish_product_schema(
    form_definition_id: str, service: ServiceDep, actor: Annotated[User, _schema_perm("edit")]
) -> ApiResponse[FormDefinitionResponse]:
    form_def = await service.publish_form_definition(form_definition_id, actor)
    result = await _resolve_form_definition_response(service, form_def)
    return ApiResponse[FormDefinitionResponse].ok(result)


# ---------------------------------------------------------------------- applications (customer self-service)


@router.post("/applications")
async def start_application(
    payload: StartApplicationRequest, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[ApplicationDetailResponse]:
    application = await service.start_application(payload, current_user)
    result = await _resolve_application_response(service, application)
    return ApiResponse[ApplicationDetailResponse].ok(result)


@router.get("/applications/me")
async def list_own_applications(
    service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep, status: str | None = None
) -> ApiResponse[list[ApplicationListItem]]:
    applications = await service.list_own_applications(current_user, status=status)
    customer_map, product_map, employee_map = await service.resolve_names_for_applications(applications)
    items = []
    for a in applications:
        progress_percent = await service.compute_progress_for_application(a)
        items.append(
            mappers.application_to_list_item(
                a, customer_map.get(a.customer_id or "", None), product_map.get(a.product_id, ""), employee_map.get(a.assigned_to or "", None),
                progress_percent,
            )
        )
    return ApiResponse[list[ApplicationListItem]].ok(items)


@router.patch("/applications/{application_id}")
async def update_application(
    application_id: str, payload: UpdateApplicationRequest, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[ApplicationDetailResponse]:
    application = await service.update_application(application_id, payload, current_user)
    result = await _resolve_application_response(service, application)
    return ApiResponse[ApplicationDetailResponse].ok(result)


@router.post("/applications/{application_id}/submit")
async def submit_application(
    application_id: str, payload: SubmitApplicationRequest, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[ApplicationDetailResponse]:
    application = await service.submit_application(application_id, payload, current_user)
    result = await _resolve_application_response(service, application)
    return ApiResponse[ApplicationDetailResponse].ok(result)


@router.post("/applications/{application_id}/documents/upload-url")
async def get_document_upload_url(
    application_id: str, payload: DocumentUploadUrlRequest, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[DocumentUploadUrlResponse]:
    url, s3_key = await service.get_document_upload_url(application_id, payload.document_type_id, payload.file_name, current_user, payload.content_type)
    return ApiResponse[DocumentUploadUrlResponse].ok(DocumentUploadUrlResponse(upload_url=url, s3_key=s3_key))


@router.post("/applications/{application_id}/documents")
async def confirm_document(
    application_id: str, payload: ConfirmDocumentRequest, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[ApplicationDocumentResponse]:
    document = await service.confirm_document(application_id, payload, current_user)
    type_names = await service.resolve_document_type_names([document])
    return ApiResponse[ApplicationDocumentResponse].ok(
        mappers.document_to_response(document, type_names.get(document.document_type_id, ""), None)
    )


# ---------------------------------------------------------------------- applications (shared: customer-self OR staff)


@router.get("/applications/{application_id}")
async def get_application(application_id: str, service: ServiceDep, current_user: CurrentUserDep) -> ApiResponse[ApplicationDetailResponse]:
    # `CurrentUserDep` alone authenticates every role, including Referral Partner — the
    # role branch below must therefore end in an explicit deny, not fall through to the
    # staff path for anyone who isn't a Customer. `get_application_for_staff` only scopes
    # Employee vs Owner; it was never meant to be reachable by a non-staff role at all.
    if current_user.role == CUSTOMER:
        application = await service.get_own_application(application_id, current_user)
    elif current_user.role in (OWNER, EMPLOYEE):
        application = await service.get_application_for_staff(application_id, current_user)
    else:
        raise ForbiddenError("You do not have access to this application.")
    result = await _resolve_application_response(service, application)
    return ApiResponse[ApplicationDetailResponse].ok(result)


@router.get("/applications/{application_id}/timeline")
async def get_application_timeline(
    application_id: str, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[list[TimelineEntryResponse]]:
    entries = await service.get_application_timeline(application_id, current_user)
    return ApiResponse[list[TimelineEntryResponse]].ok(entries)


@router.get("/applications/{application_id}/documents")
async def list_documents(application_id: str, service: ServiceDep, current_user: CurrentUserDep) -> ApiResponse[list[ApplicationDocumentResponse]]:
    # Same role-gate reasoning as `get_application` above — this endpoint mints presigned
    # download URLs, so an unauthorized role reaching the staff branch is a direct KYC/PII
    # document leak, not just a metadata leak.
    if current_user.role == CUSTOMER:
        documents = await service.list_own_documents(application_id, current_user)
    elif current_user.role in (OWNER, EMPLOYEE):
        documents = await service.list_documents_for_staff(application_id, current_user)
    else:
        raise ForbiddenError("You do not have access to these documents.")
    type_names = await service.resolve_document_type_names(documents)
    verifier_names = await service.resolve_verifier_names(documents)
    items = [
        mappers.document_to_response(
            d, type_names.get(d.document_type_id, ""), service.document_download_url(d), verifier_names.get(d.verified_by or "")
        )
        for d in documents
    ]
    return ApiResponse[list[ApplicationDocumentResponse]].ok(items)


@router.patch("/applications/{application_id}/documents/{document_id}/verify")
async def verify_document(
    application_id: str, document_id: str, service: ServiceDep, actor: StaffDep
) -> ApiResponse[ApplicationDocumentResponse]:
    document = await service.verify_document(application_id, document_id, actor)
    type_names = await service.resolve_document_type_names([document])
    verifier_names = await service.resolve_verifier_names([document])
    return ApiResponse[ApplicationDocumentResponse].ok(
        mappers.document_to_response(
            document, type_names.get(document.document_type_id, ""), None, verifier_names.get(document.verified_by or "")
        )
    )


@router.patch("/applications/{application_id}/documents/{document_id}/reject")
async def reject_document(
    application_id: str, document_id: str, payload: RejectDocumentRequest, service: ServiceDep, actor: StaffDep
) -> ApiResponse[ApplicationDocumentResponse]:
    document = await service.reject_document(application_id, document_id, payload.reason, actor)
    type_names = await service.resolve_document_type_names([document])
    verifier_names = await service.resolve_verifier_names([document])
    return ApiResponse[ApplicationDocumentResponse].ok(
        mappers.document_to_response(
            document, type_names.get(document.document_type_id, ""), None, verifier_names.get(document.verified_by or "")
        )
    )


# ---------------------------------------------------------------------- staff views (Owner + assigned Employee)


@router.get("/applications")
async def list_applications(
    service: ServiceDep, current_user: CurrentUserDep, _staff: StaffDep, page: PageParamsDep,
    customer_id: str | None = None, assigned_to: str | None = None, unassigned_only: bool = False,
    status: str | None = None, product_category: str | None = None,
) -> ApiResponse[list[ApplicationListItem]]:
    applications, total = await service.list_applications_for_staff(
        current_user, search=page.search, customer_id=customer_id, assigned_to=assigned_to, unassigned_only=unassigned_only,
        status=status, product_category=product_category, skip=page.skip, limit=page.page_size, sort=page.sort,
    )
    customer_map, product_map, employee_map = await service.resolve_names_for_applications(applications)
    items = [
        mappers.application_to_list_item(a, customer_map.get(a.customer_id or "", None), product_map.get(a.product_id, ""), employee_map.get(a.assigned_to or "", None))
        for a in applications
    ]
    return ApiResponse[list[ApplicationListItem]].ok(items, meta=ResponseMeta(pagination=page.build_meta(total)))


@router.post("/applications/{application_id}/assign")
async def assign_application(
    application_id: str, payload: AssignApplicationRequest, service: ServiceDep, current_user: CurrentUserDep, _owner: OwnerOnlyDep
) -> ApiResponse[ApplicationDetailResponse]:
    application = await service.assign_application(application_id, payload.employee_id, current_user)
    result = await _resolve_application_response(service, application)
    return ApiResponse[ApplicationDetailResponse].ok(result)


@router.get("/customers")
async def list_customers(service: ServiceDep, current_user: CurrentUserDep, _staff: StaffDep, page: PageParamsDep) -> ApiResponse[list[CustomerListItem]]:
    customers, total = await service.list_customers_for_staff(current_user, search=page.search, skip=page.skip, limit=page.page_size, sort=page.sort)
    items = [mappers.customer_to_list_item(c) for c in customers]
    return ApiResponse[list[CustomerListItem]].ok(items, meta=ResponseMeta(pagination=page.build_meta(total)))


@router.get("/customers/{customer_id}")
async def get_customer(customer_id: str, service: ServiceDep, current_user: CurrentUserDep, _staff: StaffDep) -> ApiResponse[CustomerResponse]:
    customer = await service.get_customer_for_staff(customer_id, current_user)
    return ApiResponse[CustomerResponse].ok(mappers.customer_to_response(customer))
