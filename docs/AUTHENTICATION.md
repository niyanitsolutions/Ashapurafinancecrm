# Authentication

Module 1 — **approved and frozen**. No architectural changes without explicit approval; future modules consume these APIs, they don't modify Authentication's behavior. See the Freeze Rule at the bottom.

This is the single source of truth for how Authentication works. `docs/SECURITY.md` covers cross-cutting security infrastructure (password hashing primitive, rate limiting, encryption-at-rest, geo-fencing, 2FA readiness) that isn't Auth-specific; anything below is the detailed, current behavior — if the two ever seem to disagree, this file wins.

## Roles and How Each Gets an Account

| Role | How the account is created | Self-signup? |
|---|---|---|
| Owner | `scripts/seed.py` bootstrap (`BOOTSTRAP_OWNER_MOBILE`/`BOOTSTRAP_OWNER_PASSWORD`) — there is exactly one way to create the first Owner, and it isn't an API call | Never |
| Employee | Manually provisioned until User Management exists | Never |
| Customer | Owner or Employee invites via `POST /auth/send-otp` | Never — invitation-only |
| Referral Partner | Owner **only** invites via `POST /auth/send-otp` | Never — invitation-only |

No endpoint anywhere lets an unauthenticated caller create an account. See decision 007 and decision 011 in `docs/decisions/DECISIONS.md`.

## Flow Diagrams

### Owner / Employee — Login

```
Enter Mobile Number
        ↓
Enter Password
        ↓
POST /auth/login
        ↓
   Locked? ──yes──→ 423 account_locked
        │no
   Valid? ──no──→ 401 invalid_credentials (failed_login audit logged with internal reason)
        │yes
Session created (family_id, token_id) + JWT access/refresh issued
        ↓
      Dashboard (out of scope this module — client just holds the tokens)
```

### Customer / Referral Partner — Invitation Signup

```
Owner/Employee (authenticated)
        ↓
POST /auth/send-otp { mobile, role }         ← authorization checked: who may invite whom (below)
        ↓
pending_password User created (if new) + OTP delivered to invitee's phone
        ↓
Invitee: POST /auth/verify-otp { mobile, otp, purpose: signup }
        ↓
        OTP valid? ──no──→ otp_mismatch / otp_not_found / otp_max_attempts_exceeded
        │yes
otp_verified_token issued (single-use, 10min)
        ↓
POST /auth/reset-password { otp_verified_token, new_password }   ← this call IS "Create Password"
        ↓
Account becomes active
        ↓
POST /auth/login (separately, same as any other login)
```

Who may invite whom (`backend/app/features/auth/constants.py:INVITER_ROLES_BY_INVITEE_ROLE`):

```
invite role=customer            → caller must be Owner or Employee
invite role=referral_partner    → caller must be Owner
invite role=owner or employee   → always rejected (invalid_role_for_signup)
```

**Scope note:** the brief's "Employee generates a secure link tied to a specific application" step isn't fully built — the link's target (a Lead) doesn't exist until Lead Management is built. This flow implements the security-relevant part (no public signup, staff-authorized invitation, OTP-verified) using the existing `send-otp`/`verify-otp`/`reset-password` endpoints; the literal clickable-link-to-application UX is deferred. See decision 011 and `docs/KNOWN_LIMITATIONS.md`.

### Forgot Password (any role, existing active account only)

```
POST /auth/forgot-password { mobile }
        ↓
   Account exists & active? ──no──→ 200 anyway, no OTP actually sent (no account-existence leak)
        │yes
OTP delivered
        ↓
POST /auth/verify-otp { mobile, otp, purpose: forgot_password }
        ↓
otp_verified_token issued
        ↓
POST /auth/reset-password { otp_verified_token, new_password }
        ↓
Password changed — same endpoint as Create Password, different starting state
```

### Primary Owner Password Recovery

The Primary Owner has no special recovery mechanism and needs none — the Forgot
Password flow above (`POST /auth/forgot-password` → OTP → `POST /auth/reset-password`)
already works for any active account regardless of role, Primary Owner included. There
is intentionally **no admin override, backdoor, or master password** anywhere in this
system: Owner Account Management (see the `owner` feature) explicitly forbids even a
Secondary Owner from touching the Primary Owner's account, so self-service reset via a
verified OTP is the only path by design.

**Production caveat:** the OTP is only actually delivered once a real SMS provider is
configured (see Known Gaps below — `NotConfiguredSmsClient` is a stub today). Until then,
if the Primary Owner is locked out, the only recovery path is a manual, audited
intervention by whoever holds production database access — e.g. directly setting a new
bcrypt password hash on that one `users` document (`app/security/password.hash_password`
run offline, never a plaintext write) and reviewing/rotating that access afterward. This
is an exceptional break-glass action, not a documented API or application feature, and
should be logged outside the application (e.g. in your ops/incident tracker) since the
app's own audit log only records actions taken through its own APIs. Configuring a real
SMS provider before go-live removes the need for this path entirely.

### Refresh (rotation + reuse detection)

```
POST /auth/refresh { refresh_token }
        ↓
   jti found among sessions? ──no──→ 401 invalid_refresh_token
        │yes
   row status == "rotated"? ──yes──→ REUSE DETECTED
        │no                              ↓
        │                       revoke_family(family_id) — every token in the chain dies
        │                                ↓
        │                       audit: suspicious_refresh_reuse
        │                                ↓
        │                       401 invalid_refresh_token
        │no (status == "active")
mark current row "rotated", insert new row (same family_id, new token_id)
        ↓
new access_token + refresh_token returned
```

## APIs

Full request/response shapes: `docs/api/API.md`. Error codes: `docs/api/ERROR_CODES.md`. Summary of the 9 endpoints and their auth requirement:

| Endpoint | Auth required | Notes |
|---|---|---|
| `POST /auth/send-otp` | Yes — Owner/Employee, role-gated | Invitation-only, decision 011 |
| `POST /auth/forgot-password` | No | Public, but silent on unknown/inactive accounts |
| `POST /auth/verify-otp` | No | Shared by both signup and forgot-password |
| `POST /auth/reset-password` | No (proved by the ticket instead) | Also serves as "Create Password" |
| `POST /auth/change-password` | Yes | No frontend UI yet (Settings out of scope) |
| `POST /auth/login` | No | Mobile + password only, no client-asserted role |
| `POST /auth/logout` | Yes | Ends the current session (not the whole family) |
| `POST /auth/refresh` | No (proved by the refresh token) | Rotates; see reuse detection above |
| `GET /auth/profile` | Yes | Identity fields only, no name/address |

## JWT

Three token types (`backend/app/security/jwt.py:TokenType`):

| Type | Lifetime (default, configurable) | Purpose |
|---|---|---|
| `access` | 15 minutes | Sent as `Authorization: Bearer` on every authenticated request. Stateless — verified by signature/expiry alone. |
| `refresh` | 7 days | Exchanged at `/auth/refresh` for a new pair. Stateful — must match an `active` session row by `jti` (see Sessions below). |
| `otp_verified` | 10 minutes | Short-lived ticket bridging OTP verification to `reset-password`. Single-use (Redis claim-once key on its `jti`). |

Transport: pure Bearer, **no cookies**, for either token — see decision 008. This was explicitly re-confirmed after the module review raised HttpOnly cookies as an alternative; rejected to preserve one identical API contract for React web and future Flutter apps.

Client-side storage (web): access token in memory only; refresh token in `localStorage` — see decision 012 for the full trade-off writeup, including why this is safe enough given decision 013's reuse detection.

## OTP

- 6-digit numeric, generated by `backend/app/security/otp.py`, hashed at rest (HMAC-SHA256, not bcrypt — see `docs/SECURITY.md`).
- Storage: Redis only, **never MongoDB**, key `otp:{purpose}:{mobile}` (`backend/app/features/auth/otp_service.py`), `purpose` ∈ `signup` | `forgot_password`.
- Policy (configurable via env): 5-minute expiry (`OTP_EXPIRE_MINUTES`), 5 max verification attempts (`OTP_MAX_ATTEMPTS`) before the code is invalidated and a new one must be requested.
- Delivery: `backend/app/services/sms/client.py` — currently an unconfigured stub; `dev_otp` is echoed directly in the API response outside `production` so the flow is testable without a real SMS provider. See `docs/KNOWN_LIMITATIONS.md`.

## Sessions (Login History / Session Management data)

One document per issued refresh token, chained by `family_id` into a rotation history (`backend/app/features/auth/models.py:Session`):

```
user_id, family_id, token_id (jti, unique), refresh_token_hash,
login_method ("password" today),
device, browser, operating_system      — best-effort parsed from User-Agent
ip_address, city, country              — city/country via GeoIP stub, currently always null
login_at                               — when the family began, carried through every rotation
logout_at, last_activity_at
status                                  — active | rotated | logged_out | revoked
```

No UI reads this yet — Session Management/Login History screens are Settings/Dashboard territory, out of scope this module. The data and revocation mechanics are in place for when that screen is built.

## Refresh Token Family / Reuse Detection

See the Refresh flow diagram above and decision 013. In short: rotating a refresh token doesn't overwrite its session row, it retires it (`status: rotated`) and creates a new row in the same family. Presenting an already-retired token is unambiguous evidence of a stolen/replayed token, and the response is to kill the entire family — every token in that login's chain — not just the one request. This is checked on every `/auth/refresh` call, with no additional configuration.

## Account Lockout

Separate mechanism from OTP attempts — `backend/app/features/auth/lockout_service.py`, Redis-backed:
- `login_attempts:{mobile}` counter, `login_lock:{mobile}` flag, both TTL'd to `ACCOUNT_LOCK_MINUTES` (default 15).
- 5 failed attempts (`MAX_LOGIN_ATTEMPTS`, configurable) locks the account. A lock is checked *before* password verification runs, so a locked account can't be probed via timing.
- Clears automatically on TTL expiry, or immediately on a successful login.

## Audit Logs

`backend/app/shared/audit_log.py` writes to `audit_logs` (append-only by design — no update/delete path exists). Events emitted by this module: `login`, `logout`, `failed_login` (with an internal `reason` in `metadata` — see decision 014), `password_change`, `password_reset`, `otp_sent`, `otp_verified`, `refresh_token`, `account_lock`, `suspicious_refresh_reuse`. `account_unlock` is defined but not currently emitted (locks clear via TTL, not an explicit action).

## Security Summary

- Passwords: bcrypt, direct (not passlib — see `docs/SECURITY.md`), rejected outright above 72 bytes.
- OTP: Redis-only, HMAC-hashed, 5min/5attempts.
- Login lockout: Redis-only, 5 attempts/15min, checked before password verification.
- JWT: HS256, three purpose-scoped types, pure Bearer, no cookies.
- Refresh: stateful, rotated, reuse-detected, family-revocable.
- Signup: invitation-only, role-authorized, no public entry point for any role.
- Rate limiting: `send-otp`/`forgot-password` 5/min, `verify-otp` 10/min, `login` 10/min (`backend/app/middleware/rate_limit.py`).

## Known Gaps

See `docs/KNOWN_LIMITATIONS.md` for the full, current list. The load-bearing ones: no real SMS/GeoIP provider configured (both stubbed), no Session Management/Change Password UI, no invitation-triggering UI (belongs to a future Owner/Employee portal), and the secure-link-to-application tie-in from decision 003 remains deferred to Lead Management.

## Freeze Rule

**Authentication is approved and frozen.** No architectural changes are allowed unless explicitly approved. Future modules must consume the existing authentication APIs (`docs/api/API.md`) instead of modifying authentication behavior — e.g., User Management reads `users` via new endpoints of its own, it doesn't add fields to the auth router; Lead Management wires up `security/tokens.py`'s secure-link primitives from the outside, it doesn't change how `send-otp`/`verify-otp` work.
