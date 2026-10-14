from datetime import datetime
from typing import Final, Literal, Self
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator

from app.features.voice_assistant.schemas import StrictInput

API_ORIGIN: Final = "https://api-smartflo.tatateleservices.com"
CALLBACK_EVENTS = {
    "incoming": "Call received on Server",
    "answered": "Call answered by Agent",
    "hangup": "Call hangup (Missed or Answered)",
}


class SmartfloConnectionInput(StrictInput):
    version: int = Field(default=1, ge=1)
    api_base_url: Literal["https://api-smartflo.tatateleservices.com"] = API_ORIGIN
    public_origin: str | None = Field(default=None, max_length=250)
    api_token: SecretStr | None = Field(default=None, min_length=20, max_length=4096)
    callback_token: SecretStr | None = Field(default=None, min_length=32, max_length=256)
    clear_api_token: bool = False
    clear_callback_token: bool = False
    callback_mode: Literal["disabled", "validation_only"] = "disabled"
    token_expires_at: datetime | None = None

    @field_validator("public_origin")
    @classmethod
    def valid_origin(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        host = parsed.hostname or ""
        if (
            parsed.scheme != "https"
            or "." not in host
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or parsed.port not in {None, 443}
            or host.endswith(".localhost")
        ):
            raise ValueError(
                "Enter the deployed public HTTPS origin only, without credentials or paths."
            )
        return f"https://{host}"

    @field_validator("api_token", "callback_token")
    @classmethod
    def valid_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and any(ord(c) < 33 or ord(c) > 126 for c in value.get_secret_value()):
            raise ValueError("Enter a raw token containing printable ASCII without whitespace.")
        return value

    @field_validator("token_expires_at")
    @classmethod
    def aware_expiry(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Token expiry requires a timezone offset.")
        return value

    @model_validator(mode="after")
    def exclusive_secrets(self) -> Self:
        if (self.clear_api_token and self.api_token) or (
            self.clear_callback_token and self.callback_token
        ):
            raise ValueError("Choose token replacement or removal, not both.")
        return self


class SmartfloWebhookInput(StrictInput):
    """CRM mapping of documented variables, not an invented native Smartflo envelope."""

    uuid: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    start_stamp: datetime
    call_status: Literal["Answered", "Missed"] | None = None

    @field_validator("start_stamp")
    @classmethod
    def timestamp_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Configure UTC ISO 8601 timestamps with offset in Smartflo.")
        return value
