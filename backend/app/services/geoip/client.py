"""IP geolocation client interface — stubbed, see app.services.sms.client for the
rationale (credentials/provider come from system_settings integrations once built).
Populates Session.city/country for the Login History requirement once wired up.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GeoLocation:
    city: str | None
    country: str | None


class GeoIpClient(Protocol):
    async def lookup(self, ip_address: str) -> GeoLocation | None: ...


class NotConfiguredGeoIpClient:
    async def lookup(self, ip_address: str) -> GeoLocation | None:
        raise NotImplementedError("GeoIP provider not configured yet — see system_settings integrations.")
