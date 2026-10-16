from typing import Literal

from pydantic import Field

from app.features.voice_assistant.schemas import StrictInput

Environment = Literal["test", "production"]
Component = Literal[
    "telephony", "stt", "tts", "inference", "media", "workers", "recording", "transfer", "smartflo"
]


class ComponentChange(StrictInput):
    version: int = Field(ge=1)
    enabled: bool
    profile_id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    reason: str = Field(min_length=5, max_length=160)


class ActivationChange(StrictInput):
    version: int = Field(ge=1)
    direction: Literal["inbound", "outbound", "processing"]
    enabled: bool
    confirmation: Literal["ENABLE LIVE CALLING"] | None = None
    evidence_token: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=5, max_length=160)


class EmergencyChange(StrictInput):
    reason: str = Field(min_length=5, max_length=160)
