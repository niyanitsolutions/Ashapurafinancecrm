from datetime import datetime
from typing import Any

from app.features.reminders.constants import ReminderStatus
from app.features.reminders.models import (
    Notification,
    NotificationCheckpoint,
    Reminder,
    ReminderRule,
    Task,
)
from app.shared.base_repository import BaseRepository


class TaskRepository(BaseRepository[Task]):
    collection_name = "tasks"
    model = Task

    async def search_and_filter(
        self, *, assigned_to: str | None, status: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None
    ) -> tuple[list[Task], int]:
        query: dict[str, Any] = {"is_deleted": False}
        if assigned_to:
            query["assigned_to"] = assigned_to
        if status:
            query["status"] = status
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        items = [self.model.model_validate(doc) async for doc in cursor]
        return items, total

    async def find_pending_due_before(self, before: datetime) -> list[Task]:
        return await self.find_many({"status": "pending", "due_at": {"$lte": before}}, limit=1000)

    async def find_pending(self) -> list[Task]:
        return await self.find_many({"status": "pending"}, limit=1000)


class ReminderRuleRepository(BaseRepository[ReminderRule]):
    collection_name = "reminder_rules"
    model = ReminderRule

    async def find_active_by_type(self, rule_type: str) -> list[ReminderRule]:
        return await self.find_many({"rule_type": rule_type, "status": "active"}, limit=100)


class ReminderRepository(BaseRepository[Reminder]):
    collection_name = "reminders"
    model = Reminder

    async def find_existing(
        self, *, rule_id: str, target_type: str, target_id: str, reminder_type: str, trigger_offset: int | None = None
    ) -> Reminder | None:
        doc = await self.collection.find_one(
            {
                "rule_id": rule_id, "target_type": target_type, "target_id": target_id, "reminder_type": reminder_type,
                "trigger_offset": trigger_offset, "is_deleted": False,
            }
        )
        return self.model.model_validate(doc) if doc else None

    async def find_for_target(self, *, target_type: str, target_id: str, reminder_type: str) -> list[Reminder]:
        return await self.find_many({"target_type": target_type, "target_id": target_id, "reminder_type": reminder_type}, limit=100, sort=[("created_at", -1)])

    async def mark_fired(self, reminder_id: str, *, fired_at: datetime) -> None:
        await self.update(reminder_id, {"status": ReminderStatus.FIRED, "fired_at": fired_at})

    async def count_fired(self, *, target_type: str, target_id: str, reminder_type: str) -> int:
        return await self.collection.count_documents(
            {"target_type": target_type, "target_id": target_id, "reminder_type": reminder_type, "status": ReminderStatus.FIRED, "is_deleted": False}
        )


class NotificationRepository(BaseRepository[Notification]):
    collection_name = "notifications"
    model = Notification

    async def search_and_filter(
        self, recipient_user_id: str, *, status: str | None, category: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None
    ) -> tuple[list[Notification], int]:
        query: dict[str, Any] = {"is_deleted": False, "recipient_user_id": recipient_user_id}
        if status:
            query["status"] = status
        if category:
            query["category"] = category
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        items = [self.model.model_validate(doc) async for doc in cursor]
        return items, total

    async def count_unread(self, recipient_user_id: str) -> int:
        return await self.collection.count_documents({"is_deleted": False, "recipient_user_id": recipient_user_id, "status": "unread"})

    async def find_recent(self, recipient_user_id: str, *, limit: int = 10) -> list[Notification]:
        return await self.find_many({"recipient_user_id": recipient_user_id}, limit=limit, sort=[("created_at", -1)])


class NotificationCheckpointRepository(BaseRepository[NotificationCheckpoint]):
    collection_name = "notification_checkpoints"
    model = NotificationCheckpoint

    async def get_last_processed_at(self, event_type: str) -> datetime | None:
        doc = await self.collection.find_one({"event_type": event_type})
        return self.model.model_validate(doc).last_processed_at if doc else None

    async def set_last_processed_at(self, event_type: str, when: datetime) -> None:
        await self.collection.update_one({"event_type": event_type}, {"$set": {"event_type": event_type, "last_processed_at": when}}, upsert=True)
