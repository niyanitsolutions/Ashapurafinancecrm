"""Customer Portal redesign — minimal Support Ticket vocabulary. See models.py's own
docstring for scope (Create + List-own only, no staff resolution workflow this round).
"""


class IssueType:
    APPLICATION = "application"
    DOCUMENTS = "documents"
    PAYMENT = "payment"
    OTHER = "other"

    ALL = (APPLICATION, DOCUMENTS, PAYMENT, OTHER)


class Priority:
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    ALL = (LOW, MEDIUM, HIGH)


class TicketStatus:
    # Production stabilization pass — a real, minimal staff-resolution lifecycle,
    # replacing the "only OPEN exists" placeholder now that a staff-facing view/respond
    # workflow is actually being built (was previously deferred, see models.py's
    # original docstring).
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"

    ALL = (OPEN, IN_PROGRESS, RESOLVED, CLOSED)


class AuditEvent:
    TICKET_CREATED = "support_ticket_created"
    TICKET_RESPONDED = "support_ticket_responded"
