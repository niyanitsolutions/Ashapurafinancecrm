import re

_MOBILE_RE = re.compile(r"^[6-9]\d{9}$")  # Indian 10-digit mobile numbers


def is_valid_mobile(mobile: str) -> bool:
    return bool(_MOBILE_RE.match(mobile))
