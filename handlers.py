"""Chat functions for DataForSEO Connector.

Connect/disconnect, sandbox toggle, projects (manual + Quick Add),
tracked keywords with SERP-check + history, tracked domains with
backlink-check + history, and keyword research (volume + related).
"""
from __future__ import annotations

from datetime import datetime, timezone

from imperal_sdk import ActionResult, sdl

import dfs_client as dfs
from app import ext, chat
from schemas import (
    NoParams,
    ConnectDataForSEOParams, ProviderConnection,
    SetSandboxModeParams, SandboxModeStatus,
    CreateProjectParams, ListProjectsParams, DFSProject, DFSProjectList,
    ListConnectedSitesParams, ConnectedSite, ConnectedSiteList,
    TrackKeywordParams, ListTrackedKeywordsParams, UntrackKeywordParams,
    TrackedKeyword, TrackedKeywordList,
    CheckSerpRankingParams, SerpCheckResult, SerpCompetitorItem,
    GetKeywordHistoryParams, KeywordSnapshot, KeywordSnapshotList,
    GetKeywordVolumeParams, KeywordVolumeItem, KeywordVolumeList,
    FindRelatedKeywordsParams, RelatedKeywordItem, RelatedKeywordList,
    TrackDomainParams, ListTrackedDomainsParams, UntrackDomainParams,
    TrackedDomain, TrackedDomainList,
    GetBacklinkProfileParams, BacklinkSnapshot,
    GetDomainHistoryParams, BacklinkSnapshotList,
    UntrackResult,
)

SITE_PROVIDER_APP_IDS: list[str] = ["wp-site-connector"]
_SANDBOX_MARKER = "sandbox_mode_setting"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_site_id(row: dict) -> str:
    """Normalise a provider's site identifier to its bare domain -- same
    normalisation Content Strategy Hub applies, needed for the same reason:
    providers key sites their own way (a slug), this app keys by domain."""
    host = (row.get("url") or "").strip().split("://", 1)[-1].split("/", 1)[0].lower()
    if host.startswith("www."):
        host = host[4:]
    return host or (row.get("site_id") or "")


async def fetch_connected_sites(ctx) -> tuple[list[dict], list[dict]]:
    """Pull every connected site from every registered site-provider
    extension via ctx.extensions.call. Kept as an independent copy of
    Content Strategy Hub's helper (not imported cross-app) so this
    connector works standalone even without Content Strategy Hub
    installed."""
    sites: list[dict] = []
    problems: list[dict] = []
    for app_id in SITE_PROVIDER_APP_IDS:
        try:
            rows = await ctx.extensions.call(app_id, "list_connected_sites")
        except Exception as exc:
            problems.append({"provider": app_id, "reason": str(exc)})
            continue
        for r in rows or []:
            sites.append({
                "site_id": _canonical_site_id(r),
                "name": r.get("name") or r.get("site_id", ""),
                "url": r.get("url", ""),
                "status": r.get("status", ""),
                "provider": app_id,
            })
    return sites, problems


async def _get_credentials(ctx) -> tuple[str, str]:
    login = await ctx.secrets.get("dataforseo_login")
    password = await ctx.secrets.get("dataforseo_password")
    return login or "", password or ""


async def _get_sandbox_mode(ctx) -> bool:
    page = await ctx.store.query("app_settings", where={"kind": _SANDBOX_MARKER}, limit=1)
    if page.data:
        return bool(page.data[0].data.get("sandbox", True))
    return True  # default ON -- safest first-run behaviour, costs nothing


async def _set_sandbox_mode(ctx, sandbox: bool) -> None:
    payload = {"kind": _SANDBOX_MARKER, "sandbox": sandbox}
    page = await ctx.store.query("app_settings", where={"kind": _SANDBOX_MARKER}, limit=1)
    if page.data:
        await ctx.store.update("app_settings", page.data[0].id, payload)
    else:
        await ctx.store.create("app_settings", payload)


async def _get_project(ctx, project_id: str) -> dict | None:
    page = await ctx.store.query("dfs_projects", where={"project_id": project_id}, limit=1)
    return page.data[0].data if page.data else None


# ──────────────────────────────────────────────────────────────────────────
# Connection / account management
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "connect_dataforseo",
    "Connect DataForSEO by saving your API login+password, after checking "
    "they actually work. Get them from your DataForSEO dashboard -- the API "
    "password is separate from your dashboard login password.",
    action_type="write",
    chain_callable=True,
    data_model=ProviderConnection,
    event="dataforseo-connector.connect_dataforseo",
    effects=["dataforseo.provider.connected"],
)
async def connect_dataforseo(ctx, params: ConnectDataForSEOParams) -> ActionResult:
    """Validate-then-store: credentials DataForSEO rejects are never
    written, so the stored value can never be one we already know is bad."""
    login = params.login.strip()
    password = params.password.strip()
    if not login or not password:
        return ActionResult.error(
            "Both login and password are required. Find them in your "
            "DataForSEO dashboard.",
            code="DFS_CREDENTIALS_MISSING",
        )

    sandbox = await _get_sandbox_mode(ctx)
    try:
        await dfs.validate_credentials(ctx, login, password, sandbox=sandbox)
    except dfs.ProviderError as exc:
        return ActionResult.error(str(exc), code=exc.code)

    await ctx.secrets.set("dataforseo_login", login)
    await ctx.secrets.set("dataforseo_password", password)
    mode = "Sandbox" if sandbox else "Live"
    return ActionResult.success(
        ProviderConnection(connected=True, detail=f"Verified against DataForSEO ({mode})"),
        summary=f"DataForSEO connected -- credentials verified against {mode} before saving.",
        refresh_panels=["dfs_projects"],
    )


@chat.function(
    "disconnect_dataforseo",
    "Disconnect DataForSEO: deletes the saved login+password. Existing "
    "projects, tracked keywords/domains and their history are kept -- only "
    "new checks are blocked until you connect again.",
    action_type="write",
    data_model=ProviderConnection,
    event="dataforseo-connector.disconnect_dataforseo",
    effects=["dataforseo.provider.disconnected"],
)
async def disconnect_dataforseo(ctx, params: NoParams) -> ActionResult:
    """Delete the stored credentials. Tracked projects/keywords/domains and
    their history are untouched -- only new checks are blocked."""
    await ctx.secrets.delete("dataforseo_login")
    await ctx.secrets.delete("dataforseo_password")
    return ActionResult.success(
        ProviderConnection(connected=False, detail="Disconnected"),
        summary="DataForSEO disconnected. Existing tracked data was kept.",
        refresh_panels=["dfs_projects"],
    )


@chat.function(
    "get_dataforseo_connection",
    "Check whether DataForSEO is connected (does not reveal the credentials).",
    action_type="read",
    data_model=ProviderConnection,
)
async def get_dataforseo_connection(ctx, params: NoParams) -> ActionResult:
    """Read-only connection status check -- never returns the credentials."""
    login, password = await _get_credentials(ctx)
    connected = bool(login and password)
    return ActionResult.success(
        ProviderConnection(
            connected=connected,
            detail="Connected" if connected else "Not connected -- run connect_dataforseo",
        ),
        summary="DataForSEO is connected." if connected else "DataForSEO is not connected.",
    )


@chat.function(
    "set_sandbox_mode",
    "Switch between DataForSEO's free Sandbox (test data, no charges) and "
    "Live (real data, real cost) mode. This is a standing setting -- it "
    "stays on Sandbox or Live for every check until changed again.",
    action_type="write",
    chain_callable=True,
    data_model=SandboxModeStatus,
    event="dataforseo-connector.set_sandbox_mode",
    effects=["dataforseo.sandbox_mode.changed"],
)
async def set_sandbox_mode(ctx, params: SetSandboxModeParams) -> ActionResult:
    """Persist the sandbox/live setting -- a standing toggle read by every
    request-making handler via _get_sandbox_mode, not a per-call param."""
    await _set_sandbox_mode(ctx, params.sandbox)
    mode = "Sandbox (free test data)" if params.sandbox else "Live (real data, real cost)"
    return ActionResult.success(
        SandboxModeStatus(sandbox=params.sandbox),
        summary=f"Switched to {mode}.",
        refresh_panels=["dfs_projects"],
    )


@chat.function(
    "get_sandbox_mode",
    "Check whether DataForSEO Connector is currently in Sandbox or Live mode.",
    action_type="read",
    data_model=SandboxModeStatus,
)
async def get_sandbox_mode(ctx, params: NoParams) -> ActionResult:
    """Read-only check of the standing sandbox/live setting."""
    sandbox = await _get_sandbox_mode(ctx)
    mode = "Sandbox" if sandbox else "Live"
    return ActionResult.success(SandboxModeStatus(sandbox=sandbox), summary=f"Currently in {mode} mode.")


# ──────────────────────────────────────────────────────────────────────────
# Projects -- manual create + Quick Add from connected site providers.
# Unlimited projects; each one scopes its own tracked keywords/domains and
# supplies default location/language (overridable per-keyword).
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "create_project",
    "Create a new DataForSEO tracking project for a domain -- your own site "
    "or a competitor's (set is_own_site=false). Sets the default location/"
    "language used for keyword checks in this project unless overridden "
    "per keyword. Use list_connected_sites first if you want to add a site "
    "you already connected in WordPress Hub with one click instead.",
    action_type="write",
    chain_callable=True,
    data_model=DFSProject,
    event="dataforseo-connector.create_project",
    effects=["dataforseo.project.created"],
)
async def create_project(ctx, params: CreateProjectParams) -> ActionResult:
    """Create one project. project_id is the stable business key -- reject
    a duplicate rather than silently overwrite an existing project."""
    existing = await _get_project(ctx, params.project_id)
    if existing:
        return ActionResult.error(
            f"Project '{params.project_id}' already exists.",
            code="DFS_PROJECT_EXISTS",
        )
    doc = {
        "project_id": params.project_id,
        "domain": params.domain,
        "brand_name": params.brand_name,
        "default_location_name": params.default_location_name or "Chisinau,Moldova",
        "default_language_code": params.default_language_code or "ru",
        "is_own_site": params.is_own_site,
        "created_at": _now_iso(),
    }
    await ctx.store.create("dfs_projects", doc)
    return ActionResult.success(
        DFSProject(id=params.project_id, title=params.brand_name or params.project_id, **doc),
        summary=f"Project '{params.project_id}' created.",
        refresh_panels=["dfs_projects"],
    )


@chat.function(
    "list_projects",
    "List all DataForSEO tracking projects (your own sites and any "
    "competitor domains you chose to track).",
    action_type="read",
    data_model=DFSProjectList,
)
async def list_projects(ctx, params: ListProjectsParams) -> ActionResult:
    """List every tracking project, unlimited in number."""
    page = await ctx.store.query("dfs_projects", limit=params.limit)
    items = [DFSProject(id=row.data["project_id"], title=row.data.get("brand_name") or row.data["project_id"], **row.data) for row in page.data]
    return ActionResult.success(DFSProjectList(items=items), summary=f"{len(items)} project(s).")


@chat.function(
    "list_connected_sites",
    "List sites already connected in other apps (WordPress Hub today) that "
    "Quick Add offers as one-click DataForSEO project candidates, flagging "
    "which are already registered here.",
    action_type="read",
    data_model=ConnectedSiteList,
)
async def list_connected_sites(ctx, params: ListConnectedSitesParams) -> ActionResult:
    """Quick Add source list: sites from other connected providers, each
    flagged with whether it already has a project here."""
    sites, problems = await fetch_connected_sites(ctx)
    existing_page = await ctx.store.query("dfs_projects", limit=500)
    existing_ids = {row.data.get("project_id") for row in existing_page.data}
    items = [
        ConnectedSite(
            site_id=s["site_id"], name=s["name"], url=s["url"],
            status=s["status"], provider=s["provider"],
            already_tracked=s["site_id"] in existing_ids,
        )
        for s in sites
    ]
    summary = f"{len(items)} connected site(s)"
    if problems:
        summary += f" ({len(problems)} provider(s) unreachable)"
    return ActionResult.success(ConnectedSiteList(items=items), summary=summary)


# ──────────────────────────────────────────────────────────────────────────
# Tracked keywords -- SERP position tracking with history.
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "track_keyword",
    "Start tracking a keyword's Google SERP position for a project. "
    "Uses the project's default location/language unless overridden here. "
    "Does not check the ranking yet -- call check_serp_ranking after.",
    action_type="write",
    chain_callable=True,
    data_model=TrackedKeyword,
    event="dataforseo-connector.track_keyword",
    effects=["dataforseo.keyword.tracked"],
)
async def track_keyword(ctx, params: TrackKeywordParams) -> ActionResult:
    """Register a keyword for SERP tracking under a project. Location/
    language default to the project's unless explicitly overridden."""
    project = await _get_project(ctx, params.project_id)
    if not project:
        return ActionResult.error(
            f"Project '{params.project_id}' not found. Create it first with create_project.",
            code="DFS_PROJECT_NOT_FOUND",
        )
    doc = {
        "project_id": params.project_id,
        "keyword": params.keyword,
        "location_name": params.location_name or project["default_location_name"],
        "language_code": params.language_code or project["default_language_code"],
        "search_engine": params.search_engine,
        "latest_position": 0,
        "latest_url": "",
        "latest_checked_at": "",
        "search_volume": 0,
        "cpc": 0.0,
        "competition": 0.0,
        "created_at": _now_iso(),
    }
    created = await ctx.store.create("dfs_tracked_keywords", doc)
    return ActionResult.success(
        TrackedKeyword(id=created.id, title=params.keyword, **doc),
        summary=f"Now tracking '{params.keyword}' for {params.project_id}.",
        refresh_panels=["dfs_tracked"],
    )


@chat.function(
    "list_tracked_keywords",
    "List tracked keywords, optionally filtered by project, with each "
    "keyword's latest known SERP position.",
    action_type="read",
    data_model=TrackedKeywordList,
)
async def list_tracked_keywords(ctx, params: ListTrackedKeywordsParams) -> ActionResult:
    """List tracked keywords with their latest known SERP position."""
    where = {"project_id": params.project_id} if params.project_id else None
    page = await ctx.store.query("dfs_tracked_keywords", where=where, limit=params.limit)
    items = [TrackedKeyword(id=row.id, title=row.data.get("keyword", ""), **row.data) for row in page.data]
    return ActionResult.success(TrackedKeywordList(items=items), summary=f"{len(items)} tracked keyword(s).")


@chat.function(
    "untrack_keyword",
    "Stop tracking a keyword. Its recorded history snapshots are kept.",
    action_type="write",
    data_model=UntrackResult,
    event="dataforseo-connector.untrack_keyword",
    effects=["dataforseo.keyword.untracked"],
)
async def untrack_keyword(ctx, params: UntrackKeywordParams) -> ActionResult:
    """Remove the tracking record. Position snapshots stay in
    dfs_keyword_snapshots for historical reference."""
    await ctx.store.delete("dfs_tracked_keywords", params.keyword_id)
    return ActionResult.success(
        UntrackResult(id=params.keyword_id, removed=True),
        summary="Keyword untracked. History was kept.",
        refresh_panels=["dfs_tracked"],
    )


@chat.function(
    "check_serp_ranking",
    "Run a fresh Google SERP check for a tracked keyword: finds the "
    "project's own domain among the results and records a new history "
    "snapshot, plus shows the top competing results.",
    action_type="write",
    chain_callable=True,
    data_model=SerpCheckResult,
    event="dataforseo-connector.check_serp_ranking",
    effects=["dataforseo.keyword.checked"],
)
async def check_serp_ranking(ctx, params: CheckSerpRankingParams) -> ActionResult:
    """Fetch a live Google SERP for the keyword, locate the project's own
    domain in it, and append one snapshot to the history."""
    kw_row = await ctx.store.get("dfs_tracked_keywords", params.keyword_id)
    if not kw_row:
        return ActionResult.error("Tracked keyword not found.", code="DFS_KEYWORD_NOT_FOUND")
    kw = kw_row.data
    project = await _get_project(ctx, kw["project_id"])
    if not project:
        return ActionResult.error("Project for this keyword no longer exists.", code="DFS_PROJECT_NOT_FOUND")

    login, password = await _get_credentials(ctx)
    if not login or not password:
        return ActionResult.error(
            "DataForSEO is not connected. Run connect_dataforseo first.",
            code="DFS_NOT_CONNECTED",
        )
    sandbox = await _get_sandbox_mode(ctx)

    try:
        serp = await dfs.serp_google_organic_live(
            ctx, login, password, sandbox=sandbox,
            keyword=kw["keyword"], location_name=kw["location_name"],
            language_code=kw["language_code"], depth=params.depth,
        )
    except dfs.ProviderError as exc:
        return ActionResult.error(str(exc), code=exc.code)

    items = serp.get("items") or []
    match = dfs.find_domain_rank(items, project["domain"])
    checked_at = _now_iso()

    top_competitors = [
        SerpCompetitorItem(
            position=it.get("rank_absolute") or it.get("rank_group") or 0,
            title=it.get("title", ""),
            url=it.get("url", ""),
            domain=(it.get("url") or "").split("://", 1)[-1].split("/", 1)[0],
        )
        for it in items if it.get("type") == "organic"
    ][:5]

    position = match["position"] if match else 0
    url = match["url"] if match else ""

    await ctx.store.update("dfs_tracked_keywords", params.keyword_id, {
        "latest_position": position, "latest_url": url, "latest_checked_at": checked_at,
    })
    await ctx.store.create("dfs_keyword_snapshots", {
        "keyword_id": params.keyword_id, "project_id": kw["project_id"],
        "keyword": kw["keyword"], "position": position, "url": url,
        "checked_at": checked_at,
    })

    result = SerpCheckResult(
        keyword_id=params.keyword_id, keyword=kw["keyword"],
        project_domain=project["domain"], found=bool(match),
        position=position, url=url, top_competitors=top_competitors,
        checked_at=checked_at,
    )
    summary = (
        f"'{kw['keyword']}' ranks #{position} for {project['domain']}."
        if match else f"'{kw['keyword']}': {project['domain']} not found in top {params.depth}."
    )
    return ActionResult.success(result, summary=summary, refresh_panels=["dfs_tracked"])


@chat.function(
    "get_keyword_history",
    "Read the position history for a tracked keyword -- every past SERP "
    "check, most recent first.",
    action_type="read",
    data_model=KeywordSnapshotList,
)
async def get_keyword_history(ctx, params: GetKeywordHistoryParams) -> ActionResult:
    """Read all recorded position snapshots for one tracked keyword."""
    page = await ctx.store.query(
        "dfs_keyword_snapshots", where={"keyword_id": params.keyword_id}, limit=params.limit,
    )
    rows = sorted(page.data, key=lambda r: r.data.get("checked_at", ""), reverse=True)
    items = [KeywordSnapshot(**r.data) for r in rows]
    return ActionResult.success(KeywordSnapshotList(items=items), summary=f"{len(items)} snapshot(s).")


# ──────────────────────────────────────────────────────────────────────────
# Keyword research -- search volume + related keyword ideas. Standalone
# reads, not tied to a tracked keyword, so they double as discovery tools
# for finding NEW keywords worth tracking.
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "get_keyword_volume",
    "Look up monthly Google Ads search volume, CPC, and competition for "
    "up to 1000 keywords at once. Optionally pass a project_id to use its "
    "default location/language.",
    action_type="read",
    data_model=KeywordVolumeList,
)
async def get_keyword_volume(ctx, params: GetKeywordVolumeParams) -> ActionResult:
    """Standalone Google Ads search-volume/CPC/competition lookup, not tied
    to a tracked keyword -- useful for researching before deciding to track."""
    login, password = await _get_credentials(ctx)
    if not login or not password:
        return ActionResult.error(
            "DataForSEO is not connected. Run connect_dataforseo first.",
            code="DFS_NOT_CONNECTED",
        )
    location_name, language_code = params.location_name, params.language_code
    if params.project_id and (not location_name or not language_code):
        project = await _get_project(ctx, params.project_id)
        if project:
            location_name = location_name or project["default_location_name"]
            language_code = language_code or project["default_language_code"]
    location_name = location_name or "Chisinau,Moldova"
    language_code = language_code or "ru"
    sandbox = await _get_sandbox_mode(ctx)

    try:
        rows = await dfs.keywords_search_volume_live(
            ctx, login, password, sandbox=sandbox, keywords=params.keywords,
            location_name=location_name, language_code=language_code,
        )
    except dfs.ProviderError as exc:
        return ActionResult.error(str(exc), code=exc.code)

    items = [
        KeywordVolumeItem(
            keyword=r.get("keyword", ""),
            search_volume=r.get("search_volume") or 0,
            cpc=r.get("cpc") or 0.0,
            competition=r.get("competition") or 0.0,
        )
        for r in rows
    ]
    return ActionResult.success(KeywordVolumeList(items=items), summary=f"{len(items)} keyword(s) looked up.")


@chat.function(
    "find_related_keywords",
    "Discover related keyword ideas for a seed keyword -- the 'searches "
    "related to' SERP graph, with search volume and CPC per idea. Great "
    "for finding new keywords worth tracking.",
    action_type="read",
    data_model=RelatedKeywordList,
)
async def find_related_keywords(ctx, params: FindRelatedKeywordsParams) -> ActionResult:
    """Discover related keyword ideas via DataForSEO Labs' 'searches related
    to' graph, seeded from one keyword."""
    login, password = await _get_credentials(ctx)
    if not login or not password:
        return ActionResult.error(
            "DataForSEO is not connected. Run connect_dataforseo first.",
            code="DFS_NOT_CONNECTED",
        )
    location_name, language_code = params.location_name, params.language_code
    if params.project_id and (not location_name or not language_code):
        project = await _get_project(ctx, params.project_id)
        if project:
            location_name = location_name or project["default_location_name"]
            language_code = language_code or project["default_language_code"]
    location_name = location_name or "Chisinau,Moldova"
    language_code = language_code or "ru"
    sandbox = await _get_sandbox_mode(ctx)

    try:
        rows = await dfs.labs_related_keywords_live(
            ctx, login, password, sandbox=sandbox, seed_keyword=params.seed_keyword,
            location_name=location_name, language_code=language_code,
            depth=params.depth, limit=params.limit,
        )
    except dfs.ProviderError as exc:
        return ActionResult.error(str(exc), code=exc.code)

    items = []
    for r in rows:
        info = r.get("keyword_data") or r
        kw_info = info.get("keyword_info") or {}
        items.append(RelatedKeywordItem(
            keyword=info.get("keyword", ""),
            search_volume=kw_info.get("search_volume") or 0,
            cpc=kw_info.get("cpc") or 0.0,
            competition=kw_info.get("competition") or 0.0,
        ))
    return ActionResult.success(RelatedKeywordList(items=items), summary=f"{len(items)} related keyword(s) found.")


# ──────────────────────────────────────────────────────────────────────────
# Tracked domains -- backlink profile tracking with history.
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "track_domain",
    "Start tracking a domain's backlink profile for a project (your own "
    "site or a competitor's). Does not fetch data yet -- call "
    "get_backlink_profile after.",
    action_type="write",
    chain_callable=True,
    data_model=TrackedDomain,
    event="dataforseo-connector.track_domain",
    effects=["dataforseo.domain.tracked"],
)
async def track_domain(ctx, params: TrackDomainParams) -> ActionResult:
    """Register a domain for backlink tracking under a project."""
    project = await _get_project(ctx, params.project_id)
    if not project:
        return ActionResult.error(
            f"Project '{params.project_id}' not found. Create it first with create_project.",
            code="DFS_PROJECT_NOT_FOUND",
        )
    doc = {
        "project_id": params.project_id,
        "domain": params.domain,
        "latest_backlinks": 0,
        "latest_referring_domains": 0,
        "latest_rank": 0,
        "latest_checked_at": "",
        "created_at": _now_iso(),
    }
    created = await ctx.store.create("dfs_tracked_domains", doc)
    return ActionResult.success(
        TrackedDomain(id=created.id, title=params.domain, **doc),
        summary=f"Now tracking backlinks for '{params.domain}'.",
        refresh_panels=["dfs_tracked"],
    )


@chat.function(
    "list_tracked_domains",
    "List tracked domains, optionally filtered by project.",
    action_type="read",
    data_model=TrackedDomainList,
)
async def list_tracked_domains(ctx, params: ListTrackedDomainsParams) -> ActionResult:
    """List tracked domains with their latest known backlink summary."""
    where = {"project_id": params.project_id} if params.project_id else None
    page = await ctx.store.query("dfs_tracked_domains", where=where, limit=200)
    items = [TrackedDomain(id=r.id, title=r.data.get("domain", ""), **r.data) for r in page.data]
    return ActionResult.success(TrackedDomainList(items=items), summary=f"{len(items)} tracked domain(s).")


@chat.function(
    "untrack_domain",
    "Stop tracking a domain. Its recorded history snapshots are kept.",
    action_type="write",
    data_model=UntrackResult,
    event="dataforseo-connector.untrack_domain",
    effects=["dataforseo.domain.untracked"],
)
async def untrack_domain(ctx, params: UntrackDomainParams) -> ActionResult:
    """Remove the tracking record. Backlink snapshots stay in
    dfs_backlink_snapshots for historical reference."""
    await ctx.store.delete("dfs_tracked_domains", params.domain_id)
    return ActionResult.success(
        UntrackResult(id=params.domain_id, removed=True),
        summary="Domain untracked. History was kept.",
        refresh_panels=["dfs_tracked"],
    )


@chat.function(
    "get_backlink_profile",
    "Run a fresh backlink summary check for a tracked domain: total "
    "backlinks, referring domains, and DataForSEO's domain rank, and "
    "records a new history snapshot.",
    action_type="write",
    chain_callable=True,
    data_model=BacklinkSnapshot,
    event="dataforseo-connector.get_backlink_profile",
    effects=["dataforseo.domain.checked"],
)
async def get_backlink_profile(ctx, params: GetBacklinkProfileParams) -> ActionResult:
    """Fetch a live backlinks summary for the domain and append one
    snapshot to the history."""
    dom_row = await ctx.store.get("dfs_tracked_domains", params.domain_id)
    if not dom_row:
        return ActionResult.error("Tracked domain not found.", code="DFS_DOMAIN_NOT_FOUND")
    dom = dom_row.data

    login, password = await _get_credentials(ctx)
    if not login or not password:
        return ActionResult.error(
            "DataForSEO is not connected. Run connect_dataforseo first.",
            code="DFS_NOT_CONNECTED",
        )
    sandbox = await _get_sandbox_mode(ctx)

    try:
        result = await dfs.backlinks_summary_live(ctx, login, password, sandbox=sandbox, target=dom["domain"])
    except dfs.ProviderError as exc:
        return ActionResult.error(str(exc), code=exc.code)

    backlinks = result.get("backlinks") or 0
    referring_domains = result.get("referring_domains") or 0
    rank = result.get("rank") or 0
    checked_at = _now_iso()

    await ctx.store.update("dfs_tracked_domains", params.domain_id, {
        "latest_backlinks": backlinks, "latest_referring_domains": referring_domains,
        "latest_rank": rank, "latest_checked_at": checked_at,
    })
    await ctx.store.create("dfs_backlink_snapshots", {
        "domain_id": params.domain_id, "project_id": dom["project_id"], "domain": dom["domain"],
        "backlinks": backlinks, "referring_domains": referring_domains, "rank": rank,
        "checked_at": checked_at,
    })

    snapshot = BacklinkSnapshot(
        domain_id=params.domain_id, domain=dom["domain"], backlinks=backlinks,
        referring_domains=referring_domains, rank=rank, checked_at=checked_at,
    )
    return ActionResult.success(
        snapshot,
        summary=f"'{dom['domain']}': {backlinks} backlinks from {referring_domains} referring domains, rank {rank}.",
        refresh_panels=["dfs_tracked"],
    )


@chat.function(
    "get_domain_history",
    "Read the backlink history for a tracked domain -- every past check, "
    "most recent first.",
    action_type="read",
    data_model=BacklinkSnapshotList,
)
async def get_domain_history(ctx, params: GetDomainHistoryParams) -> ActionResult:
    """Read all recorded backlink snapshots for one tracked domain."""
    page = await ctx.store.query(
        "dfs_backlink_snapshots", where={"domain_id": params.domain_id}, limit=params.limit,
    )
    rows = sorted(page.data, key=lambda r: r.data.get("checked_at", ""), reverse=True)
    items = [BacklinkSnapshot(**r.data) for r in rows]
    return ActionResult.success(BacklinkSnapshotList(items=items), summary=f"{len(items)} snapshot(s).")
