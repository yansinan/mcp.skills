# Service Lifecycle Design for Hermes Plugins

When a Hermes plugin manages a local service (Chrome, SSH tunnel, watcher daemon), the lifecycle design affects reliability, debuggability, and user experience.

## Keep-Alive Pattern

The service, once started, should remain running until explicitly stopped. The typical shape:

```bash
./cdp_local.sh start    # starts + stays running
./cdp_local.sh status   # reports running state
cdp extraction runs...  # plugin uses the already-running service
./cdp_local.sh stop     # only when user/admin asks
```

**Do NOT auto-stop** the service when the script exits or when the plugin finishes an extraction. A Service in Hermes should match the user's expectation that "first call sets it up, subsequent calls reuse it, explicit teardown is optional."

## Auto-Recovery on Crash

Services crash (OOM, segfault, kernel OOM killer). The lifecycle script should detect and recover:

```bash
# On start, when a stale PID file exists:
if [ ! -f "$PIDFILE" ]; then
    # fresh start
elif ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "[service]PIDFILE_STALE pid=$pid — cleaned up"
    rm -f "$PIDFILE"
    # then start fresh
else
    echo "[service]ALREADY_UP port=$port"  # idempotent, exit 0
    return 0
fi
```

**Recovery invariant:** After `kill -9`, a subsequent `start` should work without manual cleanup — stale PID file removal + fresh process launch.

## Idempotent Start

Calling `start` when the service is already running should:
- Detect the running instance (port probe or PID check)
- Print "already up" (not "started")
- Exit 0
- NOT restart

## pidfile Reliability Tradeoffs

| Approach | Reliability | Complexity | Use Case |
|----------|-------------|------------|----------|
| pidfile + `kill -0` | Medium | Low | Quick scripts, dev/test |
| Socket/port probe | High | Medium | Services with TCP ports |
| systemd unit | Very High | High | Production daemons |
| cgroup / PID namespace | Very High | High | Containers, CI |

**pidfile weaknesses:**
- Process can die externally → stale pidfile → false "not running"
- PID can be reused → wrong process killed
- Race condition on startup (pidfile written before process is ready)

**When to tolerate:** Quick scripts, dev tools, single-user desktop. The keep-alive + crash recovery pattern mitigates the worst stale-pidfile scenarios.

**When to upgrade:** Multi-user services, production systems, long-running daemons. Use systemd or socket activation.

For Hermes plugins on desktop Linux, pidfile + port-probe dual check is a pragmatic middle ground:
- PID file for exact process tracking
- Port/HTTP probe for functional verification
- Combined: if PID alive but port down → stale; if port up but no pidfile → adopt

## Env Var > Config > Default Priority

Always implement three-tier priority for service configuration:

1. **Environment variable** (highest) — user-set on command line: `CDP_LOCAL_PORT=9223 ./script.sh`
2. **Config file** — read from `~/.hermes/config.yaml` via self-bootstrap
3. **Hardcoded default** — bash `:--` expansion as last resort

```bash
# In the script, AFTER _load_from_hermes_config (tier 2):
PORT="${CDP_LOCAL_PORT:-9222}"   # tier 3
```

The bootstrap function must NOT override an already-set env var (otherwise tier 1 silently becomes tier 2). Use `if var in os.environ: continue` in the Python heredoc.
