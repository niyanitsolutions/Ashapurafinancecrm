from datetime import date
from io import BytesIO
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from app.config.database import get_database
from app.config.redis import get_redis
from app.config.storage import get_storage_config
from app.core.exceptions import AppError, ValidationError
from app.core.response import ApiResponse
from app.features.access_control.permission_engine import require_permission
from app.features.auth.models import User
from app.features.employee.dependencies import require_owner
from app.features.invoices.pdf import render_invoice
from app.features.invoices.revisions import InvoiceRevisionService
from app.features.invoices.schemas import (
    ArchiveInput,
    CancelInput,
    CopyInput,
    DraftDeleteInput,
    InvoiceConfig,
    InvoiceInput,
    ReissueInput,
    RevisionInput,
    StatusInput,
)
from app.features.invoices.service import InvoiceService, payment_qr
from app.services.storage.client import generate_presigned_download_url, get_s3_client
from app.utils.datetime import utc_now

router = APIRouter(tags=["invoices"])


def service(db=Depends(get_database), redis=Depends(get_redis)):
    return InvoiceService(db, redis)


Service = Annotated[InvoiceService, Depends(service)]
View = Annotated[User, require_permission("invoices", "invoices", "view")]
Create = Annotated[User, require_permission("invoices", "invoices", "create")]
Edit = Annotated[User, require_permission("invoices", "invoices", "edit")]
Owner = Annotated[User, Depends(require_owner)]


@router.get("/invoice-settings")
async def settings(svc: Service, actor: Owner):
    company = await svc.snapshot()
    raw = await svc.db.company_settings.find_one({"singleton_key": "default"})
    config = InvoiceConfig.model_validate(raw.get("invoice_config", {}))
    urls = {}
    for name, key in [("logo", company["logo_s3_key"]), ("signature", config.signature_s3_key)]:
        urls[name] = generate_presigned_download_url(key) if key else None
    return ApiResponse.ok(
        {"config": config.model_dump(mode="json"), "company": company, "assets": urls}
    )


@router.put("/invoice-settings")
async def save_settings(payload: InvoiceConfig, svc: Service, actor: Owner):
    if payload.signature_s3_key and not payload.signature_s3_key.startswith(
        "company/invoice-signature/"
    ):
        raise ValidationError("Invalid signature image reference.")
    company = await svc.company.get_or_create()
    previous = InvoiceConfig.model_validate(company.invoice_config)
    if payload.same_number_reissue_enabled and not payload.same_number_policy_reason.strip():
        raise ValidationError("An accounting-owner policy approval reason is required.")
    policy_changed = (
        payload.same_number_reissue_enabled != previous.same_number_reissue_enabled
        or payload.same_number_policy_reason != previous.same_number_policy_reason
    )
    payload.same_number_policy_approved_by = (
        actor.require_id()
        if policy_changed and payload.same_number_reissue_enabled
        else previous.same_number_policy_approved_by
    )
    payload.same_number_policy_approved_at = (
        utc_now()
        if policy_changed and payload.same_number_reissue_enabled
        else previous.same_number_policy_approved_at
    )
    await svc.company.update(
        company.require_id(),
        {"invoice_config": payload.model_dump(mode="json")},
        updated_by=actor.require_id(),
    )
    await svc.audit(
        actor,
        "reissue_policy_updated" if policy_changed else "settings_updated",
        enabled=payload.same_number_reissue_enabled,
        reason=payload.same_number_policy_reason,
    )
    return ApiResponse.ok(payload.model_dump(mode="json"))


@router.post("/invoice-settings/signature")
async def upload_signature(svc: Service, actor: Owner, file: Annotated[UploadFile, File()]):
    data = await file.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise ValidationError("Signature must be at most 2 MB.")
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format != "PNG" or max(image.size) > 4096:
                raise ValidationError("Upload a PNG signature up to 4096 pixels.")
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationError("Invalid PNG image.") from exc
    key = f"company/invoice-signature/{uuid4().hex}.png"
    await run_in_threadpool(
        get_s3_client().put_object,
        Bucket=get_storage_config().bucket_name,
        Key=key,
        Body=data,
        ContentType="image/png",
    )
    await svc.audit(actor, "signature_uploaded")
    return ApiResponse.ok({"s3_key": key, "preview_url": generate_presigned_download_url(key)})


@router.get("/invoices/defaults")
async def defaults(svc: Service, actor: View):
    return ApiResponse.ok(await svc.snapshot())


@router.get("/invoices/customers")
async def customers(svc: Service, actor: View, search: str = Query(default="", max_length=150)):
    rows = await svc.customer_options(actor, search)
    return ApiResponse.ok(
        [
            {
                "id": row.require_id(),
                "name": row.full_name,
                "phone": row.mobile,
                "email": row.email or "",
                "address": row.address.model_dump() if row.address else {},
            }
            for row in rows
        ]
    )


@router.post("/invoices/preview")
async def preview(payload: InvoiceInput, svc: Service, actor: View):
    return ApiResponse.ok(await svc.preview(payload, actor))


@router.post("/invoices/preview/pdf")
async def preview_pdf(payload: InvoiceInput, svc: Service, actor: View):
    doc = await svc.preview(payload, actor)
    return await pdf_response(doc, "preview", svc, actor)


@router.get("/invoices")
async def list_invoices(
    svc: Service,
    actor: View,
    search: str = Query(default="", max_length=150),
    status: Literal["", "draft", "issued", "paid", "partially_paid", "cancelled"] = "",
    from_date: date | None = None,
    to_date: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    sort: Literal["created_at", "invoice_date", "invoice_number", "customer.name"] = "created_at",
    direction: Literal[-1, 1] = -1,
    archived: bool = False,
):
    if from_date and to_date and from_date > to_date:
        raise ValidationError("From date cannot be after To date.")
    return ApiResponse.ok(
        await svc.list(
            actor,
            search=search,
            status=status,
            from_date=from_date,
            to_date=to_date,
            page=page,
            page_size=page_size,
            sort=sort,
            direction=direction,
            archived=archived,
        )
    )


@router.post("/invoices")
async def create_invoice(payload: InvoiceInput, svc: Service, actor: Create):
    return ApiResponse.ok(await svc.create(payload, actor))


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, svc: Service, actor: View):
    return ApiResponse.ok(await svc.get(invoice_id, actor))


@router.put("/invoices/{invoice_id}")
async def edit_invoice(invoice_id: str, payload: InvoiceInput, svc: Service, actor: Edit):
    return ApiResponse.ok(await svc.update(invoice_id, payload, actor))


@router.post("/invoices/{invoice_id}/duplicate")
async def duplicate_invoice(
    invoice_id: str, svc: Service, actor: Create, payload: CopyInput | None = None
):
    return ApiResponse.ok(
        await svc.duplicate(invoice_id, actor, request_key=payload.request_key if payload else None)
    )


@router.post("/invoices/{invoice_id}/replacement")
async def replacement_invoice(
    invoice_id: str, payload: CopyInput, svc: Service, actor: Create, editor: Edit
):
    return ApiResponse.ok(
        await svc.duplicate(
            invoice_id,
            actor,
            request_key=payload.request_key,
            reason=payload.reason,
            replacement=True,
        )
    )


@router.delete("/invoices/{invoice_id}")
async def delete_invoice(
    invoice_id: str, payload: DraftDeleteInput, svc: Service, actor: Edit
) -> ApiResponse[Any]:
    return ApiResponse.ok(
        await svc.delete_draft(invoice_id, payload.version, actor, payload.reason)
    )


@router.get("/invoices/{invoice_id}/correction")
async def correction_draft(
    invoice_id: str, svc: Service, actor: Edit, creator: Create
) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.correction_draft(invoice_id, actor))


@router.get("/invoices/{invoice_id}/delete-options")
async def delete_options(invoice_id: str, svc: Service, actor: Edit) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.delete_options(invoice_id, actor))


@router.post("/invoices/{invoice_id}/archive")
async def archive_invoice(
    invoice_id: str, payload: ArchiveInput, svc: Service, actor: Edit
) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.archive(invoice_id, payload.version, payload.reason, actor))


@router.get("/invoices/{invoice_id}/history")
async def invoice_history(invoice_id: str, svc: Service, actor: View):
    return ApiResponse.ok(await svc.history(invoice_id, actor))


@router.post("/invoices/{invoice_id}/status")
async def status_invoice(invoice_id: str, payload: StatusInput, svc: Service, actor: Edit):
    return ApiResponse.ok(await svc.status(invoice_id, payload, actor))


@router.post("/invoices/{invoice_id}/cancel")
async def cancel_invoice(invoice_id: str, payload: CancelInput, svc: Service, actor: Edit):
    return ApiResponse.ok(
        await svc.status(
            invoice_id,
            StatusInput(status="cancelled", reason=payload.reason, version=payload.version),
            actor,
        )
    )


def asset_bytes(key: str) -> bytes:
    result = get_s3_client().get_object(Bucket=get_storage_config().bucket_name, Key=key)
    try:
        data = result["Body"].read(5 * 1024 * 1024 + 1)
    finally:
        result["Body"].close()
    if len(data) > 5 * 1024 * 1024:
        raise ValidationError("Company image exceeds 5 MB.")
    with Image.open(BytesIO(data)) as img:
        if max(img.size) > 8192:
            raise ValidationError("Company image exceeds 8192 pixels.")
        img.verify()
    return data


async def pdf_response(
    doc: dict[str, Any], purpose: str, svc: InvoiceService, actor: User, frozen: bool = False
) -> Response:
    # Draft payment/signature previews follow current settings without rewriting
    # stored invoice amounts or the immutable snapshots of issued invoices.
    if doc["status"] == "draft" and not frozen:
        company = await svc.draft_company(doc)
        doc = doc | {"company": company}
        doc = doc | {"qr_value": payment_qr(company, doc)}
    assets = {}
    try:
        for name, key in [
            ("logo", doc["company"]["logo_s3_key"]),
            ("signature", doc["company"]["signature_s3_key"]),
        ]:
            if key and (name != "signature" or doc["company"]["show_signature"]):
                assets[name] = await run_in_threadpool(asset_bytes, key)
        pdf = await run_in_threadpool(render_invoice, doc, assets)
    except ValidationError:
        raise
    except Exception as exc:
        raise AppError(
            "Invoice PDF could not be generated. Check company images and try again."
        ) from exc
    if purpose != "preview":
        await svc.audit(actor, "print_requested" if purpose == "print" else "downloaded", doc["id"])
    filename = doc["invoice_number"] + ".pdf"
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{"attachment" if purpose == "download" else "inline"}; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/invoices/{invoice_id}/pdf")
async def invoice_pdf(
    invoice_id: str,
    svc: Service,
    actor: View,
    purpose: Literal["download", "print", "preview"] = "download",
):
    return await pdf_response(await svc.get(invoice_id, actor), purpose, svc, actor)


@router.post("/invoices/{invoice_id}/revision")
async def request_revision(
    invoice_id: str, payload: RevisionInput, svc: Service, actor: Edit
) -> ApiResponse[Any]:
    return ApiResponse.ok(await InvoiceRevisionService(svc).request(invoice_id, payload, actor))


@router.post("/invoices/{invoice_id}/reissue")
async def reissue(
    invoice_id: str, payload: ReissueInput, svc: Service, actor: Owner
) -> ApiResponse[Any]:
    return ApiResponse.ok(await InvoiceRevisionService(svc).reissue(invoice_id, payload, actor))


@router.get("/invoices/{invoice_id}/revisions")
async def revision_history(invoice_id: str, svc: Service, actor: View) -> ApiResponse[Any]:
    return ApiResponse.ok(await InvoiceRevisionService(svc).history(invoice_id, actor))


@router.get("/invoices/{invoice_id}/revisions/{number}")
async def historical_revision(
    invoice_id: str, number: int, svc: Service, actor: View
) -> ApiResponse[Any]:
    return ApiResponse.ok(await InvoiceRevisionService(svc).historical(invoice_id, number, actor))


@router.get("/invoices/{invoice_id}/revisions/{number}/pdf")
async def historical_pdf(invoice_id: str, number: int, svc: Service, actor: View) -> Response:
    doc = await InvoiceRevisionService(svc).historical(invoice_id, number, actor)
    response = await pdf_response(doc, "preview", svc, actor)
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{doc["invoice_number"]}-revision-{number}.pdf"'
    )
    await svc.audit(actor, "historical_pdf_downloaded", invoice_id, revision_number=number)
    return response


@router.post("/invoices/{invoice_id}/issued-delete")
async def issued_delete(
    invoice_id: str, payload: ArchiveInput, svc: Service, actor: Owner
) -> ApiResponse[Any]:
    current = await svc.get(invoice_id, actor)
    if current["status"] != "issued":
        raise ValidationError("Only an issued invoice can use this controlled archive action.")
    return ApiResponse.ok(await svc.archive(invoice_id, payload.version, payload.reason, actor))


@router.post("/invoices/{invoice_id}/revision/preview/pdf")
async def revision_preview_pdf(
    invoice_id: str, payload: RevisionInput, svc: Service, actor: Edit
) -> Response:
    current = await InvoiceRevisionService(svc).editable(invoice_id, actor)
    await svc.customer_validate(payload.invoice, actor)
    from app.features.invoices.calculations import calculate

    business = payload.invoice.model_dump(mode="json", exclude={"request_key", "version"})
    doc = current | business | calculate(payload.invoice.items, payload.invoice.tax_type)
    doc.update(company=current["company"], status="draft", qr_value="")
    return await pdf_response(doc, "preview", svc, actor, frozen=True)
