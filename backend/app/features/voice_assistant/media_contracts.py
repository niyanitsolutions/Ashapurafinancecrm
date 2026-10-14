"""Transport-neutral ports and bounded media ingress. No SIP or live speech emulation."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class AudioFormat:
    encoding: Literal["mulaw", "pcm_s16le"] = "mulaw"
    sample_rate: int = 8000
    channels: int = 1
    frame_ms: int = 20

    def __post_init__(self) -> None:
        if (
            self.encoding not in {"mulaw", "pcm_s16le"}
            or self.sample_rate not in {8000, 16000, 24000, 48000}
            or self.channels not in {1, 2}
            or self.frame_ms not in {10, 20, 40}
        ):
            raise ValueError("Unsupported negotiated audio format.")

    @property
    def frame_bytes(self) -> int:
        return (
            self.sample_rate
            * self.channels
            * (2 if self.encoding == "pcm_s16le" else 1)
            * self.frame_ms
            // 1000
        )

    @property
    def silence_byte(self) -> int:
        return 0 if self.encoding == "pcm_s16le" else 255


class MediaCodec(Protocol):
    stopped: bool
    audio_format: AudioFormat

    def output(
        self, *, audio: bytes | None = None, mark: str | None = None, clear: bool = False
    ) -> dict[str, Any]: ...


class StreamingRecognizer(Protocol):
    def recognize(self, audio: AsyncIterator[bytes], language: str) -> AsyncIterator[str]: ...


class StreamingSynthesizer(Protocol):
    def synthesize(self, text: str, language: str) -> AsyncIterator[bytes]: ...


class LanguageIdentifier(Protocol):
    async def identify(self, audio: bytes, allowed_languages: tuple[str, ...]) -> str: ...


class ComposedSpeechAdapter:
    """Replace recognition and synthesis independently; adapters must negotiate format."""

    def __init__(self, recognizer: StreamingRecognizer, synthesizer: StreamingSynthesizer) -> None:
        self.recognizer, self.synthesizer = recognizer, synthesizer

    def recognize(self, audio: AsyncIterator[bytes], language: str) -> AsyncIterator[str]:
        return self.recognizer.recognize(audio, language)

    def synthesize(self, text: str, language: str) -> AsyncIterator[bytes]:
        return self.synthesizer.synthesize(text, language)


class BoundedAudioBuffer(AsyncIterator[bytes]):
    """Ingress backpressure fails explicitly; stop flushes buffered obsolete audio."""

    def __init__(
        self, *, max_frames: int = 64, max_frame_bytes: int = 4096, timeout_seconds: float = 0.25
    ) -> None:
        if not (
            1 <= max_frames <= 256 and 1 <= max_frame_bytes <= 32000 and 0 < timeout_seconds <= 2
        ):
            raise ValueError("Audio queue limits must be bounded.")
        self.queue: asyncio.Queue[bytes | None] = asyncio.Queue(max_frames)
        self.max_frame_bytes, self.timeout_seconds = max_frame_bytes, timeout_seconds
        self.closed = False

    async def feed(self, frame: bytes) -> None:
        if (
            self.closed
            or not isinstance(frame, bytes)
            or not 0 < len(frame) <= self.max_frame_bytes
        ):
            raise ValueError("Audio buffer is closed or frame is invalid/oversized.")
        try:
            await asyncio.wait_for(self.queue.put(frame), timeout=self.timeout_seconds)
        except TimeoutError:
            self.close()
            raise TimeoutError(
                "Audio consumer is overloaded; terminate or escalate the session."
            ) from None
        if self.closed:
            raise ValueError("Audio buffer closed during ingestion.")

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        while not self.queue.empty():
            self.queue.get_nowait()
        self.queue.put_nowait(None)

    def __aiter__(self) -> "BoundedAudioBuffer":
        return self

    async def __anext__(self) -> bytes:
        if self.closed:
            raise StopAsyncIteration
        frame = await self.queue.get()
        if frame is None or self.closed:
            raise StopAsyncIteration
        return frame
