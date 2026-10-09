from datetime import date
from io import BytesIO
from typing import Annotated, Literal
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
from app.features.invoices.schemas import CancelInput, InvoiceConfig, InvoiceInput, StatusInput
from app.features.invoices.service import InvoiceService
from app.services.storage.client import generate_presigned_download_url, get_s3_client

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
    await svc.company.update(
        company.require_id(),
        {"invoice_config": payload.model_dump(mode="json")},
        updated_by=actor.require_id(),
    )
    await svc.audit(actor, "settings_updated")
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
async def duplicate_invoice(invoice_id: str, svc: Service, actor: Create):
    return ApiResponse.ok(await svc.duplicate(invoice_id, actor))


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


async def pdf_response(doc, purpose, svc, actor):
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
