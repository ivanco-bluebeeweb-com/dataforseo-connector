"""Extension declaration, secrets, lifecycle hooks.

WHY BYOK (bring-your-own-key), same reasoning as Media Hub's Magnific
integration. DataForSEO is a paid third-party API the USER has their own
account and quota with (per the onboarding email from DataForSEO's own
team) -- not something Imperal can broker centrally. The user pastes their
own DataForSEO API login+password once, Vault-encrypted via `ctx.secrets`,
and every call runs against their own quota/billing.

TWO SECRETS, MATCHING WHAT DATAFORSEO ACTUALLY HANDS OUT.

DataForSEO's dashboard issues a login (usually the account email) and a
SEPARATE API password (not the login password) -- see docs.dataforseo.com/
v3/auth/. Both are needed for every request's HTTP Basic Auth header.

WHY `write_mode="both"`, SAME REASONING AS MEDIA HUB.

Declaring `write_mode="user"` would mean only the platform's generic
Secrets screen could write these -- leaving a first-time user with no
in-app screen explaining what a DataForSEO login/password even is or
whether what they pasted actually works. `write_mode="both"` keeps the
platform Secrets screen working AND lets this extension's own
`connect_dataforseo` validate the credentials against DataForSEO's API
*before* writing them, so a bad paste is rejected immediately.
"""

from imperal_sdk import Extension, ChatExtension

ext = Extension(
    "dataforseo-connector",
    version="0.1.0",
    display_name="DataForSEO Connector",
    description=(
        "Keyword rankings, search volume, related keyword research, and "
        "backlink data via your own DataForSEO account -- SERP positions "
        "with history, Google Ads search volume/CPC, DataForSEO Labs "
        "related-keyword ideas, and domain backlink summaries. Organize "
        "tracking into projects (your own sites or a competitor's), with a "
        "permanent Sandbox/Live toggle so you can try everything free "
        "before spending real API credits."
    ),
    icon="icon.svg",
    actions_explicit=True,
    capabilities=["dataforseo:read", "dataforseo:write"],
)

chat = ChatExtension(
    ext,
    tool_name="dataforseo-connector",
    description="Keyword rankings, search volume, keyword research, and backlinks via DataForSEO",
)

ext.secret(
    name="dataforseo_login",
    description=(
        "DataForSEO API login (usually your account email) -- from your "
        "DataForSEO dashboard, NOT your dashboard login password."
    ),
    write_mode="both",
)
ext.secret(
    name="dataforseo_password",
    description=(
        "DataForSEO API password -- a separate password from your dashboard "
        "login, shown once when the API password is generated/reset in your "
        "DataForSEO dashboard."
    ),
    write_mode="both",
)


@ext.health_check
async def health_check(ctx) -> bool:
    """Basic liveness check -- confirms the store surface is reachable."""
    await ctx.store.query("dfs_projects", limit=1)
    return True
