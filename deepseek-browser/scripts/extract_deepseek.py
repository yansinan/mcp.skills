#!/usr/bin/env python3
"""
Extract DeepSeek Smart Search conversation content via Chrome CDP.

Usage:
  # Extract current page (already on a DeepSeek conversation)
  python3 extract_deepseek.py

  # Extract a specific conversation URL
  python3 extract_deepseek.py --url https://chat.deepseek.com/a/chat/s/<uuid>

  # Specify CDP port (default: 9222)
  python3 extract_deepseek.py --port 9222

Output:
  JSON with: title, full_text, source_links, web_pages_read, conversation_url
"""

import argparse
import asyncio
import json
import sys
import urllib.request

import websockets


# ---------------------------------------------------------------------------
# CDP helpers (minimal: navigate + evaluate JS)
# ---------------------------------------------------------------------------

class CDP:
    """Minimal Chrome DevTools Protocol client over WebSocket.

    Browser-level methods (Target.*) -> _send()
    Page-level methods (Page.*, Runtime.*) -> _send_page()
    """

    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self._msg_id = 0
        self._session_id = None  # set by attach_to_target

    async def __aenter__(self):
        self._ws = await websockets.connect(self.ws_url, max_size=2**24)
        return self

    async def __aexit__(self, *exc):
        await self._ws.close()

    async def _send(self, method: str, params: dict = None) -> dict:
        """Send a browser-level CDP command (no sessionId needed)."""
        self._msg_id += 1
        msg = {"id": self._msg_id, "method": method, "params": params or {}}
        await self._ws.send(json.dumps(msg))
        while True:
            raw = await self._ws.recv()
            data = json.loads(raw)
            if data.get("id") == self._msg_id:
                if "error" in data:
                    raise RuntimeError(f"CDP error: {data['error']}")
                return data.get("result", {})
            # Swallow events (method fields without id)

    async def _send_session(self, method: str, params: dict = None) -> dict:
        """Send a page-scoped CDP command (requires sessionId)."""
        self._msg_id += 1
        msg = {
            "id": self._msg_id,
            "method": method,
            "params": params or {},
            "sessionId": self._session_id,
        }
        await self._ws.send(json.dumps(msg))
        while True:
            raw = await self._ws.recv()
            data = json.loads(raw)
            if data.get("id") == self._msg_id:
                if "error" in data:
                    raise RuntimeError(f"CDP error: {data['error']}")
                return data.get("result", {})

    async def navigate(self, url: str) -> str:
        """Navigate current page to URL and wait for load."""
        await self._send_session("Page.enable")
        result = await self._send_session("Page.navigate", {"url": url})
        while True:
            raw = await self._ws.recv()
            data = json.loads(raw)
            if (data.get("method") == "Page.loadEventFired"
                    and data.get("sessionId") == self._session_id):
                break
        await asyncio.sleep(3)  # extra wait for SPA rendering
        return result.get("frameId", "")

    async def evaluate(self, js: str) -> any:
        """Execute JS in current page context."""
        result = await self._send_session("Runtime.evaluate", {
            "expression": js,
            "returnByValue": True,
            "awaitPromise": True,
        })
        return result.get("result", {}).get("value")

    async def get_targets(self) -> list:
        """List all browser tabs/pages."""
        result = await self._send("Target.getTargets")
        return result.get("targetInfos", [])

    async def attach_to_target(self, target_id: str):
        """Attach to a specific tab so Runtime.*/Page.* commands work."""
        result = await self._send("Target.attachToTarget", {
            "targetId": target_id,
            "flatten": True,
        })
        self._session_id = result.get("sessionId")


# ---------------------------------------------------------------------------
# Extraction logic
# ---------------------------------------------------------------------------

EXTRACT_JS = r"""
(function(){
  var result = {
    title: '',
    answer_text: '',
    source_links: [],
    web_pages_read: 0,
    conversation_url: window.location.href,
  };

  // 1. Title from the-header
  var headers = document.querySelectorAll('[class*="the-header"]');
  for (var i = 0; i < headers.length; i++) {
    var txt = headers[i].textContent.trim();
    if (txt && txt.length > 2 && txt.length < 100) {
      result.title = txt.replace(/Instant$|Expert$|Deep thinking$/, '').trim();
      break;
    }
  }

  // 2. Answer text from .ds-markdown
  var mds = document.querySelectorAll('.ds-markdown');
  var texts = [];
  for (var i = 0; i < mds.length; i++) {
    var t = mds[i].textContent.trim();
    if (t) texts.push(t);
  }
  result.answer_text = texts.join('\n\n---\n\n');

  // 3. Source links (exclude deepseek.com)
  var allLinks = document.querySelectorAll('a[href^="http"]');
  var seen = {};
  var links = [];
  for (var i = 0; i < allLinks.length; i++) {
    var h = allLinks[i].href;
    if (h.indexOf('deepseek.com') >= 0) continue;
    if (seen[h]) continue;
    seen[h] = true;
    links.push(h);
  }
  result.source_links = links;

  // 4. "Read N web pages" indicator
  var allText = document.body.innerText;
  var m = allText.match(/Read\s+(\d+)\s+web\s+pages?/i);
  if (m) result.web_pages_read = parseInt(m[1], 10);

  return result;
})();
"""


async def extract_from_url(cdp_url: str, target_url: str = None) -> dict:
    """Extract DeepSeek answer from current or specified page."""
    async with CDP(cdp_url) as cdp:
        # Get current page targets
        targets = await cdp.get_targets()
        pages = [t for t in targets if t.get("type") == "page"]
        if not pages:
            return {"error": "No page targets found"}

        # Find DeepSeek tab or use first page
        ds_page = None
        for p in pages:
            if "deepseek" in p.get("url", ""):
                ds_page = p
                break

        if target_url:
            # Navigate target: use first page or create new
            target = pages[0] if pages else None
            if not target:
                return {"error": "No page to navigate"}
            await cdp.attach_to_target(target["targetId"])
            await cdp.navigate(target_url)
        elif ds_page:
            # Use existing DeepSeek tab
            await cdp.attach_to_target(ds_page["targetId"])
        else:
            # Use current page (first non-special URL)
            for p in pages:
                url = p.get("url", "")
                if url not in ("about:blank", "chrome://new-tab-page/", "chrome://new-tab-page", ""):
                    await cdp.attach_to_target(p["targetId"])
                    break
            else:
                return {"error": "No usable page target found"}

        # Verify we're on a DeepSeek conversation
        cur_url = await cdp.evaluate("window.location.href")
        if "/a/chat/s/" not in (cur_url or ""):
            return {"error": f"Not a DeepSeek conversation page: {cur_url}"}

        # Check if response is loaded
        has_response = await cdp.evaluate(
            "document.querySelectorAll('.ds-markdown').length > 0"
        )
        if not has_response:
            # Wait up to 30s for response
            for _ in range(15):  # 15 × 2s = 30s
                await asyncio.sleep(2)
                has_response = await cdp.evaluate(
                    "document.querySelectorAll('.ds-markdown').length > 0"
                )
                if has_response:
                    break
            if not has_response:
                return {"error": "Timeout waiting for DeepSeek response"}

        # Extract content
        result = await cdp.evaluate(EXTRACT_JS)
        return result


def get_cdp_websocket_url(port: int = 9222) -> str:
    """Get CDP WebSocket URL from Chrome's /json/version endpoint."""
    try:
        resp = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/version", timeout=3
        )
        data = json.loads(resp.read().decode())
        return data["webSocketDebuggerUrl"]
    except Exception as e:
        raise RuntimeError(
            f"Cannot connect to Chrome CDP on port {port}: {e}\n"
            f"Make sure Chrome is running with --remote-debugging-port={port}"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract DeepSeek Smart Search conversation content via CDP"
    )
    parser.add_argument(
        "--url", "-u",
        help="DeepSeek conversation URL (e.g. https://chat.deepseek.com/a/chat/s/<uuid>)"
    )
    parser.add_argument(
        "--port", "-p", type=int, default=9222,
        help="Chrome CDP port (default: 9222)"
    )
    parser.add_argument(
        "--pretty", action="store_true",
        help="Pretty-print JSON output"
    )
    args = parser.parse_args()

    try:
        cdp_url = get_cdp_websocket_url(args.port)
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    result = asyncio.run(extract_from_url(cdp_url, args.url))

    indent = 2 if args.pretty else None
    print(json.dumps(result, ensure_ascii=False, indent=indent))


if __name__ == "__main__":
    main()
