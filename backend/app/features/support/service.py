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

from app.constants.roles import OWNER
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.features.access_control.permission_engine import PermissionEngine
from app.features.auth.models import User
from app.features.customer.repository import CustomerRepository
from app.features.customer.schemas import RaiseSupportRequestRequest
from app.features.customer.service import CustomerService
from app.features.employee.repository import EmployeeRepository
from app.features.support.constants import AuditEvent, TicketStatus
from app.features.support.models import SupportTicket
from app.features.support.repository import SupportTicketRepository
from app.features.support.schemas import CreateSupportTicketRequest, RespondToTicketRequest
from app.services.storage.client import (
    generate_presigned_download_url,
    generate_presigned_upload_url,
)
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now
from app.utils.id_generator import IdPrefix, generate_id

_UPLOAD_URL_EXPIRE_SECONDS = 300
_DOWNLOAD_URL_EXPIRE_SECONDS = 300


class SupportTicketService:
    def __init__(self, db: AsyncIOMotorDatabase[Any], redis: Redis) -> None:
        self._db = db
        self._tickets = SupportTicketRepository(db)
        self._customers = CustomerRepository(db)
        self._customer_service = CustomerService(db, redis)
        self._employees = EmployeeRepository(db)
        self._permission_engine = PermissionEngine(db)

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

    # ---------------------------------------------------------------- staff resolution workflow

    async def _has_broad_visibility(self, actor: User) -> bool:
        """Owner-level visibility into every ticket regardless of assignment — same
        pattern as `LeadService._has_broad_visibility`, reusing this feature's own
        `edit` action (an actor trusted to respond to any ticket is trusted to see the
        full queue) rather than inventing a second visibility permission."""
        if actor.role == OWNER:
            return True
        return await self._permission_engine.has_permission(actor, module="support", resource="tickets", action="edit")

    async def _own_employee_id(self, actor: User) -> str | None:
        employee = await self._employees.find_by_user_id(actor.require_id())
        return employee.require_id() if employee is not None else None

    async def list_all_tickets(self, actor: User, *, status: str | None, search: str | None) -> list[SupportTicket]:
        """Staff ticket queue. An Owner (or an Employee granted `support:tickets:edit`,
        see `_has_broad_visibility`) sees every ticket; any other Employee granted only
        `support:tickets:view` sees tickets assigned to them, plus unassigned ones (so an
        unassigned ticket remains actionable by whoever notices it — Owners are also
        separately notified via the existing `raise_support_request` side-effect on
        creation, this is not the only channel)."""
        if await self._has_broad_visibility(actor):
            tickets = await self._tickets.find_for_staff(assigned_to=None, status=status, search=search)
        else:
            employee_id = await self._own_employee_id(actor)
            if employee_id is None:
                return []
            assigned = await self._tickets.find_for_staff(assigned_to=employee_id, status=status, search=search)
            unassigned = await self._tickets.find_for_staff(assigned_to=None, status=status, search=search)
            seen = {t.require_id() for t in assigned}
            tickets = assigned + [t for t in unassigned if t.assigned_to is None and t.require_id() not in seen]
        return tickets

    async def get_ticket_for_staff(self, ticket_id: str, actor: User) -> SupportTicket:
        ticket = await self._tickets.find_by_id(ticket_id)
        if ticket is None:
            raise NotFoundError("Ticket not found.")
        if not await self._has_broad_visibility(actor):
            employee_id = await self._own_employee_id(actor)
            if ticket.assigned_to is not None and ticket.assigned_to != employee_id:
                raise ForbiddenError("You do not have access to this ticket.")
        return ticket

    async def respond_to_ticket(self, ticket_id: str, payload: RespondToTicketRequest, actor: User) -> SupportTicket:
        ticket = await self.get_ticket_for_staff(ticket_id, actor)
        new_status = payload.status or (TicketStatus.IN_PROGRESS if ticket.status == TicketStatus.OPEN else ticket.status)
        updates = {
            "staff_response": payload.staff_response, "responded_by": actor.require_id(),
            "responded_at": utc_now(), "status": new_status,
        }
        updated = await self._tickets.update(ticket_id, updates, updated_by=actor.require_id())
        await write_audit_log(
            self._db, event_type=AuditEvent.TICKET_RESPONDED, user_id=actor.require_id(),
            metadata={"ticket_id": ticket_id, "ticket_code": ticket.ticket_code, "status": new_status},
        )
        return updated or ticket

    async def resolve_staff_names(self, tickets: list[SupportTicket]) -> tuple[dict[str, str], dict[str, str]]:
        """`(assigned_to_name_map keyed by Employee id, responded_by_name_map keyed by
        User id)` — `responded_by` may be an Owner's User id (Owners have no Employee
        row), which falls back to the generic "Owner" label, same convention
        `LeadService.resolve_names` already established for `assigned_by`/`rejected_by`."""
        assigned_ids = {t.assigned_to for t in tickets if t.assigned_to}
        responder_ids = {t.responded_by for t in tickets if t.responded_by}
        employees = await self._employees.find_many({}, limit=500) if (assigned_ids or responder_ids) else []
        assigned_to_name = {e.require_id(): e.display_name for e in employees if e.require_id() in assigned_ids}
        responder_by_user_id = {e.user_id: e.display_name for e in employees if e.user_id in responder_ids}
        responded_by_name = {uid: responder_by_user_id.get(uid, "Owner") for uid in responder_ids}
        return assigned_to_name, responded_by_name
