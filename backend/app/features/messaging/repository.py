from typing import Any

from app.features.messaging.models import Conversation, ConversationMessage
from app.shared.base_repository import BaseRepository


class ConversationRepository(BaseRepository[Conversation]):
    collection_name = "conversations"
    model = Conversation

    async def find_by_customer_id(self, customer_id: str) -> Conversation | None:
        doc = await self.collection.find_one({"customer_id": customer_id, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None

    async def find_all(self) -> list[Conversation]:
        return await self.find_many({}, limit=500, sort=[("last_message_at", -1)])

    async def find_for_employee_or_unassigned(self, employee_id: str) -> list[Conversation]:
        query: dict[str, Any] = {"$or": [{"employee_id": employee_id}, {"employee_id": None}]}
        return await self.find_many(query, limit=500, sort=[("last_message_at", -1)])


class ConversationMessageRepository(BaseRepository[ConversationMessage]):
    collection_name = "conversation_messages"
    model = ConversationMessage

    async def find_for_conversation(self, conversation_id: str) -> list[ConversationMessage]:
        return await self.find_many({"conversation_id": conversation_id}, limit=500, sort=[("created_at", 1)])
