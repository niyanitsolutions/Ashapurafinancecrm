# Error Codes

The `error.code` field in the response envelope (see `docs/api/API_STANDARDS.md`). Defined centrally in `backend/app/core/exceptions.py`; add a row here in the same PR that introduces a new `AppError` subclass.

| Code | HTTP Status | Meaning |
|---|---|---|
| `not_found` | 404 | Requested resource doesn't exist or is soft-deleted |
| `validation_error` | 422 | Request failed schema/business validation |
| `unauthorized` | 401 | Missing or invalid/expired auth token |
| `forbidden` | 403 | Authenticated but lacks permission for this action |
| `conflict` | 409 | Request conflicts with current state (e.g. duplicate) |
| `rate_limited` | 429 | Too many requests in the current window |
| `internal_error` | 500 | Unhandled server error |

## Authentication (`backend/app/features/auth/`)

| Code | HTTP Status | Meaning |
|---|---|---|
| `invalid_credentials` | 401 | Wrong mobile/password (login), or wrong current password (change-password) |
| `account_locked` | 423 | 5 failed login attempts — locked for 15 minutes (both configurable) |
| `already_registered` | 409 | send-otp for a mobile that's already an active account, or registered under a different role |
| `invalid_role_for_signup` | 422 | send-otp with a role outside `customer`/`referral_partner` |
| `otp_not_found` | 422 | OTP never sent, or expired (5 min default) |
| `otp_mismatch` | 422 | Wrong OTP entered (attempt is counted) |
| `otp_max_attempts_exceeded` | 429 | 5 wrong OTP attempts (default) — request a new one |
| `invalid_or_expired_ticket` | 401 | `otp_verified_token` passed to reset-password is expired, malformed, or already used (single-use) |
| `invalid_refresh_token` | 401 | Refresh token expired/invalid, or its session is no longer active |

Feature-specific error codes are added by the owning module and listed here alongside the base codes, not as a separate document.
