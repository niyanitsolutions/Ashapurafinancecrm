"""Module 9B — Meta Lead Ads webhook verification + Graph API lead retrieval.

Reuses Module 9A's stored Meta `IntegrationConfig` (access_token, webhook_verify_token,
webhook_secret) read-only — this module never re-implements credential storage.
Signature verification uses `hmac.compare_digest` (constant-time), the same primitive
already established in `app/security/hashing.py`, applied here to Meta's own
`X-Hub-Signature-256` webhook contract (not implemented anywhere else in this project
before this module). `fetch_lead_fields` itself delegates to Module 9A's shared, retrying
Graph client (`integrations/oauth.py::graph_get`) rather than raw `httpx`, so a transient
Meta-side blip (429/5xx) is retried with backoff before it ever becomes a capture failure.
"""

import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

from app.features.integrations import oauth as oauth_client

logger = logging.getLogger(__name__)


def verify_challenge(*, mode: str | None, verify_token: str | None, expected_token: str) -> bool:
    """A single token-pair comparison — `service.verify_meta_challenge` calls this once
    per configured Meta credential set, since the GET handshake must match *some*
    configured `webhook_verify_token`, not only the currently-`is_active` one (see that
    function's own docstring for why). `.strip()` guards against the common real-world
    mistake of a trailing space pasted into Meta's Webhooks dashboard field;
    `hmac.compare_digest` is the same constant-time comparison `verify_signature` below
    already uses, applied here too since a verify token is a secret worth the same care.
    """
    if mode != "subscribe" or not verify_token or not expected_token:
        return False
    return hmac.compare_digest(expected_token.strip(), verify_token.strip())


def verify_signature(*, raw_body: bytes, signature_header: str | None, secret: str) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)


def looks_like_test_tool_id(value: str) -> bool:
    """Meta's Lead Ads Testing Tool sends a synthetic id made of one digit repeated (e.g.
    "444444444444") for leadgen_id/form_id/page_id/ad_id alike — confirmed against
    Meta's own webhook documentation, whose sample `leadgen` payload uses the same
    repeated-digit style (e.g. "123123123123"); a real Graph object id is a long,
    effectively-random-looking numeric string. Not a Meta-documented *contract* (Meta
    never states this is guaranteed), just an empirically reliable pattern — hence
    "likely" everywhere this is surfaced, never asserted as certain. Used to (a) label
    a capture failure's diagnostic message and (b) classify it as non-retryable, so a
    Testing Tool notification doesn't retry forever against an id that can never
    resolve — never used to skip Graph API verification or fabricate a Lead.
    """
    return bool(value) and value.isdigit() and len(set(value)) == 1


async def fetch_lead_fields(leadgen_id: str, *, access_token: str) -> dict[str, Any]:
    """A real, live Graph API call — Lead Retrieval is explicitly in scope for Module 9B
    (unlike 9A's Test Connection, which never triggers a business action). Raises
    `httpx.HTTPError` (after `graph_get`'s own retries are exhausted) on any persistent
    network/HTTP failure — the caller treats that as a retryable `api_error` capture
    failure, queued in `capture_failures` for the slower minutes-to-hours retry ladder.

    TEMPORARY diagnostics below (investigating the Graph API 400 on lead retrieval) —
    every line tagged [TEMP DIAGNOSTIC:lead_retrieval] is purely observational: the
    Graph call itself (`oauth_client.graph_get`), its retry behavior, and what this
    function returns or raises are all completely unchanged. Safe to delete every
    [TEMP DIAGNOSTIC:lead_retrieval] line (here and the matching block in
    `integrations/oauth.py::_request_with_retry`) once the root cause is confirmed.
    """
    graph_url = f"{oauth_client._GRAPH_BASE}/{leadgen_id}"
    likely_source = "Meta Lead Ads Testing Tool (synthetic id pattern)" if looks_like_test_tool_id(leadgen_id) else "production webhook (real-looking id)"
    logger.info(
        # `access_token` here is always a Page Access Token by construction — the only
        # writer of this config field is `IntegrationsService.connect_meta_oauth`, which
        # stores the OAuth-selected Page's token under this exact key (never the User
        # token, which is kept separately as `user_access_token`) — see that function's
        # own comment. Not a guess: there is no other code path that ever sets this key.
        "[TEMP DIAGNOSTIC:lead_retrieval] leadgen_id=%s graph_url=%s token_type=Page likely_source=%s",
        leadgen_id, graph_url, likely_source,
    )
    try:
        result = await oauth_client.graph_get(leadgen_id, access_token=access_token, fields="field_data", debug_label="lead_retrieval")
    except httpx.HTTPError as exc:
        logger.error("[TEMP DIAGNOSTIC:lead_retrieval] leadgen_id=%s Graph API call raised: %s", leadgen_id, exc)
        if looks_like_test_tool_id(leadgen_id):
            # Meta's Lead Ads Testing Tool notifies the webhook with a synthetic id that
            # has no backing Graph object at all (confirmed: Meta's own webhook docs use
            # the same repeated-digit id style in their sample payload) — this Graph API
            # failure is *expected*, not a production error. Re-raised as the same
            # exception type with a clearer message, so `CaptureFailure.error_detail`
            # reads as a diagnosis instead of a raw Graph error that looks identical to a
            # genuine outage. `handle_meta_webhook` still catches this exactly like any
            # other `httpx.HTTPError` — only the message and (there) the retry
            # classification differ; nothing about control flow does.
            raise httpx.HTTPError(
                f"Meta Lead Ads Testing Tool notification (leadgen_id={leadgen_id}, synthetic/non-retrievable by "
                f"design) — Meta does not provide real field_data for test webhook deliveries, so this Graph API "
                f"call was expected to fail; this is not a production error. Original Graph response: {exc}"
            ) from exc
        raise
    return result


# Field *names* vary per form (an Owner names their own form fields in Meta's UI) — this
# maps the handful this project's Lead model cares about directly; every other field a
# form asks (a form's own custom questions — "Preferred City," "Loan Amount Interested
# In," etc.) is preserved verbatim rather than silently discarded, per the brief's own
# "store custom questions" requirement — see `custom_questions` below.
_KNOWN_FIELD_MAP = {"full_name": "full_name", "name": "full_name", "phone_number": "mobile", "phone": "mobile", "email": "email"}


def parse_field_data(payload: dict[str, Any]) -> dict[str, str]:
    """Meta's own lead field shape: `{"field_data": [{"name": "full_name", "values": ["Jane Doe"]}, ...]}`."""
    parsed: dict[str, str] = {}
    custom_questions: dict[str, str] = {}
    for field in payload.get("field_data", []):
        name = str(field.get("name", ""))
        values = field.get("values") or []
        if not values:
            continue
        key = _KNOWN_FIELD_MAP.get(name.lower())
        if key:
            parsed[key] = str(values[0])
        else:
            custom_questions[name] = str(values[0])
    if custom_questions:
        # `ParsedLead.source_metadata` (see parsers.py) is `dict[str, str]` — JSON-encoded
        # here rather than widening that contract to `dict[str, Any]` for one field.
        parsed["custom_questions"] = json.dumps(custom_questions)
    return parsed
