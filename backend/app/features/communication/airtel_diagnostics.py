"""Conservative public projection of untrusted replies, not an Airtel error schema.

Unknown words/keys and all numbers are suppressed because arbitrary provider text
can echo names, addresses, credentials or an entire SMS. Raw replies never persist.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

MAX_BODY = 8192


@dataclass
class ProviderBody:
    content: bytes = field(repr=False)
    json_expected: bool = False


PUBLIC_WORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "not",
        "no",
        "for",
        "with",
        "to",
        "of",
        "and",
        "or",
        "in",
        "on",
        "at",
        "by",
        "from",
        "please",
        "check",
        "contact",
        "support",
        "portal",
        "request",
        "response",
        "invalid",
        "valid",
        "missing",
        "required",
        "malformed",
        "unsupported",
        "unexpected",
        "unauthorized",
        "forbidden",
        "denied",
        "authentication",
        "authorization",
        "credential",
        "credentials",
        "customer",
        "id",
        "entity",
        "template",
        "sender",
        "source",
        "destination",
        "address",
        "message",
        "type",
        "transactional",
        "prepaid",
        "account",
        "balance",
        "credit",
        "credits",
        "insufficient",
        "exhausted",
        "quota",
        "limit",
        "rate",
        "exceeded",
        "too",
        "many",
        "requests",
        "retry",
        "later",
        "unavailable",
        "service",
        "internal",
        "server",
        "error",
        "failed",
        "failure",
        "success",
        "accepted",
        "rejected",
        "expired",
        "disabled",
        "enabled",
        "active",
        "inactive",
        "permission",
        "permissions",
        "access",
        "allowed",
        "allow",
        "allowlisted",
        "whitelist",
        "ip",
        "errorcode",
        "code",
        "status",
        "detail",
        "details",
        "reason",
        "result",
        "data",
        "field",
        "parameter",
        "token",
        "timeout",
        "connection",
        "connect",
        "protocol",
        "bad",
        "gateway",
        "found",
        "mismatch",
        "registered",
        "registration",
        "dlt",
        "notfound",
        "true",
        "false",
        "null",
        "unknown",
        "numeric",
        "redacted",
        "format",
        "verify",
        "configured",
        "configuration",
        "cannot",
        "could",
        "find",
        "recognize",
        "recognized",
        "recognized",
        "enabled",
        "disabled",
        "blocked",
        "business",
        "subscription",
        "identifier",
        "does",
        "do",
        "exist",
        "exists",
        "enable",
        "invalidcustomerid",
        "invalidcredentials",
        "authenticationfailed",
        "auth",
        "failed",
        "validation",
        "exception",
        "responsecode",
        "statuscode",
        "errormessage",
        "unauthorizedaccess",
    ]
)
PUBLIC_KEYS = frozenset(
    [
        "error",
        "errors",
        "errorcode",
        "error_code",
        "code",
        "status",
        "statuscode",
        "status_code",
        "message",
        "messages",
        "detail",
        "details",
        "description",
        "reason",
        "response",
        "result",
        "data",
        "success",
    ]
)
PRIVATE_KEYS = frozenset(
    [
        "authorization",
        "headers",
        "request",
        "payload",
        "body",
        "customer",
        "customerid",
        "customer_id",
        "mobile",
        "phone",
        "number",
        "name",
        "email",
        "recipient",
        "destinationaddress",
        "otp",
        "password",
        "token",
        "secret",
    ]
)


def public_text(value: str, private: list[str]) -> str:
    for secret in sorted((item for item in private if item), key=len, reverse=True):
        value = re.sub(re.escape(secret), "[redacted]", value, flags=re.IGNORECASE)
    parts = []
    for token in re.findall(r"[A-Za-z]+|[0-9]+|\s+|.", value[:MAX_BODY], flags=re.DOTALL):
        if token.isspace():
            parts.append(" ")
        elif token.isalpha():
            parts.append(token if token.casefold() in PUBLIC_WORDS else "[redacted]")
        elif token in ".,:;_-[]()":
            parts.append(token)
        else:
            parts.append("[redacted]")
    return re.sub(r"(?:\[redacted\][ ]*){2,}", "[redacted] ", "".join(parts)).strip()[:1600]


def public_value(value: Any, private: list[str], depth: int = 0) -> Any:
    if depth > 4:
        return "[redacted]"
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return public_text(value, private)
    if isinstance(value, dict):
        result = {}
        for key, item in list(value.items())[:20]:
            normalized = str(key).casefold()
            safe_key = normalized if normalized in PUBLIC_KEYS else "[redacted_key]"
            result[safe_key] = (
                "[redacted]"
                if normalized in PRIVATE_KEYS
                else public_value(item, private, depth + 1)
            )
        return result
    if isinstance(value, list):
        return [public_value(item, private, depth + 1) for item in value[:10]]
    return "[redacted]"


def response_details(payload: Any, private: list[str]) -> dict[str, Any]:
    kind = "json"
    json_expected = isinstance(payload, ProviderBody) and payload.json_expected
    if isinstance(payload, ProviderBody):
        payload = payload.content
    truncated = False
    if payload is None or payload in (b"", ""):
        return {"response_format": "empty", "response_excerpt": None}
    if isinstance(payload, (str, bytes)):
        truncated = len(payload) > MAX_BODY
        text = (
            payload[:MAX_BODY].decode("utf-8", errors="replace")
            if isinstance(payload, bytes)
            else payload[:MAX_BODY]
        )
        try:
            value = json.loads(text)
        except (ValueError, TypeError, RecursionError):
            value = text
            kind = (
                "malformed_json"
                if json_expected or text.lstrip().startswith(("{", "["))
                else "text"
            )
    else:
        value = payload
    safe = public_value(value, private)
    excerpt = safe if isinstance(safe, str) else json.dumps(safe, ensure_ascii=True)
    return {
        "response_format": "truncated" if truncated else kind,
        "response_excerpt": excerpt[:2000],
    }


def failure_message(code: int | None, category: str) -> str:
    if category == "timeout":
        reason = "Airtel request timed out; submission outcome is unknown."
    elif category == "connection_error":
        reason = "Airtel connection failed; submission outcome is unknown."
    elif category in {"unexpected_response", "transport_error"}:
        reason = "Airtel returned an unexpected transport response; submission outcome is unknown."
    else:
        hints = {
            401: "Check account authorization in the Airtel IQ portal.",
            403: "Check account access permissions in the Airtel IQ portal.",
            429: "Check Airtel throttling and quota before another test.",
        }
        reason = f"Airtel returned HTTP {code}; submission was not accepted. " + hints.get(
            code if code is not None else 0,
            "Review the sanitized response and the Airtel IQ portal before changing settings.",
        )
    return (
        reason
        + " No automatic retry was performed. For unknown outcomes, check the Airtel IQ portal before attempting again."
    )
