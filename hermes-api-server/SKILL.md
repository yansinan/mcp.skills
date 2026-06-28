---
name: hermes-api-server
title: Hermes Agent API Server 实战：Token 节约 + Session 复用
category: local
tags: [hermes, api, openai-compatible, runs, sessions, automation, mcp]
description: Hermes Agent API Server 端点手册 + Python 客户端库 + Token 节约策略。含 /v1/responses /v1/runs /api/sessions 三种 session 复用方案的实测对比、自适应轮询、跨机 agent 协作模板。
source: /home/dr/.hermes/hermes-agent/website/docs/user-guide/features/api-server.md (v0.16.0); 实战 2026-06-24
support_files:
  - scripts/hermes_api_client.py — 完整 Python 客户端
  - references/api-server.md — 官方文档 20KB 原始版
---

# Hermes Agent API Server 实战

把远端 hermes-agent 当 OpenAI 兼容 backend 调用。本文核心关注 **token 节约 + session 复用**，因为第一轮就吃掉 ~25k tokens（system prompt）。

## 目录

1. [启用 & 认证](#1-启用--认证)
2. [端点速查](#2-端点速查)
3. [Session 复用的 3 种模式（关键）](#3-session-复用的-3-种模式关键)
4. [Token 节约策略](#4-token-节约策略)
5. [Python 客户端库](#5-python-客户端库)
6. [跨机 Skill 同步场景](#6-跨机-skill-同步场景)
7. [实战 Debug 流程](#7-实战-debug-流程)
8. [安全注意事项](#8-安全注意事项)

---

## 1. 启用 & 认证

服务端（被调用的机器）：

```bash
# ~/.hermes/.env 或 profile 的 .env
API_SERVER_ENABLED=true
API_SERVER_PORT=8642          # 默认；profile 模式 8643/8644
API_SERVER_HOST=0.0.0.0       # 仅远端需要时；否则 127.0.0.1
API_SERVER_KEY=$(openssl rand -hex 32)  # 必填，≥16 字符
```

启动：`hermes gateway`（或 `systemctl --user restart hermes-gateway.service`）

> **⚠️ API_SERVER_KEY < 16 字符 → 服务无限循环拒绝启动**
> 这是 v0.16.0 的安全保护。见 `references/api-server.md` L393-395。建议用 `openssl rand -hex 32` 生成。

认证：

```
Authorization: Bearer <API_SERVER_KEY>
```

所有 `/v1/*` 和 `/api/*` 端点强制 bearer auth。

---

## 2. 端点速查

| 端点 | 用途 | 返回值类型 |
|---|---|---|
| `GET /v1/models` | 模型发现 | 200 JSON |
| `GET /v1/capabilities` | 探测支持的功能列表 | 200 JSON |
| `GET /health` | 健康检查 → `{"status":"ok"}` | 200 JSON |
| `GET /health/detailed` | 含 active session/agent 详情的健康检查 | 200 JSON |
| `GET /v1/skills` | 列出所有 skill 元数据 | 200 JSON |
| `GET /v1/toolsets` | 列出 toolset 及具体 tools | 200 JSON |
| `POST /v1/chat/completions` | OpenAI 标准格式（无状态） | 200 SSE/JSON |
| `POST /v1/responses` | **有状态多轮，session 自动合并** | 200 JSON |
| `POST /v1/runs` | 异步长任务 → 202 + `run_id` | 202 JSON |
| `GET /v1/runs/{id}` | 轮询 run 状态 | 200 JSON |
| `GET /v1/runs/{id}/events` | SSE 实时进度 | 200 SSE |
| `POST /v1/runs/{id}/stop` | 中断运行 | 200 JSON |
| `POST /v1/runs/{id}/approval` | 解决审批卡点 | 200 JSON |
| `/api/sessions/*` | session CRUD + chat（见下方） | 见各子端点 |
| `/api/jobs/*` | cron/定时任务 CRUD | 见各子端点 |

### /api/sessions/* 子端点

| Method | Path | 用途 |
|---|---|---|
| `GET` | `/api/sessions` | 列出 sessions（`limit`/`offset`/`source`/`include_children`） |
| `POST` | `/api/sessions` | 创建空 session |
| `GET` | `/api/sessions/{id}` | 读 session 元数据 |
| `PATCH` | `/api/sessions/{id}` | 更新 title 或 end_reason |
| `DELETE` | `/api/sessions/{id}` | 删除 |
| `GET` | `/api/sessions/{id}/messages` | 消息历史 |
| `POST` | `/api/sessions/{id}/fork` | 分支（同 `/branch` 语义） |
| `POST` | `/api/sessions/{id}/chat` | **同步跑一轮（同 session）** |
| `POST` | `/api/sessions/{id}/chat/stream` | SSE 单轮（`assistant.delta`, `tool.started`, `tool.completed`） |

---

## 3. Session 复用的 3 种模式（关键）

这是 **token 节约的核心**。如果每个请求都开新 session，每轮都要重吃 ~25k tokens 的 system prompt。复用 session 后只传增量。

### 模式 A：`/v1/responses` + `conversation`（推荐）

**文档证据**（`references/api-server.md` L175-187）:

> "The server reconstructs the full conversation from the stored response chain… Chained requests also share the same session, so multi-turn conversations appear as a single entry in the dashboard and session history."
>
> "Use the `conversation` parameter instead of tracking response IDs… The server automatically chains to the latest response in that conversation."

```python
# 三轮对话共享同一个 session，只需一个 conversation 名称
client.chat("步骤 1: 做 A", conversation="my-project")
client.chat("步骤 2: 做 B", conversation="my-project")
client.chat("步骤 3: 验证", conversation="my-project")
```

**优点**: 最简单、session 自动合并、无需管 response_id

### 模式 B：`/api/sessions/{id}/chat`（显式控制）

**文档证据**（`references/api-server.md` L328-343）:

> POST /api/sessions/{id}/chat — "Run one synchronous agent turn"

```python
sid = client.create_session("my-task").id
client.chat_in_session(sid, "执行步骤 A")
client.chat_in_session(sid, "执行步骤 B")
```

**优点**: 同步返回、显式 session 控制、轮询开销为零
**缺点**: 不能看到 tool 进度（同步等终态）

### 模式 C：`/v1/runs` + `previous_response_id`（长任务异步）

**文档证据**（`references/api-server.md` L247）:

> "Runs accept … optional `session_id`, `instructions`, `conversation_history`, or `previous_response_id`"

**实验发现**: `previous_response_id` 能让 agent 记得上下文，但 **session 记录不合并**（`parent_session_id: None`）。`conversation` 字段在 `/v1/runs` 上**不在文档中**（我们是试出来的，行为可能变化）。

```python
rid1 = client.start_run("做任务 A", conversation="long-task")
result1 = client.wait_run(rid1)
rid2 = client.start_run("接续做任务 B", conversation="long-task")
result2 = client.wait_run(rid2)
```

**优点**: 异步不阻塞、支持 stop/approval/SSE 事件
**缺点**: session 记录独立、需要轮询

### 模式对比表

| 维度 | 模式 A (`/v1/responses`) | 模式 B (`/api/sessions`) | 模式 C (`/v1/runs`) |
|---|---|---|---|
| Session 合并 | ✅ **自动** | ✅ **显式** | ❌ 独立记录 |
| Context 连续性 | ✅ | ✅ | ✅（需 `previous_response_id`） |
| 返回方式 | 同步（等终态） | 同步 | 异步 202 → 轮询 |
| 可见 tool 进度 | 否（等终态） | 否（等终态） | ✅（SSE / polling） |
| 可中断 | ❌ | ❌ | ✅ `stop` / `approval` |
| **每轮 token 开销** | 第1轮 ~25k, 后续 ~增量 | 第1轮 ~25k, 后续 ~增量 | 第1轮 ~25k, 后续 ~增量 |
| 代码简洁度 | 最简（仅 1 个名称） | 中间（需先建 session） | 最复杂 |

---

## 4. Token 节约策略

### 策略 1：复用 session（最大头）

| 做法 | Token 开销 | 举例 |
|---|---|---|
| 每个请求新 session | ~25k × N 轮 | 3 轮 = 75k token |
| 同 session follow-up | ~25k + 增量 × (N-1) | 3 轮 = 30k token |
| **节省** | **~55%** | 轮数越多越省 |

### 策略 2：Follow-up 只说增量

❌ **错误**（每轮复述全量任务）：
```
"你是 x1tablet。skill 内容是 ... 步骤是 ... 现在做第 2 步 ..."
```

✅ **正确**（简化为增量）：
```
"继续上一步。现在做步骤 2：git add + commit + push"
```

### 策略 3：用 `instructions` 一次设置行为

在第一轮设置 `instructions`，后续不重发：

```python
# 第一轮
client.chat("做 xxx", instructions="回报具体文件名和字节数", conversation="task")

# 后续（instructions 自动继承）
client.chat("继续做 yyy", conversation="task")
```

### 策略 4：自适应轮询间隔

别每 2 秒死等。用自适应：
- 前 10 轮：2s（工具调用快的场景）
- 10-30 轮：5s
- >30 轮：10s

见 `scripts/hermes_api_client.py` 中 `_poll()` 的实现。

### 策略 5：短任务用 `/api/sessions/{id}/chat`

如果任务只需一两轮、没有工具调用进度需要看，用同步 chat 代替异步 run。省掉轮询的 token/时间开销。

---

## 5. Python 客户端库

文件：`scripts/hermes_api_client.py`（~19KB，纯 Python 3.11+ stdlib，无外部依赖）

### 快速入门

```python
from hermes_api_client import HermesClient

client = HermesClient("http://target:8643", "your-key")

# 探活
print(client.ping())

# 推荐：/v1/responses + conversation（session 自动合并）
r = client.chat("记住: 暗号是 PINEAPPLE", conversation="demo")
print(r.text)                     # "已记下"
r = client.chat("暗号是什么？", conversation="demo")
print(r.text)                     # "PINEAPPLE"（同 session）

# 同步 Session 控制
sess = client.create_session("my-task")
print(sess.id)                    # 返回 session ID
reply = client.chat_in_session(sess.id, "说 Hello")
print(reply)

# 异步长任务 + 轮询
rid = client.start_run("长任务", conversation="long-job")
result = client.wait_run(rid, timeout_sec=300)
print(result.output)
print(result.usage)               # tokens 统计
```

### 类结构速览

| 方法 | 用途 |
|---|---|
| `ping()` → `{alive, model}` | 探活 |
| `capabilities()` → dict | 服务端功能列表 |
| `chat(input, conversation=)` → ResponseResult | **推荐多轮模式** |
| `create_session(title=)` → SessionInfo | 建 session（title 自动加前缀） |
| `chat_in_session(session_id, input)` → str | 同步 session 对话 |
| `start_run(input, conversation=)` → run_id | 异步启动作业 |
| `wait_run(run_id, timeout, title=)` → RunResult | 轮询到终态，自动补 session title |
| `get_run(run_id)` → RunResult | 查一次状态 |
| `stop_run(run_id)` → bool | 中断运行 |
| `follow_up(run_id, next_input)` → str | 前一轮完成后接续（自动补 title） |
| `run_batch(inputs, conversation)` → [str] | 同 conversation 串行跑一批（自动补 title） |
| `tell(message, conversation=)` → str | 发单条指令到远端 |
| `list_sessions(limit)` → [SessionInfo] | 列出最近 session |
| `get_session_messages(session_id, limit)` → [dict] | 读 session 消息历史 |

### session_title_prefix

所有新建 session 的 title/conversation 自动带上来源机器名前缀。方便从 `/api/sessions` 列表里一眼看出来源：

```python
# 不传参数时自动用 socket.gethostname() 生成 "[from <hostname>] "
# 在 helix 上 = "[from helix] "
client = HermesClient("http://100.66.66.249:8643", KEY)

# chat() 的 conversation 名称自动变成 "[from helix] my-project"
client.chat("hello", conversation="my-project")

# create_session() 的 title 自动变成 "[from helix] my-title"
client.create_session("my-title")
```

效果：x1tablet 的 `/api/sessions` 列表：
```
[from helix] skill-sync-2026-06-24    ← 从 helix 发起的
[from helix] my-project
dr@x1tablet 的其他本地对话             ← 本地 / 其他源发起的
```

可覆盖：
```python
# 自定义前缀
HermesClient(url, key, session_title_prefix="[my-agent] ")

# 禁用前缀
HermesClient(url, key, session_title_prefix="")
```

### 测试（仅在 x1tablet 可达时）

```bash
# 默认 target = x1tablet:8643
cd /home/dr/.hermes/skills/local/hermes-api-server/scripts/
python3 -c "
from hermes_api_client import HermesClient
c = HermesClient('http://100.66.66.249:8643', 'Kino501502666666')
print('ping:', c.ping())
print('health:', c.health())
"
```

---

## 6. 跨机 Skill 同步场景

### 标准的跨机协作流程

1. **helix 发现问题 → 总结经验 → 写 skill**
2. **通过 API 通知 x1tablet** — 用 `chat()` 方法，`conversation="skill-sync-YYYY-MM-DD"`
3. **x1tablet hermes 收到指令** — 用 terminal/file 工具做本地操作
4. **轮询结果**

```python
client = HermesClient("http://100.66.66.249:8643", KEY)
client.tell(f"""把以下经验吸收到 x1tablet 的 sway 技能里：
（skill 内容...）

要求：吸收，不是复制。保留你自己 frontmatter，改写叙事风格为 reference。""")
```

### 重要原则（来自 dr 的教训）

| 教训 | 说明 |
|---|---|
| **各管各的** | 两端 skill 独立，不要求 byte-for-byte 一致 |
| **不盖占位** | 先 `cat` 看远端目录里有没有已存在的内容，合并不覆盖 |
| **不跨权** | 让远端 hermes 自己操作，helix 不要 SSH 去改远端文件 |
| **不回滚** | 出错就发新指令修正，不在远端 local git 做 force push |

---

## 7. 实战 Debug 流程

当 API 端点连不上时，不要盲信 `.env` 里的端口：

```bash
# 1. TCP 端口探测
for p in 8642 8643 8787 5000; do
  timeout 3 bash -c "</dev/tcp/100.66.66.249/$p" 2>&1 && echo "$p OPEN" || echo "$p closed"
done

# 2. SSH 确认实际监听进程（排除端口被别人占用）
ssh x1tablet 'ss -tlnp | grep 8643'

# 3. 看 hermes-gateway 日志（确认是否 key 校验失败没启动）
ssh x1tablet 'journalctl --user --since "10 min ago" | grep -iE "api_server|placeholder"'
```

典型问题诊断表：

| 现象 | 可能原因 | 验证 |
|---|---|---|
| 8643 端口拒绝 | key < 16 chars → 服务没启动 | `journalctl` 查 "Refusing to start" |
| 5000 返回 401 | 端口被 code-server 占了 | `ss -tlnp` 看进程名 |
| `/v1/runs` 返回 400 | 没传 `input` 字段 | 检查 body |
| session 不合并 | 用了 `/v1/runs` 不是 `/v1/responses` | 检查端点 |
| input_tokens 离谱 | 忘了设 `conversation`，每次都新 session | 看 `/api/sessions` 列表 |

---

## 8. 安全注意事项

- **API server 给完整 terminal 访问权** — key 必须强，生产用 `openssl rand -hex 32`
- 默认 **不开启 CORS**，浏览器直连才需 `API_SERVER_CORS_ORIGINS`
- `API_SERVER_HOST=0.0.0.0` 暴露在网络上 — tailnet 场景：绑 100.64.0.0/10 范围
- Tailscale: 仅放行 `tailscale0` / `tailscale1` 接口，不放 docker bridge

---

## 文件清单

| 文件 | 用途 |
|---|---|
| `SKILL.md` | 本文件 - 完整参考手册 |
| `scripts/hermes_api_client.py` | Python 客户端库（stdlib only, 19347 bytes） |
| `references/api-server.md` | Hermes 官方文档原始版（20303 bytes, v0.16.0） |

### 准备 MCP

这个 skill 的结构（SKILL.md + 自包含 Python 脚本 + reference docs）已经设计成 MCP-ready。Python 脚本可以注册为 MCP tool 的 backend——每个 `HermesClient` 方法对应一个 MCP tool。
