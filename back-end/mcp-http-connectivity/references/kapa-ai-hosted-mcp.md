# Hosted Third-Party MCP Servers (kapa.ai pattern)

Most MCP references in `mcp-http-connectivity` describe **self-hosted MCP** (running a service through LiteLLM, GitHub Copilot direct, etc.). This reference covers the **consumer side**: configuring Hermes to connect to a hosted third-party MCP provider that you don't run yourself.

## Concrete example: kapa.ai

[kapa.ai](https://docs.kapa.ai) sells hosted MCP servers for documentation retrieval. URL shape: `https://<subdomain>.mcp.kapa.ai/`. The subdomain is a project identifier you choose in their dashboard.

### Authentication

**Mechanism:** Bearer token via `Authorization` header on every request.

**Where to get the key:** kapa.ai dashboard → **Integrations** → **+ Add new integration** → choose **Hosted MCP Server** → fill in:
- Subdomain (becomes the URL prefix)
- Server name (the `server_name` label)
- **Authentication type → API key** (NOT Public-OAuth or Internal-OAuth — those are for browser-based end users)

The project API key is shown **once** after creation. Treat it as a backend secret — never put it in client-side code or browser-exposed bundles.

### Tool surface

Most hosted doc-retrieval MCPs (kapa.ai, Contextual.ai, Mintlify) follow the same shape:

- **Single semantic search tool**, named `search_<PRODUCT>_knowledge_sources` (kapa) or `<product>_search` (vendor-dependent). Example: `search_daily_docs_knowledge_sources`.
- Tool args: `query` (string), plus `_meta` for `top_k`, `max_chars`, `source_ids_include`, `source_group_ids_include`, `user.email`, `user.unique_client_id`.
- Return: structured list of `{source_url, content (Markdown)}` chunks.

### Rate limits (kapa.ai example — verify per provider)

| Auth type | Per-user limit | Per-team limit |
|---|---|---|
| Public (OAuth) | 300 req/day | 60 req/min |
| Internal (OAuth) | 300 req/day | 60 req/min |
| **API key (agent use)** | — | **60 req/min** |

The API key bucket is per-team. If you run WebUI + Telegram + cron agents concurrently, they all share the 60/min budget. Email `support@kapa.ai` for higher tiers.

## Hermes `~/.hermes/config.yaml` snippet

```yaml
mcp_servers:
  # ... existing self-hosted MCPs (mcpChores, mcpCode, mcpSway, github) ...

  daily_docs:                  # ← the server key, tools become mcp_daily_docs_*
    enabled: true
    url: https://daily-docs.mcp.kapa.ai/
    headers:
      Authorization: Bearer kapa_proj_xxxxxxxxxxxx
    timeout: 30
    connect_timeout: 15
```

**Mirror of the existing `github` MCP** (which is the canonical Bearer-auth example). Format is identical; only the URL and the `Authorization` value change.

## Verifying before adding to config

Run this probe from the command line to confirm the endpoint behaves and to extract the actual tool name (it'll be `search_<your_product>_knowledge_sources`, but the exact prefix depends on your project name):

```bash
curl -sS --max-time 15 -X POST https://<subdomain>.mcp.kapa.ai/ \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"probe","version":"0.1"}}}' \
  -w '\nHTTP %{http_code}\n'
```

- `HTTP 401 {"error":"invalid_token",...}` → missing or wrong Authorization header (expected; means URL is correct)
- `HTTP 405` to `GET /` → expected; MCP is POST-only
- Connection timeout → DNS / firewall / wrong subdomain

After adding to `~/.hermes/config.yaml`, restart the Hermes gateway (no hot-reload for native MCP). Tools appear as `mcp_<server_key>_<tool_name>` — check the Hermes startup logs.

## Generalizing to other hosted MCP providers

Pattern applies to any provider that meets all of:

1. Public Streamable HTTP MCP endpoint (URL ends in `/` or `/mcp`, POST JSON-RPC)
2. Bearer token auth via `Authorization` header
3. Project-scoped API key from a web dashboard

Known providers matching this shape as of 2026-06: **kapa.ai**, **Notion MCP** (different auth flow — OAuth, see Notion-specific notes), **Linear MCP**, **HubSpot MCP**, **Cloudflare MCP** (token in `Authorization: Bearer`).

Anti-pattern: don't try to put hosted MCPs behind LiteLLM's `/litellm/hermes/<name>/mcp` proxy. That's only for **self-hosted** MCPs you run yourself; hosted providers already have their own authentication and don't benefit from the proxy layer.

## Pitfall — token leakage to client code

If a "hosted MCP" gives you a JWT or project key with broad scope (admin), and you're tempted to call it from a frontend or mobile app: **don't**. Even if the docs say it's safe for "external users", the API key pattern is for **backend agents** (Hermes, your Pipecat bot, your cron job). For browser-side use, switch to the OAuth flow if the provider offers one.

For this user's setup: the kapa.ai key is stored in `~/.hermes/config.yaml` only, used by the Hermes gateway running on `x1tablet` and (when proxied via serverhome) other Hermes instances. Never embed it in client-side bundles or push it to public repos.