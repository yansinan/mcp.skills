# wechat-route Agent Management — Session Reference

## Current Agent Config (June 2026)

**serverhome**: `100.66.66.203` (Tailscale)
**wechat-route port**: `19990`
**Shared iLink token**: `6dace489c620@im.bot:0600009b...`

| Agent | Port | Host | Aliases |
|-------|------|------|---------|
| hermes | 19998 | 127.0.0.1 | hermes, h |
| browser.hermes | 19997 | 127.0.0.1 | 小刘, browser |
| helix | 19996 | 127.0.0.1 | helix, @h |
| openclaw | 19999 | 0.0.0.0 | openclaw, claw |
| x1tablet | 19995 | 127.0.0.1 | x1, 小叉, tablet |

## agent.json Location

`/home/dr/workspace/wechat-route/agents.json` on serverhome (mounted read-only into container at `/app/agents.json:ro`).

## Restart Commands

```bash
# wechat-route on serverhome
ssh dr@serverhome
cd ~/workspace/wechat-route
docker compose restart wechat-route

# Hermes gateway on any agent machine
systemctl --user restart hermes-gateway
```

## Verification

```bash
# Check proxy route table + heartbeats
docker logs wechat-route --tail 30

# Check agent gateway for Weixin errors
journalctl --user -u hermes-gateway --since "2 minutes ago" | grep -iE "weixin|poll error"
```

## SSH Non-Interactive PATH Fix

Problem: `ssh serverhome docker ...` bypasses `~/.local/bin/docker` wrapper
because non-interactive bash does not read `.bashrc`/`.profile`.

Fix (already applied on serverhome):
1. `.bashrc`: Moved `export PATH="$HOME/.local/bin:$PATH"` **before** the `case $-` interactive guard
2. `.profile`: Added `export BASH_ENV="$HOME/.bashrc"` so `bash -c` reads `.bashrc`

This ensures non-interactive SSH commands get the same PATH as interactive logins.
