import asyncio
from decimal import Decimal
from io import BytesIO
from urllib.parse import parse_qs, urlparse

import pymupdf
import pytest
from app.features.access_control.models import (
    EmployeeRole,
    Permission,
    Role,
    RolePermission,
)
from app.features.customer.models import Customer
from app.features.invoices.calculations import amount_in_words, calculate
from app.features.invoices.repository import ensure_invoice_indexes
from app.features.invoices.schemas import InvoiceItem
from bson import ObjectId
from PIL import Image


def sample():
    return {
        "customer_id": None,
        "customer": {
            "name": "AADIFIDELIS SOLUTIONS PRIVATE LIMITED",
            "address": "1ST FLOOR, FLAT NO. B-2, YASHODEEP APARTMENT,\nOMKARESHWAR PATH, VEER MARUTI TEMPLE,\n434 SHANIWAR PETH",
            "city": "PUNE",
            "state": "MAHARASHTRA",
            "pincode": "411030",
            "country": "India",
            "gstin": "27AAQCA5897E1Z3",
            "phone": "9880969798",
            "email": "",
        },
        "invoice_date": "2026-10-04",
        "due_date": "2026-10-04",
        "place_of_supply": "",
        "terms": "",
        "tax_type": "IGST",
        "version": 1,
        "items": [
            {
                "description": "PERSONAL LOAN\nLOAN CONSULTANCY\nCOMMISSION",
                "hsn": "9971",
                "quantity": "3",
                "unit": "nos.s",
                "rate": "7753.71",
                "gst_rate": "18",
            }
        ],
    }


async def create(client, headers, payload=None):
    response = await client.post(
        "/api/v1/invoices", headers=headers, json=payload or sample()
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def configure(client, headers):
    r = await client.patch(
        "/api/v1/company-settings",
        headers=headers,
        json={
            "company_name": "Ashapura Financial Services",
            "contact_phone": "8431002626",
            "contact_email": "ashapurafinance26@gmail.com",
            "address": {
                "line1": "GROUND FLOOR DOOR NO-146 A KONAPPANA AGRAHARA",
                "city": "BANGALORE",
                "state": "KARNATAKA",
                "pincode": "560100",
            },
        },
    )
    assert r.status_code == 200, r.text
    r = await client.put(
        "/api/v1/invoice-settings",
        headers=headers,
        json={
            "gstin": "29DFPPP1103E1ZI",
            "website": "ashapurafinancialservices.com",
            "bank_name": "Union Bank of India",
            "branch": "71247",
            "account_number": "139812010002347",
            "ifsc": "UBIN0813982",
            "qr_type": "identifier",
        },
    )
    assert r.status_code == 200, r.text


async def test_create_retrieve_update_search_and_audit(client, owner_headers, mock_db):
    await ensure_invoice_indexes(mock_db)
    doc = await create(client, owner_headers)
    assert doc["subtotal"] == "23261.13"
    assert doc["gst_total"] == "4187.00"
    assert doc["grand_total"] == "27448.13"
    assert doc["total_quantity"] == "3"
    assert (
        doc["amount_in_words"]
        == "Rupees Twenty Seven Thousand Four Hundred Forty Eight and Paise Thirteen only"
    )
    assert doc["invoice_number"] == "INV-000001"
    fetched = await client.get("/api/v1/invoices/" + doc["id"], headers=owner_headers)
    assert fetched.json()["data"]["customer"] == doc["customer"]
    payload = sample()
    payload["items"][0]["quantity"] = "4"
    r = await client.put(
        "/api/v1/invoices/" + doc["id"], headers=owner_headers, json=payload
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["version"] == 2
    assert r.json()["data"]["invoice_number"] == doc["invoice_number"]
    assert (
        await client.put(
            "/api/v1/invoices/" + doc["id"], headers=owner_headers, json=payload
        )
    ).status_code == 409
    found = await client.get(
        "/api/v1/invoices?search=AADIFIDELIS&from_date=2026-10-04&to_date=2026-10-04&page_size=1",
        headers=owner_headers,
    )
    assert found.json()["data"]["total"] == 1
    assert (
        await mock_db.audit_logs.count_documents({"event_type": "invoice_created"}) == 1
    )
    assert (
        await mock_db.audit_logs.count_documents({"event_type": "invoice_edited"}) == 1
    )


async def test_numbering_parallel_floor_and_duplicate(client, owner_headers, mock_db):
    await ensure_invoice_indexes(mock_db)
    r = await client.put(
        "/api/v1/invoice-settings",
        headers=owner_headers,
        json={"prefix": "AFS-", "starting_number": 50},
    )
    assert r.status_code == 200
    docs = await asyncio.gather(*(create(client, owner_headers) for _ in range(12)))
    assert sorted(d["invoice_number"] for d in docs) == [
        f"AFS-{i:06}" for i in range(50, 62)
    ]
    response = await client.post(
        "/api/v1/invoices/" + docs[0]["id"] + "/duplicate", headers=owner_headers
    )
    assert response.status_code == 200, response.text
    copy = response.json()["data"]
    assert copy["invoice_number"] == "AFS-000062"
    assert copy["status"] == "draft" and copy["items"] == docs[0]["items"]
    # Lowering the floor and changing prefixes never resets the global counter.
    await client.put(
        "/api/v1/invoice-settings", headers=owner_headers, json={"starting_number": 1}
    )
    assert (await create(client, owner_headers))["invoice_number"] == "INV-000063"


async def test_issue_snapshot_cancel_and_lifecycle(client, owner_headers, mock_db):
    await configure(client, owner_headers)
    doc = await create(client, owner_headers)
    url = "/api/v1/invoices/" + doc["id"]
    issued = await client.post(
        url + "/status", headers=owner_headers, json={"status": "issued", "version": 1}
    )
    assert issued.status_code == 200, issued.text
    assert issued.json()["data"]["qr_value"] == "Invoice:" + doc["invoice_number"]
    await client.patch(
        "/api/v1/company-settings",
        headers=owner_headers,
        json={"company_name": "Changed company"},
    )
    await client.put(
        "/api/v1/invoice-settings",
        headers=owner_headers,
        json={"bank_name": "Changed bank"},
    )
    original = (await client.get(url, headers=owner_headers)).json()["data"]
    assert original["company"]["name"] == "Ashapura Financial Services"
    assert original["company"]["bank_name"] == "Union Bank of India"
    assert (
        await client.put(url, headers=owner_headers, json=sample())
    ).status_code == 409
    assert (
        await client.post(
            url + "/cancel", headers=owner_headers, json={"reason": "", "version": 2}
        )
    ).status_code == 422
    r = await client.post(
        url + "/cancel",
        headers=owner_headers,
        json={"reason": "Customer requested correction", "version": 2},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["cancelled_by"] and r.json()["data"]["cancelled_at"]
    assert (
        await client.put(url, headers=owner_headers, json=sample())
    ).status_code == 409
    assert await mock_db.invoices.count_documents({}) == 1


async def test_paid_and_partial_status_rules(client, owner_headers):
    await configure(client, owner_headers)
    doc = await create(client, owner_headers)
    url = "/api/v1/invoices/" + doc["id"] + "/status"
    assert (
        await client.post(
            url, headers=owner_headers, json={"status": "paid", "version": 1}
        )
    ).status_code == 409
    for version, status in enumerate(["issued", "partially_paid", "paid"], 1):
        r = await client.post(
            url, headers=owner_headers, json={"status": status, "version": version}
        )
        assert r.status_code == 200, r.text
    assert (
        await client.post(
            url,
            headers=owner_headers,
            json={"status": "cancelled", "version": 4, "reason": "test"},
        )
    ).status_code == 409


async def test_missing_settings_and_invalid_customer(client, owner_headers):
    doc = await create(client, owner_headers)
    assert (
        await client.post(
            "/api/v1/invoices/" + doc["id"] + "/status",
            headers=owner_headers,
            json={"status": "issued", "version": 1},
        )
    ).status_code == 422
    data = sample()
    data["customer_id"] = str(ObjectId())
    assert (
        await client.post("/api/v1/invoices", headers=owner_headers, json=data)
    ).status_code == 404


@pytest.mark.parametrize(
    "field,value",
    [
        ("quantity", "0"),
        ("quantity", "-1"),
        ("quantity", "1.0001"),
        ("rate", "NaN"),
        ("rate", "Infinity"),
        ("rate", "0.001"),
        ("gst_rate", "101"),
        ("gst_rate", "-1"),
        ("hsn", "abc"),
        ("description", ""),
    ],
)
async def test_invalid_item(client, owner_headers, field, value):
    data = sample()
    data["items"][0][field] = value
    assert (
        await client.post("/api/v1/invoices", headers=owner_headers, json=data)
    ).status_code == 422


async def test_reject_totals_empty_items_bad_dates(client, owner_headers):
    for patch in [{"grand_total": "1.00"}, {"items": []}, {"due_date": "2026-10-03"}]:
        assert (
            await client.post(
                "/api/v1/invoices", headers=owner_headers, json=sample() | patch
            )
        ).status_code == 422


async def grant_employee(mock_db, actions):
    user = await mock_db.users.find_one({"role": "employee"})
    emp = await mock_db.employees.insert_one(
        {
            "user_id": str(user["_id"]),
            "employee_code": "AFS-EMP-TEST",
            "first_name": "Test",
            "last_name": "Staff",
            "display_name": "Test Staff",
            "employment_type": "full_time",
            "mobile": user["mobile"],
            "email": "staff@example.com",
            "department_id": str(ObjectId()),
            "designation_id": str(ObjectId()),
            "branch_id": str(ObjectId()),
            "joining_date": "2026-01-01",
            "status": "active",
            "is_deleted": False,
        }
    )
    permission = Permission(
        module="invoices", resource="invoices", actions=["view", "create", "edit"]
    )
    pid = (
        await mock_db.permissions.insert_one(
            permission.model_dump(by_alias=True, exclude={"id"})
        )
    ).inserted_id
    role = Role(name="Invoice staff")
    rid = (
        await mock_db.roles.insert_one(role.model_dump(by_alias=True, exclude={"id"}))
    ).inserted_id
    for collection, model in [
        (
            "employee_roles",
            EmployeeRole(employee_id=str(emp.inserted_id), role_id=str(rid)),
        ),
        (
            "role_permissions",
            RolePermission(
                role_id=str(rid), permission_id=str(pid), granted_actions=actions
            ),
        ),
    ]:
        await mock_db[collection].insert_one(
            model.model_dump(by_alias=True, exclude={"id"})
        )
    return str(emp.inserted_id)


async def test_auth_rbac_record_access_and_sensitive_settings(
    client, owner_headers, employee_headers, mock_db
):
    doc = await create(client, owner_headers)
    url = "/api/v1/invoices/" + doc["id"]
    for suffix in ["", "/pdf", "/pdf?purpose=print"]:
        assert (await client.get(url + suffix)).status_code == 401
        assert (
            await client.get(url + suffix, headers=employee_headers)
        ).status_code == 403
    employee_id = await grant_employee(mock_db, ["view"])
    await mock_db.applications.insert_one(
        {"customer_id": None, "assigned_to": employee_id, "is_deleted": False}
    )
    for suffix in ["", "/pdf"]:
        assert (
            await client.get(url + suffix, headers=employee_headers)
        ).status_code == 404
    assert (await client.get("/api/v1/invoices", headers=employee_headers)).json()[
        "data"
    ]["total"] == 0
    assert (
        await client.post("/api/v1/invoices", headers=employee_headers, json=sample())
    ).status_code == 403
    assert (
        await client.get("/api/v1/invoice-settings", headers=employee_headers)
    ).status_code == 403
    assert (
        await client.put(url, headers=employee_headers, json=sample())
    ).status_code == 403


async def test_assigned_customer_scope_and_revocation(
    client, owner_headers, employee_headers, mock_db
):
    employee_id = await grant_employee(mock_db, ["view", "create", "edit"])
    customer = Customer(
        customer_code="AFS-CUS-TEST",
        user_id=str(ObjectId()),
        full_name="Customer",
        mobile="9999999999",
    )
    cid = str(
        (
            await mock_db.customers.insert_one(
                customer.model_dump(by_alias=True, exclude={"id"})
            )
        ).inserted_id
    )
    data = sample()
    data["customer_id"] = cid
    assert (
        await client.post("/api/v1/invoices", headers=employee_headers, json=data)
    ).status_code == 403
    await mock_db.applications.insert_one(
        {
            "customer_id": cid,
            "assigned_to": employee_id,
            "is_deleted": False,
            "application_code": "AFS-APP-TEST",
            "user_id": customer.user_id,
            "product_category": "loan",
            "product_id": str(ObjectId()),
            "form_definition_id": str(ObjectId()),
        }
    )
    doc = await create(client, employee_headers, data)
    assert (
        await client.get("/api/v1/invoices/" + doc["id"], headers=employee_headers)
    ).status_code == 200
    await mock_db.applications.delete_many({})
    assert (
        await client.get(
            "/api/v1/invoices/" + doc["id"] + "/pdf", headers=employee_headers
        )
    ).status_code == 404
    manual = await create(client, employee_headers)
    assert (
        await client.get("/api/v1/invoices/" + manual["id"], headers=employee_headers)
    ).status_code == 200


def test_decimal_rounding_hsn_and_words():
    rows = sample()["items"]
    rows += [
        dict(rows[0], quantity="1", gst_rate="18.00"),
        dict(rows[0], hsn="9983", quantity="0.125", rate="0.04", gst_rate="5"),
    ]
    result = calculate([InvoiceItem(**row) for row in rows])
    assert len(result["hsn_summary"]) == 2
    assert result["hsn_summary"][0]["taxable"] == "31014.84"
    assert result["items"][2]["taxable"] == "0.01"
    split = calculate(
        [
            InvoiceItem(
                description="Split rounding",
                hsn="9971",
                quantity="1",
                rate="0.06",
                gst_rate="18",
            )
        ],
        "CGST_SGST",
    )
    assert split["gst_total"] == "0.02" and split["items"][0]["cgst"] == "0.01"
    for amount, words in [
        ("0", "Rupees Zero only"),
        ("0.01", "Rupees Zero and Paise One only"),
        ("100000", "Rupees One Lakh only"),
        ("10000000", "Rupees One Crore only"),
        (
            "123456789.12",
            "Rupees Twelve Crore Thirty Four Lakh Fifty Six Thousand Seven Hundred Eighty Nine and Paise Twelve only",
        ),
    ]:
        assert amount_in_words(Decimal(amount)) == words


async def test_real_pdf_a4_preview_audit_and_pagination(client, owner_headers, mock_db):
    await configure(client, owner_headers)
    doc = await create(client, owner_headers)
    r = await client.get(
        "/api/v1/invoices/" + doc["id"] + "/pdf", headers=owner_headers
    )
    assert r.status_code == 200, r.text
    pdf = pymupdf.open(stream=r.content, filetype="pdf")
    assert len(pdf) == 1
    assert (
        abs(pdf[0].rect.width - 595.276) < 0.1
        and abs(pdf[0].rect.height - 841.89) < 0.1
    )
    text = pdf[0].get_text()
    for phrase in [
        "INVOICE",
        "27,448.13",
        "HSN/SAC Code",
        "Bank Details",
        "Authorised Signatory",
        "1/1",
        "₹",
    ]:
        assert phrase in text
    assert (
        await mock_db.audit_logs.count_documents({"event_type": "invoice_downloaded"})
        == 1
    )
    data = sample()
    data["items"] *= 70
    r = await client.post(
        "/api/v1/invoices/preview/pdf", headers=owner_headers, json=data
    )
    assert r.status_code == 200, r.text
    long = pymupdf.open(stream=r.content, filetype="pdf")
    assert len(long) > 1
    for i, page in enumerate(long):
        assert f"{i + 1}/{len(long)}" in page.get_text()
        assert all(
            block[3] < 820
            for block in page.get_text("blocks")
            if block[4].strip() != f"{i + 1}/{len(long)}"
        )


async def test_pdf_error_and_upi_config_validation(client, owner_headers, monkeypatch):
    from app.features.invoices import router

    doc = await create(client, owner_headers)

    def fail(*args, **kwargs):
        raise RuntimeError("private failure")

    monkeypatch.setattr(router, "render_invoice", fail)
    r = await client.get(
        "/api/v1/invoices/" + doc["id"] + "/pdf", headers=owner_headers
    )
    assert r.status_code == 500 and "private failure" not in r.text
    assert (
        await client.put(
            "/api/v1/invoice-settings", headers=owner_headers, json={"qr_type": "upi"}
        )
    ).status_code == 422


async def test_signature_storage_assets_and_historical_replacement(
    client, owner_headers, mock_db, monkeypatch
):
    from app.features.invoices import assets, router

    images = {}

    class Storage:
        def put_object(self, *, Key, Body, **kwargs):
            images[Key] = Body

        def get_object(self, *, Key, **kwargs):
            return {"Body": BytesIO(images[Key])}

        def copy_object(self, *, Key, CopySource, **kwargs):
            images[Key] = images[CopySource["Key"]]

    monkeypatch.setattr(router, "get_s3_client", lambda: Storage())
    monkeypatch.setattr(assets, "get_s3_client", lambda: Storage())
    monkeypatch.setattr(
        router,
        "generate_presigned_download_url",
        lambda key: "https://example.test/" + key,
    )
    image = BytesIO()
    Image.new("RGB", (120, 40), "navy").save(image, format="PNG")
    data = image.getvalue()
    await configure(client, owner_headers)
    upload = await client.post(
        "/api/v1/invoice-settings/signature",
        headers=owner_headers,
        files={"file": ("signature.png", data, "image/png")},
    )
    assert upload.status_code == 200, upload.text
    key = upload.json()["data"]["s3_key"]
    config = (
        await client.get("/api/v1/invoice-settings", headers=owner_headers)
    ).json()["data"]["config"]
    config["signature_s3_key"] = key
    assert (
        await client.put("/api/v1/invoice-settings", headers=owner_headers, json=config)
    ).status_code == 200
    images["company/logo/sample.png"] = data
    await mock_db.company_settings.update_one(
        {"singleton_key": "default"},
        {"$set": {"logo_s3_key": "company/logo/sample.png"}},
    )
    invoice = await create(client, owner_headers)
    url = "/api/v1/invoices/" + invoice["id"]
    assert (
        await client.post(
            url + "/status",
            headers=owner_headers,
            json={"status": "issued", "version": 1},
        )
    ).status_code == 200
    historical_key = (await client.get(url, headers=owner_headers)).json()["data"][
        "company"
    ]["signature_s3_key"]
    assert historical_key != key and historical_key.startswith("invoice-assets/")
    assert images[historical_key] == data
    pdf = await client.get(url + "/pdf?purpose=print", headers=owner_headers)
    assert pdf.status_code == 200, pdf.text
    assert len(pymupdf.open(stream=pdf.content, filetype="pdf")[0].get_images()) >= 2
    assert "no-store" in pdf.headers["cache-control"]
    assert (
        await mock_db.audit_logs.count_documents(
            {"event_type": "invoice_print_requested"}
        )
        == 1
    )
    replacement = await client.post(
        "/api/v1/invoice-settings/signature",
        headers=owner_headers,
        files={"file": ("new.png", data, "image/png")},
    )
    new_key = replacement.json()["data"]["s3_key"]
    assert new_key != key
    config["signature_s3_key"] = new_key
    await client.put("/api/v1/invoice-settings", headers=owner_headers, json=config)
    original = (await client.get(url, headers=owner_headers)).json()["data"]
    assert original["company"]["signature_s3_key"] == historical_key
    assert (
        await client.post(
            "/api/v1/invoice-settings/signature",
            headers=owner_headers,
            files={"file": ("bad.png", b"not a PNG", "image/png")},
        )
    ).status_code == 422


async def test_backend_upi_qr_uses_stored_total(client, owner_headers):
    await configure(client, owner_headers)
    config = (
        await client.get("/api/v1/invoice-settings", headers=owner_headers)
    ).json()["data"]["config"]
    config.update(qr_type="upi", upi_id="example@bank")
    assert (
        await client.put("/api/v1/invoice-settings", headers=owner_headers, json=config)
    ).status_code == 200
    invoice = await create(client, owner_headers)
    r = await client.post(
        "/api/v1/invoices/" + invoice["id"] + "/status",
        headers=owner_headers,
        json={"status": "issued", "version": 1},
    )
    assert r.status_code == 200, r.text
    uri = urlparse(r.json()["data"]["qr_value"])
    query = parse_qs(uri.query)
    assert (
        uri.scheme == "upi"
        and query["am"] == ["27448.13"]
        and query["pa"] == ["example@bank"]
    )


async def test_catalog_registration_idempotent_without_grants(mock_db):
    await ensure_invoice_indexes(mock_db)
    await ensure_invoice_indexes(mock_db)
    assert await mock_db.permissions.count_documents({"module": "invoices"}) == 1
    assert await mock_db.nav_items.count_documents({"key": "invoices"}) == 1
    assert await mock_db.role_permissions.count_documents({}) == 0


async def test_invalid_signature_reference(client, owner_headers):
    assert (
        await client.put(
            "/api/v1/invoice-settings",
            headers=owner_headers,
            json={"signature_s3_key": "customer-secret.png"},
        )
    ).status_code == 422


async def test_total_quantity_is_derived_and_split_pdf(client, owner_headers, mock_db):
    data = sample()
    data["tax_type"] = "CGST_SGST"
    invoice = await create(client, owner_headers, data)
    stored = await mock_db.invoices.find_one({"_id": ObjectId(invoice["id"])})
    assert "total_quantity" not in stored and invoice["total_quantity"] == "3"
    assert invoice["cgst_total"] == "2093.50" and invoice["sgst_total"] == "2093.50"
    response = await client.get(
        "/api/v1/invoices/" + invoice["id"] + "/pdf", headers=owner_headers
    )
    assert response.status_code == 200, response.text
    text = pymupdf.open(stream=response.content, filetype="pdf")[0].get_text()
    assert "CGST" in text and "SGST" in text and "IGST" not in text


async def test_image_snapshot_failure_does_not_issue(
    client, owner_headers, mock_db, monkeypatch
):
    from app.features.invoices import service

    await configure(client, owner_headers)
    await mock_db.company_settings.update_one(
        {"singleton_key": "default"}, {"$set": {"logo_s3_key": "company/logo/test.png"}}
    )
    invoice = await create(client, owner_headers)

    def fail(*args):
        raise RuntimeError("S3 unavailable")

    monkeypatch.setattr(service, "snapshot_image", fail)
    url = "/api/v1/invoices/" + invoice["id"]
    response = await client.post(
        url + "/status", headers=owner_headers, json={"status": "issued", "version": 1}
    )
    assert response.status_code == 500
    assert (await client.get(url, headers=owner_headers)).json()["data"][
        "status"
    ] == "draft"


async def test_customer_picker_search_applies_before_limit(
    client, owner_headers, employee_headers, mock_db
):
    employee_id = await grant_employee(mock_db, ["view"])
    records = []
    for index in range(110):
        model = Customer(
            customer_code=f"AFS-CUS-{index:06}",
            user_id=str(ObjectId()),
            full_name=f"Customer {index:03}",
            mobile="9999999999",
        )
        records.append(model.model_dump(by_alias=True, exclude={"id"}))
    result = await mock_db.customers.insert_many(records)
    await mock_db.applications.insert_many(
        [
            {"customer_id": str(cid), "assigned_to": employee_id, "is_deleted": False}
            for cid in result.inserted_ids
        ]
    )
    for headers in (owner_headers, employee_headers):
        response = await client.get(
            "/api/v1/invoices/customers?search=Customer%20109", headers=headers
        )
        assert response.status_code == 200, response.text
        assert [row["name"] for row in response.json()["data"]] == ["Customer 109"]
    assert (
        await client.get(
            "/api/v1/invoices?from_date=2026-10-08&to_date=2026-10-01",
            headers=owner_headers,
        )
    ).status_code == 422
