# Hermes auto-detect context length table

When `model.context_length` is set to `0` (or absent), Hermes calls `get_model_context_length()` in `~/.hermes/hermes-agent/agent/model_metadata.py` which consults a hardcoded lookup table using **substring matching** (longest matching key wins). The string keys are matched against the model name in `model.default`.

## Source of truth

```bash
grep -nE '^\s+"[a-z0-9-]+":\s+[0-9_]+' ~/.hermes/hermes-agent/agent/model_metadata.py
```

The full table is in that file. If you need an exhaustive list, grep it. Below is the subset most users hit.

## Selected entries (verified 2026-06-03)

| Substring key | Context | Source URL / note |
|---|---|---|
| `minimax-m3` | 1,000,000 | https://platform.minimax.io/docs/api-reference/text-chat-openai |
| `minimax` | 204,800 | Generic MiniMax fallback |
| `deepseek-v4-pro` | 1,000,000 | DeepSeek v4 series |
| `deepseek-v4-flash` | 1,000,000 | DeepSeek v4 series (fast tier) |
| `deepseek-chat` | 1,000,000 | Aliased to v4-flash non-thinking |
| `deepseek-reasoner` | 1,000,000 | Aliased to v4-flash thinking |
| `deepseek` | 128,000 | Generic DeepSeek fallback |

## Matching behavior

- **Longest substring wins.** `minimax-m3` matches before `minimax` for the M3 slug.
- **Case-sensitive** substring match on the bare model name (no provider prefix).
- Provider-prefixed names like `github_copilot/gpt-4o` do **not** match `gpt-4o` because the slash in the model name is preserved when looking up.
- If no key matches, the function falls back to querying the upstream `/v1/models` endpoint for `max_input_tokens`, then to a hardcoded 8000 default.

## Per-model override (manual, not auto)

You cannot express "minimax 512K AND deepseek 1M" via config — `model.context_length` is a single global integer. Workarounds:

1. **Set explicit value** — caps every model to that value. Pick the value that matters most.
2. **Set to 0 (auto-detect)** — model name determines context per the table. Cleanest for mixed-model setups.
3. **Rename the model** to a more specific slug (e.g. `minimax` → `minimax-m3`) to trigger a different table entry. Only useful if you also want the new context size.
4. **Patch `model_metadata.py`** — adds a new key, but it's a code change that survives upgrades only if you maintain it.

## Verification

The web UI exposes resolution details:

```bash
curl -s http://localhost:8787/api/model/info | python3 -m json.tool
```

```json
{
  "model": "minimax",
  "provider": "custom",
  "auto_context_length": 204800,     // from the table above
  "config_context_length": 524288,    // from model.context_length, or 0
  "effective_context_length": 524288, // = config if >0 else auto
  "capabilities": { ... }
}
```

If `auto_context_length` is `0` for a model name that you expect to match, check:
- The model name in `model.default` exactly (no extra whitespace, no provider prefix).
- The substring key in the table (case-sensitive).
- Whether you've shadowed the table with a per-user cache at `~/.hermes/context_length_cache.yaml`.

## Persistent override

`~/.hermes/context_length_cache.yaml` lets you pin context lengths for specific `model@base_url` pairs. Format:

```yaml
context_lengths:
  github_copilot/gpt-4o@http://serverhome:4000: 64000
  github_copilot/gpt-5-mini@http://serverhome:4000: 128000
```

This takes precedence over both the hardcoded table and any `model.context_length` value for that exact `(model, base_url)` pair. Useful when a custom provider returns a different context than the upstream default.
