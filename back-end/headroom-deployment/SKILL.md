---
name: headroom-deployment
description: Deploy and maintain Headroom (headroomlabs-ai/headroom) context compression proxy for AI agents. Covers Docker setup, Hermes integration, upstream routing via serverhome reverse proxy, and troubleshooting.
trigger: When deploying, configuring, troubleshooting, or updating Headroom context compression proxy — or when integrating Headroom with Hermes Agent / LiteLLM.
source: hermes-built
---

# Headroom Deployment

## Overview

[Headroom](https://headroom-docs.vercel.app/docs) compresses AI agent context (tool outputs, logs, RAG chunks, files, conversation history) before it reaches the LLM. 60–95% token savings, same answers.

**Supported modes:** Library / Proxy / Agent wrap / MCP server.  
**For Hermes:** Use **Proxy mode** — transparent, zero code changes to Hermes internals.

**Two deployment patterns:**

| Pattern | Network | Port | When to use |
|---|---|---|---|
| **Portable (nginxNet)** | bridge (`nginxNet`) | `3999 → 8787` | Multi-machine, behind nginx reverse proxy, serverhome |
| **Local (host)** | `host` | `8788` | Single machine (x1tablet), Tailscale DNS needed inside container |

This skill documents both, with the portable pattern as the default.

---

## Portable Deployment (nginxNet) — Primary

### Defaults

| Parameter | Value |
|---|---|
| Port mapping | `3999 → 8787` |
| Network | `nginxNet` (external bridge) |
| Upstream | `http://100.66.66.203/litellm/headroom` |
| Restart | `unless-stopped` |
| Telemetry | `off` |

### Architecture

```
AI Agent / LLM client → HTTP :3999
  ↓
Headroom Proxy (container :8787, bridge)
  ↓  auto-compress tool outputs / logs / code / JSON / conversation history
  ↓  reversible (CCR — originals cached, LLM retrieves on demand)
  ↓  OPENAI_TARGET_API_URL
serverhome nginx reverse proxy (/litellm/headroom)
  ↓  injects LITELLM_MASTER_KEY
LiteLLM → DeepSeek / Anthropic / OpenAI / ...
```

### docker-compose.yml (template)

```yaml
services:
  headroom:
    container_name: headroom
    image: ghcr.io/chopratejas/headroom:latest
    restart: unless-stopped
    ports:
      - "${HOST_PORT:-3999}:8787"
    networks:
      - nginxNet
    environment:
      - OPENAI_TARGET_API_URL=http://100.66.66.203/litellm/headroom
      - HEADROOM_TELEMETRY=off
    healthcheck:
      test: ["CMD", "curl", "--fail", "--silent", "http://127.0.0.1:8787/readyz"]
      interval: 30s
      timeout: 5s
      start_period: 20s
      retries: 3

networks:
  nginxNet:
    external: true
```

### .env pattern

```env
# Override port
# HOST_PORT=3999

# Override upstream
# OPENAI_TARGET_API_URL=http://other-host/litellm/hermes

# Override mode
# HEADROOM_MODE=optimize
```

### Workspace structure

```
project.docker/
├── docker-compose.yml   ← service definition (port 3999, nginxNet)
├── .env                 ← overrides without touching compose
├── README.md            ← deployment guide for AI agents
├── run.sh               ← start/stop/logs/status/update/shell/verify
└── config/              ← reserved for future Headroom config files
```

### run.sh patterns

Provide at minimum: `start`, `stop`, `restart`, `logs`, `status`, `update`, `shell`, `verify`.

The `status` command curls the health endpoint and displays version + upstream URL.
The `verify` command runs a full smoke test: health → chat completions → responses API → stats.

### Client configuration (Hermes)

```yaml
# Hermes config.yaml — custom_providers section
custom_providers:
- api_key: <your-key>
  base_url: http://<host>:3999    # Points to Headroom proxy
  name: litellm
```

### Multi-machine migration

This `project.docker/` directory is a self-contained deployment unit:

```bash
# On target machine:
docker network create nginxNet 2>/dev/null || true
scp -r headroom.docker/ target:~/
cd headroom.docker
# Edit .env if needed
docker compose up -d
```

---

## Local Deployment (host network) — Alternative

Used when the machine does Tailscale DNS resolution and there's no shared nginxNet bridge.

```yaml
services:
  headroom:
    network_mode: host
    environment:
      - OPENAI_TARGET_API_URL=http://serverhome.tail2e6efb.ts.net/litellm/hermes
      - HEADROOM_TELEMETRY=off
    healthcheck:
      test: ["CMD", "curl", "--fail", "--silent", "http://127.0.0.1:8788/readyz"]
    command: ["--port", "8788"]
```

Tailscale hostnames resolve inside host network. No port mapping — Headroom binds directly to `0.0.0.0:8788`. Avoid when 8787 (Hermes WebUI) is on the same host.

---

## Verification

```bash
# Health
curl http://localhost:3999/health

# Chat completions
curl http://localhost:3999/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-v4-flash","messages":[{"role":"user","content":"hi"}],"max_tokens":20}'

# Responses API (Hermes codex_responses mode)
curl http://localhost:3999/v1/responses \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-v4-flash","input":"hi","max_output_tokens":30}'

# Compression stats
curl http://localhost:3999/stats
```

Compression stats are initially zero. Real tool-use sessions (grep, file reads, logs) trigger compression above the 500-token threshold.

---

## Pitfalls

- The `upstream.url` field in `/health` is a **placeholder health-probe URL**, not the real route. It often shows `https://api.anthropic.com` even when the live request goes to `https://api.minimaxi.com/v1`. To find the true upstream, send one real `POST /v1/chat/completions` and read the `x-litellm-model-api-base` response header — that's authoritative.
- `/v1/models` returns no `max_context_length` field — only `id`/`object`/`created`/`owned_by`. Headroom cannot self-report context length; clients like Hermes must use their own lookup table.
- `mode` in `/health` can flip between `cache` and `token` after restarts (the run.sh template hardcodes one; the actual mode comes from env var). If the doc says `cache` but you see `token` in the JSON, the env var was changed at restart — not a bug.
- **"Provider returned an empty stream with no finish_reason" is a network/Tailscale symptom, not a headroom bug.** The proxy itself is healthy (`/health` returns 200, real chat calls return in <10s end-to-end). The empty-stream error happens when the Tailscale path to `serverhome.tail2e6efb.ts.net` drops a frame mid-stream. The fix is on the routing path (or to bypass Tailscale and use the Tailscale IP directly), not on the headroom container.
The Docker image's default health check hardcodes `127.0.0.1:8787`. When running on a different port (common), the health check silently fails with exit code 7.

**Fix:** Always override the health check in docker-compose.yml (see templates).

### 2. sed is dangerous for Hermes config edits

When reverting base_url changes in `config.yaml` with sed, the URL pattern (`serverhome.tail2e6efb.ts.net/litellm/hermes`) appears in **many** places: 6+ aux service configs + MCP URLs + the custom_providers entry. sed replaces ALL occurrences indiscriminately.

**Fix:** Use `execute_code` with Python for targeted line-by-line replacement, or use `patch` with precise surrounding context. Never use `sed -i` with a URL that appears more than once in the file.

### 3. Compression won't show data immediately

`min_tokens_to_crush: 500` means small test requests (5–30 tokens) won't trigger compression. Real tool-use sessions with thousands of tokens are needed before stats show meaningful data.

---

## References

- Repo: [headroomlabs-ai/headroom](https://github.com/headroomlabs-ai/headroom) ⭐ 47K+
- Docs: https://headroom-docs.vercel.app/docs
- Docker image: `ghcr.io/chopratejas/headroom:latest`
- Current version (as of deploy): v0.27.0
- LiteLLM native callback: `headroom.integrations.litellm_callback.HeadroomCallback` (use when you can modify LiteLLM startup; for serverhome this is read-only)
