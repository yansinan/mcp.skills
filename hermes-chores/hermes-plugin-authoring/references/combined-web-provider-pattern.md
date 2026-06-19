# Combined Web Provider Pattern

## When to Use

You have two existing `WebSearchProvider` plugins — one that does **search** (e.g. SearXNG, DuckDuckGo, Tavily) and one that does **extraction** (e.g. CDP-extract, Firecrawl). You want a single `web.backend` that serves both capabilities without writing duplicate code.

## Two Approaches

This reference covers two approaches — the **simple composition** (hardcoded sub-providers for quick setup) and the **registry delegation** (dynamic routing to whatever is registered, for more flexible multi-provider setups).

---

## Approach A: Simple Composition (Hardcoded Sub-Providers)

Best for: known, fixed setup where you always use the same pair of providers.

```python
from plugins.web.searxng.provider import SearXNGWebSearchProvider
from plugins.web.cdp_extract.provider import CDPExtractProvider

class HermesCombinedWebProvider(WebSearchProvider):
    """Combines search (SearXNG) and extract (CDP-extract) under one name."""
```

### Rules

1. **Composition, not inheritance.** Keep both sub-providers as private instance attributes. Do NOT subclass them.
2. **Lazy instantiation.** Create sub-providers in `__init__()` — they have no expensive setup by convention.
3. **Pure delegation.** Every method is one line: `return self._search.search(...)` / `return self._cdp.extract(...)`.
4. **No code changes to existing plugins.** Import and delegate only.
5. **No fallback logic.** If a sub-provider fails, propagate its error verbatim. The config chooses the provider, the provider doesn't choose its own fallback.
6. **`is_available()` checks both.** Return `True` only when both sub-providers are available.

### Canonical Implementation (Hardcoded)

```python
"""Combined web provider — search → SearXNG, extract → CDP-extract."""

from __future__ import annotations

from typing import Any, Dict, List

from agent.web_search_provider import WebSearchProvider
from plugins.web.searxng.provider import SearXNGWebSearchProvider
from plugins.web.cdp_extract.provider import CDPExtractProvider


class HermesCombinedWebProvider(WebSearchProvider):
    """Unified web provider: delegates search/extract to specialized backends."""

    def __init__(self) -> None:
        self._search = SearXNGWebSearchProvider()
        self._extract = CDPExtractProvider()

    @property
    def name(self) -> str:
        return "hermes-combined"

    @property
    def display_name(self) -> str:
        return "Combined: SearXNG (search) + CDP (extract)"

    def supports_search(self) -> bool:
        return self._search.supports_search()

    def supports_extract(self) -> bool:
        return self._extract.supports_extract()

    def is_available(self) -> bool:
        return self._search.is_available() and self._extract.is_available()

    async def search(self, queries: List[str], **kwargs: Any) -> Dict[str, Any]:
        return await self._search.search(queries, **kwargs)

    async def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        return await self._extract.extract(urls, **kwargs)

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": self.display_name,
            "badge": "combined · self-hosted",
            "tag": "SearXNG search + CDP-extract",
            "env_vars": ["SEARXNG_URL"],
        }
```

---

## Approach B: Registry Delegation (Preferred for Flexibility)

Best for: when you want the combined provider to **dynamically discover** whatever search provider the user has configured, rather than hardcoding one.

### Why This Matters

Hardcoding `SearXNGWebSearchProvider` means:
- Can't switch search provider without code changes
- If SearXNG isn't configured, search silently fails
- Can't add new search providers dynamically

The registry pattern solves this by using `agent.web_search_registry` to **iterate all registered providers** at call time, skipping itself.

### Key Challenge: Avoiding Recursion

If config is `web.backend: web_selfhost`, the registry's `get_active_search_provider()` resolves to the meta-provider itself — causing infinite recursion when `search()` calls the registry.

**Solution:** Don't call `get_active_search_provider()`. Instead:
1. Read `web.search_backend` or `web.backend` config keys directly via `_read_config_key()`
2. If the resolved name is your own name, skip and try the next available provider
3. Fall back to scanning `list_providers()` filtered by capability + availability

### Canonical Implementation (Registry Delegation)

```python
"""Combined web provider — dynamically routes to registered providers."""

from __future__ import annotations

from typing import Any, Dict, List

from agent.web_search_provider import WebSearchProvider
from agent.web_search_registry import (
    list_providers,
    get_provider,
    _read_config_key,
)


class WebSelfhostProvider(WebSearchProvider):
    """Meta-provider: search → whichever search provider is registered,
    extract → whichever extract provider is registered.

    Avoids recursion by skipping its own name when resolving backends
    and never calling get_active_search_provider().
    """

    @property
    def name(self) -> str:
        return "web_selfhost"

    @property
    def display_name(self) -> str:
        return "Web Self-Host (registry-delegated)"

    def supports_search(self) -> bool:
        return self._resolve_search() is not None

    def supports_extract(self) -> bool:
        return self._resolve_provider("extract") is not None

    def is_available(self) -> bool:
        return self.supports_search() or self.supports_extract()

    def _resolve_search(self) -> WebSearchProvider | None:
        return self._resolve_provider_by_capability("search")

    def _resolve_extract(self) -> WebSearchProvider | None:
        return self._resolve_provider_by_capability("extract")

    def _resolve_provider_by_capability(self, capability: str) -> WebSearchProvider | None:
        """Resolve a provider by capability, avoiding self."""
        config_key = f"web.{capability}_backend"
        explicit = _read_config_key("web", f"{capability}_backend") \
                   or _read_config_key("web", "backend")

        # 1. Exact match from config (but skip self)
        if explicit and explicit != self.name:
            p = get_provider(explicit)
            if p and self._capable(p, capability) and p.is_available():
                return p

        # 2. Scan all registered, skip self, filter by capability + available
        for p in list_providers():
            if p.name != self.name and self._capable(p, capability) and p.is_available():
                return p

        return None

    @staticmethod
    def _capable(p: WebSearchProvider, capability: str) -> bool:
        if capability == "search":
            return bool(p.supports_search())
        if capability == "extract":
            return bool(p.supports_extract())
        return False

    async def search(self, queries: List[str], **kwargs: Any) -> Dict[str, Any]:
        provider = self._resolve_search()
        if not provider:
            return {"success": False, "error": "No search provider available"}
        return await provider.search(queries, **kwargs)

    async def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        provider = self._resolve_extract()
        if not provider:
            return [{"url": u, "error": "No extract provider available"} for u in urls]
        return await provider.extract(urls, **kwargs)
```

### ⚠️ Pitfall: Recursive Resolution

If you call `get_active_search_provider()` or `get_active_extract_provider()` from within a meta-provider, and the user has `web.backend: web_selfhost`, you get **infinite recursion**:

```
web_selfhost.search()
  → get_active_search_provider()
    → _resolve("web_selfhost", capability="search")
      → found it! return web_selfhost provider
        → web_selfhost.search() ← BACK TO START
```

**Always use `_read_config_key()` + `get_provider()` directly** — never call the `get_active_*` resolver functions from inside a meta-provider.

---

## Config Namespace Forwarding

When your meta-provider calls a sub-provider that reads its own config from `config.yaml`, you face a config-namespace problem:

- **When called via web_selfhost**: config should come from `plugins.web_selfhost.*`
- **When called standalone**: config should come from `plugins.cdp_extract.*`

### Solution: `prefer_prefix` Parameter

Modify the sub-provider's config reader to accept an optional prefix:

```python
# In cdp_extract/provider.py:
def _load_cdp_config(prefer_prefix: str | None = None) -> dict:
    """读取 CDP 配置。

    prefer_prefix: 调用者指定 config 路径前缀
        - web_selfhost 调用时传 "plugins.web_selfhost"
        - 独立运行时传 None (回退 plugins.cdp_extract)
    """
    try:
        from hermes_cli.config import load_config
        cfg = load_config()

        if prefer_prefix:
            node = cfg
            for key in prefer_prefix.split("."):
                if not isinstance(node, dict):
                    node = {}
                    break
                node = node.get(key, {})
            if node:
                return dict(node)

        return cfg.get("plugins", {}).get("cdp_extract", {}) or {}
    except Exception:
        return {}
```

### Calling from a Meta-Provider

```python
cdp_cfg = _load_cdp_config("plugins.web_selfhost")
# Now cdp_cfg contains cdp_url, local_chrome_profile, etc.
# from under plugins.web_selfhost: rather than plugins.cdp_extract:
```

### Config Priority Chain

```yaml
# User sees only this config:
plugins:
  web_selfhost:
    cdp_url: http://127.0.0.1:9222
    local_chrome_profile: /tmp/cdp-profile
    browser_search:
      enabled: true
      hosts:
        - "www.google.com"

  cdp_extract:       # fallback path — standalone only
    local_port: 9223
```

---

## CDP Browser Search

When no API-based search provider is available, use the local Chrome CDP to search via a configured search engine:

### Config

```yaml
plugins:
  web_selfhost:
    browser_search:
      enabled: true
      hosts: ["www.google.com", "www.bing.com", "www.baidu.com"]
      templates:
        "www.google.com": "https://www.google.com/search?q={query}"
        "www.bing.com":    "https://www.bing.com/search?q={query}"
        "www.baidu.com":   "https://www.baidu.com/s?wd={query}"
      preferred_host: "www.google.com"
```

### Implementation Sketch

```python
def _browser_search(self, query: str, limit: int = 5) -> Dict[str, Any]:
    cfg = _load_cdp_config()
    bs = cfg.get("browser_search", {})
    if not bs.get("enabled"):
        return {"success": False, "error": "browser_search disabled"}

    host = bs.get("preferred_host", "www.google.com")
    template = bs.get("templates", {}).get(host)
    if not template:
        return {"success": False, "error": f"No template for {host}"}

    search_url = template.replace("{query}", requests.utils.quote(query))
    results = self._cdp.extract([search_url])
    # Parse SERP into search result items (requires DOM parsing)
    ...
```

**Caveat:** Browser search is inherently less reliable than API-based search — page structure changes, rate limits, CAPTCHAs. Use as **fallback only**.

---

## Config Integration

Replace split backend with single `web.backend`:

```yaml
# Before:
web:
  search_backend: searxng
  extract_backend: cdp-extract

# After:
web:
  backend: web_selfhost
```

## Plugin Registration

```python
# __init__.py
from .provider import WebSelfhostProvider

def register(ctx) -> None:
    ctx.register_web_search_provider(WebSelfhostProvider())
```

```yaml
# plugin.yaml
name: web-selfhost
version: 1.0.0
description: "Unified web backend: registry-delegated search + CDP-extract"
author: dr
kind: backend
provides_web_providers:
  - web_selfhost
```

## Verification

```bash
cd ~/.hermes && source hermes-agent/venv/bin/activate && python3 -c "
import asyncio
from agent.web_search_registry import get_provider, list_providers
from hermes_cli.plugins import PluginManager
pm = PluginManager()
pm.discover_and_load()

p = get_provider('web_selfhost')
print('available:', p.is_available())
print('supports_search:', p.supports_search())
print('supports_extract:', p.supports_extract())
if p.supports_search():
    result = asyncio.run(p.search(['hermes agent']))
    print('search ok:', result.get('success'))
"
```
