"""Fields every collection must carry, per the project's database rules.

`tenant_id` is intentionally omitted — deferred to Phase 2 (see docs/decisions/DECISIONS.md).
Adding it later means touching this one mixin plus the repository-layer query filter in
base_repository.py, not every model in the codebase.
"""

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from app.utils.datetime import utc_now

PyObjectId = Annotated[str, BeforeValidator(str)]


class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    # Populated from Mongo's `_id` on read (BeforeValidator coerces ObjectId -> str).
    # None for a not-yet-inserted instance; BaseRepository.insert excludes it from the
    # write payload so Mongo always generates the real value.
    id: PyObjectId | None = Field(default=None, alias="_id")
    status: str = "active"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    created_by: str | None = None
    updated_by: str | None = None
    is_deleted: bool = False
    deleted_at: datetime | None = None
    deleted_by: str | None = None
    version: int = 1

    def touch(self, updated_by: str | None = None) -> dict[str, Any]:
        """Returns the field updates a repository should apply on every write."""
        return {
            "updated_at": utc_now(),
            "updated_by": updated_by,
            "version": self.version + 1,
        }

    def require_id(self) -> str:
        """Returns `id`, asserting it's set — safe to call on anything just read back
        from the DB (only a freshly-constructed, not-yet-inserted instance has `id=None`).
        """
        if self.id is None:
            raise ValueError(f"{type(self).__name__} has no id — was it read from the database?")
        return self.id
