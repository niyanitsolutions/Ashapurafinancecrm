from typing import Any

from app.features.auth.models import SESSION_STATUS_REVOKED, Session, User
from app.shared.base_repository import BaseRepository
from app.utils.datetime import utc_now


class UserRepository(BaseRepository[User]):
    collection_name = "users"
    model = User

    async def require_available_mobile(self, mobile: str, *, session: Any = None) -> None:
        from app.core.exceptions import ConflictError
        from app.shared.customer_identity import mobile_match_pattern

        # Include deleted identities and legacy formatting; neither may be silently replaced.
        existing = await self.collection.find_one(
            {"mobile": {"$regex": mobile_match_pattern(mobile)}}, {"_id": 1}, session=session
        )
        if existing:
            raise ConflictError(
                "This mobile belongs to an existing identity. Owner review is required."
            )

    async def insert(self, document: User) -> str:
        from app.shared.customer_identity import normalize_mobile

        document = document.model_copy(update={"mobile": normalize_mobile(document.mobile)})
        await self.require_available_mobile(document.mobile)
        return await super().insert(document)

    async def find_by_mobile(self, mobile: str, *, include_deleted: bool = False) -> User | None:
        from app.core.exceptions import ConflictError
        from app.shared.customer_identity import mobile_match_pattern, normalize_mobile

        mobile = normalize_mobile(mobile)
        query: dict[str, Any] = {"mobile": {"$regex": mobile_match_pattern(mobile)}}
        if not include_deleted:
            query["is_deleted"] = False
        rows = await self.collection.find(query).limit(2).to_list(2)
        if len(rows) > 1:
            raise ConflictError("Conflicting historical mobile identities require Owner review.")
        return self.model.model_validate(rows[0]) if rows else None


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
        if await self.collection.find_one({"family_id": family_id, "is_deleted": False,
                                            "status": {"$in": ["logged_out", SESSION_STATUS_REVOKED]}}, {"_id": 1}):
            return  # Preserve an already-completed session's end time and reason.
        await self.collection.update_many(
            {"family_id": family_id, "is_deleted": False, "status": {"$in": ["active", "rotated"]}},
            {"$set": {"status": SESSION_STATUS_REVOKED, "logout_at": utc_now(), "end_reason": "session_revoked", "updated_at": utc_now()}, "$inc": {"version": 1}},
        )
