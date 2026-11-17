"""Confirmed Airtel payload fields; three-credential authentication remains undocumented."""

from typing import Any

from app.core.exceptions import ForbiddenError, ValidationError
from app.features.integrations.models import IntegrationProvider

PROVIDER = "airtel_iq"
ENDPOINT = "https://iqsms.airtel.in/api/v1/send-prepaid-sms"
DEFAULTS = {
    "api_url": ENDPOINT,
    "sender_id": "ASHFNS",
    "dlt_template_id": "1077151820081508033",
    "entity_id": "AIR7316372024",
    "message_type": "TRANSACTIONAL",
    "destination_template": '["{{mobile}}"]',
}
# Credentials are collected securely. Their wire authentication format is not known.
# Legacy header/message parsing values are retained encrypted but cannot authorize a send.
SENSITIVE = frozenset({"customer_id", "username", "password", "authorization_value"})
MASK = "********"
BLOCKED = "Save and validate the complete Airtel IQ configuration, then confirm the account contract. No SMS was sent; activation is unavailable."
APPROVED_MESSAGE = "Your OTP for mobile verification with Ashapura Financial Services is {OTP}. It is valid for 10 minutes. Do not share this OTP with anyone."
ALLOWED = frozenset(
    {
        *DEFAULTS,
        *SENSITIVE,
        "message_type",
        "destination_template",
        "success_field",
        "success_value",
        "message_id_field",
        "contract_confirmed",
    }
)


def validate_config(values: dict[str, str]) -> dict[str, str]:
    if values.keys() - ALLOWED:
        raise ValidationError("Unsupported Airtel IQ configuration fields.")
    data = DEFAULTS | values
    if any(data[key] != value for key, value in DEFAULTS.items() if key != "destination_template"):
        raise ValidationError(
            "Use the supplied Airtel IQ prepaid endpoint and approved sender/DLT identifiers."
        )
    if any(len(value) > 2000 or "\r" in value or "\n" in value for value in data.values()):
        raise ValidationError("Invalid Airtel IQ configuration value.")
    if data.get("contract_confirmed", "false") not in {"true", "false"}:
        raise ValidationError("Invalid Airtel contract confirmation.")
    if data.get("contract_confirmed") == "true" and not contract_ready(data):
        raise ValidationError("Complete and validate the confirmed Airtel configuration first.")
    return data


async def ensure_provider(db: Any) -> None:
    row = IntegrationProvider(integration_type="sms", provider=PROVIDER, label="Airtel IQ")
    await db.integration_providers.update_one(
        {"integration_type": "sms", "provider": PROVIDER},
        {"$setOnInsert": row.model_dump(exclude={"id"})},
        upsert=True,
    )


def contract_ready(config: dict[str, str]) -> bool:
    """Local consistency only; never authenticates or sends an SMS."""
    import json

    try:
        return (
            all(
                config.get(key) == value
                for key, value in DEFAULTS.items()
                if key != "destination_template"
            )
            and bool(config.get("customer_id", "").strip())
            and config.get("customer_id") != MASK
            and all(
                config.get(key, "").strip() and config.get(key) != MASK
                for key in ("username", "password")
            )
            and json.loads(config.get("destination_template", "")) == ["{{mobile}}"]
        )
    except (ValueError, TypeError):
        return False


def confirmed_contract(config: dict[str, str]) -> bool:
    return (
        config.get("contract_confirmed") == "true"
        and contract_ready(config)
        and authentication_ready(config)
    )


def require_owner(actor: Any) -> None:
    if actor.role != "owner":
        raise ForbiddenError("Only the Owner can configure or test Airtel SMS.")


def config_fingerprint(config: dict[str, str]) -> str:
    import json

    from app.features.auth.pin_service import otp_digest

    return otp_digest(
        "airtel-config",
        json.dumps(
            {
                k: v
                for k, v in config.items()
                if k
                not in {
                    "contract_confirmed",
                    "success_field",
                    "success_value",
                    "provider",
                    "_provider",
                }
            },
            sort_keys=True,
        ),
    )


def validation_errors(config: dict[str, str]) -> list[str]:
    import json

    errors = []
    for key, value in DEFAULTS.items():
        if key != "destination_template" and config.get(key) != value:
            errors.append(key + ": use the confirmed Airtel value.")
    if not config.get("customer_id", "").strip() or config.get("customer_id") == MASK:
        errors.append("customer_id: saved Customer ID is required.")
    for key in ("username", "password"):
        if not config.get(key, "").strip() or config.get(key) == MASK:
            errors.append(key + ": a saved credential is required.")
    try:
        valid = json.loads(config.get("destination_template", "")) == ["{{mobile}}"]
    except (ValueError, TypeError):
        valid = False
    if not valid:
        errors.append("destination_template: use one {{mobile}} string in a JSON array.")
    if config.get("contract_confirmed", "false") not in {"false", "true"}:
        errors.append("contract_confirmed: invalid confirmation state.")
    return errors


def require_validated(
    config: Any, values: dict[str, str], *, require_authentication: bool = True
) -> None:
    if (
        not config.airtel_config_validated_at
        or config.airtel_validated_fingerprint != config_fingerprint(values)
    ):
        raise ValidationError(
            "Run successful Validate Configuration (no SMS) on the saved settings first."
        )
    if require_authentication and not authentication_ready(values):
        raise ValidationError(AUTHENTICATION_PENDING)
    if values.get("contract_confirmed") != "true" or not contract_ready(values):
        raise ValidationError("Confirm and save the account-specific Airtel contract first.")


AUTHENTICATION_PENDING = "Airtel authentication is not documented for this prepaid endpoint. Customer ID, Username and Password can be saved securely, but SMS submission and activation are blocked until Airtel confirms the exact authentication mechanism. No SMS was sent."


def authentication_ready(_config: dict[str, str]) -> bool:
    """No runtime flag, guessed scheme or owner-entered header can bypass missing docs."""
    return False
