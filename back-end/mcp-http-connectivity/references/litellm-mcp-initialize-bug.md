# LiteLLM v1.85.1 MCP `initialize` Handshake Bug

## Discovery Session

**Date:** 2026-05-29
**Setup:** Hermes Agent → LiteLLM v1.85.1 gateway → GitHub Copilot MCP upstream
**Endpoint:** `http://serverhome.tail2e6efb.ts.net/litellm/hermes/github/mcp`
**Auth header:** `x-litellm-api-key: Bearer sk-UkP...u55g`

## Symptoms

```bash
# ✅ tools/list works — returns SSE with 21 GitHub tools
curl -s -X POST http://serverhome.tail2e6efb.ts.net/litellm/hermes/github/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "x-litellm-api-key: Bearer sk-UkP...u55g" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
# → SSE event:message / data:{"tools":[...21 tools...]}

# ❌ initialize fails for ALL protocol versions
for pv in "2024-11-05" "2025-03-26" "2025-06-18" "2025-11-25"; do
  curl -s -X POST http://serverhome.tail2e6efb.ts.net/litellm/hermes/github/mcp \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "x-litellm-api-key: Bearer sk-UkP...u55g" \
    -H "mcp-protocol-version: $pv" \
    -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"$pv\",\"capabilities\":{},\"clientInfo\":{\"name\":\"test\",\"version\":\"1.0\"}}}"
# → {"error":"MCP request failed","details":""}
done
```

## Debug Headers (from user curl)

When the user ran the curl with `x-litellm-mcp-debug: true`, the response headers showed:

```
x-mcp-debug-inbound-auth: x-litellm-api-key=Bearer***
x-mcp-debug-auth-resolution: static-token
x-mcp-debug-outbound-url: https://api.githubcopilot.com/mcp/
x-mcp-debug-server-auth-type: bearer_token
```

This confirmed LiteLLM was routing successfully to GitHub Copilot MCP. The 500 comes from LiteLLM processing the initialize response, not from the upstream.

## Why Hermes Can't Connect

The Hermes MCP client (`tools/mcp_tool.py`) follows the standard Streamable HTTP flow:

1. Open SSE read/write stream via `streamable_http_client()`
2. Call `session.initialize()` (line 1585) → sends initialize JSON-RPC
3. LiteLLM returns 500 → Client retries 3 times → Gives up
4. Circuit breaker opens (~60s cooldown)

Since `session.initialize()` is hardcoded in the SDK, there's no way to skip it per-server without modifying Hermes source code.

## Config Overrides That Don't Help

| Override | Result |
|----------|--------|
| `mcp-protocol-version: 2025-11-25` in headers | Still 500 — the issue is the JSON-RPC method, not version negotiation |
| `x-litellm-mcp-debug: true` in headers | Debug headers don't appear on 500 responses |
| Different Accept formats | Still 500 — `Accept` only affects non-initialize calls |

## Workaround

Connect Hermes native MCP **directly** to the upstream (e.g. GitHub Copilot MCP with PAT):

```yaml
mcp_servers:
  github:
    url: https://api.githubcopilot.com/mcp/
    headers:
      Authorization: "Bearer ${GITHUB_PAT}"
    enabled: true
```

## When to Re-test

- LiteLLM upgrades: check if `initialize` handling is fixed
- Test command: the curl above with `method: "initialize"`
- Expected success: returns `InitializeResult` JSON, not 500
