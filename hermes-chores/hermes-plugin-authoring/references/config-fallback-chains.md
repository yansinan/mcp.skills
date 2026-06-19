# Config Fallback Chains for Hermes Plugins

## When to Use

Your plugin needs to read configuration from `config.yaml`, but the config may live at **different paths** depending on how the plugin is invoked:

- **As a standalone plugin**: config at `plugins.<name>.*`
- **As a sub-provider of a meta-plugin**: config at `plugins.<metaname>.*`

The solution: a `prefer_prefix` parameter that lets the caller specify the config path.

## Basic Pattern

```python
def _load_config(prefer_prefix: str | None = None) -> dict:
    """Read config from config.yaml.

    prefer_prefix: Optional dotted config path for the caller's namespace.
        - meta-plugin calls:  _load_config("plugins.web_selfhost")
        - standalone calls:    _load_config()  → uses default fallback
    """
    try:
        from hermes_cli.config import load_config
        cfg = load_config()

        # 1. Caller's namespace (if provided and present)
        if prefer_prefix:
            node = cfg
            for key in prefer_prefix.split("."):
                if not isinstance(node, dict):
                    node = {}
                    break
                node = node.get(key, {})
            if node:  # namespace exists and has content
                return dict(node)

        # 2. Default fallback path (standalone mode)
        return cfg.get("plugins", {}).get("cdp_extract", {}) or {}
    except Exception:
        return {}
```

## Calling Convention

```python
# In standalone mode — no prefix → uses default fallback
cfg = _load_config()
port = cfg.get("local_port", 9222)

# When called by a meta-provider — explicit prefix
cfg = _load_config("plugins.web_selfhost")
port = cfg.get("local_port", 9222)
```

## Why Not Just Use a Single Config Path

Two reasons:

1. **Separation of concerns.** The meta-plugin's config namespace (`plugins.web_selfhost.*`) is semantically its own. A user who configures `web.backend: web_selfhost` should find all relevant settings under `plugins.web_selfhost:`, not have to dig into `plugins.cdp_extract.*` as well.

2. **Graceful fallback when standalone.** If someone removes `web_selfhost` from their config but keeps `cdp_extract` running as its own backend, the plugin continues to work — no config migration needed.

## Practical Example: cdp-extract + web_selfhost

```yaml
# Full config — all CDP params under web_selfhost namespace
plugins:
  web_selfhost:
    cdp_url: http://127.0.0.1:9222
    local_chrome_profile: /tmp/cdp-profile
    browser_search:
      enabled: true
      hosts:
        - "www.google.com"

  # Standalone fallback — only used if web_selfhost is removed
  cdp_extract:
    local_port: 9222
```

The `prefer_prefix="plugins.web_selfhost"` reads from the first block. When called standalone (no prefix), it reads from the second. The user only needs to know one namespace.

## ⚠️ Pitfall: Empty Namespace Masks Fallback

If `prefer_prefix` resolves to a path that exists but is empty (`{}`), the function returns `{}` — it does NOT fall through to the default path.

```yaml
plugins:
  web_selfhost: {}       # ← empty dict
  cdp_extract:
    local_port: 9222     # ← never reached when prefix set
```

**Fix:** Use `if node:` (truthiness check, not `is not None`) to distinguish empty dict from absent path. Empty means intentionally empty — don't override it.

## All Config Names Flow Through Here

This pattern applies to any sub-provider that:
- Reads `plugins.*` config keys
- Is called from a meta-provider that has its own config namespace
- Needs to be independently runnable

Examples:
- cdp-extract: `_load_cdp_config(prefer_prefix)`
- SearXNG: `_searxng_url()` (reads from env, not config — less applicable)
- Any custom extract/search provider used via web_selfhost
