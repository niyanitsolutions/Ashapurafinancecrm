from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.constants.roles import OWNER
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.features.access_control.permission_engine import PermissionEngine
from app.features.auth.models import User
from app.features.customer.repository import CustomerRepository
from app.features.customer.service import CustomerService
from app.features.employee.repository import EmployeeRepository
from app.features.messaging.constants import AuditEvent, SenderRole
from app.features.messaging.models import Conversation, ConversationMessage
from app.features.messaging.repository import ConversationMessageRepository, ConversationRepository
from app.features.messaging.schemas import ConversationMessageResponse, ConversationResponse
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now

_PREVIEW_LENGTH = 200


class MessagingService:
    def __init__(self, db: AsyncIOMotorDatabase[Any], redis: Redis) -> None:
        self._db = db
        self._conversations = ConversationRepository(db)
        self._messages = ConversationMessageRepository(db)
        self._customers = CustomerRepository(db)
        self._employees = EmployeeRepository(db)
        self._customer_service = CustomerService(db, redis)
        self._permission_engine = PermissionEngine(db)

    async def _get_own_customer_id(self, actor: User) -> str:
        customer = await self._customers.find_by_user_id(actor.require_id())
        if customer is None:
            raise NotFoundError("Customer profile not found.")
        return customer.require_id()

    async def _own_employee_id(self, actor: User) -> str | None:
        employee = await self._employees.find_by_user_id(actor.require_id())
        return employee.require_id() if employee is not None else None

    # ---------------------------------------------------------------- customer side

    async def get_or_create_own_conversation(self, actor: User) -> tuple[Conversation, list[ConversationMessage]]:
        customer_id = await self._get_own_customer_id(actor)
        conversation = await self._conversations.find_by_customer_id(customer_id)
        if conversation is None:
            employee_id = await self._customer_service.get_relationship_manager_employee_id(actor)
            conversation = Conversation(customer_id=customer_id, employee_id=employee_id)
            conversation_id = await self._conversations.insert(conversation)
            conversation = await self._conversations.find_by_id(conversation_id) or conversation
        messages = await self._messages.find_for_conversation(conversation.require_id())
        return conversation, messages

    async def send_own_message(self, body: str, actor: User) -> ConversationMessage:
        if not body.strip():
            raise ValidationError("Message cannot be empty.")
        customer_id = await self._get_own_customer_id(actor)
        conversation = await self._conversations.find_by_customer_id(customer_id)
        # Re-resolved on every customer-sent message — an RM reassignment made after the
        # conversation was first created routes future messages to the new RM, without
        # losing prior history (the RM display on the portal dashboard already re-resolves
        # this live on every load; the conversation mirrors that, not a separate value).
        employee_id = await self._customer_service.get_relationship_manager_employee_id(actor)
        if conversation is None:
            conversation = Conversation(customer_id=customer_id, employee_id=employee_id)
            conversation_id = await self._conversations.insert(conversation)
            conversation = await self._conversations.find_by_id(conversation_id) or conversation
        elif conversation.employee_id != employee_id:
            await self._conversations.update(conversation.require_id(), {"employee_id": employee_id})

        message = ConversationMessage(
            conversation_id=conversation.require_id(), customer_id=customer_id,
            sender_role=SenderRole.CUSTOMER, sender_user_id=actor.require_id(), body=body.strip(),
        )
        message_id = await self._messages.insert(message)
        await self._conversations.update(
            conversation.require_id(), {"last_message_at": utc_now(), "last_message_preview": body.strip()[:_PREVIEW_LENGTH]}
        )
        await write_audit_log(
            self._db, event_type=AuditEvent.MESSAGE_SENT, user_id=actor.require_id(),
            metadata={"conversation_id": conversation.require_id(), "sender_role": SenderRole.CUSTOMER},
        )
        return await self._messages.find_by_id(message_id) or message

    # ---------------------------------------------------------------- staff side

    async def get_conversation_for_staff(self, conversation_id: str, actor: User) -> Conversation:
        conversation = await self._conversations.find_by_id(conversation_id)
        if conversation is None:
            raise NotFoundError("Conversation not found.")
        if actor.role != OWNER:
            employee_id = await self._own_employee_id(actor)
            if conversation.employee_id is not None and conversation.employee_id != employee_id:
                raise ForbiddenError("You do not have access to this conversation.")
        return conversation

    async def list_conversations_for_staff(self, actor: User) -> list[Conversation]:
        """An Owner sees every conversation; an Employee sees conversations currently
        assigned to them plus unassigned ones (so an unassigned customer's message
        remains reachable by any staff member with access, not stranded) — same IDOR
        boundary shape as `SupportTicketService.list_all_tickets`."""
        if actor.role == OWNER:
            return await self._conversations.find_all()
        employee_id = await self._own_employee_id(actor)
        if employee_id is None:
            return []
        return await self._conversations.find_for_employee_or_unassigned(employee_id)

    async def list_messages_for_staff(self, conversation_id: str, actor: User) -> tuple[Conversation, list[ConversationMessage]]:
        conversation = await self.get_conversation_for_staff(conversation_id, actor)
        messages = await self._messages.find_for_conversation(conversation_id)
        return conversation, messages

    async def send_staff_message(self, conversation_id: str, body: str, actor: User) -> ConversationMessage:
        if not body.strip():
            raise ValidationError("Message cannot be empty.")
        conversation = await self.get_conversation_for_staff(conversation_id, actor)
        message = ConversationMessage(
            conversation_id=conversation.require_id(), customer_id=conversation.customer_id,
            sender_role=SenderRole.STAFF, sender_user_id=actor.require_id(), body=body.strip(),
        )
        message_id = await self._messages.insert(message)
        await self._conversations.update(
            conversation.require_id(), {"last_message_at": utc_now(), "last_message_preview": body.strip()[:_PREVIEW_LENGTH]}
        )
        await write_audit_log(
            self._db, event_type=AuditEvent.MESSAGE_SENT, user_id=actor.require_id(),
            metadata={"conversation_id": conversation_id, "sender_role": SenderRole.STAFF},
        )
        return await self._messages.find_by_id(message_id) or message

    # ---------------------------------------------------------------- response assembly

    async def to_response(self, conversation: Conversation, messages: list[ConversationMessage]) -> ConversationResponse:
        customer = await self._customers.find_by_id(conversation.customer_id)
        employee_name = None
        if conversation.employee_id:
            employee = await self._employees.find_by_id(conversation.employee_id)
            employee_name = employee.display_name if employee else None

        staff_sender_ids = {m.sender_user_id for m in messages if m.sender_role == SenderRole.STAFF}
        staff_name_by_user_id: dict[str, str] = {}
        if staff_sender_ids:
            employees = await self._employees.find_many({}, limit=500)
            staff_name_by_user_id = {e.user_id: e.display_name for e in employees if e.user_id in staff_sender_ids}

        message_items = [
            ConversationMessageResponse(
                id=m.require_id(),
                sender_role=m.sender_role,
                sender_name=(
                    (customer.full_name if customer else "Customer")
                    if m.sender_role == SenderRole.CUSTOMER
                    else staff_name_by_user_id.get(m.sender_user_id, "Owner")
                ),
                body=m.body,
                created_at=m.created_at,
            )
            for m in messages
        ]
        return ConversationResponse(
            id=conversation.require_id(), customer_id=conversation.customer_id,
            customer_name=customer.full_name if customer else None,
            employee_id=conversation.employee_id, employee_name=employee_name,
            last_message_at=conversation.last_message_at, last_message_preview=conversation.last_message_preview,
            messages=message_items,
        )
