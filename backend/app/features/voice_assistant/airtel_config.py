"""Write-only Airtel VoiceBOT settings, distinct from existing Airtel SMS."""

from typing import Self

from pydantic import Field, SecretStr, field_validator, model_validator

from app.features.voice_assistant.schemas import StrictInput
from app.features.voice_assistant.smartflo_config import SmartfloConnectionInput


class AirtelConnectionInput(StrictInput):
    version: int = Field(default=1, ge=1, strict=True)
    public_origin: str | None = Field(default=None, max_length=250)
    app_id: SecretStr | None = Field(default=None, min_length=1, max_length=256)
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=4096)
    clear_credentials: bool = False
    account_sid: str | None = Field(
        default=None, min_length=1, max_length=256, pattern=r"^[A-Za-z0-9_-]+$"
    )
    caller_id: str | None = Field(default=None, pattern=r"^\+?[1-9][0-9]{7,14}$")
    call_flow_id: str | None = Field(
        default=None, min_length=1, max_length=256, pattern=r"^[A-Za-z0-9_-]+$"
    )
    requested_concurrency: int = Field(default=500, ge=1, le=500, strict=True)

    @field_validator("public_origin")
    @classmethod
    def origin(cls, value: str | None) -> str | None:
        return SmartfloConnectionInput.valid_origin(value)

    @field_validator("app_id", "api_key")
    @classmethod
    def secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and any(ord(c) < 33 or ord(c) > 126 for c in value.get_secret_value()):
            raise ValueError("Use printable ASCII credentials without whitespace.")
        return value

    @model_validator(mode="after")
    def paired(self) -> Self:
        if bool(self.app_id) != bool(self.api_key) or (self.clear_credentials and self.app_id):
            raise ValueError("Replace both credentials together, retain both, or remove both.")
        return self
