"""Airtel VoiceBOT v1.0.0 pp14–20. Offline codec; identities require an authenticated host.

Unlike Smartflo, this specification has no sequenceNumber requirement. Mark echoes
caused by clear are cleared audio, never evidence of completed playback.
"""

import base64
import binascii
import json
import re
from collections import OrderedDict
from typing import Any, NoReturn, cast
from uuid import uuid4

from app.core.exceptions import ValidationError
from app.features.voice_assistant.media_contracts import AudioFormat


def fail(message: str) -> NoReturn:
    raise ValidationError(message)


def identity(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 256
        or any(ord(c) < 32 or ord(c) > 126 for c in value)
    ):
        raise ValidationError("Invalid bounded Airtel session identity.")
    return value


def keys(value: Any, required: set[str], optional: set[str] | None = None) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or not required <= value.keys()
        or value.keys() - required - (optional or set())
    ):
        raise ValidationError("Airtel message fields do not match the documented envelope.")
    return cast(dict[str, Any], value)


class AirtelMediaSession:
    audio_format = AudioFormat(encoding="mulaw", sample_rate=8000, channels=1, frame_ms=20)

    def __init__(self, *, account_sid: str, call_sid: str | None = None) -> None:
        self.account_sid = identity(account_sid)
        self.call_sid = identity(call_sid) if call_sid is not None else None
        self.stream_sid: str | None = None
        self.connected = self.stopped = self.held = self.termination_requested = False
        self.marks: OrderedDict[str, str] = OrderedDict()
        self._nonce, self._counter = uuid4().hex[:16], 0

    def ingest(self, message: str) -> dict[str, Any]:
        if not isinstance(message, str) or len(message.encode("utf-8")) > 65536 or self.stopped:
            raise ValidationError("Airtel stream stopped or message exceeds its limit.")
        try:
            frame = json.loads(message)
        except (ValueError, RecursionError):
            raise ValidationError("Invalid Airtel JSON text frame.") from None
        if not isinstance(frame, dict):
            fail("Airtel frame must be an object.")
        kind = frame.get("event")
        if kind == "connected":
            keys(frame, {"event", "protocol", "version"})
            if self.connected or frame["protocol"] != "Call" or frame["version"] != "1.0.0":
                fail("Unsupported or repeated Airtel protocol handshake.")
            self.connected = True
            return {"event": kind}
        if not self.connected:
            fail("Airtel connected must precede all session messages.")
        if kind == "start":
            keys(frame, {"event", "streamSid", "start"})
            start = keys(
                frame["start"],
                {
                    "streamSid",
                    "accountSid",
                    "callSid",
                    "mediaFormat",
                    "callerNumber",
                    "calledNumber",
                },
                {"customParameters", "customParams"},
            )
            sid, call = identity(start["streamSid"]), identity(start["callSid"])
            if (
                self.stream_sid
                or frame["streamSid"] != sid
                or start["accountSid"] != self.account_sid
                or (self.call_sid is not None and self.call_sid != call)
            ):
                fail("Airtel start identity does not match its authenticated reservation.")
            fmt = keys(start["mediaFormat"], {"encoding", "sampleRate", "channels"})
            if (
                not isinstance(fmt["encoding"], str)
                or fmt["encoding"] not in {"ulaw", "audio/x-mulaw"}
                or type(fmt["sampleRate"]) not in {str, int}
                or str(fmt["sampleRate"]) != "8000"
                or type(fmt["channels"]) not in {str, int}
                or str(fmt["channels"]) != "1"
            ):
                fail("Airtel requires mono G.711 mu-law at 8000 Hz.")
            for field in ("callerNumber", "calledNumber"):
                if not isinstance(start[field], str) or not re.fullmatch(
                    r"\+?[0-9]{8,15}", start[field]
                ):
                    fail("Airtel start numbers must be bounded telephone identifiers.")
            parameters = []
            for field in ("customParameters", "customParams"):
                if field in start:
                    raw = start[field]
                    if not isinstance(raw, str) or len(raw) > 4096:
                        fail("Airtel custom parameters must be a bounded JSON string.")
                    try:
                        parsed = json.loads(raw)
                    except (ValueError, RecursionError):
                        raise ValidationError("Invalid Airtel custom parameter JSON.") from None
                    if (
                        not isinstance(parsed, dict)
                        or len(parsed) > 3
                        or any(
                            not isinstance(k, str)
                            or len(k) > 128
                            or not isinstance(v, (str, int, bool, type(None)))
                            or len(str(v)) > 512
                            for k, v in parsed.items()
                        )
                    ):
                        fail("Airtel custom parameters exceed supported metadata bounds.")
                    parameters.append(parsed)
            if len(parameters) == 2 and parameters[0] != parameters[1]:
                fail("Conflicting Airtel custom parameter variants.")
            self.stream_sid, self.call_sid = sid, call
            return {
                "event": kind,
                "stream_sid": sid,
                "call_sid": call,
                "caller_number": start["callerNumber"],
                "called_number": start["calledNumber"],
                "custom_parameters": parameters[0] if parameters else {},
            }
        if not self.stream_sid or frame.get("streamSid") != self.stream_sid:
            fail("Airtel stream identity changed or start is missing.")
        detail = {
            "media": "media",
            "dtmf": "dtmf",
            "stop": "stop",
            "callState": "call",
            "mark": "mark",
        }.get(str(kind))
        if detail is None:
            fail("Unsupported Airtel inbound event.")
        keys(frame, {"event", "streamSid", str(detail)})
        data = frame[str(detail)]
        if kind == "media":
            keys(data, {"payload"})
            payload = data["payload"]
            if not isinstance(payload, str) or len(payload) != 216:
                fail("Airtel inbound media must contain one 160-byte frame.")
            try:
                audio = base64.b64decode(payload, validate=True)
            except (ValueError, binascii.Error):
                raise ValidationError("Invalid Airtel Base64 audio.") from None
            if len(audio) != 160:
                fail("Invalid Airtel mu-law frame length.")
            return {"event": kind, "audio": audio}
        if kind == "dtmf":
            keys(data, {"digit"})
            if not isinstance(data["digit"], str) or data["digit"] not in tuple("0123456789*#"):
                fail("Unsupported Airtel DTMF digit.")
            return {"event": kind, "digit": data["digit"]}
        if kind == "callState":
            keys(data, {"state"})
            if not isinstance(data["state"], str) or data["state"] not in {"hold", "unhold"}:
                fail("Unsupported Airtel call state.")
            self.held = data["state"] == "hold"
            return {"event": kind, "state": data["state"]}
        if kind == "mark":
            keys(data, {"name"})
            name = data["name"]
            if not isinstance(name, str) or name not in self.marks:
                fail("Airtel playback acknowledgement has no matching sent mark.")
            state = self.marks[name]
            duplicate = state in {"played", "clear_acknowledged"}
            state = "played" if state in {"sent", "played"} else "clear_acknowledged"
            self.marks[name] = state
            return {"event": kind, "name": name, "playback": state, "duplicate": duplicate}
        keys(data, {"accountSid", "callSid"}, {"streamSid"})
        if (
            data["accountSid"] != self.account_sid
            or data["callSid"] != self.call_sid
            or data.get("streamSid", self.stream_sid) != self.stream_sid
        ):
            fail("Airtel stop identity differs from its session.")
        self.stopped = True
        return {"event": "stop"}

    def output(
        self, *, audio: bytes | None = None, mark: str | None = None, clear: bool = False
    ) -> dict[str, Any]:
        if not self.stream_sid or self.stopped:
            fail("Airtel output requires a started active stream.")
        if sum((audio is not None, mark is not None, clear)) != 1:
            fail("Choose exactly one Airtel output event.")
        base = {"streamSid": self.stream_sid}
        if clear:
            for name, state in self.marks.items():
                if state == "sent":
                    self.marks[name] = "cleared"
            return base | {"event": "clear"}
        if self.termination_requested or self.held:
            fail("Airtel audio is disabled during hold or termination.")
        if mark is not None:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", mark):
                fail("Invalid local playback label.")
            while len(self.marks) >= 256 and next(iter(self.marks.values())) in {
                "played",
                "clear_acknowledged",
            }:
                self.marks.popitem(last=False)
            if len(self.marks) >= 256:
                fail("Airtel playback acknowledgements exceeded their bounded budget.")
            self._counter += 1
            name = f"afs-{self._nonce}-{self._counter}"
            self.marks[name] = "sent"
            return base | {"event": "mark", "mark": {"name": name}}
        if not isinstance(audio, bytes) or len(audio) != 160:
            fail("Airtel output requires raw 160-byte mu-law frames, without file headers.")
        return base | {
            "event": "media",
            "media": {"payload": base64.b64encode(audio).decode("ascii")},
        }

    def terminate(self, code: int, text: str, fallback_number: str | None = None) -> dict[str, Any]:
        if not self.stream_sid or self.stopped or self.termination_requested:
            fail("Airtel termination requires one active stream and is not repeatable.")
        if (
            type(code) is not int
            or code not in {1, 2, 3}
            or not isinstance(text, str)
            or not 1 <= len(text) <= 300
            or any(ord(c) < 32 for c in text)
        ):
            fail("Invalid documented Airtel termination reason.")
        reason: dict[str, Any] = {"code": code, "text": text}
        if code == 3:
            if not isinstance(fallback_number, str) or not re.fullmatch(
                r"\+[1-9][0-9]{7,14}", fallback_number
            ):
                fail("Particular-DID fallback requires an E.164 number.")
            reason["fallbackNumber"] = fallback_number
        elif fallback_number is not None:
            fail("A particular fallback DID is only sent with reason code 3.")
        self.termination_requested = True
        return {"event": "terminate", "streamSid": self.stream_sid, "reason": reason}
