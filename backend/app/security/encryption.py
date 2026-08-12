"""Symmetric encryption for sensitive fields at rest (e.g. bank account numbers, PAN).
Distinct from hashing.py: this is reversible, for data the app must read back later.
"""

import base64
from functools import lru_cache

from cryptography.fernet import Fernet

from app.config.settings import get_settings


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    # Prefer the dedicated ENCRYPTION_KEY (required in production — see settings.py's
    # _reject_insecure_production_config). Falls back to deriving from jwt_secret_key
    # only when ENCRYPTION_KEY is unset, so existing local/staging encrypted data
    # doesn't need re-encrypting and dev environments keep working unchanged.
    source = settings.encryption_key or settings.jwt_secret_key
    key_material = source.encode().ljust(32, b"0")[:32]
    return Fernet(base64.urlsafe_b64encode(key_material))


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
