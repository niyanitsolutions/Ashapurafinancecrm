"""Documented ARI read-only functional probes. No dial/control/media methods.

https://docs.asterisk.org/Asterisk_22_Documentation/API_Documentation/Asterisk_REST_Interface/Asterisk_REST_API/
https://docs.asterisk.org/Asterisk_22_Documentation/API_Documentation/Asterisk_REST_Interface/Endpoints_REST_API/
"""

import asyncio
import json
from typing import Any

import httpx


class NativeProbeFailure(Exception):
    pass


class AsteriskReadOnlyAdapter:
    def __init__(self, origin: str, username: str, password: str) -> None:
        self.origin = origin
        self.auth = httpx.BasicAuth(username, password)

    async def get_json(self, client: httpx.AsyncClient, path: str) -> Any:
        async with client.stream("GET", self.origin + path) as response:
            if response.status_code in {401, 403}:
                raise NativeProbeFailure("credentials_or_read_permission_rejected")
            if response.status_code == 404:
                raise NativeProbeFailure("ari_resource_or_pjsip_endpoint_not_found")
            if response.status_code == 429:
                raise NativeProbeFailure("pbx_rate_limited")
            if response.status_code != 200:
                raise NativeProbeFailure("pbx_unexpected_status")
            if (
                response.headers.get("content-type", "").split(";", 1)[0].strip()
                != "application/json"
            ):
                raise NativeProbeFailure("pbx_invalid_json_content_type")
            if response.headers.get("content-encoding", "identity") != "identity":
                raise NativeProbeFailure("pbx_compressed_response_not_supported")
            body = bytearray()
            async for part in response.aiter_bytes(chunk_size=8192):
                body.extend(part)
                if len(body) > 65536:
                    raise NativeProbeFailure("pbx_response_too_large")
            try:
                return json.loads(body)
            except (ValueError, UnicodeError):
                raise NativeProbeFailure("pbx_invalid_json") from None

    async def probe(self, endpoint_name: str) -> dict[str, Any]:
        try:
            async with (
                asyncio.timeout(12),
                httpx.AsyncClient(
                    auth=self.auth,
                    timeout=httpx.Timeout(5),
                    follow_redirects=False,
                    trust_env=False,
                    limits=httpx.Limits(max_connections=1),
                    headers={"Accept": "application/json", "Accept-Encoding": "identity"},
                ) as client,
            ):
                ping = await self.get_json(client, "/ari/asterisk/ping")
                if not isinstance(ping, dict) or ping.get("ping") != "pong":
                    raise NativeProbeFailure("ari_ping_not_confirmed")
                endpoint = await self.get_json(client, f"/ari/endpoints/PJSIP/{endpoint_name}")
                if (
                    not isinstance(endpoint, dict)
                    or endpoint.get("technology") != "PJSIP"
                    or endpoint.get("resource") != endpoint_name
                ):
                    raise NativeProbeFailure("pjsip_endpoint_identity_mismatch")
                state = endpoint.get("state")
                if state not in {"online", "offline", "unknown"}:
                    raise NativeProbeFailure("pjsip_endpoint_state_invalid")
                return {
                    "status": "control_probe_passed"
                    if state == "online"
                    else "endpoint_not_online",
                    "control_api_reachable": True,
                    "endpoint_online": state == "online",
                    "media_verified": False,
                    "calling_verified": False,
                }
        except NativeProbeFailure as exc:
            return {
                "status": str(exc),
                "control_api_reachable": False,
                "endpoint_online": False,
                "media_verified": False,
                "calling_verified": False,
            }
        except (httpx.HTTPError, TimeoutError):
            return {
                "status": "pbx_unreachable_or_timeout",
                "control_api_reachable": False,
                "endpoint_online": False,
                "media_verified": False,
                "calling_verified": False,
            }
