"""Provider-neutral dynamic response and interruption orchestration.

Speech adapters must supply recognition/synthesis in the codec's negotiated format.
This engine is tested with adapters, but is not registered for live calls.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from time import monotonic
from typing import Any, Protocol

from app.features.voice_assistant.adapters import SAFETY_POLICY, ConversationAdapter
from app.features.voice_assistant.intent_policy import proposal_policy
from app.features.voice_assistant.media_contracts import MediaCodec


class StreamingSpeechAdapter(Protocol):
    def recognize(self, audio: AsyncIterator[bytes], language: str) -> AsyncIterator[str]: ...
    def synthesize(self, text: str, language: str) -> AsyncIterator[bytes]: ...


class DynamicAudioConversation:
    def __init__(
        self,
        *,
        model: ConversationAdapter,
        speech: StreamingSpeechAdapter,
        codec: MediaCodec,
        retrieve: Callable[[str, str], Awaitable[list[dict[str, Any]]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
        instructions: str,
        operational_rules: str,
        language: str = "en",
        max_turns: int = 30,
        max_seconds: int = 300,
        authorize: Callable[[], Awaitable[bool]] | None = None,
    ) -> None:
        if not 1 <= max_turns <= 60 or not 1 <= max_seconds <= 1800:
            raise ValueError("Conversation limits must be bounded.")
        self.model, self.speech, self.codec = model, speech, codec
        self.audio_format = codec.audio_format
        self.retrieve, self.send = retrieve, send
        self.instructions, self.operational_rules, self.language = (
            instructions,
            operational_rules,
            language,
        )
        self.max_turns, self.max_seconds = max_turns, max_seconds
        self.history: list[dict[str, str]] = []
        self.turns = 0
        self.started = monotonic()
        self.closed = False
        self.escalation_required = False
        self._task: asyncio.Task[None] | None = None
        # The host must revalidate the trusted session, current permissions,
        # publications, release and emergency state. An unbound engine is denied.
        self.authorize = authorize
        self._generation = 0
        self._control = asyncio.Lock()

    async def _current(self, generation: int) -> bool:
        if (
            self.closed or self.codec.stopped or generation != self._generation
            or monotonic() - self.started >= self.max_seconds
            or self.authorize is None
        ):
            return False
        permitted = await self.authorize()
        current = not (
            self.closed or self.codec.stopped or generation != self._generation
            or monotonic() - self.started >= self.max_seconds
        )
        if current and not permitted:
            self.escalation_required = True
            await self.send(self.codec.output(clear=True))
        return bool(permitted) and current

    async def interrupt(self) -> None:
        async with self._control:
            await self._interrupt()

    async def _interrupt(self) -> None:
        self._generation += 1
        if self._task and not self._task.done():
            self._task.cancel()
            finished, _ = await asyncio.wait({self._task}, timeout=1)
            if not finished:
                # A noncooperative adapter cannot hold takeover indefinitely or
                # permit another generation to accumulate behind it.
                self.closed = True
                self.escalation_required = True
                self._task.add_done_callback(self._consume_result)
            else:
                self._consume_result(self._task)
        elif self._task and not self._task.cancelled():
            if self._task.exception() is not None:
                self.escalation_required = True
        if not self.codec.stopped:
            await self.send(self.codec.output(clear=True))

    def _consume_result(self, task: asyncio.Task[None]) -> None:
        if not task.cancelled() and task.exception() is not None:
            self.escalation_required = True

    async def question(self, transcript: str) -> None:
        async with self._control:
            await self._question(transcript)

    async def _question(self, transcript: str) -> None:
        if self.closed:
            return
        if self.turns >= self.max_turns or monotonic() - self.started >= self.max_seconds:
            await self._close()
            return
        transcript = transcript.strip()
        if not transcript or len(transcript) > 2000:
            raise ValueError("Recognized transcript is empty or oversized.")
        await self._interrupt()
        if self.closed:
            return
        self.turns += 1
        self._task = asyncio.create_task(self._reply(transcript, self._generation))

    async def _reply(self, question: str, generation: int) -> None:
        async with asyncio.timeout(max(0, self.max_seconds - (monotonic() - self.started))):
            await self._generate(question, generation)

    async def _generate(self, question: str, generation: int) -> None:
        if not await self._current(generation):
            self.escalation_required = True
            return
        context = " ".join(turn["content"] for turn in self.history[-4:] if turn["role"] == "user")
        sources = await self.retrieve(context + " " + question, self.language)
        if not await self._current(generation):
            return
        answer = await self.model.respond(
            question=question,
            history=self.history[-10:],
            sources=sources,
            instructions=f"{SAFETY_POLICY}\nBehaviour configuration: {self.instructions}",
            operational_rules=self.operational_rules,
            language=self.language,
        )
        text = answer.get("response")
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ValueError("The model did not produce a bounded response.")
        valid_ids = {source["id"] for source in sources}
        if not set(answer.get("source_ids", [])) <= valid_ids:
            raise ValueError("The model cited an unauthorized source.")
        if not proposal_policy(answer, sources, question)["response_allowed"]:
            self.escalation_required = True
            return
        if not await self._current(generation):
            return
        self.escalation_required = self.escalation_required or bool(
            answer.get("escalate") or answer.get("uncertain") or not sources
        )
        self.history = [
            *self.history,
            {"role": "user", "content": question},
            {"role": "assistant", "content": text[:2000]},
        ][-12:]
        pending = bytearray()
        async for audio in self.speech.synthesize(text, self.language):
            if not await self._current(generation):
                self.escalation_required = True
                return
            if len(audio) > 16000:
                raise ValueError("Speech adapter produced an oversized chunk.")
            pending.extend(audio)
            while len(pending) >= self.audio_format.frame_bytes:
                if not await self._current(generation):
                    return
                chunk = bytes(pending[: self.audio_format.frame_bytes])
                del pending[: self.audio_format.frame_bytes]
                await self.send(self.codec.output(audio=chunk))
        if pending:
            if not await self._current(generation):
                return
            if self.audio_format.encoding == "pcm_s16le" and len(pending) % (
                2 * self.audio_format.channels
            ):
                raise ValueError("Speech adapter ended with an incomplete PCM sample.")
            await self.send(
                self.codec.output(
                    audio=bytes(pending)
                    + bytes([self.audio_format.silence_byte])
                    * (self.audio_format.frame_bytes - len(pending))
                )
            )
        if await self._current(generation):
            await self.send(self.codec.output(mark=f"turn_{self.turns}"))

    async def drain(self) -> None:
        if self._task:
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def run(self, audio: AsyncIterator[bytes]) -> None:
        try:
            async with asyncio.timeout(max(0, self.max_seconds - (monotonic() - self.started))):
                async for transcript in self.speech.recognize(audio, self.language):
                    await self.question(transcript)
                await self.drain()
        finally:
            await self.close()

    async def close(self) -> None:
        async with self._control:
            await self._close()

    async def _close(self) -> None:
        if not self.closed:
            self.closed = True
            await self._interrupt()
