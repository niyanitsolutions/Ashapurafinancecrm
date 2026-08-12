from typing import Any

from app.features.auth.models import SESSION_STATUS_REVOKED, Session, User
from app.shared.base_repository import BaseRepository
from app.utils.datetime import utc_now


class UserRepository(BaseRepository[User]):
    collection_name = "users"
    model = User

    async def find_by_mobile(self, mobile: str, *, include_deleted: bool = False) -> User | None:
        query: dict[str, Any] = {"mobile": mobile}
        if not include_deleted:
            query["is_deleted"] = False
        doc = await self.collection.find_one(query)
        return self.model.model_validate(doc) if doc else None


class SessionRepository(BaseRepository[Session]):
    collection_name = "sessions"
    model = Session

    async def find_by_token_id(self, token_id: str) -> Session | None:
        doc = await self.collection.find_one({"token_id": token_id, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None

    async def revoke_family(self, family_id: str) -> None:
        """Kills every row in a rotation family — the response to detecting a stale
        refresh token being reused (see docs/decisions/DECISIONS.md #013).
        """
        await self.collection.update_many(
            {"family_id": family_id, "is_deleted": False},
            {"$set": {"status": SESSION_STATUS_REVOKED, "updated_at": utc_now()}, "$inc": {"version": 1}},
        )
