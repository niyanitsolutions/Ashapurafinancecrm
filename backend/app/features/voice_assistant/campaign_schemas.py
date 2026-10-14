from datetime import date, datetime
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from app.features.voice_assistant.scheduling import timezone_name
from app.features.voice_assistant.schemas import StrictInput

ID = r"^[a-f0-9]{24}$"
PURPOSE = r"^[a-z][a-z0-9_-]{2,49}$"


class CampaignInput(StrictInput):
    version: int = Field(default=1, ge=1)
    name: str = Field(min_length=3, max_length=100)
    purpose: str = Field(pattern=PURPOSE)
    objective: str = Field(min_length=10, max_length=2000)
    mode: Literal["dry_run", "test", "production"] = "dry_run"
    timezone: str = "Asia/Kolkata"
    scheduled_at: datetime | None = None
    calling_start: str = Field(default="09:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    calling_end: str = Field(default="18:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    holidays: list[str] = Field(default_factory=list, max_length=366)
    dst_fold: Literal[0, 1] = 0
    maximum_attempts: int = Field(default=3, ge=1, le=5)
    frequency_hours: int = Field(default=24, ge=1, le=720)

    _timezone = field_validator("timezone")(timezone_name)

    @model_validator(mode="after")
    def valid_schedule(self) -> Self:
        if self.calling_start >= self.calling_end:
            raise ValueError("Use a same-day calling window with start before end.")
        if self.scheduled_at is not None and self.scheduled_at.tzinfo is None:
            raise ValueError("Campaign schedule requires an explicit UTC offset.")
        for day in self.holidays:
            if len(day) != 10:
                raise ValueError("Holiday dates must use YYYY-MM-DD.")
            date.fromisoformat(day)
        return self


class CampaignAction(StrictInput):
    version: int = Field(ge=1)
    action: Literal["validate", "start", "pause", "resume", "cancel", "archive"]


class RecipientInput(StrictInput):
    customer_id: str = Field(pattern=ID)
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def optional_timezone(cls, value: str | None) -> str | None:
        return timezone_name(value) if value else None


class AudienceInput(StrictInput):
    version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=16, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    recipients: list[RecipientInput] = Field(min_length=1, max_length=500)


class ContactConsentInput(StrictInput):
    version: int = Field(default=1, ge=1)
    customer_id: str = Field(pattern=ID)
    purpose: str = Field(pattern=PURPOSE)
    action: Literal["grant", "withdraw"]
    evidence_reference: str = Field(min_length=5, max_length=150)
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def aware_expiry(self) -> Self:
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("Consent expiry requires an explicit UTC offset.")
        if self.action == "grant" and self.expires_at is None:
            raise ValueError("A consent grant requires an expiry timestamp.")
        return self


class SuppressionInput(StrictInput):
    version: int = Field(default=1, ge=1)
    customer_id: str = Field(pattern=ID)
    campaign_id: str | None = Field(default=None, pattern=ID)
    suppressed: bool = True
    reason: str = Field(min_length=5, max_length=160)


class EmergencyInput(StrictInput):
    stopped: bool
    reason: str = Field(min_length=5, max_length=160)
