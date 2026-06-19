# Provider-Specific `response_format` Quirks

When an API call includes `response_format: { "type": "json_object" }`, different providers enforce different constraints.

## Dashscope (阿里云通义千问)

**Restriction:** `'messages' must contain the word 'json' in some form, to use 'response_format' of type 'json_object'.`

The word "json" must appear literally somewhere in the messages array (usually the system or user prompt). A request with `json_object` but no "json" in any message text → 400 error.

**Workarounds:**
1. Add a system instruction like `"Always respond in valid JSON format."` — the word "JSON" satisfies the check.
2. Switch to a provider that doesn't enforce this rule (OpenAI, DeepSeek, etc.).
3. Use `response_format: { "type": "text" }` with a JSON schema via prompt engineering instead.

**Tip:** To test, send a simple request with the exact messages to Dashscope's API directly. If it passes with "JSON" in the prompt and fails without, this is the cause.

## OpenAI

No restriction on json_object — any messages work. However, OpenAI does require the model to actually output valid JSON; if the model doesn't comply, the response may be malformed but there's no 400-level rejection based on prompt content.

## DeepSeek

Supports `response_format: json_object` freely, no keyword requirement.

## Affected patterns in this deployment

Hermes with `api_mode: codex_responses` uses the `_CodexCompletionsAdapter` (agent/auxiliary_client.py) which bridges `/v1/responses` to `/v1/chat/completions` and injects `response_format: json_object` for structured auxiliary calls. Two aux slots that hit this:

| Slot | Purpose | 
|---|---|
| `approval` | Tool-call approval — asks LLM for yes/no structured response |
| `title_generation` | Session naming — asks for a concise title |

If either slot uses a Dashscope-routed model (`free`), the request fails with the json_object error. Fix: assign these slots a model that supports json_object (deepseek-v4-flash, minimax, etc.).
