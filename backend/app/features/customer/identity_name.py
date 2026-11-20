"""Explicit applicant-name keys verified against seed_product_schemas.py."""

from typing import Any

NAME_KEYS = ("full_name", "full_name_as_per_pan_card", "applicant_name_as_per_pan_card")


def actual_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned: str = " ".join(value.split())
    if not cleaned or len(cleaned) > 200 or cleaned.casefold() in {"customer", "name unavailable"}:
        return None
    return cleaned


def application_name(application: Any, schema: dict[str, Any] | None) -> str | None:
    keys = {f.get("key") for f in (schema or {}).get("fields", []) if not f.get("hidden")}
    for key in NAME_KEYS:
        if key in keys and (name := actual_name(application.form_data.get(key))):
            return name
    # Existing model's persisted inline applicant profile, never a user/phone lookup.
    return actual_name((application.pending_profile or {}).get("full_name"))
