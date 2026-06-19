---
name: wechat-route-agent-management
description: "Add, remove, or reconfigure Hermes agents behind the wechat-route multi-agent iLink proxy. Covers agents.json, .env WEIXIN_BASE_URL, container restart, and verification."
version: 1.0.0
author: user-created
tags: [wechat, weixin, ilink, wechat-route, multi-agent, gateway]
---

# wechat-route Agent Management

Manage Hermes agents behind the **wechat-route** reverse proxy. The wechat-route sits between iLink (Tencent WeChat Bot API) and multiple Hermes instances, sharing one iLink token across agents.

## Architecture

```
iLink(微信)
  ↕ (poll_loop — runs inside wechat-route container)
router.py + proxy.py (port 19990)
  ├── /hermes        → 127.0.0.1:19998  ← Hermes Agent (local to serverhome)
  ├── /helix         → 127.0.0.1:19996  ← helix@Hermes
  ├── /x1tablet      → 127.0.0.1:19995  ← x1tablet@Hermes
  ├── /openclaw      → 0.0.0.0:19999    ← OpenClaw (external)
  └── /browser.hermes → 127.0.0.1:19997 ← browser@Hermes
```

- **proxy.py**: Path-based reverse proxy on port 19990. Forwards `/{agent_name}/ilink/bot/*` → `agent_host:agent_port/ilink/bot/*`
- **router.py**: Per-agent proxy servers + iLink poll loop. Proxies `sendmessage` to real iLink (with tag prefix) and returns queued messages on `getupdates`
- Both run inside the **same Docker container** (entrypoint: `bin/entrypoint.sh`)

## Adding a New Agent

### 1. agents.json (on serverhome)

Path: `~/workspace/wechat-route/agents.json`

Add an agent entry:
```json
{
  "name": "x1tablet",
  "host": "127.0.0.1",
  "port": 19995,
  "tag": "[x1tablet]",
  "enabled": true,
  "aliases": ["x1", "小叉", "tablet"]
}
```

Rules:
- **`host`**: Always `127.0.0.1` for agents on the same Docker network (except OpenClaw which uses `0.0.0.0` because it's an external instance)
- **`port`**: Container-internal, does not need to be exposed in docker-compose.yml. Pick an unused port in the 19990+ range
- **`tag`**: Prepended to all outbound text messages via this agent
- **`aliases`**: Used for group routing. Short names like `x1`, `小叉` work as wechat-route @-mentions

Optionally add the agent to a group:
```json
"groups": {
  "all": {
    "members": ["hermes", "x1tablet", ...],
    "aliases": ["both", "all", "@all"]
  }
}
```

### 2. The new agent's .env (on the agent's own machine)

Set the Weixin adapter to poll through wechat-route:
```
WEIXIN_BASE_URL=http://serverhome:19990/x1tablet
```
Replace `x1tablet` with the agent name from agents.json.

All other WEIXIN_* vars (account_id, token, cdn, etc.) stay the same — the iLink token is shared.

### 3. Restart wechat-route (on serverhome)

```bash
cd ~/workspace/wechat-route && docker compose restart wechat-route
```

### 4. Restart the new agent's Hermes gateway

```bash
systemctl --user restart hermes-gateway
```

## Verification

Check wechat-route proxy logs for the new route and heartbeat:
```bash
docker logs wechat-route --tail 5
```

Look for:
- `wechat-route proxy listening on :19990` — including `/x1tablet -> 127.0.0.1:19995` in the route list
- `AgentTracker: heartbeat from x1tablet` — confirms the agent is polling
- `[x1tablet] 上线` — agent tracker notification

On the agent's machine, check gateway logs for Weixin adapter status:
```bash
journalctl --user -u hermes-gateway --since "1 minute ago" | grep -iE "weixin|poll error"
```
No "poll error" lines = adapter connected cleanly.

## Removing an Agent

1. Remove the agent entry from `agents.json` (and from any groups)
2. Restart wechat-route container
3. (Optional) Stop the agent's gateway

## Pitfalls

- **`host: 0.0.0.0`** → proxy.py internally rewrites to `127.0.0.1` for forwarding. Only use `0.0.0.0` for external agents that need Docker-to-host port mapping
- **agent name → path prefix**: The agent `name` field becomes the URL path prefix. Must match the `WEIXIN_BASE_URL` path suffix on the agent's machine
- **Ports are container-internal**: No need to add new ports to `docker-compose.yml` or `EXPOSE` in the Dockerfile — 19996-19999 all work without exposure
- **Error: `Backend refused` (502)**: The router.py proxy server on that port hasn't started yet. Wait a few seconds for container startup
- **No `WEIXIN_GROUP_POLICY` related**: That warning is harmless — it fires for every agent using the same iLink bot identity
- **WEIXIN_DM_POLICY blocks all users on new agents**: When you copy another agent's `.env`, the DM policy is likely `pairing`. The new gateway instance has no paired users, so every user gets `WARNING gateway.run: Unauthorized user: ... on weixin`. Fix: set `WEIXIN_DM_POLICY=open` (or add admin users to `WEIXIN_ALLOWED_USERS`). The iLink token is shared, but DM policy is evaluated per-gateway-instance — each new agent must configure its own access.
- **router.py logs go to file, not docker logs**: `proxy.py` (path routing) logs to stdout (visible via `docker logs`), but `router.py` (iLink poll loop, per-agent proxy, message routing) logs only to `logs/wechat-route.log` inside the container. To see message routing, use `docker exec wechat-route tail -20 /app/logs/wechat-route.log`.
