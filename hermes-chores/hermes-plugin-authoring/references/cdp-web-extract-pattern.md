# CDP Web Extract Plugin Pattern

This reference captures the pattern built in session 2026-05-29: a web extract provider that fetches full HTML via local Chrome DevTools Protocol (port 9222), then extracts Markdown via a Node.js Readability + Turndown pipeline.

## Architecture

```
User: web_extract(urls)
  │
  ▼ Python provider (sync dispatcher)
  │
  ├── Step 1: CDP fetch
  │   ├── _get_browser_ws_url()    — GET /json/version → ws://127.0.0.1:9222/...
  │   ├── Target.createTarget      — Create new tab (about:blank)
  │   ├── Page.navigate(url)       — Navigate to target URL
  │   ├── Runtime.evaluate(...)    — Get document.title + outerHTML
  │   └── _close_target()          — GET /json/close/{id}
  │
  ├── Step 2: read_down (Node.js subprocess)
  │   ├── stdin: {"html":"...","url":"...","options":{...}}
  │   ├── linkedom → Readability → article {text, html, title, ...}
  │   ├── Turndown → article HTML → markdown
  │   └── stdout: {"markdown":"...","text":"...","html":"...",...}
  │
  └── Return: list of PageExtractionResult dicts
```

## CDP Python Helper Functions

### WebSocket Management

```python
# Browser-level WS URL
def _get_browser_ws_url() -> str:
    resp = requests.get("http://127.0.0.1:9222/json/version", timeout=5)
    return resp.json()["webSocketDebuggerUrl"]

# Create a tab target
async def _create_target(browser_ws: str) -> tuple[str, str]:
    async with websockets.connect(browser_ws, max_size=None) as ws:
        await ws.send(json.dumps({
            "id": 1, "method": "Target.createTarget",
            "params": {"url": "about:blank"},
        }))
        resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        target_id = resp["result"]["targetId"]
    # Get target's individual WS URL
    for t in requests.get("http://127.0.0.1:9222/json", timeout=5).json():
        if t["id"] == target_id:
            return target_id, t["webSocketDebuggerUrl"]

# Close target
def _close_target(target_id: str) -> None:
    requests.get(f"http://127.0.0.1:9222/json/close/{target_id}", timeout=5)
```

### CDP Command with Event Filtering

```python
async def _cdp_send(ws, method, params=None, msg_id=1):
    """Send CDP command, skip interleaved events, return matching response."""
    payload = {"id": msg_id, "method": method}
    if params:
        payload["params"] = params
    await ws.send(json.dumps(payload))
    while True:
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
        if msg.get("id") == msg_id:  # Response (has matching id)
            return msg
        # Events have "method" but no "id" — skip silently
```

### Fetch Page HTML

```python
async def _fetch_raw_html(url: str) -> dict:
    """Open page via CDP, return {url, html, title, error}."""
    browser_ws = _get_browser_ws_url()
    target_id, target_ws = await _create_target(browser_ws)
    try:
        async with websockets.connect(target_ws, max_size=None) as ws:
            await _cdp_send(ws, "Page.enable", msg_id=1)
            await _cdp_send(ws, "Page.navigate", {"url": url}, msg_id=2)
            # page loads automatically — no Page.loadEventFired (deprecated)
            title_resp = await _cdp_send(ws, "Runtime.evaluate",
                {"expression": "document.title"}, msg_id=3)
            html_resp = await _cdp_send(ws, "Runtime.evaluate",
                {"expression": "document.documentElement.outerHTML",
                 "returnByValue": True}, msg_id=4)
            return {
                "url": url,
                "title": title_resp.get("result",{}).get("result",{}).get("value",""),
                "html": html_resp.get("result",{}).get("result",{}).get("value",""),
            }
    finally:
        _close_target(target_id)
```

## read_down Node.js Module

Directory: `<plugin_dir>/read_down/`

### Dependencies (package.json)

```json
{
  "dependencies": {
    "@mozilla/readability": "^0.5.0",
    "linkedom": "^0.18.12",
    "turndown": "^7.2.0",
    "turndown-plugin-gfm": "^1.0.2"
  }
}
```

### Key Design Decisions

- **`linkedom` over `jsdom`** — lighter (2.7MB vs 4.3MB), 60 fewer transitive deps
- **Turndown takes HTML strings directly** — no need to wrap in JSDOM before turndown
- **Readability needs a DOM** — `@mozilla/readability` is zero-dependency; pass it `linkedom`'s `document`
- **GFM plugin** — enables tables, strikethrough, task lists in Markdown output
- **CLI via stdin/stdout** — Python feeds `{"html":"...","url":"...","options":{...}}` via JSON stdin, reads result from stdout

### CLI Interface

```bash
echo '{"html":"<html>...</html>","url":"https://...","options":{"debugTrace":true}}' \
  | node index.js
# stdout → {"markdown":"...","text":"...","html":"...","title":"...","length":3632}
```

### Python Bridge (subprocess)

```python
import json, subprocess

def _call_readdown(html, url="", debug=False):
    payload = {"html": html, "url": url, "options": {"debugTrace": debug}}
    proc = subprocess.run(
        ["node", "/path/to/read_down/index.js"],
        input=json.dumps(payload),
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        return {"text": "", "error": f"read-down-exit-{proc.returncode}"}
    return json.loads(proc.stdout)
```

## Alignment with hermes-sidebar

When building an extract pipeline intended for future parallel replacement with hermes-sidebar code:

| Parameter | Must Match |
|-----------|-----------|
| Output interface keys | `text`, `markdown?`, `html?`, `title?`, `byline?`, `dir?`, `length?`, `lang?`, `error?` |
| Optional fields | `None` (not `""`) when absent |
| Turndown config | `headingStyle: "atx"`, `codeBlockStyle: "fenced"`, `bulletListMarker: "-"`, `linkStyle: "inlined"`, `hr: "---"` |
| Remove selectors | `script, style, noscript, nav, footer, iframe` |
| Readability config | `maxElemsToParse: 12000`, `charThreshold: 140`, `keepClasses: false` |
| Fallback | `fallbackHtmlToMarkdown()` — regex handles h1-6/strong/em/code/a/p/br/li |

## Known Issues

- **WeChat articles (mp.weixin.qq.com)**: Cannot extract — login wall/JS-rendered content. CDP loads the page but Readability returns null.
- **SegmentFault articles**: Title extracts correctly but Readability may return null depending on page structure. Fallback markdown is minimal.
- **CDP reliability**: Occasional empty HTML return — likely page load timing. Use `Page.setLifecycleEventsEnabled` + `lifecycleEvent("load")` for reliable loading.
- **`awaitPromise` works with macrotasks**: The earlier belief that `Runtime.evaluate(awaitPromise=True)` cannot handle setTimeout was WRONG. The real issue was websocket buffer pollution by leftover navigation events. When using proper msg-id filtering (`_cdp_send` helper), `setTimeout(3000)` inside an async function works perfectly (verified: 3.01s elapsed).
- **Scroll with inline setTimeout + awaitPromise**: The single-command JS scroll technique works reliably when:
  1. Page load is confirmed via `lifecycleEvent("load")` before any scroll command
  2. All navigation events are consumed (or properly filtered by `_cdp_send`)
  3. `document.scrollingElement.scrollHeight` is used (not `document.body`)

