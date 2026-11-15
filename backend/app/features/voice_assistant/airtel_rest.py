"""Documented Airtel REST wire contract (guide pp9–13), not live admission authority."""

import asyncio
import json
from typing import Literal
from urllib.parse import urlencode

import httpx
from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator

from app.features.voice_assistant.airtel_auth import signed_headers
from app.features.voice_assistant.airtel_logging import private_transport_logs
from app.features.voice_assistant.schemas import StrictInput
from app.utils.datetime import utc_now

ORIGIN = "https://openapi.airtel.in"
C2C_PATH = "/gateway/airtel-xchange/v2/adv/ob-click-to-call"
RECORDING_PATH = "/gateway/airtel-xchange/callv2/recording"
EVENTS = frozenset(
    {
        "CalledNumber",
        "Ringing",
        "NotReachable",
        "NoAnswer",
        "Busy",
        "Answer",
        "RecordingStarted",
        "PlaybackFinished",
        "ChannelHold",
        "ChannelUnhold",
        "Matched",
        "NotMatched",
        "Timeout",
        "Streaminfo",
        "StreamError",
        "terminate",
        "Disconnected",
        "RecordingFinished",
        "Removed",
    }
)


class CallbackOverride(StrictInput):
    # p11 table variant only when the account contract explicitly confirms it.
    eventType: Literal[
        "ALL", "CALL", "MEDIA", "DTMF", "RECORD", "CDR", "API", "SUBMITTED", "DELIVERED", "ERROR"
    ]
    notifyURL: str = Field(max_length=500)
    method: Literal["POST"] = "POST"
    headers: dict[str, str] = Field(default_factory=dict, max_length=5)

    @field_validator("notifyURL")
    @classmethod
    def callback_url(cls, value: str) -> str:
        try:
            parsed = httpx.URL(value)
        except httpx.InvalidURL:
            raise ValueError("Invalid HTTPS callback URL.") from None
        if (
            parsed.scheme != "https"
            or not parsed.host
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Use an HTTPS callback without credentials, query or fragment.")
        return value


class RetryPolicy(StrictInput):
    count: int = Field(ge=0, le=3, strict=True)
    status: list[str] = Field(max_length=10)


class ClickToCallRequest(StrictInput):
    from_number: str = Field(alias="from", pattern=r"^\+?[1-9][0-9]{7,14}$")
    to: list[str] = Field(min_length=1, max_length=500)
    caller_id: str = Field(pattern=r"^\+?[1-9][0-9]{7,14}$")
    to_caller_id: str | None = Field(default=None, pattern=r"^\+?[1-9][0-9]{7,14}$")
    record: StrictBool = False
    early_media: StrictBool = False
    callbacks: list[CallbackOverride] | None = Field(default=None, max_length=10)
    retry: StrictInt | RetryPolicy = 0
    metadata: dict[str, str] = Field(default_factory=dict, max_length=3)
    call_flow_id: str = Field(min_length=1, max_length=256)

    @field_validator("from_number", mode="before")
    @classmethod
    def source_number(cls, value: object) -> object:
        return str(value) if type(value) is int else value

    @field_validator("to", mode="before")
    @classmethod
    def destination_numbers(cls, value: object) -> object:
        return (
            [str(item) if type(item) is int else item for item in value]
            if isinstance(value, list)
            else value
        )

    @field_validator("to")
    @classmethod
    def destinations(cls, values: list[str]) -> list[str]:
        import re

        if len(set(values)) != len(values) or any(
            not re.fullmatch(r"\+?[1-9][0-9]{7,14}", value) for value in values
        ):
            raise ValueError("Supply distinct bounded telephone destinations.")
        return values

    @model_validator(mode="after")
    def limits(self) -> "ClickToCallRequest":
        if isinstance(self.retry, int) and (
            isinstance(self.retry, bool) or not 0 <= self.retry <= 3
        ):
            raise ValueError("Airtel retry count must be 0–3.")
        if len(json.dumps(self.metadata).encode()) > 4096:
            raise ValueError("Metadata exceeds the application budget.")
        return self


class AirtelRequestFailure(Exception):
    """Sanitized outcome; never includes request URL/headers, tokens or provider body."""


class AirtelRestAdapter:
    def __init__(
        self,
        app_id: str,
        api_key: str,
        *,
        c2c_origin_confirmed: bool = False,
        callback_variant_confirmed: bool = False,
    ) -> None:
        self._app_id, self._api_key = app_id, api_key
        self._c2c_origin_confirmed = c2c_origin_confirmed
        self._callback_variant_confirmed = callback_variant_confirmed

    async def request(
        self,
        method: Literal["POST", "GET"],
        path: str,
        *,
        body: bytes = b"",
        recording_token: str | None = None,
    ) -> tuple[int, bytes]:
        if (method, path) not in {("POST", C2C_PATH), ("GET", RECORDING_PATH)}:
            raise AirtelRequestFailure("Unsupported Airtel operation.")
        if method == "POST" and not self._c2c_origin_confirmed:
            raise AirtelRequestFailure("The account's click-to-call origin is not confirmed.")
        if method == "GET" and (recording_token is None or body):
            raise AirtelRequestFailure("Recording requests require a token and an empty body.")
        if not isinstance(body, bytes) or len(body) > 65536:
            raise AirtelRequestFailure("Airtel request body exceeds the supported budget.")
        url = ORIGIN + path
        if recording_token is not None:
            if (
                method != "GET"
                or not 1 <= len(recording_token) <= 4096
                or any(ord(c) < 33 or ord(c) > 126 for c in recording_token)
            ):
                raise AirtelRequestFailure("Invalid recording reference.")
            # Guide p12 curl places token in query. Never expose/log this URL.
            url += "?" + urlencode({"token": recording_token})
        maximum = 20 * 1024 * 1024 if recording_token else 65536
        try:
            with private_transport_logs():
                return await self._send(method, url, body, maximum)
        except (httpx.HTTPError, TimeoutError, ValueError):
            raise AirtelRequestFailure(
                "Airtel request failed; no automatic retry or confirmed call outcome."
            ) from None

    async def _send(self, method: str, url: str, body: bytes, maximum: int) -> tuple[int, bytes]:
        async with (
            asyncio.timeout(35),
            httpx.AsyncClient(timeout=30, follow_redirects=False, trust_env=False) as client,
            client.stream(
                method,
                url,
                content=body,
                headers=signed_headers(self._app_id, self._api_key, body, at=utc_now())
                | {"Accept-Encoding": "identity"},
            ) as response,
        ):
            if (
                not 200 <= response.status_code < 300
                or response.headers.get("content-encoding", "identity") != "identity"
            ):
                raise AirtelRequestFailure(
                    "Airtel rejected or could not confirm the request; do not retry a call automatically."
                )
            result = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=8192):
                result.extend(chunk)
                if len(result) > maximum:
                    raise AirtelRequestFailure("Airtel response exceeds the supported budget.")
            return response.status_code, bytes(result)

    async def click_to_call(self, payload: ClickToCallRequest) -> tuple[int, bytes]:
        if not self._c2c_origin_confirmed:
            raise AirtelRequestFailure(
                "Confirm the account's click-to-call origin before using this adapter."
            )
        if payload.callbacks and not self._callback_variant_confirmed:
            raise AirtelRequestFailure(
                "Confirm the account's callback field variant before sending overrides."
            )
        body = json.dumps(
            payload.model_dump(mode="json", by_alias=True, exclude_none=True),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return await self.request("POST", C2C_PATH, body=body)

    async def recording(self, token: str) -> bytes:
        _, body = await self.request("GET", RECORDING_PATH, recording_token=token)
        return body
