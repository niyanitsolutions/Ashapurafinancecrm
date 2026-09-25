from app.features.lead_capture.models import CaptureFailure, CaptureSource, MetaLeadRouting
from app.features.lead_capture.schemas import (
    CaptureFailureResponse,
    CaptureSourceResponse,
    MetaLeadRoutingResponse,
)


def source_to_response(source: CaptureSource) -> CaptureSourceResponse:
    return CaptureSourceResponse(
        id=source.require_id(), key=source.key, label=source.label, lead_source_id=source.lead_source_id,
        default_product_category=source.default_product_category, default_product_id=source.default_product_id,
    )


def failure_to_response(failure: CaptureFailure) -> CaptureFailureResponse:
    return CaptureFailureResponse(
        id=failure.require_id(), capture_source=failure.capture_source, failure_reason=failure.failure_reason, raw_payload=failure.raw_payload,
        error_detail=failure.error_detail, status=failure.status, retry_count=failure.retry_count, next_retry_at=failure.next_retry_at,
        resolved_lead_id=failure.resolved_lead_id, created_at=failure.created_at,
    )


def routing_to_response(routing: MetaLeadRouting) -> MetaLeadRoutingResponse:
    return MetaLeadRoutingResponse(
        id=routing.require_id(), meta_form_id=routing.meta_form_id, form_name=routing.form_name,
        category=routing.category, product_mode=routing.product_mode,
        default_product_id=routing.default_product_id, destination_module=routing.destination_module,
        destination_type=routing.destination_type, product_question_key=routing.product_question_key,
        product_question_label=routing.product_question_label, answer_mappings=routing.answer_mappings,
        discovered_questions=routing.discovered_questions, priority=routing.priority,
        status=routing.status, created_at=routing.created_at, updated_at=routing.updated_at,
    )
