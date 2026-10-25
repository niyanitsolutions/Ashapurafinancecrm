"""Bounded previews and retry-safe, independent row commits. No uploaded files on disk."""

import hashlib
import io
import json
from datetime import date as CalendarDate
from datetime import timedelta
from typing import Any, Literal

from bson import ObjectId
from openpyxl import Workbook  # type: ignore[import-untyped]
from pydantic import BaseModel, Field, model_validator
from pydantic import ValidationError as SchemaError

from app.core.exceptions import AppError, ConflictError, NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.bulk_import.files import parse_file
from app.features.daily_operations.schemas import (
    FollowUpInput,
    IssueInput,
    ProgressActionInput,
    ProgressInput,
)
from app.features.daily_operations.service import DailyOperationsService
from app.features.daily_operations.views import SessionCorrection, correct_session
from app.features.loan_management.service import LoanCaseService
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now

Kind = Literal["follow-ups", "progress", "sessions", "issues"]
FOLLOW_COLUMNS = {
    "date": "DATE",
    "lead_id": "LEAD ID",
    "case_id": "LOAN CASE ID",
    "bank": "BANK / NBFCs",
    "status": "TODAY CASE STATUS",
    "remarks": "REMARKS",
    "remarks_date": "REMARKS DATE",
    "next_action": "NEXT ACTION",
    "due_date": "FOLLOW PENDING",
    "rejection_reason": "REJECTION REASON",
}
ISSUE_COLUMNS = {
    "date": "DATE",
    "inquiry": "INQUIRY OR ISSUE",
    "priority": "Priority",
    "assigned_to": "Assigned To",
    "status": "Status",
    "resolution_notes": "Resolution Notes",
}
PROGRESS_COLUMNS = {
    "case_id": "LOAN CASE ID",
    "date": "DATE",
    "next_action": "WHAT'S NEXT FOLLOW-UP TMROW",
    "due_date": "FOLLOW PENDING",
}


class CorrectionRow(SessionCorrection):
    family_id: str
    date: CalendarDate | None = None
    employee_name: str = ""


class FollowUpRow(FollowUpInput):
    record_id: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{24}$")
    version: int | None = Field(default=None, ge=1)
    loan_type: str = Field(default="", max_length=200)
    customer_name: str = Field(default="", max_length=200)
    customer_number: str = Field(default="", max_length=30)
    employee_name: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def update_requires_version(self) -> "FollowUpRow":
        if bool(self.record_id) != bool(self.version):
            raise ValueError("Updates require both RECORD ID and VERSION.")
        return self


class IssueRow(IssueInput):
    record_id: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{24}$")
    version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def update_requires_version(self) -> "IssueRow":
        if bool(self.record_id) != bool(self.version):
            raise ValueError("Updates require both RECORD ID and VERSION.")
        return self


class ProgressRow(ProgressInput):
    record_id: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{24}$")
    version: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def update_requires_version(self) -> "ProgressRow":
        if (self.record_id is None) != (self.version is None):
            raise ValueError("Updates require both RECORD ID and VERSION.")
        return self


READ_ONLY = {"loan_type", "customer_name", "customer_number", "employee_name"}
FOLLOW_COLUMNS.update(
    loan_type="LOAN TYPE",
    customer_name="CX NAME",
    customer_number="CX NUMBER",
    employee_name="EMPLOYEE NAME",
    record_id="RECORD ID",
    version="VERSION",
)
ISSUE_COLUMNS.update(record_id="RECORD ID", version="VERSION")
ISSUE_COLUMNS.update(employee_name="EMPLOYEE NAME")
PROGRESS_COLUMNS.update(
    customer_name="CX NAME",
    customer_number="CX NUMBER",
    loan_type="LOAN TYPE",
    bank="APPLIED BANK OR NBFC",
    status="TODAY CASE STAGE",
    employee_name="EMPLOYEE NAME",
    remarks="REMARKS",
    login_date="DATE OF LOGIN",
    approved_amount="APPROVED LOAN AMT",
    disbursed_amount="LOAN AMOUNT",
    disbursed_at="DATE OF DISBURSE",
    record_id="RECORD ID",
    version="VERSION",
)


MODELS: dict[str, type[BaseModel]] = {
    "follow-ups": FollowUpRow,
    "issues": IssueRow,
    "progress": ProgressRow,
    "sessions": CorrectionRow,
}


def row_key(actor: User, kind: str, values: dict[str, Any]) -> str:
    values = dict(values)
    if values.get("assigned_to") is None:
        values.pop("assigned_to", None)  # Preserve fingerprints from pre-manual-entry imports.
    if kind == "issues" and not values.get("employee_name"):
        values.pop("employee_name", None)
    return hashlib.sha256(
        json.dumps([actor.require_id(), kind, values], sort_keys=True, default=str).encode()
    ).hexdigest()


async def legacy_progress_row(
    service: DailyOperationsService, actor: User, kind: str, values: dict[str, Any]
) -> bool:
    # Old progress templates wrote follow-up actions rather than progress annotations.
    # Keep their durable fingerprints effective across this UI/data-model upgrade.
    keys = {"case_id", "date", "next_action", "due_date"}
    if (
        kind != "progress"
        or not values.get("case_id")
        or not {key for key, value in values.items() if value != ""}.issubset(keys)
    ):
        return False
    legacy = ProgressActionInput.model_validate({key: values[key] for key in keys if key in values})
    key = row_key(actor, kind, legacy.model_dump(mode="json"))
    return bool(
        await service.db.daily_follow_ups.find_one(
            {"$or": [{"import_key": key}, {"history.import_key": key}]}, {"_id": 1}
        )
    )


COLUMNS = {
    "follow-ups": FOLLOW_COLUMNS,
    "issues": ISSUE_COLUMNS,
    "progress": PROGRESS_COLUMNS,
    "sessions": {
        "date": "DATE",
        "employee_name": "EMPLOYEE NAME",
        "family_id": "SESSION FAMILY ID",
        "login_at": "LOGIN TIME",
        "logout_at": "LOGOUT TIME",
        "reason": "CORRECTION REASON",
        "version": "VERSION",
    },
}


def safe_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else text


def spreadsheet(headers: list[str], rows: list[list[Any]], format: str) -> bytes:
    if format == "csv":
        import csv

        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow([safe_cell(h) for h in headers])
        writer.writerows([[safe_cell(value) for value in row] for row in rows])
        return buffer.getvalue().encode("utf-8-sig")
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Daily Operations"
    sheet.append(headers)
    for row in rows:
        sheet.append([safe_cell(value) for value in row])
    for row in sheet:
        for cell in row:
            if isinstance(cell.value, str):
                cell.data_type = "s"
    sheet.freeze_panes = "A2"
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


async def progress_payload(
    service: DailyOperationsService, actor: User, row: ProgressActionInput
) -> FollowUpInput:
    case = await LoanCaseService(service.db).get_case(row.case_id, actor)
    application = await service.db.applications.find_one(
        {"_id": ObjectId(case.application_id), "is_deleted": False}
    )
    if not application or not application.get("lead_id"):
        raise ValidationError(
            "Progress action imports require an existing linked lead; use Loan Management for lead-less cases."
        )
    details = case.loan_details
    bank = (details.bank_nbfc_name or details.preferred_bank_name) if details else None
    if not bank:
        raise ValidationError(
            "Record the applied bank in Loan Management before importing follow-up actions."
        )
    return FollowUpInput(
        date=row.date,
        lead_id=application["lead_id"],
        case_id=row.case_id,
        bank=bank,
        status="NEXT FOLLOW UP",
        remarks_date=row.date,
        next_action=row.next_action,
        due_date=row.due_date,
    )


async def validate_row(
    service: DailyOperationsService,
    kind: str,
    actor: User,
    values: dict[str, Any],
    allow_updates: bool = False,
) -> BaseModel:
    if any(
        str(value).lstrip().startswith(("=", "+", "-", "@")) for value in values.values() if value
    ):
        raise ValidationError("Formula-prefixed cells are not supported.")
    model = MODELS[kind].model_validate(
        {key: value for key, value in values.items() if value != ""}
    )
    old = None
    if isinstance(model, (FollowUpRow, IssueRow, ProgressRow)):
        if model.record_id:
            if not allow_updates:
                raise ValidationError(
                    "Updates are disabled. Explicitly enable updates and preview again."
                )
            await service.authorize(actor, kind, "edit")
            old = await service.get(kind, model.record_id, actor)
            # A retry of an already committed row is allowed past the version check.
            key = row_key(actor, kind, model.model_dump(mode="json"))
            processed = any(event.get("import_key") == key for event in old.get("history", []))
            if old["version"] != model.version and not processed:
                raise ConflictError("VERSION changed. Export or reload the record before updating.")
        else:
            await service.authorize(actor, kind, "create")
    if isinstance(model, FollowUpInput):
        derived = await service.validate_follow_up(model, actor)
        if isinstance(model, FollowUpRow) and (model.lead_id or model.case_id):
            for field in READ_ONLY - {"employee_name"}:
                if getattr(model, field) and getattr(model, field) != derived[field]:
                    raise ValidationError(
                        f"{FOLLOW_COLUMNS[field]} is read-only and must match the linked CRM record."
                    )
    elif isinstance(model, IssueInput):
        await service.validate_issue(model, actor, old)
    elif isinstance(model, ProgressInput):
        from app.features.daily_operations.entries import progress_data

        await progress_data(service, actor, model)
    elif isinstance(model, ProgressActionInput):
        await service.authorize(actor, "follow-ups", "create")
        await service.validate_follow_up(await progress_payload(service, actor, model), actor)
    else:
        if actor.role != "owner":
            from app.core.exceptions import ForbiddenError

            raise ForbiddenError("Only an Owner can import session corrections.")
        await service.authorize(actor, "sessions", "edit")
        assert isinstance(model, CorrectionRow)
        session = await service.db.sessions.find_one(
            {"family_id": model.family_id, "is_deleted": False}
        )
        employee = (
            await service.db.employees.find_one(
                {"user_id": session["user_id"], "is_deleted": False}
            )
            if session
            else None
        )
        if not session or not employee:
            raise ValidationError("Employee session family not found.")
        if model.employee_name and model.employee_name != employee["display_name"]:
            raise ValidationError("EMPLOYEE NAME must match the existing session owner.")
        if model.date:
            from app.utils.datetime import to_ist

            if model.date != to_ist(model.login_at).date():
                raise ValidationError("DATE must match the corrected login date in Asia/Kolkata.")
    return model


def errors(exc: Exception, kind: str) -> list[dict[str, str]]:
    if isinstance(exc, SchemaError):
        return [
            {
                "column": COLUMNS[kind].get(str(e["loc"][0]), "ROW") if e["loc"] else "ROW",
                "message": e["msg"],
            }
            for e in exc.errors(include_input=False, include_url=False)
        ]
    return [
        {
            "column": "ROW",
            "message": exc.message if isinstance(exc, AppError) else "Row could not be processed.",
        }
    ]


async def preview(
    service: DailyOperationsService,
    kind: str,
    actor: User,
    content: bytes,
    filename: str,
    content_type: str | None,
    mapping: dict[str, str],
    allow_updates: bool = False,
) -> dict[str, Any]:
    await service.authorize(actor, kind, "import")
    await service.authorize(actor, kind)
    from starlette.concurrency import run_in_threadpool

    rows = await run_in_threadpool(
        parse_file,
        content,
        filename,
        content_type,
        kind,
        model=MODELS[kind],
        columns=COLUMNS[kind],
        column_mapping=mapping,
    )
    digest = hashlib.sha256(
        actor.require_id().encode()
        + kind.encode()
        + content
        + json.dumps(mapping, sort_keys=True).encode()
        + str(allow_updates).encode()
    ).hexdigest()
    existing = await service.db.daily_imports.find_one({"_id": digest})
    if existing and existing["expires_at"] > utc_now():
        return {
            "id": digest,
            "rows": existing["rows"],
            "policy": "Independent atomic rows; updates require opt-in, RECORD ID and VERSION. Session imports correct existing records with version checks.",
        }
    results = []
    seen: set[str] = set()
    for number, values in rows:
        row_errors = []
        duplicate = False
        try:
            model = await validate_row(service, kind, actor, values, allow_updates)
            key = row_key(actor, kind, model.model_dump(mode="json"))
            from app.features.daily_operations.service import COLLECTIONS

            collection = service.db[COLLECTIONS.get(kind, "daily_follow_ups")]
            duplicate = key in seen or bool(
                await collection.find_one(
                    {"$or": [{"import_key": key}, {"history.import_key": key}]}, {"_id": 1}
                )
            )
            duplicate = duplicate or await legacy_progress_row(service, actor, kind, values)
            if kind == "sessions":
                duplicate = duplicate or bool(
                    await service.db.session_corrections.find_one(
                        {"history.import_key": key}, {"_id": 1}
                    )
                )
            seen.add(key)
        except (AppError, SchemaError) as exc:
            row_errors = errors(exc, kind)
        results.append(
            {"row": number, "values": values, "errors": row_errors, "duplicate": duplicate}
        )
    batch = {
        "_id": digest,
        "kind": kind,
        "actor_id": actor.require_id(),
        "rows": results,
        "expires_at": utc_now() + timedelta(minutes=30),
        "created_at": utc_now(),
        "allow_updates": allow_updates,
    }
    await service.db.daily_imports.replace_one({"_id": digest}, batch, upsert=True)
    await write_audit_log(
        service.db,
        event_type="daily_import_preview",
        user_id=actor.require_id(),
        metadata={"kind": kind, "batch_id": digest, "rows": len(rows)},
    )
    return {
        "id": digest,
        "rows": results,
        "policy": "Independent atomic rows; updates require opt-in, RECORD ID and VERSION. Session imports correct existing records with version checks.",
    }


async def commit(service: DailyOperationsService, actor: User, batch_id: str) -> dict[str, Any]:
    batch = await service.db.daily_imports.find_one(
        {"_id": batch_id, "actor_id": actor.require_id()}
    )
    if not batch or batch["expires_at"] <= utc_now():
        raise NotFoundError("Preview expired. Upload the file again.")
    kind = batch["kind"]
    await service.authorize(actor, kind, "import")
    await service.authorize(actor, kind)
    summary: dict[str, Any] = {
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "rejected": 0,
        "errors": [],
    }
    for row in batch["rows"]:
        try:
            model = await validate_row(
                service, kind, actor, row["values"], batch.get("allow_updates", False)
            )
            key = row_key(actor, kind, model.model_dump(mode="json"))
            if await legacy_progress_row(service, actor, kind, row["values"]):
                summary["skipped"] += 1
                continue
            destination = kind
            if kind == "sessions":
                assert isinstance(model, CorrectionRow)
                # CAS version plus a durable marker IN the correction document makes a
                # process interruption between row mutation and summary persistence safe.
                correction = await service.db.session_corrections.find_one(
                    {"_id": model.family_id, "history.import_key": key}
                )
                if correction:
                    summary["skipped"] += 1
                    continue
                await correct_session(
                    service,
                    actor,
                    model.family_id,
                    SessionCorrection.model_validate(
                        model.model_dump(exclude={"family_id", "date", "employee_name"})
                    ),
                    import_key=key,
                )
                summary["updated"] += 1
            else:
                if isinstance(model, ProgressActionInput):
                    model = await progress_payload(service, actor, model)
                assert isinstance(model, (FollowUpInput, IssueInput, ProgressInput))
                from app.features.daily_operations.service import COLLECTIONS

                collection = service.db[COLLECTIONS[destination]]
                if await collection.find_one(
                    {"$or": [{"import_key": key}, {"history.import_key": key}]}, {"_id": 1}
                ):
                    summary["skipped"] += 1
                    continue
                try:
                    record_id = (
                        model.record_id
                        if isinstance(model, (FollowUpRow, IssueRow, ProgressRow))
                        else None
                    )
                    version = (
                        model.version
                        if isinstance(model, (FollowUpRow, IssueRow, ProgressRow))
                        else None
                    )
                    schemas: dict[str, type[FollowUpInput | IssueInput | ProgressInput]] = {
                        "issues": IssueInput,
                        "follow-ups": FollowUpInput,
                        "progress": ProgressInput,
                    }
                    schema = schemas[destination]
                    values_to_save = model.model_dump(exclude={"record_id", "version"})
                    if isinstance(model, ProgressRow) and "status" not in model.model_fields_set:
                        values_to_save.pop("status", None)
                    payload = schema.model_validate(values_to_save)
                    await service.save(
                        destination, payload, actor, record_id, version, import_key=key
                    )
                    summary["updated" if record_id else "inserted"] += 1
                except ConflictError:
                    if await collection.find_one(
                        {"$or": [{"import_key": key}, {"history.import_key": key}]}, {"_id": 1}
                    ):
                        summary["skipped"] += 1
                    else:
                        raise
        except (AppError, SchemaError) as exc:
            summary["rejected"] += 1
            summary["errors"].append({"row": row["row"], "errors": errors(exc, kind)})
    await write_audit_log(
        service.db,
        event_type="daily_import_commit",
        user_id=actor.require_id(),
        metadata={
            "kind": kind,
            "batch_id": batch_id,
            **{k: v for k, v in summary.items() if k != "errors"},
        },
    )
    return summary
