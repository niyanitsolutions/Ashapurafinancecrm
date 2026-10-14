from datetime import date
from typing import Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VoiceSettings(StrictInput):
    version: int = Field(default=1, ge=1)
    mode: Literal["disabled", "mock"] = "disabled"
    ring_seconds: int = Field(default=10, ge=3, le=120)
    transfer_seconds: int = Field(default=20, ge=3, le=120)
    max_duration_seconds: int = Field(default=300, ge=30, le=1800)
    max_concurrent_calls: int = Field(default=2, ge=1, le=20)
    daily_call_limit: int = Field(default=50, ge=1, le=1000)
    monthly_minute_limit: int = Field(default=500, ge=1, le=10000)
    calls_per_minute: int = Field(default=5, ge=1, le=60)
    retry_limit: int = Field(default=1, ge=0, le=3)
    retry_interval_seconds: int = Field(default=3600, ge=300, le=86400)
    queue_timeout_seconds: int = Field(default=120, ge=10, le=600)
    max_queue_length: int = Field(default=10, ge=1, le=100)
    ai_fallback: bool = True
    timezone: str = "Asia/Kolkata"
    calling_start: str = Field(default="09:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    calling_end: str = Field(default="18:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    holidays: list[date] = Field(default_factory=list, max_length=366)
    primary_employee_id: str | None = Field(default=None, max_length=24)
    conversation_instructions: str = Field(
        default="Be professional, concise and helpful. Identify yourself as an AI assistant.",
        min_length=10,
        max_length=4000,
    )
    operational_rules: str = Field(
        default="Answer from approved knowledge. Offer human assistance when uncertain.",
        min_length=10,
        max_length=4000,
    )
    default_language: str = Field(default="en", pattern=r"^[a-z]{2}$")

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Use a valid IANA timezone.") from exc
        return value

    @model_validator(mode="after")
    def valid_window(self) -> Self:
        if self.calling_start >= self.calling_end:
            raise ValueError("Calling hours must be a same-day window with start before end.")
        return self


class MockCallInput(StrictInput):
    direction: Literal["incoming", "outgoing"]
    # A descriptive label only; the simulator has no dialable destination field.
    contact_label: str = Field(default="Test caller", min_length=1, max_length=80)
    idempotency_key: str = Field(min_length=16, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    consent_reference: str | None = Field(default=None, min_length=5, max_length=150)


class CallAction(StrictInput):
    action: Literal["answer", "reject", "transfer", "transfer_confirmed", "transfer_failed", "end"]
    version: int = Field(ge=1)


class KnowledgeInput(StrictInput):
    title: str = Field(min_length=3, max_length=150)
    content: str = Field(min_length=20, max_length=50000)
    language: str = Field(default="en", pattern=r"^[a-z]{2}$")
    effective_on: date | None = None
    expires_on: date | None = None
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def valid_dates(self) -> Self:
        if self.effective_on and self.expires_on and self.effective_on >= self.expires_on:
            raise ValueError("Expiry must be after the effective date.")
        return self


class KnowledgeAction(StrictInput):
    action: Literal["review", "publish", "archive", "rollback", "rollback_published"]
    version: int = Field(ge=1)
    target_version: int | None = Field(default=None, ge=1)


class EvaluationCase(StrictInput):
    question: str = Field(min_length=2, max_length=2000)
    required_facts: list[str] = Field(default_factory=list, max_length=10)
    expect_evidence: bool = True

    @field_validator("required_facts")
    @classmethod
    def bounded_facts(cls, value: list[str]) -> list[str]:
        if any(not fact.strip() or len(fact) > 200 for fact in value):
            raise ValueError("Required facts must contain 1 to 200 characters.")
        return value

    @model_validator(mode="after")
    def positive_facts(self) -> Self:
        if self.expect_evidence and not self.required_facts:
            raise ValueError("An evidence test requires at least one required fact.")
        if not self.expect_evidence and self.required_facts:
            raise ValueError("No-evidence tests cannot specify required facts.")
        return self


class KnowledgeEvaluationInput(StrictInput):
    version: int = Field(ge=1)
    cases: list[EvaluationCase] = Field(min_length=1, max_length=20)


class ConsoleInput(StrictInput):
    question: str = Field(min_length=2, max_length=2000)
    language: str = Field(default="en", pattern=r"^[a-z]{2}$")
    history: list[dict[str, str]] = Field(default_factory=list, max_length=12)

    @field_validator("history")
    @classmethod
    def valid_history(cls, value: list[dict[str, str]]) -> list[dict[str, str]]:
        for turn in value:
            if set(turn) != {"role", "content"} or turn["role"] not in {"user", "assistant"}:
                raise ValueError("History must contain user/assistant content only.")
            if len(turn["content"]) > 2000:
                raise ValueError("History turn too long.")
        return value
