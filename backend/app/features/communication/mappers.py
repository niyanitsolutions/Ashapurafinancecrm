from app.features.communication.models import (
    CommunicationHistory,
    CommunicationQueueItem,
    CommunicationTemplate,
)
from app.features.communication.schemas import (
    HistoryResponse,
    QueueItemResponse,
    TemplateResponse,
)


def template_to_response(template: CommunicationTemplate) -> TemplateResponse:
    return TemplateResponse(
        id=template.require_id(), name=template.name, channel=template.channel, category=template.category,
        subject=template.subject, body=template.body, variables=template.variables, language=template.language,
        status=template.status, created_at=template.created_at,
    )


def queue_item_to_response(item: CommunicationQueueItem) -> QueueItemResponse:
    return QueueItemResponse(
        id=item.require_id(), channel=item.channel, recipient=item.recipient, template_id=item.template_id,
        variables=item.variables, rendered_subject=item.rendered_subject, rendered_body=item.rendered_body,
        status=item.status, provider_message_id=item.provider_message_id, retry_count=item.retry_count,
        next_retry_at=item.next_retry_at, error_detail=item.error_detail, business_event=item.business_event,
        entity_type=item.entity_type, entity_id=item.entity_id, sent_at=item.sent_at, delivered_at=item.delivered_at,
        created_at=item.created_at,
    )


def history_to_response(history: CommunicationHistory) -> HistoryResponse:
    return HistoryResponse(
        id=history.require_id(), queue_item_id=history.queue_item_id, channel=history.channel, provider=history.provider,
        recipient=history.recipient, template_id=history.template_id, template_name=history.template_name,
        variables=history.variables, status=history.status, error=history.error, sent_at=history.sent_at,
        delivered_at=history.delivered_at, retry_count=history.retry_count, created_at=history.created_at,
    )
