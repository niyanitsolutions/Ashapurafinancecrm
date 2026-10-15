"""Operator-controlled native PBX settings; never a browser-supplied URL fetcher."""

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.features.voice_assistant.origin_policy import service_origin as native_origin
from app.features.voice_assistant.schemas import StrictInput


class NativeConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="VOICE_NATIVE_")
    allowed_origins: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("allowed_origins")
    @classmethod
    def origins(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(native_origin(value) for value in values))


@lru_cache
def get_native_config() -> NativeConfig:
    return NativeConfig()


class NativeConnectionInput(StrictInput):
    version: int = Field(default=1, ge=1)
    name: str = Field(min_length=3, max_length=80)
    api_origin: str = Field(max_length=300)
    endpoint_name: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    username: SecretStr | None = Field(default=None, min_length=1, max_length=100)
    password: SecretStr | None = Field(default=None, min_length=8, max_length=512)
    clear_credentials: bool = False

    _origin = field_validator("api_origin")(native_origin)

    @model_validator(mode="after")
    def credentials(self) -> "NativeConnectionInput":
        if bool(self.username) != bool(self.password):
            raise ValueError("Replace username and password together.")
        if self.clear_credentials and self.password:
            raise ValueError("Choose credential replacement or removal, not both.")
        for secret in (self.username, self.password):
            if secret and any(ord(c) < 32 or ord(c) > 126 for c in secret.get_secret_value()):
                raise ValueError("PBX credentials must contain printable ASCII only.")
        if self.username and ":" in self.username.get_secret_value():
            raise ValueError("The Basic authentication username cannot contain a colon.")
        return self
