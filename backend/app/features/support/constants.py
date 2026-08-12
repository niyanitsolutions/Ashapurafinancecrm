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
    # Only one value exists this round — same precedent as Module 6A's Lead.status
    # (only NEW exists until a real pipeline is scoped); a future resolution workflow
    # is additive data at that point, not a code change now.
    OPEN = "open"

    ALL = (OPEN,)


class AuditEvent:
    TICKET_CREATED = "support_ticket_created"
