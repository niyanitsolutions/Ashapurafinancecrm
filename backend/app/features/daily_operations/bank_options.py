"""Daily-only bank options reuse status option permissions, atomic updates and audit."""

from __future__ import annotations

import builtins
from typing import Any, cast

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.exceptions import ValidationError
from app.features.auth.models import User
from app.features.daily_operations.status_options import (
    COMPANY,
    StatusOptions,
    normalized,
)


class BankName(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def meaningful(cls, value: str) -> str:
        # Same normalization/control-character rules as shared status options.
        import unicodedata

        value = unicodedata.normalize("NFKC", " ".join(value.split()))
        if (
            not value
            or len(value) > 200
            or any(unicodedata.category(c).startswith("C") for c in value)
        ):
            raise ValueError("Enter a visible bank / NBFC name.")
        return value


class BankEdit(BankName):
    version: int = Field(ge=1)


class BankChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    option_id: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{24}$")
    name: str = Field(default="", max_length=200)


def saved_banks(doc: dict[str, Any]) -> builtins.list[dict[str, Any]]:
    if "banks" in doc and doc["banks"] is not None:
        return cast(builtins.list[dict[str, Any]], doc["banks"])
    return [{"option_id": None, "name": doc["bank"]}] if doc.get("bank") else []


class BankOptions(StatusOptions):
    collection_name = "daily_followup_bank_options"
    audit_prefix = "followup_bank_option_"
    styled = False

    async def list(self, actor: User, archived: bool = False) -> builtins.list[dict[str, Any]]:
        rows = await super().list(actor, archived)
        return sorted(rows, key=lambda row: row["name"].casefold())

    async def selections(
        self, choices: builtins.list[BankChoice] | None, legacy: str, old: dict[str, Any] | None
    ) -> builtins.list[dict[str, Any]]:
        previous = saved_banks(old or {})
        if choices is None:
            # Compatibility with older clients and single-bank CSV templates.
            if old and previous and legacy == old.get("bank", ""):
                return previous
            if not legacy.strip():
                raise ValidationError("Select at least one Bank / NBFC.")
            return [{"option_id": None, "name": legacy}]
        result = []
        for choice in choices:
            prior = next(
                (
                    row
                    for row in previous
                    if row.get("option_id") == choice.option_id
                    and (choice.option_id or row["name"] == choice.name)
                ),
                None,
            )
            if prior:
                result.append(prior)
            elif choice.option_id:
                doc = await self.collection.find_one(
                    {"_id": ObjectId(choice.option_id), "company_id": COMPANY, "is_active": True}
                )
                if not doc:
                    raise ValidationError(
                        "Choose active bank options from this company. Refresh options if a bank was archived."
                    )
                result.append({"option_id": str(doc["_id"]), "name": doc["name"]})
            else:
                raise ValidationError("New bank selections require a valid saved bank option.")
        if not result:
            raise ValidationError("Select at least one Bank / NBFC.")
        if len({row["option_id"] for row in result if row["option_id"]}) != sum(
            bool(row["option_id"]) for row in result
        ) or len({normalized(row["name"]) for row in result}) != len(result):
            raise ValidationError("Duplicate Bank / NBFC selections are not allowed.")
        return result


async def install(db: Any) -> None:
    await db.daily_followup_bank_options.create_index(
        [("company_id", 1), ("normalized_name", 1)],
        unique=True,
        partialFilterExpression={"is_active": True},
        name="active_company_followup_bank_name",
    )
    await db.daily_followup_bank_options.create_index(
        [("company_id", 1), ("is_active", 1), ("name", 1)]
    )
    await db.daily_follow_ups.create_index([("banks.option_id", 1), ("date", -1)])
    await db.daily_follow_ups.create_index([("banks.name", 1), ("date", -1)])
