from typing import Any

from app.features.support.models import SupportTicket
from app.shared.base_repository import BaseRepository


class SupportTicketRepository(BaseRepository[SupportTicket]):
    collection_name = "support_tickets"
    model = SupportTicket

    async def find_for_customer(self, customer_id: str) -> list[SupportTicket]:
        return await self.find_many({"customer_id": customer_id}, limit=200, sort=[("created_at", -1)])

    async def find_for_staff(self, *, assigned_to: str | None, status: str | None, search: str | None) -> list[SupportTicket]:
        """Staff list view. `assigned_to=None` means "unrestricted" (Owner/broadly-visible
        caller — see SupportTicketService); a real employee id restricts to tickets
        assigned to that employee only."""
        query: dict[str, Any] = {}
        if assigned_to is not None:
            query["assigned_to"] = assigned_to
        if status:
            query["status"] = status
        if search:
            query["$or"] = [
                {"ticket_code": {"$regex": search, "$options": "i"}},
                {"subject": {"$regex": search, "$options": "i"}},
            ]
        return await self.find_many(query, limit=500, sort=[("created_at", -1)])
