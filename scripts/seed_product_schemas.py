"""Phase 2 — Product Schema Engine: the real, spec-sourced product catalog.

Every product/section/field/required-document below is transcribed verbatim from the
uploaded product specification (loan + insurance product details). Two things ARE
mechanically assigned rather than copied verbatim, because the engine needs a value for
them and the spec doesn't speak in those terms — both follow one fixed, explainable rule
applied uniformly, never a per-field guess:

  - `field_type` (one of the engine's 6 fixed widget hints — see
    `app.features.customer.constants.FieldType`): DATE only for a literal "Date of
    Birth" field; NUMBER for amount/income/turnover/cost/value/fee/premium/sum-insured/
    vintage-years/duration-style fields; SELECT *only* when the spec's own field text
    already enumerates the options in parentheses/slashes (e.g. "Employment Type
    (Salaried / Self-Employed)") — the options list is exactly that enumeration, never
    invented; TEXTAREA for narrative/history-style fields (existing loan/medical
    details, family details); TEXT otherwise.
  - `required` — False whenever the spec itself qualifies an item with "(if any)" /
    "(if applicable)" / "(if available)" / "(if known)" / "(if required)", True
    otherwise.

No field, section, or document was renamed, merged, simplified, or dropped. Where a
single spec bullet named two distinct things (e.g. "Personal Email ID & Official Email
ID"), it was split into two separate fields rather than merged into one, per instruction.

Document *groupings* (section labels under "Required Documents") reproduce the spec's
own numbered sub-groups where the spec gives them (e.g. Business Loan's "Identity &
Address Proof" / "Business Proof" / "Financial Documents" / "Business Proof Documents").
Where insurance products list required documents as one flat, ungrouped list, they are
grouped here by document nature (Identity & Address Proof / Income Proof / Bank
Documents / Medical Documents / Additional Documents) — a consistent classification
applied the same way to every insurance product, not a per-product invention. Two
products (Used Bike Loan; FD Based Credit Card's "Address Proof") had either no
sub-grouping at all or a section with only one item in the source spec — both are kept
exactly as the spec gave them (a single group), rather than inventing sub-groups. See
the Phase 2 report for the full per-product verification counts.

Products NOT included here (name mentioned with no field/document detail block in the
spec) are deliberately left out — not guessed, not stubbed — pending a future schema
authored through the Owner's own Product Schema CRUD (Phase 1). See the Phase 2 report.

Idempotent: products/document types are upserted by name ($setOnInsert — never
overwritten if already present), and each form definition is upserted by
(product_category, product_id) so a later manual Owner edit is never clobbered by
re-running this script.
"""

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.features.customer.constants import FieldFormat, FieldType, SchemaStatus
from app.features.customer.models import (
    ApplicationFormDefinition,
    FieldValidation,
    FormFieldDefinition,
    RequiredDocumentDefinition,
)
from app.features.system_settings.models import DocumentType, InsuranceProduct, LoanProduct

# --------------------------------------------------------------------------- authoring helpers

_OPTIONAL_MARKERS = ("if any", "if applicable", "if available", "if known", "if required")


def _is_optional(label: str) -> bool:
    lowered = label.lower()
    return any(marker in lowered for marker in _OPTIONAL_MARKERS)


def _slugify(label: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def F(
    label: str,
    field_type: str = FieldType.TEXT,
    *,
    options: list[str] | None = None,
    key: str | None = None,
    validation: FieldValidation | None = None,
) -> FormFieldDefinition:
    """One Basic Information field — `label` is the exact spec text. `validation` is
    schema-driven metadata (format/min/max — see FieldValidation), never a hardcoded
    per-product check; only set where the client's own spec explicitly calls for it."""
    return FormFieldDefinition(
        key=key or _slugify(label), label=label, field_type=field_type, required=not _is_optional(label), options=options,
        validation=validation,
    )


def D(name: str, note: str | None = None) -> tuple[str, str | None]:
    """One required-document entry — `name` becomes/matches a DocumentType master row."""
    return (name, note)


# --------------------------------------------------------------------------- LOAN PRODUCTS

_PERSONAL_LOAN_FIELDS = [
    F("Full Name (as per PAN Card)"),
    F("Mobile Number (Linked with Bank Account)"),
    F("Personal Email ID"),
    F("Official Email ID"),
    F("Gender"),
    F("Date of Birth", FieldType.DATE),
    F("PAN Card Number"),
    F("Aadhaar Card Number"),
    F("Current Residential Address with PIN Code"),
    F("Company Name"),
    F("Company Address With Pincode"),
    F("Designation"),
    F("Monthly Net Salary", FieldType.NUMBER),
    F("Total Work Experience"),
    F("Current Company Experience"),
    F("Existing Loan Details (if any)", FieldType.TEXTAREA),
    F("CIBIL Score (if known)"),
    F("Purpose of Loan"),
    F("Loan Amount Required", FieldType.NUMBER),
]

# Phase 2 — Business Loan Master Product Schema, transcribed field-for-field, in order,
# from the client's own detailed table (label / type / required column). Business Type
# options match the client's own "Business Type Options" list verbatim (note: "Private
# Limited Company", not the shorthand "Pvt. Ltd." used in earlier products' labels).
_BUSINESS_LOAN_FIELDS = [
    F("Business Name"),
    F("Applicant Name (as per PAN Card)"),
    F("Mobile Number (Linked with Bank Account)", validation=FieldValidation(format=FieldFormat.MOBILE)),
    F("Personal Email ID", validation=FieldValidation(format=FieldFormat.EMAIL)),
    F("Gender", FieldType.SELECT, options=["Male", "Female", "Other"]),
    F("Date of Birth", FieldType.DATE),
    F("PAN Card Number", validation=FieldValidation(format=FieldFormat.PAN, auto_uppercase=True)),
    F("Aadhaar Card Number"),
    F("Current Residential Address with PIN Code", FieldType.TEXTAREA),
    F("Business Address with PIN Code", FieldType.TEXTAREA),
    F("Business Type", FieldType.SELECT, options=["Proprietorship", "Partnership", "LLP", "Private Limited Company"]),
    F("Nature of Business"),
    F("Business Vintage (Years in Business)", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
    F("Annual Turnover", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
    F("Loan Amount Required", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
    F("Purpose of Loan", FieldType.TEXTAREA),
    F("Existing Loan Details (if any)", FieldType.TEXTAREA),
    F("CIBIL Score (if known)", FieldType.NUMBER),
]

# Phase 3 — Property Loan Master Product Schema, transcribed field-for-field, in order,
# from the client's own detailed table (label / type / required column).
_PROPERTY_LOAN_FIELDS = [
    F("Full Name"),
    F("Mobile Number", validation=FieldValidation(format=FieldFormat.MOBILE)),
    F("Email ID", validation=FieldValidation(format=FieldFormat.EMAIL)),
    F("Current Residential Address with PIN Code", FieldType.TEXTAREA),
    F("Employment Type", FieldType.SELECT, options=["Salaried", "Self-Employed"], key="employment_type"),
    F("Monthly Income", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
    F("Company / Business Name"),
    F("Existing EMI Details (if any)", FieldType.TEXTAREA),
    F("Property Location", FieldType.TEXTAREA),
    F("Property Value", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
    F("Required Loan Amount", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
    F("Purpose of Loan", FieldType.TEXTAREA),
]

# Phase 3 — every document listed individually, matching the client's own document
# table exactly (never merged with "/" or combined applicant/co-applicant notes the way
# the old, pre-Phase-3 shared Property/Home list did). Property Loan's own, independent
# list — see `_HOME_LOAN_DOCUMENT_GROUPS` (Phase 4) for Home Loan's equally independent
# one; the two are never shared, per each product's own explicit isolation requirement.
_PROPERTY_LOAN_DOCUMENT_GROUPS = [
    (
        "Identity Proof (Any One)",
        [D("Aadhaar Card (Applicant)"), D("Aadhaar Card (Co-applicant)"), D("PAN Card (Applicant)"), D("PAN Card (Co-applicant)")],
    ),
    (
        "Income Documents – Salaried Applicants",
        [D("Last 3 Months Salary Slips"), D("Last 12 Months Salary Bank Statement"), D("Latest Form-16", "if available"), D("Employee ID Card")],
    ),
    (
        "Income Documents – Self-Employed / Business Owners",
        [D("Last 3 Years ITR"), D("Last 3 Years Financial Statements"), D("GST Registration", "if applicable")],
    ),
    ("Business Proof", [D("Last 12 Months Bank Statement")]),
    (
        "Property Documents",
        [
            D("Sale Agreement"),
            D("Sale Deed / Title Deed"),
            D("Mother Deed", "if applicable"),
            D("Khata Certificate & Extract"),
            D("Encumbrance Certificate (EC)"),
            D("Latest Property Tax Receipt"),
            D("Approved Building Plan"),
            D("Occupancy Certificate", "if applicable"),
            D("NOC", "if required"),
            D("Property Photos"),
        ],
    ),
    ("Bank Details", [D("Last 12 Months Bank Statement"), D("Cancelled Cheque")]),
    ("Passport Size Photographs", [D("Applicant Photograph"), D("Co-applicant Photograph")]),
    (
        "Other Documents (If Required)",
        [D("Co-applicant KYC"), D("Existing Loan Statement", "For Balance Transfer"), D("Additional Documents", "requested by Bank/NBFC")],
    ),
]

# Phase 4 — Home Loan Master Product Schema, transcribed field-for-field, in order,
# from the client's own detailed table. Deliberately its own field/validation list, not
# a copy of Property Loan's — the client's Phase 4 brief explicitly requires Home Loan
# to be independently maintainable (see `_HOME_LOAN_DOCUMENT_GROUPS` below): a single
# combined "Personal / Official Email ID" field here (Property Loan/older products keep
# their own field lists exactly as those products' own briefs gave them).
_HOME_LOAN_FIELDS = [
    F("Full Name"),
    F("Mobile Number", validation=FieldValidation(format=FieldFormat.MOBILE)),
    F("Personal / Official Email ID", validation=FieldValidation(format=FieldFormat.EMAIL)),
    F("Current Residential Address with PIN Code", FieldType.TEXTAREA),
    F("Employment Type", FieldType.SELECT, options=["Salaried", "Self-Employed"], key="employment_type"),
    F("Monthly Income", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
    F("Company / Business Name"),
    F("Existing EMI Details (if any)", FieldType.TEXTAREA),
    F("Property Location", FieldType.TEXTAREA),
    F("Property Cost", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
    F("Own Contribution (Down Payment)", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
    F("Required Loan Amount", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
    F("Purpose of Loan", FieldType.TEXTAREA),
]

# Phase 4 — Home Loan's own, fully independent document list (explicit "Isolation
# Rules" in the Phase 4 brief: never share document constants or arrays with Property
# Loan, so a future edit to one can never affect the other — the fact that the client's
# own document names happen to read identically to Property Loan's is coincidental
# content, not a reason to share the Python list). Every document is its own schema
# item, none merged.
_HOME_LOAN_DOCUMENT_GROUPS = [
    (
        "Identity Proof (Any One)",
        [D("Aadhaar Card (Applicant)"), D("Aadhaar Card (Co-applicant)"), D("PAN Card (Applicant)"), D("PAN Card (Co-applicant)")],
    ),
    (
        "Income Documents – Salaried Applicants",
        [D("Last 3 Months Salary Slips"), D("Last 12 Months Salary Bank Statement"), D("Latest Form-16", "if available"), D("Employee ID Card")],
    ),
    (
        "Income Documents – Self-Employed / Business Owners",
        [D("Last 3 Years ITR"), D("Last 3 Years Financial Statements"), D("GST Registration", "if applicable")],
    ),
    ("Business Proof", [D("Last 12 Months Bank Statement")]),
    (
        "Property Documents",
        [
            D("Sale Agreement"),
            D("Sale Deed / Title Deed"),
            D("Mother Deed", "if applicable"),
            D("Khata Certificate & Extract"),
            D("Encumbrance Certificate (EC)"),
            D("Latest Property Tax Receipt"),
            D("Approved Building Plan"),
            D("Occupancy Certificate", "if applicable"),
            D("NOC", "if required"),
            D("Property Photos"),
        ],
    ),
    ("Bank Details", [D("Last 12 Months Bank Statement"), D("Cancelled Cheque")]),
    ("Passport Size Photographs", [D("Applicant Photograph"), D("Co-applicant Photograph")]),
    (
        "Other Documents (If Required)",
        [D("Co-applicant KYC"), D("Existing Loan Statement", "For Balance Transfer"), D("Additional Documents", "requested by Bank / NBFC")],
    ),
]

# Phase 5 — Education Loan, re-verified field-for-field against the client's own
# updated list (a single combined "Personal / Official Email ID" field, same merge
# Home Loan's own brief called for — different products are allowed their own
# structure, not forced into consistency with each other). `Course Duration` is
# NUMBER per this file's own documented rule for duration-style fields (see module
# docstring), matching how `Business Vintage (Years in Business)` is typed elsewhere.
_EDUCATION_LOAN_FIELDS = [
    F("Student's Full Name"),
    F("Parent/Guardian Name"),
    F("Mobile Number", validation=FieldValidation(format=FieldFormat.MOBILE)),
    F("Personal / Official Email ID", validation=FieldValidation(format=FieldFormat.EMAIL)),
    F("Current Residential Address with PIN Code", FieldType.TEXTAREA),
    F("Course Name"),
    F("College/University Name"),
    F("Country (India/Abroad)", FieldType.SELECT, options=["India", "Abroad"], key="country"),
    F("Total Course Fee", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
    F("Required Loan Amount", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
    F("Course Duration", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
    F("Parent/Guardian Occupation"),
    F("Monthly Income", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
]

# Phase 6 — Machinery Loan, re-verified field-for-field against the client's own
# updated list (single combined "Personal / Official Email ID" field, same merge
# pattern as Home/Education Loan). `Business Vintage` is NUMBER per this file's own
# documented rule for vintage-years-style fields.
_MACHINERY_LOAN_FIELDS = [
    F("Applicant/Company Name"),
    F("Mobile Number", validation=FieldValidation(format=FieldFormat.MOBILE)),
    F("Personal / Official Email ID", validation=FieldValidation(format=FieldFormat.EMAIL)),
    F("Business Address with PIN Code", FieldType.TEXTAREA),
    F("Business Type", FieldType.SELECT, options=["Proprietorship", "Partnership", "LLP", "Pvt. Ltd."], key="business_type"),
    F("Nature of Business"),
    F("Business Vintage", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
    F("Annual Turnover", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
    F("Monthly Business Income", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
    F("GST Number (if applicable)"),
    F("Machinery Name & Model"),
    F("Machinery Cost", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
    F("Vendor Name"),
    F("Required Loan Amount", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
    F("Existing Loan/EMI Details (if any)", FieldType.TEXTAREA),
]

# Phase 6 — FD Based Credit Card, re-verified field-for-field against the client's own
# updated list (single combined "Personal / Official Email ID" field).
_FD_CREDIT_CARD_FIELDS = [
    F("Full Name"),
    F("Mobile Number", validation=FieldValidation(format=FieldFormat.MOBILE)),
    F("Personal / Official Email ID", validation=FieldValidation(format=FieldFormat.EMAIL)),
    F("Current Residential Address with PIN Code", FieldType.TEXTAREA),
    F("PAN Number"),
    F("Aadhaar Number"),
    F("Occupation", FieldType.SELECT, options=["Salaried", "Self-Employed", "Student", "Others"], key="occupation"),
    F("Bank Name"),
    F("FD Amount", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
]

# Phase 6 — Used Bike Loan, re-verified field-for-field against the client's own
# updated list (single combined "Personal / Official Email ID" field). Documents are
# unchanged — the client's list (Aadhaar/PAN/RC/photos/statement/insurance) already
# matched exactly what was authored, both flat and ungrouped as this product's own
# spec has always given it (see module docstring).
_USED_BIKE_LOAN_FIELDS = [
    F("Full Name"),
    F("Mobile Number", validation=FieldValidation(format=FieldFormat.MOBILE)),
    F("Personal / Official Email ID", validation=FieldValidation(format=FieldFormat.EMAIL)),
    F("Current Residential Address with PIN Code", FieldType.TEXTAREA),
    F("Employment Type", FieldType.SELECT, options=["Salaried", "Self-Employed"], key="employment_type"),
    F("Monthly Income", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
    F("Company/Business Name"),
    F("Existing EMI Details (if any)", FieldType.TEXTAREA),
    F("Bike Make & Model"),
    F("Manufacturing Year", FieldType.NUMBER),
    F("Registration Number (if available)"),
    F("Purchase Price of the Bike", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
    F("Required Loan Amount", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
    F("Father Name"),
    F("Mother Name"),
    F("Wife Name"),
]

# Phase 6 — Used Car Loan, re-verified field-for-field against the client's own
# updated list (single combined "Personal / Official Email ID" field).
_USED_CAR_LOAN_FIELDS = [
    F("Full Name"),
    F("Mobile Number", validation=FieldValidation(format=FieldFormat.MOBILE)),
    F("Personal / Official Email ID", validation=FieldValidation(format=FieldFormat.EMAIL)),
    F("Current Residential Address with PIN Code", FieldType.TEXTAREA),
    F("Employment Type", FieldType.SELECT, options=["Salaried", "Self-Employed"], key="employment_type"),
    F("Monthly Income", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
    F("Company/Business Name"),
    F("Existing EMI Details (if any)", FieldType.TEXTAREA),
    F("Vehicle Make & Model"),
    F("Manufacturing Year", FieldType.NUMBER),
    F("Registration Number (if available)"),
    F("Purchase Price of the Vehicle", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
    F("Required Loan Amount", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
]

LOAN_PRODUCTS: list[dict] = [
    {
        "name": "Personal Loan",
        "sections": [("Basic Information", _PERSONAL_LOAN_FIELDS)],
        "document_groups": [
            ("Identity & Address Proof", [D("Aadhaar Card"), D("PAN Card")]),
            (
                "Income Proof",
                [
                    D("Salary Slips (Last 3 Months)", "if available, otherwise 1 month payslip mandatory"),
                    D("Bank Statement (Salary Account) / Passbook", "Last 3 Months"),
                ],
            ),
            ("Employment Proof", [D("Company ID Card / Employee ID Card / Offer Letter", "if available")]),
            ("Photographs", [D("Passport Size Photograph", "1 recent")]),
        ],
    },
    {
        "name": "Business Loan",
        "sections": [("Basic Information", _BUSINESS_LOAN_FIELDS)],
        # Phase 2 — every document listed individually, matching the client's own
        # document table exactly (not combined with "/" the way earlier products'
        # groupings were) — see the Phase 2 brief's explicit per-document breakdown.
        "document_groups": [
            ("Identity & Address Proof", [D("Aadhaar Card"), D("PAN Card")]),
            (
                "Business Proof",
                [
                    D("GST Registration Certificate", "if applicable"),
                    D("Shop & Establishment Certificate"),
                    D("Trade Licence"),
                    D("UDYAM Certificate", "if available"),
                    D("Partnership Deed"),
                    D("LLP Agreement"),
                    D("Certificate of Incorporation"),
                ],
            ),
            (
                "Financial Documents",
                [
                    D("Current Account Bank Statement", "Last 6–12 Months"),
                    D("ITR (Income Tax Return)", "Last 2 Years — Applicant & Business"),
                    D("Profit & Loss Account", "Last 2 Years"),
                    D("Balance Sheet", "Last 2 Years"),
                    D("GST Returns", "if applicable"),
                ],
            ),
            (
                "Business Proof Documents",
                [
                    D("Business Address Proof"),
                    D("Business Ownership Proof"),
                    D("Rent Agreement", "if applicable"),
                    D("Shop Photographs"),
                    D("Passport Size Photograph", "1 recent"),
                ],
            ),
        ],
    },
    {
        "name": "Property Loan",
        "sections": [("Basic Information", _PROPERTY_LOAN_FIELDS)],
        "document_groups": _PROPERTY_LOAN_DOCUMENT_GROUPS,
    },
    {
        "name": "Home Loan",
        "sections": [("Basic Information", _HOME_LOAN_FIELDS)],
        "document_groups": _HOME_LOAN_DOCUMENT_GROUPS,
    },
    {
        "name": "Education Loan",
        "sections": [("Basic Information", _EDUCATION_LOAN_FIELDS)],
        # Phase 5 — re-verified against the client's own updated document list; wording
        # matched to this product's own spec text (e.g. "Last 3 Months Salary Slips",
        # "GST Registration") even where a near-identical document exists on another
        # product under slightly different phrasing — each product's document list is
        # independently authored from its own brief, never silently deduped against a
        # different product's DocumentType wording.
        "document_groups": [
            (
                "Student KYC Documents",
                [
                    D("PAN Card", "if available"),
                    D("Aadhaar Card"),
                    D("Passport", "Mandatory for overseas education"),
                    D("Passport Size Photograph"),
                ],
            ),
            (
                "Parent/Co-applicant KYC Documents",
                [D("PAN Card", "Mandatory"), D("Aadhaar Card"), D("Passport / Voter ID / Driving Licence"), D("Passport Size Photograph")],
            ),
            (
                "Address Proof",
                [D("Aadhaar Card"), D("Passport"), D("Driving Licence"), D("Electricity Bill"), D("Rental Agreement", "if applicable")],
            ),
            (
                "Academic Documents",
                [
                    D("10th & 12th Marks Cards"),
                    D("Graduation Mark Sheets", "if applicable"),
                    D("Entrance Exam Score Card", "if applicable"),
                    D("Admission Letter / Offer Letter", "from the Institution"),
                    D("Course Fee Structure"),
                ],
            ),
            (
                "Income Documents (Parent/Co-applicant) – Salaried",
                [D("Last 3 Months Salary Slips"), D("Last 12 Months Salary Account Bank Statement"), D("Latest Form-16", "if available")],
            ),
            (
                "Income Documents (Parent/Co-applicant) – Self-Employed / Business Owners",
                [D("Last 2 Years ITR"), D("Last 2 Years Financial Statements", "if applicable"), D("GST Registration", "if applicable")],
            ),
            ("Business Proof", [D("Last 12 Months Bank Statement")]),
            ("Bank Documents", [D("Last 6 Months Bank Statement"), D("Cancelled Cheque")]),
            (
                "Collateral Documents (If Required)",
                [D("Property Documents"), D("Fixed Deposit (FD) Details"), D("Other Security Documents", "as required by the lender")],
            ),
            (
                "Additional Documents (If Required)",
                [
                    D("Visa Copy", "for overseas education"),
                    D("Passport Copy"),
                    D("Scholarship Letter", "if applicable"),
                    D("Additional Documents", "requested by the bank/NBFC"),
                ],
            ),
        ],
    },
    {
        "name": "Machinery Loan",
        "sections": [("Basic Information", _MACHINERY_LOAN_FIELDS)],
        # Phase 6 — re-verified against the client's own updated document list; wording
        # matched to this product's own spec text.
        "document_groups": [
            ("KYC Documents", [D("PAN Card", "Mandatory"), D("Aadhaar Card"), D("Passport / Driving Licence / Voter ID")]),
            (
                "Address Proof",
                [D("Aadhaar Card"), D("Electricity Bill"), D("Rental Agreement", "if applicable"), D("Business Address Proof")],
            ),
            (
                "Business Documents",
                [
                    D("GST Registration Certificate"),
                    D("UDYAM/MSME Registration", "if available"),
                    D("Shop & Establishment Certificate"),
                    D("Trade Licence", "if applicable"),
                    D("Partnership Deed / LLP Agreement / MOA & AOA", "as applicable"),
                ],
            ),
            (
                "Financial Documents",
                [
                    D("Last 2 Years Income Tax Returns (ITR)"),
                    D("Last 2 Years Financial Statements (Balance Sheet & Profit & Loss)"),
                    D("Last 12 Months Business Bank Statement"),
                    D("GST Returns", "if applicable"),
                ],
            ),
            (
                "Machinery Documents",
                [
                    D("Quotation/Proforma Invoice of Machinery"),
                    D("Machinery Specifications"),
                    D("Vendor Details"),
                    D("Purchase Order", "if available"),
                ],
            ),
            ("Bank Documents", [D("Last 12 Months Business Bank Statement"), D("Cancelled Cheque")]),
            ("Photographs", [D("Passport Size Photograph", "of Applicant/Partners/Directors")]),
            (
                "Additional Documents (If Required)",
                [
                    D("Existing Loan Statement"),
                    D("Collateral Documents", "if required"),
                    D("Project Report", "for high-value loans"),
                    D("Additional Documents", "requested by the bank/NBFC"),
                ],
            ),
        ],
    },
    {
        "name": "FD Based Credit Card",
        "sections": [("Basic Information", _FD_CREDIT_CARD_FIELDS)],
        "document_groups": [
            ("KYC Documents", [D("Aadhaar Card"), D("PAN Card")]),
            ("Address Proof", [D("Rental Agreement", "if applicable")]),
            ("Bank Documents", [D("Savings Account Passbook or Statement"), D("Cancelled Cheque", "if required")]),
        ],
    },
    {
        "name": "Used Bike Loan",
        "sections": [("Basic Information", _USED_BIKE_LOAN_FIELDS)],
        # Source spec gives one flat, ungrouped document list for this product (unlike
        # every other loan) — kept as a single "Required Documents" group rather than
        # inventing sub-groups it doesn't have.
        "document_groups": [
            (
                "Required Documents",
                [
                    D("Aadhaar Card"),
                    D("PAN Card"),
                    D("RC Copy"),
                    D("Bike Photographs (Front & Back)"),
                    D("Meter Photo"),
                    D("Bank Statement (12 Months)", "1st May to till date"),
                    D("Insurance Policy (Soft Copy)"),
                ],
            )
        ],
    },
    {
        "name": "Used Car Loan",
        "sections": [("Basic Information", _USED_CAR_LOAN_FIELDS)],
        "document_groups": [
            ("KYC Documents", [D("Aadhaar Card"), D("PAN Card"), D("Driving Licence")]),
            ("Address Proof", [D("Aadhaar Card"), D("Driving Licence"), D("Rental Agreement", "if applicable")]),
            (
                "Income Documents – Salaried Applicants",
                [D("Last 3 Months Salary Slips"), D("Last 12 Months Salary Account Bank Statement"), D("Latest Form-16", "if available"), D("Employee ID Card")],
            ),
            (
                "Income Documents – Self-Employed / Business Owners",
                [D("Last 2 Years ITR"), D("Last 2 Years Financial Statements", "if applicable")],
            ),
            (
                "Vehicle Documents",
                [
                    D("Registration Certificate (RC)"),
                    D("Insurance Copy"),
                    D("Pollution Under Control (PUC) Certificate"),
                    D("Vehicle Invoice", "if available"),
                ],
            ),
            ("Bank Documents", [D("Last 12 Months Bank Statement"), D("Cancelled Cheque")]),
            (
                "Photographs",
                [D("Vehicle Photographs (4 Photos)", "Front, Back or L-R both sides"), D("Odometer Photo")],
            ),
            ("Additional Documents", [D("Existing Car Loan Statement", "for refinance")]),
        ],
    },
]

# --------------------------------------------------------------------------- LIFE INSURANCE
#
# Phase 7 — all 7 products re-verified field-for-field and document-for-document
# against the client's own updated per-product lists. Real Mobile/Email format and
# positive-number validation added throughout (this file's now-established convention,
# applied consistently even where not restated). Bank Statement wording follows each
# product's own text exactly: "Last 6 Months Bank Statement" only where that product's
# own list says so (Smart Secure Plus, Smart Term Plan Plus); plain "Bank Statement"
# everywhere else, since the other 5 products' own lists drop the time qualifier.

_LIFE_IDENTITY_DOCS = [D("PAN Card"), D("Aadhaar Card"), D("Passport / Driving Licence / Voter ID"), D("Passport Size Photograph")]

LIFE_INSURANCE_PRODUCTS: list[dict] = [
    {
        "name": "Smart Secure Plus Plan (Term Insurance)",
        "description": (
            "Pure Term Life Insurance Plan. Financial protection for your family in case of the "
            "policyholder's death. Optional Critical Illness & Accidental Death Riders. Flexible "
            "premium payment options. Lump Sum / Monthly Income / Combination payout options. "
            "Coverage up to age 85 (selected variants)."
        ),
        "sections": [
            (
                "Basic Information",
                [
                    F("Full Name"),
                    F("Date of Birth", FieldType.DATE),
                    F("Gender"),
                    F("Mobile Number", validation=FieldValidation(format=FieldFormat.MOBILE)),
                    F("Email ID", validation=FieldValidation(format=FieldFormat.EMAIL)),
                    F("Occupation"),
                    F("Annual Income", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
                    F("Smoking Status"),
                    F("Sum Assured Required", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
                    F("Nominee Details", FieldType.TEXTAREA),
                ],
            )
        ],
        "document_groups": [
            ("Identity & Address Proof", _LIFE_IDENTITY_DOCS),
            ("Income Proof", [D("Income Proof", "Salary Slips / ITR / Form-16")]),
            ("Bank Documents", [D("Last 6 Months Bank Statement"), D("Cancelled Cheque")]),
            ("Medical Documents", [D("Medical Reports", "if required")]),
        ],
    },
    {
        "name": "Smart Term Plan Plus",
        "description": (
            "Affordable Pure Term Insurance. High Life Cover at Low Premium. Death Benefit. "
            "Critical Illness & Disability Riders. Flexible Premium Payment Options. Tax Benefits "
            "as per applicable laws."
        ),
        "sections": [
            (
                "Basic Information",
                [
                    F("Name"),
                    F("Date of Birth", FieldType.DATE),
                    F("Gender"),
                    F("Mobile Number", validation=FieldValidation(format=FieldFormat.MOBILE)),
                    F("Email ID", validation=FieldValidation(format=FieldFormat.EMAIL)),
                    F("Annual Income", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
                    F("Occupation"),
                    F("Nominee Details", FieldType.TEXTAREA),
                ],
            )
        ],
        "document_groups": [
            ("Identity & Address Proof", [D("PAN Card"), D("Aadhaar Card"), D("Address Proof"), D("Passport Size Photograph")]),
            ("Income Proof", [D("Income Proof")]),
            ("Bank Documents", [D("Last 6 Months Bank Statement")]),
            ("Medical Documents", [D("Medical Reports", "if applicable")]),
        ],
    },
    {
        "name": "Savings Advantage Plan",
        "description": (
            "Guaranteed Savings + Life Insurance. Regular Savings Plan. Maturity Benefits. Death "
            "Benefit. Flexible Premium Payment Options. Long-term Wealth Creation."
        ),
        "sections": [
            (
                "Basic Information",
                [
                    F("Name"),
                    F("Mobile Number", validation=FieldValidation(format=FieldFormat.MOBILE)),
                    F("Email ID", validation=FieldValidation(format=FieldFormat.EMAIL)),
                    F("Date of Birth", FieldType.DATE),
                    F("Gender"),
                    F("Annual Income", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
                    F("Premium Budget", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
                    F("Nominee Details", FieldType.TEXTAREA),
                ],
            )
        ],
        "document_groups": [
            ("Identity & Address Proof", [D("PAN Card"), D("Aadhaar Card"), D("Address Proof"), D("Passport Size Photograph")]),
            ("Bank Documents", [D("Bank Statement"), D("Cancelled Cheque")]),
        ],
    },
    {
        "name": "Smart Wealth Advantage Guarantee Plan",
        "description": (
            "Guaranteed Returns. Guaranteed Income. Life Insurance Cover. Wealth Creation. "
            "Long-Term Financial Planning. Tax Benefits as per applicable laws."
        ),
        "sections": [
            (
                "Basic Information",
                [
                    F("Name"),
                    F("Date of Birth", FieldType.DATE),
                    F("Gender"),
                    F("Mobile Number", validation=FieldValidation(format=FieldFormat.MOBILE)),
                    F("Email ID", validation=FieldValidation(format=FieldFormat.EMAIL)),
                    F("Annual Income", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
                    F("Investment Amount", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
                    F("Nominee Details", FieldType.TEXTAREA),
                ],
            )
        ],
        "document_groups": [
            ("Identity & Address Proof", [D("PAN Card"), D("Aadhaar Card"), D("Address Proof"), D("Passport Size Photograph")]),
            ("Bank Documents", [D("Bank Statement"), D("Cancelled Cheque")]),
            ("Income Proof", [D("Income Proof", "if required")]),
        ],
    },
    {
        "name": "Smart Wealth Income Plan",
        "description": "Guaranteed Regular Income. Life Insurance Cover. Savings + Income. Flexible Premium Payment. Long-Term Financial Security.",
        "sections": [
            (
                "Basic Information",
                [
                    F("Name"),
                    F("Mobile Number", validation=FieldValidation(format=FieldFormat.MOBILE)),
                    F("Date of Birth", FieldType.DATE),
                    F("Gender"),
                    F("Email ID", validation=FieldValidation(format=FieldFormat.EMAIL)),
                    F("Premium Amount", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
                    F("Income Requirement", FieldType.TEXTAREA),
                    F("Nominee Details", FieldType.TEXTAREA),
                ],
            )
        ],
        "document_groups": [
            ("Identity & Address Proof", [D("PAN Card"), D("Aadhaar Card"), D("Address Proof"), D("Passport Size Photograph")]),
            ("Bank Documents", [D("Bank Statement"), D("Cancelled Cheque")]),
        ],
    },
    {
        "name": "Online Savings Plan Plus (ULIP)",
        "description": (
            "Market-Linked Investment Plan (ULIP). Equity & Debt Fund Options. Life Insurance "
            "Cover. Long-Term Wealth Creation. Fund Switching Facility. Tax Benefits as per "
            "applicable laws."
        ),
        "sections": [
            (
                "Basic Information",
                [
                    F("Name"),
                    F("Mobile Number", validation=FieldValidation(format=FieldFormat.MOBILE)),
                    F("Email ID", validation=FieldValidation(format=FieldFormat.EMAIL)),
                    F("Date of Birth", FieldType.DATE),
                    F("Gender"),
                    F("Investment Amount", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
                    F("Risk Profile"),
                    F("Nominee Details", FieldType.TEXTAREA),
                ],
            )
        ],
        "document_groups": [
            ("Identity & Address Proof", [D("PAN Card"), D("Aadhaar Card"), D("Address Proof"), D("Passport Size Photograph")]),
            ("Income Proof", [D("Income Proof")]),
            ("Bank Documents", [D("Bank Statement"), D("Cancelled Cheque")]),
        ],
    },
    {
        "name": "Fast Track Super Plan (ULIP)",
        "description": (
            "Unit Linked Insurance Plan (ULIP). Market-Linked Returns. Life Insurance Protection. "
            "Multiple Fund Options. Long-Term Wealth Creation. Partial Withdrawal Facility (as per "
            "policy terms)."
        ),
        "sections": [
            (
                "Basic Information",
                [
                    F("Name"),
                    F("Mobile Number", validation=FieldValidation(format=FieldFormat.MOBILE)),
                    F("Date of Birth", FieldType.DATE),
                    F("Gender"),
                    F("Email ID", validation=FieldValidation(format=FieldFormat.EMAIL)),
                    F("Investment Amount", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
                    F("Occupation"),
                    F("Annual Income", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
                    F("Nominee Details", FieldType.TEXTAREA),
                ],
            )
        ],
        "document_groups": [
            ("Identity & Address Proof", [D("PAN Card"), D("Aadhaar Card"), D("Address Proof"), D("Passport Size Photograph")]),
            ("Income Proof", [D("Income Proof")]),
            ("Bank Documents", [D("Bank Statement"), D("Cancelled Cheque")]),
        ],
    },
]

# --------------------------------------------------------------------------- HEALTH INSURANCE
#
# Phase 8 — all 8 products re-verified field-for-field and document-for-document
# against the client's own updated per-product lists. Real Mobile/Email format and
# positive-number validation added throughout, matching every prior phase's
# established convention. Two documents were corrected to each product's own literal
# name where it genuinely differed from what had been authored (Prime Senior's
# "Existing Policy Details" not "Previous Policy Details"; Super Top Up's "Medical
# Documents" not "Medical Reports"; Critical Illness Plan's plain "Passport Photo" not
# "Passport Size Photograph" with the alt name stuffed into the note field).

HEALTH_INSURANCE_PRODUCTS: list[dict] = [
    {
        "name": "ManipalCigna ProHealth Prime",
        "description": (
            "Comprehensive Health Insurance Plan. Individual & Family Floater Options. "
            "Hospitalization Expenses Cover. Cashless Treatment Facility. Pre & Post "
            "Hospitalization Expenses. Restoration Benefit. Annual Health Check-up. "
            "Customizable Health Cover Options. Sum Insured options available from ₹3 Lakh to "
            "₹1 Crore (as per plan variant)."
        ),
        "sections": [
            (
                "Basic Information",
                [
                    F("Full Name"),
                    F("Date of Birth", FieldType.DATE),
                    F("Gender"),
                    F("Mobile Number", validation=FieldValidation(format=FieldFormat.MOBILE)),
                    F("Email ID", validation=FieldValidation(format=FieldFormat.EMAIL)),
                    F("Occupation"),
                    F("Annual Income", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
                    F("Height & Weight"),
                    F("Medical History", FieldType.TEXTAREA),
                    F("Existing Diseases", FieldType.TEXTAREA),
                    F("Family Member Details", FieldType.TEXTAREA),
                ],
            )
        ],
        "document_groups": [
            ("Identity & Address Proof", [D("PAN Card"), D("Aadhaar Card"), D("Address Proof"), D("Passport Size Photograph")]),
            ("Medical Documents", [D("Medical Reports", "if required")]),
            ("Additional Documents", [D("Previous Policy Details", "if applicable")]),
        ],
    },
    {
        "name": "ManipalCigna Sarvah Health Insurance",
        "description": (
            "Comprehensive Health Protection Plan. Individual & Family Coverage. Hospitalization "
            "Cover. Long-Term Health Security. Wide Range of Benefits & Add-on Options. Suitable "
            "for Family Protection."
        ),
        "sections": [
            (
                "Basic Information",
                [
                    F("Name"),
                    F("Date of Birth", FieldType.DATE),
                    F("Gender"),
                    F("Mobile Number", validation=FieldValidation(format=FieldFormat.MOBILE)),
                    F("Email ID", validation=FieldValidation(format=FieldFormat.EMAIL)),
                    F("Occupation"),
                    F("Income Details", FieldType.TEXTAREA),
                    F("Family Details", FieldType.TEXTAREA),
                    F("Medical History", FieldType.TEXTAREA),
                    F("Required Sum Insured", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
                ],
            )
        ],
        "document_groups": [
            ("Identity & Address Proof", [D("PAN Card"), D("Aadhaar Card"), D("Address Proof"), D("Passport Size Photograph")]),
            ("Medical Documents", [D("Medical Reports", "if required")]),
            ("Additional Documents", [D("Previous Health Policy Copy", "if available")]),
        ],
    },
    {
        "name": "ManipalCigna Prime Senior (Senior Citizen Health Insurance)",
        "description": (
            "Health Insurance Plan for Senior Citizens. Protection Against Hospitalization "
            "Expenses. Suitable for Parents & Elderly Customers. Medical Coverage Based on "
            "Eligibility. Financial Protection Against Healthcare Costs."
        ),
        "sections": [
            (
                "Basic Information",
                [
                    F("Name"),
                    F("Date of Birth", FieldType.DATE),
                    F("Gender"),
                    F("Mobile Number", validation=FieldValidation(format=FieldFormat.MOBILE)),
                    F("Email ID", validation=FieldValidation(format=FieldFormat.EMAIL)),
                    F("Medical History", FieldType.TEXTAREA),
                    F("Existing Diseases", FieldType.TEXTAREA),
                    F("Required Coverage Amount", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
                    F("Nominee Details", FieldType.TEXTAREA),
                ],
            )
        ],
        "document_groups": [
            ("Identity & Address Proof", [D("PAN Card"), D("Aadhaar Card"), D("Address Proof"), D("Passport Size Photograph")]),
            ("Medical Documents", [D("Medical Reports")]),
            ("Additional Documents", [D("Existing Policy Details", "if applicable")]),
        ],
    },
    {
        "name": "ManipalCigna Super Top Up Plan",
        "description": (
            "Additional Health Cover Over Existing Policy. Helps Manage High Medical Expenses. "
            "Affordable Premium Option. Suitable for Customers Already Having Base Health "
            "Insurance. Extra Financial Protection Layer."
        ),
        "sections": [
            (
                "Basic Information",
                [
                    F("Name"),
                    F("Date of Birth", FieldType.DATE),
                    F("Gender"),
                    F("Mobile Number", validation=FieldValidation(format=FieldFormat.MOBILE)),
                    F("Email ID", validation=FieldValidation(format=FieldFormat.EMAIL)),
                    F("Existing Health Cover Amount", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
                    F("Required Additional Cover", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
                    F("Family Details", FieldType.TEXTAREA),
                ],
            )
        ],
        "document_groups": [
            ("Identity & Address Proof", [D("PAN Card"), D("Aadhaar Card"), D("Address Proof")]),
            ("Additional Documents", [D("Existing Health Insurance Details")]),
            ("Medical Documents", [D("Medical Documents", "if required")]),
        ],
    },
    {
        "name": "ManipalCigna Critical Illness Plan",
        "description": (
            "Protection Against Major Critical Diseases. Lump Sum Benefit on Diagnosis of "
            "Covered Illness. Helps Manage Treatment Expenses & Income Loss. Additional "
            "Financial Security."
        ),
        "sections": [
            (
                "Basic Information",
                [
                    F("Name"),
                    F("Date of Birth", FieldType.DATE),
                    F("Gender"),
                    F("Mobile Number", validation=FieldValidation(format=FieldFormat.MOBILE)),
                    F("Email ID", validation=FieldValidation(format=FieldFormat.EMAIL)),
                    F("Occupation"),
                    F("Annual Income", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
                    F("Medical History", FieldType.TEXTAREA),
                    F("Required Coverage Amount", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
                ],
            )
        ],
        "document_groups": [
            ("Identity & Address Proof", [D("PAN Card"), D("Aadhaar Card"), D("Address Proof"), D("Passport Photo")]),
            ("Medical Documents", [D("Medical Reports")]),
            ("Income Proof", [D("Income Proof", "if required")]),
        ],
    },
    {
        "name": "ManipalCigna Accident Shield / Personal Accident Plan",
        "description": (
            "Accidental Death Protection. Permanent Disability Cover. Financial Support for "
            "Family. Accident Risk Protection. Suitable for Working Professionals & Business "
            "Owners."
        ),
        "sections": [
            (
                "Basic Information",
                [
                    F("Name"),
                    F("Date of Birth", FieldType.DATE),
                    F("Gender"),
                    F("Mobile Number", validation=FieldValidation(format=FieldFormat.MOBILE)),
                    F("Email ID", validation=FieldValidation(format=FieldFormat.EMAIL)),
                    F("Occupation"),
                    F("Annual Income", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
                    F("Nominee Details", FieldType.TEXTAREA),
                ],
            )
        ],
        "document_groups": [
            ("Identity & Address Proof", [D("PAN Card"), D("Aadhaar Card"), D("Address Proof"), D("Passport Size Photograph")]),
            ("Income Proof", [D("Income Proof", "if required")]),
        ],
    },
    {
        "name": "ManipalCigna Lifestyle Protection – Critical Care",
        "description": (
            "Critical Illness Financial Protection. Helps During Serious Medical Conditions. "
            "Lump Sum Financial Support. Protection Against Major Health Risks."
        ),
        "sections": [
            (
                "Basic Information",
                [
                    F("Name"),
                    F("Date of Birth", FieldType.DATE),
                    F("Gender"),
                    F("Mobile Number", validation=FieldValidation(format=FieldFormat.MOBILE)),
                    F("Email ID", validation=FieldValidation(format=FieldFormat.EMAIL)),
                    F("Occupation"),
                    F("Medical History", FieldType.TEXTAREA),
                    F("Coverage Requirement", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
                ],
            )
        ],
        "document_groups": [
            ("Identity & Address Proof", [D("PAN Card"), D("Aadhaar Card"), D("Address Proof"), D("Passport Size Photograph")]),
            ("Medical Documents", [D("Medical Reports", "if required")]),
        ],
    },
    {
        "name": "ManipalCigna Daily Cash Plan",
        "description": (
            "Daily Cash Benefit During Hospitalization. Helps Manage Non-Medical Expenses. "
            "Additional Support Along With Health Insurance."
        ),
        "sections": [
            (
                "Basic Information",
                [
                    F("Name"),
                    F("Date of Birth", FieldType.DATE),
                    F("Gender"),
                    F("Mobile Number", validation=FieldValidation(format=FieldFormat.MOBILE)),
                    F("Email ID", validation=FieldValidation(format=FieldFormat.EMAIL)),
                    F("Occupation"),
                    F("Hospitalization Cover Requirement", FieldType.NUMBER, validation=FieldValidation(min_value=0)),
                ],
            )
        ],
        "document_groups": [
            ("Identity & Address Proof", [D("PAN Card"), D("Aadhaar Card"), D("Address Proof"), D("Passport Photo")]),
        ],
    },
]

# --------------------------------------------------------------------------- seeding

# Products named in the spec but with no field/document detail block given — deliberately
# NOT built (per instruction: never guess a product or its fields). Reported, not stubbed.
PRODUCTS_NOT_YET_DEFINED: list[str] = [
    "Gold Loan",
    "Vehicle Insurance",
    "Travel Insurance",
    "Mortgage Loan",
    "Agriculture Loan",
]


async def _upsert_by_name(collection, name: str, factory) -> str:
    existing = await collection.find_one({"name": name, "is_deleted": False})
    if existing:
        return str(existing["_id"])
    payload = factory().model_dump(by_alias=True, exclude={"id"})
    result = await collection.insert_one(payload)
    return str(result.inserted_id)


async def seed_real_product_schemas() -> None:
    db: AsyncIOMotorDatabase = get_database()
    loan_products = db["loan_products"]
    insurance_products = db["insurance_products"]
    document_types = db["document_types"]
    form_definitions = db["application_form_definitions"]

    document_type_ids: dict[str, str] = {}

    async def _doc_type_id(name: str) -> str:
        if name not in document_type_ids:
            document_type_ids[name] = await _upsert_by_name(document_types, name, lambda: DocumentType(name=name))
        return document_type_ids[name]

    async def _seed_one(category: str, products_collection, entry: dict) -> tuple[str, int, int, int]:
        name = entry["name"]
        if category == "loan":
            product_id = await _upsert_by_name(products_collection, name, lambda: LoanProduct(name=name))
        else:
            product_id = await _upsert_by_name(
                products_collection, name, lambda: InsuranceProduct(name=name, description=entry.get("description"))
            )

        fields: list[FormFieldDefinition] = []
        for section_name, section_fields in entry["sections"]:
            for field in section_fields:
                fields.append(field.model_copy(update={"section": section_name}))

        required_documents: list[RequiredDocumentDefinition] = []
        for group_name, docs in entry["document_groups"]:
            for doc_name, note in docs:
                doc_id = await _doc_type_id(doc_name)
                required_documents.append(RequiredDocumentDefinition(document_type_id=doc_id, section=group_name, note=note))

        definition = ApplicationFormDefinition(
            product_category=category,
            product_id=product_id,
            fields=fields,
            required_documents=required_documents,
            status=SchemaStatus.ACTIVE,
        )
        payload = definition.model_dump(by_alias=True, exclude={"id"})
        await form_definitions.update_one(
            {"product_category": category, "product_id": product_id}, {"$setOnInsert": payload}, upsert=True
        )
        section_count = len(entry["sections"])
        doc_group_count = len(entry["document_groups"])
        return name, section_count, len(fields), len(required_documents)

    summary: list[tuple[str, str, int, int, int]] = []
    for entry in LOAN_PRODUCTS:
        name, sections, field_count, doc_count = await _seed_one("loan", loan_products, entry)
        summary.append(("loan", name, sections, field_count, doc_count))
    for entry in LIFE_INSURANCE_PRODUCTS:
        name, sections, field_count, doc_count = await _seed_one("insurance", insurance_products, entry)
        summary.append(("insurance/life", name, sections, field_count, doc_count))
    for entry in HEALTH_INSURANCE_PRODUCTS:
        name, sections, field_count, doc_count = await _seed_one("insurance", insurance_products, entry)
        summary.append(("insurance/health", name, sections, field_count, doc_count))

    print(f"product schemas: ensured {len(summary)} entries ({len(document_type_ids)} distinct document types)")
    for category, name, sections, field_count, doc_count in summary:
        print(f"  [{category}] {name}: {sections} section(s), {field_count} field(s), {doc_count} required document(s)")
    if PRODUCTS_NOT_YET_DEFINED:
        print(f"product schemas: {len(PRODUCTS_NOT_YET_DEFINED)} product(s) intentionally NOT seeded (no spec detail): {', '.join(PRODUCTS_NOT_YET_DEFINED)}")
