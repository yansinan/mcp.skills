# 部署拓扑与测试模式

data: 2026-06 Hermes webui session — 验证 minimax 切换到 `mode: responses` 后是否正常

## 1. 部署拓扑：两种 URL 形式指向同一 backend

serverhome 上的 LiteLLM 同一进程同时暴露两种 URL：

```
http://serverhome:4000/v1/...            ← 直打端口
http://serverhome/litellm/hermes/v1/...  ← 走 nginx/caddy 反代（不写端口）
```

两个 URL 都能 work，三种端点（`/v1/models`、`/v1/chat/completions`、`/v1/responses`）全部返回 200。

**用途区别**：
- `serverhome:4000` — 直连，最简单，调试时方便
- `serverhome/litellm/hermes/` — 路径式，能走反向代理（更接近"对外发布"的形式），Hermes 配置里更自然

## 2. ⚠️ 测试原则：必须跨机测，不要在 server 上跑 localhost

**用户明确要求**（2026-06 session）：

> "你不应该跑 localhost:4000,是 serverhome:4000"

**理由**：测试的目的是验证 Hermes（x1tablet 端）能不能调到 serverhome 上的 LiteLLM。如果 SSH 进 serverhome 然后跑 `curl localhost:4000`，等于在 server 上 curl 它自己，根本没测网络路径。必须从 client 端（x1tablet）发起跨机请求。

**反模式**（不要这样做）：

```bash
# ❌ 错 — 从 server 内部 curl 它自己
ssh dr@serverhome 'curl http://localhost:4000/v1/responses ...'
```

**正确模式**：

```bash
# ✅ 对 — 从 x1tablet 端跨机请求
KEY=$(ssh dr@serverhome 'grep LITELLM_MASTER_KEY ~/workspace/liteLLM.docker/.env | cut -d= -f2 | tr -d "\"')
curl -X POST http://serverhome:4000/v1/responses \
  -H "Authorization: Bearer ***    -H "Content-Type: application/json" \
  -d '{"model": "minimax", "input": "...", "max_output_tokens": 500}'
```

**或者从 serverhome 拿到 key 后用文件传，避免 shell 嵌套引号爆炸**：

```bash
KEY=$(ssh dr@serverhome 'grep LITELLM_MASTER_KEY ~/workspace/liteLLM.docker/.env | cut -d= -f2 | tr -d "\""')
curl -X POST http://serverhome:4000/v1/responses \
  -H "Authorization: Bearer $KEY" ...
```

## 3. 真实测试结果（minimax + mode: responses）

### 从 x1tablet 跨机测 `http://serverhome:4000/v1/responses`

| 检查项 | 结果 |
|---|---|
| HTTP 状态 | ✅ 200 OK |
| 响应对象类型 | ✅ `object: "response"`（标准 Responses API 对象） |
| 输出结构 | ✅ `output[]` 数组包含 typed items（`reasoning` + `message`） |
| 状态 | ✅ `status: "completed"`（max_output_tokens=500 足够） |
| Token 用量 | input 183, output 62, **cached 114**（cache 命中） |

### 实际模型回复

```
reasoning: 用户让我用一句话告诉今天天气怎么样。我需要先查询一下当前日期和天气信息。
           不过我并不知道用户所在的位置，也无法直接获取实时天气数据。
message: 抱歉，我无法直接获取您所在地的实时天气信息。您可以告诉我所在城市，
         我尝试为您查询当前天气状况。
```

**观察**：
- `max_output_tokens=100` 时 status=`incomplete`（reasoning 模型吃光 token）
- `max_output_tokens=500` 时 status=`completed`（推荐 500+ 给 reasoning 模型）
- 路径式 `serverhome/litellm/hermes/v1/responses` 同样 200 OK

## 4. `mode: responses` 实际激活条件（分层模型 + 关键发现）

**两种调用路径，两种激活状态**：

| 调用来源 | 客户端方法 | 实际路径 | `mode: responses` 是否生效 |
|---|---|---|---|
| Hermes 主对话 agent | `client.chat.completions.create(...)` | `/v1/chat/completions` | ❌ 不生效（直走 chat handler） |
| Hermes 辅助功能（vision / web_extract / session_search） | `client.chat.completions.create(...)` → **被 adapter 拦截** | **`/v1/responses`** | ✅ **生效**（adapter 内部转译） |

LiteLLM 端的配置（**auxiliary 路径已生效**）：

```yaml
- model_name: minimax
  model_info:
    mode: responses           # ← auxiliary 路径用上了
  litellm_params:
    model: minimax/minimax-m3
    api_base: os.environ/MINIMAX_API_BASE
    api_key: os.environ/MINIMAX_API_KEY
```

Hermes 端（**已生效的辅助层 adapter，尚未完成的主对话改造**）：

```yaml
# ~/.hermes/config.yaml
auxiliary:
  vision:         { model: minimax, base_url: http://serverhome/litellm/hermes }
  web_extract:    { model: minimax, base_url: http://serverhome/litellm/hermes }
  session_search: { model: minimax, base_url: http://serverhome/litellm/hermes }
default: deepseek-v4-flash   # 主对话，仍走 chat completions
```

### 关键发现：`_CodexCompletionsAdapter`（2026-06 后续 session）

`agent/auxiliary_client.py` 内部有一个 adapter shim（line 634-660, 640-845），**业务代码写的是**：

```python
client.chat.completions.create(model=..., messages=[...])
```

**但 adapter 实际把它转成**：

```python
self._client.responses.create(**stream_kwargs)   # line 844
```

adapter 注释（line 635-637）原文：

> "All auxiliary consumers call client.chat.completions.create(**kwargs) and read response.choices[0].message.content. This adapter translates those calls to the Codex Responses streaming API."

这意味着：

- **辅助功能已经在用 `/v1/responses`**（之前认为"未完全激活"是错的）
- **`mode: responses` 配置对 minimax 模型已经发挥作用**（之前 200 OK + reasoning+message 的测试结果就是证据）
- 业务代码不需要改就能用上 responses 的能力（adapter 替我们做了）
- **但主对话 agent 走的是另一条 transport 路径**（`agent/transports/codex.py` 或 `agent/run_agent.py`），那边没有这个 adapter，仍然打 `/v1/chat/completions`

要主对话也走 responses 路径，需要改主对话 transport 层的源码（参考 `agent/codex_responses_adapter.py` 的 `_chat_messages_to_responses_input` 函数，auxiliary 已经在用了）。这是一个独立的、非平凡的代码改造工作。

## 5. URL 形式选择建议

| 场景 | 推荐 base_url |
|---|---|
| 调试 / 本地测试 | `http://serverhome:4000`（直连，最简单） |
| 正式配置（Hermes / 其他 client） | `http://serverhome/litellm/hermes`（路径式，反代后更干净） |
| 跨 Tailscale 子网访问 | `http://serverhome:4000`（端口直连，避免 DNS 解析路径） |

## 6. 容易踩的坑

- **shell 嵌套引号**：在 ssh 内嵌 curl 的双引号 + json body 双引号，bash 解析会爆。用 `execute_code` (Python) 跑子进程最稳。
- **minimax reasoning 模型 token 消耗大**：`max_output_tokens=100` 不够，至少 500+。
- **跨机测时不要在 server 上 curl localhost**：根本测不到网络。
- **改 base_url 后两边都要改**：LiteLLM 反代路径要对应，Hermes config 也要对应。
