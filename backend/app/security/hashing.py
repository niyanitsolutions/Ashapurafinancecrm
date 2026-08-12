"""Non-password one-way hashing (e.g. hashing OTPs at rest, hashing refresh tokens for
revocation lookups) — deliberately separate from password.py, which is bcrypt-tuned for
slow, salted password verification and is the wrong tool for high-frequency lookups.
"""

import hashlib
import hmac

from app.config.security import get_security_policy


def hash_value(value: str) -> str:
    key = get_security_policy().jwt_secret_key.encode()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def verify_hash(value: str, hashed: str) -> bool:
    return hmac.compare_digest(hash_value(value), hashed)
