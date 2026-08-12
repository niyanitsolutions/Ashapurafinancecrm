"""Meta (Facebook/Instagram lead ads) API client interface — stubbed, see
app.services.sms.client for the rationale."""

from typing import Any, Protocol


class MetaLeadsClient(Protocol):
    async def fetch_new_leads(self, form_id: str) -> list[dict[str, Any]]: ...


class NotConfiguredMetaLeadsClient:
    async def fetch_new_leads(self, form_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError("Meta integration not configured yet — see system_settings integrations.")
