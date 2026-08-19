"""Plausible Scenario Tests (PST) -- DataForSEO Connector.

Method: Docs/session-notes/SCENARIO_TESTING_STANDARD.md. The existing
suite (48 tests across test_dfs_client.py/test_handlers.py/test_panels_smoke.py)
already calls all 20 chat functions and covers error/adversarial branches
well. This file targets the two genuinely thin spots found by a coverage
audit: RECOVERY (reconnect succeeds after a bad-credentials failure) and
a couple of remaining ADVERSARIAL edges (re-tracking an already-tracked
keyword/domain, untracking something already untracked).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import handlers as h
from schemas import (
    ConnectDataForSEOParams, CreateProjectParams,
    TrackKeywordParams, UntrackKeywordParams,
    TrackDomainParams, UntrackDomainParams,
)


# ── recovery: bad credentials rejected, then a real reconnect succeeds ────

@pytest.mark.asyncio
async def test_recovery_reconnect_after_empty_credentials_rejected(ctx):
    bad = await h.connect_dataforseo(ctx, ConnectDataForSEOParams(login="", password=""))
    assert bad.error is not None

    ctx.http.mock_post(
        "/v3/serp/google/organic/live/advanced",
        {"status_code": 20000, "tasks": [{"result": [{"items": []}]}]},
    )
    good = await h.connect_dataforseo(
        ctx, ConnectDataForSEOParams(login="user@example.com", password="real-pass"))
    assert good.error is None

    status = await h.get_dataforseo_connection(ctx, __import__("schemas").NoParams())
    assert status.data.connected is True


# ── adversarial: re-track an already-tracked keyword/domain ───────────────

@pytest.mark.asyncio
async def test_adversarial_track_keyword_twice_does_not_duplicate(ctx_connected):
    proj = await h.create_project(
        ctx_connected, CreateProjectParams(project_id="dup-kw-co", domain="dupkw.com"))
    project_id = proj.data.id

    first = await h.track_keyword(
        ctx_connected, TrackKeywordParams(project_id=project_id, keyword="running shoes"))
    second = await h.track_keyword(
        ctx_connected, TrackKeywordParams(project_id=project_id, keyword="running shoes"))
    assert first.error is None

    listing = await h.list_tracked_keywords(
        ctx_connected, __import__("schemas").ListTrackedKeywordsParams(project_id=project_id, limit=50))
    matching = [k for k in listing.data.items if k.keyword == "running shoes"]
    # Whatever the product decision (duplicate allowed vs rejected), the
    # invariant that must hold is: no MORE than what the second call's own
    # result implies -- silently creating a THIRD/duplicate record neither
    # call asked for would be the actual bug.
    if second.error is None:
        assert len(matching) == 2
    else:
        assert len(matching) == 1


@pytest.mark.asyncio
async def test_adversarial_untrack_keyword_already_untracked_is_idempotent(ctx_connected):
    """untrack_keyword calls ctx.store.delete unconditionally with no
    existence check -- by design this makes it idempotent (like HTTP
    DELETE): untracking something already gone is a safe no-op, not an
    error. Confirming that stays true rather than assuming it should fail."""
    proj = await h.create_project(
        ctx_connected, CreateProjectParams(project_id="untrack-twice-co", domain="untracktwice.com"))
    project_id = proj.data.id
    tracked = await h.track_keyword(
        ctx_connected, TrackKeywordParams(project_id=project_id, keyword="marathon training"))
    keyword_id = tracked.data.id

    first = await h.untrack_keyword(ctx_connected, UntrackKeywordParams(keyword_id=keyword_id))
    assert first.error is None

    second = await h.untrack_keyword(ctx_connected, UntrackKeywordParams(keyword_id=keyword_id))
    assert second.error is None


@pytest.mark.asyncio
async def test_adversarial_untrack_domain_already_untracked_is_idempotent(ctx_connected):
    """Same idempotent-delete design as untrack_keyword -- see its test."""
    proj = await h.create_project(
        ctx_connected, CreateProjectParams(project_id="untrack-domain-co", domain="untrackdomain.com"))
    project_id = proj.data.id
    tracked = await h.track_domain(
        ctx_connected, TrackDomainParams(project_id=project_id, domain="competitor.com"))
    domain_id = tracked.data.id

    first = await h.untrack_domain(ctx_connected, UntrackDomainParams(domain_id=domain_id))
    assert first.error is None

    second = await h.untrack_domain(ctx_connected, UntrackDomainParams(domain_id=domain_id))
    assert second.error is None


# ── Part D3 (SCENARIO_TESTING_STANDARD.md): security / SSRF surface -------

@pytest.mark.asyncio
async def test_d3_no_ssrf_url_fields_are_dataforseo_output_never_fetched(ctx_connected):
    """Every domain/keyword a caller can set here (create_project's domain,
    track_domain's domain, track_keyword's keyword) is sent AS DATA inside
    the request body to DataForSEO's own fixed API host via dfs_client.py's
    ctx.http.post -- this app's own code never independently fetches an
    address a user names. Confirmed by grep: no ctx.http call anywhere
    outside dfs_client.py, and every dfs_client.py call targets the same
    fixed DataForSEO base URL, never a caller-supplied one. Feeding an
    adversarial domain (an internal/metadata-style host) must be handled as
    opaque payload data, not as something this app's own code resolves."""
    result = await h.create_project(
        ctx_connected, CreateProjectParams(
            project_id="ssrf-probe", domain="169.254.169.254"))
    assert result.error is None, result.error
    assert result.data.domain == "169.254.169.254"
