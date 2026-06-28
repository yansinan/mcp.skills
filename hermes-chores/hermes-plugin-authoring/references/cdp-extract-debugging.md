# CDP-Extract Debugging: Isolate Plugin vs Infrastructure

## When to use

CDP-extract plugin's `extract()` returns empty `content`/`raw_content` (or all-zero lengths), but the browser on port 9222 is alive and `curl localhost:9222/json/version` returns 200.

## Three-layer isolation drill

### Layer 1: CDP infrastructure alive?

```bash
curl -s http://localhost:9222/json/version | python3 -m json.tool
# Expected: {"Browser": "Chrome/...", "webSocketDebuggerUrl": "ws://..."}

curl -s http://localhost:9222/json | python3 -c "
import json,sys
for t in json.load(sys.stdin):
    print(t.get('title','?')[:40], '|', t.get('url','?')[:60])
"
```

If this fails: the browser isn't running at all. Check `ps aux | grep chrome` and `hermes_cli.browser_connect.try_launch_chrome_debug`.

### Layer 2: Raw CDP websocket extraction (bypass plugin)

Use this script to test bare CDP extraction without any plugin layer:

```python
import asyncio, json, httpx, websockets

async def test():
    async with httpx.AsyncClient() as client:
        r = await client.get("http://localhost:9222/json/version", timeout=5)
        ws_url = r.json()["webSocketDebuggerUrl"]

        # Create a fresh target tab
        async with websockets.connect(ws_url, max_size=None) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Target.createTarget",
                "params": {"url": "about:blank"}}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            tid = resp["result"]["targetId"]

        # Get target-specific WS URL
        async with httpx.AsyncClient() as c2:
            for t in (await c2.get("http://localhost:9222/json", timeout=5)).json():
                if t.get("id") == tid:
                    target_ws = t["webSocketDebuggerUrl"]
                    break

        async with websockets.connect(target_ws, max_size=None) as tws:
            mid = 1
            for cmd, params in [
                ("Page.enable", {}),
                ("Page.setLifecycleEventsEnabled", {"enabled": True})
            ]:
                await tws.send(json.dumps({"id": mid, "method": cmd, "params": params}))
                mid += 1
                await asyncio.wait_for(tws.recv(), timeout=10)  # consume response

            # Navigate and wait for load
            nav_id = mid
            await tws.send(json.dumps({"id": nav_id, "method": "Page.navigate",
                "params": {"url": "https://example.com"}}))
            mid += 1
            nav_ok = load_ok = False
            while not (nav_ok and load_ok):
                msg = json.loads(await asyncio.wait_for(tws.recv(), timeout=30))
                if msg.get("id") == nav_id:
                    nav_ok = True
                elif (msg.get("method") == "Page.lifecycleEvent"
                      and msg.get("params", {}).get("name") == "load"):
                    load_ok = True

            # Evaluate content
            for expr, label in [
                ("document.title", "Title"),
                ("document.body?.innerText ?? ''", "Content"),
                ("document.documentElement?.outerHTML ?? ''", "HTML"),
            ]:
                await tws.send(json.dumps({"id": mid, "method": "Runtime.evaluate",
                    "params": {"expression": expr, "returnByValue": True}}))
                while True:
                    msg = json.loads(await asyncio.wait_for(tws.recv(), timeout=10))
                    if msg.get("id") == mid:
                        val = msg.get("result", {}).get("result", {}).get("value", "")
                        print(f"{label}: {len(val)} chars")
                        if val:
                            print(f"  Preview: {val[:100]}")
                        break
                mid += 1

asyncio.run(test())
```

Expected output for example.com:
```
Title: 14 chars
  Preview: Example Domain
Content: 129 chars
HTML: 544 chars
```

If this works but the plugin returns empty → problem is in the plugin's call chain (Layer 3).

### Layer 3: Plugin call chain tracing

The user plugin's `extract()` calls:
```
extract() → _fetch_raw_html(url) → _call_readdown(html, url)
```

Test each intermediate value:

```python
from hermes_cli.plugins import PluginManager
pm = PluginManager(); pm.discover_and_load()
p = get_provider('cdp-extract')

# If the provider module is accessible:
raw = await p._fetch_raw_html("https://example.com")
print(f"html_len={len(raw.get('html',''))}")
print(f"title='{raw.get('title','')}'")

# If readdown is separate:
rd = p._call_readdown(html=raw.get("html",""), url="https://example.com")
print(f"rd keys={list(rd.keys()) if isinstance(rd, dict) else type(rd)}")
```

Common failure modes after `_fetch_raw_html` succeeds:
| Symptom | Probable root cause |
|---------|-------------------|
| Title populated, html empty | `_fetch_raw_html` return dict uses wrong key (e.g. `"content"` not `"html"`) |
| html populated, _call_readdown output empty | Readability/Turndown parse failure |
| Both raw and plugin return empty | Page blocked by target server (503, CAPTCHA, rate limit) — try a different URL like example.com |
| Different result between user override and bundled | User plugin at `~/.hermes/plugins/<category>/<name>/` is the runtime version, not the bundled one being edited on a git branch |
