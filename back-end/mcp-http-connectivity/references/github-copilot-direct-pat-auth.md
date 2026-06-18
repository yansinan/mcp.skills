# GitHub Copilot MCP — Direct PAT Auth (Session 2026-05-29)

## Context

LiteLLM v1.85.1 MCP gateway cannot handle the `initialize` JSON-RPC handshake.
Hermes MCP client always sends `initialize` first → 500 → give up.
Solution: bypass LiteLLM, connect Hermes native MCP directly to GitHub Copilot MCP.

## Config

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  github:
    url: https://api.githubcopilot.com/mcp/
    headers:
      Authorization: "Bearer ghp_..."
    enabled: true
```

## Auth source

The PAT lives in `~/.hermes/.env` as `MCP_GITHUB_API_KEY=ghp_...`.

## Protocol version

GitHub Copilot MCP accepts `2025-03-26` — no override needed.
The `mcp-protocol-version` header override (`2025-11-25`) was added but unnecessary
for direct connection (the LiteLLM gateway needed it, but direct doesn't).

## Verification commands

```bash
# tools/list — confirms server is alive
curl -s -X POST https://api.githubcopilot.com/mcp/ \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# initialize — confirms Hermes can complete the handshake
curl -s -X POST https://api.githubcopilot.com/mcp/ \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```

## Key findings

| Check | Result |
|-------|--------|
| initialize | ✅ Returns `protocolVersion: 2025-03-26`, `serverInfo: github-mcp-server` |
| tools/list | ✅ 21+ tools via SSE |
| Tool count | 50 tools registered as `mcp_github_*` |
| Auth format | `Authorization: Bearer ghp_...` |
| Accept header required | Yes — must include both `application/json, text/event-stream` |
| Direct connect PAT timeout | Client token expired — regenerate at https://github.com/settings/tokens |

## Lazy MCP discovery

`discover_mcp_tools()` is NOT called at gateway startup. It's triggered by:
- Agent session initialization
- Manual call via `python3 -c "from tools.mcp_tool import discover_mcp_tools; discover_mcp_tools()"`
- `hermes tools` command

To verify MCP connection from Hermes:
```bash
cd ~/.hermes/hermes-agent && source venv/bin/activate
python3 -c "
from tools.mcp_tool import discover_mcp_tools, _servers
tools = discover_mcp_tools()
print(f'{len(tools)} tools, servers: {list(_servers.keys())}')
"
```
