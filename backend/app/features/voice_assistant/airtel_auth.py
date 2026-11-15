"""Airtel guide v1.0.0 pp9–10. Sign the exact bytes sent, never log headers."""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from email.utils import format_datetime


def signed_headers(app_id: str, api_key: str, body: bytes, *, at: datetime) -> dict[str, str]:
    if at.tzinfo is None or not app_id or not api_key:
        raise ValueError("Airtel signing requires credentials and an aware timestamp.")
    if any(ord(char) < 32 or ord(char) > 126 for char in app_id + api_key):
        raise ValueError("Airtel signing credentials must contain printable ASCII.")
    stamp = format_datetime(at.astimezone(UTC), usegmt=True)
    digest = "SHA-256=" + base64.b64encode(hashlib.sha256(body).digest()).decode("ascii")
    canonical = f"x-date: {stamp}\ndigest: {digest}"
    signature = base64.b64encode(
        hmac.new(api_key.encode(), canonical.encode(), hashlib.sha256).digest()
    ).decode("ascii")
    authorization = (
        f'hmac username={json.dumps(app_id)}, algorithm="hmac-sha256", '
        f'headers="x-date digest", signature={json.dumps(signature)}'
    )
    return {
        "Authorization": authorization,
        "Digest": digest,
        "X-Date": stamp,
        "Content-Type": "application/json",
    }
