from datetime import datetime

from pydantic import Field

from app.features.messaging.constants import SenderRole
from app.shared.base_document import BaseDocument
from app.utils.datetime import utc_now


class Conversation(BaseDocument):
    """One conversation per Customer, lazily get-or-created on first message — the same
    pattern Module 6C already established for Loan/Insurance Cases (decision #058), not
    a new architectural idea. `employee_id` tracks the customer's *current* RM (re-resolved
    on every customer-sent message, so a later reassignment routes future messages to the
    new RM without losing history) — see MessagingService."""

    customer_id: str  # ref: customers
    employee_id: str | None = None  # ref: employees — current RM, may be unassigned
    last_message_at: datetime = Field(default_factory=utc_now)
    last_message_preview: str = ""


class ConversationMessage(BaseDocument):
    conversation_id: str
    customer_id: str  # denormalized for ownership checks, same pattern as SupportTicket
    sender_role: str = Field(pattern=f"^({'|'.join(SenderRole.ALL)})$")
    sender_user_id: str  # ref: users — the customer's own User id, or the responding staff member's
    body: str
