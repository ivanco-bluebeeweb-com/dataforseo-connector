"""DataForSEO API client -- auth, sandbox/live base URL switch, and thin
wrappers around the four API families we use: SERP, Keywords Data,
DataForSEO Labs, Backlinks.

WHY LIVE ENDPOINTS, NOT task_post/task_get, FOR MOST CALLS.

DataForSEO offers two shapes per data family: async task_post -> task_get
(cheaper, can take minutes) and synchronous "Live" endpoints (costs the
same or a bit more, but the whole request/response happens in one HTTP
call, no polling). Every operation this connector exposes is expected to
finish inside a single chat-turn/panel-click response, so we use the Live
endpoints everywhere they exist -- there is no user-visible benefit to
polling here the way there was for Magnific's genuinely slow image jobs.
If a genuinely bulk operation is added later (checking hundreds of
keywords at once) task_post/task_get becomes worth adding as a second path.

WHY SANDBOX AND LIVE ARE JUST A BASE_URL SWITCH.

Per DataForSEO's own "Sandbox Best Practices" doc, sandbox.dataforseo.com
mirrors the exact same paths and request/response shapes as
api.dataforseo.com -- it just returns generic/test data and never bills the
account. So the entire sandbox/live toggle is exactly one string swap, not
a separate code path -- this is the same shape as Magnific's BASE_URL
constant, just resolved per-call instead of hardcoded.

WHY BASIC AUTH IS BUILT HERE, NOT LEFT TO ctx.http.

DataForSEO authenticates with plain HTTP Basic Auth (login:password,
base64-encoded in the Authorization header) -- not an API-key header like
Magnific's `x-magnific-api-key`. httpx/ctx.http do not auto-attach Basic
Auth from separate fields, so `_headers()` builds it explicitly with
`base64.b64encode` rather than assuming a client does it for us.
"""
from __future__ import annotations

import base64

LIVE_BASE_URL = "https://api.dataforseo.com"
SANDBOX_BASE_URL = "https://sandbox.dataforseo.com"


class ProviderError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


def base_url(sandbox: bool) -> str:
    return SANDBOX_BASE_URL if sandbox else LIVE_BASE_URL


def _headers(login: str, password: str) -> dict:
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def _check_status(resp, action: str) -> dict:
    """DataForSEO returns HTTP 200 even for auth/quota failures -- the real
    outcome is in the JSON body's own status_code (20000 = ok). A wrong
    login/password round-trips as a normal-looking 200 with status_code
    40100 ("Auth error") buried inside, so checking resp.status_code alone
    would silently treat a bad credential as success."""
    if resp.status_code >= 400:
        raise ProviderError(
            f"DataForSEO {action} failed: HTTP {resp.status_code}", "DFS_HTTP_ERROR",
        )
    body = resp.json()
    status_code = body.get("status_code")
    if status_code is not None and status_code != 20000:
        raise ProviderError(
            f"DataForSEO {action} failed: {body.get('status_message', 'unknown error')} "
            f"(status_code {status_code})",
            "DFS_API_ERROR",
        )
    return body


async def validate_credentials(ctx, login: str, password: str, *, sandbox: bool) -> None:
    """Verify login/password work without generating billable load -- calls
    the account-info-free 'user_data' appendix endpoint some SDKs use for
    exactly this, but that endpoint isn't guaranteed sandboxed cheaply, so
    validation instead does the cheapest real Live call in the catalogue:
    a 1-result Google Organic SERP Live Advanced lookup. It is small and
    ~free, and its 20000/40100 status_code makes a bad credential
    unambiguous either way."""
    resp = await ctx.http.post(
        f"{base_url(sandbox)}/v3/serp/google/organic/live/advanced",
        headers=_headers(login, password),
        json=[{"keyword": "test", "location_name": "United States", "language_code": "en", "depth": 1}],
    )
    _check_status(resp, "credential check")


# ──────────────────────────────────────────────────────────────────────────
# SERP -- Google Organic Live Advanced. One call = current top-N results
# for one keyword/location/language, used both for rank-checking a tracked
# keyword (find our own domain in the results) and for showing "who else
# ranks here" competitor context.
# ──────────────────────────────────────────────────────────────────────────


async def serp_google_organic_live(
    ctx, login: str, password: str, *, sandbox: bool,
    keyword: str, location_name: str, language_code: str, depth: int = 20,
) -> dict:
    resp = await ctx.http.post(
        f"{base_url(sandbox)}/v3/serp/google/organic/live/advanced",
        headers=_headers(login, password),
        json=[{
            "keyword": keyword, "location_name": location_name,
            "language_code": language_code, "depth": depth,
        }],
    )
    body = _check_status(resp, "SERP lookup")
    tasks = body.get("tasks") or []
    if not tasks or not tasks[0].get("result"):
        return {"items": []}
    result = tasks[0]["result"][0]
    return {"items": result.get("items") or []}


def find_domain_rank(serp_items: list[dict], domain: str) -> dict | None:
    """Scan SERP items for the first organic result matching `domain`
    (bare-host compare, www-insensitive). Returns {"position", "url",
    "title"} or None if the domain isn't in the fetched depth."""
    bare = domain.lower().removeprefix("www.")
    for item in serp_items:
        if item.get("type") != "organic":
            continue
        url = item.get("url") or item.get("domain") or ""
        host = url.split("://", 1)[-1].split("/", 1)[0].lower().removeprefix("www.")
        if host == bare or host.endswith("." + bare):
            return {
                "position": item.get("rank_absolute") or item.get("rank_group"),
                "url": url,
                "title": item.get("title", ""),
            }
    return None


# ──────────────────────────────────────────────────────────────────────────
# Keywords Data -- Google Ads search volume (+ CPC, competition).
# ──────────────────────────────────────────────────────────────────────────


async def keywords_search_volume_live(
    ctx, login: str, password: str, *, sandbox: bool,
    keywords: list[str], location_name: str, language_code: str,
) -> list[dict]:
    resp = await ctx.http.post(
        f"{base_url(sandbox)}/v3/keywords_data/google_ads/search_volume/live",
        headers=_headers(login, password),
        json=[{
            "keywords": keywords[:1000], "location_name": location_name,
            "language_code": language_code,
        }],
    )
    body = _check_status(resp, "keyword search volume")
    tasks = body.get("tasks") or []
    if not tasks or not tasks[0].get("result"):
        return []
    return tasks[0]["result"] or []


# ──────────────────────────────────────────────────────────────────────────
# DataForSEO Labs -- related keyword ideas (search-suggestion graph).
# ──────────────────────────────────────────────────────────────────────────


async def labs_related_keywords_live(
    ctx, login: str, password: str, *, sandbox: bool,
    seed_keyword: str, location_name: str, language_code: str, depth: int = 2, limit: int = 50,
) -> list[dict]:
    resp = await ctx.http.post(
        f"{base_url(sandbox)}/v3/dataforseo_labs/google/related_keywords/live",
        headers=_headers(login, password),
        json=[{
            "keyword": seed_keyword, "location_name": location_name,
            "language_code": language_code, "depth": depth, "limit": limit,
        }],
    )
    body = _check_status(resp, "related keywords lookup")
    tasks = body.get("tasks") or []
    if not tasks or not tasks[0].get("result"):
        return []
    result = tasks[0]["result"][0] or {}
    return result.get("items") or []


# ──────────────────────────────────────────────────────────────────────────
# Backlinks -- domain-level summary (count, referring domains, rank).
# ──────────────────────────────────────────────────────────────────────────


async def backlinks_summary_live(
    ctx, login: str, password: str, *, sandbox: bool, target: str,
) -> dict:
    resp = await ctx.http.post(
        f"{base_url(sandbox)}/v3/backlinks/summary/live",
        headers=_headers(login, password),
        json=[{"target": target, "internal_list_limit": 10}],
    )
    body = _check_status(resp, "backlink summary")
    tasks = body.get("tasks") or []
    if not tasks or not tasks[0].get("result"):
        return {}
    return tasks[0]["result"][0] or {}
