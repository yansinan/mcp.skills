# agent-browser `chat` — AI 聊天架构

> 基于 agent-browser 0.27.0 Rust 源码（[cli/src/chat.rs](https://github.com/vercel-labs/agent-browser/blob/main/cli/src/chat.rs)、[cli/src/native/stream/chat.rs](https://github.com/vercel-labs/agent-browser/blob/main/cli/src/native/stream/chat.rs)）的逆向分析。
> 安装：`npm install -g agent-browser` → `~/.hermes/node/bin/agent-browser`

## 一句话

`agent-browser chat` 是一个**内置的 AI 聊天客户端**，把自然语言翻译成 `agent-browser` CLI 命令。LLM 通过 Vercel AI Gateway 调用，只有一个工具：`agent_browser(command)`。

## 依赖：Vercel AI Gateway

chat 命令后端是一个统一 API 代理 `https://ai-gateway.vercel.sh`（Vercel 托管）：

- **端点**：`{AI_GATEWAY_URL}/v1/chat/completions`（OpenAI 协议）
- **认证**：`AI_GATEWAY_API_KEY` 环境变量
- **默认模型**：`anthropic/claude-sonnet-4.6`（可通过 `AI_GATEWAY_MODEL` 或 `--model` 覆盖）
- **支持的模型数**：200+ 个（Alibaba Qwen、Anthropic Claude、OpenAI GPT、Google Gemini、xAI Grok、DeepSeek、Mistral、Meta Llama 等）

Vercel AI Gateway 本质上与 LiteLLM Proxy 同类——一个统一 API 代理层，附带用量监控、预算控制、负载均衡、回退/重试功能。对于已有自建 LiteLLM 的用户，这是一个多余的中间人。

## 架构

```
用户输入
    │
    ▼ System Prompt (约几十KB)
    │   ┌──────────────────────────────────────────────┐
    │   │ "You are an AI assistant that controls a      │
    │   │  browser through agent-browser..."            │
    │   │  + <skill name="agent-browser">{SKILL.md}</skill>  │
    │   │  + <skill name="slack">{SKILL.md}</skill>         │
    │   │  + <skill name="electron">{SKILL.md}</skill>      │
    │   │  + <skill name="dogfood">{SKILL.md}</skill>      │
    │   │  + <skill name="agentcore">{SKILL.md}</skill>    │
    │   └──────────────────────────────────────────────┘
    │
    ▼ Vercel AI Gateway
    │   POST /v1/chat/completions
    │   { model, messages, tools: [agent_browser], stream: true }
    │
    ▼ LLM 回复 (SSE stream)
    │   文字描述 ← 打印到 stdout
    │   + 工具调用 ← execute_chat_tool() 解析执行
    │
    ▼ agent-browser CLI
    │   std::process::Command 执行命令
    │   输出作为 tool result 返回给 LLM
    │
    ▼ 循环，直到模型不返回 tool_calls（最多 50 步，5 分钟超时）
```

## System Prompt 的完整构造

`get_system_prompt()` 函数（`cli/src/native/stream/chat.rs`）：

```rust
// 1. 加载所有 skill 文件
// 扫描路径：../skills/（相对于可执行文件）
const SKILL_NAMES: &[&str] = &["agent-browser", "slack", "electron", "dogfood", "agentcore"];

// 2. 去掉 YAML 前置元数据（---...---）
fn strip_frontmatter(s: &str) -> &str { ... }

// 3. 组装成 XML 块嵌入 system prompt
"<skill name=\"agent-browser\">\n{SKILL.md content}\n</skill>"
```

所以 System Prompt = 硬编码角色指令（约 500 字符）+ skill 文档（几十KB）。LLM 知道所有命令、参数、用法模式。

## 唯一的工具

```rust
const CHAT_TOOLS: &str = r#"[{
    "type":"function",
    "function":{
        "name":"agent_browser",
        "description":"Execute an agent-browser command...",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "e.g. 'agent-browser open https://...' or 'agent-browser snapshot -i'"
                }
            },
            "required": ["command"]
        }
    }
}]"#;
```

LLM 只能调用这一个工具，传一个 `command` 字符串。

## 命令白名单（不允许随意 shell）

`execute_chat_tool()` 严格校验：

1. **只允许指定命令**：`open`, `click`, `fill`, `snapshot`, `screenshot`, `eval`, `close`, `tab`, `network`... 约 100 个白名单命令
2. **只允许全局 flag**：`--session`, `--engine`
3. **禁止链式执行**：`split("&&")` 只取第一段，`split(";")` 只取第一段
4. **禁止非 agent-browser 命令**：不允许任意 shell

## 两种模式

### 单轮：`chat "指令"`

```rust
async fn run_single_turn(session, model, message, verbosity, json_mode) {
    let mut messages = vec![system_prompt];
    messages.push(user_message);
    run_chat_turn().await;
    // 执行完结束，不保存任何东西
}
```

**完全 stateless** — 每次 `chat "..."` 都是全新上下文。

### REPL：`chat`（TTY 交互）

```rust
async fn run_interactive(session, model, verbosity, json_mode) {
    let mut messages = vec![system_prompt];
    loop {
        let input = read_line();       // 读用户输入
        messages.push(user_msg);
        // 上下文压缩检查（见下文）
        run_chat_turn().await;         // 发送消息 + 执行工具调用
        // 工具结果自动追加到 messages
    }
}
```

**有完整的对话历史**累积，直到退出。

## 上下文压缩

当累积消息超过 **200,000 字符**（约 50K tokens）时：

```rust
const COMPACT_THRESHOLD_CHARS: usize = 200_000;
const KEEP_RECENT_MESSAGES: usize = 6;

// 1. 在 user message 边界找安全分割点
let split = find_safe_split(&messages, KEEP_RECENT_MESSAGES);

// 2. 用另一个 LLM 调用来 summarize 旧消息
let summary = summarize_for_compaction(client, url, api_key, model, &messages[1..split]);

// 3. 替换：system + summary + 最近 6 轮
messages = vec![system, summary_msg];
messages.extend(recent);
```

摘要 prompt：
```
"Summarize this browser automation conversation concisely.
Preserve: URLs visited, actions performed, current page state,
errors encountered, and user goals. Output only the summary."
```

## 输出模式

| flag | 行为 |
|---|---|
| 默认（无 flag） | 流式输出文字到 stdout，工具调用提示到 stderr |
| `-q` / `--quiet` | 隐藏工具调用行，只显示 AI 文字回复 |
| `-v` / `--verbose` | 显示每条工具调用的原始输出 |
| `--json` | 整条 JSON 输出（`{"success": true, "text": "...", "tool_calls": [...]}`） |

## 截图处理

自动将截图路径→base64 data URL→作为 tool result 的 `image` 字段返回：
- JPEG 压缩到 1024px 宽、quality=40
- LLM 可以"看到"图片（多模态模型时）

## 与 Hermes Chat 核心差异

| 维度 | agent-browser chat | Hermes Chat |
|---|---|---|
| **定位** | 浏览器 CLI 内置的 AI 助手 | 全栈 AI Agent |
| **工具集** | 1 个工具（`agent_browser command`） | 40+ 工具 |
| **System Prompt** | 固定角色 + skill 文件注入 | 完整 system prompt + 工具定义 + memory 注入 |
| **对话历史** | REPL 有，单轮无 | 全有 |
| **持久化** | 无（退出即丢失） | state.db 持久化 |
| **记忆** | 无 | memory + session_search |
| **LLM 后端** | Vercel AI Gateway（固定） | 可配置（LiteLLM / OpenAI / 自定义等） |
| **上下文压缩** | 200K chars 触发摘要 | 无（靠大 context window） |
| **能力边界** | 仅浏览器操作 | 全栈（终端、文件、web、代码执行等） |

## 密钥

- 实现语言：**Rust**（预编译二进制，源码不可 grep 本地）
- 源码仓库：`vercel-labs/agent-browser`，`cli/src/` 下
- `run_chat_turn()` 有 50 步硬限制、300s 全局超时、60s 单工具超时
- HTTP 客户端：`reqwest`，stream 用 `futures_util::StreamExt`
