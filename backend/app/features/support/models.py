"""Customer Portal redesign — minimal Support Ticket. A real, listable, persisted record
alongside the existing lightweight `CustomerService.raise_support_request` (Module 6B's
Task/Notification side-effect to the assigned Relationship Manager / Owners) — that flow is
untouched and keeps firing on every ticket creation; this adds a queryable history the
customer can actually see, which the old flow never provided.

Deliberately Create + List-own only: `assigned_to` is reserved (same "reserve a slot, no
logic" posture as IntegrationConfig.health_status / ReferralPartner.parent_partner_id) —
a future staff-side ticket-resolution workflow is additive data, not a redesign, when it's
actually asked for.
"""

from pydantic import Field

from app.features.support.constants import IssueType, Priority, TicketStatus
from app.shared.base_document import BaseDocument


class SupportTicket(BaseDocument):
    ticket_code: str  # AFS-TICKET-000001
    customer_id: str  # ref: customers
    issue_type: str = Field(pattern=f"^({'|'.join(IssueType.ALL)})$")
    priority: str = Field(pattern=f"^({'|'.join(Priority.ALL)})$")
    subject: str
    message: str
    attachment_s3_key: str | None = None
    assigned_to: str | None = None  # ref: employees — reserved, unused this round

    # Overrides BaseDocument.status's generic "active" default with this collection's own
    # (currently one-value) lifecycle vocabulary — see TicketStatus.
    status: str = Field(default=TicketStatus.OPEN, pattern=f"^({'|'.join(TicketStatus.ALL)})$")
