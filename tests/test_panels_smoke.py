"""Smoke tests -- every panel renders without raising, in both the empty
state and after creating a project/keyword/domain. Mirrors the shape of
Content Strategy Hub's panel smoke tests (render, don't assert markup)."""
from __future__ import annotations

import pytest

import panels
import handlers as h
from schemas import CreateProjectParams, TrackKeywordParams, TrackDomainParams


@pytest.mark.asyncio
async def test_dfs_projects_panel_renders_empty(ctx):
    result = await panels.dfs_projects_panel(ctx)
    assert result is not None


@pytest.mark.asyncio
async def test_dfs_tracked_panel_renders_empty(ctx):
    result = await panels.dfs_tracked_panel(ctx)
    assert result is not None


@pytest.mark.asyncio
async def test_dfs_detail_panel_renders_empty(ctx):
    result = await panels.dfs_detail_panel(ctx)
    assert result is not None


@pytest.mark.asyncio
async def test_panels_render_with_data(ctx):
    await h.create_project(ctx, CreateProjectParams(project_id="climtec.md", domain="climtec.md"))
    kw = await h.track_keyword(ctx, TrackKeywordParams(project_id="climtec.md", keyword="aer conditionat"))
    dom = await h.track_domain(ctx, TrackDomainParams(project_id="climtec.md", domain="climtec.md"))

    projects_view = await panels.dfs_projects_panel(ctx)
    assert projects_view is not None

    tracked_view = await panels.dfs_tracked_panel(ctx, project_id="climtec.md")
    assert tracked_view is not None

    kw_detail = await panels.dfs_detail_panel(ctx, kind="keyword", record_id=kw.data.id)
    assert kw_detail is not None

    dom_detail = await panels.dfs_detail_panel(ctx, kind="domain", record_id=dom.data.id)
    assert dom_detail is not None
