"""Optional local CLI speech engines. No install, network access or model discovery.

CLI contracts: ggml-org/whisper.cpp examples/cli; OHF-Voice/piper1-gpl docs/CLI.md.
Profiles and paths are operator-managed, never supplied as browser commands.
"""

import asyncio
import hashlib
import io
import os
import signal
import sys
import tempfile
import unicodedata
import wave
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SpeechProfile(BaseModel):
    kind: Literal["stt", "tts"]
    engine: Literal["whisper_cpp", "piper"]
    executable: str
    executable_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    model: str
    model_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    language: str = Field(pattern=r"^[a-z]{2}$")
    version: str = Field(min_length=1, max_length=80)
    license_reference: str = Field(min_length=5, max_length=160)
    config_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    sample: str | None = None
    sample_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    expected_transcript: str | None = Field(default=None, min_length=3, max_length=500)

    @model_validator(mode="after")
    def compatible(self) -> "SpeechProfile":
        if (self.kind == "stt") != (self.engine == "whisper_cpp"):
            raise ValueError("Engine does not match speech component.")
        if self.kind == "stt" and not (
            self.sample and self.sample_sha256 and self.expected_transcript
        ):
            raise ValueError(
                "STT needs an approved checksum-pinned reference WAV and expected transcript."
            )
        if self.kind == "tts" and (not self.config_sha256 or self.language != "en"):
            raise ValueError(
                "Initial Piper verification requires an English voice and pinned model config."
            )
        return self


class SpeechConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VOICE_SPEECH_", env_file=".env", extra="ignore")
    root: str = ""
    profiles: dict[str, SpeechProfile] = Field(default_factory=dict, max_length=20)
    timeout_seconds: int = Field(default=60, ge=5, le=120)
    threads: int = Field(default=2, ge=1, le=8)
    memory_limit_mb: int = Field(default=2048, ge=256, le=16384)


@lru_cache
def get_speech_config() -> SpeechConfig:
    return SpeechConfig()


def asset(root: str, relative: str) -> Path:
    if not root or not Path(root).is_absolute() or Path(relative).is_absolute():
        raise ValueError("Operator-approved absolute speech root and relative assets required.")
    base = Path(root).resolve(strict=True)
    path = (base / relative).resolve(strict=True)
    if not path.is_relative_to(base) or not path.is_file():
        raise ValueError("Speech asset is outside the approved directory.")
    return path


def verify(path: Path, expected: str) -> None:
    if not 0 < path.stat().st_size <= 4 * 1024**3:
        raise ValueError("Speech asset size is unsupported.")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != expected:
        raise ValueError("Speech asset integrity verification failed.")


def wav_metadata(data: bytes, *, reference: bool = False) -> dict[str, int | float]:
    try:
        return decode_wav(data, reference=reference)
    except (wave.Error, EOFError) as exc:
        raise ValueError("Audio is not a supported complete PCM WAV.") from exc


def decode_wav(data: bytes, *, reference: bool = False) -> dict[str, int | float]:
    if not 44 <= len(data) <= 2_000_000:
        raise ValueError("WAV size is unsupported.")
    with wave.open(io.BytesIO(data), "rb") as audio:
        rate, channels, width, frames = (
            audio.getframerate(),
            audio.getnchannels(),
            audio.getsampwidth(),
            audio.getnframes(),
        )
        if (
            audio.getcomptype() != "NONE"
            or width != 2
            or channels != 1
            or rate not in {8000, 16000, 22050, 24000, 44100, 48000}
        ):
            raise ValueError("Expected mono uncompressed signed 16-bit PCM WAV.")
        if reference and rate != 16000:
            raise ValueError("whisper.cpp reference audio must be 16 kHz mono PCM.")
        if not 0 < frames <= rate * 15:
            raise ValueError("Audio duration must be positive and no more than 15 seconds.")
        samples = audio.readframes(frames + 1)
        if len(samples) != frames * width or not any(samples):
            raise ValueError("Audio is truncated or entirely silent.")
    return {
        "sample_rate": rate,
        "channels": channels,
        "duration_seconds": round(frames / rate, 3),
        "size_bytes": len(data),
    }


async def execute(command: list[str], directory: Path, timeout: int, memory_limit_mb: int) -> None:
    if sys.platform != "linux":
        raise ValueError("Local speech execution requires the reviewed Linux worker deployment.")
    # Minimal environment excludes CRM secrets, credentials and proxy settings.
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        str(Path(__file__).with_name("speech_process.py")),
        str(timeout),
        str(memory_limit_mb),
        str(os.getpid()),
        *command,
        cwd=directory,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        env={
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "HOME": str(directory),
            "OMP_NUM_THREADS": "2",
            "HF_HUB_OFFLINE": "1",
        },
        start_new_session=True,
    )
    try:
        async with asyncio.timeout(timeout):
            while process.returncode is None:
                # Bound generated artifacts during execution, not just after exit.
                if sum(p.stat().st_size for p in directory.iterdir() if p.is_file()) > 3_000_000:
                    raise ValueError("Speech process exceeded its output budget.")
                try:
                    await asyncio.wait_for(process.wait(), timeout=0.1)
                except TimeoutError:
                    continue
            if process.returncode != 0:
                raise ValueError("Speech process failed; inspect the isolated deployment locally.")
    finally:
        # Reap descendants on cancellation, deadline, successful exit and failure.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()


class LocalSpeechRuntime:
    def __init__(self, config: SpeechConfig | None = None) -> None:
        self.config = config or get_speech_config()

    async def test(self, profile_id: str) -> tuple[dict[str, object], bytes | None]:
        return await self.run(profile_id, reference=True)

    async def transcribe(self, profile_id: str, audio: bytes) -> str:
        profile = self.config.profiles.get(profile_id)
        if not profile or profile.kind != "stt":
            raise ValueError("An approved STT profile is required.")
        evidence, _ = await self.run(profile_id, reference=False, audio=audio)
        return str(evidence["transcript"])

    async def synthesize(self, profile_id: str, text: str) -> bytes:
        profile = self.config.profiles.get(profile_id)
        if not profile or profile.kind != "tts" or not text.strip() or len(text) > 1000:
            raise ValueError("An approved TTS profile and bounded text are required.")
        _, audio = await self.run(profile_id, reference=False, text=text)
        assert audio is not None
        return audio

    async def run(
        self,
        profile_id: str,
        *,
        reference: bool,
        audio: bytes | None = None,
        text: str | None = None,
    ) -> tuple[dict[str, object], bytes | None]:
        profile = self.config.profiles.get(profile_id)
        if profile is None:
            raise ValueError("Speech profile not configured.")
        async with asyncio.timeout(self.config.timeout_seconds + 10):
            model = asset(self.config.root, profile.model)
            executable = Path(profile.executable)
            if not executable.is_absolute() or not executable.is_file():
                raise ValueError("Speech executable unavailable.")
            await asyncio.to_thread(verify, executable, profile.executable_sha256)
            await asyncio.to_thread(verify, model, profile.model_sha256)
            with tempfile.TemporaryDirectory(prefix="afs-voice-test-") as temp:
                directory = Path(temp)
                output = directory / "result"
                if profile.kind == "stt":
                    assert profile.sample and profile.sample_sha256 and profile.expected_transcript
                    if reference:
                        sample = asset(self.config.root, profile.sample)
                        await asyncio.to_thread(verify, sample, profile.sample_sha256)
                        if sample.stat().st_size > 1_000_000:
                            raise ValueError("Reference WAV is oversized.")
                        wav_metadata(sample.read_bytes(), reference=True)
                    else:
                        if audio is None or len(audio) > 1_000_000:
                            raise ValueError("Bounded input WAV required.")
                        wav_metadata(audio, reference=True)
                        sample = directory / "input.wav"
                        sample.write_bytes(audio)
                    command = [
                        str(executable),
                        "-m",
                        str(model),
                        "-f",
                        str(sample),
                        "-l",
                        profile.language,
                        "-t",
                        str(self.config.threads),
                        "-otxt",
                        "-of",
                        str(output),
                        "-ng",
                    ]
                else:
                    assert profile.config_sha256
                    config = asset(self.config.root, profile.model + ".json")
                    await asyncio.to_thread(verify, config, profile.config_sha256)
                    sample_text = directory / "sample.txt"
                    sample_text.write_text(
                        text
                        if text is not None
                        else "This is a local speech verification. No call has been placed.",
                        encoding="utf-8",
                    )
                    command = [
                        str(executable),
                        "-I",
                        "-m",
                        "piper",
                        "-m",
                        str(model),
                        "-f",
                        str(output.with_suffix(".wav")),
                        "--input-file",
                        str(sample_text),
                    ]
                await execute(
                    command, directory, self.config.timeout_seconds, self.config.memory_limit_mb
                )
                evidence: dict[str, object] = {
                    "engine": profile.engine,
                    "version": profile.version,
                    "version_provenance": "operator_declared_binary_checksum_pinned",
                    "runtime_integrity_scope": "python_interpreter_only_package_pin_required"
                    if profile.engine == "piper"
                    else "native_executable_checksum",
                    "language": profile.language,
                    "model_sha256": profile.model_sha256,
                    "integrity_verified": True,
                }
                if profile.kind == "stt":
                    transcript_file = output.with_suffix(".txt")
                    if transcript_file.stat().st_size > 8000:
                        raise ValueError("Speech transcript exceeded its budget.")
                    transcript = transcript_file.read_text(encoding="utf-8").strip()
                    if not transcript or len(transcript) > 2000:
                        raise ValueError("Recognizer returned empty or oversized text.")
                    if reference and normalize_text(transcript) != normalize_text(
                        profile.expected_transcript or ""
                    ):
                        raise ValueError(
                            "Reference transcription does not match approved test text."
                        )
                    return evidence | (
                        {"reference_transcription_matched": True}
                        if reference
                        else {"transcript": transcript}
                    ), None
                wave_file = output.with_suffix(".wav")
                if wave_file.stat().st_size > 2_000_000:
                    raise ValueError("Speech WAV exceeded its budget.")
                audio = wave_file.read_bytes()
                return evidence | wav_metadata(audio), audio


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(
        "".join(
            c if unicodedata.category(c)[0] in {"L", "N", "M"} else " " for c in normalized
        ).split()
    )
