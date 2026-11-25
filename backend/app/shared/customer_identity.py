"""Shared identity normalization. India is the existing account/lead numbering policy."""

import re
import unicodedata
from typing import Any


def normalize_mobile(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Enter a valid mobile number.")  # noqa: TRY004
    number = re.sub(r"[\s().-]", "", value)
    if number.startswith("+91"):
        number = number[3:]
    elif number.startswith("0091"):
        number = number[4:]
    elif len(number) == 12 and number.startswith("91"):
        number = number[2:]
    if not re.fullmatch(r"[6-9][0-9]{9}", number):
        raise ValueError("Enter a valid Indian mobile number, optionally prefixed with +91.")
    return number


def normalized_name(value: str) -> str:
    return " ".join(
        "".join(
            c if c.isalnum() else " " for c in unicodedata.normalize("NFKC", value).casefold()
        ).split()
    )


def pan_search_digest(value: str) -> str:
    """Domain-separated keyed exact lookup; never store a plaintext PAN search key."""
    import hashlib
    import hmac

    from app.config.settings import get_settings

    settings = get_settings()
    key = (settings.encryption_key or settings.jwt_secret_key).encode()
    return hmac.new(key, b"customer-pan-search-v1:" + value.strip().upper().encode(), hashlib.sha256).hexdigest()


def mobile_match_pattern(value: str) -> str:
    """Anchored comparison for permitted Indian mobile formatting; no suffix matches."""
    number = normalize_mobile(value)
    return r"^[\s().-]*(?:(?:\+91|0091|91)[\s().-]*)?" + r"[\s().-]*".join(number) + r"[\s().-]*$"
