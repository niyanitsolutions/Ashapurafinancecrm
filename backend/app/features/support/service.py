"""Customer Portal redesign — minimal Support Ticket service. Composes Module 6B's
`CustomerService.raise_support_request` (its existing Task/Notification side-effect to the
assigned Relationship Manager, or every Owner if unassigned) rather than duplicating it —
creating a ticket both persists a real, listable record here AND keeps firing that existing
notification, unchanged, in one call from the frontend's point of view.
"""

from typing import Any
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.core.exceptions import NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.customer.repository import CustomerRepository
from app.features.customer.schemas import RaiseSupportRequestRequest
from app.features.customer.service import CustomerService
from app.features.support.constants import AuditEvent
from app.features.support.models import SupportTicket
from app.features.support.repository import SupportTicketRepository
from app.features.support.schemas import CreateSupportTicketRequest
from app.services.storage.client import (
    generate_presigned_download_url,
    generate_presigned_upload_url,
)
from app.shared.audit_log import write_audit_log
from app.utils.id_generator import IdPrefix, generate_id

_UPLOAD_URL_EXPIRE_SECONDS = 300
_DOWNLOAD_URL_EXPIRE_SECONDS = 300


class SupportTicketService:
    def __init__(self, db: AsyncIOMotorDatabase[Any], redis: Redis) -> None:
        self._db = db
        self._tickets = SupportTicketRepository(db)
        self._customers = CustomerRepository(db)
        self._customer_service = CustomerService(db, redis)

    async def _get_own_customer_id(self, actor: User) -> str:
        customer = await self._customers.find_by_user_id(actor.require_id())
        if customer is None:
            raise NotFoundError("Customer profile not found.")
        return customer.require_id()

    async def get_attachment_upload_url(self, file_name: str, content_type: str | None, actor: User) -> tuple[str, str]:
        customer_id = await self._get_own_customer_id(actor)
        s3_key = f"support-tickets/{customer_id}/{uuid4()}/{file_name}"
        url = generate_presigned_upload_url(s3_key, expires_in=_UPLOAD_URL_EXPIRE_SECONDS, content_type=content_type)
        return url, s3_key

    async def create_ticket(self, payload: CreateSupportTicketRequest, actor: User) -> SupportTicket:
        customer_id = await self._get_own_customer_id(actor)
        # `attachment_s3_key` is client-supplied — never trust it outright (same class of
        # bug as CustomerService.confirm_document: an unvalidated key here becomes a read
        # primitive over any object in the shared bucket via `attachment_download_url`'s
        # presigned GET). `get_attachment_upload_url` only ever issues keys under this
        # customer's own `support-tickets/{customer_id}/` prefix, so rejecting anything
        # outside it closes the cross-tenant read without needing a separate per-upload
        # token — the customer_id segment IS the ownership check.
        if payload.attachment_s3_key is not None and not payload.attachment_s3_key.startswith(f"support-tickets/{customer_id}/"):
            raise ValidationError("Invalid attachment reference.")
        ticket_code = await generate_id(self._db, IdPrefix.TICKET)
        ticket = SupportTicket(
            ticket_code=ticket_code, customer_id=customer_id, issue_type=payload.issue_type, priority=payload.priority,
            subject=payload.subject, message=payload.message, attachment_s3_key=payload.attachment_s3_key,
            created_by=actor.require_id(),
        )
        ticket_id = await self._tickets.insert(ticket)
        await write_audit_log(
            self._db, event_type=AuditEvent.TICKET_CREATED, user_id=actor.require_id(),
            metadata={"ticket_id": ticket_id, "ticket_code": ticket_code},
        )

        # Keeps the existing Module 6B notification side-effect firing unchanged — a
        # persisted, listable ticket is additive, it doesn't replace that behavior.
        await self._customer_service.raise_support_request(
            RaiseSupportRequestRequest(subject=payload.subject, message=payload.message), actor
        )

        return await self._tickets.find_by_id(ticket_id) or ticket

    async def list_own_tickets(self, actor: User) -> list[SupportTicket]:
        customer_id = await self._get_own_customer_id(actor)
        return await self._tickets.find_for_customer(customer_id)

    def attachment_download_url(self, ticket: SupportTicket) -> str | None:
        if not ticket.attachment_s3_key:
            return None
        return generate_presigned_download_url(ticket.attachment_s3_key, expires_in=_DOWNLOAD_URL_EXPIRE_SECONDS)
