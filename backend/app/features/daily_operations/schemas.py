from datetime import date as CalendarDate
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

FollowStatus = Literal["FOLLOW UP PENDING", "NEXT FOLLOW UP", "DISBURSE", "REJECTED WITH REASON"]


class FollowUpInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    date: CalendarDate
    lead_id: str = Field(min_length=24, max_length=24, pattern=r"^[a-fA-F0-9]+$")
    case_id: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{24}$")
    bank: str = Field(min_length=1, max_length=200)
    status: FollowStatus = "FOLLOW UP PENDING"
    remarks: str = Field(default="", max_length=4000)
    remarks_date: CalendarDate
    next_action: str = Field(default="", max_length=1000)
    due_date: CalendarDate | None = None
    rejection_reason: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.due_date and self.due_date < self.date:
            raise ValueError("FOLLOW PENDING cannot be before DATE.")
        if self.status in {"FOLLOW UP PENDING", "NEXT FOLLOW UP"} and (
            not self.due_date or not self.next_action
        ):
            raise ValueError("Open follow-ups require FOLLOW PENDING and a next action.")
        if self.status == "REJECTED WITH REASON" and not self.rejection_reason:
            raise ValueError("REJECTED WITH REASON requires a rejection reason.")
        if self.status != "REJECTED WITH REASON" and self.rejection_reason:
            raise ValueError("Rejection reason is only valid for REJECTED WITH REASON.")
        if self.status == "DISBURSE" and not self.case_id:
            raise ValueError("DISBURSE requires a linked loan case.")
        if self.status in {"DISBURSE", "REJECTED WITH REASON"} and self.due_date:
            raise ValueError("Resolved follow-ups cannot have a pending due date.")
        return self


class FollowUpUpdate(FollowUpInput):
    version: int = Field(ge=1)


class IssueInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    date: CalendarDate
    inquiry: str = Field(min_length=1, max_length=4000)
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    assigned_to: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{24}$")
    status: Literal["OPEN", "IN PROGRESS", "RESOLVED", "REOPENED"] = "OPEN"
    resolution_notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_resolution(self) -> Self:
        if self.status == "RESOLVED" and not self.resolution_notes:
            raise ValueError("Resolution Notes are required to resolve an issue.")
        if self.status != "RESOLVED" and self.resolution_notes:
            raise ValueError(
                "Resolution Notes belong to a resolved issue; history retains prior notes."
            )
        return self


class IssueUpdate(IssueInput):
    version: int = Field(ge=1)


class ProgressActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    case_id: str = Field(pattern=r"^[a-fA-F0-9]{24}$")
    date: CalendarDate
    next_action: str = Field(min_length=1, max_length=1000)
    due_date: CalendarDate
