# Chrome DevTools Protocol (CDP) Integration via Python

How to control local Chrome via CDP websocket for page fetching, rendering, and content extraction.

## Quick Start: Connect to Local Chrome

```python
import asyncio, json, requests, websockets

CDP_URL = "http://127.0.0.1:9222"

async def get_page_html(url: str) -> str:
    # 1. Get browser-level websocket URL
    resp = requests.get(f"{CDP_URL}/json/version", timeout=5)
    browser_ws = resp.json()["webSocketDebuggerUrl"]

    # 2. Create a new tab
    async with websockets.connect(browser_ws, max_size=None) as ws:
        await ws.send(json.dumps({
            "id": 1, "method": "Target.createTarget",
            "params": {"url": "about:blank"},
        }))
        r = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        target_id = r["result"]["targetId"]

    # 3. Get the tab's websocket URL
    targets = requests.get(f"{CDP_URL}/json", timeout=5).json()
    target_ws = next(t["webSocketDebuggerUrl"] for t in targets if t["id"] == target_id)

    # 4. Connect to tab, navigate, get HTML
    async with websockets.connect(target_ws, max_size=None) as ws:
        await _cdp_send(ws, "Page.enable", 1)
        await _cdp_send(ws, "Page.navigate", {"url": url}, 2)

        title = await _cdp_send(ws, "Runtime.evaluate",
                                {"expression": "document.title"}, 3)
        html = await _cdp_send(ws, "Runtime.evaluate",
                               {"expression": "document.documentElement.outerHTML",
                                "returnByValue": True}, 4)

        html_text = html["result"]["result"].get("value", "")
        page_title = title["result"]["result"].get("value", "")

    # 5. Clean up
    requests.get(f"{CDP_URL}/json/close/{target_id}", timeout=5)
    return page_title, html_text


def _cdp_send(ws, method: str, msg_id: int, params: dict | None = None) -> dict:
    """Send CDP command, filter events, return matching response."""
    import json
    payload = {"id": msg_id, "method": method}
    if params:
        payload["params"] = params
    async def _do():
        await ws.send(json.dumps(payload))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
            msg = json.loads(raw)
            if msg.get("id") == msg_id:
                return msg
    return asyncio.get_event_loop().run_until_complete(_do())
```

## Critical CDP Patterns

### 1. Always Filter Responses by Message ID

CDP interleaves **events** (no `id` field) with **responses** (have matching `id`). Never take the first message after sending a command:

```python
# ❌ WRONG — next message might be an event
await ws.send(json.dumps({"id": 1, "method": "Page.navigate", ...}))
resp = json.loads(await ws.recv())  # Might be Page.frameStartedNavigating event!

# ✅ CORRECT — loop until we get our response
await ws.send(json.dumps({"id": 1, "method": "Page.navigate", ...}))
while True:
    msg = json.loads(await ws.recv())
    if msg.get("id") == 1:
        return msg  # This is the actual response
    # else: it's an event — skip
```

### 2. Page.loadEventFired is Deprecated

In Chrome 120+, `Page.loadEventFired` returns `-32601 method not found` in most cases. The page loads naturally — `Runtime.evaluate` executed after `Page.navigate` will wait for the page to render. No explicit load-wait is needed for simple HTML extraction. For JS-heavy pages, add a small `asyncio.sleep()` before evaluating.

### 3. Create + Close Targets

Always create a dedicated target for each operation and close it when done. Don't reuse existing tabs:

```python
# Create
target_id = await create_target(browser_ws)

try:
    # ... do work ...
finally:
    requests.get(f"{CDP_URL}/json/close/{target_id}", timeout=5)
```

### 4. Available CDP Port

Default port is 9222. Verify connectivity:
```bash
curl -s http://127.0.0.1:9222/json/version | jq '.Browser'
```

### 5. Runtime.evaluate with returnByValue

For getting DOM content, always set `returnByValue: True`:
```python
{"expression": "document.documentElement.outerHTML", "returnByValue": True}
```

Without it, the result is a remote object reference, not the actual text.

## Common CDP Commands for Page Extraction

| Method | Params | Purpose |
|--------|--------|---------|
| `Page.enable` | `{}` | Enable page events (needed for navigation) |
| `Page.navigate` | `{"url": "..."}` | Navigate to URL |
| `Runtime.evaluate` | `{"expression": "document.title"}` | Get page title |
| `Runtime.evaluate` | `{"expression": "document.documentElement.outerHTML", "returnByValue": True}` | Get full HTML |
| `Target.createTarget` | `{"url": "about:blank"}` | Create new tab |
| `Page.printToPDF` | `{}` | Generate PDF of page |

## Python Dependencies

- `requests` — for REST endpoints (`/json/version`, `/json`, `/json/close/{id}`)
- `websockets` — for WebSocket CDP communication (Hermes bundle includes `websockets==15.x`)
- NOT `websocket-client` (different package)

## Provider Use (Hermes Plugin)

When implementing CDP-based extraction in a `WebSearchProvider`:

1. Mark `extract()` as `async def` (CDP is inherently async via websockets)
2. Check `is_available()` by hitting `/json/version` — cheap HTTP call, no network to third parties
3. Keep the `extract()` return as a flat list of dicts (not wrapped in `success/data`)
