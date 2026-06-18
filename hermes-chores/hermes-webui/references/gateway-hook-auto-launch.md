# Gateway Hook: Auto-Launch Hermes WebUI

Created during a session where the user wanted Hermes WebUI to start automatically
whenever the gateway starts, without manual intervention.

## Structure

```
~/.hermes/hooks/webui-launcher/
├── HOOK.yaml       # Declares gateway:startup event listener
└── handler.py      # Async subprocess launch of ctl.sh start
```

## HOOK.yaml

```yaml
name: webui-launcher
description: "Start Hermes WebUI on gateway startup"
events:
  - gateway:startup
```

## handler.py

```python
"""Gateway startup hook: start Hermes WebUI via ctl.sh."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path

CTL_SCRIPT = Path.home() / ".hermes" / "local" / "hermes-webui" / "ctl.sh"
HOOK_NAME = "webui-launcher"


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    print(f"[hook][{HOOK_NAME}][{ts}] {msg}", flush=True)


async def handle(event_type: str, context: dict) -> None:
    """Start Hermes WebUI as daemon on gateway startup."""
    if not CTL_SCRIPT.exists():
        _log(f"ctl.sh not found at {CTL_SCRIPT}")
        return

    proc = await asyncio.create_subprocess_exec(
        str(CTL_SCRIPT), "start",
        cwd=str(CTL_SCRIPT.parent),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
    except asyncio.TimeoutError:
        proc.kill()
        _log("ctl.sh timed out after 10s")
        return

    out = stdout.decode(errors="replace").strip()
    err = stderr.decode(errors="replace").strip()

    if proc.returncode != 0:
        _log(f"ctl.sh exited {proc.returncode}: {err or out}")
    elif "already running" in out:
        _log("already running")
    else:
        last = out.splitlines()[-1] if out else ""
        _log(f"started: {last}")
```

## Design Decisions

- **Use `ctl.sh start` (not `start.sh`):** `ctl.sh` is the proper daemon manager —
  nohup + background, PID file, log file, idempotent start (checks already-running
  before spawning). `start.sh` runs bootstrap in foreground and won't survive logout.
- **`_log()` helper with `[hook][名称][时间]` prefix:** custom print-based logging
  so output is distinguishable in gateway logs. Format: `[hook][webui-launcher][2026-05-29T18:20:00] message`.
  Reused across all gateway hooks for consistency.
- **Async subprocess (`asyncio.create_subprocess_exec`):** non-blocking — handler
  returns immediately, gateway startup not delayed.
- **10s timeout:** `ctl.sh start` may need to SSH in the tunnel case, so timeout
  is generous but bounded.
- **Error-log only on failure:** hook errors never crash the gateway (caught by
  HookRegistry.emit()).

## How It Works

1. Gateway starts → `HookRegistry.discover_and_load()` scans `~/.hermes/hooks/`
2. Finds `webui-launcher/HOOK.yaml` + `handler.py` → imports the module
3. Registers `handle()` for the `gateway:startup` event
4. After gateway init completes → `hooks.emit("gateway:startup", ...)`
5. `handle()` runs → `ctl.sh start` → WebUI is up (or prints "already running")

No config file changes needed — just create the hook directory and restart the gateway.
