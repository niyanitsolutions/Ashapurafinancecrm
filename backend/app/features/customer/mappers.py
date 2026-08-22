from app.features.customer.models import (
    Application,
    ApplicationDocument,
    ApplicationFormDefinition,
    Customer,
    FormFieldDefinition,
    RequiredDocumentDefinition,
    SecureLink,
)
from app.features.customer.schemas import (
    ApplicationDetailResponse,
    ApplicationDocumentResponse,
    ApplicationListItem,
    CustomerListItem,
    CustomerResponse,
    FieldConditionResponse,
    FieldValidationResponse,
    FormDefinitionResponse,
    FormFieldResponse,
    RepeatableGroupResponse,
    RequiredDocumentResponse,
    SecureLinkResponse,
)
from app.features.employee.schemas import AddressSchema
from app.features.employee.service import EmployeeService
from app.features.workflow_engine.models import ApplicationWorkflow


def customer_to_response(customer: Customer, lead_code: str | None = None, lead_source_name: str | None = None) -> CustomerResponse:
    return CustomerResponse(
        id=customer.require_id(),
        customer_code=customer.customer_code,
        full_name=customer.full_name,
        mobile=customer.mobile,
        email=customer.email,
        date_of_birth=customer.date_of_birth.date() if customer.date_of_birth else None,
        gender=customer.gender,
        pan_number_masked=EmployeeService.mask_account_number(customer.pan_number_encrypted) if customer.pan_number_encrypted else None,
        aadhaar_number_masked=EmployeeService.mask_account_number(customer.aadhaar_number_encrypted) if customer.aadhaar_number_encrypted else None,
        address=AddressSchema(**customer.address.model_dump()) if customer.address else None,
        status=customer.status,
        converted_from_lead_id=customer.converted_from_lead_id,
        registration_source="lead" if customer.converted_from_lead_id else "direct",
        lead_code=lead_code,
        lead_source_name=lead_source_name,
        created_at=customer.created_at,
    )


def customer_to_list_item(customer: Customer) -> CustomerListItem:
    return CustomerListItem(
        id=customer.require_id(), customer_code=customer.customer_code, full_name=customer.full_name,
        mobile=customer.mobile, email=customer.email, status=customer.status,
        registration_source="lead" if customer.converted_from_lead_id else "direct",
        created_at=customer.created_at,
    )


def field_to_response(f: FormFieldDefinition) -> FormFieldResponse:
    return FormFieldResponse(
        key=f.key,
        label=f.label,
        field_type=f.field_type,
        required=f.required,
        options=f.options,
        section=f.section,
        visible_when=FieldConditionResponse(field_key=f.visible_when.field_key, operator=f.visible_when.operator, value=f.visible_when.value)
        if f.visible_when
        else None,
        validation=FieldValidationResponse(**f.validation.model_dump()) if f.validation else None,
        options_source=f.options_source,
        options_endpoint=f.options_endpoint,
        source=f.source,
        master_key=f.master_key,
        placeholder=f.placeholder,
        hidden=f.hidden,
    )


def required_document_to_response(
    d: RequiredDocumentDefinition, document_type_names: dict[str, str] | None = None, document_type_password_support: dict[str, bool] | None = None
) -> RequiredDocumentResponse:
    names = document_type_names or {}
    password_support = document_type_password_support or {}
    return RequiredDocumentResponse(
        document_type_id=d.document_type_id, document_type_name=names.get(d.document_type_id, ""), section=d.section, note=d.note,
        name_override=d.name_override, required=d.required, allowed_types=d.allowed_types, max_size_mb=d.max_size_mb,
        multiple_upload=d.multiple_upload, preview_enabled=d.preview_enabled, source=d.source, hidden=d.hidden,
        supports_password=password_support.get(d.document_type_id, False),
    )


def form_definition_to_response(
    form_def: ApplicationFormDefinition, document_type_names: dict[str, str] | None = None, product_name: str = "",
    document_type_password_support: dict[str, bool] | None = None,
) -> FormDefinitionResponse:
    names = document_type_names or {}
    return FormDefinitionResponse(
        id=form_def.require_id(),
        product_category=form_def.product_category,
        product_id=form_def.product_id,
        product_name=product_name,
        fields=[field_to_response(f) for f in form_def.fields],
        required_documents=[required_document_to_response(d, names, document_type_password_support) for d in form_def.required_documents],
        repeatable_groups=[
            RepeatableGroupResponse(
                key=g.key, label=g.label, add_button_label=g.add_button_label, min_count=g.min_count, max_count=g.max_count,
                fields=[field_to_response(f) for f in g.fields],
            )
            for g in form_def.repeatable_groups
        ],
        status=form_def.status,
        version=form_def.version,
        created_by=form_def.created_by,
        created_at=form_def.created_at,
        updated_at=form_def.updated_at,
        is_locked=form_def.is_locked,
        frozen_at=form_def.frozen_at,
        frozen_by=form_def.frozen_by,
        schema_version=form_def.schema_version,
        source_schema_version=form_def.source_schema_version,
    )


def application_to_list_item(
    application: Application, customer_name: str | None, product_name: str, employee_name: str | None, progress_percent: int = 0,
    case: ApplicationWorkflow | None = None, case_status_label: str | None = None,
) -> ApplicationListItem:
    return ApplicationListItem(
        id=application.require_id(),
        application_code=application.application_code,
        customer_id=application.customer_id,
        customer_name=customer_name,
        lead_id=application.lead_id,
        product_category=application.product_category,
        product_id=application.product_id,
        product_name=product_name,
        assigned_to=application.assigned_to,
        assigned_to_name=employee_name,
        status=application.status,
        created_at=application.created_at,
        submitted_at=application.submitted_at,
        progress_percent=progress_percent,
        case_id=case.require_id() if case else None,
        case_type=case.case_type if case else None,
        case_code=case.case_code if case else None,
        case_status=case.current_status if case else None,
        case_status_label=case_status_label,
    )


def application_to_detail(
    application: Application, customer_name: str | None, product_name: str, employee_name: str | None, progress_percent: int = 0,
    case: ApplicationWorkflow | None = None, case_status_label: str | None = None,
) -> ApplicationDetailResponse:
    return ApplicationDetailResponse(
        **application_to_list_item(application, customer_name, product_name, employee_name, progress_percent, case, case_status_label).model_dump(),
        form_definition_id=application.form_definition_id,
        form_data=application.form_data,
        updated_at=application.updated_at,
    )


def secure_link_to_response(link: SecureLink, link_url: str, created_by_name: str | None) -> SecureLinkResponse:
    return SecureLinkResponse(
        id=link.require_id(),
        secure_code=link.secure_code,
        link_url=link_url,
        status=link.status,
        expires_at=link.expires_at,
        one_time_use=link.one_time_use,
        created_by=link.created_by,
        created_by_name=created_by_name,
        created_at=link.created_at,
        used_at=link.used_at,
        last_opened_at=link.last_opened_at,
        notification_status=link.notification_status,
    )


def document_to_response(
    document: ApplicationDocument, document_type_name: str, download_url: str | None, verified_by_name: str | None = None
) -> ApplicationDocumentResponse:
    return ApplicationDocumentResponse(
        id=document.require_id(),
        application_id=document.application_id,
        document_type_id=document.document_type_id,
        document_type_name=document_type_name,
        file_name=document.file_name,
        content_type=document.content_type,
        download_url=download_url,
        created_at=document.created_at,
        verification_status=document.verification_status,
        verified_by_name=verified_by_name,
        verified_at=document.verified_at,
        rejection_reason=document.rejection_reason,
        document_status=document.document_status,
        file_size_bytes=document.file_size_bytes,
        is_current=document.is_current,
        doc_version=document.doc_version,
        replaces_document_id=document.replaces_document_id,
        has_password=document.password_encrypted is not None,
    )
