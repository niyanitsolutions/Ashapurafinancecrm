from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from app.features.voice_assistant.scheduling import timezone_name
from app.features.voice_assistant.schemas import StrictInput


class TelephoneNumberInput(StrictInput):
    version: int = Field(default=1, ge=1)
    number: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$")
    label: str = Field(min_length=3, max_length=80)
    purpose: Literal["inbound", "outbound", "bidirectional"] = "bidirectional"
    connection_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{24}$")
    authorization_reference: str | None = Field(default=None, min_length=5, max_length=150)
    compliance_reference: str | None = Field(default=None, min_length=5, max_length=150)
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
    calling_start: str = Field(default="09:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    calling_end: str = Field(default="18:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    inbound_route: Literal["dynamic_ai"] = "dynamic_ai"

    _timezone = field_validator("timezone")(timezone_name)

    @model_validator(mode="after")
    def window(self) -> Self:
        if self.calling_start >= self.calling_end:
            raise ValueError("Use a same-day calling window, start before end.")
        return self


class TelephoneNumberAction(StrictInput):
    version: int = Field(ge=1)
    action: Literal["submit", "review", "activate", "suspend", "disable", "reject", "revoke"]
    reason: str = Field(min_length=5, max_length=160)
