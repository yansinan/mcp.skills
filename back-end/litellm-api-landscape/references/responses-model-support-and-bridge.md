# Responses API 模型支持清单 + 桥接行为

数据来源：https://developers.openai.com/api/docs/models/all（2026-06 确认）

## 原生支持 Responses API 的 OpenAI 模型

以下所有当前活跃（非 deprecated）的 OpenAI 模型都支持 `/v1/responses` 原生协议。

### 旗舰 / 主流

| 模型 ID | 档次 |
|---|---|
| `gpt-5.5`、`gpt-5.5-pro` | 旗舰推理+编码 |
| `gpt-5.4`、`gpt-5.4-pro` | 主流编码+专业工作 |
| `gpt-5.4-mini`、`gpt-5.4-nano` | 低成本/低延迟 |
| `gpt-5.3-codex` | Agentic 编码 |
| `gpt-5`、`gpt-5-pro`、`gpt-5-mini`、`gpt-5-nano` | 上一代 |
| `gpt-5.1`、`gpt-5.2`、`gpt-5.2-pro` | 上一代 |
| `o3`、`o3-pro` | 推理模型 |
| `gpt-4.1`、`gpt-4.1-mini` | 非推理 |
| `gpt-4o-mini` | 小模型 |

### embedding / 其他

`text-embedding-3-large`、`text-embedding-3-small`、`text-embedding-ada-002` 等也支持 Responses API。

## 不原生支持 / deprecated 的模型

以下模型通过 LiteLLM 桥接（→ `/v1/chat/completions`）或不可用：

| 模型 | 状态 | Responses API |
|---|---|---|
| `gpt-4o` | ❌ Deprecated（2026-10-23 关停） | 可通过桥接 |
| `o1`、`o1-pro` | ❌ Deprecated | 可通过桥接 |
| `o3-mini`、`o4-mini` | ❌ Deprecated | 可通过桥接 |
| `gpt-4-turbo` | ❌ Deprecated | 可通过桥接 |
| `gpt-3.5-turbo` | ❌ Deprecated | 可通过桥接 |
| `gpt-3.5-turbo-instruct` | ❌ Deprecated（2026-09-28 关停） | ❌ completions 端点 |
| **DeepSeek** | 非 OpenAI | ⚠️ 桥接模式 |
| **Anthropic** | 非 OpenAI | ⚠️ 桥接模式 |
| **Gemini** | 非 OpenAI | ⚠️ 桥接模式 |

## LiteLLM 桥接机制详解

### 自动桥接规则

```
你调用 /v1/responses (input=...)
    │
    ├─ 如果模型原生支持 Responses API（OpenAI 活跃模型）
    │   → 直通上游，全部特性可用
    │
    └─ 如果模型不支持（DeepSeek / Anthropic / Gemini / 自定义）
        → LiteLLM 自动桥接到 /v1/chat/completions
```

### 桥接后能工作的功能

| 功能 | 桥接后 |
|---|---|
| 基本文本对话 | ✅ 正常 |
| Streaming | ✅ 正常 |
| Function calling | ✅ 正常 |
| Structured output | ✅ 正常 |
| Multi-turn（`previous_response_id`） | ✅ 桥接成 messages 拼接 |

### 桥接后会丢失的功能

| 功能 | 原因 |
|---|---|
| `web_search_preview` tool | 底层 provider 不支持 |
| `computer_use_preview` tool | 底层 provider 不支持 |
| 内置 `shell` tool（代码执行） | 底层 provider 不支持 |
| Tool Search / Namespaces（延迟加载工具） | 需 OpenAI 原生支持 |
| Context-Free Grammar（语法约束） | 需 OpenAI 原生支持 |
| WebSocket 模式 | 桥接不支持 |
| Server-side compaction | 仅 OpenAI/Azure 原生 |
| typed output items（搜索结果以独立 item 返回） | 桥接展平为 message |

### 强制桥接开关

对于通过 `openai/` 前缀访问的自定义 endpoint（vLLM、llama.cpp、LM Studio 等），LiteLLM 默认**不会自动桥接**，需手动设置：

```yaml
# config.yaml
litellm_params:
  model: openai/my-custom-model
  use_chat_completions_api: true
```

或通过模型名前缀：

```
model: "openai/chat_completions/<model>"
```

## 对你的配置（DeepSeek 用户）的影响

你的 LiteLLM 配置中只有 `deepseek/deepseek-v4-flash` 一个活跃模型。DeepSeek 不支持 Responses API 原生协议，走桥接模式。

| 你想做的事 | 可行性 |
|---|---|
| 用 `/v1/responses` 做基本对话 | ✅ 能跑，但无额外收益 |
| 用 `web_search_preview` | ❌ DeepSeek 不支持 |
| 用 `previous_response_id` 多轮 | ✅ 桥接为 session_id |
| 用 Tool Search / Namespaces | ❌ 需 OpenAI 原生模型 |

**结论**：对 DeepSeek 用 `/v1/responses` 是有额外桥接开销但无收益的等价替换。保持 `/v1/chat/completions` 最优。
