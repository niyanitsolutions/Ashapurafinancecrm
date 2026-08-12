"""WhatsApp Business API client interface — stubbed, see app.services.sms.client for the
rationale (credentials come from system_settings integrations once built)."""

from typing import Protocol


class WhatsAppClient(Protocol):
    async def send_template_message(self, mobile: str, template_name: str, params: dict[str, str]) -> bool: ...


class NotConfiguredWhatsAppClient:
    async def send_template_message(self, mobile: str, template_name: str, params: dict[str, str]) -> bool:
        raise NotImplementedError("WhatsApp provider not configured yet — see system_settings integrations.")
