from app.features.support.models import SupportTicket
from app.shared.base_repository import BaseRepository


class SupportTicketRepository(BaseRepository[SupportTicket]):
    collection_name = "support_tickets"
    model = SupportTicket

    async def find_for_customer(self, customer_id: str) -> list[SupportTicket]:
        return await self.find_many({"customer_id": customer_id}, limit=200, sort=[("created_at", -1)])
