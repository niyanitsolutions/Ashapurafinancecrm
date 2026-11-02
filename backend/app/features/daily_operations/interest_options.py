"""Shared follow-up options in this deployment's single-company database.

company_id is the existing company-settings singleton key, never a client input.
Separate company deployments must use separate authenticated databases (decision 001).
"""

import hashlib
import unicodedata
from typing import Any

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.constants.roles import OWNER
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.features.auth.models import User
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now

COMPANY = "default"
INITIAL = [
    "INTERESTED",
    "NOT INTERESTED",
    "HIGH INTEREST",
    "LOW INTEREST",
    "FOLLOW-UP REQUIRED",
    "CALL BACK LATER",
    "REJECTED",
    "NOT CONTACTABLE",
    "DOCUMENTS PENDING",
    "OTHER",
]


def normalized(name: str) -> str:
    return unicodedata.normalize("NFKC", " ".join(name.split())).casefold()


class OptionName(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=60)

    @field_validator("name")
    @classmethod
    def meaningful(cls, value: str) -> str:
        value = unicodedata.normalize("NFKC", " ".join(value.split()))
        if (
            not value
            or len(value) > 60
            or any(unicodedata.category(c).startswith("C") for c in value)
        ):
            raise ValueError("Enter an option name of 1 to 60 visible characters.")
        return value


class OptionEdit(OptionName):
    version: int = Field(ge=1)


class OptionVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)


def public(doc: dict[str, Any]) -> dict[str, Any]:
    return {**{k: v for k, v in doc.items() if k != "_id"}, "id": str(doc["_id"])}


async def install(db: Any) -> None:
    collection = db.daily_interest_options
    await collection.create_index(
        [("company_id", 1), ("normalized_name", 1)],
        unique=True,
        partialFilterExpression={"is_active": True},
        name="active_company_interest_name",
    )
    await collection.create_index([("company_id", 1), ("is_active", 1), ("name", 1)])
    for name in INITIAL:
        oid = ObjectId(hashlib.sha256((COMPANY + ":interest:" + name).encode()).hexdigest()[:24])
        now = utc_now()
        try:
            await collection.update_one(
                {"_id": oid},
                {
                    "$setOnInsert": {
                        "company_id": COMPANY,
                        "name": name,
                        "normalized_name": normalized(name),
                        "is_active": True,
                        "version": 1,
                        "created_by": None,
                        "created_by_name": "Initial setup",
                        "created_at": now,
                        "updated_by": None,
                        "updated_at": now,
                        "deleted_at": None,
                    }
                },
                upsert=True,
            )
        except DuplicateKeyError:
            # An existing active custom option has this name. Never rename/rewrite it.
            pass


class InterestOptions:
    def __init__(self, service: Any) -> None:
        self.service = service
        self.db = service.db
        self.collection = self.db.daily_interest_options

    async def authorize(self, actor: User, manage: bool = False) -> None:
        await self.service.employee_id(actor)  # active employee or owner, no customers/partners
        await self.service.authorize(actor, "follow-ups", "view")
        if manage and actor.role != OWNER:
            from app.core.exceptions import ForbiddenError
            from app.features.access_control.permission_engine import PermissionEngine

            engine = PermissionEngine(self.db)
            if not any(
                [
                    await engine.has_permission(
                        actor, module="daily_operations", resource="follow-ups", action=action
                    )
                    for action in ("create", "edit")
                ]
            ):
                raise ForbiddenError(
                    "Follow-up create or edit permission is required to manage options."
                )

    async def list(self, actor: User, archived: bool = False) -> list[dict[str, Any]]:
        await self.authorize(actor)
        query: dict[str, Any] = {"company_id": COMPANY}
        if not archived:
            query["is_active"] = True
        return [
            public(doc) for doc in await self.collection.find(query).sort("name", 1).to_list(None)
        ]

    async def change(
        self,
        actor: User,
        *,
        name: str | None = None,
        option_id: str | None = None,
        version: int | None = None,
        active: bool | None = None,
    ) -> dict[str, Any]:
        await self.authorize(actor, True)
        now = utc_now()
        before = None
        if option_id:
            if not ObjectId.is_valid(option_id):
                raise NotFoundError("Interest option not found.")
            before = await self.collection.find_one(
                {"_id": ObjectId(option_id), "company_id": COMPANY}
            )
            if not before:
                raise NotFoundError("Interest option not found.")
        data: dict[str, Any] = {"updated_by": actor.require_id(), "updated_at": now}
        if name is not None:
            data.update(name=name, normalized_name=normalized(name))
        if active is not None:
            data.update(is_active=active, deleted_at=None if active else now)
        action = "renamed" if name is not None else "restored" if active else "archived"
        try:
            if before:
                doc = await self.collection.find_one_and_update(
                    {"_id": before["_id"], "company_id": COMPANY, "version": version},
                    {"$set": data, "$inc": {"version": 1}},
                    return_document=ReturnDocument.AFTER,
                )
                if not doc:
                    raise ConflictError("This option changed. Refresh options and try again.")
            else:
                profile = (
                    await self.db.employees.find_one(
                        {"user_id": actor.require_id(), "is_deleted": False}
                    )
                    if actor.role != OWNER
                    else await self.db.owner_profiles.find_one({"user_id": actor.require_id()})
                )
                doc = {
                    **data,
                    "company_id": COMPANY,
                    "is_active": True,
                    "version": 1,
                    "created_by": actor.require_id(),
                    "created_by_name": (profile or {}).get("display_name")
                    or (profile or {}).get("full_name")
                    or actor.require_id(),
                    "created_at": now,
                    "deleted_at": None,
                }
                doc["_id"] = (await self.collection.insert_one(doc)).inserted_id
                action = "created"
        except DuplicateKeyError:
            raise ConflictError(
                "An active option with this name already exists. Use it or rename this option."
            ) from None
        await write_audit_log(
            self.db,
            event_type="customer_interest_option_" + action,
            user_id=actor.require_id(),
            metadata={
                "company_id": COMPANY,
                "option_id": str(doc["_id"]),
                "before": public(before) if before else None,
                "after": public(doc),
            },
        )
        return public(doc)

    async def record_value(
        self, option_id: str | None, old: dict[str, Any] | None
    ) -> dict[str, Any]:
        if old and option_id == old.get("customer_interest_option_id"):
            # Keep the saved label even after a central rename or archive.
            return {
                "customer_interest_option_id": option_id,
                "customer_interest_status_snapshot": old.get("customer_interest_status_snapshot"),
            }
        if option_id is None:
            return {"customer_interest_option_id": None, "customer_interest_status_snapshot": None}
        doc = await self.collection.find_one(
            {"_id": ObjectId(option_id), "company_id": COMPANY, "is_active": True}
        )
        if not doc:
            raise ValidationError(
                "Select an active Customer Interest Status. Refresh options if it was removed."
            )
        return {
            "customer_interest_option_id": option_id,
            "customer_interest_status_snapshot": doc["name"],
        }
