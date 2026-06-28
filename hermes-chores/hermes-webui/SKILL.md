---
name: hermes-webui
category: local_share/hermes-chores
description: |
  Deploy, configure, and troubleshoot Hermes WebUI — the self-hosted browser
  interface for Hermes Agent. Covers initial setup, path resolution, Python
  interpreter selection, and common pitfalls.
tags:
  - hermes
  - webui
  - deployment
  - configuration
  - frontend
---

# Hermes WebUI

## Overview

The Hermes WebUI is a self-hosted browser interface for Hermes Agent. It depends
on the gateway's `api_server` platform (port 8643 by default).

## Prerequisites

- Hermes gateway running (systemd user service)
- Node.js 18+ (for the frontend build)
- Python 3.10+ (for the backend daemon)

## Setup

See the [Hermes WebUI docs](https://hermes-agent.nousresearch.com/docs/webui)
for installation instructions.

## Key Files

| File | Purpose |
|------|---------|
| `~/.hermes/.env` | API_SERVER_HOST, API_SERVER_PORT, API_SERVER_KEY |
| `~/.hermes/local/hermes-webui/` | WebUI installation directory |
| `~/.hermes/local/hermes-webui/ctl.sh` | Start/stop/status daemon wrapper |

## Common Pitfalls

### API Server refuses to start

The gateway may report `active` while `api_server` silently fails to bind port
8643. Always check the journal:

```bash
journalctl --user -u hermes-gateway --no-pager | grep api_server
```

**Typical error:**
```
Refusing to start: API_SERVER_KEY is a placeholder or too short (<16 chars)
for a network-accessible bind.
```

**Causes and fixes:**

| Cause | Fix |
|-------|-----|
| `API_SERVER_HOST=0.0.0.0` + key < 16 chars | Increase key to 16+ characters, or bind to `127.0.0.1` |
| Placeholder key like `fuck_key` or `Kino501502` | Use a proper ≥ 16-char key |
| Key changed but gateway not restarted | `systemctl --user restart hermes-gateway` |

Full debugging workflow in [`references/api-server-troubleshooting.md`](references/api-server-troubleshooting.md).

### Python interpreter not found

If `python` isn't aliased to `python3`, ctl.sh may fail. Either symlink
`python → python3` or override in ctl.sh.

### WebUI can't reach API server

Verify the api_server is actually listening (`ss -tlnp | grep 8643`) and the
CORS origins include the WebUI's URL.

## Related References

- [`references/gateway-hook-auto-launch.md`](references/gateway-hook-auto-launch.md)
  — Auto-start WebUI on gateway startup
- [`references/api-server-troubleshooting.md`](references/api-server-troubleshooting.md)
  — Debugging the API server port binding
