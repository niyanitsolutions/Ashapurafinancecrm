"""Module 9A — Meta OAuth Connect flow + reusable Graph API service.

Every Meta Graph API call this project makes — OAuth token exchange, Page/Ad
Account/Lead Form/Instagram listing, webhook subscription, campaign/adset/ad name
lookup, and token refresh — funnels through `graph_get`/`graph_post` here, so retry-on-
transient-failure, rate-limit backoff, and error normalization live in exactly one
place rather than being reimplemented per caller. `meta_status.py` (Connection Health)
and `lead_capture/meta_client.py` (live Lead Retrieval) both call into this module for
their own Graph requests instead of raw `httpx` — see their own docstrings.

A `None`/empty-list return from the higher-level `fetch_*` functions means "could not
be determined" (bad token, missing scope) and is handled by the caller as an empty
picker list, never a hard failure. Only a real, non-retryable transport/API error
(`httpx.HTTPError`) propagates out of `graph_get`/`graph_post` themselves.
"""

import asyncio
import logging
from typing import Any
from urllib.parse import urlencode

import httpx

from app.features.integrations.constants import META_OAUTH_SCOPES
from app.features.integrations.testers import GRAPH_API_VERSION

logger = logging.getLogger(__name__)

_AUTHORIZE_URL = "https://www.facebook.com/v19.0/dialog/oauth"
_GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# Transient conditions worth retrying: 429 (Meta's own app-level/ad-account-level rate
# limiting), and 5xx (Meta-side outage/timeout). A 4xx auth/permission error (expired
# token, missing scope) is never retried — retrying a token that will never become valid
# just wastes calls and delays surfacing the real problem to the Owner.
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_BASE_SECONDS = 1.0
_MAX_PAGINATION_PAGES = 10  # safety valve — same posture as meta_status._MAX_PAGES_FOR_LEAD_FORMS


def build_authorize_url(*, app_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": ",".join(META_OAUTH_SCOPES),
        "response_type": "code",
    }
    return f"{_AUTHORIZE_URL}?{urlencode(params)}"


def _graph_error_message(body: dict[str, Any], status_code: int) -> str:
    error = body.get("error") or {}
    return str(error.get("message") or f"HTTP {status_code} from Meta.")


async def _request_with_retry(
    method: str, url: str, *, params: dict[str, Any] | None = None, debug_label: str | None = None
) -> dict[str, Any]:
    # `debug_label` is kept in the signature for call-site compatibility (some callers
    # still pass one, e.g. "page_subscription") even though nothing here logs it anymore.
    del debug_label
    last_error: httpx.HTTPError | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            # Graph API accepts every parameter (including access_token) as a query
            # string regardless of HTTP verb — matches the original POST call this
            # replaced (`client.post(url, params={...})`), not a form-encoded body.
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.request(method, url, params=params)
        except httpx.HTTPError as exc:
            last_error = exc
            logger.warning("Meta Graph API request failed (network error), attempt %s/%s: %s", attempt + 1, _MAX_ATTEMPTS, exc)
        else:
            body: dict[str, Any] = response.json() if response.content else {}
            if response.status_code not in _RETRYABLE_STATUS_CODES and "error" not in body:
                if response.status_code >= 400:
                    raise httpx.HTTPError(_graph_error_message(body, response.status_code))
                return body
            if response.status_code not in _RETRYABLE_STATUS_CODES:
                # A well-formed `error` object on a non-retryable status (e.g. 400 invalid
                # parameter) — fail immediately, no point retrying.
                raise httpx.HTTPError(_graph_error_message(body, response.status_code))
            last_error = httpx.HTTPError(_graph_error_message(body, response.status_code))
            logger.warning(
                "Meta Graph API returned retryable status %s, attempt %s/%s: %s", response.status_code, attempt + 1, _MAX_ATTEMPTS, last_error
            )
        if attempt < _MAX_ATTEMPTS - 1:
            await asyncio.sleep(_RETRY_BACKOFF_BASE_SECONDS * (2**attempt))
    assert last_error is not None
    raise last_error


async def graph_get(path: str, *, debug_label: str | None = None, **params: Any) -> dict[str, Any]:
    """`path` may be a bare Graph edge (`"me/accounts"`) or a full `paging.next` URL —
    both are retried identically. `debug_label` is TEMPORARY diagnostic plumbing only —
    see `_request_with_retry`; omitting it (every existing call site does) changes
    nothing about behavior."""
    url = path if path.startswith("http") else f"{_GRAPH_BASE}/{path}"
    return await _request_with_retry("GET", url, params=params, debug_label=debug_label)


async def graph_post(path: str, *, debug_label: str | None = None, **params: Any) -> dict[str, Any]:
    url = path if path.startswith("http") else f"{_GRAPH_BASE}/{path}"
    return await _request_with_retry("POST", url, params=params, debug_label=debug_label)


async def _graph_get_all_pages(path: str, **params: Any) -> list[dict[str, Any]]:
    """Follows Meta's cursor-based `paging.next` up to `_MAX_PAGINATION_PAGES` — unlike
    `meta_status.py`'s deliberately-uncapped-at-one-page diagnostic reads, the OAuth
    Connect picker is a one-time setup action where an Owner genuinely needs to see every
    Page/Ad Account/Form, not just the first ~25."""
    items: list[dict[str, Any]] = []
    next_url: str | None = None
    for _ in range(_MAX_PAGINATION_PAGES):
        body = await graph_get(next_url or path, **({} if next_url else params))
        items.extend(body.get("data", []))
        next_url = (body.get("paging") or {}).get("next")
        if not next_url:
            break
    return items


async def exchange_code_for_token(*, app_id: str, app_secret: str, redirect_uri: str, code: str) -> tuple[str, int | None]:
    """Short-lived User Access Token — the first leg of the OAuth code exchange."""
    body = await graph_get("oauth/access_token", client_id=app_id, client_secret=app_secret, redirect_uri=redirect_uri, code=code)
    return str(body["access_token"]), body.get("expires_in")


async def exchange_for_long_lived_token(*, app_id: str, app_secret: str, short_lived_token: str) -> tuple[str, int | None]:
    """~60-day long-lived User Access Token — what a Page Access Token is derived from,
    and what `worker/tasks/meta_token_refresh.py` re-runs before it expires."""
    body = await graph_get(
        "oauth/access_token", grant_type="fb_exchange_token", client_id=app_id, client_secret=app_secret, fb_exchange_token=short_lived_token
    )
    return str(body["access_token"]), body.get("expires_in")


async def fetch_pages_with_tokens(user_access_token: str) -> list[dict[str, str]]:
    """Includes each Page's linked Instagram Business Account (if any) — Instagram Lead
    Ads submissions arrive over the *same* Page-level `leadgen` webhook subscription
    (`subscribe_page_to_leadgen`), so no separate Instagram OAuth/picker step exists;
    this is surfaced purely so the Owner can see which Page also covers Instagram."""
    rows = await _graph_get_all_pages(
        "me/accounts", access_token=user_access_token, fields="id,name,access_token,instagram_business_account{id,username}", limit=100
    )
    pages = []
    for p in rows:
        ig = p.get("instagram_business_account")
        pages.append({"id": p["id"], "name": p["name"], "access_token": p["access_token"], "instagram_username": ig.get("username", "") if ig else ""})
    return pages


async def fetch_ad_accounts(user_access_token: str) -> list[dict[str, str]]:
    rows = await _graph_get_all_pages("me/adaccounts", access_token=user_access_token, fields="id,name", limit=100)
    return [{"id": a["id"], "name": a.get("name", a["id"])} for a in rows]


async def fetch_lead_forms(*, page_access_token: str, page_id: str) -> list[dict[str, str]]:
    rows = await _graph_get_all_pages(f"{page_id}/leadgen_forms", access_token=page_access_token, fields="id,name", limit=100)
    return [{"id": f["id"], "name": f.get("name", f["id"])} for f in rows]


async def fetch_page_business_id(*, page_access_token: str, page_id: str) -> str | None:
    """Best-effort only — requires the Page to belong to a Business Manager and the token
    to carry `business_management`; a missing value here never blocks Connect."""
    try:
        body = await graph_get(page_id, access_token=page_access_token, fields="business")
    except httpx.HTTPError:
        return None
    business = body.get("business")
    return str(business["id"]) if isinstance(business, dict) and business.get("id") else None


async def fetch_ad_campaign_details(*, access_token: str, ad_id: str) -> dict[str, str]:
    """Resolves a leadgen webhook entry's bare `ad_id` into human-readable Campaign/Ad
    Set/Ad names — best-effort (needs `ads_read` and the token's user to have access to
    the ad account the ad belongs to); an empty dict means "could not be resolved," which
    the caller treats the same as Meta never having supplied the id at all."""
    try:
        body = await graph_get(ad_id, access_token=access_token, fields="name,adset{name},campaign{name}")
    except httpx.HTTPError:
        return {}
    result: dict[str, str] = {}
    if body.get("name"):
        result["ad_name"] = str(body["name"])
    if isinstance(body.get("adset"), dict) and body["adset"].get("name"):
        result["adset_name"] = str(body["adset"]["name"])
    if isinstance(body.get("campaign"), dict) and body["campaign"].get("name"):
        result["campaign_name"] = str(body["campaign"]["name"])
    return result


async def subscribe_page_to_leadgen(*, page_access_token: str, page_id: str) -> bool:
    """Registers this app for `leadgen` webhook notifications on the Page — the API
    equivalent of the manual "Subscribe" click in Meta's Webhooks dashboard product."""
    body = await graph_post(f"{page_id}/subscribed_apps", access_token=page_access_token, subscribed_fields="leadgen", debug_label="page_subscription")
    return bool(body.get("success"))


async def refresh_page_token(*, user_access_token: str, page_id: str) -> str | None:
    """Re-derives a Page Access Token from a freshly-refreshed long-lived User token —
    used by the refresh worker after `exchange_for_long_lived_token`."""
    try:
        body = await graph_get(page_id, access_token=user_access_token, fields="access_token")
    except httpx.HTTPError:
        return None
    token = body.get("access_token")
    return str(token) if token else None
