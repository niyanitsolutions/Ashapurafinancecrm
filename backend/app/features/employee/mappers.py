"""Employee model -> API response shape conversion. Kept separate from service.py since
this is presentation concern (e.g. masking bank account numbers), not business logic.
"""

from app.features.employee.models import Address, Branch, Department, Designation, Employee
from app.features.employee.schemas import (
    AddressSchema,
    BankDetailsResponse,
    BranchResponse,
    EmergencyContactSchema,
    EmployeeDetailResponse,
    EmployeeListItem,
    MasterDataResponse,
)
from app.features.employee.service import EmployeeService


def _address_schema(address: Address | None) -> AddressSchema | None:
    return AddressSchema(**address.model_dump()) if address else None


def to_list_item(employee: Employee, department_name: str, designation_name: str, branch_name: str) -> EmployeeListItem:
    return EmployeeListItem(
        id=employee.require_id(),
        employee_code=employee.employee_code,
        first_name=employee.first_name,
        last_name=employee.last_name,
        display_name=employee.display_name,
        email=employee.email,
        mobile=employee.mobile,
        department_id=employee.department_id,
        department_name=department_name,
        designation_id=employee.designation_id,
        designation_name=designation_name,
        branch_id=employee.branch_id,
        branch_name=branch_name,
        status=employee.status,
        joining_date=employee.joining_date,
        product_ids=employee.product_ids,
    )


def to_detail(employee: Employee, department_name: str, designation_name: str, branch_name: str) -> EmployeeDetailResponse:
    bank_details = None
    if employee.bank_details:
        bank_details = BankDetailsResponse(
            account_holder_name=employee.bank_details.account_holder_name,
            bank_name=employee.bank_details.bank_name,
            branch_name=employee.bank_details.branch_name,
            ifsc_code=employee.bank_details.ifsc_code,
            account_number_masked=EmployeeService.mask_account_number(employee.bank_details.account_number_encrypted),
        )
    return EmployeeDetailResponse(
        id=employee.require_id(),
        user_id=employee.user_id,
        employee_code=employee.employee_code,
        first_name=employee.first_name,
        last_name=employee.last_name,
        display_name=employee.display_name,
        gender=employee.gender,
        date_of_birth=employee.date_of_birth,
        blood_group=employee.blood_group,
        photo_s3_key=employee.photo_s3_key,
        mobile=employee.mobile,
        alternative_mobile=employee.alternative_mobile,
        email=employee.email,
        emergency_contact=EmergencyContactSchema(**employee.emergency_contact.model_dump()) if employee.emergency_contact else None,
        current_address=_address_schema(employee.current_address),
        permanent_address=_address_schema(employee.permanent_address),
        department_id=employee.department_id,
        department_name=department_name,
        designation_id=employee.designation_id,
        designation_name=designation_name,
        branch_id=employee.branch_id,
        branch_name=branch_name,
        joining_date=employee.joining_date,
        employment_type=employee.employment_type,
        reporting_manager_id=employee.reporting_manager_id,
        status=employee.status,
        bank_details=bank_details,
        product_ids=employee.product_ids,
        created_at=employee.created_at,
        updated_at=employee.updated_at,
    )


def department_to_response(department: Department) -> MasterDataResponse:
    return MasterDataResponse(id=department.require_id(), name=department.name, description=department.description, status=department.status)


def designation_to_response(designation: Designation) -> MasterDataResponse:
    return MasterDataResponse(id=designation.require_id(), name=designation.name, description=designation.description, status=designation.status)


def branch_to_response(branch: Branch) -> BranchResponse:
    return BranchResponse(
        id=branch.require_id(), name=branch.name, code=branch.code,
        address=_address_schema(branch.address), phone=branch.phone, status=branch.status,
    )
