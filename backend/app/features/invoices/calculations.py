"""Deterministic line rounding (half up, paise), including split GST."""

from decimal import ROUND_HALF_UP, Decimal

from app.features.invoices.schemas import InvoiceItem

PAISE = Decimal("0.01")


def money(value: Decimal) -> str:
    return str(value.quantize(PAISE, rounding=ROUND_HALF_UP))


def integer_words(n: int) -> str:
    small = [
        "Zero",
        "One",
        "Two",
        "Three",
        "Four",
        "Five",
        "Six",
        "Seven",
        "Eight",
        "Nine",
        "Ten",
        "Eleven",
        "Twelve",
        "Thirteen",
        "Fourteen",
        "Fifteen",
        "Sixteen",
        "Seventeen",
        "Eighteen",
        "Nineteen",
    ]
    tens = [
        "Zero",
        "Ten",
        "Twenty",
        "Thirty",
        "Forty",
        "Fifty",
        "Sixty",
        "Seventy",
        "Eighty",
        "Ninety",
    ]
    if n < 20:
        return small[n]
    if n < 100:
        return tens[n // 10] + (" " + small[n % 10] if n % 10 else "")
    for size, label in [
        (10000000, "Crore"),
        (100000, "Lakh"),
        (1000, "Thousand"),
        (100, "Hundred"),
    ]:
        if n >= size:
            return (
                integer_words(n // size)
                + " "
                + label
                + (" " + integer_words(n % size) if n % size else "")
            )
    raise ValueError("Negative amount")


def amount_in_words(value: Decimal) -> str:
    paise = int(value.quantize(PAISE, rounding=ROUND_HALF_UP) * 100)
    return (
        "Rupees "
        + integer_words(paise // 100)
        + (" and Paise " + integer_words(paise % 100) if paise % 100 else "")
        + " only"
    )


def calculate(items: list[InvoiceItem], tax_type: str = "IGST") -> dict:
    rows, groups = [], {}
    subtotal = tax = quantity = Decimal(0)
    tax_totals = {"igst": Decimal(0), "cgst": Decimal(0), "sgst": Decimal(0)}
    for item in items:
        taxable = Decimal(money(item.quantity * item.rate))
        if tax_type == "IGST":
            igst, cgst, sgst = Decimal(money(taxable * item.gst_rate / 100)), Decimal(0), Decimal(0)
        else:
            cgst = sgst = Decimal(money(taxable * item.gst_rate / 200))
            igst = Decimal(0)
        gst = igst + cgst + sgst
        row = item.model_dump(mode="json") | {
            "igst_rate": str(item.gst_rate) if tax_type == "IGST" else "0",
            "cgst_rate": str(item.gst_rate / 2) if tax_type != "IGST" else "0",
            "sgst_rate": str(item.gst_rate / 2) if tax_type != "IGST" else "0",
            "taxable": money(taxable),
            "gst": money(gst),
            "igst": money(igst),
            "cgst": money(cgst),
            "sgst": money(sgst),
            "total": money(taxable + gst),
        }
        rows.append(row)
        key = (item.hsn, item.gst_rate)
        group = groups.setdefault(
            key,
            {
                "hsn": item.hsn,
                "gst_rate": str(item.gst_rate),
                "igst_rate": row["igst_rate"],
                "cgst_rate": row["cgst_rate"],
                "sgst_rate": row["sgst_rate"],
                "taxable": Decimal(0),
                "gst": Decimal(0),
                "igst": Decimal(0),
                "cgst": Decimal(0),
                "sgst": Decimal(0),
            },
        )
        for field in ("taxable", "gst", "igst", "cgst", "sgst"):
            group[field] += Decimal(row[field])
        subtotal += taxable
        tax += gst
        quantity += item.quantity
        for field in tax_totals:
            tax_totals[field] += Decimal(row[field])
    return {
        "items": rows,
        "subtotal": money(subtotal),
        "gst_total": money(tax),
        **{field + "_total": money(value) for field, value in tax_totals.items()},
        "grand_total": money(subtotal + tax),
        "amount_in_words": amount_in_words(subtotal + tax),
        "total_quantity": str(quantity),
        "hsn_summary": [
            {k: money(v) if isinstance(v, Decimal) else v for k, v in g.items()}
            for g in groups.values()
        ],
    }
