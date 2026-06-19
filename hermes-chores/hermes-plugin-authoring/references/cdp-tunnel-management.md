# CDP Tunnel Management Pattern

Pattern for managing SSH tunnels to remote Chrome CDP endpoints from a Hermes plugin.

## Architecture

```
Plugin provider (_ensure_cdp)
  │
  ├─ Local CDP (port 9222) available? → done
  │
  └─ Local CDP unavailable? → cdp_tunnel.sh start
      ├─ Remote CDP available? → autossh tunnel → local:9222
      └─ Remote CDP unavailable? → SSH → start Chrome → autossh tunnel → local:9222
```

## Tunnel Script Design

The tunnel script (`cdp_tunnel.sh`) must be:

1. **Self-bootstrapping** — reads config.yaml directly when no env vars are set
2. **Environment-variable compatible** — when called from Python provider, accepts `CDP_TUNNEL_*` vars
3. **Idempotent** — `start` when already running returns success
4. **Remote Chrome lifecycle** — starts/stops Chrome on the remote machine if needed

### Self-Bootstrapping

```bash
_load_from_hermes_config() {
  local output
  output=$(python3 -c "
import os, yaml, shlex
paths = [
    os.getenv('HERMES_HOME', os.path.expanduser('~/.hermes')) + '/config.yaml',
    os.path.expanduser('~/.hermes/config.yaml')
]
for p in paths:
    if os.path.isfile(p):
        cfg = yaml.safe_load(open(p))
        c = cfg.get('plugins', {}).get('cdp_extract', {})
        if c:
            mapping = {
                'remote_host': 'CDP_TUNNEL_REMOTE_HOST',
                'remote_user': 'CDP_TUNNEL_REMOTE_USER',
                'ssh_key': 'CDP_TUNNEL_SSH_KEY',
                'remote_port': 'CDP_TUNNEL_REMOTE_PORT',
                'local_port': 'CDP_TUNNEL_LOCAL_PORT',
                'remote_debug_port': 'CDP_TUNNEL_REMOTE_DEBUG_PORT',
                'tunnel_tool': 'CDP_TUNNEL_TOOL',
                'remote_chrome_bin': 'CDP_TUNNEL_REMOTE_CHROME_BIN',
                'remote_chrome_profile': 'CDP_TUNNEL_REMOTE_CHROME_PROFILE',
                'remote_chrome_args': 'CDP_TUNNEL_REMOTE_CHROME_ARGS',
                'agent_browser_bin': 'CDP_TUNNEL_AGENT_BROWSER_BIN',
                'hermes_py': 'CDP_TUNNEL_HERMES_PY',
            }
            for key, var in mapping.items():
                val = c.get(key)
                if val is not None and val != '':
                    print(f'{var}={shlex.quote(str(val))}')
            break
  " 2>/dev/null) || return 1
  [ -n "$output" ] && eval "$output"
}
```

### Critical Detail: `shlex.quote()`

Paths with spaces (like `/Applications/Google Chrome.app/...`) need shell quoting or `eval` breaks. Use Python's `shlex.quote()` when printing `VAR=VALUE` pairs from the inline Python. Without it, `eval "CDP_TUNNEL_REMOTE_CHROME_BIN=/Applications/Google Chrome.app/..."` splits on the space.

### Plugin-Side Integration

```python
def _load_cdp_config() -> dict:
    from hermes_cli.config import load_config
    return load_config().get("plugins", {}).get("cdp_extract", {}) or {}

def _build_tunnel_env(cfg: dict) -> dict:
    mapping = {
        "remote_host": "CDP_TUNNEL_REMOTE_HOST",
        "remote_user": "CDP_TUNNEL_REMOTE_USER",
        # ... all config keys mapped to env vars
    }
    return {var: str(cfg[k]) for k, var in mapping.items() if cfg.get(k)}

def _ensure_cdp() -> bool:
    if _check_local_cdp(): return True
    cfg = _load_cdp_config()
    if not cfg.get("remote_host"): return False
    env = os.environ.copy()
    env.update(_build_tunnel_env(cfg))
    subprocess.run([TUNNEL_SCRIPT, "start"], env=env, timeout=30)
    return _check_local_cdp()
```

## Registration: Slash Command

```python
# In __init__.py
ctx.register_command(
    name="cdp_tunnel",
    handler=lambda raw: _run_tunnel(raw.strip() or "status"),
    description="管理 CDP 隧道: status / start / stop / restart",
    args_hint="status|start|stop|restart",
)
```

## Key Decisions

- **One script, two call paths**: same `cdp_tunnel.sh` works standalone (reads config.yaml) or provider-called (gets env vars)
- **No duplicate hook**: old filesystem hook (`~/.hermes/hooks/start-remote-browser-tunnel/`) replaced by lazy init in `is_available()` / `extract()`
- **autossh preferred** for persistent tunnels; falls back to `ssh -f -N` when autossh unavailable
- **agent-browser** integration: optional, configurable via `agent_browser_bin` env var
