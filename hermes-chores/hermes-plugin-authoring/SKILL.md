---
name: hermes-plugin-authoring
description: "Create, override, and manage Hermes Agent plugins — covers plugin.yaml, __init__.py register() pattern, PluginContext registration methods, discovery order, activation rules, and override semantics for all plugin types."
version: 1.0.0
author: Hermes Agent (learned)
tags: [hermes, plugins, development, override]
---

# Hermes Plugin Authoring

Create, override, and manage Hermes Agent plugins. Covers the complete plugin lifecycle: structure, registration, activation, and override.

## When to Use

- User asks to **create a new plugin** or **override a bundled plugin**
- User wants to understand how plugins are discovered and loaded
- User is developing a **web search/extract provider**, **model provider**, **memory provider**, **context engine**, **image/video gen provider**, or any other plugin type
- User reports a plugin not loading or being picked up

## Plugin Types

| Kind | Description | Bundle auto-load? | User opt-in? |
|------|-------------|-------------------|--------------|
| `backend` | Pluggable backend for core tools (web, image_gen, browser, etc.) | ✅ Bundled auto-load | ✅ `plugins.enabled` |
| `standalone` | Own hooks/tools | ❌ | ✅ `plugins.enabled` |
| `platform` | Gateway messaging adapter (IRC, Discord, etc.) | ✅ Bundled auto-load | ✅ `plugins.enabled` |
| `exclusive` | Memory/context engine providers | N/A (category config) | Via `<category>.provider` |
| `model-provider` | Inference backend (OpenAI, Anthropic, etc.) | N/A (lazy discovery) | Via `model.provider` |

## Required Files

A plugin is a directory with at least these files:

```
plugins/<category>/<name>/
├── plugin.yaml        # Metadata — REQUIRED
├── __init__.py        # register(ctx) entry point — REQUIRED
└── provider.py        # Implementation — convention, not enforced
```

### plugin.yaml Fields

```yaml
name: my-plugin                    # Unique identifier
version: 1.0.0                     # Semver
description: "What it does"        # Brief
author: YourName                   # Or organization
kind: backend                      # One of: standalone, backend, platform, exclusive, model-provider
provides_web_providers:            # Only for web plugins
  - my-provider-name
```

Supported `provides_*` fields (use the one matching your plugin category):
- `provides_web_providers` — for web search/extract backends
- `provides_memory_providers` — for memory backends
- `provides_context_engines` — for context compression

### __init__.py — register() Pattern

```python
"""Short docstring."""

from __future__ import annotations

from plugins.web.<name>.provider import MyProvider

def register(ctx) -> None:
    """Register plugin components."""
    ctx.register_web_search_provider(MyProvider())
```

### PluginContext Registration Methods

| Method | Plugin Type |
|--------|-------------|
| `ctx.register_web_search_provider(provider)` | Web search/extract |
| `ctx.register_memory_provider(provider)` | Memory backend |
| `ctx.register_context_engine(engine)` | Context compression |
| `ctx.register_image_gen_provider(provider)` | Image generation |
| `ctx.register_video_gen_provider(provider)` | Video generation |
| `ctx.register_browser_provider(provider)` | Cloud browser |
| `ctx.register_tool(name, schema, handler)` | Custom tools |
| `ctx.register_hook(event, handler)` | Event hooks |

## Discovery Order (Override Semantics)

Sources are scanned in this order, **later wins on name collision**:

1. **Bundled** — `<repo>/plugins/<category>/<name>/`
2. **User** — `$HERMES_HOME/plugins/<category>/<name>/` **(overrides bundled)**
3. **Project** — `./.hermes/plugins/<category>/<name>/` (overrides user)
4. **Pip entry-point** — installed packages

**Override key insight:** Drop a plugin with the same name in `$HERMES_HOME/plugins/<category>/<name>/` and Hermes loads it instead of the bundled one. No repo changes needed.

## Activation Rules

### Bundled `kind: backend` / `platform` plugins
Auto-loaded. No config needed — they "just work" out of the box.

### User plugins (all kinds including backend)
**Must** be explicitly enabled in `config.yaml` under `plugins.enabled`:

```yaml
plugins:
  enabled:
    - web/my-plugin           # path-derived registry key
```

Run `hermes plugins enable web/my-plugin` to set it interactively.

### Exclusive plugins (memory, context engine)
Activated via category config key, not `plugins.enabled`:
```yaml
memory:
  provider: my-memory-provider
context_engine:
  provider: my-context-engine
```

### Model-provider plugins
Discovered lazily on first `get_provider_profile()` / `list_providers()` call. Override is last-writer-wins via `register_provider()`.

## Verification Steps

1. Check the plugin is scanned: `hermes plugins list` → see your plugin in the list
2. Verify it's enabled: check `plugins.enabled` in config.yaml
3. Check registration: `hermes doctor` or test the relevant tool
4. For web providers: `/reset` then call `web_search` / `web_extract` in a fresh session

## ⚠️ Critical Pitfalls

### 1. User plugins MUST use RELATIVE imports (the #1 gotcha)

The plugin system loads user plugins via `importlib` into the `hermes_plugins.<slug>` namespace, NOT under the `plugins.` package. Using an absolute `plugins.web.xxx` import will fail with `No module named 'plugins.web.xxx'`.

**WRONG** (works only for bundled plugins):
```python
# ❌ FileNotFoundError for user plugins
from plugins.web.my_plugin.provider import MyProvider
```

**CORRECT** (works for both):
```python
# ✅ Relative import — correctly resolves from the plugin's directory
from .provider import MyProvider
```

### 2. User plugins (even `kind: backend`) are NOT auto-loaded

Bundled backend plugins auto-load; user plugins of the same kind must be in `plugins.enabled`. Use the path-derived key (`web/my_plugin`), not the `plugin.yaml` name.

```yaml
plugins:
  enabled:
    - web/my_plugin       # ✅ correct — uses directory path
    # - web-my-plugin     # ❌ wrong — only works for standalone plugins
```

### 3. `hermes config set` stores lists as YAML STRINGS

```bash
hermes config set plugins.enabled '["a", "b"]'
# → stores literally '["a", "b"]' as a YAML string, not a list
```

The test `hermes plugins list` won't show your plugin enabled. Fix by editing `config.yaml` directly:

```yaml
plugins:
  enabled:
    - disk-cleanup
    - web/my_plugin
```

### 4. Plugin name vs config name — two different identifiers

| Field | What it is | Example |
|-------|-----------|---------|
| `plugins.enabled` key | Path-derived: `category/directory_name` | `web/cdp_extract` |
| `web.extract_backend` value | The provider's `.name` property | `cdp-extract` (hyphens OK) |

Don't confuse them — the config key uses the directory path, the backend config uses the provider's `.name`.

### General pitfalls

- **After adding/reloading plugins**, run `/reset` or start a new session — tools/skills don't update mid-conversation
- **`kind: model-provider`** is a separate discovery path (`providers/__init__.py`), not the general plugin loader
- **do NOT modify bundled plugin files** — drop user copy at `$HERMES_HOME/plugins/` instead
- **name collision** across categories is fine (`image_gen/openai` and `tts/openai` don't collide); collision within the same category is what triggers override

### 6. User plugin override vs bundled branch divergence (the "why isn't my change working" gotcha)

You hack on a bundled plugin in a git branch (`feat/xxx`), make changes, verify them. But the runtime loads the **user override** at `~/.hermes/plugins/<category>/<name>/` — not the bundled copy. Your branch changes are invisible.

**Diagnosis:**
```bash
# 1. Check which version is actually loaded at runtime
from hermes_cli.plugins import PluginManager
pm = PluginManager(); pm.discover_and_load()
p = get_provider('<provider-name>')
print(f'{type(p).__module__}.{type(p).__qualname__}')

# 2. Diff bundled vs user override
diff ~/.hermes/hermes-agent/plugins/<category>/<name>/provider.py \
     ~/.hermes/plugins/<category>/<name>/provider.py

# 3. If they differ massively, the user override is the runtime version
```

**Fix:** Apply your changes to the user override at `~/.hermes/plugins/<category>/<name>/`, or remove the user override to let the bundled version take effect. After changing: restart gateway (`systemctl --user restart hermes-gateway`) then `/reset`.

### 7. CDP-extract returns empty content when raw CDP works — isolation drill

When the CDP-extract plugin's `extract()` returns `content: ""` / `raw_content: ""` but a raw CDP websocket test (bypassing the plugin) succeeds:

```python
# Step 1: Verify CDP infrastructure
# curl localhost:9222/json/version → should return 200
# curl localhost:9222/json → list tabs

# Step 2: Raw CDP test (bypass plugin layer)
# See references/cdp-extract-debugging.md for the full script

# Step 3: Trace the plugin call chain
# extract() → _fetch_raw_html(url) → _call_readdown(html, url)
# Each function's output feeds the next. Print intermediate values:
#   raw = await _fetch_raw_html(url)  → check raw["html"] length
#   rd = _call_readdown(html=raw["html"], url=url) → check rd keys
```

**Common failure modes:**
- `_fetch_raw_html` connects to CDP and navigates correctly (title populated) but returns empty `"html"`: check `Page.setLifecycleEventsEnabled` and `lifecycleEvent(name='load')` handling — on Chrome 148+ `Page.loadEventFired` is removed
- `_call_readdown` returns empty because `raw["html"]` was already empty (see above)
- The result dict uses `"html"` key but downstream expects `"content"` / `"raw_content"` — field name mismatch between bundled and user plugin versions

## Quick Verification

After creating a user plugin, verify it loads and registers:

```bash
cd ~/.hermes && source hermes-agent/venv/bin/activate && python3 -c "
import sys
sys.path.insert(0, '/home/dr/.hermes/hermes-agent')

from hermes_cli.plugins import PluginManager
from agent.web_search_registry import get_provider, list_providers

pm = PluginManager()
pm.discover_and_load()

# Check plugin was loaded
for key, loaded in pm._plugins.items():
    if 'MY_PLUGIN' in key:
        print(f'{key}: enabled={loaded.enabled} error={loaded.error}')

# Check provider registered
p = get_provider('MY_PROVIDER_NAME')
if p:
    print(f'{p.name}: search={p.supports_search()} extract={p.supports_extract()} available={p.is_available()}')
"
```

### CDP-Based Provider Patterns (absorbed from hermes-plugin-development)

#### Page Loading — The Correct Sequence

```python
await _cdp_send(ws, "Page.enable", msg_id=1)
await _cdp_send(ws, "Page.setLifecycleEventsEnabled", {"enabled": True}, msg_id=2)

await ws.send(json.dumps({"id": 3, "method": "Page.navigate", "params": {"url": url}}))
nav_ok = load_ok = False
while not (nav_ok and load_ok):
    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
    if msg.get("id") == 3:
        nav_ok = True
        if "error" in msg: raise RuntimeError(...)
    elif msg.get("method") == "Page.lifecycleEvent" and \
         msg.get("params", {}).get("name") == "load":
        load_ok = True
```

**Why NOT other methods:**
- `Page.loadEventFired` → removed in Chrome 148+
- `Page.frameStoppedLoading` → fires too early, before images/scripts complete
- `Page.lifecycleEvent(name="init" or "DOMContentLoaded")` → fires before all resources

#### awaitPromise + Macrotasks

**`Runtime.evaluate(expression, awaitPromise=True) CAN handle setTimeout/setInterval/macrotasks.**

**Why earlier attempts failed:** websocket buffer pollution from navigation events. Always filter by `msg.get("id") == sent_id`.

#### SSH Tunnel Self-Bootstrap Script

For plugins needing remote Chrome, the tunnel script reads config from config.yaml:

```bash
# In cdp_tunnel.sh:
_load_from_hermes_config() {
  output=$(python3 -c "
import os, yaml, shlex
cfg = yaml.safe_load(open(os.path.expanduser('~/.hermes/config.yaml')))
c = cfg.get('plugins', {}).get('cdp_extract', {})
for key, var in {'remote_host': 'CDP_TUNNEL_REMOTE_HOST', ...}.items():
    if c.get(key): print(f'{var}={shlex.quote(str(c[key]))}')
")
  [ -n "$output" ] && eval "$output"
}
```

#### Plugin-Managed SSH Tunnel

The provider calls the tunnel script lazily in `is_available()` / `extract()`:

```python
def _ensure_cdp() -> bool:
    if _check_local_cdp(): return True
    cfg = _load_cdp_config()
    if not cfg.get("remote_host"): return False
    subprocess.run([TUNNEL_SCRIPT, "start"],
        env={**os.environ, **_build_tunnel_env(cfg)}, timeout=30)
    return _check_local_cdp()
```

#### In-Session Slash Commands

Register custom slash commands from a plugin:

```python
def register(ctx) -> None:
    ctx.register_web_search_provider(CDPProvider())
    ctx.register_command(
        name="cdp_tunnel",
        handler=_handle_cdp_tunnel,
        description="Manage CDP tunnel: status / start / stop / restart",
        args_hint="status|start|stop|restart",
    )
```

Handler signature: `fn(raw_args: str) -> str | None`. Can be sync or async.

#### Output Interface (PageExtractionResult)

When building an extract provider, match this shape:

```python
{
    "text": str,           # Always present
    "markdown": None|str,  # Omit when not available
    "html": None|str,      # Readability article HTML
    "title": None|str,
    "byline": None|str,
    "dir": None|str,
    "length": None|int,
    "lang": None|str,
    "error": None|str,     # Present only on failure
}
```

Set `markdown`/`html` to `None` (not `""`) when absent.

## References

See `references/web-search-provider.md` for the full `WebSearchProvider` ABC interface and response shape contract.
See `references/plugin-yaml-reference.md` for all plugin.yaml fields and schema.
See `references/cdp-integration.md` for Chrome DevTools Protocol integration patterns (page fetch, websocket, event filtering).
See `references/cdp-tunnel-management.md` (from hermes-plugin-development) for SSH tunnel orchestration patterns.
See `references/cdp-web-extract-pattern.md` (from hermes-plugin-development) for CDP web extraction provider details.

## Templates

See `templates/basic-web-provider/` for a minimal working web search provider plugin template.

## CDP-Based Provider Patterns

When building a `WebSearchProvider` that uses Chrome DevTools Protocol (port 9222):

### extract() Must Be async def

CDP uses WebSockets natively (async). Mark `extract()` as `async def`:

```python
async def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
    for url in urls:
        result = await _fetch_via_cdp(url)
        results.append(result)
    return results  # flat list, NOT wrapped in {"success": ..., "data": ...}
```

The dispatcher detects coroutines via `inspect.iscoroutinefunction` and awaits automatically.

### extract() Return Shape

`extract()` returns a **flat list** of per-URL result dicts, each with optional `error` field:

```python
[
    {"url": str, "title": str, "content": str, "raw_content": str, "metadata": dict},
    {"url": str, "error": str},  # per-URL failure
]
```

NOT wrapped in `{"success": True, "data": [...]}` — that envelope is for `search()` only.

### CDP Event Filtering

CDP interleaves events (no `id`) with command responses (have `id`). Always loop to skip events:

```python
async def _cdp_send(ws, method, params, msg_id):
    payload = {"id": msg_id, "method": method, "params": params}
    await ws.send(json.dumps(payload))
    while True:
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
        if msg.get("id") == msg_id:
            return msg  # This is the response
        # Events (no "id") are silently skipped
```

### Page.loadEventFired — Do NOT Use, and Do NOT Use frameStoppedLoading Either

Chrome 120+ removed `Page.loadEventFired`. But `Page.frameStoppedLoading` is also unreliable — it fires when the frame finishes its initial render, NOT when all resources (images, scripts, stylesheets) are fully loaded.

**Correct approach:** Use `Page.setLifecycleEventsEnabled(true)` before navigation, then wait for `Page.lifecycleEvent(name="load")`:

```python
await _cdp_send(ws, "Page.setLifecycleEventsEnabled", {"enabled": True}, msg_id)

# Navigate manually (not via _cdp_send) to read both response and events
await ws.send(json.dumps({"id": msg_id, "method": "Page.navigate", "params": {"url": url}}))
navigate_ok = load_ok = False
while not (navigate_ok and load_ok):
    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
    if msg.get("id") == msg_id:
        navigate_ok = True
    elif msg.get("method") == "Page.lifecycleEvent" and msg.get("params", {}).get("name") == "load":
        load_ok = True  # window.onload fired — all resources loaded
```

Reference: https://chromedevtools.github.io/devtools-protocol/tot/Page/#event-lifecycleEvent

### Test Without Full Hermes Loop

```bash
cd ~/.hermes && source hermes-agent/venv/bin/activate && python3 -c "
import asyncio

async def test():
    from agent.web_search_registry import get_provider
    from hermes_cli.plugins import PluginManager
    pm = PluginManager()
    pm.discover_and_load()
    p = get_provider('cdp-extract')
    results = await p.extract(['https://httpbin.org/html'])
    print(results[0].get('content', '')[:200])

asyncio.run(test())
"
```

### CDP Scroll Pattern

Use a **single `Runtime.evaluate` with a JS async IIFE + `awaitPromise: True`**. Chrome's message loop continues running while CDP awaits a Promise — `setTimeout(3000)` returns in exactly 3.01s.

```python
scroll_js = """
    (async () => {
        const el = document.scrollingElement;
        const step = 80;
        let pos = 0, bottomCount = 0;

        await new Promise((resolve) => {
            const iv = setInterval(() => {
                pos += step;
                window.scrollTo(0, pos);
                if (window.scrollY + window.innerHeight >= el.scrollHeight) {
                    bottomCount++;
                    if (bottomCount >= 2) {
                        clearInterval(iv);
                        setTimeout(() => { resolve(el.scrollHeight); }, 3000);
                    }
                }
            }, 50);
        });
        return el.scrollHeight;
    })()
"""
resp = await _cdp_send(ws, "Runtime.evaluate", {
    "expression": scroll_js,
    "awaitPromise": True,
    "returnByValue": True,
}, msg_id=msg_id)
```

**The real reason earlier attempts failed: websocket buffer pollution.** After navigating, residual CDP events remain in the receive buffer. Without message-ID-based filtering (`_cdp_send` matching on `msg.id`), `await ws.recv()` reads a stale event instead of the Runtime.evaluate response. Always use message-ID filtering for ALL commands after navigation.

Key points:
- Use `document.scrollingElement.scrollHeight` — NOT `document.body.scrollHeight` (standards mode scrolls `<html>`)
- Use `Page.setLifecycleEventsEnabled(true)` + wait for `lifecycleEvent(name="load")` — NOT `frameStoppedLoading` (too early) or `Page.loadEventFired` (deprecated)
- Check both `"error"` and `"exceptionDetails"` in the response
- See `skill: browser-content-extraction` for full reference