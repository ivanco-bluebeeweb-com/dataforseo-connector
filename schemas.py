"""Pydantic params models + SDL entity contracts for DataForSEO Connector.

All params models are module-scope (V17 federal invariant).
Entities/EntityLists follow the read-tool contract: a single record is an
sdl.Entity subclass, a list result is sdl.EntityList[T] -- never a bare dict.
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from imperal_sdk import sdl


class NoParams(BaseModel):
    """Explicit empty params model -- V17 disallows untyped handlers."""
    pass


class UntrackResult(sdl.Entity):
    """Result of untrack_keyword/untrack_domain -- confirms the id removed
    from active tracking; history snapshots are kept."""
    id: str = ""
    title: str = ""
    removed: bool = True


# ──────────────────────────────────────────────────────────────────────────
# Connection / account management.
# ──────────────────────────────────────────────────────────────────────────


class ConnectDataForSEOParams(BaseModel):
    login: str = Field("", description="DataForSEO API login (from your DataForSEO dashboard, usually your account email)")
    password: str = Field("", description="DataForSEO API password (from your DataForSEO dashboard -- a separate password from your dashboard login)")


class ProviderConnection(sdl.Entity):
    id: str = ""
    title: str = ""
    connected: bool = False
    detail: str = ""


class SetSandboxModeParams(BaseModel):
    sandbox: bool = Field(
        ...,
        description="True = use DataForSEO's free Sandbox (test data, no charges). "
                    "False = Live (real data, real cost).",
    )


class SandboxModeStatus(sdl.Entity):
    id: str = ""
    title: str = ""
    sandbox: bool = True


# ──────────────────────────────────────────────────────────────────────────
# Projects -- the "site/domain I'm tracking in DataForSEO" concept.
#
# Same shape as Content Strategy Hub's SiteProfile + Quick Add pattern:
# a project can be created manually (any domain, even one you don't own --
# useful for tracking a competitor) OR one-click from a connected site
# provider (WordPress Hub today). Kept as this app's OWN entity rather than
# reusing Content Strategy Hub's SiteProfile, because a DataForSEO project
# needs fields (default location/language for SERP) that have no meaning
# in Content Strategy Hub, and this connector must work standalone even if
# Content Strategy Hub is never installed.
# ──────────────────────────────────────────────────────────────────────────


class DFSProject(sdl.Entity):
    """One tracked domain/project in DataForSEO Connector."""
    id: str = ""
    title: str = ""
    project_id: str = ""  # stable business key, e.g. 'climtec.md'
    domain: str = ""
    brand_name: str = ""
    default_location_name: str = "Chisinau,Moldova"
    default_language_code: str = "ru"
    is_own_site: bool = True  # False = tracking a competitor's domain, not your own
    created_at: str = ""


class DFSProjectList(sdl.EntityList[DFSProject]):
    pass


class CreateProjectParams(BaseModel):
    project_id: str = Field(..., description="Unique project identifier, e.g. 'climtec.md'")
    domain: str = Field(..., description="Domain, e.g. 'climtec.md'")
    brand_name: str = Field("", description="Brand/company name")
    default_location_name: str = Field(
        "Chisinau,Moldova",
        description="Default DataForSEO location name for SERP/keyword lookups, "
                     "e.g. 'Chisinau,Moldova' or 'London,England,United Kingdom'",
    )
    default_language_code: str = Field("ru", description="Default two-letter language code, e.g. 'ru', 'ro', 'en'")
    is_own_site: bool = Field(True, description="False if this project tracks a competitor's domain, not your own")


class ListProjectsParams(BaseModel):
    limit: int = Field(50, description="Max items to return (1-100)")


# ──────────────────────────────────────────────────────────────────────────
# Quick Add -- read connected sites from other site-provider extensions
# (WordPress Hub today), same IPC contract Content Strategy Hub already
# uses (list_connected_sites via ctx.extensions.call), so a project can be
# started in one click without retyping the domain.
# ──────────────────────────────────────────────────────────────────────────


class ConnectedSite(sdl.Entity):
    """One site read from a site-provider extension -- the raw material
    behind the Quick Add list."""
    id: str = ""
    title: str = ""
    site_id: str = ""
    name: str = ""
    url: str = ""
    status: str = ""
    provider: str = ""
    already_tracked: bool = False


class ConnectedSiteList(sdl.EntityList[ConnectedSite]):
    pass


class ListConnectedSitesParams(BaseModel):
    limit: int = Field(50, description="Max items to return (1-100)")


# ──────────────────────────────────────────────────────────────────────────
# Tracked keywords -- SERP position tracking, with history snapshots.
# ──────────────────────────────────────────────────────────────────────────


class TrackedKeyword(sdl.Entity):
    """One keyword being tracked for SERP position within a project."""
    id: str = ""
    title: str = ""
    project_id: str = ""
    keyword: str = ""
    location_name: str = ""
    language_code: str = ""
    search_engine: str = "google"
    latest_position: int = 0  # 0 = not ranking in top results checked
    latest_url: str = ""
    latest_checked_at: str = ""
    search_volume: int = 0
    cpc: float = 0.0
    competition: float = 0.0
    created_at: str = ""


class TrackedKeywordList(sdl.EntityList[TrackedKeyword]):
    pass


class TrackKeywordParams(BaseModel):
    project_id: str = Field(..., description="Project id from list_projects")
    keyword: str = Field(..., description="Keyword phrase to track")
    location_name: str = Field("", description="Override the project's default location name; empty = use project default")
    language_code: str = Field("", description="Override the project's default language code; empty = use project default")
    search_engine: str = Field("google", description="Search engine: currently google only")


class ListTrackedKeywordsParams(BaseModel):
    project_id: str = Field("", description="Filter by project. Empty = all projects.")
    limit: int = Field(100, description="Max items to return (1-200)")


class UntrackKeywordParams(BaseModel):
    keyword_id: str = Field(..., description="Tracked keyword id from list_tracked_keywords")


class CheckSerpRankingParams(BaseModel):
    keyword_id: str = Field(..., description="Tracked keyword id from list_tracked_keywords -- runs a fresh SERP check and records a new history snapshot")
    depth: int = Field(20, description="How many top organic results to scan for the project's domain (1-100)")


class SerpCompetitorItem(sdl.Entity):
    """One competing organic result shown alongside our own ranking."""
    id: str = ""
    title: str = ""
    position: int = 0
    title: str = ""
    url: str = ""
    domain: str = ""


class SerpCheckResult(sdl.Entity):
    """Result of a fresh SERP check for one tracked keyword."""
    id: str = ""
    title: str = ""
    keyword_id: str = ""
    keyword: str = ""
    project_domain: str = ""
    found: bool = False
    position: int = 0
    url: str = ""
    top_competitors: list[SerpCompetitorItem] = []
    checked_at: str = ""


class GetKeywordHistoryParams(BaseModel):
    keyword_id: str = Field(..., description="Tracked keyword id from list_tracked_keywords")
    limit: int = Field(50, description="Max snapshots to return, most recent first (1-200)")


class KeywordSnapshot(sdl.Entity):
    """One historical SERP-position reading for a tracked keyword."""
    id: str = ""
    title: str = ""
    keyword_id: str = ""
    project_id: str = ""
    keyword: str = ""
    position: int = 0
    url: str = ""
    checked_at: str = ""


class KeywordSnapshotList(sdl.EntityList[KeywordSnapshot]):
    pass


# ──────────────────────────────────────────────────────────────────────────
# Keyword research -- volume lookup + related keyword discovery (Labs).
# ──────────────────────────────────────────────────────────────────────────


class GetKeywordVolumeParams(BaseModel):
    project_id: str = Field("", description="Optional project id -- supplies default location/language when set")
    keywords: list[str] = Field(..., description="Up to 1000 keyword phrases to look up search volume/CPC/competition for")
    location_name: str = Field("", description="Override location name; empty = use project default or 'Chisinau,Moldova'")
    language_code: str = Field("", description="Override two-letter language code; empty = use project default or 'ru'")


class KeywordVolumeItem(sdl.Entity):
    id: str = ""
    title: str = ""
    keyword: str = ""
    search_volume: int = 0
    cpc: float = 0.0
    competition: float = 0.0
    competition_level: str = ""


class KeywordVolumeList(sdl.EntityList[KeywordVolumeItem]):
    pass


class FindRelatedKeywordsParams(BaseModel):
    project_id: str = Field("", description="Optional project id -- supplies default location/language when set")
    seed_keyword: str = Field(..., description="Seed keyword to expand from")
    location_name: str = Field("", description="Override location name; empty = use project default or 'Chisinau,Moldova'")
    language_code: str = Field("", description="Override two-letter language code; empty = use project default or 'ru'")
    depth: int = Field(2, description="Search-graph depth to explore (1-4) -- higher finds more but costs more")
    limit: int = Field(20, description="Max related keywords to return (1-100)")


class RelatedKeywordItem(sdl.Entity):
    id: str = ""
    title: str = ""
    keyword: str = ""
    search_volume: int = 0
    cpc: float = 0.0
    competition: float = 0.0


class RelatedKeywordList(sdl.EntityList[RelatedKeywordItem]):
    pass


# ──────────────────────────────────────────────────────────────────────────
# Domain tracking -- backlink profile, with history snapshots.
# ──────────────────────────────────────────────────────────────────────────


class TrackedDomain(sdl.Entity):
    """One domain being monitored for backlink profile within a project.
    Usually the project's own domain, but can also be a competitor's."""
    id: str = ""
    title: str = ""
    project_id: str = ""
    domain: str = ""
    latest_backlinks: int = 0
    latest_referring_domains: int = 0
    latest_rank: int = 0
    latest_checked_at: str = ""
    created_at: str = ""


class TrackedDomainList(sdl.EntityList[TrackedDomain]):
    pass


class TrackDomainParams(BaseModel):
    project_id: str = Field(..., description="Project id from list_projects")
    domain: str = Field(..., description="Domain to monitor for backlinks, e.g. 'climtec.md' or a competitor's domain")


class ListTrackedDomainsParams(BaseModel):
    project_id: str = Field("", description="Filter by project. Empty = all projects.")
    limit: int = Field(100, description="Max items to return (1-200)")


class UntrackDomainParams(BaseModel):
    domain_id: str = Field(..., description="Tracked domain id from list_tracked_domains")


class GetBacklinkProfileParams(BaseModel):
    domain_id: str = Field(..., description="Tracked domain id from list_tracked_domains -- runs a fresh backlink check and records a new history snapshot")


class BacklinkSnapshot(sdl.Entity):
    """One historical backlink-profile reading for a tracked domain."""
    id: str = ""
    title: str = ""
    domain_id: str = ""
    project_id: str = ""
    domain: str = ""
    backlinks: int = 0
    referring_domains: int = 0
    rank: int = 0
    checked_at: str = ""


class BacklinkSnapshotList(sdl.EntityList[BacklinkSnapshot]):
    pass


class GetDomainHistoryParams(BaseModel):
    domain_id: str = Field(..., description="Tracked domain id from list_tracked_domains")
    limit: int = Field(50, description="Max snapshots to return, most recent first (1-200)")
