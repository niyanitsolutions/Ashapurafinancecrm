"""Invoice inputs: money crosses JSON/BSON boundaries as decimal strings."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

Money = Annotated[
    Decimal, Field(ge=0, le=Decimal("999999999999.99"), max_digits=14, decimal_places=2)
]
GST = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]


class InvoiceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    gstin: str = Field(default="", max_length=15, pattern=r"^$|^[0-9]{2}[A-Z0-9]{13}$")
    website: str = Field(default="", max_length=150)
    bank_name: str = Field(default="", max_length=100)
    branch: str = Field(default="", max_length=100)
    account_number: str = Field(default="", max_length=40)
    account_holder: str = Field(default="", max_length=150)
    ifsc: str = Field(default="", pattern=r"^$|^[A-Z]{4}0[A-Z0-9]{6}$")
    prefix: str = Field(default="INV-", pattern=r"^[A-Za-z0-9-]{0,20}$")
    starting_number: int = Field(default=1, ge=1, le=999999999)
    default_gst: GST = Decimal(18)
    default_terms: str = Field(default="", max_length=500)
    signatory: str = Field(default="", max_length=100)
    designation: str = Field(default="", max_length=100)
    signature_s3_key: str | None = None
    show_signature: bool = True
    qr_type: Literal["none", "identifier", "upi"] = "none"
    upi_id: str = Field(default="", max_length=100, pattern=r"^$|^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+$")

    @model_validator(mode="after")
    def qr_valid(self):
        if self.qr_type == "upi" and not self.upi_id:
            raise ValueError("Configure a UPI ID before enabling payment QR.")
        return self


class BillingCustomer(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=150)
    address: str = Field(min_length=1, max_length=500)
    city: str = Field(default="", max_length=80)
    state: str = Field(default="", max_length=80)
    pincode: str = Field(default="", pattern=r"^$|^\d{6}$")
    country: str = Field(default="India", max_length=80)
    gstin: str = Field(default="", pattern=r"^$|^[0-9]{2}[A-Z0-9]{13}$")
    phone: str = Field(default="", max_length=25)
    email: EmailStr | Literal[""] = Field(default="", max_length=150)


class InvoiceItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    description: str = Field(min_length=1, max_length=500)
    hsn: str = Field(pattern=r"^\d{4,8}$")
    quantity: Decimal = Field(gt=0, le=1000000, max_digits=10, decimal_places=3)
    unit: str = Field(default="nos.s", min_length=1, max_length=20)
    rate: Money
    gst_rate: GST


class InvoiceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    customer_id: str | None = None
    customer: BillingCustomer
    invoice_date: date
    due_date: date
    place_of_supply: str = Field(default="", max_length=100)
    terms: str = Field(default="", max_length=500)
    tax_type: Literal["IGST", "CGST_SGST"] = "IGST"
    items: list[InvoiceItem] = Field(min_length=1, max_length=100)
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def dates_valid(self):
        if self.due_date < self.invoice_date:
            raise ValueError("Due date cannot precede invoice date.")
        return self


class StatusInput(BaseModel):
    status: Literal["issued", "paid", "partially_paid", "cancelled"]
    reason: str = Field(default="", max_length=500)
    version: int = Field(ge=1)


class CancelInput(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    version: int = Field(ge=1)
