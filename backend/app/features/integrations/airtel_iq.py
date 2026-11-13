"""Airtel prepaid configuration stage. Unconfirmed account rules remain explicit configuration."""

from typing import Any

from app.core.exceptions import ValidationError
from app.features.integrations.models import IntegrationProvider

PROVIDER = "airtel_iq"
ENDPOINT = "https://iqsms.airtel.in/api/v1/send-prepaid-sms"
DEFAULTS = {
    "api_url": ENDPOINT,
    "sender_id": "ASHFNS",
    "dlt_template_id": "1077151820081508033",
    "entity_id": "1001474305342749488",
}
# username/password and message_id_field remain accepted for saved-config compatibility;
# they are never used to infer authentication or sent in the Airtel request.
SENSITIVE = frozenset({"customer_id", "username", "password", "authorization_value"})
MASK = "********"
BLOCKED = "Airtel IQ prepaid API contract is awaiting confirmation. No SMS was sent; activation is unavailable."
APPROVED_MESSAGE = "Your OTP for mobile verification with Ashapura Financial Services is {#numeric#}. It is valid for 10 minutes. Do not share this OTP with anyone."
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
    if any(data[key] != value for key, value in DEFAULTS.items()):
        raise ValidationError(
            "Use the supplied Airtel IQ prepaid endpoint and approved sender/DLT identifiers."
        )
    if any(len(value) > 2000 or "\r" in value or "\n" in value for value in data.values()):
        raise ValidationError("Invalid Airtel IQ configuration value.")
    # No guessed messageType or authentication mode is supplied by this stage.
    return data


async def ensure_provider(db: Any) -> None:
    row = IntegrationProvider(integration_type="sms", provider=PROVIDER, label="Airtel IQ")
    await db.integration_providers.update_one(
        {"integration_type": "sms", "provider": PROVIDER},
        {"$setOnInsert": row.model_dump(exclude={"id"})},
        upsert=True,
    )


CONTRACT_KEYS = (
    "customer_id",
    "authorization_value",
    "message_type",
    "destination_template",
    "success_field",
    "success_value",
)


def confirmed_contract(config: dict[str, str]) -> bool:
    import json

    if config.get("contract_confirmed") != "true" or any(
        not config.get(key, "").strip() for key in CONTRACT_KEYS
    ):
        return False
    try:
        target = json.loads(config["destination_template"].replace("{{mobile}}", "9000000000"))
        expected = json.loads(config["success_value"])
        return (
            isinstance(target, list)
            and len(target) == 1
            and isinstance(target[0], str)
            and bool(target[0].strip())
            and config["destination_template"].count("{{mobile}}") == 1
            and type(expected) in (str, int, bool)
            and bool(config["success_field"].strip())
        )
    except (ValueError, TypeError):
        return False
