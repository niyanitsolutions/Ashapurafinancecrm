from typing import Literal, Self

from pydantic import Field, model_validator

from app.features.voice_assistant.schemas import StrictInput


class TranscriptSegment(StrictInput):
    speaker: Literal["caller", "assistant", "agent", "unknown"]
    start_seconds: float = Field(ge=0, le=1800, allow_inf_nan=False)
    end_seconds: float = Field(gt=0, le=1800, allow_inf_nan=False)
    text: str = Field(min_length=1, max_length=1000)
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def ordered_times(self) -> Self:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("Transcript end must follow start.")
        return self


class TranscriptInput(StrictInput):
    version: int = Field(ge=1)
    language: str = Field(default="en", pattern=r"^[a-z]{2}$")
    recognizer_label: str = Field(min_length=3, max_length=80)
    segments: list[TranscriptSegment] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def bounded_transcript(self) -> Self:
        if sum(len(segment.text) for segment in self.segments) > 50000:
            raise ValueError("Transcript exceeds 50,000 characters.")
        if any(a.start_seconds > b.start_seconds for a, b in zip(self.segments, self.segments[1:])):
            raise ValueError("Segments must be ordered by start time.")
        return self
