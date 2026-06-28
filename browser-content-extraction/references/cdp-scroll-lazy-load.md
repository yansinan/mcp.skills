# CDP Scroll Strategy for Lazy-Loaded Content

## When to Use

Pages that load content incrementally as the user scrolls (WeChat articles, infinite-scroll feeds, intersection-observer-based lazy loading, SPA pages with dynamic content).

## The Strategy: JS Async IIFE + awaitPromise

**Flow:** `Navigate → lifecycleEvent("load") → Runtime.evaluate(async IIFE) → return scrollHeight`

A single `Runtime.evaluate` command with `awaitPromise: true` runs the entire scroll inside a JS async IIFE. Python sends ONE command and truly awaits completion.

## Prerequisite: Correct Page Load Detection

**CRITICAL:** Use `Page.setLifecycleEventsEnabled(true)` + `Page.lifecycleEvent(name="load")`, NOT `Page.frameStoppedLoading` or `Page.loadEventFired`.

```python
# Before navigate:
await _cdp_send(ws, "Page.setLifecycleEventsEnabled", {"enabled": True})

# After sending Page.navigate, use message-ID-based filtering:
# ⚠️ There WILL be residual events in the websocket buffer after
#    the navigation loop exits. Always use _cdp_send (which filters
#    by msg.id) for ALL subsequent commands.
```

## Implementation: Single-Command JS Async IIFE

```python
async def _scroll_to_bottom(ws, msg_id: int) -> int | None:
    scroll_js = """
        (async () => {
            const el = document.scrollingElement;
            const step = 80;
            let pos = 0;
            let bottomCount = 0;

            await new Promise((resolve) => {
                const iv = setInterval(() => {
                    pos += step;
                    window.scrollTo(0, pos);

                    if (window.scrollY + window.innerHeight >= el.scrollHeight) {
                        bottomCount++;
                        if (bottomCount >= 2) {
                            clearInterval(iv);
                            setTimeout(() => {
                                const h = el.scrollHeight;
                                resolve(h);
                            }, 3000);
                        }
                    }
                }, 50);
            });

            return el.scrollHeight;
        })()
    """

    resp = await _cdp_send(ws, "Runtime.evaluate", {
        "expression": scroll_js,
        "awaitPromise": True,      # ← Python truly awaits JS completion
        "returnByValue": True,
    }, msg_id=msg_id)
```

### How `awaitPromise` + macrotasks actually works

Despite earlier assumptions, `Runtime.evaluate` with `awaitPromise: true` **can** handle JS macrotasks (`setTimeout`, `setInterval`, `requestAnimationFrame`). Chrome's message loop continues running while CDP awaits a Promise — the event loop is not blocked.

**Proof:** `setTimeout(3000)` inside an async IIFE with `awaitPromise: true` takes exactly 3.01s to return. ✅

### Previous failures: the real cause was websocket buffer pollution

Earlier attempts to use `awaitPromise` "failed" because **residual events from navigation** were stuck in the websocket receive buffer. The naive `await ws.recv()` reads the NEXT available message — which could be a stale `Page.lifecycleEvent` event from navigation, NOT the `Runtime.evaluate` response.

**Fix:** Always use message-ID-based filtering. Our helper `_cdp_send` does:

```python
def _cdp_send(ws, method, params, msg_id):
    await ws.send(payload)
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=30)
        msg = json.loads(raw)
        if msg.get("id") == msg_id:    # ← skip events, match by ID
            return msg
        # Events (no "id") are silently skipped
```

This skips any residual events and correctly returns only the response matching our command's `msg_id`.

### Alternative: Python-Controlled Scroll (more granular)

For debugging or when you need per-step visibility, control each scroll from Python:

```python
for y in range(0, total + 1, step):
    await _cdp_send(ws, "Runtime.evaluate",
                   {"expression": f"window.scrollTo(0, {y})"}, msg_id)
    msg_id += 1
    await asyncio.sleep(0.2)
await asyncio.sleep(3)
```

Each step is its own CDP command with a confirmed response. More verbose but easier to debug.

## Key Points

1. **`document.scrollingElement.scrollHeight`** — NOT `document.body.scrollHeight`. Modern pages (standards mode) scroll `<html>`, not `<body>`. Using `body.scrollHeight` returns a smaller value, causing scroll to end early. Reference: [MDN Document.scrollingElement](https://developer.mozilla.org/en-US/docs/Web/API/Document/scrollingElement)

2. **`Page.setLifecycleEventsEnabled(true)` must be sent before navigation** — otherwise `Page.lifecycleEvent` events are never emitted. Do this before `Page.navigate`.

3. **Always use message-ID filtering** (`_cdp_send`) for ALL commands after navigation. Residual events (Page.frameStoppedLoading, Page.lifecycleEvent init/DOMContentLoaded) remain in the buffer even after the navigation loop exits.

4. **`Page.bringToFront` is a page-level CDP command** — it works on the target WebSocket, not the browser WebSocket. Use it to bring the tab to the foreground so the user can see scrolling.

5. **`Input.synthesizeScrollGesture`** is **EXPERIMENTAL** and [broken since Chrome 97+](https://issues.chromium.org/issues/40815748). Do not use.

## Results

Before (no scroll): Readability null, 67 chars markdown (just title)
After (JS async IIFE with awaitPromise): Readability parses correctly, 3632 chars markdown, 93%+ coverage on WeChat articles

## Common Pitfalls

1. **`Page.frameStoppedLoading` fires too early.** This event means the frame finished rendering, NOT that all resources loaded. Scroll starting before `lifecycleEvent("load")` may capture incomplete content.

2. **Don't use `Page.loadEventFired`.** It's deprecated in Chrome 148+ and returns `-32601 method not found`.

3. **Close the CDP target after use.** Each call creates a new tab. Orphan tabs accumulate and slow down Chrome.

4. **Explicit `returnByValue: True` is required** when the JS returns a primitive (number/string). Without it, CDP returns a `RemoteObject` reference, not the actual value.

5. **Check both `"error"` and `"exceptionDetails"`** in the Runtime.evaluate response. A JS exception inside the async IIFE sets `exceptionDetails` but not the top-level `"error"` field.
