import base64
import json

import pytest

from app.core.exceptions import ForbiddenError, ValidationError
from app.features.voice_assistant.exotel import ExotelAdapter, ExotelMediaSession


def session():
    codec = ExotelMediaSession(account_sid="reserved-account", call_sid="reserved-call")
    codec.ingest(json.dumps({"event": "connected"}))
    start = {
        "event": "start",
        "sequence_number": "1",
        "stream_sid": "reserved-stream",
        "start": {
            "stream_sid": "reserved-stream",
            "call_sid": "reserved-call",
            "account_sid": "reserved-account",
            "media_format": {
                "encoding": "audio/x-raw",
                "sample_rate": "8000",
                "bit_rate": "16",
            },
        },
    }
    return codec, start


def test_exotel_pcm_playback_and_interruption():
    codec, start = session()
    assert codec.ingest(json.dumps(start))["sample_rate"] == 8000
    audio = bytes(3200)
    event = {
        "event": "media",
        "sequence_number": "2",
        "stream_sid": "reserved-stream",
        "media": {"payload": base64.b64encode(audio).decode()},
    }
    assert codec.ingest(json.dumps(event))["audio"] == audio
    assert codec.output(audio)["media"]["payload"] == event["media"]["payload"]
    assert codec.output(interrupt=True)["event"] == "clear"
    assert codec.output(mark="turn_1")["mark"]["name"] == "turn_1"
    with pytest.raises(ValidationError):
        codec.ingest(json.dumps(event))


def test_exotel_identity_format_and_frame_bounds():
    codec, start = session()
    start["start"]["account_sid"] = "other-account"
    with pytest.raises(ValidationError):
        codec.ingest(json.dumps(start))
    start["start"]["account_sid"] = "reserved-account"
    start["start"]["media_format"]["sample_rate"] = "16000"
    with pytest.raises(ValidationError):
        codec.ingest(json.dumps(start))
    start["start"]["media_format"]["sample_rate"] = "8000"
    codec.ingest(json.dumps(start))
    with pytest.raises(ValidationError):
        codec.output(bytes(100001))
    for invalid in ("[]", "bad-json", "x" * 150001):
        with pytest.raises(ValidationError):
            codec.ingest(invalid)
    for payload in ("not-base64", base64.b64encode(b"x").decode()):
        with pytest.raises(ValidationError):
            codec.ingest(
                json.dumps(
                    {
                        "event": "media",
                        "sequence_number": "2",
                        "stream_sid": "reserved-stream",
                        "media": {"payload": payload},
                    }
                )
            )


def test_exotel_stop_and_unstarted_stream():
    codec, start = session()
    with pytest.raises(ValidationError):
        codec.output(interrupt=True)
    codec.ingest(json.dumps(start))
    codec.ingest(
        json.dumps(
            {
                "event": "stop",
                "sequence_number": "2",
                "stream_sid": "reserved-stream",
                "stop": {
                    "call_sid": "reserved-call",
                    "account_sid": "reserved-account",
                    "reason": "callended",
                },
            }
        )
    )
    with pytest.raises(ValidationError):
        codec.output(interrupt=True)


async def test_exotel_live_methods_always_block():
    adapter = ExotelAdapter()
    operations = [
        adapter.verify_event(b"{}", {}),
        adapter.dial("test-destination", "test-key"),
        adapter.transfer("test-call", "test-destination"),
        adapter.hangup("test-call"),
        adapter.reconcile("test-call"),
    ]
    for operation in operations:
        with pytest.raises(ForbiddenError):
            await operation
    assert not adapter.capabilities.streaming_audio
