import json
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Form, Query, Response, UploadFile
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.config.database import get_database
from app.core.exceptions import ValidationError
from app.core.response import ApiResponse
from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.bulk_import.files import MAX_BYTES
from app.features.daily_operations import transfers, views
from app.features.daily_operations.schemas import (
    FollowUpInput,
    FollowUpUpdate,
    IssueInput,
    IssueUpdate,
)
from app.features.daily_operations.service import DailyOperationsService, public
from app.shared.audit_log import write_audit_log

router = APIRouter(prefix="/daily-operations", tags=["daily-operations"])
Actor = Annotated[User, Depends(get_current_active_user)]
Db = Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]
Kind = Literal["follow-ups", "issues"]


class Filters(BaseModel):
    page: int = 1
    page_size: int = 20
    search: str = ""
    status: str = ""
    employee: str = ""
    bank: str = ""
    loan_type: str = ""
    date_from: date | None = None
    date_to: date | None = None
    overdue: bool = False
    sort: str = "-date"
    old_days: int = 0


def filters(
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str, Query(max_length=200)] = "",
    status: Annotated[str, Query(max_length=100)] = "",
    employee: Annotated[str, Query(max_length=24)] = "",
    bank: Annotated[str, Query(max_length=200)] = "",
    loan_type: Annotated[str, Query(max_length=200)] = "",
    date_from: date | None = None,
    date_to: date | None = None,
    overdue: bool = False,
    sort: Annotated[str, Query(max_length=30)] = "-date",
    old_days: Annotated[int, Query(ge=0, le=36500)] = 0,
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
                if k in {"page", "page_size", "employee", "date_from", "date_to"}
            },
        )
    if kind == "progress":
        values.pop("overdue")
        if values["sort"] == "-date":
            values["sort"] = "-updated_at"
        return await views.progress(service, actor, **values)
    values.pop("old_days")
    return await service.list_records(kind, actor, **values)


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
            "assigned_to": "EMPLOYEE ID",
        },
        "issues": {
            "id": "Issue ID",
            "employee_id": "EMPLOYEE ID",
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
            "assigned_to": "EMPLOYEE ID",
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
    values = criteria.model_dump(exclude={"overdue"})
    if values["sort"] == "-date":
        values["sort"] = "-updated_at"
    return ApiResponse[dict[str, Any]].ok(
        await views.progress(DailyOperationsService(db), actor, **values)
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
            FollowUpInput.model_validate(payload.model_dump(exclude={"version"})),
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
