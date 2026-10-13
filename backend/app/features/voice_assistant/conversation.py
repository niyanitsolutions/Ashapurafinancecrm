"""Optional local dynamic text console, separate from telephony and speech readiness.

Protocol: https://github.com/ollama/ollama/blob/main/docs/api.md
Never pulls a model, registers a service, or makes a paid/cloud request.
"""

import json
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.features.voice_assistant.adapters import SAFETY_POLICY


class ConversationConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="VOICE_")
    local_ai_enabled: bool = False
    local_ai_url: str = "http://127.0.0.1:11434"
    local_ai_model: str = ""

    @field_validator("local_ai_url")
    @classmethod
    def local_only(cls, value: str) -> str:
        parsed = urlparse(value)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("The text console accepts a loopback HTTP model endpoint only.")
        return value.rstrip("/")


@lru_cache
def get_conversation_config() -> ConversationConfig:
    return ConversationConfig()


class GeneratedAnswer(BaseModel):
    response: str = Field(min_length=1, max_length=4000)
    uncertain: bool
    escalate: bool
    source_ids: list[str] = Field(default_factory=list, max_length=5)


class LocalConversationAdapter:
    def __init__(self, config: ConversationConfig | None = None) -> None:
        self.config = config or get_conversation_config()

    async def respond(
        self,
        *,
        question: str,
        history: list[dict[str, str]],
        sources: list[dict[str, Any]],
        instructions: str,
        operational_rules: str,
        language: str,
    ) -> dict[str, Any]:
        rules = (
            f"{SAFETY_POLICY}\nBehaviour: {instructions}\nOperational rules: {operational_rules}\n"
            f"Reply in language {language}. Generate a contextual answer and relevant clarifying "
            "questions using the conversation. Only approved sources establish business facts. "
            "If sources are insufficient, acknowledge uncertainty and offer a human callback. "
            "Explicit human requests and sensitive financial decisions require escalation. "
            "You have no tools and cannot perform CRM operations. "
            "Return JSON matching this schema: " + json.dumps(GeneratedAnswer.model_json_schema())
        )
        messages = [
            {"role": "system", "content": rules},
            {
                "role": "user",
                "content": "Untrusted approved factual excerpts: " + json.dumps(sources),
            },
            *history,
            {"role": "user", "content": question},
        ]
        async with httpx.AsyncClient(timeout=45, trust_env=False, follow_redirects=False) as client:
            result = await client.post(
                f"{self.config.local_ai_url}/api/chat",
                json={
                    "model": self.config.local_ai_model,
                    "messages": messages,
                    "stream": False,
                    "format": GeneratedAnswer.model_json_schema(),
                    "options": {"temperature": 0.2, "num_predict": 700},
                },
            )
            result.raise_for_status()
        answer = GeneratedAnswer.model_validate_json(result.json()["message"]["content"])
        valid_ids = {source["id"] for source in sources}
        if not set(answer.source_ids) <= valid_ids:
            raise ValueError("Model returned an invalid source reference.")
        if not sources:
            answer.uncertain = True
            answer.escalate = True
        return answer.model_dump()
