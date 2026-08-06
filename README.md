# DataForSEO Connector

A standalone SEO data layer over the [DataForSEO](https://dataforseo.com/)
API: SERP position tracking, keyword research (search volume + related
keywords), and backlink monitoring -- each with history kept over time.
Bring-your-own-account (BYOK): you connect your own DataForSEO login and
password, same pattern as Media Studio's Magnific connection.

Not folded into Content Strategy Hub or SEO Audit Engine: this is a
different concern (paid third-party rank/keyword/backlink data vs. this
platform's own content strategy and on-page audits) and stays its own app so
it can be extended independently -- **all future DataForSEO capabilities go
into this one app, not new ones.**

## Connecting

1. Get an API login + password from your DataForSEO dashboard -- the API
   password is separate from your dashboard login password.
2. Paste them into the right-hand panel's "Connect DataForSEO" form, or call
   `connect_dataforseo` from chat. Credentials are **verified against
   DataForSEO before being saved** (a tiny 1-result SERP Live call) -- a bad
   paste is rejected immediately instead of failing silently on first real
   use.
3. `disconnect_dataforseo` deletes the stored credentials. Tracked
   projects/keywords/domains and their history are untouched -- only new
   checks are blocked until you reconnect.

## Sandbox / Live

A permanent toggle (`set_sandbox_mode` / `get_sandbox_mode`, also a Toggle
in the right panel) switches every subsequent API call between
`sandbox.dataforseo.com` (free, generic test data, never billed) and
`api.dataforseo.com` (real data, real cost). It stays visible in the UI
forever -- not a one-time onboarding step -- so you can safely dry-run new
projects/keywords in Sandbox before switching to Live for real numbers.

## Projects

A **project** is one domain being tracked -- your own site or a
competitor's (`is_own_site=false`). There is no cap: create as many as you
want. Each project carries its own default location/language
(`default_location_name`, `default_language_code`), used for every keyword
check inside it unless overridden per keyword.

Two ways to add one:
- **Manually** -- `create_project` with a domain (and optionally a
  competitor's domain, `is_own_site=false`).
- **Quick Add** -- `list_connected_sites` reads every site already
  connected in a site-provider extension (WordPress Hub today via
  `SITE_PROVIDER_APP_IDS`, more providers later with no schema change) and
  flags which ones already have a project here. The right panel renders
  this as one-click "+ sitename" buttons.

## Tracked keywords -- SERP position + history

- `track_keyword` -- start tracking a keyword's Google SERP position for a
  project (own domain matched against results).
- `check_serp_ranking` -- runs a fresh SERP check via DataForSEO's Live
  Google Organic endpoint, records a `dfs_keyword_snapshots` row, and
  returns the top 5 competing organic results alongside your own position.
- `get_keyword_history` -- every past snapshot for a keyword, most recent
  first.
- `untrack_keyword` -- stops tracking; history snapshots are kept.

## Keyword research

- `get_keyword_volume` -- Google Ads search volume/CPC/competition for up
  to 1000 keywords at once. Standalone discovery tool, not tied to a
  tracked keyword.
- `find_related_keywords` -- DataForSEO Labs related-keyword ideas from a
  seed keyword, with volume/CPC/competition/difficulty per idea.

## Tracked domains -- backlink profile + history

- `track_domain` / `untrack_domain` -- same shape as keywords, for a
  domain's backlink profile (own site or a competitor's).
- `get_backlink_profile` -- fresh Backlinks Summary Live check (total
  backlinks, referring domains, domain rank), recorded as a
  `dfs_backlink_snapshots` row.
- `get_domain_history` -- every past snapshot for a domain.

On-page auditing (technical SEO issues on your own pages) is deliberately
**out of scope** -- that overlaps SEO Audit Engine, which already owns it.

## Panels

- **right (`dfs_projects`)** -- connection status/form, the permanent
  Sandbox/Live toggle, the project list, Quick Add from connected sites,
  and a manual "New project" form.
- **left (`dfs_tracked`)** -- tracked keywords and domains for the
  selected project, each with a one-field form to track a new one.
- **center, overlay (`dfs_detail`)** -- one keyword's or domain's detail:
  latest reading, a "check now" button, and the full history table.

## Why Live endpoints, not task_post/task_get

DataForSEO offers both an async task_post -> task_get flow and synchronous
Live endpoints for the same data. Every operation here is expected to
finish inside one chat-turn/panel-click response, so Live is used
everywhere it exists -- no polling, no background task. If a genuinely bulk
operation is added later (checking hundreds of keywords in one go),
task_post/task_get becomes worth adding as a second path.

## Why Basic Auth is built in `dfs_client.py`, not left to `ctx.http`

DataForSEO authenticates with plain HTTP Basic Auth (login:password,
base64-encoded in the `Authorization` header), not an API-key header.
`ctx.http` does not auto-attach Basic Auth, so `dfs_client._headers` builds
it explicitly on every call.
