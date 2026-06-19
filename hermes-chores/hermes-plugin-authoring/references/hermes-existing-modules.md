# Hermes Existing Modules — Capability Audit Reference

This is a working reference for "does Hermes already have X?" queries during plugin authoring. Updated 2026-06-13 after the cdp_local.sh reinvention incident.

## How to use

Before writing any cross-cutting code in your plugin, run:

```bash
# 1. Find candidate modules
grep -rln "<keyword>" /home/dr/.hermes/hermes-agent --include="*.py" | head -20

# 2. Check skills for relevant patterns
ls /home/dr/.hermes/skills/local/ | grep -iE "<keyword>"

# 3. Read the top 1-2 candidates (look for module docstring, exported functions)
```

If the capability exists, **import and call it**. Don't reimplement.

## Capability map (curated 2026-06-13)

### Browser / CDP

| Capability | Module | Function | Notes |
|------------|--------|----------|-------|
| Launch local Chromium-family with debug port | `hermes_cli.browser_connect` | `try_launch_chrome_debug(port=9222)` | Cross-platform (Chrome/Chromium/Brave/Edge), 13 Linux install paths covered. Returns bool. Fire-and-forget (`start_new_session=True`). Profile: `~/.hermes/chrome-debug/`. |
| Detect installed browsers | `hermes_cli.browser_connect` | `get_chrome_debug_candidates(system)` | Returns ordered list of executable paths. |
| Check if CDP is reachable | `hermes_cli.browser_connect` | `is_browser_debug_ready(url, timeout=1.0)` | HTTP probe to `/json/version` and `/json`. |
| Print manual launch command | `hermes_cli.browser_connect` | `manual_chrome_debug_command(port, system)` | Returns shell-quoted command string for user to copy-paste. |
| Browser launch args | `hermes_cli.browser_connect` | `_chrome_debug_args(port)` | Returns list: `["--remote-debugging-port=PORT", "--user-data-dir=.../chrome-debug", "--no-first-run", "--no-default-browser-check"]`. |

### Config

| Capability | Module | Function | Notes |
|------------|--------|----------|-------|
| Load config.yaml | `hermes_cli.config` | `load_config()` | Returns merged user+defaults dict. |
| Read plugin section | inline after `load_config()` | `cfg.get("plugins", {}).get("<name>", {})` | Standard pattern. |
| Get Hermes home (profile-aware) | `hermes_constants` | `get_hermes_home()` | Returns Path. Respects `HERMES_HOME` env var. |

### Slash commands

| Capability | Module | Function | Notes |
|------------|--------|----------|-------|
| Register in-session slash command | plugin's `__init__.py` | `ctx.register_command(name, handler, description, args_hint)` | See "In-Session Slash Commands" section in SKILL.md. |
| Centralized command registry | `hermes_cli.commands` | `COMMAND_REGISTRY` (list of `CommandDef`) | Source of truth for built-in commands. |

### Session / persistence

| Capability | Module | Function | Notes |
|------------|--------|----------|-------|
| Session DB (SQLite + FTS5) | `hermes_state` | `SessionDB` class | FTS5-backed search. See `hermes-session-store` skill. |
| Cross-session memory | `agent/memory_manager` | (varies) | See `memory` skill. |

### MCP

| Capability | Module | Function | Notes |
|------------|--------|----------|-------|
| Native MCP client | built-in | `mcp__<server>__<tool>` naming | See `native-mcp` skill. |
| Connect external MCP server | `~/.hermes/config.yaml` | `mcp.servers` block | Auto-discovered. |

### Image / video / audio gen

| Capability | Module | Notes |
|------------|--------|-------|
| Image gen providers | `plugins/image_gen/<name>/` | Bundled: `openai`, `gemini`, etc. User plugins at `~/.hermes/plugins/image_gen/`. |
| Video gen | `plugins/video_gen/<name>/` | Similar pattern. |
| Audio (TTS, music) | `plugins/audio/`, `plugins/music/` | Provider ABC in `agent/audio_provider.py` etc. |

## Worked example: 2026-06-13 cdp-extract session

**Original plan (3 iterations)**:
1. Create `cdp_local.sh` (192 lines) with start/stop/restart/status, nohup + pidfile, env-var driven.
2. Generalize `cdp_tunnel.sh` to also handle local.
3. Re-plan to single generic script.

**After 3 plans, the user intervened**: "差一下hermes文档关于浏览器的部分，好像hermes有处理本地浏览器的机制，能用已有能力的用已有能力"

**The audit (took ~5 minutes)**:
```bash
# Found browser_connect.py
grep -rln "chrome.*--remote-debugging-port\|launch_chrome" /home/dr/.hermes/hermes-agent --include="*.py"
# → hermes_cli/browser_connect.py, cli.py, hermes_cli/cli_commands_mixin.py, ...
```

**Discovered**:
- `hermes_cli.browser_connect.try_launch_chrome_debug(port=9222)` — exactly the local Chrome launcher
- `hermes_cli.browser_connect.is_browser_debug_ready(url)` — CDP health check
- `hermes_cli.browser_connect._chrome_debug_args(port)` — same launch flags my script used
- `~/.hermes/chrome-debug/` — same profile path

**Result**: 192-line script deleted. `provider.py` got a 50-line change to call `try_launch_chrome_debug` + wait-for-CDP loop. End-to-end test (real Wikipedia extraction, 159 KB markdown) passed on first run.

**Time wasted on reinventing**: ~45 minutes across 3 plans, plus 7-task implementation cycle.

**Time to discover and integrate**: ~10 minutes after the user's prompt.

## Pitfalls when calling existing modules

1. **Don't modify them in-place**. The bundled `hermes_cli/browser_connect.py` is in the Hermes repo; modifying it could break other plugins. Override via a user plugin (e.g., a `hermes_cli_ext/browser_connect.py` if you need a different behavior).

2. **Imports may fail in some environments**. Wrap in try/except:
   ```python
   try:
       from hermes_cli.browser_connect import try_launch_chrome_debug
   except ImportError as exc:
       logger.warning("browser_connect not available: %s", exc)
       return False
   ```

3. **Profile path is `~/.hermes/chrome-debug/`, not the XDG default**. If your plugin assumes `~/.local/share/<plugin-name>/`, it will diverge from the rest of Hermes. Use `chrome_debug_data_dir()` from the same module for the canonical path.

4. **Process management is fire-and-forget**. `try_launch_chrome_debug` returns immediately and the Chrome process detaches (no PID tracking). To check liveness, call `is_browser_debug_ready(url)`. Don't try to track PIDs — it won't work.

5. **The functions are stable but undocumented**. Names and signatures can change. Always check the actual `hermes_cli/browser_connect.py` source before relying on internals (especially `_chrome_debug_args` which has a leading underscore — could become private).
