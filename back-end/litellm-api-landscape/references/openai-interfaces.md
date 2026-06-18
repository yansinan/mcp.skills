# OpenAI 文本生成接口对比（在 LiteLLM 中）

数据来源：https://docs.litellm.ai/docs/response_api 、 https://docs.litellm.ai/docs/completion

## 四种接口

### `/v1/chat/completions` — 主力

**输入**：`messages` 数组（`{role, content}` 对）
**输出**：`choices[0].message.content`

```python
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello"}]
)
```

- ✅ 100+ 供应商全部支持（LiteLLM 统一为 OpenAI 格式）
- ✅ streaming、tool calling、structured output、vision
- ❌ 多轮上下文由客户端自己管理 messages 数组

### `/v1/responses` — OpenAI 新一代

**输入**：`input`（字符串或 typed items 数组）
**输出**：`output` 数组（每个 item 有 type）

```python
response = client.responses.create(
    model="gpt-4o",
    input="Hello",
    previous_response_id="resp_abc123"  # 服务端管理多轮
)
```

**独有特性**（chat/completions 没有）：

| 特性 | 说明 |
|---|---|
| `previous_response_id` | 服务端管理上下文，客户端免拼 messages |
| `web_search_preview` tool | 内置搜索引擎 |
| `computer_use_preview` tool | 操作桌面/浏览器 |
| `shell` tool | 内置代码执行容器 |
| `image_generation` tool | 图片生成流式输出 |
| Tool Search / Namespaces | 延迟加载工具定义，省 tokens |
| server-side compaction | 上下文超阈值自动压缩 |
| WebSocket 模式 | 低延迟持久连接 |
| typed output items | 搜索结果、调用结果都是结构化 item |
| MCP tools | 原生 MCP 协议支持 |
| Context-Free Grammar | Lark 语法约束输出格式 |
| 可 GET/DELETE response | 像管理资源一样管理回复 |

**桥接机制**：非 OpenAI 模型自动 fallback 到 chat/completions，但丢失 typed items、previous_response_id、独有工具。

### `/v1/completions` — 原始 text completion

```python
response = client.completions.create(
    model="gpt-3.5-turbo-instruct",
    prompt="Once upon a time"
)
```

- 输入纯文本，输出纯文本
- 仅少数 instruct 类模型支持
- 几乎已淘汰，建议迁移

### `/v1/assistants` — 已废弃

- 包含 Thread / Message / Run / Assistant 等资源
- **OpenAI 官方标记 deprecated，2026-08-26 关停**
- 迁移目标：`/v1/responses`（首选）或 `/v1/chat/completions`
- LiteLLM 仍支持 pass-through，但不推荐新建

## 快速选型表

| 你的需求 | 推荐接口 |
|---|---|
| 通用对话、ChatBot | `chat/completions` |
| 需要内置搜索能力的 Agent | `responses` + `web_search_preview` |
| 需要 Computer Use | `responses` + `computer_use_preview` |
| Agent 需要内置代码执行 | `responses` + `shell` |
| 大量工具定义想省 tokens | `responses` + Tool Search / Namespaces |
| 低延迟持久连接 | `responses` + WebSocket |
| 超长会话需要自动压缩 | `responses` + server-side compaction |
| 多供应商后端（DeepSeek 等） | `chat/completions` |
| 旧系统维护（Assistants) | 尽快迁移到 `responses` |
