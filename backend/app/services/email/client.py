"""SMTP email client interface — stubbed, see app.services.sms.client for the rationale."""

from typing import Protocol


class EmailClient(Protocol):
    async def send_email(self, to: str, subject: str, body_html: str) -> bool: ...


class NotConfiguredEmailClient:
    async def send_email(self, to: str, subject: str, body_html: str) -> bool:
        raise NotImplementedError("SMTP provider not configured yet — see system_settings integrations.")
