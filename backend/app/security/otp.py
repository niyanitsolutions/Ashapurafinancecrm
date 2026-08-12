"""OTP generation/verification. Storage of the OTP + attempt count + lock state lives in
Redis (see core requirement: OTP/sessions/rate-limiting are Redis concerns), keyed by
mobile number. This module only owns the generation/hashing algorithm and the policy
thresholds; the auth feature (not yet implemented) owns the Redis read/write calls.
"""

import secrets

from app.security.hashing import hash_value, verify_hash


def generate_otp(length: int = 6) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))


def hash_otp(otp: str) -> str:
    return hash_value(otp)


def verify_otp(otp: str, hashed_otp: str) -> bool:
    return verify_hash(otp, hashed_otp)
