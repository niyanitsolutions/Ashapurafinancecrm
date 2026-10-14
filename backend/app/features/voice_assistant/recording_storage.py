"""Private encrypted artifact storage. Not a live call recorder or public file server."""

import hashlib
import io
import os
import re
import wave
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.exceptions import ValidationError
from app.security.encryption import decrypt_bytes, encrypt_bytes

MAX_RECORDING_BYTES = 20 * 1024 * 1024


class RecordingConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="VOICE_")
    recordings_dir: str = ""

    @field_validator("recordings_dir")
    @classmethod
    def private_absolute_directory(cls, value: str) -> str:
        if not value:
            return value
        path = Path(value)
        if (
            not path.is_absolute()
            or path == Path(path.anchor)
            or any(
                part.casefold() in {"frontend", "static", "public", "dist"} for part in path.parts
            )
        ):
            raise ValueError(
                "Use an absolute private recording directory outside any web/static root."
            )
        return str(path)


@lru_cache
def get_recording_config() -> RecordingConfig:
    return RecordingConfig()


def validate_wav(data: bytes) -> dict[str, Any]:
    if not data or len(data) > MAX_RECORDING_BYTES:
        raise ValidationError("Choose a non-empty WAV file no larger than 20 MB.")
    try:
        if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
            raise ValueError("not WAV")
        with wave.open(io.BytesIO(data), "rb") as audio:
            channels, width, rate, count = (
                audio.getnchannels(),
                audio.getsampwidth(),
                audio.getframerate(),
                audio.getnframes(),
            )
            if channels not in {1, 2} or width != 2 or rate not in {8000, 16000, 24000, 48000}:
                raise ValueError("unsupported format")
            duration = count / rate
            if not 0.1 <= duration <= 1800 or count * channels * width > MAX_RECORDING_BYTES:
                raise ValueError("duration bounds")
            frames = audio.readframes(count)
            if len(frames) != count * channels * width:
                raise ValueError("truncated recording")
        return {
            "duration_seconds": round(duration, 3),
            "sample_rate": rate,
            "channels": channels,
            "encoding": "pcm_s16le",
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    except (ValueError, EOFError, wave.Error, OSError):
        raise ValidationError(
            "Invalid or truncated recording. Use PCM 16-bit WAV, mono/stereo, "
            "8/16/24/48 kHz, duration 0.1 to 1,800 seconds."
        ) from None


class PrivateRecordingStorage:
    def __init__(self, config: RecordingConfig | None = None) -> None:
        self.config = config or get_recording_config()

    def path(self, record_id: str) -> Path:
        if not self.config.recordings_dir:
            raise ValidationError(
                "Private recording storage is not configured. Set VOICE_RECORDINGS_DIR."
            )
        if not re.fullmatch(r"[a-f0-9]{24}", record_id):
            raise ValidationError("Invalid private artifact identifier.")
        root = Path(self.config.recordings_dir)
        # Operators control the configured root; storage must not redirect through symlinks.
        for parent in [root, *root.parents]:
            if parent.is_symlink():
                raise ValidationError("Private recording storage must not contain symbolic links.")
        target = root / f"{record_id}.enc"
        if target.is_symlink():
            raise ValidationError("Invalid private artifact path.")
        return target

    def put(self, record_id: str, data: bytes) -> None:
        path = self.path(record_id)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name == "posix" and path.parent.stat().st_mode & 0o077:
            raise ValidationError(
                "Private recording directory must have owner-only permissions (0700)."
            )
        encrypted = encrypt_bytes(data)
        temporary = path.with_suffix(".part")
        # Exclusive staging file and durable rename: never publish incomplete ciphertext.
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(encrypted)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
            if os.name == "posix":
                directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)

    def read(self, record_id: str, expected_hash: str) -> bytes:
        path = self.path(record_id)
        if path.stat().st_size > MAX_RECORDING_BYTES * 2:
            raise ValueError("oversized encrypted artifact")
        data = decrypt_bytes(path.read_bytes())
        if hashlib.sha256(data).hexdigest() != expected_hash:
            raise ValueError("artifact integrity failure")
        return data

    def delete(self, record_id: str) -> None:
        path = self.path(record_id)
        temporary = path.with_suffix(".part")
        if temporary.is_symlink():
            raise ValidationError("Invalid private staging path.")
        path.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)
        if path.exists() or temporary.exists():
            raise OSError("artifact deletion not verified")
