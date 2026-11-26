import json
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Form, Query, Response, UploadFile
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from app.config.database import get_database
from app.core.exceptions import ValidationError
from app.core.response import ApiResponse
from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.bulk_import.files import MAX_BYTES
from app.features.daily_operations import entries, transfers, views
from app.features.daily_operations.bank_options import BankEdit, BankName, BankOptions
from app.features.daily_operations.linked import OpenLinkedRequest, open_linked
from app.features.daily_operations.loan_options import LoanOptions
from app.features.daily_operations.schemas import (
    DeleteRecord,
    FollowUpInput,
    FollowUpUpdate,
    IssueInput,
    IssueUpdate,
    ProgressInput,
    ProgressUpdate,
)
from app.features.daily_operations.service import DailyOperationsService, public
from app.features.daily_operations.status_options import (
    OptionEdit,
    OptionName,
    OptionVersion,
    StatusOptions,
)
from app.shared.audit_log import write_audit_log

router = APIRouter(prefix="/daily-operations", tags=["daily-operations"])
Actor = Annotated[User, Depends(get_current_active_user)]
Db = Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]
Kind = Literal["follow-ups", "issues"]


class Filters(BaseModel):
    page: int = 1
    page_size: int = 200
    search: str = ""
    status: str = ""
    employee: str = ""
    employee_name: str = ""
    bank: str = ""
    loan_type: str = ""
    date_from: date | None = None
    date_to: date | None = None
    overdue: bool = False
    workflow: Literal["normal", "reeligible"] = "normal"
    sort: str = "-date"
    old_days: int = 0
    month: str | None = None


def filters(
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 200,
    search: Annotated[str, Query(max_length=200)] = "",
    status: Annotated[str, Query(max_length=100)] = "",
    employee: Annotated[str, Query(max_length=24)] = "",
    employee_name: Annotated[str, Query(max_length=200)] = "",
    bank: Annotated[str, Query(max_length=200)] = "",
    loan_type: Annotated[str, Query(max_length=200)] = "",
    date_from: date | None = None,
    date_to: date | None = None,
    overdue: bool = False,
    workflow: Literal["normal", "reeligible"] = "normal",
    sort: Annotated[str, Query(max_length=30)] = "-date",
    old_days: Annotated[int, Query(ge=0, le=36500)] = 0,
    month: Annotated[str | None, Query(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")] = None,
) -> Filters:
    return Filters(**locals())


async def list_area(
    service: DailyOperationsService, kind: str, actor: User, criteria: Filters
) -> dict[str, Any]:
    values = criteria.model_dump()
    if kind == "sessions":
        return await views.sessions(
            service,
            actor,
            **{
                k: v
                for k, v in values.items()
                if k
                in {
                    "page",
                    "page_size",
                    "employee",
                    "employee_name",
                    "date_from",
                    "date_to",
                    "month",
                }
            },
        )
    values.pop("month")
    if kind == "progress":
        values.pop("workflow")
        values.pop("overdue")
        if values["sort"] == "-date":
            values["sort"] = "-updated_at"
        return await views.progress(service, actor, **values)
    values.pop("old_days")
    return await service.list_records(kind, actor, **values)


@router.get("/lookups")
async def lookups(
    actor: Actor,
    db: Db,
    search: Annotated[str, Query(max_length=200)] = "",
    include_crm: bool = False,
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse[dict[str, Any]].ok(
        await entries.lookups(DailyOperationsService(db), actor, search, include_crm)
    )


@router.get("/follow-up-identities")
async def follow_up_identities(
    actor: Actor, db: Db, search: str = Query(default="", max_length=120)
) -> ApiResponse[Any]:
    from app.features.daily_operations.resolution import search as resolve

    return ApiResponse.ok(await resolve(DailyOperationsService(db), actor, search))


@router.post("/linked-follow-up")
async def linked_follow_up(payload: OpenLinkedRequest, actor: Actor, db: Db) -> ApiResponse[dict[str, Any]]:
    return ApiResponse[dict[str, Any]].ok(await open_linked(DailyOperationsService(db), payload, actor))


@router.post("/progress")
async def create_progress(
    payload: ProgressInput, actor: Actor, db: Db
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse[dict[str, Any]].ok(
        await entries.save_progress(DailyOperationsService(db), actor, payload)
    )


@router.patch("/progress/{record_id}")
async def update_progress(
    record_id: str, payload: ProgressUpdate, actor: Actor, db: Db
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse[dict[str, Any]].ok(
        await entries.save_progress(
            DailyOperationsService(db),
            actor,
            ProgressInput.model_validate(payload.model_dump(exclude={"version"})),
            record_id,
            payload.version,
        )
    )


@router.delete("/{area}/{record_id}")
async def delete_record(
    area: transfers.Kind, record_id: str, payload: DeleteRecord, actor: Actor, db: Db
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse[dict[str, Any]].ok(
        await entries.remove(DailyOperationsService(db), actor, area, record_id, payload)
    )


@router.get("/transfers/{kind}/template")
async def template(
    kind: transfers.Kind, actor: Actor, db: Db, format: Literal["csv", "xlsx"] = "xlsx"
) -> Response:
    await DailyOperationsService(db).authorize(actor, kind, "import")
    content = await run_in_threadpool(
        transfers.spreadsheet, list(transfers.COLUMNS[kind].values()), [], format
    )
    return download(content, f"{kind}-template.{format}", format)


@router.post("/transfers/{kind}/preview")
async def preview(
    kind: transfers.Kind,
    actor: Actor,
    db: Db,
    file: UploadFile,
    mapping: Annotated[str, Form(max_length=8000)] = "{}",
    allow_updates: Annotated[bool, Form()] = False,
) -> ApiResponse[dict[str, Any]]:
    service = DailyOperationsService(db)
    await service.authorize(actor, kind, "import")
    try:
        columns = json.loads(mapping)
        if not isinstance(columns, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in columns.items()
        ):
            raise ValueError()
    except (ValueError, TypeError):
        raise ValidationError(
            "Column mapping must be a JSON object of source heading to destination field."
        ) from None
    content = await file.read(MAX_BYTES + 1)
    try:
        result = await transfers.preview(
            service,
            kind,
            actor,
            content,
            file.filename or "",
            file.content_type,
            columns,
            allow_updates,
        )
    finally:
        await file.close()
    return ApiResponse[dict[str, Any]].ok(result)


class Confirm(BaseModel):
    confirmed: Literal[True]


@router.post("/transfers/{batch_id}/confirm")
async def confirm(
    batch_id: str, payload: Confirm, actor: Actor, db: Db
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse[dict[str, Any]].ok(
        await transfers.commit(DailyOperationsService(db), actor, batch_id)
    )


def download(content: bytes, name: str, format: str) -> Response:
    return Response(
        content,
        media_type="text/csv"
        if format == "csv"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/{kind}/export")
async def export(
    kind: transfers.Kind,
    actor: Actor,
    db: Db,
    criteria: Annotated[Filters, Depends(filters)],
    format: Literal["csv", "xlsx"] = "csv",
) -> Response:
    service = DailyOperationsService(db)
    await service.authorize(actor, kind, "export")
    criteria = criteria.model_copy(update={"page": 1, "page_size": 501})
    result = await list_area(service, kind, actor, criteria)
    if result["total"] > 500:
        raise ValidationError("Export is limited to 500 rows. Narrow the date range or filters.")
    extra = {
        "follow-ups": {
            "loan_type": "LOAN TYPE",
            "customer_name": "CX NAME",
            "customer_number": "CX NUMBER",
            "employee_name": "EMPLOYEE NAME",
        },
        "issues": {
            "id": "Issue ID",
            "employee_name": "EMPLOYEE NAME",
            "created_by": "Created By",
            "updated_by": "Updated By",
            "created_at": "Created At",
            "updated_at": "Updated At",
            "resolved_at": "Resolved Date",
        },
        "progress": {
            "login_date": "DATE OF LOGIN",
            "bank": "APPLIED BANK OR NBFC",
            "lead_id": "LEAD ID",
            "customer_name": "CX NAME",
            "customer_number": "CX NUMBER",
            "status": "TODAY CASE STAGE",
            "approved_amount": "APPROVED LOAN AMT",
            "updated_at": "UPDATE DATE",
            "age_days": "OLD CASES UNDER PROGRESS",
            "disbursed_at": "DATE OF DISBURSE",
            "disbursed_amount": "LOAN AMOUNT",
            "employee_name": "EMPLOYEE NAME",
            "source": "RECORD TYPE",
        },
        "sessions": {
            "date": "DATE",
            "employee_name": "EMPLOYEE NAME",
            "id": "SESSION FAMILY ID",
            "recorded_seconds": "RECORDED SECONDS",
            "corrected": "CORRECTED",
        },
    }
    columns = {**transfers.COLUMNS[kind], **extra[kind]}
    items = result["items"]
    if kind == "follow-ups":
        items = [{**item, "status": item.get("status_display") or item["status"]} for item in items]
    if kind == "sessions":
        columns = {
            "date": "DATE",
            "employee_name": "EMPLOYEE NAME",
            "id": "DAILY SUMMARY ID",
            "login_at": "LOGIN TIME",
            "logout_at": "LOGOUT TIME",
            "recorded_seconds": "RECORDED SECONDS",
            "status": "STATUS",
        }
    content = await run_in_threadpool(
        transfers.spreadsheet,
        list(columns.values()),
        [
            [
                item.get(
                    k,
                    item.get("id")
                    if k in {"record_id", "family_id"}
                    else item.get("correction_version")
                    if k == "version"
                    else None,
                )
                for k in columns
            ]
            for item in items
        ],
        format,
    )
    await write_audit_log(
        db,
        event_type="daily_export",
        user_id=actor.require_id(),
        metadata={"kind": kind, "rows": len(items)},
    )
    return download(content, f"{kind}.{format}", format)


@router.get("/progress")
async def progress(
    actor: Actor,
    db: Db,
    criteria: Annotated[Filters, Depends(filters)],
) -> ApiResponse[dict[str, Any]]:
    values = criteria.model_dump(exclude={"overdue", "month", "workflow"})
    if values["sort"] == "-date":
        values["sort"] = "-updated_at"
    return ApiResponse[dict[str, Any]].ok(
        await views.progress(DailyOperationsService(db), actor, **values)
    )


@router.get("/progress/{record_id}")
async def get_progress(record_id: str, actor: Actor, db: Db) -> ApiResponse[dict[str, Any]]:
    return ApiResponse[dict[str, Any]].ok(
        public(await entries.get_progress(DailyOperationsService(db), actor, record_id))
    )


@router.get("/sessions")
async def sessions(
    actor: Actor, db: Db, criteria: Annotated[Filters, Depends(filters)]
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse[dict[str, Any]].ok(
        await list_area(DailyOperationsService(db), "sessions", actor, criteria)
    )


@router.post("/sessions/{family_id}/correction")
async def correction(
    family_id: str, payload: views.SessionCorrection, actor: Actor, db: Db
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse[dict[str, Any]].ok(
        await views.correct_session(DailyOperationsService(db), actor, family_id, payload)
    )


@router.post("/follow-ups")
async def create_follow_up(
    payload: FollowUpInput, actor: Actor, db: Db
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse[dict[str, Any]].ok(
        await DailyOperationsService(db).save("follow-ups", payload, actor)
    )


@router.patch("/follow-ups/{record_id}")
async def update_follow_up(
    record_id: str, payload: FollowUpUpdate, actor: Actor, db: Db
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse[dict[str, Any]].ok(
        await DailyOperationsService(db).save(
            "follow-ups",
            FollowUpInput.model_validate(
                payload.model_dump(exclude={"version"}, exclude_unset=True)
            ),
            actor,
            record_id,
            payload.version,
        )
    )


@router.post("/issues")
async def create_issue(payload: IssueInput, actor: Actor, db: Db) -> ApiResponse[dict[str, Any]]:
    return ApiResponse[dict[str, Any]].ok(
        await DailyOperationsService(db).save("issues", payload, actor)
    )


@router.patch("/issues/{record_id}")
async def update_issue(
    record_id: str, payload: IssueUpdate, actor: Actor, db: Db
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse[dict[str, Any]].ok(
        await DailyOperationsService(db).save(
            "issues",
            IssueInput.model_validate(payload.model_dump(exclude={"version"})),
            actor,
            record_id,
            payload.version,
        )
    )


@router.get("/bank-options")
async def bank_options(actor: Actor, db: Db, include_archived: bool = False) -> ApiResponse[Any]:
    return ApiResponse.ok(
        await BankOptions(DailyOperationsService(db)).list(actor, include_archived)
    )


@router.post("/bank-options")
async def create_bank_option(payload: BankName, actor: Actor, db: Db) -> ApiResponse[Any]:
    return ApiResponse.ok(
        await BankOptions(DailyOperationsService(db)).change(actor, name=payload.name)
    )


@router.patch("/bank-options/{option_id}")
async def edit_bank_option(
    option_id: str, payload: BankEdit, actor: Actor, db: Db
) -> ApiResponse[Any]:
    return ApiResponse.ok(
        await BankOptions(DailyOperationsService(db)).change(
            actor, name=payload.name, option_id=option_id, version=payload.version
        )
    )


@router.post("/bank-options/{option_id}/archive")
async def archive_bank_option(
    option_id: str, payload: OptionVersion, actor: Actor, db: Db
) -> ApiResponse[Any]:
    return ApiResponse.ok(
        await BankOptions(DailyOperationsService(db)).change(
            actor, option_id=option_id, version=payload.version, active=False
        )
    )


@router.post("/bank-options/{option_id}/restore")
async def restore_bank_option(
    option_id: str, payload: OptionVersion, actor: Actor, db: Db
) -> ApiResponse[Any]:
    return ApiResponse.ok(
        await BankOptions(DailyOperationsService(db)).change(
            actor, option_id=option_id, version=payload.version, active=True
        )
    )


@router.get("/loan-type-options")
async def loan_type_options(
    actor: Actor, db: Db, include_archived: bool = False
) -> ApiResponse[Any]:
    return ApiResponse.ok(
        await LoanOptions(DailyOperationsService(db)).list(actor, include_archived)
    )


@router.post("/loan-type-options")
async def create_loan_type_option(payload: BankName, actor: Actor, db: Db) -> ApiResponse[Any]:
    return ApiResponse.ok(
        await LoanOptions(DailyOperationsService(db)).change(actor, name=payload.name)
    )


@router.patch("/loan-type-options/{option_id}")
async def edit_loan_type_option(
    option_id: str, payload: BankEdit, actor: Actor, db: Db
) -> ApiResponse[Any]:
    return ApiResponse.ok(
        await LoanOptions(DailyOperationsService(db)).change(
            actor, name=payload.name, option_id=option_id, version=payload.version
        )
    )


@router.post("/loan-type-options/{option_id}/archive")
async def archive_loan_type_option(
    option_id: str, payload: OptionVersion, actor: Actor, db: Db
) -> ApiResponse[Any]:
    return ApiResponse.ok(
        await LoanOptions(DailyOperationsService(db)).change(
            actor, option_id=option_id, version=payload.version, active=False
        )
    )


@router.post("/loan-type-options/{option_id}/restore")
async def restore_loan_type_option(
    option_id: str, payload: OptionVersion, actor: Actor, db: Db
) -> ApiResponse[Any]:
    return ApiResponse.ok(
        await LoanOptions(DailyOperationsService(db)).change(
            actor, option_id=option_id, version=payload.version, active=True
        )
    )


@router.get("/follow-up-status-options")
async def status_options(actor: Actor, db: Db, include_archived: bool = False) -> ApiResponse[Any]:
    return ApiResponse.ok(
        await StatusOptions(DailyOperationsService(db)).list(actor, include_archived)
    )


@router.post("/follow-up-status-options")
async def create_status_option(payload: OptionName, actor: Actor, db: Db) -> ApiResponse[Any]:
    return ApiResponse.ok(
        await StatusOptions(DailyOperationsService(db)).change(actor, **payload.model_dump())
    )


@router.patch("/follow-up-status-options/{option_id}")
async def rename_status_option(
    option_id: str, payload: OptionEdit, actor: Actor, db: Db
) -> ApiResponse[Any]:
    return ApiResponse.ok(
        await StatusOptions(DailyOperationsService(db)).change(
            actor,
            option_id=option_id,
            version=payload.version,
            **payload.model_dump(exclude={"version"}, exclude_unset=True),
        )
    )


@router.post("/follow-up-status-options/{option_id}/archive")
async def archive_status_option(
    option_id: str, payload: OptionVersion, actor: Actor, db: Db
) -> ApiResponse[Any]:
    return ApiResponse.ok(
        await StatusOptions(DailyOperationsService(db)).change(
            actor, option_id=option_id, version=payload.version, active=False
        )
    )


@router.post("/follow-up-status-options/{option_id}/restore")
async def restore_status_option(
    option_id: str, payload: OptionVersion, actor: Actor, db: Db
) -> ApiResponse[Any]:
    return ApiResponse.ok(
        await StatusOptions(DailyOperationsService(db)).change(
            actor, option_id=option_id, version=payload.version, active=True
        )
    )


class IdentityDecision(BaseModel):
    application_id: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{24}$")
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    version: int = Field(ge=1)
    customer_id: str = Field(pattern=r"^[a-fA-F0-9]{24}$")
    preview_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=5, max_length=1000)
    confirmed: Literal[True]


class IdentityRollback(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    version: int = Field(ge=1)
    event_id: str = Field(pattern=r"^[a-fA-F0-9]{24}$")
    reason: str = Field(min_length=5, max_length=1000)
    confirmed: Literal[True]


class IdentityReviewDisposition(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    version: int = Field(ge=1)
    decision: Literal["reject_suggestion", "leave_standalone", "manual_review"]
    reason: str = Field(min_length=5, max_length=1000)


@router.post("/identity-review/{record_id}/decision")
async def identity_review_decision(
    record_id: str, body: IdentityReviewDisposition, actor: Actor, db: Db
) -> ApiResponse[Any]:
    from bson import ObjectId

    from app.core.exceptions import ConflictError, ForbiddenError
    from app.shared.audit_log import AuditLog

    if actor.role != "owner":
        raise ForbiddenError("Owner review is required.")
    if not ObjectId.is_valid(record_id):
        raise ValidationError("Invalid record ID.")
    async with await db.client.start_session() as session, session.start_transaction():
        row = await db.daily_follow_ups.find_one(
            {"_id": ObjectId(record_id), "version": body.version, "is_deleted": False},
            session=session,
        )
        if not row:
            raise ConflictError("Record changed. Generate a fresh preview.")
        if body.decision == "manual_review":
            from app.utils.datetime import utc_now

            if len(row.get("history", [])) >= 250:
                raise ConflictError("History limit reached; review archival first.")
            changed = await db.daily_follow_ups.update_one(
                {"_id": row["_id"], "version": body.version},
                {
                    "$set": {
                        "identity_review_state": "pending",
                        "updated_by": actor.require_id(),
                        "updated_at": utc_now(),
                    },
                    "$inc": {"version": 1},
                    "$push": {
                        "history": {
                            "source": "identity_review",
                            "actor_id": actor.require_id(),
                            "at": utc_now(),
                            "before": {"identity_review_state": row.get("identity_review_state")},
                            "after": {"identity_review_state": "pending"},
                            "reason": body.reason,
                        }
                    },
                },
                session=session,
            )
            if not changed.modified_count:
                raise ConflictError("Record changed. Generate a fresh preview.")
        audit = AuditLog(
            event_type="daily_identity_review_decision",
            user_id=actor.require_id(),
            metadata={
                "record_id": record_id,
                "version": body.version,
                "decision": body.decision,
                "reason": body.reason,
            },
        )
        await db.audit_logs.insert_one(
            audit.model_dump(by_alias=True, exclude={"id"}), session=session
        )
    return ApiResponse.ok(
        {"decision": body.decision, "record_unchanged": body.decision != "manual_review"}
    )


@router.get("/identity-review/duplicates")
async def identity_duplicates(actor: Actor, db: Db) -> ApiResponse[Any]:
    from app.features.daily_operations.duplicate_report import preview

    return ApiResponse.ok(await preview(db, actor))


@router.get("/identity-review/preview")
async def identity_preview(
    actor: Actor, db: Db, after: str | None = None, limit: int = Query(default=50, ge=1, le=100)
) -> ApiResponse[Any]:
    from app.features.daily_operations.identity import preview

    return ApiResponse.ok(await preview(db, actor, after, limit))


@router.post("/identity-review/{record_id}/link")
async def identity_link(
    record_id: str, body: IdentityDecision, actor: Actor, db: Db
) -> ApiResponse[Any]:
    from bson import ObjectId

    from app.features.daily_operations.identity import apply_link

    if not ObjectId.is_valid(record_id):
        raise ValidationError("Invalid record ID.")
    return ApiResponse.ok(await apply_link(db, actor, record_id, body))


@router.post("/identity-review/{record_id}/rollback")
async def identity_rollback(
    record_id: str, body: IdentityRollback, actor: Actor, db: Db
) -> ApiResponse[Any]:
    from bson import ObjectId

    from app.features.daily_operations.identity import rollback_link

    if not ObjectId.is_valid(record_id):
        raise ValidationError("Invalid record ID.")
    return ApiResponse.ok(await rollback_link(db, actor, record_id, body))


@router.get("/{kind}")
async def records(
    kind: Kind, actor: Actor, db: Db, criteria: Annotated[Filters, Depends(filters)]
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse[dict[str, Any]].ok(
        await list_area(DailyOperationsService(db), kind, actor, criteria)
    )


@router.get("/{kind}/{record_id}")
async def detail(kind: Kind, record_id: str, actor: Actor, db: Db) -> ApiResponse[dict[str, Any]]:
    return ApiResponse[dict[str, Any]].ok(
        public(await DailyOperationsService(db).get(kind, record_id, actor))
    )
