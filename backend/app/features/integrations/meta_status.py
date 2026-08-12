"""Module 9A — Meta connection live-status aggregation (Connection Health panel).

On-demand only, never cached or polled — this is an admin diagnostic view, not a sync job.
Every call is bounded to the first page of results (no recursive pagination through Graph's
cursor-based paging), keeping this a cheap, occasional read rather than something that could
balloon into hundreds of requests for a large Business Manager account. A `None` return means
"could not be determined" (e.g. an invalid token, or a transient Graph failure even after
`oauth.graph_get`'s own retry/backoff was exhausted) — distinct from a genuine `0`.
"""

from typing import Any

import httpx

from app.features.integrations import oauth as oauth_client

_MAX_PAGES_FOR_LEAD_FORMS = 10


async def _graph_get(path: str, access_token: str, **params: Any) -> dict[str, Any] | None:
    # Delegates to the shared, retrying Graph client (oauth.py) — this module's own
    # contract of "None means couldn't determine it, never raise" is preserved here by
    # catching the one exception type `graph_get` can raise.
    try:
        return await oauth_client.graph_get(path, access_token=access_token, **params)
    except httpx.HTTPError:
        return None


async def fetch_ad_accounts_count(access_token: str) -> int | None:
    body = await _graph_get("me/adaccounts", access_token, fields="id")
    return len(body.get("data", [])) if body is not None else None


async def fetch_pages(access_token: str) -> list[dict[str, str]] | None:
    body = await _graph_get("me/accounts", access_token, fields="id,name")
    return body.get("data", []) if body is not None else None


async def fetch_lead_forms_count(access_token: str, page_ids: list[str]) -> int | None:
    if not page_ids:
        return 0
    total = 0
    any_success = False
    for page_id in page_ids[:_MAX_PAGES_FOR_LEAD_FORMS]:
        body = await _graph_get(f"{page_id}/leadgen_forms", access_token, fields="id")
        if body is not None:
            any_success = True
            total += len(body.get("data", []))
    return total if any_success else None
