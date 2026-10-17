from datetime import datetime
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from app.features.voice_assistant.platform_schemas import Environment
from app.features.voice_assistant.scheduling import timezone_name
from app.features.voice_assistant.schemas import StrictInput

EntityType = Literal["lead", "loan_case", "insurance_case"]


class CallbackTimeInput(StrictInput):
    request: str = Field(min_length=5, max_length=500)
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
    _zone = field_validator("timezone")(timezone_name)


class CallbackInput(StrictInput):
    environment: Environment = "test"
    entity_type: EntityType
    entity_id: str = Field(pattern=r"^[a-f0-9]{24}$")
    assigned_to: str = Field(pattern=r"^[a-f0-9]{24}$")
    requested_local: datetime
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
    dst_fold: int | None = Field(default=None, ge=0, le=1)
    customer_request: str = Field(min_length=5, max_length=500)
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_-]{16,100}$")
    source_call_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{24}$")
    _zone = field_validator("timezone")(timezone_name)


class CallbackAction(StrictInput):
    version: int = Field(ge=1)
    action: Literal["confirm", "reschedule", "cancel", "retry_readiness"]
    reason: str = Field(min_length=5, max_length=160)
    requested_local: datetime | None = None
    timezone: str | None = Field(default=None, max_length=64)
    dst_fold: int | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def reschedule_time(self) -> Self:
        if self.action == "reschedule":
            if self.requested_local is None or self.timezone is None:
                raise ValueError("Rescheduling requires an explicit local date/time and timezone.")
            timezone_name(self.timezone)
        elif (
            self.requested_local is not None
            or self.timezone is not None
            or self.dst_fold is not None
        ):
            raise ValueError("Only rescheduling can change the requested callback time.")
        return self
