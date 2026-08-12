# Security

Cross-cutting security infrastructure — primitives in `backend/app/security/` and `backend/app/middleware/`, and the parts of the original brief not specific to Authentication's own behavior. For how Authentication actually uses these (OTP policy, JWT types, session/refresh mechanics, lockout, audit events), see `docs/AUTHENTICATION.md` — that file is the source of truth for Auth-specific detail; this one won't repeat it.

## Primitives (`backend/app/security/`)

| File | Provides |
|---|---|
| `password.py` | bcrypt hashing, called directly (not passlib — its bcrypt backend detection is broken against bcrypt≥4.1 and the library is unmaintained). Passwords over 72 bytes are rejected outright, never silently truncated. |
| `otp.py` | OTP generation + HMAC hashing (deliberately not bcrypt — high-frequency, short-lived, unlike passwords). |
| `hashing.py` | Generic HMAC-SHA256 for non-password one-way hashing (e.g. refresh token hashes at rest). |
| `jwt.py` | Token creation/decoding for all three JWT types Authentication uses — see `docs/AUTHENTICATION.md`. |
| `tokens.py` | Secure-link tokens scoped to a resource (`resource_type`+`resource_id`) — reserved for when Lead Management needs to link a Customer to a specific application; not yet consumed by anything. |
| `encryption.py` | Fernet symmetric encryption for sensitive fields (bank account numbers, PAN, etc.) once a feature needs it. Currently derives its key from `JWT_SECRET_KEY` as a placeholder — see `docs/KNOWN_LIMITATIONS.md`, needs a dedicated key before real use. |

Never store or log plaintext passwords or OTPs.

## Rate Limiting

`backend/app/middleware/rate_limit.py` — Redis fixed-window counter, applied per-route via the `rate_limited()` dependency, not globally. Current limits are all on Authentication routes (`docs/AUTHENTICATION.md`); other modules set their own as needed.

## Audit Logs

`audit_logs` collection (see `docs/database/COLLECTIONS.md`) — referenced, never embedded, append-only by design (`backend/app/shared/audit_log.py` exposes only a write function, intentionally no update/delete). Authentication is the first writer — event list in `docs/AUTHENTICATION.md`. Every future feature that needs an audit trail writes to this same collection/function rather than inventing its own.

## Geo-fencing

Marked "ready" per the original brief but the concrete use case isn't defined yet — see `docs/roadmap/TODO.md`. `app/services/maps/client.py` reserves the interface (`distance_meters`) that a geo-fencing check would use once the requirement is confirmed.

## Two-Factor Authentication

Not implemented; `security/` is structured (separate OTP/JWT/token/hashing modules) so adding a 2FA step later composes with existing primitives rather than requiring a rewrite.
