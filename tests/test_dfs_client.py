"""Tests for dfs_client -- auth, base URL switch, response parsing."""
from __future__ import annotations

import pytest

import dfs_client as dfs


def test_base_url_switches_on_sandbox_flag():
    assert dfs.base_url(sandbox=True) == dfs.SANDBOX_BASE_URL
    assert dfs.base_url(sandbox=False) == dfs.LIVE_BASE_URL


@pytest.mark.asyncio
async def test_validate_credentials_raises_on_http_error(ctx):
    ctx.http.mock_post("/v3/serp/google/organic/live/advanced", {}, status=401)
    with pytest.raises(dfs.ProviderError) as exc:
        await dfs.validate_credentials(ctx, "bad", "creds", sandbox=True)
    assert exc.value.code == "DFS_HTTP_ERROR"


@pytest.mark.asyncio
async def test_validate_credentials_raises_on_api_status_code(ctx):
    ctx.http.mock_post(
        "/v3/serp/google/organic/live/advanced",
        {"status_code": 40100, "status_message": "Auth error", "tasks": []},
        status=200,
    )
    with pytest.raises(dfs.ProviderError) as exc:
        await dfs.validate_credentials(ctx, "bad", "creds", sandbox=True)
    assert exc.value.code == "DFS_API_ERROR"


@pytest.mark.asyncio
async def test_validate_credentials_passes_on_20000(ctx):
    ctx.http.mock_post(
        "/v3/serp/google/organic/live/advanced",
        {"status_code": 20000, "status_message": "Ok", "tasks": [{"result": [{"items": []}]}]},
        status=200,
    )
    await dfs.validate_credentials(ctx, "good", "creds", sandbox=True)  # no raise


@pytest.mark.asyncio
async def test_serp_google_organic_live_returns_items(ctx):
    ctx.http.mock_post(
        "/v3/serp/google/organic/live/advanced",
        {"status_code": 20000, "tasks": [{"result": [{"items": [
            {"type": "organic", "rank_absolute": 3, "url": "https://climtec.md/page", "title": "Climtec"},
        ]}]}]},
    )
    result = await dfs.serp_google_organic_live(
        ctx, "l", "p", sandbox=True, keyword="aer conditionat",
        location_name="Chisinau,Moldova", language_code="ru",
    )
    assert result["items"][0]["rank_absolute"] == 3


@pytest.mark.asyncio
async def test_serp_google_organic_live_empty_result(ctx):
    ctx.http.mock_post("/v3/serp/google/organic/live/advanced", {"status_code": 20000, "tasks": []})
    result = await dfs.serp_google_organic_live(
        ctx, "l", "p", sandbox=True, keyword="x", location_name="y", language_code="ru",
    )
    assert result == {"items": []}


def test_find_domain_rank_matches_bare_host():
    items = [
        {"type": "organic", "rank_absolute": 1, "url": "https://other.com/x", "title": "Other"},
        {"type": "organic", "rank_absolute": 5, "url": "https://www.climtec.md/y", "title": "Climtec"},
    ]
    match = dfs.find_domain_rank(items, "climtec.md")
    assert match["position"] == 5
    assert match["url"] == "https://www.climtec.md/y"


def test_find_domain_rank_no_match_returns_none():
    items = [{"type": "organic", "rank_absolute": 1, "url": "https://other.com/x"}]
    assert dfs.find_domain_rank(items, "climtec.md") is None


def test_find_domain_rank_skips_non_organic_items():
    items = [{"type": "featured_snippet", "url": "https://climtec.md/"}]
    assert dfs.find_domain_rank(items, "climtec.md") is None


@pytest.mark.asyncio
async def test_keywords_search_volume_live_returns_result_list(ctx):
    ctx.http.mock_post(
        "/v3/keywords_data/google_ads/search_volume/live",
        {"status_code": 20000, "tasks": [{"result": [
            {"keyword": "aer conditionat", "search_volume": 1200, "cpc": 0.5, "competition": 0.3},
        ]}]},
    )
    result = await dfs.keywords_search_volume_live(
        ctx, "l", "p", sandbox=True, keywords=["aer conditionat"],
        location_name="Chisinau,Moldova", language_code="ru",
    )
    assert result[0]["search_volume"] == 1200


@pytest.mark.asyncio
async def test_labs_related_keywords_live_returns_items(ctx):
    ctx.http.mock_post(
        "/v3/dataforseo_labs/google/related_keywords/live",
        {"status_code": 20000, "tasks": [{"result": [{"items": [
            {"keyword_data": {"keyword": "climatizare birou"}},
        ]}]}]},
    )
    result = await dfs.labs_related_keywords_live(
        ctx, "l", "p", sandbox=True, seed_keyword="aer conditionat",
        location_name="Chisinau,Moldova", language_code="ru",
    )
    assert result[0]["keyword_data"]["keyword"] == "climatizare birou"


@pytest.mark.asyncio
async def test_backlinks_summary_live_returns_result_dict(ctx):
    ctx.http.mock_post(
        "/v3/backlinks/summary/live",
        {"status_code": 20000, "tasks": [{"result": [
            {"target": "climtec.md", "backlinks": 340, "referring_domains": 42, "rank": 210},
        ]}]},
    )
    result = await dfs.backlinks_summary_live(ctx, "l", "p", sandbox=True, target="climtec.md")
    assert result["backlinks"] == 340


@pytest.mark.asyncio
async def test_backlinks_summary_live_empty_result(ctx):
    ctx.http.mock_post("/v3/backlinks/summary/live", {"status_code": 20000, "tasks": []})
    result = await dfs.backlinks_summary_live(ctx, "l", "p", sandbox=True, target="climtec.md")
    assert result == {}
