"""Phase 3.1 — the Product Schema Engine's validation/visibility logic. One place both
`CustomerService.submit_application` and `LeadService.create_lead` call, so "what makes
a field's value valid" is never duplicated or allowed to drift between the Application
and Lead entry points — mirrored (not re-derived) on the frontend in
`components/forms/fieldValidation.ts` for inline UX, but this module is the real gate.
"""

import re
from typing import Any

from app.features.customer.constants import ConditionOperator, FieldFormat, FieldType
from app.features.customer.models import FormFieldDefinition

# One regex per FieldFormat value — the engine-code half of the "engine is code, catalog
# is data" split (a field only ever *names* one of these). Deliberately the common
# Indian KYC/financial formats named in the brief; not exhaustive of every real-world
# edge case (e.g. IFSC's 5th character convention), good enough for a required-shape gate.
_FORMAT_PATTERNS: dict[str, str] = {
    FieldFormat.EMAIL: r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    FieldFormat.MOBILE: r"^[6-9]\d{9}$",
    FieldFormat.PAN: r"^[A-Z]{5}\d{4}[A-Z]$",
    FieldFormat.AADHAAR: r"^\d{12}$",
    FieldFormat.IFSC: r"^[A-Z]{4}0[A-Z0-9]{6}$",
    FieldFormat.GST: r"^\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z]{1}[A-Z\d]{1}$",
    FieldFormat.PINCODE: r"^\d{6}$",
}

_FORMAT_LABELS: dict[str, str] = {
    FieldFormat.EMAIL: "a valid email address",
    FieldFormat.MOBILE: "a valid 10-digit mobile number",
    FieldFormat.PAN: "a valid PAN (e.g. ABCDE1234F)",
    FieldFormat.AADHAAR: "a valid 12-digit Aadhaar number",
    FieldFormat.IFSC: "a valid IFSC code",
    FieldFormat.GST: "a valid GST number",
    FieldFormat.PINCODE: "a valid 6-digit PIN code",
}


def is_field_visible(field: FormFieldDefinition, form_data: dict[str, Any]) -> bool:
    """A field with no `visible_when` is always visible. Otherwise it's visible only
    when the controlling field's current value satisfies the condition — an unset
    controlling field never satisfies `equals`/`in` (there's nothing to match).
    Governance round — an Owner-`hidden` field is never visible, regardless of
    `visible_when`: never rendered, never required, never counted toward progress."""
    if field.hidden:
        return False
    condition = field.visible_when
    if condition is None:
        return True
    current = form_data.get(condition.field_key)
    if condition.operator == ConditionOperator.EQUALS:
        return current == condition.value
    if condition.operator == ConditionOperator.NOT_EQUALS:
        return current != condition.value
    if condition.operator == ConditionOperator.IN:
        return current in (condition.value or [])
    return True


def normalize_field_value(field: FormFieldDefinition, value: Any) -> Any:
    """Governance round — `trim`/`auto_uppercase` are applied to the value before
    `validate_field_value` (and before it's persisted), so a value normalized on the
    way in is what's actually validated and stored — not just cosmetically displayed.
    Non-string values (numbers, booleans, dates) pass through unchanged."""
    validation = field.validation
    if validation is None or not isinstance(value, str):
        return value
    if validation.trim:
        value = value.strip()
    if validation.auto_uppercase:
        value = value.upper()
    return value


def validate_field_value(field: FormFieldDefinition, value: Any) -> str | None:
    """Returns an error message, or None if `value` satisfies `field`'s required/
    min/max/pattern/format rules. Caller decides whether to call this at all for a
    field that's currently hidden (see `is_field_visible`) — a hidden field is never
    required, regardless of what its own `required` flag says. Caller is expected to
    have already run the value through `normalize_field_value`."""
    is_empty = value is None or (isinstance(value, str) and value.strip() == "")
    if is_empty:
        return f"{field.label} is required." if field.required else None

    validation = field.validation
    if validation is None:
        return None

    text = str(value)
    if validation.min_length is not None and len(text) < validation.min_length:
        return f"{field.label} must be at least {validation.min_length} characters."
    if validation.max_length is not None and len(text) > validation.max_length:
        return f"{field.label} must be at most {validation.max_length} characters."
    if validation.format:
        pattern = _FORMAT_PATTERNS.get(validation.format)
        if pattern and not re.match(pattern, text):
            return f"{field.label} must be {_FORMAT_LABELS.get(validation.format, 'in the correct format')}."
    if validation.pattern and not re.match(validation.pattern, text):
        return f"{field.label} is not in the correct format."
    if field.field_type == FieldType.NUMBER:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = None
        if number is not None:
            if validation.min_value is not None and number < validation.min_value:
                return f"{field.label} must be at least {validation.min_value}."
            if validation.max_value is not None and number > validation.max_value:
                return f"{field.label} must be at most {validation.max_value}."
    if field.field_type == FieldType.DATE:
        if validation.min_date is not None and text < validation.min_date:
            return f"{field.label} must be on or after {validation.min_date}."
        if validation.max_date is not None and text > validation.max_date:
            return f"{field.label} must be on or before {validation.max_date}."
    return None


def validate_form_data(fields: list[FormFieldDefinition], form_data: dict[str, Any]) -> list[str]:
    """The full pass over one schema's fields against submitted `form_data` — skips any
    field that's currently hidden by its own `visible_when` condition. Normalizes each
    visible field's value in place (trim/auto_uppercase) before validating it, so what
    gets persisted is what was actually checked. Returns every error found (empty list
    = valid)."""
    errors: list[str] = []
    for field in fields:
        if not is_field_visible(field, form_data):
            continue
        if field.key in form_data:
            form_data[field.key] = normalize_field_value(field, form_data[field.key])
        error = validate_field_value(field, form_data.get(field.key))
        if error:
            errors.append(error)
    return errors
