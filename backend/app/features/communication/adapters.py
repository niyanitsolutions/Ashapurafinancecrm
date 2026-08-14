"""Module 9C — Provider Adapters. Every channel implements the exact same interface
(`send(recipient, subject, body, config, ...) -> DeliveryOutcome`) so the queue processor
never branches on provider-specific logic, and a future channel/provider only needs one
more function registered in `ADAPTERS`. Reuses Module 9A's stored, encrypted
`IntegrationConfig` for credentials — never re-implements credential storage.

WhatsApp/SMS send via a generic HTTP POST to the config's own `api_url` by default (these
are explicitly multi-provider per the brief — there's no single fixed API contract to
target more deeply for an arbitrary future provider, the same honest limitation 9A's own
Test Connection already disclosed for these two channels). When the active config's own
`provider` is `"msg91"` (Stage 2 of the Geo Fencing/MSG91 request — see
docs/COMMUNICATION.md), `send_sms`/`send_whatsapp` branch to a real MSG91 API call instead
— the generic path is untouched and remains the fallback for every other provider. Email
sends a real message via SMTP (`smtplib`, standard library) when the active config looks
like SMTP (has `host`) — this is also MSG91 Email's own path (MSG91 issues standard SMTP
relay credentials for transactional email; no MSG91-specific email code exists, by
design, see docs/COMMUNICATION.md) — or a generic HTTP POST for an API-based email provider.

`recipient`/`subject`/`body`/`config` stay the required, original 4 positional-by-keyword
arguments every existing caller already passes. `variables`/`variable_order`/
`provider_template_meta` are new, optional, default-`None` keyword arguments — needed only
by MSG91's WhatsApp/SMS branches (real WhatsApp Business / DLT-registered SMS templates
take *named positional* placeholders, not a pre-rendered free-text body); every other path
(the 2 generic branches, all of `send_email`) ignores them entirely, so no existing
behavior changes for a caller/test that doesn't pass them.

`_timed_post`/`_send_smtp`/`_send_msg91_request` are the functions tests monkeypatch to
avoid live network/SMTP calls — see tests/api/test_communication.py.
"""

import asyncio
import re
import smtplib
import ssl
import time
from dataclasses import dataclass
from email.mime.text import MIMEText
from typing import Any

import httpx

from app.features.communication.constants import Channel

MSG91_SMS_FLOW_URL = "https://api.msg91.com/api/v5/flow/"
MSG91_WHATSAPP_URL = "https://api.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/"


@dataclass(frozen=True)
class DeliveryOutcome:
    success: bool
    provider_message_id: str | None
    error: str | None
    is_transient: bool  # whether a failure is worth retrying automatically
    response_time_ms: int = 0


async def _timed_post(url: str, **kwargs: Any) -> tuple[bool, str | None, int]:
    start = time.monotonic()
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, **kwargs)
    elapsed_ms = int((time.monotonic() - start) * 1000)
    return response.status_code < 400, response.text[:200] if response.status_code >= 400 else None, elapsed_ms


def _normalize_indian_mobile(recipient: str) -> str:
    """MSG91's Flow/WhatsApp APIs want international format (e.g. `919876543210`);
    every recipient in this codebase is stored as a plain 10-digit Indian mobile number
    (`Lead.mobile`/`Employee.mobile`/etc. all validate `^[6-9]\\d{9}$`) — this is a data-
    shape adapter for our own model, not a guess about MSG91's own contract."""
    digits = re.sub(r"\D", "", recipient)
    if len(digits) == 10:
        return f"91{digits}"
    return digits


def _ordered_variable_values(variables: dict[str, str] | None, variable_order: list[str] | None) -> list[str]:
    if not variable_order:
        return []
    values = variables or {}
    return [values.get(name, "") for name in variable_order]


def _classify_msg91_error(status_code: int, message: str) -> tuple[str, bool]:
    """Maps a raw MSG91 error onto the spec's own required error message shapes (Part 16)
    — never surfaces MSG91's raw response body/stack trace verbatim beyond its own
    human-readable `message` field. Returns (error_message, is_transient)."""
    lowered = message.lower()
    if status_code in (401, 403) or "authkey" in lowered or "auth key" in lowered or "unauthorized" in lowered:
        return "Unable to authenticate with the communication provider.", False
    if status_code == 429 or "rate limit" in lowered:
        return "Provider rate limit reached. Message will be retried.", True
    if status_code >= 500:
        return "MSG91 is temporarily unavailable. Message will be retried.", True
    if "mobile" in lowered or "number" in lowered or "recipient" in lowered:
        return "Invalid recipient.", False
    if "template" in lowered or "flow" in lowered or "namespace" in lowered:
        return "Message template is invalid or not approved.", False
    return message[:300], status_code >= 500


async def _send_msg91_request(url: str, *, auth_key: str, json_body: dict[str, Any]) -> tuple[bool, dict[str, Any] | str, int, int]:
    """Returns (http_ok, parsed_json_or_raw_text, status_code, elapsed_ms) — never raises
    on an HTTP error status (MSG91 returns a 200 with `{"type": "error", ...}` for some
    failures and a non-2xx for others, per docs.msg91.com; both are handled by the caller)."""
    start = time.monotonic()
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, headers={"authkey": auth_key, "Content-Type": "application/json"}, json=json_body)
    elapsed_ms = int((time.monotonic() - start) * 1000)
    try:
        return response.status_code < 400, response.json(), response.status_code, elapsed_ms
    except ValueError:
        return response.status_code < 400, response.text[:300], response.status_code, elapsed_ms


async def _send_msg91_sms(*, recipient: str, config: dict[str, str], variables: dict[str, str] | None, variable_order: list[str] | None) -> DeliveryOutcome:
    auth_key = config.get("auth_key")
    flow_id = config.get("flow_id")
    if not auth_key or not flow_id:
        return DeliveryOutcome(False, None, "MSG91 is not configured for this channel.", is_transient=False)

    recipient_entry: dict[str, str] = {"mobiles": _normalize_indian_mobile(recipient)}
    for index, value in enumerate(_ordered_variable_values(variables, variable_order), start=1):
        recipient_entry[f"VAR{index}"] = value
    json_body: dict[str, Any] = {"flow_id": flow_id, "recipients": [recipient_entry]}
    if config.get("sender_id"):
        json_body["sender"] = config["sender_id"]

    try:
        ok, payload, status_code, elapsed_ms = await _send_msg91_request(MSG91_SMS_FLOW_URL, auth_key=auth_key, json_body=json_body)
    except httpx.HTTPError as exc:
        return DeliveryOutcome(False, None, str(exc), is_transient=True)

    if isinstance(payload, dict) and ok and payload.get("type") == "success":
        return DeliveryOutcome(True, payload.get("message"), None, is_transient=False, response_time_ms=elapsed_ms)

    raw_message = payload.get("message") if isinstance(payload, dict) else str(payload)
    error, is_transient = _classify_msg91_error(status_code, str(raw_message or f"HTTP {status_code}"))
    return DeliveryOutcome(False, None, error, is_transient=is_transient, response_time_ms=elapsed_ms)


async def _send_msg91_whatsapp(
    *, recipient: str, config: dict[str, str], variables: dict[str, str] | None, variable_order: list[str] | None,
    provider_template_meta: dict[str, str | None] | None,
) -> DeliveryOutcome:
    auth_key = config.get("auth_key")
    integrated_number = config.get("integrated_number")
    if not auth_key or not integrated_number:
        return DeliveryOutcome(False, None, "MSG91 is not configured for this channel.", is_transient=False)

    template_name = (provider_template_meta or {}).get("name")
    namespace = (provider_template_meta or {}).get("namespace")
    if not template_name or not namespace:
        return DeliveryOutcome(False, None, "Message template is invalid or not approved.", is_transient=False)
    language_code = (provider_template_meta or {}).get("language") or "en"

    components = {f"body_{i}": {"type": "text", "value": v} for i, v in enumerate(_ordered_variable_values(variables, variable_order), start=1)}
    json_body = {
        "integrated_number": integrated_number,
        "content_type": "template",
        "payload": {
            "messaging_product": "whatsapp",
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code, "policy": "deterministic"},
                "namespace": namespace,
                "to_and_components": [{"to": [_normalize_indian_mobile(recipient)], "components": components}],
            },
        },
    }

    try:
        ok, payload, status_code, elapsed_ms = await _send_msg91_request(MSG91_WHATSAPP_URL, auth_key=auth_key, json_body=json_body)
    except httpx.HTTPError as exc:
        return DeliveryOutcome(False, None, str(exc), is_transient=True)

    if isinstance(payload, dict) and ok and payload.get("type") == "success":
        provider_message_id = payload.get("message") or payload.get("request_id")
        return DeliveryOutcome(True, provider_message_id, None, is_transient=False, response_time_ms=elapsed_ms)

    raw_message = payload.get("message") if isinstance(payload, dict) else str(payload)
    error, is_transient = _classify_msg91_error(status_code, str(raw_message or f"HTTP {status_code}"))
    return DeliveryOutcome(False, None, error, is_transient=is_transient, response_time_ms=elapsed_ms)


async def send_whatsapp(
    *, recipient: str, subject: str | None, body: str, config: dict[str, str],
    variables: dict[str, str] | None = None, variable_order: list[str] | None = None, provider_template_meta: dict[str, str | None] | None = None,
) -> DeliveryOutcome:
    if config.get("_provider") == "msg91":
        return await _send_msg91_whatsapp(
            recipient=recipient, config=config, variables=variables, variable_order=variable_order, provider_template_meta=provider_template_meta
        )
    api_url = config.get("api_url")
    access_token = config.get("access_token")
    if not api_url or not access_token:
        return DeliveryOutcome(False, None, "WhatsApp config is missing api_url/access_token.", is_transient=False)
    try:
        ok, error, elapsed_ms = await _timed_post(
            api_url, headers={"Authorization": f"Bearer {access_token}"}, json={"to": recipient, "type": "text", "text": {"body": body}}
        )
        return DeliveryOutcome(ok, None, error, is_transient=not ok, response_time_ms=elapsed_ms)
    except httpx.HTTPError as exc:
        return DeliveryOutcome(False, None, str(exc), is_transient=True)


async def send_sms(
    *, recipient: str, subject: str | None, body: str, config: dict[str, str],
    variables: dict[str, str] | None = None, variable_order: list[str] | None = None, provider_template_meta: dict[str, str | None] | None = None,
) -> DeliveryOutcome:
    if config.get("_provider") == "msg91":
        return await _send_msg91_sms(recipient=recipient, config=config, variables=variables, variable_order=variable_order)
    api_url = config.get("api_url")
    api_key = config.get("api_key")
    if not api_url or not api_key:
        return DeliveryOutcome(False, None, "SMS config is missing api_url/api_key.", is_transient=False)
    try:
        ok, error, elapsed_ms = await _timed_post(
            api_url, headers={"Authorization": f"Bearer {api_key}"}, json={"to": recipient, "message": body, "sender_id": config.get("sender_id")}
        )
        return DeliveryOutcome(ok, None, error, is_transient=not ok, response_time_ms=elapsed_ms)
    except httpx.HTTPError as exc:
        return DeliveryOutcome(False, None, str(exc), is_transient=True)


def _send_smtp(*, host: str, port: int, use_tls: bool, username: str | None, password: str | None, from_email: str, to_email: str, subject: str, body: str) -> None:
    message = MIMEText(body, "plain")
    message["Subject"] = subject
    message["From"] = from_email
    message["To"] = to_email
    server = smtplib.SMTP(host, port, timeout=10)
    try:
        server.ehlo()
        if use_tls:
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        if username and password:
            server.login(username, password)
        server.sendmail(from_email, [to_email], message.as_string())
    finally:
        server.quit()


async def send_email(
    *, recipient: str, subject: str | None, body: str, config: dict[str, str],
    variables: dict[str, str] | None = None, variable_order: list[str] | None = None, provider_template_meta: dict[str, str | None] | None = None,
) -> DeliveryOutcome:
    # MSG91 Email is sent via this exact same generic SMTP path (MSG91 issues standard
    # SMTP relay credentials — no MSG91-specific request/response contract to guess or
    # target). `variables`/`variable_order`/`provider_template_meta` are accepted only for
    # interface uniformity with send_sms/send_whatsapp and are unused here.
    host = config.get("host")
    from_email = config.get("from_email", "")
    start = time.monotonic()
    if host:
        port = config.get("port")
        if not port:
            return DeliveryOutcome(False, None, "SMTP config is missing port.", is_transient=False)
        use_tls = config.get("tls_ssl", "").strip().lower() in ("true", "1", "yes")
        try:
            await asyncio.to_thread(
                _send_smtp, host=host, port=int(port), use_tls=use_tls, username=config.get("username"), password=config.get("password"),
                from_email=from_email, to_email=recipient, subject=subject or "", body=body,
            )
            return DeliveryOutcome(True, None, None, is_transient=False, response_time_ms=int((time.monotonic() - start) * 1000))
        except (OSError, smtplib.SMTPException) as exc:
            return DeliveryOutcome(False, None, str(exc), is_transient=True, response_time_ms=int((time.monotonic() - start) * 1000))

    api_key = config.get("api_key")
    api_url = config.get("api_url")
    if not api_key or not api_url:
        return DeliveryOutcome(False, None, "Email config is missing host (SMTP) or api_key+api_url (API-based).", is_transient=False)
    try:
        ok, error, elapsed_ms = await _timed_post(
            api_url, headers={"Authorization": f"Bearer {api_key}"}, json={"to": recipient, "from": from_email, "subject": subject, "body": body}
        )
        return DeliveryOutcome(ok, None, error, is_transient=not ok, response_time_ms=elapsed_ms)
    except httpx.HTTPError as exc:
        return DeliveryOutcome(False, None, str(exc), is_transient=True)


ADAPTERS = {
    Channel.WHATSAPP: send_whatsapp,
    Channel.SMS: send_sms,
    Channel.EMAIL: send_email,
}
