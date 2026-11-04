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
    ("FOLLOW UP PENDING", "#FFF0C2"),
    ("NEXT FOLLOW UP", "#DCEBFF"),
    ("DISBURSE", "#D9F5E3"),
    ("REJECTED WITH REASON", "#FFE0E0"),
]
BUILTINS = {name for name, _color in INITIAL}


def normalized(name: str) -> str:
    return unicodedata.normalize("NFKC", " ".join(name.split())).casefold()


class OptionName(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=60)
    color: str = Field(default="#DCEBFF", pattern=r"^#[0-9a-fA-F]{6}$")
    display_order: int = Field(default=100, ge=0, le=100000)

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
    collection = db.daily_followup_status_options
    await collection.create_index(
        [("company_id", 1), ("normalized_name", 1)],
        unique=True,
        partialFilterExpression={"is_active": True},
        name="active_company_followup_status_name",
    )
    await collection.create_index([("company_id", 1), ("is_active", 1), ("name", 1)])
    await collection.create_index([("company_id", 1), ("value", 1)], unique=True)
    for order, (name, color) in enumerate(INITIAL):
        oid = ObjectId(
            hashlib.sha256((COMPANY + ":followup-status:" + name).encode()).hexdigest()[:24]
        )
        now = utc_now()
        try:
            await collection.update_one(
                {"_id": oid},
                {
                    "$setOnInsert": {
                        "company_id": COMPANY,
                        "name": name,
                        "value": name,
                        "color": color,
                        "display_order": order,
                        "is_system": True,
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


class StatusOptions:
    def __init__(self, service: Any) -> None:
        self.service = service
        self.db = service.db
        self.collection = self.db.daily_followup_status_options

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
            public(doc)
            for doc in await self.collection.find(query)
            .sort([("display_order", 1), ("name", 1)])
            .to_list(None)
        ]

    async def change(
        self,
        actor: User,
        *,
        name: str | None = None,
        option_id: str | None = None,
        version: int | None = None,
        active: bool | None = None,
        color: str | None = None,
        display_order: int | None = None,
    ) -> dict[str, Any]:
        await self.authorize(actor, True)
        now = utc_now()
        before = None
        if option_id:
            if not ObjectId.is_valid(option_id):
                raise NotFoundError("Follow-up status option not found.")
            before = await self.collection.find_one(
                {"_id": ObjectId(option_id), "company_id": COMPANY}
            )
            if not before:
                raise NotFoundError("Follow-up status option not found.")
        if (
            before
            and before.get("is_system")
            and ((name is not None and name != before["name"]) or active is False)
        ):
            raise ValidationError(
                "Default status names must be kept. You can edit their colors and display order."
            )
        data: dict[str, Any] = {"updated_by": actor.require_id(), "updated_at": now}
        if color is not None:
            data["color"] = color.upper()
        if display_order is not None:
            data["display_order"] = display_order
        if name is not None:
            data.update(name=name, normalized_name=normalized(name))
        if active is not None:
            data.update(is_active=active, deleted_at=None if active else now)
        action = (
            "updated"
            if name is not None or color is not None or display_order is not None
            else "restored"
            if active
            else "archived"
        )
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
                oid = ObjectId()
                doc = {
                    **data,
                    "_id": oid,
                    "value": "custom:" + str(oid),
                    "is_system": False,
                    "color": data.get("color", "#DCEBFF"),
                    "display_order": data.get("display_order", 100),
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
            event_type="followup_status_option_" + action,
            user_id=actor.require_id(),
            metadata={
                "company_id": COMPANY,
                "option_id": str(doc["_id"]),
                "before": public(before) if before else None,
                "after": public(doc),
            },
        )
        return public(doc)

    async def record_value(self, value: str, old: dict[str, Any] | None) -> dict[str, Any]:
        if old and value == old.get("status"):
            return {"status_label": old.get("status_label")}
        doc = await self.collection.find_one(
            {"value": value, "company_id": COMPANY, "is_active": True}
        )
        if doc:
            return {"status_label": None if doc.get("is_system") else doc["name"]}
        # Built-in business rules also work in older databases before additive setup.
        if value in BUILTINS:
            return {"status_label": None}
        raise ValidationError(
            "Select an active Follow-up Status. Refresh options if it was archived."
        )
