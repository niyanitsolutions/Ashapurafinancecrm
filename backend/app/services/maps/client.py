"""Google Maps client interface (geocoding, geofence distance checks) — stubbed, see
app.services.sms.client for the rationale. Backs the geo_fencing feature once built."""

from typing import Protocol


class MapsClient(Protocol):
    async def distance_meters(self, origin: tuple[float, float], destination: tuple[float, float]) -> float: ...


class NotConfiguredMapsClient:
    async def distance_meters(self, origin: tuple[float, float], destination: tuple[float, float]) -> float:
        raise NotImplementedError("Maps provider not configured yet — see system_settings integrations.")
