"""Tests for handlers.py -- connection, sandbox toggle, projects, Quick Add,
tracked keywords + SERP check + history, keyword research, tracked domains +
backlink check + history."""
from __future__ import annotations

import pytest

import handlers as h
from schemas import (
    ConnectDataForSEOParams, SetSandboxModeParams, NoParams,
    CreateProjectParams, ListProjectsParams, ListConnectedSitesParams,
    TrackKeywordParams, ListTrackedKeywordsParams, UntrackKeywordParams,
    CheckSerpRankingParams, GetKeywordHistoryParams,
    GetKeywordVolumeParams, FindRelatedKeywordsParams,
    TrackDomainParams, ListTrackedDomainsParams, UntrackDomainParams,
    GetBacklinkProfileParams, GetDomainHistoryParams,
)


# ── connection / sandbox ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_connect_dataforseo_rejects_empty_credentials(ctx):
    result = await h.connect_dataforseo(ctx, ConnectDataForSEOParams(login="", password=""))
    assert result.error is not None
    assert result.error_code == "DFS_CREDENTIALS_MISSING"


@pytest.mark.asyncio
async def test_connect_dataforseo_validates_before_saving(ctx):
    ctx.http.mock_post("/v3/serp/google/organic/live/advanced", {}, status=401)
    result = await h.connect_dataforseo(ctx, ConnectDataForSEOParams(login="a", password="b"))
    assert result.error is not None
    login = await ctx.secrets.get("dataforseo_login")
    assert login is None


@pytest.mark.asyncio
async def test_connect_dataforseo_saves_on_success(ctx):
    ctx.http.mock_post(
        "/v3/serp/google/organic/live/advanced",
        {"status_code": 20000, "tasks": [{"result": [{"items": []}]}]},
    )
    result = await h.connect_dataforseo(ctx, ConnectDataForSEOParams(login="a@b.com", password="secret"))
    assert result.data.connected is True
    assert await ctx.secrets.get("dataforseo_login") == "a@b.com"


@pytest.mark.asyncio
async def test_disconnect_dataforseo_deletes_credentials(ctx_connected):
    result = await h.disconnect_dataforseo(ctx_connected, NoParams())
    assert result.data.connected is False
    assert await ctx_connected.secrets.get("dataforseo_login") is None


@pytest.mark.asyncio
async def test_get_dataforseo_connection_reports_status(ctx):
    not_connected = await h.get_dataforseo_connection(ctx, NoParams())
    assert not_connected.data.connected is False


@pytest.mark.asyncio
async def test_get_dataforseo_connection_reports_connected(ctx_connected):
    connected = await h.get_dataforseo_connection(ctx_connected, NoParams())
    assert connected.data.connected is True


@pytest.mark.asyncio
async def test_sandbox_mode_defaults_to_true(ctx):
    result = await h.get_sandbox_mode(ctx, NoParams())
    assert result.data.sandbox is True


@pytest.mark.asyncio
async def test_set_sandbox_mode_persists(ctx):
    await h.set_sandbox_mode(ctx, SetSandboxModeParams(sandbox=False))
    result = await h.get_sandbox_mode(ctx, NoParams())
    assert result.data.sandbox is False


# ── projects ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_project_then_list(ctx):
    await h.create_project(ctx, CreateProjectParams(project_id="climtec.md", domain="climtec.md"))
    result = await h.list_projects(ctx, ListProjectsParams())
    assert len(result.data.items) == 1
    assert result.data.items[0].project_id == "climtec.md"


@pytest.mark.asyncio
async def test_create_project_rejects_duplicate(ctx):
    await h.create_project(ctx, CreateProjectParams(project_id="climtec.md", domain="climtec.md"))
    result = await h.create_project(ctx, CreateProjectParams(project_id="climtec.md", domain="climtec.md"))
    assert result.error is not None
    assert result.error_code == "DFS_PROJECT_EXISTS"


@pytest.mark.asyncio
async def test_create_project_defaults_location_language(ctx):
    result = await h.create_project(ctx, CreateProjectParams(project_id="x.md", domain="x.md"))
    assert result.data.default_location_name == "Chisinau,Moldova"
    assert result.data.default_language_code == "ru"


@pytest.mark.asyncio
async def test_list_connected_sites_flags_already_tracked(ctx):
    async def fake_call(app_id, tool, **kwargs):
        return [{"site_id": "climtec-md", "name": "Climtec", "url": "https://climtec.md", "status": "connected"}]
    ctx.extensions.call = fake_call
    await h.create_project(ctx, CreateProjectParams(project_id="climtec.md", domain="climtec.md"))
    result = await h.list_connected_sites(ctx, ListConnectedSitesParams())
    assert len(result.data.items) == 1
    assert result.data.items[0].already_tracked is True


@pytest.mark.asyncio
async def test_list_connected_sites_reports_unreachable_provider(ctx):
    async def fake_call(app_id, tool, **kwargs):
        raise RuntimeError("provider down")
    ctx.extensions.call = fake_call
    result = await h.list_connected_sites(ctx, ListConnectedSitesParams())
    assert len(result.data.items) == 0
    assert "unreachable" in result.summary


# ── tracked keywords ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_track_keyword_requires_existing_project(ctx):
    result = await h.track_keyword(ctx, TrackKeywordParams(project_id="nope", keyword="aer conditionat"))
    assert result.error is not None
    assert result.error_code == "DFS_PROJECT_NOT_FOUND"


@pytest.mark.asyncio
async def test_track_keyword_inherits_project_defaults(ctx):
    await h.create_project(ctx, CreateProjectParams(
        project_id="climtec.md", domain="climtec.md",
        default_location_name="Bucharest,Romania", default_language_code="ro",
    ))
    result = await h.track_keyword(ctx, TrackKeywordParams(project_id="climtec.md", keyword="aer conditionat"))
    assert result.data.location_name == "Bucharest,Romania"
    assert result.data.language_code == "ro"


@pytest.mark.asyncio
async def test_track_keyword_override_beats_project_default(ctx):
    await h.create_project(ctx, CreateProjectParams(project_id="climtec.md", domain="climtec.md"))
    result = await h.track_keyword(ctx, TrackKeywordParams(
        project_id="climtec.md", keyword="aer conditionat", location_name="London,England,United Kingdom",
    ))
    assert result.data.location_name == "London,England,United Kingdom"


@pytest.mark.asyncio
async def test_list_tracked_keywords_filters_by_project(ctx):
    await h.create_project(ctx, CreateProjectParams(project_id="a.md", domain="a.md"))
    await h.create_project(ctx, CreateProjectParams(project_id="b.md", domain="b.md"))
    await h.track_keyword(ctx, TrackKeywordParams(project_id="a.md", keyword="kw1"))
    await h.track_keyword(ctx, TrackKeywordParams(project_id="b.md", keyword="kw2"))
    result = await h.list_tracked_keywords(ctx, ListTrackedKeywordsParams(project_id="a.md"))
    assert len(result.data.items) == 1
    assert result.data.items[0].keyword == "kw1"


@pytest.mark.asyncio
async def test_untrack_keyword_removes_it(ctx):
    await h.create_project(ctx, CreateProjectParams(project_id="a.md", domain="a.md"))
    created = await h.track_keyword(ctx, TrackKeywordParams(project_id="a.md", keyword="kw1"))
    result = await h.untrack_keyword(ctx, UntrackKeywordParams(keyword_id=created.data.id))
    assert result.data.removed is True
    remaining = await h.list_tracked_keywords(ctx, ListTrackedKeywordsParams())
    assert len(remaining.data.items) == 0


@pytest.mark.asyncio
async def test_check_serp_ranking_not_found_case(ctx_connected):
    await h.create_project(ctx_connected, CreateProjectParams(project_id="climtec.md", domain="climtec.md"))
    created = await h.track_keyword(ctx_connected, TrackKeywordParams(project_id="climtec.md", keyword="aer conditionat"))
    ctx_connected.http.mock_post(
        "/v3/serp/google/organic/live/advanced",
        {"status_code": 20000, "tasks": [{"result": [{"items": [
            {"type": "organic", "rank_absolute": 1, "url": "https://other.com/x", "title": "Other"},
        ]}]}]},
    )
    result = await h.check_serp_ranking(ctx_connected, CheckSerpRankingParams(keyword_id=created.data.id))
    assert result.data.found is False
    assert result.data.position == 0


@pytest.mark.asyncio
async def test_check_serp_ranking_found_case_records_history(ctx_connected):
    await h.create_project(ctx_connected, CreateProjectParams(project_id="climtec.md", domain="climtec.md"))
    created = await h.track_keyword(ctx_connected, TrackKeywordParams(project_id="climtec.md", keyword="aer conditionat"))
    ctx_connected.http.mock_post(
        "/v3/serp/google/organic/live/advanced",
        {"status_code": 20000, "tasks": [{"result": [{"items": [
            {"type": "organic", "rank_absolute": 4, "url": "https://climtec.md/page", "title": "Climtec"},
        ]}]}]},
    )
    result = await h.check_serp_ranking(ctx_connected, CheckSerpRankingParams(keyword_id=created.data.id))
    assert result.data.found is True
    assert result.data.position == 4

    history = await h.get_keyword_history(ctx_connected, GetKeywordHistoryParams(keyword_id=created.data.id))
    assert len(history.data.items) == 1
    assert history.data.items[0].position == 4


@pytest.mark.asyncio
async def test_check_serp_ranking_requires_connection(ctx):
    await h.create_project(ctx, CreateProjectParams(project_id="climtec.md", domain="climtec.md"))
    created = await h.track_keyword(ctx, TrackKeywordParams(project_id="climtec.md", keyword="kw"))
    result = await h.check_serp_ranking(ctx, CheckSerpRankingParams(keyword_id=created.data.id))
    assert result.error is not None
    assert result.error_code == "DFS_NOT_CONNECTED"


@pytest.mark.asyncio
async def test_check_serp_ranking_missing_keyword(ctx_connected):
    result = await h.check_serp_ranking(ctx_connected, CheckSerpRankingParams(keyword_id="missing"))
    assert result.error is not None
    assert result.error_code == "DFS_KEYWORD_NOT_FOUND"


# ── keyword research ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_keyword_volume_requires_connection(ctx):
    result = await h.get_keyword_volume(ctx, GetKeywordVolumeParams(keywords=["kw"]))
    assert result.error is not None
    assert result.error_code == "DFS_NOT_CONNECTED"


@pytest.mark.asyncio
async def test_get_keyword_volume_uses_project_defaults(ctx_connected):
    await h.create_project(ctx_connected, CreateProjectParams(
        project_id="climtec.md", domain="climtec.md",
        default_location_name="Bucharest,Romania", default_language_code="ro",
    ))
    captured = {}

    async def fake_call(ctx, login, password, *, sandbox, keywords, location_name, language_code):
        captured["location_name"] = location_name
        captured["language_code"] = language_code
        return [{"keyword": "kw", "search_volume": 500, "cpc": 0.3, "competition": 0.2}]

    import dfs_client
    orig = dfs_client.keywords_search_volume_live
    dfs_client.keywords_search_volume_live = fake_call
    try:
        result = await h.get_keyword_volume(ctx_connected, GetKeywordVolumeParams(project_id="climtec.md", keywords=["kw"]))
    finally:
        dfs_client.keywords_search_volume_live = orig
    assert captured["location_name"] == "Bucharest,Romania"
    assert captured["language_code"] == "ro"
    assert result.data.items[0].search_volume == 500


@pytest.mark.asyncio
async def test_find_related_keywords_requires_connection(ctx):
    result = await h.find_related_keywords(ctx, FindRelatedKeywordsParams(seed_keyword="kw"))
    assert result.error is not None
    assert result.error_code == "DFS_NOT_CONNECTED"


@pytest.mark.asyncio
async def test_find_related_keywords_parses_nested_keyword_data(ctx_connected):
    ctx_connected.http.mock_post(
        "/v3/dataforseo_labs/google/related_keywords/live",
        {"status_code": 20000, "tasks": [{"result": [{"items": [
            {"keyword_data": {"keyword": "climatizare birou", "keyword_info": {
                "search_volume": 90, "cpc": 0.4, "competition": 0.6,
            }}},
        ]}]}]},
    )
    result = await h.find_related_keywords(ctx_connected, FindRelatedKeywordsParams(seed_keyword="aer conditionat"))
    assert len(result.data.items) == 1
    assert result.data.items[0].keyword == "climatizare birou"
    assert result.data.items[0].search_volume == 90


# ── tracked domains ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_track_domain_requires_existing_project(ctx):
    result = await h.track_domain(ctx, TrackDomainParams(project_id="nope", domain="climtec.md"))
    assert result.error is not None
    assert result.error_code == "DFS_PROJECT_NOT_FOUND"


@pytest.mark.asyncio
async def test_track_domain_then_list_and_untrack(ctx):
    await h.create_project(ctx, CreateProjectParams(project_id="climtec.md", domain="climtec.md"))
    created = await h.track_domain(ctx, TrackDomainParams(project_id="climtec.md", domain="climtec.md"))
    listed = await h.list_tracked_domains(ctx, ListTrackedDomainsParams())
    assert len(listed.data.items) == 1

    untracked = await h.untrack_domain(ctx, UntrackDomainParams(domain_id=created.data.id))
    assert untracked.data.removed is True
    listed_again = await h.list_tracked_domains(ctx, ListTrackedDomainsParams())
    assert len(listed_again.data.items) == 0


@pytest.mark.asyncio
async def test_get_backlink_profile_records_history(ctx_connected):
    await h.create_project(ctx_connected, CreateProjectParams(project_id="climtec.md", domain="climtec.md"))
    created = await h.track_domain(ctx_connected, TrackDomainParams(project_id="climtec.md", domain="climtec.md"))
    ctx_connected.http.mock_post(
        "/v3/backlinks/summary/live",
        {"status_code": 20000, "tasks": [{"result": [
            {"target": "climtec.md", "backlinks": 340, "referring_domains": 42, "rank": 210},
        ]}]},
    )
    result = await h.get_backlink_profile(ctx_connected, GetBacklinkProfileParams(domain_id=created.data.id))
    assert result.data.backlinks == 340
    assert result.data.rank == 210

    history = await h.get_domain_history(ctx_connected, GetDomainHistoryParams(domain_id=created.data.id))
    assert len(history.data.items) == 1
    assert history.data.items[0].backlinks == 340


@pytest.mark.asyncio
async def test_get_backlink_profile_missing_domain(ctx_connected):
    result = await h.get_backlink_profile(ctx_connected, GetBacklinkProfileParams(domain_id="missing"))
    assert result.error is not None
    assert result.error_code == "DFS_DOMAIN_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_backlink_profile_requires_connection(ctx):
    await h.create_project(ctx, CreateProjectParams(project_id="climtec.md", domain="climtec.md"))
    created = await h.track_domain(ctx, TrackDomainParams(project_id="climtec.md", domain="climtec.md"))
    result = await h.get_backlink_profile(ctx, GetBacklinkProfileParams(domain_id=created.data.id))
    assert result.error is not None
    assert result.error_code == "DFS_NOT_CONNECTED"
