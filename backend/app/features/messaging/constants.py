"""Production stabilization pass — "Message your RM". A real two-way Customer<->Staff
conversation. No prior module built one to reuse: Module 9C's Communication Engine is a
one-way outbound bulk/template log (no reply capability by design), and the customer
portal's own Messages page was a documented read-only feed over that same one-way
history. This module is additive, new infrastructure, composing CustomerService's
existing RM-resolution rather than re-deriving assignment.
"""


class SenderRole:
    CUSTOMER = "customer"
    STAFF = "staff"

    ALL = (CUSTOMER, STAFF)


class AuditEvent:
    MESSAGE_SENT = "conversation_message_sent"
