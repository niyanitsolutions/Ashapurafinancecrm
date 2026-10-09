"""Offline visual QA only; never writes to MongoDB or S3.

Run with PYTHONPATH=backend and the backend dev dependencies installed.
Optional --reference renders logo/signature clips from the supplied PDF for comparison.
"""

import argparse
import runpy
from pathlib import Path

import pymupdf
from app.features.invoices.calculations import calculate
from app.features.invoices.pdf import render_invoice
from app.features.invoices.schemas import InvoiceConfig, InvoiceItem

parser = argparse.ArgumentParser()
parser.add_argument("--reference", type=Path)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
sample = runpy.run_path(str(root / "tests/api/test_invoices.py"))["sample"]()
config = InvoiceConfig(
    gstin="29DFPPP1103E1ZI",
    website="ashapurafinancialservices.com",
    bank_name="Union Bank of India",
    branch="71247",
    account_number="139812010002347",
    ifsc="UBIN0813982",
    designation="",
)
sample.update(calculate([InvoiceItem(**row) for row in sample["items"]]))
sample.update(
    invoice_number="9",
    status="issued",
    qr_value="Invoice:9",
    company={
        **config.model_dump(mode="json"),
        "name": "Ashapura Financial Services",
        "address": {
            "line1": "GROUND FLOOR DOOR NO-146 A KONAPPANA AGRAHARA",
            "city": "BANGALORE",
            "state": "KARNATAKA",
            "pincode": "560100",
        },
        "phone": "8431002626",
        "email": "ashapurafinance26@gmail.com",
        "logo_s3_key": None,
    },
)
assets = {}
if args.reference:
    ref = pymupdf.open(args.reference)
    # These are PDF rendering clips for this test fixture, never production assets.
    for key, rect in [
        ("logo", (474, 50, 581, 127)),
        ("signature", (442, 436, 567, 481)),
    ]:
        assets[key] = (
            ref[0]
            .get_pixmap(matrix=pymupdf.Matrix(3, 3), clip=pymupdf.Rect(rect))
            .tobytes("png")
        )
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_bytes(render_invoice(sample, assets))
pdf = pymupdf.open(args.output)
for i, page in enumerate(pdf):
    page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).save(
        str(args.output.with_suffix("")) + f"-{i + 1}.png"
    )
print(f"{args.output}: {len(pdf)} A4 page(s)")
