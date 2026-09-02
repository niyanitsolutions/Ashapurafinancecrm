"""The single definition of WHAT is deletable through the centralized Bin and HOW each
record type is described, guarded, and (on 30-day purge) cascaded.

Only genuine BUSINESS records are here. Configuration / master-data collections
(`loan_products`, `lead_sources`, `roles`, `permissions`, `workflow_definitions`,
`reminder_rules`, `communication_templates`, `application_form_definitions`, branches /
departments / designations, geo fences / exceptions, `company_settings`, integration
configs, ...) are deliberately absent — permanently deleting one could corrupt live
system configuration, and each already has its own activate/deactivate lifecycle. Those
keep their existing feature-specific management and are never routed through the Bin.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import ValidationError
from app.features.workflow_engine.constants import (
    TERMINAL_STATUSES_BY_CASE_TYPE,
    CaseType,
)

Guard = Callable[[dict[str, Any], AsyncIOMotorDatabase[Any]], Awaitable[None]]


@dataclass(frozen=True)
class DeletableResource:
    key: str
    collection: str
    module_label: str
    # Field on the document whose (title-cased) value labels the record's stage in the
    # Bin table — `stage`/`current_status`/`status`. None for records with no stage.
    stage_field: str | None = None
    code_field: str | None = None
    summary_fields: tuple[str, ...] = ()
    # (child collection, foreign-key field) pairs hard-deleted alongside the parent on
    # 30-day purge — strictly OWNED private children only (never shared entities like
    # `customers`, `users`, `applications`, or financial ledgers).
    child_collections: tuple[tuple[str, str], ...] = ()
    # Only rows of `collection` with this `case_type` belong to this resource
    # (`application_workflows` holds both loan and insurance cases).
    case_type: str | None = None
    guard: Guard | None = field(default=None)

    def matches(self, doc: dict[str, Any]) -> bool:
        return self.case_type is None or doc.get("case_type") == self.case_type


# ---------------------------------------------------------------------- guards


async def _guard_customer(doc: dict[str, Any], db: AsyncIOMotorDatabase[Any]) -> None:
    customer_id = str(doc["_id"])
    open_case = await db["application_workflows"].find_one(
        {
            "customer_id": customer_id, "is_deleted": False,
            "current_status": {"$nin": [s for statuses in TERMINAL_STATUSES_BY_CASE_TYPE.values() for s in statuses]},
        }
    )
    if open_case is not None:
        raise ValidationError("This customer still has an open loan/insurance case. Close or delete that case first.")


async def _guard_employee(doc: dict[str, Any], db: AsyncIOMotorDatabase[Any]) -> None:
    employee_id = str(doc["_id"])
    for collection in ("leads", "application_workflows"):
        if await db[collection].find_one({"assigned_to": employee_id, "is_deleted": False}) is not None:
            raise ValidationError(
                "This employee still has leads or cases assigned. Reassign them first "
                "(or deactivate the employee instead of deleting)."
            )


# ---------------------------------------------------------------------- registry

_RESOURCES: tuple[DeletableResource, ...] = (
    DeletableResource(
        key="leads", collection="leads", module_label="Leads",
        stage_field="stage", code_field="lead_code", summary_fields=("full_name", "mobile"),
        child_collections=(("lead_notes", "lead_id"), ("lead_activities", "lead_id")),
    ),
    DeletableResource(
        key="loan_cases", collection="application_workflows", module_label="Loan Management",
        stage_field="current_status", code_field="case_code", summary_fields=("case_code",),
        case_type=CaseType.LOAN,
        child_collections=(
            ("application_status_history", "application_workflow_id"),
            ("application_notes", "application_workflow_id"),
            ("application_decisions", "application_workflow_id"),
            ("loan_case_bank_offers", "loan_case_id"),
            ("loan_case_additional_documents", "loan_case_id"),
        ),
    ),
    DeletableResource(
        key="insurance_cases", collection="application_workflows", module_label="Insurance Management",
        stage_field="current_status", code_field="case_code", summary_fields=("case_code",),
        case_type=CaseType.INSURANCE,
        child_collections=(
            ("application_status_history", "application_workflow_id"),
            ("application_notes", "application_workflow_id"),
            ("application_decisions", "application_workflow_id"),
        ),
    ),
    DeletableResource(
        key="customers", collection="customers", module_label="Customers",
        code_field=None, summary_fields=("full_name", "mobile"),
        guard=_guard_customer,
    ),
    DeletableResource(
        key="applications", collection="applications", module_label="Applications",
        stage_field="status", code_field="application_code", summary_fields=("application_code",),
        child_collections=(("application_documents", "application_id"),),
    ),
    DeletableResource(
        key="referral_partners", collection="referral_partners", module_label="Referral Partners",
        stage_field="status", code_field="partner_code", summary_fields=("full_name", "mobile"),
    ),
    DeletableResource(
        key="employees", collection="employees", module_label="Employees",
        stage_field="status", code_field="employee_code", summary_fields=("first_name", "last_name"),
        guard=_guard_employee,
    ),
    DeletableResource(
        key="scheduled_reports", collection="scheduled_reports", module_label="Scheduled Reports",
        code_field=None, summary_fields=("report_key",),
    ),
)

_BY_KEY = {r.key: r for r in _RESOURCES}


def get_resource(key: str) -> DeletableResource:
    resource = _BY_KEY.get(key)
    if resource is None:
        raise ValidationError(f"'{key}' is not a deletable record type.")
    return resource


def all_resources() -> tuple[DeletableResource, ...]:
    return _RESOURCES


def stage_label(resource: DeletableResource, doc: dict[str, Any]) -> str | None:
    if resource.stage_field is None:
        return None
    raw = doc.get(resource.stage_field)
    return str(raw).replace("_", " ").title() if raw else None


def record_code(resource: DeletableResource, doc: dict[str, Any]) -> str | None:
    return str(doc[resource.code_field]) if resource.code_field and doc.get(resource.code_field) else None


def record_summary(resource: DeletableResource, doc: dict[str, Any]) -> str | None:
    parts = [str(doc[f]) for f in resource.summary_fields if doc.get(f)]
    return " · ".join(parts) or None
