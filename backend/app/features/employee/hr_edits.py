"""Employee edit requests keep official values unchanged until an owner decision."""

from typing import Any, Literal

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import ConflictError, ValidationError
from app.features.employee.hr_notifications import record_event as write_audit_log
from app.features.employee.hr_profile import HrProfiles, ProfileInput
from app.utils.datetime import utc_now


class EditDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approved", "rejected"]
    reason: str = Field(default="", max_length=2000)


class HrEdits(HrProfiles):
    async def request(self, employee_id: str, payload: ProfileInput, actor: Any) -> dict[str, Any]:
        employee = await self.employee(employee_id, actor)
        if employee.get("onboarding", {}).get("status") != "verified":
            raise ConflictError("Complete profile verification before requesting an official edit.")
        if employee.get("version", 1) != payload.version:
            raise ConflictError("Official profile changed. Refresh before requesting an edit.")
        previous = employee.get("hr_edit_requests", [])
        if any(row["status"] == "pending" for row in previous):
            raise ConflictError("An edit request is already awaiting review.")
        proposal = payload.model_dump(mode="json", exclude={"version"})
        before = employee["onboarding"]["profile"]
        if proposal == before:
            raise ValidationError("Change at least one profile value before submitting.")
        now = utc_now()
        request = {
            "id": str(ObjectId()),
            "employee_id": str(employee["_id"]),
            "requested_by": actor.require_id(),
            "previous_values": before,
            "proposed_values": proposal,
            "requested_at": now,
            "base_version": payload.version,
            "status": "pending",
            "history": [{"status": "pending", "at": now, "actor_id": actor.require_id()}],
        }
        changed = await self.commit(
            {
                "_id": employee["_id"],
                "is_deleted": False,
                "version": payload.version,
                "hr_edit_requests": employee.get("hr_edit_requests"),
            },
            {"$set": {"hr_edit_requests": previous + [request]}},
            actor,
            "employee_edit_requested",
            {"employee_id": str(employee["_id"]), "request_id": request["id"]},
        )
        if not changed:
            raise ConflictError("Another edit request was submitted. Refresh.")
        await write_audit_log(
            self.db,
            event_type="employee_edit_requested",
            user_id=actor.require_id(),
            metadata={"employee_id": str(employee["_id"]), "request_id": request["id"]},
        )
        return request

    async def review(
        self, employee_id: str, request_id: str, payload: EditDecision, actor: Any
    ) -> dict[str, Any]:
        employee = await self.employee(employee_id, actor, review=True)
        requests = employee.get("hr_edit_requests", [])
        request = next(
            (row for row in requests if row["id"] == request_id and row["status"] == "pending"),
            None,
        )
        if not request:
            raise ConflictError("This request is no longer pending.")
        if payload.decision == "rejected" and not payload.reason.strip():
            raise ValidationError("A rejection reason is required.")
        query = {"_id": employee["_id"], "is_deleted": False, "hr_edit_requests": requests}
        updates: dict[str, Any] = {}
        if payload.decision == "approved":
            query["version"] = request["base_version"]
            if employee.get("version", 1) != request["base_version"]:
                raise ConflictError(
                    "Official profile changed; reject this stale request and ask for a new one."
                )
            proposal = ProfileInput.model_validate(
                request["proposed_values"] | {"version": request["base_version"]}
            ).model_dump(mode="json", exclude={"version"})
            from app.features.employee.hr_documents import HrDocuments

            await HrDocuments(self.service).require_approved(
                employee | {"onboarding": employee["onboarding"] | {"profile": proposal}}
            )
            updates.update(
                {
                    key: proposal[key]
                    for key in (
                        "first_name",
                        "last_name",
                        "email",
                        "emergency_contact",
                        "current_address",
                        "permanent_address",
                    )
                }
            )
            updates["display_name"] = proposal["first_name"] + " " + proposal["last_name"]
            updates["onboarding.profile"] = proposal
        now = utc_now()
        decided = request | {
            "status": payload.decision,
            "reviewed_by": actor.require_id(),
            "reviewed_at": now,
            "reason": payload.reason.strip(),
            "history": request["history"]
            + [
                {
                    "status": payload.decision,
                    "reason": payload.reason.strip(),
                    "actor_id": actor.require_id(),
                    "at": now,
                }
            ],
        }
        updates["hr_edit_requests"] = [
            decided if row["id"] == request_id else row for row in requests
        ]
        mutation: dict[str, Any] = {"$set": updates}
        if payload.decision == "approved":
            mutation["$inc"] = {"version": 1, "onboarding.version": 1}
        try:
            changed = await self.commit(
                query,
                mutation,
                actor,
                "employee_edit_" + payload.decision,
                {"employee_id": str(employee["_id"]), "request_id": request_id},
            )
        except DuplicateKeyError:
            raise ConflictError(
                "The proposed email is already assigned to another employee."
            ) from None
        if not changed:
            raise ConflictError(
                "The request or official profile changed. Refresh before reviewing."
            )
        await write_audit_log(
            self.db,
            event_type="employee_edit_" + payload.decision,
            user_id=actor.require_id(),
            metadata={"employee_id": str(employee["_id"]), "request_id": request_id},
        )
        return dict(decided)
