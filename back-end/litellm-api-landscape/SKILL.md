---
name: litellm-api-landscape
description: "LiteLLM Proxy 暴露的 OpenAI 兼容 API 端点全景 — chat/completions vs responses vs assistants vs completions 的区别、选型、桥接机制，以及 memory（KV）和 RAG（向量存储）两套数据检索体系的对比。"
---

# LiteLLM API Landscape

LiteLLM Proxy 统一了 100+ LLM 供应商的调用方式，暴露出多套 **OpenAI 兼容的文本生成端点**。选错端点会导致功能缺失或兼容性问题。

## OpenAI 文本生成接口概览

| 接口 | 状态 | 核心区别 |
|---|---|---|
| `/v1/chat/completions` | ✅ 主力 | messages 数组输入 → choices output，最广兼容 |
| `/v1/responses` | ✅ 新一代 | input（typed items）→ output（typed items），`previous_response_id` 多轮 |
| `/v1/completions` | ❌ **生命末期**，2026-09-28 最后模型关停 | 纯文本 prompt → text，仅剩 1 个模型 |
| `/v1/assistants` | ❌ **已废弃**，2026-08-26 关停 | Thread/Run/Message 体系 |

详见 `references/openai-interfaces.md`。
详见 `references/completions-deprecation-timeline.md`（弃用时间线）。
详见 `references/responses-model-support-and-bridge.md`（模型支持清单 + 桥接行为）。
详见 `references/deployment-topology-and-testing.md`（serverhome 部署拓扑 + 跨机测试模式）。

## 两套数据检索系统

| 系统 | 端点 | 查询方式 | 适用场景 |
|---|---|---|---|
| KV Memory | `/v1/memory` | 精确 key／前缀匹配 | 用户偏好、配置、简短上下文 |
| Vector Store RAG | `/v1/vector_stores/` + `/v1/rag/` | 语义相似度搜索 | 知识库、文档 QA、需要引用源 |

详见 `references/memory-ecosystem.md`。

## 选型原则

### chat/completions vs responses

**用 chat/completions 当：**
- 需要兼容非 OpenAI 供应商（DeepSeek、Anthropic、Ollama 等）
- 不需要 Web Search / Computer Use / Shell 等内置工具
- 客户端已经有一整套 messages 管理逻辑

**用 responses 当：**
- 目标模型是 OpenAI 原生（或 Azure OpenAI）
- 需要 `web_search_preview` / `computer_use_preview` / `shell` 等内置工具
- 希望服务端管理多轮上下文（`previous_response_id`）
- 需要 Tool Search / Namespaces 节省 tokens
- 需要 server-side compaction（超长上下文自动压缩）
- 需要 WebSocket 低延迟持久连接

### 桥接机制（LiteLLM 关键细节）

当非 OpenAI 模型收到 `/v1/responses` 请求时，LiteLLM 自动桥接到 `/v1/chat/completions`。丢失的特性：
- typed output items（搜索结果、代码执行结果等集成到 output 里会丢失结构化）
- `previous_response_id` 管理多轮上下文（fallback 为 session_id 做替代）
- 部分内置工具不可用

强制桥接方式：
- `use_chat_completions_api: true` 在 model config 中
- `model: "openai/chat_completions/<model>"` 模型名前缀

### ⚠️ `mode: responses` 是有条件的开关（非自动激活）

`mode: responses` 写在 LiteLLM `config.yaml` 里**不会让客户端自动改用 `/v1/responses`**。OpenAI Python 客户端由**调用方法**决定路径：

| 客户端调用的方法 | 实际请求路径 | 触发 LiteLLM 哪个分支 |
|---|---|---|
| `client.chat.completions.create(...)` | `/v1/chat/completions` | chat completions handler，**忽略** `mode: responses` |
| `client.responses.create(...)` | `/v1/responses` | responses handler，**才会用到** `mode: responses` |

要真正发挥 `mode: responses` 的效果，需要**双管齐下**：
1. LiteLLM 配置层 `model_info.mode: responses` ✅
2. 客户端代码改用 `client.responses.create()` ❌（必须改源码）

仅改 LiteLLM 配置而客户端仍用 `chat.completions.create()`，`mode: responses` **对主对话无效**。Hermes 的 `custom:litellm` provider（OpenAI 兼容客户端）默认走 chat completions — 这是当前现状（主对话）。

**重要例外**：Hermes 辅助功能（vision / web_extract / session_search）走的是 `agent/auxiliary_client.py` 里的 `_CodexCompletionsAdapter`，内部把 `client.chat.completions.create(...)` 转成 `client.responses.create(...)`，所以 `mode: responses` 对辅助功能是**实际生效**的。详见 `references/deployment-topology-and-testing.md` 第 4 节。

详见 `references/deployment-topology-and-testing.md`。

### memory 选型

- **短小的用户偏好** → `/v1/memory`（精确读取，no embedding needed）
- **大量文档需要语义搜索** → vector store（需要后端：OpenAI/Bedrock/PG Vector 等）
- **跨会话 Agent 记忆（对话历史 + 画像）** → Honcho（自带后端，Hermes 已集成）
- **从对话自动提炼事实** → Mem0（事实提取能力强，需额外维护）

## 已废弃端点注意

- `/v1/assistants` — OpenAI 已标记 deprecated，**2026-08-26 关停**
- 迁移目标：`/v1/responses`（首选）或 `/v1/chat/completions`（通用）
- LiteLLM 仍支持 Assistants 端点作为 pass-through，但不推荐新建

## 数据来源

- https://docs.litellm.ai/docs/supported_endpoints
- https://docs.litellm.ai/docs/response_api
- https://docs.litellm.ai/docs/completion
- https://docs.litellm.ai/docs/memory_management
- https://docs.litellm.ai/docs/completion/knowledgebase
- https://docs.litellm.ai/docs/vector_stores/search
