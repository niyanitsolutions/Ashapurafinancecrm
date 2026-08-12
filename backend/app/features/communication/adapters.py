"""Module 9C — Provider Adapters. Every channel implements the exact same interface
(`send(recipient, subject, body, config) -> DeliveryOutcome`) so the queue processor
never branches on provider-specific logic, and a future channel/provider only needs one
more function registered in `ADAPTERS`. Reuses Module 9A's stored, encrypted
`IntegrationConfig` for credentials — never re-implements credential storage.

WhatsApp/SMS send via a generic HTTP POST to the config's own `api_url` (these are
explicitly multi-provider per the brief — there's no single fixed API contract to
target more deeply, the same honest limitation 9A's own Test Connection already
disclosed for these two channels). Email sends a real message via SMTP
(`smtplib`, standard library) when the active config looks like SMTP (has `host`), or a
generic HTTP POST for an API-based email provider.

`_timed_post`/`_send_smtp` are the two functions tests monkeypatch to avoid live
network/SMTP calls — see tests/api/test_communication.py.
"""

import asyncio
import smtplib
import ssl
import time
from dataclasses import dataclass
from email.mime.text import MIMEText
from typing import Any

import httpx

from app.features.communication.constants import Channel


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


async def send_whatsapp(*, recipient: str, subject: str | None, body: str, config: dict[str, str]) -> DeliveryOutcome:
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


async def send_sms(*, recipient: str, subject: str | None, body: str, config: dict[str, str]) -> DeliveryOutcome:
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


async def send_email(*, recipient: str, subject: str | None, body: str, config: dict[str, str]) -> DeliveryOutcome:
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
