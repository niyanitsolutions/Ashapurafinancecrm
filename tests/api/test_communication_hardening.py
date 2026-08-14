"""Stage 4 (production verification/hardening) — regression test for a pre-existing bug
found during security review: an adapter exception (not just a negative `DeliveryOutcome`)
was never caught anywhere in `_send_one`, so it crashed the entire
`process_pending_queue`/`process_retry_queue` loop for that worker tick and stranded the
triggering item in `PROCESSING` forever (never retried, invisible as neither pending nor
failed). Confirmed concretely: `email.errors.HeaderParseError` (raised by Python's own
`email` package for a Subject/From/To header containing an embedded CR/LF) is neither an
`OSError` nor an `smtplib.SMTPException`, so `send_email`'s existing `except (OSError,
smtplib.SMTPException)` never caught it — and nothing validates a Lead/Customer's
`full_name` against control characters, so a self-registered Customer's own name could
already trigger this before Stage 3. Bulk Messaging (Stage 3) made it materially more
likely to be hit in practice (many customer-supplied names flowing through unattended).
"""

import json

from app.features.communication import adapters as communication_adapters
from app.features.communication.constants import Channel, QueueStatus, TemplateCategory
from app.features.communication.models import CommunicationQueueItem, CommunicationTemplate
from app.features.communication.service import CommunicationService
from app.features.communication.template_engine import extract_variable_names
from app.features.integrations.models import IntegrationConfig
from app.security.encryption import encrypt
from app.utils.helpers import to_object_id


async def _seed_active_config(mock_db, *, channel: str) -> None:
    config = IntegrationConfig(
        integration_code=f"AFS-INTG-{channel.upper()}", integration_type=channel, provider="generic", name=f"{channel} test",
        config_encrypted=encrypt(json.dumps({"api_url": "https://example.test/send", "api_key": "key123", "access_token": "tok123"})),
        is_enabled=True, is_active=True,
    )
    await mock_db["integration_configs"].insert_one(config.model_dump(by_alias=True, exclude={"id"}))


async def _seed_template(mock_db, *, channel: str) -> str:
    body = "Hi {{name}}"
    template = CommunicationTemplate(name=f"t-{channel}", channel=channel, category=TemplateCategory.WELCOME, body=body, variables=extract_variable_names(body))
    result = await mock_db["communication_templates"].insert_one(template.model_dump(by_alias=True, exclude={"id"}))
    return str(result.inserted_id)


async def _seed_pending_item(mock_db, *, channel: str, template_id: str, recipient: str) -> str:
    item = CommunicationQueueItem(
        channel=channel, recipient=recipient, template_id=template_id, variables={"name": "Test"},
        rendered_body="Hi Test", status=QueueStatus.PENDING,
    )
    result = await mock_db["communication_queue"].insert_one(item.model_dump(by_alias=True, exclude={"id"}))
    return str(result.inserted_id)


async def test_adapter_exception_marks_item_failed_not_stuck_in_processing(mock_db, monkeypatch):
    await _seed_active_config(mock_db, channel=Channel.WHATSAPP)
    template_id = await _seed_template(mock_db, channel=Channel.WHATSAPP)
    item_id = await _seed_pending_item(mock_db, channel=Channel.WHATSAPP, template_id=template_id, recipient="9876543210")

    async def _raising_adapter(*, recipient, subject, body, config, **_kwargs):
        raise RuntimeError("simulated adapter crash — e.g. email.errors.HeaderParseError")

    monkeypatch.setitem(communication_adapters.ADAPTERS, Channel.WHATSAPP, _raising_adapter)

    service = CommunicationService(mock_db)
    await service._send_one(item_id)  # exercising the exact worker code path directly

    updated = await mock_db["communication_queue"].find_one({"_id": to_object_id(item_id)})
    assert updated["status"] == QueueStatus.FAILED  # not stuck in PROCESSING
    assert "simulated adapter crash" in updated["error_detail"]
    # Never a raw traceback leaked into the stored error.
    assert "Traceback" not in updated["error_detail"]


async def test_adapter_exception_does_not_abort_the_rest_of_the_batch(mock_db, monkeypatch):
    """The actual production-blocking symptom: one bad item must not silently swallow
    every other item due in the same worker tick."""
    await _seed_active_config(mock_db, channel=Channel.WHATSAPP)
    template_id = await _seed_template(mock_db, channel=Channel.WHATSAPP)
    bad_item_id = await _seed_pending_item(mock_db, channel=Channel.WHATSAPP, template_id=template_id, recipient="9876543211")
    good_item_id = await _seed_pending_item(mock_db, channel=Channel.WHATSAPP, template_id=template_id, recipient="9876543212")

    async def _flaky_adapter(*, recipient, subject, body, config, **_kwargs):
        if recipient == "9876543211":
            raise RuntimeError("simulated crash for this one recipient only")
        return communication_adapters.DeliveryOutcome(True, "MSGID-OK", None, is_transient=False)

    monkeypatch.setitem(communication_adapters.ADAPTERS, Channel.WHATSAPP, _flaky_adapter)

    service = CommunicationService(mock_db)
    await service.process_pending_queue()  # the real worker-cron entry point, unmodified

    bad = await mock_db["communication_queue"].find_one({"_id": to_object_id(bad_item_id)})
    good = await mock_db["communication_queue"].find_one({"_id": to_object_id(good_item_id)})
    assert bad["status"] == QueueStatus.FAILED
    assert good["status"] == QueueStatus.SENT  # proves the loop continued past the bad item
