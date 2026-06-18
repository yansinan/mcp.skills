---
name: hermes-webui
description: "Deploy, configure, and troubleshoot Hermes WebUI — the self-hosted browser interface for Hermes Agent. Covers initial setup, path resolution, Python interpreter selection, and common pitfalls."
version: 1.1.0
author: agent
metadata:
  hermes:
    tags: [hermes, webui, deployment, configuration, frontend]
---

# Hermes WebUI

Hermes WebUI is a lightweight, dark-themed web app providing a browser interface to Hermes Agent with 1:1 CLI parity. No build step — just Python + vanilla JS.

**Repo:** `~/.hermes/local/hermes-webui/` (or wherever it's cloned)
**Server:** `server.py` (entry point, started via `bootstrap.py`)
**Config:** `.env` file in the repo root (see `.env.example`)

## Setup Steps

### 0. Clone the repo

```bash
mkdir -p ~/.hermes/local
cd ~/.hermes/local
GIT_TERMINAL_PROMPT=0 git clone https://github.com/nesquena/hermes-webui.git
```

**⚠ `GIT_TERMINAL_PROMPT=0` is required here** — without it, git may hang indefinitely waiting for a credential prompt in headless/hermes-terminal environments that lack a credential helper. This happens even for public repos if `credential.helper` is misconfigured.

**⚠ Repo is at `nesquena/hermes-webui`, not `NousResearch/hermes-webui`.** The Hermes WebUI is maintained by @nesquena, not under the Nous Research org. Searching GitHub for "hermes-webui NousResearch" will 404.

### 1. Check project structure

```bash
ls ~/.hermes/local/hermes-webui/
```

Key files:
- `bootstrap.py` — launcher; resolves paths, creates venv if needed, spawns server
- `server.py` — the actual web server
- `start.sh` — shell wrapper that sources `.env` and runs `bootstrap.py`
- `ctl.sh` — daemon manager: `start|stop|restart|status|logs` (preferred for production/background use)
- `.env.example` — template for local config
- `requirements.txt` — `pyyaml>=6.0`, `cryptography>=42.0`

### 2. Resolve Hermes Agent path

Bootstrap auto-discovers the agent in this order:
1. `HERMES_WEBUI_AGENT_DIR` env var
2. `$HERMES_HOME/hermes-agent/`
3. `../hermes-agent/` (sibling dir)
4. `~/.hermes/hermes-agent/`
5. `~/hermes-agent/`
6. From the `hermes` CLI shebang (walk parents looking for `run_agent.py`)

Verify manually:
```bash
ls /home/dr/.hermes/hermes-agent/run_agent.py
```

### 3. Pick the right Python interpreter

The WebUI needs an interpreter that can import BOTH:
- `yaml` (from PyYAML)
- `run_agent.AIAgent` (from Hermes Agent)

The agent's own venv usually satisfies both:
```bash
# Check if agent venv has both deps
~/.hermes/hermes-agent/venv/bin/python3 -c "import yaml; import run_agent; print('OK')"
```

If it does, use it as `HERMES_WEBUI_PYTHON`. Otherwise bootstrap auto-creates a local `.venv` with PyYAML + cryptography and sets `PYTHONPATH` to find the agent.

### 4. Create `.env`

Copy `.env.example` and fill in resolved values. At minimum:

```env
HERMES_WEBUI_AGENT_DIR=/home/dr/.hermes/hermes-agent
HERMES_WEBUI_PYTHON=/home/dr/.hermes/hermes-agent/venv/bin/python3
HERMES_WEBUI_HOST=127.0.0.1
HERMES_WEBUI_PORT=8787
HERMES_WEBUI_STATE_DIR=/home/dr/.hermes/webui
HERMES_WEBUI_DEFAULT_WORKSPACE=/home/dr
```

All env vars are optional — auto-discovery fills in blanks. But explicitly setting `HERMES_WEBUI_AGENT_DIR` and `HERMES_WEBUI_PYTHON` avoids confusion.

### 5. Verify bootstrap dry-run

```bash
cd ~/.hermes/local/hermes-webui
export HERMES_WEBUI_AGENT_DIR=/home/dr/.hermes/hermes-agent
export HERMES_WEBUI_PYTHON=/home/dr/.hermes/hermes-agent/venv/bin/python3
$HERMES_WEBUI_PYTHON -c "
import sys; sys.path.insert(0, '.')
from bootstrap import discover_agent_dir, discover_launcher_python, ensure_python_has_webui_deps
agent_dir = discover_agent_dir()
print(f'Agent dir: {agent_dir}')
py = discover_launcher_python(agent_dir)
print(f'Python: {py}')
py2 = ensure_python_has_webui_deps(py, agent_dir)
print(f'Final: {py2}')
"
```

All three should resolve without errors.

### 6. Launch

```bash
cd ~/.hermes/local/hermes-webui
./ctl.sh start              # daemon (preferred — PID file, log, health check)
# or
./start.sh                  # background (simple)
# or
python3 bootstrap.py        # foreground (debug)
```

Then open `http://127.0.0.1:8787`. Use `./ctl.sh status` / `stop` / `logs` to manage.

## Config Reference

| Env var | Default | What it does |
|---------|---------|-------------|
| `HERMES_WEBUI_AGENT_DIR` | auto-discovered | Path to Hermes Agent checkout (has `run_agent.py`) |
| `HERMES_WEBUI_PYTHON` | auto-discovered | Python interpreter to run server.py |
| `HERMES_WEBUI_HOST` | `127.0.0.1` | Bind address (loopback only = safe) |
| `HERMES_WEBUI_PORT` | `8787` | Listen port |
| `HERMES_WEBUI_STATE_DIR` | `~/.hermes/webui` | Sessions, workspaces, logs |
| `HERMES_WEBUI_DEFAULT_WORKSPACE` | (none) | Dir shown on first launch |
| `HERMES_WEBUI_DEFAULT_MODEL` | (none) | Override the active Hermes model |
| `HERMES_WEBUI_BOT_NAME` | `Hermes` | Assistant display name |
| `HERMES_HOME` | `~/.hermes` | Base Hermes state dir |
| `HERMES_CONFIG_PATH` | `~/.hermes/config.yaml` | Hermes config path |

## Auto-Launch via Gateway Hook

Create a gateway event hook to start WebUI automatically whenever the Hermes gateway starts. Uses `ctl.sh start` for proper daemon management (PID tracking, idempotent start, dedicated log file).

```bash
mkdir -p ~/.hermes/hooks/webui-launcher
```

**`~/.hermes/hooks/webui-launcher/HOOK.yaml`:**
```yaml
name: webui-launcher
description: "Start Hermes WebUI on gateway startup"
events:
  - gateway:startup
```

**`~/.hermes/hooks/webui-launcher/handler.py`:**
```python
import asyncio
from datetime import datetime, timezone
from pathlib import Path

CTL_SCRIPT = Path.home() / ".hermes" / "local" / "hermes-webui" / "ctl.sh"
HOOK_NAME = "webui-launcher"

def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    print(f"[hook][{HOOK_NAME}][{ts}] {msg}", flush=True)

async def handle(event_type: str, context: dict) -> None:
    if not CTL_SCRIPT.exists():
        _log(f"ctl.sh not found at {CTL_SCRIPT}")
        return
    proc = await asyncio.create_subprocess_exec(
        str(CTL_SCRIPT), "start", cwd=str(CTL_SCRIPT.parent),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
    except asyncio.TimeoutError:
        proc.kill(); _log("ctl.sh timed out"); return
    out = stdout.decode(errors="replace").strip()
    err = stderr.decode(errors="replace").strip()
    if proc.returncode != 0:
        _log(f"ctl.sh exited {proc.returncode}: {err or out}")
    elif "already running" in out:
        _log("already running")
    else:
        _log(f"started: {out.splitlines()[-1] if out else ''}")
```

Gateway 重启后 WebUI 会自动启动。完整说明见 `references/gateway-hook-auto-launch.md`。

## Pitfalls

### State dir doesn't exist
Bootstrap auto-creates it. If manual: `mkdir -p $(HERMES_WEBUI_STATE_DIR)`.

### HERMES_WEBUI_PYTHON can't import AIAgent
The interpreter can run WebUI deps but can't see Hermes Agent. Two fixes:
- Set `HERMES_WEBUI_PYTHON` to the agent venv's Python
- Or let bootstrap auto-create a `.venv` — it sets `PYTHONPATH` to include the agent dir

### Port already in use
Change port: edit `HERMES_WEBUI_PORT` in `.env`, or pass as arg: `./start.sh 8788`

### Health check fails after launch
Check the log:
```bash
cat ~/.hermes/webui/bootstrap-8787.log
```
Common cause: wrong Python interpreter, or agent dependency missing.

### Server dies on SSH logout
Use `ctl.sh stop` + `ctl.sh start` for proper nohup-daemon (PID file, log management). The `start.sh` wrapper runs bootstrap synchronously and won't survive logout. `ctl.sh` wraps bootstrap with `nohup` + `&`.

## See Also

- `docs/onboarding-agent-checklist.md` for multi-session first-run flows
- `docs/supervisor.md` for systemd / launchd / supervisord setup
- `docs/troubleshooting.md` for diagnostic flows
- `docs/docker.md` for container deployment
- `docs/wsl-autostart.md` for WSL2 autostart
- `references/gateway-hook-auto-launch.md` for gateway hook auto-launch details
