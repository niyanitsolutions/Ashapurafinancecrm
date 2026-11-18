"""Customer PIN hashes; legacy bcrypt PINs remain verifiable during enrollment."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.security.password import verify_password

_hasher = PasswordHasher()


def hash_pin(pin: str) -> str:
    return _hasher.hash(pin)


def verify_pin(pin: str, encoded: str) -> bool:
    if encoded.startswith("$2"):
        return verify_password(pin, encoded)
    try:
        return _hasher.verify(encoded, pin)
    except (InvalidHashError, VerificationError):
        return False
