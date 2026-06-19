# plugin.yaml Reference

The plugin manifest file — every Hermes plugin needs one at the root of its directory.

## Required Fields

```yaml
name: my-plugin              # Unique identifier, lowercase-hyphens
version: 1.0.0               # Semver string
description: >               # Single line or block
  What this plugin does.
author: YourName             # Person or org
kind: backend                # One of the kinds below
```

## Optional Fields

```yaml
# Which providers this plugin contributes (list of string names).
# Use the field matching your plugin's category.
provides_web_providers:
  - my-web-provider

provides_memory_providers:
  - my-memory-provider

provides_context_engines:
  - my-context-engine

# Plugin entry point — defaults to __init__.py's `register(ctx)`.
# Point at an alternative module:function if needed.
entry_point: my_module:register
```

## Kind Values

| Kind | Meaning | Activation |
|------|---------|------------|
| `standalone` | Own hooks/tools | `plugins.enabled` opt-in |
| `backend` | Pluggable tool backend | Bundle auto-loads; user needs `plugins.enabled` |
| `platform` | Gateway messaging adapter | Bundle auto-loads; user needs `plugins.enabled` |
| `exclusive` | Category with exactly-one active (memory) | Via `<category>.provider` config |
| `model-provider` | Inference backend | Via `model.provider` config; lazy-discovered |

## Example: Minimal Web Plugin

```yaml
name: web-test
version: 0.1.0
description: "Test web extract plugin — returns mock data."
author: user
kind: backend
provides_web_providers:
  - test-extract
```

## Example: Full-Featured Plugin (from firecrawl)

```yaml
name: web-firecrawl
version: 1.0.0
description: "Firecrawl web search + content extraction. Supports direct API and Nous-hosted tool-gateway routing for subscribers. ..."
author: NousResearch
kind: backend
provides_web_providers:
  - firecrawl
```
