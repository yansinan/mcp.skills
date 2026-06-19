# Web Search Provider Plugin Reference

**Base class:** `agent.web_search_provider.WebSearchProvider` (ABC)
**Registration:** `ctx.register_web_search_provider(instance)` in `__init__.py`
**Registry:** `agent.web_search_registry` — central map of registered providers

## Required: Provider Class

Subclass `WebSearchProvider` and implement at minimum `name` + `is_available()` + at least one capability.

### Interface Methods

| Method | Returns | Required | Notes |
|--------|---------|----------|-------|
| `name` (property) | `str` | ✅ | Lowercase, no spaces. Used in config keys `web.search_backend`, `web.extract_backend`, `web.backend` |
| `display_name` (property) | `str` | Optional | Defaults to `name`. Human-readable for `hermes tools` |
| `is_available()` | `bool` | ✅ | Cheap check (env vars, import). MUST NOT make network calls |
| `supports_search()` | `bool` | Optional | Default `True` |
| `supports_extract()` | `bool` | Optional | Default `False` |
| `search(query, limit=5)` | `Dict[str, Any]` | If supports | Sync |
| `extract(urls, **kwargs)` | `List[Dict]` or coroutine | If supports | Can be `async def` |
| `get_setup_schema()` | `Dict` | Optional | Metadata for `hermes tools` picker |

### Response Shapes

**Search results (success):**
```python
{
    "success": True,
    "data": {
        "web": [
            {"title": str, "url": str, "description": str, "position": int},
            ...
        ]
    }
}
```

**Extract results (success):**
```python
{
    "success": True,
    "data": [
        {
            "url": str,
            "title": str,
            "content": str,
            "raw_content": str,    # optional
            "metadata": dict,      # optional
        },
        ...
    ]
}
```

**Failure (either capability):**
```python
{"success": False, "error": str}
```

### extract() Special Notes

- Can be `async def` — the dispatcher detects coroutines via `inspect.iscoroutinefunction` and awaits
- `kwargs` may carry `format`, `include_raw`, `max_chars` — ignore unknown keys
- Sync implementations doing blocking I/O should wrap in `asyncio.to_thread` at the call site

## Registration

In `__init__.py`:

```python
def register(ctx) -> None:
    ctx.register_web_search_provider(MyProvider())
```

## Activation

In `config.yaml`:

```yaml
web:
  search_backend: my-provider     # per-capability override
  extract_backend: my-provider    # per-capability override
  # OR shared fallback:
  backend: my-provider
```

The resolution order is:

1. `web.search_backend` / `web.extract_backend` (per-capability)
2. `web.backend` (shared fallback)
3. If exactly one eligible provider registered AND available, use it
4. Legacy preference order: `firecrawl` → `parallel` → `tavily` → `exa` → `searxng` → `brave-free` → `ddgs` (filtered by availability)
5. Otherwise `None`

## Reference Plugins in the Codebase

All under `<repo>/plugins/web/`:

| Plugin | Supports | Notes |
|--------|----------|-------|
| `ddgs` | Search only | Simplest: no API key, uses `ddgs` Python package. Best template for a minimal provider |
| `brave_free` | Search only | API key required, simple structure |
| `searxng` | Search + Extract | Self-hosted instance |
| `firecrawl` | Search + Extract | Most complex: dual auth (direct + gateway), lazy SDK import, async extract with 60s timeout, SSRF checks, response-shape normalization |
| `tavily` | Search + Extract | |
| `exa` | Search + Extract | |
| `parallel` | Search + Extract | |

## Override Mechanics

Drop a user plugin at `$HERMES_HOME/plugins/web/<name>/` with the same `name` as a bundled plugin. User plugins are discovered after bundled ones, and `register_web_search_provider()` is last-writer-wins in the registry.

However, user plugins (even `kind: backend`) must be explicitly enabled via `plugins.enabled` in config.yaml:
```yaml
plugins:
  enabled:
    - web/my-provider
```
