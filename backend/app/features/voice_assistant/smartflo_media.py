"""Smartflo's documented mu-law protocol; no Exotel PCM assumptions."""

import base64
import binascii
import json
import re
from typing import Any

from app.core.exceptions import ValidationError
from app.features.voice_assistant.media_contracts import AudioFormat


class SmartfloMediaSession:
    audio_format = AudioFormat()

    def __init__(self, account_sid: str, call_sid: str) -> None:
        if not all(re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", sid) for sid in (account_sid, call_sid)):
            raise ValidationError("Media requires bounded reserved account and call identities.")
        self.account_sid, self.call_sid = account_sid, call_sid
        self.stream_sid: str | None = None
        self.connected = False
        self.stopped = False
        self.last_sequence = 0
        self.output_chunk = 0

    def ingest(self, message: str) -> dict[str, Any]:
        if len(message) > 65536 or self.stopped:
            raise ValidationError("Media frame exceeds limits or stream has ended.")
        try:
            event = json.loads(message)
        except (ValueError, RecursionError) as exc:
            raise ValidationError("Invalid Smartflo media JSON.") from exc
        if not isinstance(event, dict):
            raise ValidationError("Media frame must be an object.")
        kind = event.get("event")
        if kind == "connected":
            if self.connected:
                raise ValidationError("Repeated connection event.")
            self.connected = True
            return {"event": "connected"}
        sequence = str(event.get("sequenceNumber"))
        if (
            not self.connected
            or not re.fullmatch(r"[0-9]{1,12}", sequence)
            or int(sequence) <= self.last_sequence
        ):
            raise ValidationError("Connection missing or media sequence invalid/replayed.")
        result: dict[str, Any]
        if kind == "start":
            start = event.get("start")
            if not isinstance(start, dict) or self.stream_sid:
                raise ValidationError("Invalid or repeated start frame.")
            if start.get("accountSid") != self.account_sid or start.get("callSid") != self.call_sid:
                raise ValidationError("Smartflo media identity does not match reservation.")
            fmt = start.get("mediaFormat", {})
            if not isinstance(fmt, dict) or any(
                str(fmt.get(k)) != str(v)
                for k, v in {
                    "encoding": "audio/x-mulaw",
                    "sampleRate": 8000,
                    "bitRate": 64,
                    "bitDepth": 8,
                }.items()
            ):
                raise ValidationError("Smartflo requires negotiated mu-law mono 8000 Hz audio.")
            sid = start.get("streamSid")
            if (
                not isinstance(sid, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", sid)
                or event.get("streamSid") != sid
            ):
                raise ValidationError("Invalid Smartflo stream identifier.")
            self.stream_sid = sid
            result = {"event": "start", "encoding": "audio/x-mulaw", "sample_rate": 8000}
        else:
            if not self.stream_sid or event.get("streamSid") != self.stream_sid:
                raise ValidationError("Media stream not started or identifier changed.")
            detail = event.get(str(kind))
            if not isinstance(detail, dict):
                raise ValidationError("Invalid Smartflo frame details.")
            if kind == "media":
                payload = detail.get("payload")
                if not isinstance(payload, str) or len(payload) > 32768:
                    raise ValidationError("Invalid or oversized audio payload.")
                try:
                    audio = base64.b64decode(payload, validate=True)
                except (ValueError, binascii.Error) as exc:
                    raise ValidationError("Invalid base64 audio.") from exc
                if not audio:
                    raise ValidationError("Empty audio frame.")
                result = {"event": "media", "audio": audio}
            elif kind == "stop":
                if (
                    detail.get("accountSid") != self.account_sid
                    or detail.get("callSid") != self.call_sid
                ):
                    raise ValidationError("Stop identity does not match reservation.")
                self.stopped = True
                result = {"event": "stop"}
            elif kind == "mark":
                name = detail.get("name")
                if not isinstance(name, str) or not 1 <= len(name) <= 64:
                    raise ValidationError("Invalid playback mark.")
                result = {"event": "mark", "name": name}
            elif kind == "dtmf":
                digit = detail.get("digit")
                if not isinstance(digit, str) or len(digit) != 1 or digit not in "0123456789*#ABCD":
                    raise ValidationError("Invalid DTMF frame.")
                result = {"event": "dtmf", "digit": digit}
            else:
                raise ValidationError("Unsupported Smartflo media event.")
        self.last_sequence = int(sequence)
        return result

    def output(
        self, *, audio: bytes | None = None, mark: str | None = None, clear: bool = False
    ) -> dict[str, Any]:
        if not self.stream_sid or self.stopped:
            raise ValidationError("Audio output requires an active Smartflo stream.")
        if sum((audio is not None, mark is not None, clear)) != 1:
            raise ValidationError("Choose one output event.")
        base = {"streamSid": self.stream_sid}
        if clear:
            return {**base, "event": "clear"}
        if mark is not None:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", mark):
                raise ValidationError("Invalid playback mark.")
            return {**base, "event": "mark", "mark": {"name": mark}}
        assert audio is not None
        if not 160 <= len(audio) <= 16000 or len(audio) % 160:
            raise ValidationError("Output mu-law frames must align to 160 bytes and be bounded.")
        self.output_chunk += 1
        return {
            **base,
            "event": "media",
            "media": {
                "payload": base64.b64encode(audio).decode("ascii"),
                "chunk": self.output_chunk,
            },
        }


def offline_audio_test() -> dict[str, Any]:
    session = SmartfloMediaSession("offline-account", "offline-call")
    session.ingest('{"event":"connected"}')
    session.ingest(
        json.dumps(
            {
                "event": "start",
                "sequenceNumber": "1",
                "streamSid": "offline-stream",
                "start": {
                    "accountSid": "offline-account",
                    "callSid": "offline-call",
                    "streamSid": "offline-stream",
                    "mediaFormat": {
                        "encoding": "audio/x-mulaw",
                        "sampleRate": 8000,
                        "bitRate": 64,
                        "bitDepth": 8,
                    },
                },
            }
        )
    )
    session.output(audio=bytes([255]) * 160)
    session.output(clear=True)
    return {
        "status": "offline_protocol_passed",
        "live_stream_verified": False,
        "message": "Local mu-law framing and clear-message validation passed. No Smartflo socket, speech service or interruption latency was tested.",
    }
