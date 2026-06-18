# LiteLLM MCP Behavior v1.85.1

Tested 2026-05-29 against `http://serverhome.tail2e6efb.ts.net/litellm/hermes`

## Endpoint Inventory

| Endpoint | Method | Response |
|----------|--------|----------|
| `/mcp/` | POST | 500 "MCP request failed" (empty hub) |
| `/mcp` | GET | 500 "MCP request failed" (empty hub) |
| `/v1/mcp/tools` | GET | 401 (key not registered) |
| `/v1/mcp/server` | GET | 401 (key not registered) |
| `/mcp-rest/tools/list` | POST | 405 Method Not Allowed |
| `/mcp-rest/test/connection` | GET | 405 Method Not Allowed |
| `/{server_name}/mcp` | POST | 200+SSE (when hub populated), 500 (empty hub) |

## Auth Behavior

- Every LiteLLM endpoint requires auth (even `/health`)
- The `x-litellm-api-key` header is the documented format in LiteLLM docs
- `Authorization: Bearer` also works — LiteLLM treats both identically
- Key `sk-UkP...u55g` is used as **provider API key** (for LLM calls) but NOT registered as a LiteLLM **virtual key** → 401 on admin/MCP management endpoints
- `/mcp/` endpoint accepts ALL auth headers but returns 500 regardless

## Key Observations

1. The 500 response includes no `details` field — empty string
2. No `Mcp-Session-Id` header is returned (because it never reaches session creation)
3. No `Content-Type: text/event-stream` ever returned — always `application/json`
4. Trailing slash matters: `/mcp` redirects (307) to `/mcp/`, but both produce same 500
5. Server is `uvicorn` (Python ASGI) — confirms LiteLLM is the responder

## Successful Configuration (2026-05-29)

After adding MCP server named `github` via LiteLLM Admin UI pointing to `https://api.githubcopilot.com/mcp/`:

### Working Endpoint
- URL: `http://serverhome.tail2e6efb.ts.net/litellm/hermes/github/mcp` (not `/mcp/` or `/toolset/github/mcp`)
- Auth: `x-litellm-api-key: Bearer sk-UkP...u55g`
- Accept: `application/json, text/event-stream` (required by GitHub Copilot upstream)

### Initialize Response (SSE format)
```
event: message
data: {"jsonrpc":"2.0","id":1,"result":{
  "protocolVersion":"2025-11-25",
  "capabilities":{"experimental":{},"prompts":{"listChanged":false},
    "resources":{"subscribe":false,"listChanged":false},
    "tools":{"listChanged":false}},
  "serverInfo":{"name":"litellm-mcp-server","version":"1.0.0"}}}
```

### Debug Headers (when hub populated)
```
x-mcp-debug-inbound-auth: x-litellm-api-key=Bearer**********************u55g
x-mcp-debug-oauth2-token: (none)
x-mcp-debug-auth-resolution: static-token
x-mcp-debug-outbound-url: https://api.githubcopilot.com/mcp/
x-mcp-debug-server-auth-type: bearer_token
```

### 406 Not Acceptable Error
GitHub Copilot MCP upstream requires `Accept: application/json, text/event-stream`:
```
HTTP/1.1 406 Not Acceptable
{"jsonrpc":"2.0","id":"server-error","error":{"code":-32600,
  "message":"Not Acceptable: Client must accept both application/json and text/event-stream"}}
```

## Hermes Native MCP Client Connection Failure Pattern

When Hermes native MCP client connects through LiteLLM gateway:

### Error Log Signature
```
2026-05-29 16:58:23,123 [ERROR] tools.mcp_tool - Failed to connect to MCP server 'github': Server error '500 Internal Server Error' for url 'http://serverhome.tail2e6efb.ts.net/litellm/hermes/github/mcp'
[... repeated 2 more times ...]
2026-05-29 16:59:00,456 [ERROR] tools.mcp_tool - MCP server 'github': All connection attempts failed after 3 retries
```

### Root Cause Analysis

| Factor | Impact |
|--------|--------|
| **Protocol version** | Hermes sends `mcp-protocol-version: 2025-03-26` (hardcoded in `tools/mcp_tool.py`); LiteLLM returns `2025-11-25`. LiteLLM may reject the outdated version header, causing 500. |
| **Auth header** | Hermes sends per-server `headers`, which become `Authorization` bearer by default. For LiteLLM proxy, MUST use `x-litellm-api-key` format. |
| **Circuit breaker** | After 3 retries, breaker opens (~60s). Even if the underlying issue is fixed, subsequent client calls are blocked until cooldown expires or gateway is restarted. |
| **Gateway state** | `hermes gateway run --replace` creates overlapping gateway processes. Two gateways maintain separate connection pools, both hitting LiteLLM simultaneously. |
| **User side vs agent side** | User's curl from the same machine returns 200+SSE; agent's curl returns 500. Possible causes: (a) circuit breaker in Hermes process intercepts even external curl via shared state; (b) dual gateway processes create connection pool exhaustion at LiteLLM; (c) stale DNS/connection reuse. |

### Clean-Restart Procedure

```bash
# 1. Kill ALL Hermes gateway processes
pkill -f 'hermes-gateway' 2>/dev/null || true
sleep 2

# 2. Verify none remaining
ps aux | grep hermes

# 3. Restart cleanly
systemctl --user restart hermes-gateway

# 4. Verify in logs
tail -f ~/.hermes/logs/errors.log
```

## Known Pitfalls

| Issue | Symptom | Fix |
|-------|---------|-----|
| Hub empty (no upstream registered) | 500 + no debug headers | Register MCP server via UI or config.yaml |
| Upstream error | 500 + outbound-url in debug headers | Check upstream server status |
| Missing Accept header | 406 Not Acceptable | Add `Accept: application/json, text/event-stream` |
| UI config not persistent | MCP works then stops after LiteLLM restart | Use config.yaml: `litellm_settings.mcp_servers` instead of UI |
| Missing trailing slash | 307 redirect | Both `/mcp` and `/mcp/` work after redirect |
| Key not in virtual key DB | 401 on admin endpoints | Register key via master key or Admin UI |

## OpenAPI Paths Discovered

```
/public/mcp_hub
/get/mcp_semantic_filter_settings
/update/mcp_semantic_filter_settings
/toolset/{toolset_name}/mcp
/{mcp_server_name}/mcp
/v1/mcp/tools
/v1/mcp/access_groups
/v1/mcp/network/client-ip
/v1/mcp/registry.json
/v1/mcp/server
/v1/mcp/server/health
/v1/mcp/server/register
/v1/mcp/server/submissions
/v1/mcp/...
```
