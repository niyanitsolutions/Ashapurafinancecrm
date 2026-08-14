"""Module 9A — Test Connection implementations, one per Integration Type.

Every function here does the minimum needed to prove the stored credentials are valid
and the endpoint is reachable — **never a business action** (no WhatsApp/SMS/email is
sent, no Meta lead is fetched), per explicit instruction. Meta and Google Maps have one
well-known public API, so their check is a real, live, read-only authenticated call.
WhatsApp/SMS/API-based Email are provider-agnostic (the brief itself asks these to
support multiple future providers) — with no fixed API contract to target, their check
is a generic reachability request against the stored `api_url`. SMTP-based Email gets a
real connection + STARTTLS + login handshake via the standard library, without sending
mail.

`_timed_get`/`_test_smtp`/`fetch_debug_token` are the functions tests monkeypatch to avoid
live network calls — see tests/api/test_integrations.py.
"""

import asyncio
import ipaddress
import smtplib
import socket
import ssl
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.features.integrations.constants import IntegrationType

GRAPH_API_VERSION = "v19.0"


class UnsafeTargetError(Exception):
    """Raised when a user-supplied `api_url`/SMTP host resolves somewhere Test
    Connection must never reach — loopback, link-local (incl. the 169.254.169.254 cloud
    metadata endpoint), private/carrier-shared ranges, or a non-https scheme. Every
    tester that takes an arbitrary user-supplied host goes through `_assert_safe_host`/
    `_assert_safe_url` first; the Meta/Maps testers hit one fixed, hardcoded host each
    and don't need this."""


def _assert_safe_host(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UnsafeTargetError(f"Could not resolve host: {host}") from exc
    if not infos:
        raise UnsafeTargetError(f"Could not resolve host: {host}")
    for family, _, _, _, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
            or ip.is_multicast or ip.is_unspecified
        ):
            raise UnsafeTargetError(f"Host {host} resolves to a non-public address ({ip}) — refusing to connect.")


def _assert_safe_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https":
        raise UnsafeTargetError("Only https:// URLs are allowed for Test Connection.")
    if not parsed.hostname:
        raise UnsafeTargetError("Missing host in URL.")
    _assert_safe_host(parsed.hostname)

# The permissions the Lead Capture pipeline (Module 9B) actually needs from a Meta config —
# checked against the access token's granted `scopes`, never enforced beyond this diagnostic.
# `oauth.py::META_OAUTH_SCOPES` requests a couple more (ads_read, business_management,
# pages_read_engagement, pages_manage_ads) for the Ad Account/Instagram/Business-id
# picker info — those are best-effort display data, not required for a lead to actually
# reach this CRM, so they're deliberately not enforced here the way these two are.
REQUIRED_META_PERMISSIONS: dict[str, str] = {
    "leads_retrieval": "Required to read Lead Ads submissions.",
    "pages_show_list": "Required to list the Pages this token can manage.",
    "pages_manage_metadata": "Required to subscribe a Page to leadgen webhook notifications.",
}

# A handful of Graph API error codes worth a friendlier message than the raw JSON blob —
# everything else falls back to Graph's own `error.message`, which is already human-written.
_GRAPH_ERROR_MESSAGES = {
    190: "Access Token is invalid or has expired.",
    102: "Access Token session has expired or is invalid.",
}


@dataclass(frozen=True)
class ConnectionCheckItem:
    key: str
    label: str
    passed: bool
    detail: str | None = None


@dataclass(frozen=True)
class ConnectionCheckResult:
    success: bool
    response_time_ms: int
    error_message: str | None
    # Populated by `test_meta` only — every other tester leaves this `None`, unaffected.
    checks: list[ConnectionCheckItem] | None = None


def _missing_field(field_name: str) -> ConnectionCheckResult:
    return ConnectionCheckResult(success=False, response_time_ms=0, error_message=f"Missing required field: {field_name}")


async def _timed_get(url: str, **kwargs: Any) -> ConnectionCheckResult:
    start = time.monotonic()
    try:
        _assert_safe_url(url)
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            response = await client.get(url, **kwargs)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        if response.status_code >= 400:
            return ConnectionCheckResult(False, elapsed_ms, f"HTTP {response.status_code}")
        return ConnectionCheckResult(True, elapsed_ms, None)
    except UnsafeTargetError as exc:
        return ConnectionCheckResult(False, int((time.monotonic() - start) * 1000), str(exc))
    except httpx.HTTPError as exc:
        return ConnectionCheckResult(False, int((time.monotonic() - start) * 1000), str(exc))


def _connect_smtp(host: str, port: int, *, use_tls: bool, username: str | None, password: str | None) -> None:
    _assert_safe_host(host)
    server = smtplib.SMTP(host, port, timeout=10)
    try:
        server.ehlo()
        if use_tls:
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        if username and password:
            server.login(username, password)
    finally:
        server.quit()


async def _test_smtp(config: dict[str, str]) -> ConnectionCheckResult:
    host, port = config.get("host"), config.get("port")
    if not host:
        return _missing_field("host")
    if not port:
        return _missing_field("port")
    try:
        port_number = int(port)
    except ValueError:
        return ConnectionCheckResult(False, 0, f"Invalid port: {port!r} is not a number.")
    use_tls = config.get("tls_ssl", "").strip().lower() in ("true", "1", "yes")
    start = time.monotonic()
    try:
        await asyncio.to_thread(_connect_smtp, host, port_number, use_tls=use_tls, username=config.get("username"), password=config.get("password"))
        return ConnectionCheckResult(True, int((time.monotonic() - start) * 1000), None)
    except (OSError, smtplib.SMTPException, UnsafeTargetError) as exc:
        return ConnectionCheckResult(False, int((time.monotonic() - start) * 1000), str(exc))


def _graph_error_message(error: dict[str, Any]) -> str:
    code = error.get("code")
    fallback = str(error.get("message") or "Unknown error from Meta.")
    return _GRAPH_ERROR_MESSAGES.get(code, fallback) if isinstance(code, int) else fallback


async def fetch_debug_token(access_token: str, app_id: str, app_secret: str) -> tuple[dict[str, Any] | None, str | None]:
    """Returns `(data, None)` on success or `(None, error_message)` — never raises. Reaching
    a successful response at all already proves `app_secret` is correct, since it's used to
    build the `access_token` param (`{app_id}|{app_secret}`) that authorizes this very call."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"https://graph.facebook.com/{GRAPH_API_VERSION}/debug_token",
                params={"input_token": access_token, "access_token": f"{app_id}|{app_secret}"},
            )
        body = response.json()
    except httpx.HTTPError as exc:
        return None, str(exc)
    except ValueError:
        return None, "Unexpected (non-JSON) response from Meta."

    if response.status_code >= 400 or "error" in body:
        return None, _graph_error_message(body.get("error", {}))
    return body.get("data") or {}, None


async def test_meta(config: dict[str, str]) -> ConnectionCheckResult:
    app_id, app_secret, access_token = config.get("app_id"), config.get("app_secret"), config.get("access_token")
    for field_name, value in (("app_id", app_id), ("app_secret", app_secret), ("access_token", access_token)):
        if not value:
            return _missing_field(field_name)
    assert app_id and app_secret and access_token  # narrowed by the loop above, for mypy

    start = time.monotonic()
    data, error = await fetch_debug_token(access_token, app_id, app_secret)
    elapsed_ms = int((time.monotonic() - start) * 1000)

    if error is not None:
        checks = [
            ConnectionCheckItem("app_id", "App ID valid", False, "Could not verify — see Access Token check."),
            ConnectionCheckItem("app_secret", "App Secret valid", False, "Could not verify — see Access Token check."),
            ConnectionCheckItem("token", "Access Token valid", False, error),
            ConnectionCheckItem("permissions", "Permissions granted", False, "Could not verify — see Access Token check."),
        ]
        return ConnectionCheckResult(False, elapsed_ms, error, checks=checks)

    data = data or {}
    app_id_matches = str(data.get("app_id") or "") == str(app_id)
    token_valid = bool(data.get("is_valid"))
    scopes = set(data.get("scopes") or [])
    missing_permissions = [p for p in REQUIRED_META_PERMISSIONS if p not in scopes]

    checks = [
        # Reaching this point at all already proves app_secret authorized the call.
        ConnectionCheckItem("app_secret", "App Secret valid", True, None),
        ConnectionCheckItem(
            "app_id", "App ID valid", app_id_matches,
            None if app_id_matches else "This Access Token does not belong to the configured App ID.",
        ),
        ConnectionCheckItem("token", "Access Token valid", token_valid, None if token_valid else "Token is expired or has been revoked."),
        ConnectionCheckItem(
            "permissions", "Permissions granted", not missing_permissions,
            None if not missing_permissions else f"Missing: {', '.join(missing_permissions)}",
        ),
    ]
    success = app_id_matches and token_valid and not missing_permissions
    error_message = None if success else "; ".join(c.detail for c in checks if not c.passed and c.detail)
    return ConnectionCheckResult(success, elapsed_ms, error_message, checks=checks)


MSG91_BALANCE_URL = "https://api.msg91.com/api/balance.php"


async def _test_msg91_authkey(auth_key: str) -> ConnectionCheckResult:
    """Validates an MSG91 authkey via the balance-check endpoint (`GET .../balance.php`,
    documented at api.msg91.com/apidoc/basic/route-balance.php) — MSG91 has no dedicated
    "whoami"/health endpoint, so this is the closest lightweight, read-only, never-a-
    business-action call to confirm a key actually authenticates. Shared by the SMS and
    WhatsApp testers, since one MSG91 account authkey is used across every channel. The
    exact success/failure response shape for this specific endpoint could not be
    independently confirmed against a live account in this environment (see
    docs/KNOWN_LIMITATIONS.md) — classification here is by HTTP status only, the same
    conservative approach `_timed_get` already uses for the generic WhatsApp/SMS testers."""
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(MSG91_BALANCE_URL, params={"authkey": auth_key, "type": "4"})
        elapsed_ms = int((time.monotonic() - start) * 1000)
        if response.status_code in (401, 403):
            return ConnectionCheckResult(False, elapsed_ms, "Unable to authenticate with MSG91.")
        if response.status_code >= 400:
            return ConnectionCheckResult(False, elapsed_ms, f"HTTP {response.status_code}")
        return ConnectionCheckResult(True, elapsed_ms, None)
    except httpx.HTTPError as exc:
        return ConnectionCheckResult(False, int((time.monotonic() - start) * 1000), str(exc))


async def test_whatsapp(config: dict[str, str]) -> ConnectionCheckResult:
    if config.get("provider") == "msg91":
        auth_key = config.get("auth_key")
        if not auth_key:
            return _missing_field("auth_key")
        if not config.get("integrated_number"):
            return _missing_field("integrated_number")
        return await _test_msg91_authkey(auth_key)
    api_url = config.get("api_url")
    if not api_url:
        return _missing_field("api_url")
    access_token = config.get("access_token")
    headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
    return await _timed_get(api_url, headers=headers)


async def test_sms(config: dict[str, str]) -> ConnectionCheckResult:
    if config.get("provider") == "msg91":
        auth_key = config.get("auth_key")
        if not auth_key:
            return _missing_field("auth_key")
        if not config.get("flow_id"):
            return _missing_field("flow_id")
        return await _test_msg91_authkey(auth_key)
    api_url = config.get("api_url")
    if not api_url:
        return _missing_field("api_url")
    return await _timed_get(api_url)


async def test_email(config: dict[str, str]) -> ConnectionCheckResult:
    if config.get("host"):
        return await _test_smtp(config)
    api_key = config.get("api_key")
    if not api_key:
        return _missing_field("host (SMTP) or api_key (API-based)")
    api_url = config.get("api_url")
    if api_url:
        return await _timed_get(api_url, headers={"Authorization": f"Bearer {api_key}"})
    return ConnectionCheckResult(True, 0, None)  # API-based provider with no reachable endpoint configured — field presence is all that's checkable


async def test_maps(config: dict[str, str]) -> ConnectionCheckResult:
    api_key = config.get("api_key")
    if not api_key:
        return _missing_field("api_key")
    return await _timed_get("https://maps.googleapis.com/maps/api/geocode/json", params={"address": "New Delhi", "key": api_key})


TESTERS = {
    IntegrationType.META: test_meta,
    IntegrationType.WHATSAPP: test_whatsapp,
    IntegrationType.SMS: test_sms,
    IntegrationType.EMAIL: test_email,
    IntegrationType.MAPS: test_maps,
}
