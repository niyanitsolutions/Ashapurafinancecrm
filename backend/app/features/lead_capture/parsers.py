"""Module 9B — the generic Webhook -> Provider -> Parser -> Lead pipeline's "Parser"
half. Each capture source has its own payload shape (a website form posts flat JSON;
Meta posts a webhook notification, then a separate Graph API call returns field_data) —
parsing that shape is inherently source-specific code, but every parser produces the
same normalized `ParsedLead`, which the shared pipeline in `service.py` then runs
through the identical validate -> duplicate-check -> `LeadService.create_lead` steps.
Adding a future source (Google Forms, Facebook, a partner API) means adding one more
parser function here, never touching the shared pipeline.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.features.lead_capture.constants import FailureReason

_MOBILE_PATTERN = re.compile(r"^[6-9]\d{9}$")

# Reserved per the user's own recommendation, given at Module 9B's freeze review — "if
# Meta/the website provides those values [campaign/ad set/ad/form/UTM], capture them;
# if not available now, don't force it." Passed through into the Lead's own Timeline
# metadata (see service.py) whenever a source's raw payload happens to carry one of
# these keys — never fabricated when absent.
_METADATA_KEYS = ("form_id", "form_version", "campaign_id", "adset_id", "ad_id", "utm_source", "utm_campaign", "utm_medium")


class CaptureValidationError(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class ParsedLead:
    full_name: str
    mobile: str
    email: str | None
    product_category: str
    product_id: str
    remarks: str | None
    source_metadata: dict[str, str] = field(default_factory=dict)


def normalize_mobile(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits


def extract_source_metadata(payload: dict[str, Any]) -> dict[str, str]:
    return {key: str(payload[key]) for key in _METADATA_KEYS if payload.get(key)}


def parse_website_payload(payload: dict[str, Any]) -> ParsedLead:
    full_name = payload.get("full_name")
    mobile_raw = payload.get("mobile")
    product_category = payload.get("product_category")
    product_id = payload.get("product_id")
    if not full_name or not mobile_raw or not product_category or not product_id:
        raise CaptureValidationError(FailureReason.MISSING_REQUIRED_FIELDS, "full_name, mobile, product_category, and product_id are all required.")

    mobile = normalize_mobile(str(mobile_raw))
    if not _MOBILE_PATTERN.match(mobile):
        raise CaptureValidationError(FailureReason.INVALID_DATA, f"'{mobile_raw}' is not a valid Indian mobile number.")

    return ParsedLead(
        full_name=str(full_name), mobile=mobile, email=payload.get("email"), product_category=str(product_category), product_id=str(product_id),
        remarks=payload.get("remarks"), source_metadata=extract_source_metadata(payload),
    )


def parse_meta_fields(fields: dict[str, str], *, default_product_category: str | None, default_product_id: str | None, raw_entry: dict[str, Any] | None = None) -> ParsedLead:
    full_name = fields.get("full_name")
    mobile_raw = fields.get("mobile")
    if not full_name or not mobile_raw:
        raise CaptureValidationError(FailureReason.MISSING_REQUIRED_FIELDS, "Meta lead is missing a name or phone number field.")

    mobile = normalize_mobile(mobile_raw)
    if not _MOBILE_PATTERN.match(mobile):
        raise CaptureValidationError(FailureReason.INVALID_DATA, f"'{mobile_raw}' is not a valid Indian mobile number.")

    if not default_product_category or not default_product_id:
        # Actionable for whoever reads it in the Capture Failures admin page (Lead
        # Capture Log > Source Mapping already has the form to fix this — no missing
        # UI, just unset data) rather than a code-reference an Owner can't act on.
        raise CaptureValidationError(
            FailureReason.MISSING_REQUIRED_FIELDS,
            "Meta Lead Ads source requires a default Product Category and Product before leads can be created.",
        )

    source_metadata = extract_source_metadata(raw_entry or {})
    # A form's own custom questions (see meta_client.parse_field_data) — folded in here
    # rather than in extract_source_metadata, since that function only ever reads the
    # webhook envelope (raw_entry), never the separately-fetched field_data this value
    # comes from.
    if fields.get("custom_questions"):
        source_metadata = {**source_metadata, "custom_questions": fields["custom_questions"]}

    return ParsedLead(
        full_name=full_name, mobile=mobile, email=fields.get("email"), product_category=default_product_category, product_id=default_product_id,
        remarks=None, source_metadata=source_metadata,
    )
