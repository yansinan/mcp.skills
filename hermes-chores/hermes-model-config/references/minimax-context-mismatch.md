# MiniMax Context-Length Mismatch — Full Root Cause

When a MiniMax model reports `Context: 204,800 tokens` in `/model` or
`/info` output but the real vendor specs say 1,000,000 (M3) or 262,144
(M2.5 newer tiers), the displayed number is wrong. This file documents
the exact override path that fixes it.

## Root cause

`~/.hermes/hermes-agent/agent/model_metadata.py` ships a hardcoded
fallback table keyed by generic model slug:

  line 257:  # MiniMax — M3 is 1M context (max output 512K); M2.x series is 204,800.
  line 263:  "minimax": 204800,
  line 312:  "MiniMaxAI/MiniMax-M2.5": 204800,

When the user sets `model: minimax` (a vendor-neutral catch-all) and
probes come back empty, the resolver lands on `204800`. The display
path `resolve_display_context_length` (`hermes_cli/model_switch.py:620`)
threads `custom_providers` into `get_model_context_length`
(`agent/model_metadata.py:1613`), and resolution order has a hook at
step 0b that checks `custom_providers[i].models.<model_id>.context_length`
**before** the hardcoded table at line 263. That hook is the user
override. Use it.

The cache also has a deliberate invalidation rule at line 1699
(`# Invalidate stale ≤204,800 cache entries for MiniMax-M3`) — the
Hermes team knows about the catch-all bug, but the fix is only
triggered by the **explicit** slug `MiniMax-M3`, not by the generic
`minimax`. So if your provider's `model` field is the generic slug,
you must override, not rename.

## The override (the only working path)

In `~/.hermes/config.yaml`, add a `models:` sub-block to each affected
`custom_providers` entry:

```yaml
custom_providers:
  - name: headroom
    base_url: http://100.66.66.203/litellm/headroom/v1
    api_key: fuck_key
    model: minimax
    models:                              # <- required sub-block
      minimax:                           # <- model id as key
        context_length: 1000000          # <- 1M, overrides 204800 default
  - name: litellm
    base_url: http://serverhome.tail2e6efb.ts.net/litellm/hermes
    api_key: fuck_key
    model: minimax
    models:
      minimax:
        context_length: 1000000
```

Match rule (from `hermes_cli/config.py:4450`
`get_custom_provider_context_length`):

  1. `entry.base_url.rstrip("/") == target_url`   (trailing-slash insensitive)
  2. `entry.models[model_id]` is a dict
  3. `int(entry.models[model_id].context_length) > 0`

If any of those fails, override is skipped and the hardcoded 204800
wins.

## Why this is needed, not "just use model: MiniMax-M3"

`model: MiniMax-M3` would route to the explicit slug, but your
LiteLLM model group on the upstream side is registered as `minimax`
(the generic catch-all). The two have to agree, otherwise the upstream
returns 404 / unknown_model. Override in client config is the cleaner
fix because it doesn't require touching the upstream model group.

## Verification (works on the running install, no restart needed for the lookup)

```bash
# 1. yaml syntax
python3 -c "import yaml; yaml.safe_load(open('/home/dr/.hermes/config.yaml'))" \
  && echo "yaml OK"

# 2. resolver returns the override
~/.hermes/hermes-agent/venv/bin/python3 -c "
from hermes_cli.config import (
    get_custom_provider_context_length, get_compatible_custom_providers)
import yaml
cfg = yaml.safe_load(open('/home/dr/.hermes/config.yaml'))
cp = get_compatible_custom_providers(cfg)
ctx = get_custom_provider_context_length(
    'minimax',
    'http://100.66.66.203/litellm/headroom/v1',
    custom_providers=cp)
print('Resolved:', ctx)
"
# expect: Resolved: 1000000
```

## Related source pointers (verified 2026-06-26)

  - `~/.hermes/hermes-agent/agent/model_metadata.py:1613`  `get_model_context_length`
  - `~/.hermes/hermes-agent/agent/model_metadata.py:257-263`  hardcoded fallback table
  - `~/.hermes/hermes-agent/agent/model_metadata.py:1699-1700`  cache invalidation
  - `~/.hermes/hermes-agent/hermes_cli/config.py:4450`  `get_custom_provider_context_length`
  - `~/.hermes/hermes-agent/hermes_cli/model_switch.py:620`  `resolve_display_context_length`
  - `~/.hermes/hermes-agent/hermes_cli/web_dist/assets/index-*.js`  mentions
    "MiniMax M2.7" in UI copy but has no context-length numbers — UI is
    driven by the resolver at runtime
