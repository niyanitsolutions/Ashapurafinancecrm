"""Offline Exotel protocol boundary; never authenticates a webhook or places a call.

Reference: https://developer.exotel.com/docs/agentstream/websocket-protocol
Reservation identities MUST eventually come from an authenticated provider flow.
Matching an account/call field by itself is not proof of event authenticity.
"""

import base64
import binascii
import json
import re
from typing import Any, NoReturn

from app.core.exceptions import ForbiddenError, ValidationError
from app.features.voice_assistant.adapters import ProviderCapabilities


def blocked() -> NoReturn:
    raise ForbiddenError(
        "Exotel sandbox, event authentication and live readiness are not configured."
    )


class ExotelAdapter:
    """Fail-closed implementation of the telephony interface for the selected vendor.

    No HTTP client exists here. Protocol parsing is available for offline fixtures;
    all live methods reject even if accidentally invoked outside the router gates.
    """

    capabilities = ProviderCapabilities()

    async def verify_event(self, body: bytes, headers: dict[str, str]) -> dict[str, Any]:
        blocked()

    async def dial(self, destination: str, idempotency_key: str) -> str:
        blocked()

    async def transfer(self, provider_call_id: str, destination: str) -> None:
        blocked()

    async def hangup(self, provider_call_id: str) -> None:
        blocked()

    async def reconcile(self, provider_call_id: str) -> dict[str, Any]:
        blocked()


class ExotelMediaSession:
    """Bounded in-memory codec for preverified sessions, with no public socket route."""

    def __init__(self, *, account_sid: str, call_sid: str, sample_rate: int = 8000) -> None:
        if not all(re.fullmatch(r"[A-Za-z0-9_-]{1,128}", sid) for sid in (account_sid, call_sid)):
            raise ValidationError("Invalid reserved Exotel identity.")
        if sample_rate not in {8000, 16000, 24000}:
            raise ValidationError("Unsupported Exotel PCM rate.")
        self.account_sid = account_sid
        self.call_sid = call_sid
        self.sample_rate = sample_rate
        self.stream_sid: str | None = None
        self.connected = False
        self.stopped = False
        self.last_sequence = 0

    def ingest(self, message: str) -> dict[str, Any]:
        if len(message) > 150000 or self.stopped:
            raise ValidationError("Exotel media session stopped or frame too large.")
        try:
            event = json.loads(message)
        except (ValueError, RecursionError) as exc:
            raise ValidationError("Invalid Exotel media JSON.") from exc
        if not isinstance(event, dict):
            raise ValidationError("Invalid Exotel media frame.")
        kind = event.get("event")
        result: dict[str, Any]
        if kind == "connected":
            if self.connected:
                raise ValidationError("Duplicate Exotel connection event.")
            self.connected = True
            return {"event": "connected"}
        if not self.connected:
            raise ValidationError("Exotel connection event required first.")
        sequence = event.get("sequence_number")
        if (
            not re.fullmatch(r"[0-9]{1,12}", str(sequence))
            or int(str(sequence)) <= self.last_sequence
        ):
            raise ValidationError("Exotel sequence is invalid or replayed.")
        if kind == "start":
            start = event.get("start")
            if not isinstance(start, dict) or self.stream_sid is not None:
                raise ValidationError("Invalid or repeated Exotel start event.")
            if (
                start.get("account_sid") != self.account_sid
                or start.get("call_sid") != self.call_sid
            ):
                raise ValidationError("Exotel session does not match its reservation.")
            sid = start.get("stream_sid")
            if (
                not isinstance(sid, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", sid)
                or event.get("stream_sid") != sid
            ):
                raise ValidationError("Invalid Exotel stream identity.")
            fmt = start.get("media_format")
            if (
                not isinstance(fmt, dict)
                or fmt.get("encoding") != "audio/x-raw"
                or str(fmt.get("bit_rate")) != "16"
                or str(fmt.get("sample_rate")) != str(self.sample_rate)
            ):
                raise ValidationError("Exotel audio format differs from configured PCM.")
            self.stream_sid = sid
            result = {"event": "start", "sample_rate": self.sample_rate}
        else:
            if not self.stream_sid or event.get("stream_sid") != self.stream_sid:
                raise ValidationError("Exotel stream has not started or identity changed.")
            if kind == "media":
                media = event.get("media")
                payload = media.get("payload") if isinstance(media, dict) else None
                if not isinstance(payload, str) or len(payload) > 133336:
                    raise ValidationError("Invalid Exotel audio payload.")
                try:
                    audio = base64.b64decode(payload, validate=True)
                except (ValueError, binascii.Error) as exc:
                    raise ValidationError("Invalid Exotel audio encoding.") from exc
                if not audio or len(audio) > 100000 or len(audio) % 2:
                    raise ValidationError("Invalid Exotel 16-bit PCM payload length.")
                result = {"event": "media", "audio": audio}
            elif kind == "stop":
                stop = event.get("stop")
                if (
                    not isinstance(stop, dict)
                    or stop.get("call_sid") != self.call_sid
                    or stop.get("account_sid") != self.account_sid
                ):
                    raise ValidationError("Exotel stop identity differs from reservation.")
                self.stopped = True
                result = {"event": "stop", "reason": stop.get("reason")}
            elif kind in {"mark", "dtmf"}:
                detail = event.get(kind)
                if not isinstance(detail, dict):
                    raise ValidationError("Invalid Exotel control event.")
                if kind == "dtmf" and (
                    not isinstance(detail.get("digit"), str)
                    or len(detail["digit"]) != 1
                    or detail["digit"] not in "0123456789*#ABCD"
                ):
                    raise ValidationError("Invalid Exotel DTMF digit.")
                result = {"event": kind, "detail": detail}
            else:
                raise ValidationError("Unsupported Exotel media event.")
        self.last_sequence = int(str(sequence))
        return result

    def output(
        self, audio: bytes | None = None, *, mark: str | None = None, interrupt: bool = False
    ) -> dict[str, Any]:
        if not self.stream_sid or self.stopped:
            raise ValidationError("Exotel output requires an active stream.")
        if sum((audio is not None, mark is not None, interrupt)) != 1:
            raise ValidationError("Choose exactly one Exotel output event.")
        if interrupt:
            return {"event": "clear", "stream_sid": self.stream_sid}
        if mark is not None:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", mark):
                raise ValidationError("Invalid playback marker.")
            return {"event": "mark", "stream_sid": self.stream_sid, "mark": {"name": mark}}
        assert audio is not None
        if not 3200 <= len(audio) <= 100000 or len(audio) % 320:
            raise ValidationError(
                "Exotel output PCM must be 3200–100000 bytes, aligned to 320 bytes."
            )
        return {
            "event": "media",
            "stream_sid": self.stream_sid,
            "media": {"payload": base64.b64encode(audio).decode("ascii")},
        }
