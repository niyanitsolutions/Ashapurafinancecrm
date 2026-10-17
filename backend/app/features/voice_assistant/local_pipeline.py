"""Actual local utterance pipeline, deliberately not a live telephone session.

Each speech subprocess loads its model per utterance. Real-time latency, voice
activity detection, codec negotiation and barge-in need separate media acceptance.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from app.features.voice_assistant.adapters import SAFETY_POLICY
from app.features.voice_assistant.conversation import LocalConversationAdapter
from app.features.voice_assistant.intent_policy import proposal_policy
from app.features.voice_assistant.speech_runtime import LocalSpeechRuntime, wav_metadata


class LocalUtterancePipeline:
    def __init__(self, speech: LocalSpeechRuntime, model: LocalConversationAdapter) -> None:
        self.speech, self.model = speech, model

    async def respond(
        self,
        *,
        audio: bytes,
        stt_profile: str,
        tts_profile: str,
        sources: list[dict[str, Any]],
        instructions: str,
        operational_rules: str,
        language: str,
        history: list[dict[str, str]] | None = None,
        authorize: Callable[[], Awaitable[bool]] | None = None,
    ) -> tuple[bytes, dict[str, Any]]:
        started = time.perf_counter()
        async with asyncio.timeout(300):
            if authorize and not await authorize():
                raise ValueError("Local pipeline disabled before recognition.")
            transcript = await self.speech.transcribe(stt_profile, audio)
            recognized = time.perf_counter()
            if authorize and not await authorize():
                raise ValueError("Local pipeline disabled before inference.")
            answer = await self.model.respond(
                question=transcript,
                history=history or [],
                sources=sources,
                instructions=f"{SAFETY_POLICY}\n{instructions}",
                operational_rules=operational_rules,
                language=language,
            )
            text = answer.get("response")
            source_ids = answer.get("source_ids", [])
            if (
                not isinstance(text, str)
                or not text.strip()
                or len(text) > 1000
                or not isinstance(source_ids, list)
                or any(not isinstance(item, str) for item in source_ids)
            ):
                raise ValueError("Local model returned unsupported speech output.")
            if not set(source_ids) <= {str(source["id"]) for source in sources}:
                raise ValueError("Local model referenced unapproved knowledge.")
            generated = time.perf_counter()
            decision = proposal_policy(answer, sources, transcript)
            if not decision["response_allowed"]:
                raise ValueError("Server conversation policy withheld speech; human review required.")
            if authorize and not await authorize():
                raise ValueError("Local pipeline disabled before synthesis.")
            output = await self.speech.synthesize(tts_profile, text)
            if authorize and not await authorize():
                raise ValueError("Local pipeline disabled after synthesis; output withheld.")
            metadata = wav_metadata(output)
            finished = time.perf_counter()
            # No raw transcript/response retained in job evidence.
            return output, {
                "scope": "local_stt_inference_tts_utterance_only",
                "audio": metadata,
                "stt_ms": round((recognized - started) * 1000),
                "inference_ms": round((generated - recognized) * 1000),
                "tts_ms": round((finished - generated) * 1000),
                "total_ms": round((finished - started) * 1000),
                "escalation_required": bool(
                    answer.get("escalate") or answer.get("uncertain") or not sources
                ),
                "live_telephony_verified": False,
                "language_quality_verified": False,
                "policy_version": decision["policy_version"],
                "policy_digest": decision["policy_digest"],
                "intent": decision["intent"],
                "tool_execution_permitted": False,
            }
