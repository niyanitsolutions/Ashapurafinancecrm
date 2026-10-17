"""Offline orchestration safety; no provider, installed model or audio delivery proof."""

import asyncio

import pytest

from app.features.voice_assistant.dynamic_audio import DynamicAudioConversation
from app.features.voice_assistant.media_contracts import AudioFormat


class Codec:
    stopped = False
    audio_format = AudioFormat(encoding="pcm_s16le", sample_rate=16000)

    def output(self, *, audio=None, mark=None, clear=False):
        return {"audio": audio, "mark": mark, "clear": clear}


def public_answer():
    return {"response": "Reviewed public information.", "source_ids": ["approved"], "uncertain": False,
            "intent": {"intent": "product_information", "confidence": .95, "proposed_action": "answer_public_knowledge"}}


async def retrieve(*args):
    return [{"id": "approved", "excerpt": "Reviewed public information."}]


@pytest.mark.parametrize("mode", ["unbound", "denied", "protected", "unclassified", "unsafe_clarification", "unsupported_public"])
async def test_unsafe_or_unbound_response_never_reaches_speech(mode):
    sent = []
    class Model:
        async def respond(self, **kwargs):
            result = public_answer()
            if mode == "protected":
                result["intent"] |= {"intent": "loan_status", "proposed_action": "request_verification"}
            elif mode == "unclassified":
                result.pop("intent")
            elif mode == "unsafe_clarification":
                result |= {"response": "Your loan is approved.", "uncertain": True}
                result["intent"] |= {"intent": "unclear", "proposed_action": "clarify"}
            elif mode == "unsupported_public":
                result["response"] = "Your loan is approved."
            return result
    class Speech:
        async def synthesize(self, *args):
            pytest.fail("Withheld content reached synthesis")
            yield b""
    async def authorize():
        return mode != "denied"
    async def send(event):
        sent.append(event)
    engine = DynamicAudioConversation(model=Model(), speech=Speech(), codec=Codec(), retrieve=retrieve,
        send=send, instructions="test", operational_rules="test", authorize=None if mode == "unbound" else authorize)
    await engine.question("General question")
    await engine.drain()
    assert engine.escalation_required
    assert not any(event["audio"] or event["mark"] for event in sent)


@pytest.mark.parametrize("stage", ["model", "synthesis", "between_frames"])
async def test_revocation_during_every_delivery_stage_prevents_later_audio(stage):
    permitted = True
    sent = []
    class Model:
        async def respond(self, **kwargs):
            nonlocal permitted
            if stage == "model":
                permitted = False
            return public_answer()
    class Speech:
        async def synthesize(self, *args):
            nonlocal permitted
            if stage == "synthesis":
                permitted = False
            yield bytes(1280)
    async def authorize():
        return permitted
    async def send(event):
        nonlocal permitted
        sent.append(event)
        if stage == "between_frames" and event["audio"]:
            permitted = False
    engine = DynamicAudioConversation(model=Model(), speech=Speech(), codec=Codec(), retrieve=retrieve,
        send=send, instructions="test", operational_rules="test", authorize=authorize)
    await engine.question("General information")
    await engine.drain()
    assert sum(event["audio"] is not None for event in sent) == (1 if stage == "between_frames" else 0)
    assert not any(event["mark"] for event in sent)


async def test_model_suppressing_cancellation_cannot_publish_obsolete_turn():
    started = asyncio.Event()
    sent = []
    attempts = 0
    class Model:
        async def respond(self, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    pass  # Misbehaving adapter; generation fence must still win.
            return public_answer()
    class Speech:
        async def synthesize(self, *args):
            yield bytes(640)
    async def authorize():
        return True
    async def send(event):
        sent.append(event)
    engine = DynamicAudioConversation(model=Model(), speech=Speech(), codec=Codec(), retrieve=retrieve,
        send=send, instructions="test", operational_rules="test", authorize=authorize)
    await engine.question("First question")
    await started.wait()
    await engine.question("Second question")
    await engine.drain()
    assert sum(event["audio"] is not None for event in sent) == 1
    assert [entry["content"] for entry in engine.history if entry["role"] == "user"] == ["Second question"]


async def test_noncooperative_model_cannot_block_takeover_or_start_another_turn():
    started, release = asyncio.Event(), asyncio.Event()
    sent = []
    class Model:
        async def respond(self, **kwargs):
            started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
            return public_answer()
    class Speech:
        async def synthesize(self, *args):
            pytest.fail("Revoked model must not reach synthesis")
            yield b""
    async def authorize():
        return True
    async def send(event):
        sent.append(event)
    engine = DynamicAudioConversation(model=Model(), speech=Speech(), codec=Codec(), retrieve=retrieve,
        send=send, instructions="test", operational_rules="test", authorize=authorize)
    await engine.question("First question")
    await started.wait()
    try:
        await asyncio.wait_for(engine.question("Take over"), timeout=2)
        assert engine.closed and engine.escalation_required and engine.turns == 1
    finally:
        release.set()
        await engine.drain()
    assert not any(event["audio"] or event["mark"] for event in sent)


async def test_simultaneous_questions_cannot_share_a_generation():
    clear_started, release_clear = asyncio.Event(), asyncio.Event()
    sent = []
    first = True
    class Model:
        async def respond(self, **kwargs):
            await asyncio.sleep(0)
            return public_answer()
    class Speech:
        async def synthesize(self, *args):
            yield bytes(640)
    async def authorize():
        return True
    async def send(event):
        nonlocal first
        if event["clear"] and first:
            first = False
            clear_started.set()
            await release_clear.wait()
        sent.append(event)
    engine = DynamicAudioConversation(model=Model(), speech=Speech(), codec=Codec(), retrieve=retrieve,
        send=send, instructions="test", operational_rules="test", authorize=authorize)
    original = asyncio.create_task(engine.question("First question"))
    await clear_started.wait()
    newer = asyncio.create_task(engine.question("Second question"))
    release_clear.set()
    await asyncio.gather(original, newer)
    await engine.drain()
    assert engine.turns == 2
    assert sum(event["audio"] is not None for event in sent) == 1
    assert [entry["content"] for entry in engine.history if entry["role"] == "user"] == ["Second question"]
