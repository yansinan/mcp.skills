# Dashscope `json_object` Limitation

## Error signature

```
DashscopeException - <400> InternalError.Algo.InvalidParameter:
'messages' must contain the word 'json' in some form, to use 'response_format' of type 'json_object'.
```

## Root cause

Dashscope (阿里云通义千问) enforces a rule: when `response_format: { type: "json_object" }` is set, at least one message in the conversation must literally contain the substring "json". If no message does, the request is rejected with 400.

## How it manifests in Hermes

1. Main agent sets `api_mode: codex_responses` in config.yaml
2. Aux features (`approval`, `title_generation`) inherit this mode
3. `CodexAuxiliaryClient` wraps calls → routes through `/v1/responses`
4. LiteLLM's `_CodexCompletionsAdapter` converts back to `/v1/chat/completions`, injecting `response_format: json_object` for structured output calls
5. Dashscope receives `json_object` with messages lacking "json" → 400

## Fix

### Option A: Per-feature `api_mode: chat_completions`

Add `api_mode: chat_completions` to the specific aux feature in `config.yaml`:

```yaml
auxiliary:
  approval:
    provider: custom:litellm
    model: free
    api_mode: chat_completions   # ← bypasses _CodexCompletionsAdapter
    base_url: ''
    api_key: ''

  title_generation:
    provider: custom:litellm
    model: free
    api_mode: chat_completions
    base_url: ''
    api_key: ''
```

This bypasses `_CodexCompletionsAdapter` entirely — the feature sends plain `/v1/chat/completions` without `response_format: json_object`.

### Option B: Switch model

Assign a model that handles `json_object` correctly (deepseek-v4-flash, minimax, etc.).

## Verification

```python
from agent.auxiliary_client import _resolve_task_provider_model, resolve_provider_client, CodexAuxiliaryClient

# Check api_mode resolution
provider, model, base_url, api_key, api_mode = _resolve_task_provider_model("approval")
print(f"api_mode={api_mode}")  # Should show "chat_completions"

# Check client type
client, resolved = resolve_provider_client(
    "custom:litellm", model="free",
    api_mode="chat_completions",
)
print(f"is CodexAuxiliaryClient: {isinstance(client, CodexAuxiliaryClient)}")
# Should be False — plain OpenAI client
```

## Code reference

- `agent/auxiliary_client.py:4826` — reads `api_mode` from per-task config
- `agent/auxiliary_client.py:3246-3258` — falls back to main runtime `api_mode`
- `agent/auxiliary_client.py:3777-3779` — per-task override wins over provider entry
- `agent/auxiliary_client.py:3843-3848` — `entry_api_mode == "codex_responses"` gates wrapping
