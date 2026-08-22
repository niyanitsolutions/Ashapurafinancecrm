from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.core.response import ApiResponse
from app.features.access_control.permission_engine import require_permission
from app.features.auth.models import User
from app.features.messaging.dependencies import (
    CurrentUserDep,
    get_messaging_service,
    require_customer,
)
from app.features.messaging.schemas import ConversationResponse, SendMessageRequest
from app.features.messaging.service import MessagingService

router = APIRouter(prefix="/conversations", tags=["messaging"])

ServiceDep = Annotated[MessagingService, Depends(get_messaging_service)]
CustomerDep = Annotated[User, Depends(require_customer)]


def _staff_perm(action: str) -> Any:
    return require_permission("messaging", "conversations", action)


# ---------------------------------------------------------------- customer side


@router.get("/me")
async def get_own_conversation(
    service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[ConversationResponse]:
    conversation, messages = await service.get_or_create_own_conversation(current_user)
    return ApiResponse[ConversationResponse].ok(await service.to_response(conversation, messages))


@router.post("/me/messages")
async def send_own_message(
    payload: SendMessageRequest, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[ConversationResponse]:
    await service.send_own_message(payload.body, current_user)
    conversation, messages = await service.get_or_create_own_conversation(current_user)
    return ApiResponse[ConversationResponse].ok(await service.to_response(conversation, messages))


# ---------------------------------------------------------------- staff side


@router.get("")
async def list_conversations(service: ServiceDep, actor: Annotated[User, _staff_perm("view")]) -> ApiResponse[list[ConversationResponse]]:
    conversations = await service.list_conversations_for_staff(actor)
    items = [await service.to_response(c, []) for c in conversations]
    return ApiResponse[list[ConversationResponse]].ok(items)


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str, service: ServiceDep, actor: Annotated[User, _staff_perm("view")]
) -> ApiResponse[ConversationResponse]:
    conversation, messages = await service.list_messages_for_staff(conversation_id, actor)
    return ApiResponse[ConversationResponse].ok(await service.to_response(conversation, messages))


@router.post("/{conversation_id}/messages")
async def send_staff_message(
    conversation_id: str, payload: SendMessageRequest, service: ServiceDep, actor: Annotated[User, _staff_perm("create")]
) -> ApiResponse[ConversationResponse]:
    await service.send_staff_message(conversation_id, payload.body, actor)
    conversation, messages = await service.list_messages_for_staff(conversation_id, actor)
    return ApiResponse[ConversationResponse].ok(await service.to_response(conversation, messages))
