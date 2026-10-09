"""Vector A4 invoice, based on the supplied Ashapura printed invoice.

Accounting is deliberately absent: this renderer consumes stored calculated values.
Platypus splits long item/HSN tables and repeats their column headings.
"""

from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from threading import Lock
from xml.sax.saxutils import escape

import font_roboto
import qrcode
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

_FONT_LOCK = Lock()


def fonts():
    root = Path(font_roboto.__file__).parent / "files"
    with _FONT_LOCK:
        if "Invoice" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("Invoice", str(root / "Roboto-Regular.ttf")))
            pdfmetrics.registerFont(TTFont("InvoiceBold", str(root / "Roboto-Bold.ttf")))
            pdfmetrics.registerFontFamily("Invoice", normal="Invoice", bold="InvoiceBold")


class NumberedCanvas(Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.states = []

    def showPage(self):
        self.states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        count = len(self.states)
        for state in self.states:
            self.__dict__.update(state)
            self.setFont("Invoice", 7)
            self.drawRightString(A4[0] - 28, 18, f"{self._pageNumber}/{count}")
            Canvas.showPage(self)
        Canvas.save(self)


def render_invoice(invoice: dict, assets: dict[str, bytes] | None = None) -> bytes:
    fonts()
    assets = assets or {}
    out = BytesIO()
    width = A4[0] - 56
    style = ParagraphStyle("body", fontName="Invoice", fontSize=8, leading=12)
    bold = ParagraphStyle("bold", parent=style, fontName="InvoiceBold")
    right = ParagraphStyle("right", parent=style, alignment=TA_RIGHT)
    right_bold = ParagraphStyle("right_bold", parent=bold, alignment=TA_RIGHT)
    center = ParagraphStyle("center", parent=style, alignment=TA_CENTER)
    center_bold = ParagraphStyle("center_bold", parent=bold, alignment=TA_CENTER)
    header = ParagraphStyle("company", parent=bold, fontSize=21, leading=25)

    def p(value="", s=style):
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), s)

    def amount(value):
        return f"{Decimal(value):,.2f}"

    def percent(value):
        whole, fraction = f"{Decimal(value):.3f}".split(".")
        return whole + "." + fraction.rstrip("0").ljust(2, "0") + "%"

    def image(data, w, h):
        result = Image(BytesIO(data))
        ratio = min(w / result.imageWidth, h / result.imageHeight)
        result.drawWidth, result.drawHeight = result.imageWidth * ratio, result.imageHeight * ratio
        return result

    def table(rows, widths, *, headings=False, borders=True):
        t = Table(rows, colWidths=widths, repeatRows=1 if headings else 0, hAlign="LEFT")
        t.setStyle(
            TableStyle(
                ([("GRID", (0, 0), (-1, -1), 0.6, colors.black)] if borders else [])
                + [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        return t

    company, customer = invoice["company"], invoice["customer"]
    address = company["address"]
    address_text = ", ".join(
        str(address.get(k) or "")
        for k in ("line1", "line2", "city", "state", "pincode")
        if address.get(k)
    )
    logo = image(assets["logo"], 105, 76) if assets.get("logo") else ""
    top = Table(
        [
            [
                [
                    p(company["name"], header),
                    p(address_text, bold),
                    p(
                        "   |   ".join(
                            filter(None, [company["phone"], company["email"], company["website"]])
                        )
                    ),
                ],
                logo,
            ]
        ],
        colWidths=[width - 115, 115],
    )
    top.setStyle(
        TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)])
    )
    story = [
        top,
        Spacer(1, 26),
        p(
            "INVOICE",
            ParagraphStyle("title", parent=bold, alignment=TA_CENTER, fontSize=14, leading=20),
        ),
        Spacer(1, 10),
    ]
    cust = [
        p("To :", bold),
        p(customer["name"], bold),
        p(customer["address"]),
        p(
            ", ".join(
                filter(
                    None,
                    [customer["city"], customer["state"], customer["pincode"], customer["country"]],
                )
            )
        ),
        p("GSTIN : " + customer["gstin"]),
        p("Phone : " + customer["phone"]),
    ]
    details = [
        p("Invoice No. : " + invoice["invoice_number"], right),
        p("Date : " + date.fromisoformat(invoice["invoice_date"]).strftime("%d-%b-%Y"), right),
        p("Valid till : " + date.fromisoformat(invoice["due_date"]).strftime("%d-%b-%Y"), right),
        p("GSTIN : " + company["gstin"], right),
    ]
    if invoice.get("place_of_supply"):
        details.append(p("Place of supply : " + invoice["place_of_supply"], right))
    if invoice.get("status") in ("draft", "cancelled"):
        details.append(p(invoice["status"].upper(), right))
    bill = Table([[cust, details]], colWidths=[width * 0.62, width * 0.38])
    bill.setStyle(
        TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)])
    )
    story += [bill, Spacer(1, 7)]
    split = invoice["tax_type"] == "CGST_SGST"
    labels = ["No.", "Item & Description", "HSN / SAC", "Qty", "Unit", "Rate (₹)", "Taxable (₹)"]
    labels += ["CGST", "SGST"] if split else ["IGST"]
    labels += ["Amount (₹)"]
    ratios = [4, 32, 10, 6, 7, 9, 10] + ([6, 6] if split else [8]) + [10]
    widths = [width * r / sum(ratios) for r in ratios]
    rows = [[p(x, bold) for x in labels]]
    for i, item in enumerate(invoice["items"], 1):
        cells = [
            str(i),
            item["description"],
            item["hsn"],
            item["quantity"],
            item["unit"],
            amount(item["rate"]),
            amount(item["taxable"]),
        ]
        cells += (
            [percent(item["cgst_rate"]), percent(item["sgst_rate"])]
            if split
            else [percent(item["igst_rate"])]
        )
        cells += [amount(item["total"])]
        rendered = [p(v, style if j in (1, 4) else right) for j, v in enumerate(cells)]
        lines = item["description"].split("\n")
        rendered[1] = Paragraph(
            "<b>"
            + escape(lines[0])
            + "</b>"
            + "".join("<br/>" + escape(line) for line in lines[1:]),
            style,
        )
        rows.append(rendered)
    items_table = table(rows, widths, headings=True)
    story += [items_table, Spacer(1, 8)]
    bank = [p("Bank Details :", bold)] + [
        p(label + " : " + company[key])
        for label, key in [
            ("Bank Name", "bank_name"),
            ("Branch", "branch"),
            ("Account No.", "account_number"),
            ("IFSC", "ifsc"),
        ]
    ]
    words = [
        p("Total Invoice Amount in Words :", bold),
        p(
            invoice["amount_in_words"],
            ParagraphStyle("words", parent=bold, fontSize=8.5, leading=14),
        ),
    ]
    totals = [[p("Total Amount before Tax (₹)", right), p(amount(invoice["subtotal"]), right)]]
    if split:
        for label, field in [("CGST", "cgst"), ("SGST", "sgst")]:
            totals.append(
                [
                    p("Add " + label + " (₹)", right),
                    p(amount(invoice[field + "_total"]), right),
                ]
            )
    else:
        totals.append([p("Add IGST (₹)", right), p(amount(invoice["gst_total"]), right)])
    totals.append([p("Grand Total (₹)", right_bold), p(amount(invoice["grand_total"]), right_bold)])
    total_table = table(totals, [width * 0.24, width * 0.11])
    total_table.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 2)]))
    bank_table = table([[bank, words, total_table]], [width * 0.33, width * 0.32, width * 0.35])
    bank_table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (2, 0), (2, 0), 0),
                ("RIGHTPADDING", (2, 0), (2, 0), 0),
                ("TOPPADDING", (2, 0), (2, 0), 0),
                ("BOTTOMPADDING", (2, 0), (2, 0), 0),
            ]
        )
    )
    qr = ""
    if invoice.get("qr_value"):
        qr_bytes = BytesIO()
        code = qrcode.QRCode(border=4, box_size=8)
        code.add_data(invoice["qr_value"])
        code.make(fit=True)
        code.make_image().save(qr_bytes, format="PNG")
        qr = image(qr_bytes.getvalue(), 74, 74)
    sign = [p("For, " + company["name"], center)]
    if company["show_signature"] and assets.get("signature"):
        sign += [image(assets["signature"], 130, 48)]
    else:
        sign += [Spacer(1, 36)]
    if company["signatory"]:
        sign += [p(company["signatory"], center_bold)]
    if company["designation"]:
        sign += [p(company["designation"], center)]
    sign += [p("Authorised Signatory", center_bold)]
    foot = table(
        [
            [
                [
                    Spacer(1, 24),
                    p("Total Qty : " + invoice["total_quantity"], bold),
                    p("This is a computer-generated invoice. E. & O.E."),
                ],
                qr,
                sign,
            ]
        ],
        [width * 0.55, width * 0.15, width * 0.30],
        borders=False,
    )
    # Reference has no border between declaration and QR.
    foot.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, colors.black),
                ("LINEBEFORE", (2, 0), (2, 0), 0.6, colors.black),
            ]
        )
    )
    summary_labels = ["HSN/SAC Code", "Taxable (₹)"] + (
        ["CGST %", "CGST (₹)", "SGST %", "SGST (₹)"] if split else ["IGST %", "IGST (₹)"]
    )
    summary = [[p(v, bold) for v in summary_labels]]
    for g in invoice["hsn_summary"]:
        row = [g["hsn"], amount(g["taxable"])]
        row += (
            [
                percent(g["cgst_rate"]),
                amount(g["cgst"]),
                percent(g["sgst_rate"]),
                amount(g["sgst"]),
            ]
            if split
            else [percent(g["igst_rate"]), amount(g["igst"])]
        )
        summary.append([p(v, style if i == 0 else right) for i, v in enumerate(row)])
    story += [
        KeepTogether([bank_table, foot]),
        Spacer(1, 8),
        table(
            summary,
            [width * 0.75 / len(summary_labels)] * len(summary_labels)
            if split
            else [width * 0.5 * r for r in (0.343, 0.268, 0.187, 0.202)],
            headings=True,
        ),
    ]
    if invoice.get("terms"):
        story += [Spacer(1, 6), p("Payment terms : " + invoice["terms"])]
    doc = BaseDocTemplate(
        out,
        pagesize=A4,
        rightMargin=28,
        leftMargin=28,
        topMargin=32,
        bottomMargin=32,
        title="Invoice " + invoice["invoice_number"],
        author=company["name"],
    )
    doc.addPageTemplates(
        PageTemplate(
            id="invoice",
            frames=[
                Frame(
                    28,
                    32,
                    width,
                    A4[1] - 70,
                    leftPadding=0,
                    rightPadding=0,
                    topPadding=0,
                    bottomPadding=0,
                )
            ],
        )
    )
    doc.build(story, canvasmaker=NumberedCanvas)
    return out.getvalue()
