"""Panel UI: right = Projects + connection + Sandbox/Live toggle, left =
tracked keywords/domains for the selected project, center = keyword/domain
detail with history. Same three-slot shape as Content Strategy Hub
(sources/queue/brief), chosen because DataForSEO Connector has the same
project-scoped-list-plus-detail shape.
"""
from __future__ import annotations

from imperal_sdk import ui

from app import ext
import handlers as h


async def _connection_status(ctx) -> tuple[bool, str]:
    login, password = await h._get_credentials(ctx)
    return bool(login and password), ("Connected" if login and password else "Not connected")


def _connect_card(connected: bool) -> ui.UINode:
    if connected:
        return ui.Card(
            title="DataForSEO",
            subtitle="Connected",
            content=ui.Stack(direction="v", gap=2, children=[
                ui.Text("Your login/password are saved and verified.", variant="caption"),
                ui.Button("Disconnect", variant="danger", size="sm",
                          on_click=ui.Call("disconnect_dataforseo")),
            ]),
        )
    return ui.Card(
        title="Connect DataForSEO",
        subtitle="Bring your own DataForSEO account",
        content=ui.Stack(direction="v", gap=2, children=[
            ui.Text(
                "Get login+password from your DataForSEO dashboard -- the "
                "API password is separate from your dashboard login "
                "password. Credentials are verified before saving.",
                variant="caption",
            ),
            ui.Link(label="Open dataforseo.com", href="https://dataforseo.com/"),
            ui.Form(
                action="connect_dataforseo",
                submit_label="Verify and connect",
                children=[
                    ui.Input(param_name="login", placeholder="API login (email)"),
                    ui.Password(param_name="password", placeholder="API password"),
                ],
            ),
        ]),
    )


def _sandbox_toggle(sandbox: bool) -> ui.UINode:
    return ui.Card(
        title="Sandbox / Live",
        subtitle="Sandbox = free test data, never billed. Live = real data, real cost.",
        content=ui.Toggle(
            param_name="sandbox", value=sandbox, label="Sandbox mode",
            on_change=ui.Call("set_sandbox_mode"),
        ),
    )


def _quick_add_block(connected_sites: list, existing_ids: set) -> ui.UINode:
    candidates = [s for s in connected_sites if s.get("site_id") not in existing_ids]
    refresh = ui.Button("Refresh", variant="secondary", size="sm", icon="RefreshCw",
                         on_click=ui.Call("list_connected_sites"))
    if not candidates:
        return ui.Card(
            title="Quick Add — from connected sites",
            content=ui.Stack(direction="v", gap=2, children=[
                ui.Text(
                    "Nothing new to add — every site connected in "
                    "WordPress Hub already has a project here.",
                    variant="caption",
                ),
                refresh,
            ]),
        )
    buttons = [
        ui.Button(
            f"+ {c.get('name') or c['site_id']}", variant="secondary", size="sm",
            on_click=ui.Call(
                "create_project",
                project_id=c["site_id"], domain=c["site_id"],
                brand_name=c.get("name", ""), is_own_site=True,
            ),
        )
        for c in candidates
    ]
    return ui.Card(
        title="Quick Add — from connected sites",
        content=ui.Stack(direction="v", gap=2, children=buttons + [refresh]),
    )


def _new_project_form() -> ui.UINode:
    return ui.Card(
        title="New project",
        content=ui.Form(
            action="create_project",
            submit_label="Create project",
            children=[
                ui.Input(param_name="project_id", placeholder="Project id, e.g. climtec.md"),
                ui.Input(param_name="domain", placeholder="Domain, e.g. climtec.md"),
                ui.Input(param_name="brand_name", placeholder="Brand name (optional)"),
                ui.Input(param_name="default_location_name",
                         placeholder="Default location, e.g. Chisinau,Moldova"),
                ui.Input(param_name="default_language_code", placeholder="Default language, e.g. ru"),
                ui.Toggle(param_name="is_own_site", value=True, label="This is my own site (off = tracking a competitor)"),
            ],
        ),
    )


@ext.panel("dfs_projects", slot="right", title="DataForSEO Projects", icon="🔍",
           default_width=300, min_width=240, max_width=420)
async def dfs_projects_panel(ctx, **kwargs) -> object:
    connected, _ = await _connection_status(ctx)
    sandbox = await h._get_sandbox_mode(ctx)

    page = await ctx.store.query("dfs_projects", limit=200)
    projects = [d.data | {"_id": d.id} for d in page.data]

    connected_sites, _problems = await h.fetch_connected_sites(ctx)
    existing_ids = {p.get("project_id") for p in projects}

    children: list[ui.UINode] = [_connect_card(connected), _sandbox_toggle(sandbox)]

    if not connected:
        children.append(ui.Alert(
            title="Not connected yet",
            message="Projects can be created without a connection, but "
                    "checking rankings/volume/backlinks needs DataForSEO connected.",
            type="info",
        ))

    if not projects:
        children.append(ui.Empty(message="No projects yet — add one below.", icon="🔍"))
    else:
        items = [
            ui.ListItem(
                id=p["project_id"], title=p.get("brand_name") or p["project_id"],
                subtitle=p.get("domain", "") + ("" if p.get("is_own_site", True) else " (competitor)"),
                on_click=ui.Call("__panel__dfs_tracked", project_id=p["project_id"]),
            )
            for p in projects
        ]
        children.append(ui.Card(title="Projects", content=ui.List(items=items, searchable=True)))

    children.append(_quick_add_block(connected_sites, existing_ids))
    children.append(_new_project_form())

    return ui.Stack(direction="v", gap=3, children=children)


@ext.panel("dfs_tracked", slot="left", title="Tracked", icon="📈")
async def dfs_tracked_panel(ctx, project_id: str = "", **kwargs) -> object:
    if not project_id:
        page = await ctx.store.query("dfs_projects", limit=1)
        if page.data:
            project_id = page.data[0].data.get("project_id", "")
    if not project_id:
        return ui.Empty(message="Create a project on the right to start tracking.", icon="📈")

    kw_page = await ctx.store.query("dfs_tracked_keywords", where={"project_id": project_id}, limit=200)
    dom_page = await ctx.store.query("dfs_tracked_domains", where={"project_id": project_id}, limit=200)

    kw_items = [
        ui.ListItem(
            id=d.id, title=d.data.get("keyword", ""),
            subtitle=(f"#{d.data['latest_position']}" if d.data.get("latest_position") else "not checked yet"),
            on_click=ui.Call("__panel__dfs_detail", kind="keyword", record_id=d.id),
        )
        for d in kw_page.data
    ]
    dom_items = [
        ui.ListItem(
            id=d.id, title=d.data.get("domain", ""),
            subtitle=f"rank {d.data['latest_rank']}" if d.data.get("latest_rank") else "not checked yet",
            on_click=ui.Call("__panel__dfs_detail", kind="domain", record_id=d.id),
        )
        for d in dom_page.data
    ]

    kw_form = ui.Form(
        action="track_keyword", submit_label="Track keyword",
        defaults={"project_id": project_id},
        children=[ui.Input(param_name="keyword", placeholder="Keyword phrase")],
    )
    dom_form = ui.Form(
        action="track_domain", submit_label="Track domain",
        defaults={"project_id": project_id},
        children=[ui.Input(param_name="domain", placeholder="Domain, e.g. competitor.md")],
    )

    return ui.Stack(direction="v", gap=3, children=[
        ui.Card(title="Keywords", content=ui.Stack(direction="v", gap=2, children=[
            ui.List(items=kw_items, searchable=True) if kw_items else ui.Text("No keywords tracked yet.", variant="caption"),
            kw_form,
        ])),
        ui.Card(title="Domains", content=ui.Stack(direction="v", gap=2, children=[
            ui.List(items=dom_items, searchable=True) if dom_items else ui.Text("No domains tracked yet.", variant="caption"),
            dom_form,
        ])),
    ])


async def _keyword_detail(ctx, record_id: str) -> ui.UINode:
    row = await ctx.store.get("dfs_tracked_keywords", record_id)
    if not row:
        return ui.Error(message="This keyword is no longer tracked.")
    kw = row.data

    snaps_page = await ctx.store.query(
        "dfs_keyword_snapshots", where={"keyword_id": record_id}, limit=50,
    )
    snaps = sorted(snaps_page.data, key=lambda r: r.data.get("checked_at", ""), reverse=True)

    history_rows = [
        {"Checked": s.data.get("checked_at", "")[:19].replace("T", " "),
         "Position": s.data.get("position") or "—",
         "URL": s.data.get("url", "")}
        for s in snaps
    ]

    return ui.Stack(direction="v", gap=3, children=[
        ui.Header(text=kw.get("keyword", ""), level=3,
                   subtitle=f"{kw.get('location_name', '')} · {kw.get('language_code', '')}"),
        ui.KeyValue(columns=2, items=[
            {"key": "Latest position", "value": kw.get("latest_position") or "not checked"},
            {"key": "Latest URL", "value": kw.get("latest_url") or "—"},
            {"key": "Search volume", "value": kw.get("search_volume") or "—"},
            {"key": "CPC", "value": kw.get("cpc") or "—"},
        ]),
        ui.Button("Check ranking now", icon="RefreshCw", variant="primary",
                   on_click=ui.Call("check_serp_ranking", keyword_id=record_id)),
        ui.Section(title="History", children=[
            ui.DataTable(columns=[
                ui.DataColumn(key="Checked", label="Checked"),
                ui.DataColumn(key="Position", label="Position"),
                ui.DataColumn(key="URL", label="URL"),
            ], rows=history_rows) if history_rows else ui.Text("No history yet.", variant="caption"),
        ]),
        ui.Button("Untrack this keyword", variant="danger", size="sm",
                   on_click=ui.Call("untrack_keyword", keyword_id=record_id)),
    ])


async def _domain_detail(ctx, record_id: str) -> ui.UINode:
    row = await ctx.store.get("dfs_tracked_domains", record_id)
    if not row:
        return ui.Error(message="This domain is no longer tracked.")
    dom = row.data

    snaps_page = await ctx.store.query(
        "dfs_backlink_snapshots", where={"domain_id": record_id}, limit=50,
    )
    snaps = sorted(snaps_page.data, key=lambda r: r.data.get("checked_at", ""), reverse=True)
    history_rows = [
        {"Checked": s.data.get("checked_at", "")[:19].replace("T", " "),
         "Rank": s.data.get("rank") or "—",
         "Backlinks": s.data.get("backlinks") or "—",
         "Referring domains": s.data.get("referring_domains") or "—"}
        for s in snaps
    ]

    return ui.Stack(direction="v", gap=3, children=[
        ui.Header(text=dom.get("domain", ""), level=3),
        ui.KeyValue(columns=2, items=[
            {"key": "Latest rank", "value": dom.get("latest_rank") or "not checked"},
            {"key": "Backlinks", "value": dom.get("latest_backlinks") or "—"},
            {"key": "Referring domains", "value": dom.get("latest_referring_domains") or "—"},
        ]),
        ui.Button("Check backlinks now", icon="RefreshCw", variant="primary",
                   on_click=ui.Call("get_backlink_profile", domain_id=record_id)),
        ui.Section(title="History", children=[
            ui.DataTable(columns=[
                ui.DataColumn(key="Checked", label="Checked"),
                ui.DataColumn(key="Rank", label="Rank"),
                ui.DataColumn(key="Backlinks", label="Backlinks"),
                ui.DataColumn(key="Referring domains", label="Referring domains"),
            ], rows=history_rows) if history_rows else ui.Text("No history yet.", variant="caption"),
        ]),
        ui.Button("Untrack this domain", variant="danger", size="sm",
                   on_click=ui.Call("untrack_domain", domain_id=record_id)),
    ])


@ext.panel("dfs_detail", slot="center", title="Detail", icon="🔎", center_overlay=True)
async def dfs_detail_panel(ctx, kind: str = "", record_id: str = "", **kwargs) -> object:
    if not record_id:
        return ui.Empty(message="Select a tracked keyword or domain to see its detail.", icon="🔎")
    if kind == "domain":
        return await _domain_detail(ctx, record_id)
    return await _keyword_detail(ctx, record_id)
