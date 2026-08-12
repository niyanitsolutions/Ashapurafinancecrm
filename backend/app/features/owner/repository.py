from typing import Any

from app.features.owner.constants import OwnerType
from app.features.owner.models import OwnerProfile
from app.shared.base_repository import BaseRepository
from app.utils.helpers import to_object_id


class OwnerProfileRepository(BaseRepository[OwnerProfile]):
    collection_name = "owner_profiles"
    model = OwnerProfile

    async def find_by_user_id(self, user_id: str) -> OwnerProfile | None:
        doc = await self.collection.find_one({"user_id": user_id, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None

    async def find_by_email(self, email: str, *, exclude_id: str | None = None) -> OwnerProfile | None:
        query: dict[str, Any] = {"email": email, "is_deleted": False}
        if exclude_id:
            query["_id"] = {"$ne": to_object_id(exclude_id)}
        doc = await self.collection.find_one(query)
        return self.model.model_validate(doc) if doc else None

    async def find_primary(self) -> OwnerProfile | None:
        doc = await self.collection.find_one({"owner_type": OwnerType.PRIMARY, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None

    async def list_all(self) -> list[OwnerProfile]:
        # "primary" sorts before "secondary" alphabetically, so this also happens to put
        # the Primary Owner first in the list — convenient, not load-bearing.
        return await self.find_many({}, limit=500, sort=[("owner_type", 1), ("created_at", 1)])
