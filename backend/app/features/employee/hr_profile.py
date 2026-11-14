"""Additive onboarding state on canonical employee records; no new login identity."""

from typing import Any, Literal, Self

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.employee.hr_notifications import record_event as write_audit_log
from app.features.employee.schemas import AddressSchema, EmergencyContactSchema
from app.utils.datetime import utc_now


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    version: int = Field(ge=0)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    emergency_contact: EmergencyContactSchema
    current_address: AddressSchema
    permanent_same_as_current: bool = False
    permanent_address: AddressSchema | None = None
    fresher: bool = True
    previous_company: str | None = Field(default=None, max_length=200)
    experience_years: int = Field(default=0, ge=0, le=70)
    experience_months: int = Field(default=0, ge=0, le=11)

    @model_validator(mode="after")
    def conditional_fields(self) -> Self:
        if self.permanent_same_as_current:
            self.permanent_address = self.current_address.model_copy()
        if not self.permanent_address:
            raise ValueError("Permanent address is required unless it matches the local address.")
        if self.fresher:
            self.previous_company = None
            self.experience_years = self.experience_months = 0
        elif not self.previous_company or not (self.experience_years or self.experience_months):
            raise ValueError("Previous company and positive experience are required.")
        if (
            not self.emergency_contact.name.strip()
            or not self.emergency_contact.relationship.strip()
        ):
            raise ValueError("Emergency contact name and relationship are required.")
        for address in (self.current_address, self.permanent_address):
            if not all(
                value.strip()
                for value in (address.line1, address.city, address.state, address.pincode)
            ):
                raise ValueError("Complete the address fields.")
        return self


class ProfileDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    decision: Literal["approve", "changes_required"]
    reason: str = Field(default="", max_length=2000)


class HrProfiles:
    def __init__(self, service: Any):
        self.service = service
        self.db = service._db

    async def commit(
        self,
        query: dict[str, Any],
        mutation: dict[str, Any],
        actor: Any,
        event_type: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any] | None:
        from app.features.employee.hr_notifications import queue_event

        row = await self.db.employees.find_one_and_update(
            query,
            queue_event(mutation, event_type, actor.require_id(), metadata),
            return_document=ReturnDocument.AFTER,
        )
        return dict(row) if row else None

    async def employee(
        self, employee_id: str, actor: User, *, review: bool = False
    ) -> dict[str, Any]:
        if actor.role not in {"owner", "employee"}:
            raise ForbiddenError("Employee or owner access is required.")
        if review and actor.role != "owner":
            raise ForbiddenError("Only an owner can review employee information.")
        query: dict[str, Any] = {"is_deleted": False}
        if employee_id == "me":
            query["user_id"] = actor.require_id()
        elif ObjectId.is_valid(employee_id):
            query["_id"] = ObjectId(employee_id)
        else:
            raise NotFoundError("Employee not found.")
        employee = await self.db.employees.find_one(query)
        if not employee:
            raise NotFoundError("Employee not found.")
        if actor.role != "owner" and employee["user_id"] != actor.require_id():
            raise ForbiddenError("You can only access your own employee profile.")
        if review and employee["user_id"] == actor.require_id():
            raise ForbiddenError("You cannot approve your own profile.")
        return dict(employee)

    @staticmethod
    def public(employee: dict[str, Any]) -> dict[str, Any]:
        return {
            "employee_id": str(employee["_id"]),
            "employee_version": employee.get("version", 1),
            "user_id": employee["user_id"],
            "employee_code": employee["employee_code"],
            "mobile": employee["mobile"],
            "account_status": employee["status"],
            "onboarding": {
                "status": "incomplete",
                "version": 0,
                "history": [],
                "mode": "account_only",
            }
            | (employee.get("onboarding") or {}),
            "current_profile": {
                key: employee.get(key)
                for key in (
                    "first_name",
                    "last_name",
                    "email",
                    "emergency_contact",
                    "current_address",
                    "permanent_address",
                )
            },
        }

    async def save(self, employee_id: str, payload: ProfileInput, actor: User) -> dict[str, Any]:
        employee = await self.employee(employee_id, actor)
        current = employee.get("onboarding", {})
        if current.get("status") == "verified":
            raise ConflictError("Verified information must be changed through an edit request.")
        if current.get("status") == "pending_verification":
            raise ConflictError("The submitted profile is awaiting review.")
        now = utc_now()
        profile = payload.model_dump(exclude={"version"}, mode="json")
        changed = (
            await self.commit(
                {
                    "_id": employee["_id"],
                    "is_deleted": False,
                    "onboarding": employee.get("onboarding"),
                },
                {
                    "$set": {
                        "onboarding": {
                            **{
                                key: current[key]
                                for key in ("ever_verified", "account_created_at", "access_review")
                                if key in current
                            },
                            "mode": current.get("mode", "account_only"),
                            "status": "incomplete",
                            "version": payload.version + 1,
                            "profile": profile,
                            "history": current.get("history", [])
                            + [{"action": "saved", "at": now, "actor_id": actor.require_id()}],
                            "updated_at": now,
                        },
                        "updated_at": now,
                    }
                },
                actor,
                "employee_onboarding_saved",
                {"employee_id": str(employee["_id"])},
            )
            if payload.version == current.get("version", 0)
            else None
        )
        if not changed:
            raise ConflictError("The profile changed. Refresh and try again.")
        await write_audit_log(
            self.db,
            event_type="employee_onboarding_saved",
            user_id=actor.require_id(),
            metadata={"employee_id": str(employee["_id"])},
        )
        return self.public(changed)

    async def submit(self, employee_id: str, version: int, actor: User) -> dict[str, Any]:
        employee = await self.employee(employee_id, actor)
        current = employee.get("onboarding", {})
        if current.get("status") not in {"incomplete", "changes_required"} or not current.get(
            "profile"
        ):
            raise ConflictError("Complete and save the profile before submitting.")
        ProfileInput.model_validate(current["profile"] | {"version": version})
        now = utc_now()
        changed = await self.commit(
            {
                "_id": employee["_id"],
                "is_deleted": False,
                "onboarding.version": version,
                "onboarding.status": current["status"],
            },
            {
                "$set": {
                    "onboarding.status": "pending_verification",
                    "onboarding.submitted_at": now,
                },
                "$inc": {"onboarding.version": 1},
                "$push": {
                    "onboarding.history": {
                        "action": "submitted",
                        "at": now,
                        "actor_id": actor.require_id(),
                    }
                },
            },
            actor,
            "employee_onboarding_submitted",
            {"employee_id": str(employee["_id"])},
        )
        if not changed:
            raise ConflictError("The profile changed. Refresh before submitting.")
        await write_audit_log(
            self.db,
            event_type="employee_onboarding_submitted",
            user_id=actor.require_id(),
            metadata={"employee_id": str(employee["_id"])},
        )
        return self.public(changed)

    async def decide(
        self, employee_id: str, payload: ProfileDecision, actor: User
    ) -> dict[str, Any]:
        employee = await self.employee(employee_id, actor, review=True)
        current = employee.get("onboarding", {})
        if current.get("status") != "pending_verification":
            raise ConflictError("Only a submitted profile can be reviewed.")
        if payload.decision == "changes_required" and not payload.reason.strip():
            raise ValidationError("Explain which changes are required.")
        if payload.decision == "approve":
            # Approval is unavailable until the document batch can prove completeness.
            from app.features.employee.hr_documents import HrDocuments

            await HrDocuments(self.service).require_approved(employee)
            if current.get("mode") == "owner_complete" and not current.get("account_created_at"):
                access = current.get("access_review")
                roles = sorted(
                    [
                        row["role_id"]
                        async for row in self.db.employee_roles.find(
                            {"employee_id": str(employee["_id"]), "is_deleted": False}
                        )
                    ]
                )
                organization = {
                    key: employee[key] for key in ("department_id", "designation_id", "branch_id")
                }
                if (
                    not access
                    or access.get("role_ids") != roles
                    or access.get("organization") != organization
                ):
                    raise ValidationError(
                        "Review the current organization, role and permissions before final account creation."
                    )

        if payload.decision == "approve" and await self.db.employees.find_one(
            {
                "email": current["profile"]["email"],
                "_id": {"$ne": employee["_id"]},
                "is_deleted": False,
            }
        ):
            raise ConflictError("This email belongs to another employee.")
        now = utc_now()
        updates: dict[str, Any] = {
            "onboarding.status": "verified"
            if payload.decision == "approve"
            else "changes_required",
            "onboarding.reviewed_by": actor.require_id(),
            "onboarding.reviewed_at": now,
            "onboarding.reason": payload.reason.strip(),
        }
        if payload.decision == "approve":
            data = ProfileInput.model_validate(
                current["profile"] | {"version": payload.version}
            ).model_dump(exclude={"version"}, mode="json")
            updates.update(
                {
                    key: data[key]
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
            updates["display_name"] = data["first_name"] + " " + data["last_name"]
            updates["onboarding.ever_verified"] = True
        try:
            changed = await self.commit(
                {
                    "_id": employee["_id"],
                    "is_deleted": False,
                    "onboarding.version": payload.version,
                    "onboarding.status": "pending_verification",
                },
                {
                    "$set": updates,
                    "$inc": {"onboarding.version": 1, "version": 1},
                    "$push": {
                        "onboarding.history": {
                            "action": payload.decision,
                            "reason": payload.reason.strip(),
                            "at": now,
                            "actor_id": actor.require_id(),
                        }
                    },
                },
                actor,
                "employee_onboarding_" + payload.decision,
                {"employee_id": str(employee["_id"])},
            )
        except DuplicateKeyError:
            raise ConflictError("This email belongs to another employee.") from None
        if not changed:
            raise ConflictError("The profile changed. Refresh before reviewing.")
        await write_audit_log(
            self.db,
            event_type="employee_onboarding_" + payload.decision,
            user_id=actor.require_id(),
            metadata={"employee_id": str(employee["_id"])},
        )
        if (
            payload.decision == "approve"
            and current.get("mode") == "owner_complete"
            and not current.get("account_created_at")
        ):
            await self.service.activate_employee(str(employee["_id"]), actor)
            changed = await self.db.employees.find_one({"_id": employee["_id"]}) or changed
        return self.public(changed)
