---
name: hermes-model-config
description: "Configure Hermes Agent models — default model, context_length, auxiliary slot assignment, delegation model. Covers the single global context_length field, the auto-detect lookup table, and the per-slot semantics that bite first-time configurers."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [hermes, configuration, models, context-length, auxiliary, litellm]
---

# Hermes Model Configuration

How to set the default model, context window, and per-task auxiliary models in Hermes Agent. Load this skill before any task that touches `model.*`, `auxiliary.*`, or `delegation.*` in `config.yaml`.

## Trigger conditions

- User asks to switch default model, provider, or context window
- User asks to inspect/change "辅助模型" (auxiliary models) for vision, compression, web extract, etc.
- A session hits a context-length error or truncation
- User wants different models for different tasks (e.g. cheap model for compression, big model for main)
- Setting up a new Hermes profile/installation and needs to configure the model stack

## Quick start

```bash
# Show current model + context
hermes config show model

# Switch default model (also clears context_length so it auto-detects)
hermes config set model.default <model_id>

# Set explicit context window (overrides auto-detect for ALL models)
hermes config set model.context_length <bytes>

# Set to 0 → auto-detect from internal lookup table
hermes config set model.context_length 0

# Change auxiliary slot
hermes config set auxiliary.vision.model <model_id>
hermes config set auxiliary.compression.model <model_id>

# Verify effective resolution via WebUI API
curl -s http://localhost:8787/api/model/info | python3 -m json.tool
```

## The four most important things

### 1. `context_length` is ONE global field, not per-model

`model.context_length` is a single integer that Hermes uses for **every** model call — main chat, auxiliary compression, subagent delegation, all of it. There is no per-model override. Setting it to 200000 means *every* model (including a 1M-capable one) gets capped at 200K.

This is the #1 surprise. The user's mental model "minimax 512K, deepseek 1M" cannot be expressed as-is; you must pick one value (or rely on auto-detect) and accept the trade-off.

### 2. Setting `context_length` to 0 enables auto-detect

When `context_length` is `0` (or missing), Hermes calls `get_model_context_length()` which consults a hardcoded lookup table in `agent/model_metadata.py`. The lookup uses **substring matching** (longest key wins). The model name you put in `model.default` is what gets matched.

Selected entries (full table: `references/auto-detect-context-lengths.md`):

| Model name (substring) | Context |
|---|---|
| `minimax-m3` | 1,000,000 |
| `minimax` | 204,800 |
| `deepseek-v4-flash` | 1,000,000 |
| `deepseek-chat`, `deepseek-reasoner` | 1,000,000 |
| `deepseek` | 128,000 |

**Pitfall:** the bare name `minimax` matches 200K; you must use `minimax-m3` to get the 1M window. The two are different slugs for the same underlying model in this user's litellm setup.

### 3. Auxiliary slots are independent providers, not "extras" of the main

The `auxiliary` block has 10 named sub-slots, each with its own `provider` + `model`:

| Slot | Used for | Default |
|---|---|---|
| `vision` | Image analysis fallback | `auto` (inherits main) |
| `web_extract` | Long-page summarization before LLM reads it | `auto` |
| `compression` | Auto context compression near token limit | `auto` |
| `skills_hub` | Skill discovery / installation | `auto` |
| `approval` | Smart command-approval LLM | `auto` |
| `mcp` | MCP-related auxiliary calls | `auto` |
| `title_generation` | Auto-name sessions | `auto` |
| `triage_specifier` | Triage incoming tasks | `auto` |
| `kanban_decomposer` | Kanban task decomposition | `auto` |
| `profile_describer` | Profile description generation | `auto` |
| `curator` | Skill curator background pass | `auto` |

Setting any one of them overrides only that slot. **`auto` (provider: auto, model: empty) means "use the main model and its config"** — including its context_length. So if you set `model.context_length: 524288` and `auxiliary.compression.model: deepseek-v4-flash`, compression runs on deepseek but is still capped at 524288.

### 4. `delegation.model` is also independent

`delegation.*` is the model used by the `delegate_task` tool for subagents. Default is empty (= inherit main). Set it explicitly only if you want subagents to use a different model than the main loop (e.g. cheap model for bulk subtasks).

## Common workflows

### Switch default model cleanly

```bash
hermes config set model.default <new_model>
# Optionally clear context_length to use auto-detect for the new model:
hermes config set model.context_length 0
```

**Source:** `hermes_agent/hermes_cli/web_server.py:655-669` — the `set_model_assignment` helper explicitly pops `context_length` when switching models because the new model may have a different window. The CLI does this for you, but the `auto` mode relies on the table above.

### Set context window to a specific value

```bash
hermes config set model.context_length 524288   # 512K
hermes config set model.context_length 1000000  # 1M
hermes config set model.context_length 0        # auto-detect
```

Verify with: `curl -s http://localhost:8787/api/model/info | jq .effective_context_length`

### Configure an auxiliary slot for a different model

```bash
# Example: use deepseek for compression (cheap, long context)
hermes config set auxiliary.compression.provider custom:litellm
hermes config set auxiliary.compression.model deepseek-v4-flash
```

**Gotcha:** if `auxiliary.compression.provider` is `auto`, setting just `model` does nothing. You need to set `provider` to a concrete value first (e.g. `custom:litellm` if you have one in `custom_providers`).

### Verify what's actually being used

```bash
# Effective resolution (auto vs config, capabilities, etc.)
curl -s http://localhost:8787/api/model/info | python3 -m json.tool
```

Returns:

```json
{
  "model": "minimax",
  "provider": "custom",
  "auto_context_length": 204800,
  "config_context_length": 524288,
  "effective_context_length": 524288,
  "capabilities": {"supports_tools": true, ...}
}
```

**`effective_context_length = config_context_length if > 0 else auto_context_length`** — that's the actual value used at runtime.

## Pitfalls

- **Don't trust the server's `/v1/models` for context length** — OpenAI-format `/v1/models` doesn't return context info. The `minimax` and `deepseek-v4-flash` entries from litellm all return `{"owned_by": "openai"}` only. The 200K / 1M values come from Hermes's hardcoded table, not the upstream.
- **Auxiliary provider must match the model** — if you set `auxiliary.compression.model: deepseek-v4-flash` without setting `provider: custom:litellm`, you may get an empty/default provider. Always pair model + provider.
- **Context_length is read once at session start** — changing it mid-session does not affect the running process. You need `/reset` (chat) or `hermes gateway restart` (gateway).
- **`approval` and `title_generation` aux slots send structured output (`response_format: json_object`)** — the model backing these slots MUST support `response_format: json_object`. Some providers (e.g. Dashscope/阿里云 via LiteLLM) reject json_object unless the messages literally contain the word "json". If these slots get 400 errors with `'messages' must contain the word 'json'`, the model assigned to them doesn't support the response_format correctly.
- **Auxiliary slots with `api_mode: codex_responses` route through `_CodexCompletionsAdapter`** — this adapter bridges `/v1/responses` to `/v1/chat/completions` and injects `response_format: json_object` for structured calls (approval, title_generation). If the backing model's provider rejects json_object, the error appears as a Dashscope (or similar) 400.

  **Two fixes when a model can't handle json_object:**
  1. **Switch model** — assign a model that supports json_object (e.g. deepseek-v4-flash, minimax).
  2. **Opt out of codex_responses per feature** — add `api_mode: chat_completions` to the individual aux feature entry in config.yaml. This bypasses `_CodexCompletionsAdapter` entirely, so the feature sends plain `/v1/chat/completions` without `response_format: json_object`. Allows keeping the original model (e.g. `free` → Dashscope). Example:
     ```yaml
     auxiliary:
       approval:
         provider: custom:litellm
         model: free
         api_mode: chat_completions
         base_url: ''
         api_key: ''
     ```

- **Every aux feature can set its own `api_mode`** — config.yaml `auxiliary.<task>.api_mode` overrides the inherited main `api_mode` for that feature only. Valid values: `chat_completions`, `codex_responses`, `anthropic_messages`. Leave empty to inherit. Useful when a feature needs a different wire format than the main model (e.g. approval via plain chat completions while the main agent uses codex_responses).

  **Two fixes when a model can't handle json_object:**
  1. **Switch model** — assign a model that supports json_object (e.g. deepseek-v4-flash, minimax).
  2. **Opt out of codex_responses per feature** — add `api_mode: chat_completions` to the individual aux feature entry in config.yaml. This bypasses `_CodexCompletionsAdapter` entirely, so the feature sends plain `/v1/chat/completions` without `response_format: json_object`. Allows keeping the original model (e.g. `free` → Dashscope). Example:
     ```yaml
     auxiliary:
       approval:
         provider: custom:litellm
         model: free
         api_mode: chat_completions
         base_url: ''
         api_key: ''
     ```

- **Every aux feature can set its own `api_mode`** — config.yaml `auxiliary.<task>.api_mode` overrides the inherited main `api_mode` for that feature only. Valid values: `chat_completions`, `codex_responses`, `anthropic_messages`. Leave empty to inherit. Useful when a feature needs a different wire format than the main model (e.g. approval via plain chat completions while the main agent uses codex_responses).
- **WebUI schema has a virtual `model_context_length` field** — appears adjacent to `model` in the WebUI form. This is the same as `model.context_length`, just surfaced separately for clarity. Editing either is equivalent.

## File locations

- Config: `~/.hermes/config.yaml`
- API key storage: `~/.hermes/.env` (for `MINIMAX_API_KEY` etc.)
- Auto-detect table: `~/.hermes/hermes-agent/agent/model_metadata.py` (substring match → context)
- WebUI endpoint: `~/.hermes/hermes-agent/hermes_cli/web_server.py:1957` (`/api/model/info`)

## Related

- Bundled `hermes-agent` skill — high-level CLI reference and config-section overview
- `local/hermes-webui` — WebUI deployment (different concern: hosting, not model config)
