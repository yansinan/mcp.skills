---
name: litellm-mcp-config
title: LiteLLM MCP 服务配置
description: 基于官方文档，在 LiteLLM Proxy 中配置自建 MCP 服务（HTTP/SSE/STDIO），包括认证、权限管理、REST API 调用和排错
author: hermes
source: https://docs.litellm.ai/docs/mcp
tags: [litellm, mcp, llm, gateway, proxy, practical-case]
---

# LiteLLM MCP 服务配置

## 概述

LiteLLM Proxy 提供 **MCP Gateway** 功能，可将多个 MCP 服务器统一注册到 LiteLLM 中，作为统一的 endpoint 对外暴露，实现：

- **统一 endpoint**：所有 MCP 工具通过 LiteLLM 单个端点访问
- **按 Key/Team 控制权限**：精细控制哪些用户/团队可以访问哪些 MCP 工具
- **认证代理**：支持 API Key、Bearer Token、OAuth2、AWS SigV4 等多种认证方式
- **成本追踪**：记录每次 MCP 工具调用的 token 消耗

流量路径：Client → LiteLLM Proxy → MCP Server

## 重要警告

### ⚠️ 如果当前会话正通过此 LiteLLM 实例提供模型

当您的 Agent（Hermes、Cursor、Claude Code 等）正通过此 LiteLLM 实例获取 LLM 推理时：
- **绝对不要重启 LiteLLM 容器/进程** — 重启会中断正在运行的会话，导致当前工作丢失
- `mcp_servers` 段在 config.yaml 中的修改需要重启才生效，但重启会使当前 Agent 断连
- 安全做法：做所有能做的文件修改（config.yaml、docker-compose.yml、脚本），然后告知用户手动重启的步骤和时机

### ⚠️ Docker 部署的卷挂载

LiteLLM 在 Docker 中运行时，STDIO 类型的 MCP 服务器脚本必须在容器内可访问。需要在 `docker-compose.yml` 中挂载脚本目录：

```yaml
volumes:
  - ./config.yaml:/app/config.yaml
  - ./mcps:/mcps   # ← 确保 STDIO 脚本路径映射到容器内
```

容器内的 `command`/`args` 路径使用 `/mcps/...`（挂载点内的路径）。

## 配置提交清单 ⚠️

每次向用户汇报 MCP 服务器配置结果时，**必须同时回答以下三个问题**，缺一不可：

| # | 问题 | 答案示例 |
|---|------|----------|
| 1 | **配置文件怎么写的？** | 给出 config.yaml 的 mcp_servers 段实际内容 |
| 2 | **访问路径是什么？** | 列出所有可用方式：MCP JSON-RPC 端点、MCP REST API、Responses API、标准 curl 示例 |
| 3 | **鉴权怎么做？** | 给出 header 格式（`x-litellm-api-key` / `Authorization`）、是否需要 object_permission、是否用了 `allow_all_keys` |
| 4 | **验证步骤是什么？** | 给出重启后的 curl 验证命令（list servers → list tools → call tool） |

**常见错误**：只说了"我在 config.yaml 加了 mcp_servers"，没说访问路径，也没说鉴权方式 → 用户追问"这么简单吗？访问路径是什么？鉴权怎么做？" → 说明遗漏了强制三步。

## 在 config.yaml 中添加 MCP 服务器

在 LiteLLM Proxy 的 `config.yaml` 中使用 `mcp_servers` 字段注册 MCP 服务。

### 基本结构

```yaml
mcp_servers:
  my_server:
    url: "https://my-mcp-server.com/mcp"
    transport: "http"  # http | sse | stdio
    description: "My custom MCP server"
```

### HTTP Streamable Server（推荐）

```yaml
mcp_servers:
  deepwiki_mcp:
    url: "https://mcp.deepwiki.com/mcp"
```

### SSE Server

```yaml
mcp_servers:
  zapier_mcp:
    url: "https://actions.zapier.com/mcp/sk-akxxxxx/sse"
```

### STDIO Server（本地进程）

```yaml
mcp_servers:
  circleci_mcp:
    transport: "stdio"
    command: "npx"
    args: ["-y", "@circleci/mcp-server-circleci"]
    env:
      CIRCLECI_TOKEN: "your-circleci-token"
      CIRCLECI_BASE_URL: "https://circleci.com"

  strands_mcp:
    transport: "stdio"
    command: "uvx"
    args: ["strands-agents-mcp-server"]
    env:
      FASTMCP_LOG_LEVEL: "INFO"

  # 注册自建 STDIO MCP 服务器（脚本位于子模块仓库内）
  # ⚠️ server name 不能含连字符（-），用 camelCase
  mcpSway:
    transport: stdio
    command: python3
    args: [/mcps/mcpSway/mcpSway-server.py]
    description: mcpSway 技能库 — Sway 桌面环境配置技能集合
```

**格式说明**：mcp_servers 使用 dict 格式（`server_name:` 直接接配置），非列表格式（`- server_name:`）。LiteLLM 官方文档的 STDIO 示例均使用 dict 格式，列表格式会导致配置解析失败。

**自建 STDIO 服务器**：参见 `references/custom-stdio-mcp-server-pattern.md` — 包含 MCP JSON-RPC 协议实现骨架、主循环模板、文件传输方案等。

**Skills → MCP Gateway 全流程**：参见 `references/hermes-skills-to-mcp-pipeline.md` — 从本地技能迁移到 mcpSway 仓库、注册 LiteLLM STDIO、Hermes HTTP 客户端的完整端到端模式。

**Hermes 客户端接入方式**：参见 `references/hermes-mcp-client-patterns.md` — Hermes external_dirs / mcp_servers stdio / mcp_servers HTTP / 直接文件读取策略决策树。

**STDIO 空工具排错**：参见 `references/stdio-empty-tools-debug.md` — `tools/list` 静默返回空时的系统化调试方法（目录深度不匹配、卷挂载遗漏等）。

**从 template.mcp 创建新 MCP 服务**：参见 `references/template-mcp-new-service.md` — 使用 `yansinan/template.mcp` 标准化模板创建新 MCP 服务仓库的完整工作流（GitHub 创建 → 克隆 → 模板复制 → 定制 → 验证 → LiteLLM 注册）。

**mcp.skills 子模块技能库**：参见 `references/mcp-skills-submodule-workflow.md` — 将本地成熟技能分类组织为独立 git 仓库，作为 MCP 服务仓库的子模块，实现 serverHome LiteLLM 定期拉取同步的模式。

### 自建 HTTP MCP 服务示例

假设你在本地起了一个 MCP 服务（如 Python 的 `mcp` 库或 Node.js 的 `@modelcontextprotocol/server`），暴露在 `http://localhost:9000/sse` 或 `http://localhost:9000/mcp`：

```yaml
mcp_servers:
  my_local_mcp:
    url: "http://localhost:9000/mcp"
    # 如果是 SSE 协议：
    # url: "http://localhost:9000/sse"
```

## 认证配置

### API Key 认证

```yaml
mcp_servers:
  api_key_example:
    url: "https://my-mcp-server.com/mcp"
    auth_type: "api_key"
    auth_value: "abc123"  # → headers={"X-API-Key": "abc123"}
```

### Bearer Token

```yaml
mcp_servers:
  bearer_example:
    url: "https://my-mcp-server.com/mcp"
    auth_type: "bearer_token"
    auth_value: "abc123"  # → headers={"Authorization": "Bearer abc123"}
```

### Basic Auth

```yaml
mcp_servers:
  basic_example:
    url: "https://my-mcp-server.com/mcp"
    auth_type: "basic"
    auth_value: "dXNlcjpwYXNz"  # base64("user:pass")
```

### 自定义 Authorization Header

```yaml
mcp_servers:
  custom_auth_example:
    url: "https://my-mcp-server.com/mcp"
    auth_type: "authorization"
    auth_value: "Token example123"  # → headers={"Authorization": "Token example123"}
```

### OAuth 2.0 Client Credentials

```yaml
mcp_servers:
  oauth2_example:
    url: "https://my-mcp-server.com/mcp"
    auth_type: "oauth2"
    authorization_url: "https://my-mcp-server.com/oauth/authorize"  # 可选覆盖
    token_url: "https://my-mcp-server.com/oauth/token"              # 可选覆盖
    registration_url: "https://my-mcp-server.com/oauth/register"    # 可选覆盖
    client_id: os.environ/OAUTH_CLIENT_ID
    client_secret: os.environ/OAUTH_CLIENT_SECRET
    scopes: ["tool.read", "tool.write"]  # 可选
```

### AWS SigV4（Bedrock AgentCore）

```yaml
mcp_servers:
  agentcore_mcp:
    url: "https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/.../invocations"
    transport: "http"
    auth_type: "aws_sigv4"
    aws_role_name: os.environ/AWS_ROLE_ARN           # 可选 — IAM role 切换
    aws_access_key_id: os.environ/AWS_ACCESS_KEY_ID   # 可选 — 不设则用 IAM role
    aws_secret_access_key: os.environ/AWS_SECRET_ACCESS_KEY
    aws_region_name: us-east-1
    aws_service_name: bedrock-agentcore
```

### 静态 Headers

直接在配置中设置固定的请求头：

```yaml
mcp_servers:
  my_mcp_server:
    url: "https://my-mcp-server.com/mcp"
    static_headers:
      X-API-Key: "abc123"
      X-Custom-Header: "some-value"
```

### 转发客户端请求头到 STDIO 环境变量

对于 STDIO 类型的 MCP 服务器，可以配置用户请求头注入为环境变量：

```yaml
mcp_servers:
  my_stdio_mcp:
    transport: "stdio"
    command: "my-mcp-server"
    args: []
    env:
      LITELLM_FORWARDED_HEADER_MAPPING:
        "Authorization": "AUTH_TOKEN"
        "X-User-Id": "USER_ID"
```

此时客户端请求的 `Authorization` header 将作为 `AUTH_TOKEN` 环境变量传给 STDIO 进程。

### 服务器变量（Server Variables）

服务器变量允许在不同环境下复用同一配置模版，通过 `variables` 字段声明；LiteLLM UI 会为用户展示变量表单以填充实际值。

```yaml
mcp_servers:
  cloudflare_mcp:
    url: "https://api.cloudflare.com/client/v4/mcp"
    variables:
      cloudflare_api_token:
        description: "Your Cloudflare API token"
        required: true
        default: ""
      account_id:
        description: "Cloudflare account ID to operate on"
        required: true
        default: ""
    auth_type: bearer_token
```

## MCP 别名（Aliases）

配置别名便于工具名更短也更可读。在 `litellm_settings` 中设置：

```yaml
litellm_settings:
  mcp_aliases:
    "github": "github_mcp_server"
    "zapier": "zapier_mcp_server"
    "deepwiki": "deepwiki_mcp_server"
```

配置后工具名前缀从完整 server_name 变为别名，如 `github-search_issues` 而非 `github_mcp_server-search_issues`。

## 使用 MCP 工具

### 方法 1：通过 Responses API（推荐用于 LLM 驱动）

```python
import openai

client = openai.OpenAI(
    api_key="sk-1234",
    base_url="http://localhost:4000"  # LiteLLM Proxy URL
)

response = client.responses.create(
    model="gpt-4o",
    input=[
        {"role": "user", "content": "give me TLDR of what BerriAI/litellm repo is about"}
    ],
    tools=[
        {
            "type": "mcp",
            "server_label": "litellm",
            "server_url": "litellm_proxy/mcp",
            "require_approval": "never",
            "allowed_tools": ["GitMCP-fetch_litellm_documentation"]
        }
    ],
    stream=True,
    tool_choice="required"
)
```

当 `server_url="litellm_proxy"` 时，LiteLLM 自动将非 MCP 原生的 LLM provider 桥接到 MCP 工具。

### 方法 2：通过 MCP REST API（直接调用，无需 LLM）

#### 列出 MCP 服务器

```bash
curl -s http://localhost:4000/v1/mcp/server \
  -H "Authorization: Bearer *** | jq .
```

#### 列出工具

```bash
# 所有服务器
curl -s http://localhost:4000/mcp-rest/tools/list \
  -H "Authorization: Bearer *** | jq .

# 单台服务器（推荐）
curl -s "http://localhost:4000/mcp-rest/tools/list?server_id=my_mcp" \
  -H "Authorization: Bearer *** | jq .
```

#### 调用工具

```bash
curl -s -X POST http://localhost:4000/mcp-rest/tools/call \
  -H "Authorization: Bearer *** \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "my_mcp",
    "name": "my_mcp-tool_name",
    "arguments": {"key": "value"}
  }' | jq .
```

工具名格式：`{server_prefix}-{upstream_tool_name}`，默认分隔符为 `-`。也可用 MCP 原生的工具名 + `server_id` 字段：

```bash
curl -s -X POST http://localhost:4000/mcp-rest/tools/call \
  -H "Authorization: Bearer *** \
  -d '{
    "server_id": "places_api",
    "name": "getPlaces",
    "arguments": {"query": "coffee"}
  }'
```

**注意**：`arguments` 必须传 JSON 对象，传 `null` 会报 500 错误。没有参数时用 `{}`。

### 方法 3：通过 /chat/completions

```python
import openai

client = openai.OpenAI(
    api_key="sk-1234",
    base_url="http://localhost:4000"
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "What's the weather in Tokyo?"}],
    tools=[
        {
            "type": "mcp",
            "server_label": "weather",
            "server_url": "litellm_proxy/mcp",
            "require_approval": "never"  # 自动执行，无需用户确认
        }
    ]
)
```

### 方法 4：在 Cursor IDE 中使用

在 Cursor 的 MCP 配置中添加：

```json
{
  "mcpServers": {
    "LiteLLM": {
      "url": "litellm_proxy",
      "headers": {
        "x-litellm-api-key": "Bearer $LITELLM_API_KEY"
      }
    }
  }
}
```

`server_url="litellm_proxy"` 时，LiteLLM 自动桥接非 MCP provider 到 MCP 工具：
- **工具发现**：LiteLLM 获取 MCP 工具并转为 OpenAI 兼容格式
- **LLM 调用**：工具发给 LLM，LLM 选择哪些工具调用
- **工具执行**：LiteLLM 自动解析参数、路由到 MCP 服务器、执行并取回结果
- **响应整合**：工具结果回传给 LLM 生成最终响应

## 权限管理

### 权限层级（从最宽松到最严格）

1. **Public / allow_all_keys**：所有有 API key 的调用者都可访问
2. **Organization**：Organization 级权限作为最高上限
3. **Team**：Team 级别权限
4. **End-User**：终端用户级别权限
5. **Key**：单 API Key 级别权限

最终权限 = **五层交集**（最严格的限制取胜），Organization 作为天花板。

### 在 Server 级别限制工具白/黑名单

```yaml
mcp_servers:
  github_mcp:
    url: "https://api.githubcopilot.com/mcp"
    auth_type: "bearer_token"
    auth_value: "ghp_example_token"
    allowed_tools: ["list_repositories", "create_issue", "search_code"]
    # disallowed_tools: ["delete_repository"]  # 黑名单模式
```

### 公开 MCP 服务（allow_all_keys）

默认所有已认证的调用者可以调用所有 MCP 工具。要给某个 MCP 服务器跳过权限检查：

```yaml
mcp_servers:
  web_search:
    url: "https://mcp.exa.ai/mcp"
    allow_all_keys: true  # 所有有效 key 均可访问，无需在 object_permission 中显式声明
```

### 按 Key/Team 控制服务器访问

#### 给 Key 授权 MCP 服务器

```bash
curl -X POST "http://localhost:4000/key/generate" \
  -H "Authorization: Bearer *** \
  -H "Content-Type: application/json" \
  -d '{
    "object_permission": {
      "mcp_servers": ["github_mcp", "slack_mcp"]
    }
  }'
```

#### 给 Team 授权

```bash
curl -X POST "http://localhost:4000/team/new" \
  -H "Authorization: Bearer *** \
  -H "Content-Type: application/json" \
  -d '{
    "team_alias": "engineering",
    "object_permission": {
      "mcp_servers": ["github_mcp", "deepwiki_mcp"]
    }
  }'
```

### 工具级权限（mcp_tool_permissions）

在 Server 注册的 `allowed_tools` 之后，还可通过 `mcp_tool_permissions` 进一步按实体细化。

```bash
# 给 Engineering Key — 完整 GitHub 权限
curl -X POST "http://localhost:4000/key/generate" \
  -H "Authorization: Bearer *** \
  -d '{
    "object_permission": {
      "mcp_servers": ["github_mcp"],
      "mcp_tool_permissions": {
        "github_mcp": ["list_repositories", "create_issue", "search_code"]
      }
    }
  }'

# 给 Sales Key — 同一服务器只读
curl -X POST "http://localhost:4000/key/generate" \
  -d '{
    "object_permission": {
      "mcp_servers": ["github_mcp"],
      "mcp_tool_permissions": {
        "github_mcp": ["search_code", "close_issue"]
      }
    }
  }'
```

### 参数级权限控制

可以精确控制 MCP 工具参数中哪些字段允许/禁止：

```yaml
mcp_servers:
  github_mcp:
    url: "https://api.githubcopilot.com/mcp"
    auth_type: "bearer_token"
    auth_value: "ghp_token"
    allowed_tool_parameters:  # 白名单模式
      "github_mcp-create_issue": ["owner", "repo", "title", "body", "labels", "assignees"]
    # disallowed_tool_parameters: ...  # 黑名单模式
```

### 每 MCP 服务器速率限制（mcp_rpm_limit）

```bash
curl -X POST "http://localhost:4000/key/generate" \
  -H "Authorization: Bearer *** \
  -d '{
    "mcp_rpm_limit": {"github": 100, "slack": 200},
    "object_permission": {"mcp_servers": ["github", "slack"]}
  }'
```

超过限制后该服务器返回 `429 Too Many Requests`，不影响其他服务器。

## 从 OpenAPI 生成 MCP 服务器

可以通过 OpenAPI/Swagger 规范自动生成 MCP 服务器配置：

```bash
curl -X POST "http://localhost:4000/mcp/openapi/from_url" \
  -H "Authorization: Bearer *** \
  -H "Content-Type: application/json" \
  -d '{
    "openapi_url": "https://petstore.swagger.io/v2/swagger.json",
    "server_name": "petstore"
  }'
```

## 带客户端凭证使用 MCP

### 新的推荐方式：服务器专用 Auth Header

```python
from fastmcp import Client
import asyncio

config = {
    "mcpServers": {
        "mcp_group": {
            "url": "http://localhost:4000/mcp/",
            "headers": {
                "x-mcp-servers": "dev_group",
                "x-litellm-api-key": "Bearer sk-1234",
                "x-mcp-github-authorization": "Bearer gho_token",
                "x-mcp-zapier-x-api-key": "sk-xxxxxxxxx",
                "custom_key": "value"
            }
        }
    }
}
```

### 传统方式：按 URL 路径访问

```python
config = {
    "mcpServers": {
        "github": {
            "url": "http://localhost:4000/github_mcp/mcp",
            "headers": {
                "x-litellm-api-key": "Bearer sk-1234",
                "Authorization": "Bearer gho_token"
            }
        }
    }
}
```

### 客户追踪

```python
config = {
    "mcpServers": {
        "github": {
            "url": "http://localhost:4000/github_mcp/mcp",
            "headers": {
                "x-litellm-api-key": "Bearer sk-1234",
                "x-litellm-end-user-id": "customer_123",
                "Authorization": "Bearer gho_token"
            }
        }
    }
}
```

## 部署拓扑

### 方案 A：单 Gateway（推荐）

一个 LiteLLM 实例处理 LLM 路由、MCP 工具调用和 A2A Agent 调用。

```yaml
general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  store_model_in_db: true
  mcp_internal_ip_ranges:
    - "10.0.0.0/8"
    - "172.16.0.0/12"
    - "192.168.0.0/16"
    - "100.64.0.0/10"   # VPN/Tailscale 范围

mcp_servers:
  - server_name: internal-db
    url: "http://db-mcp.internal:8000/mcp"
    transport: http
    available_on_public_internet: false  # 仅内部访问
  - server_name: web-search
    url: "https://mcp.exa.ai/mcp"
    transport: http
    available_on_public_internet: true   # 对 ChatGPT/Claude Desktop 可见
```

### 方案 B：分离 LLM Gateway 和 MCP Gateway

LLM Gateway 放在内网无公网端口，MCP Gateway 可暴露到公网。LLM 凭据始终不会从 MCP Gateway 泄漏。

## 启用 MCP Registry

让外部 MCP 客户端（Claude Desktop、IDE）自动发现 LiteLLM 托管的 MCP 服务：

```yaml
general_settings:
  enable_mcp_registry: true
```

启动后 `GET /v1/mcp/registry.json` 返回遵循 MCP Registry 规范的发现清单。

Claude Desktop 配置：

```json
{
  "mcpServers": {
    "litellm": {
      "url": "https://your-litellm.example.com/mcp",
      "headers": {
        "Authorization": "Bearer sk-..."
      }
    }
  }
}
```

## ⚠️ 关键陷阱

### 1. STDIO 服务器必须实现 initialize 握手

LiteLLM 的 MCP 客户端（基于 mcp Python SDK）在调用 tools/list 之前必先发送 initialize 请求。如果 STDIO 服务器不处理 initialize，SDK 会报 ValidationError：

```
MCP client list_tools failed - Error Type: ValidationError
3 validation errors for InitializeResult
protocolVersion: Field required
capabilities: Field required
serverInfo: Field required
```

**修复**：主循环中必须处理 initialize 方法和 notifications/initialized notification。参见 references/custom-stdio-mcp-server-pattern.md 中的完整骨架。

### 2. MCP 端点访问需要 Accept Header

LiteLLM 的 Streamable HTTP 原生 MCP 端点（/{server_name}/mcp）要求客户端同时接受两个 Content-Type：

```bash
curl -X POST http://litellm:4000/mcpSway/mcp \
  -H "Accept: application/json, text/event-stream"
```

缺少此 header 会返回 Not Acceptable 错误。响应格式为 SSE（Server-Sent Events）：
```
event: message
data: {"jsonrpc":"2.0","id":1,"result":{...}}
```

### 3. REST API /mcp-rest/tools/call 对 STDIO 的限制

GET /mcp-rest/tools/list 对 STDIO 服务器工作正常，但 POST /mcp-rest/tools/call 可能返回 Tool config not found。推荐使用原生 MCP 端点 POST /{server_name}/mcp 进行工具调用。

### 4. 工具名自动加 server 前缀

LiteLLM 在原生 MCP 端点下会自动为工具名添加 server 前缀：
- 注册名：waybar-config
- 暴露名：mcpSway-waybar-config

### 5. STDIO 服务器的 tools/list 静默返回空

自建 STDIO MCP 服务器的 `tools/list` 返回空工具列表时，**无 stdout 错误也无 stderr 输出**（静默失败）。常见原因：

**目录深度不匹配**：`load_entries` 扫描 `skills/` 下直接子目录的 `SKILL.md`，但仓库结构用了分类子目录（例如 `mcp.skills` 的 `back-end/<name>/SKILL.md` 或 `hermes-chores/<name>/SKILL.md`，多了一层分类目录）。

两种常见情况：
- **旧模式**：`skills/local/<name>/SKILL.md`（平铺，`local/` 是虚拟分类）
- **新模式**（mcp.skills 子模块）：`skills/back-end/<name>/SKILL.md` 或 `skills/hermes-chores/<name>/SKILL.md`（真实分类目录）

```python
# ❌ 只扫一级：skills/<name>/SKILL.md — 找不到任何技能
for sub in sorted(skills_dir.iterdir()):
    skill_md = sub / "SKILL.md"

# ✅ 方案 A（推荐 — 容许多层目录）：递归扫描
def _scan(dir_path):
    for sub in sorted(dir_path.iterdir()):
        if not sub.is_dir():
            continue
        if (sub / "SKILL.md").is_file():
            entries.append(sub.name, ...)
        else:
            _scan(sub)   # 继续下钻
_scan(skills_dir)

# ✅ 方案 B（替代 — 保持原始 load_skills 简单）：展平目录
# 如果 skills/ 下多了一层级（如 skills/local/<name>/），可以直接移上来：
#   mv skills/local/* skills/  &&  rmdir skills/local
# 恢复原始 load_skills 的一级扫描即可，无需改代码。
# 适用场景：多出的层级是分类前缀（local/、back-end/ 等）而非真正的嵌套结构。

**选择策略**：递归扫描（方案 A）适用于技能库可能持续增长层级的场景；展平目录（方案 B）适用于多余层级是历史遗留且无分类价值时，优点是保持脚本简单。

⚠️ **注意**：多余的 `local/` 层可能由 agent 操作失误产生（例如将 Hermes 的 `skills/local/` 目录结构错误地迁移到了 MCP 仓库）。遇到 `tools/list` 空返回且 `skills/` 下有分类子目录时，先确认这个分层是否有实际分类意义，再选方案 A 或 B。
```

**诊断方法**：用 echo pipe 独立测试脚本（见 `references/stdio-empty-tools-debug.md`），不必依赖 LiteLLM 重启。先确认脚本本身的 `tools/list` 能返回数据，再排查 LiteLLM 侧问题。

```bash
# 快速确定实际 SKILL.md 深度
find /path/to/skills -name SKILL.md -type f | sed 's|[^/]*/|  |g' | sort -u

# 第一列缩进数就是深度，与脚本中的扫描逻辑对比即可定位问题
```

**根源**：stdout 输出了合法的 JSON-RPC 空数组结果（`{"tools": []}`），所以没有错误日志。唯一线索是 `find` 检查实际 SKILL.md 的层级与脚本扫描深度是否匹配。

### 6. 脚本路径 vs SWAY_DIR/HERE 路径依赖

当 STDIO 脚本从一个位置迁移到另一个位置时，`SWAY_DIR` 的路径计算必须随之更新，否则 `tools/list` 会静默返回空。

**典型场景**：脚本从 `mcps/mcpSway-server.py`（mcps/ 根目录）移到 `mcps/mcpSway/mcpSway-server.py`（子模块仓库内）。

```python
# ❌ 脚本在 mcps/ 根目录时正确，移到子模块后错误
HERE = Path(__file__).resolve().parent     # → /mcps/mcpSway/（变了！）
SWAY_DIR = HERE / "mcpSway"                # → /mcps/mcpSway/mcpSway/ ❌ 不存在

# ✅ 脚本在子模块内时
HERE = Path(__file__).resolve().parent     # → /mcps/mcpSway/
SWAY_DIR = HERE                            # → /mcps/mcpSway/ ✅ skills 在同级
```

**规则**：`SWAY_DIR` 始终指向 skills/ 的 **父目录**。脚本每深入一层目录，`SWAY_DIR` 就减少一次 `/"subdir"` 拼接。确认配置中的 `args` 路径与实际文件位置一致后，再检查脚本内的 `SWAY_DIR` 计算。

**不要创建 standalone 副本**：config.yaml 应直接引用子模块仓库内的脚本（如 `/mcps/mcpSway/mcpSway-server.py`），而不是在 mcps/ 根目录创建 standalone 副本。副本会过时，也让路径关系难以维护——当子模块脚本更新了 `SWAY_DIR` 或 `load_skills`，副本永远是旧版本。

## 排错

### 一键诊断

```bash
curl -si -X POST http://localhost:4000/{your_mcp_server}/mcp \
  -H "Content-Type: application/json" \
  -H "x-litellm-api-key: Bearer sk-YOUR_KEY" \
  -H "x-litellm-mcp-debug: true" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  2>&1 | grep -i "x-mcp-debug"
```

返回的诊断 header 示例：

```
x-mcp-debug-inbound-auth: x-litellm-api-key=Bearer****1234
x-mcp-debug-oauth2-token: Bearer****ef01
x-mcp-debug-auth-resolution: oauth2-passthrough
x-mcp-debug-outbound-url: https://mcp.atlassian.com/v1/mcp
x-mcp-debug-server-auth-type: oauth2
```

如果 `x-mcp-debug-oauth2-token` 显示 `SAME_AS_LITELLM_KEY`，说明 LiteLLM API key 泄漏到了 MCP 服务器，需要检查 OAuth 配置。

### 常见错误

| 错误 | 原因 | 修复 |
|------|------|------|
| `400 missing_parameter` | 缺少 `server_id` | 调用 tools/call 时传 `server_id` |
| `500` | `arguments: null` | 用 `arguments: {}` 或省略字段 |
| `403 tool_server_mismatch` | 工具名和 server_id 不匹配 | 确认工具属于正确的服务器 |
| `404 server_not_found` | server_id 无效 | 先 `GET /v1/mcp/server` 确认 ID |
| `429 Too Many Requests` | 超出该 MCP 服务器的速率限制 | 检查 `mcp_rpm_limit` 配置或等待窗口重置 |

### 关键步骤

1. 确认 MCP 服务器可达：从 LiteLLM 所在主机 `curl` MCP endpoint
2. 使用 **MCP Inspector** 验证 MCP 服务器独立运行正常
3. 在 LiteLLM UI 的 **MCP Tool Testing Playground** 中测试
4. 检查 LiteLLM proxy 日志（access log + error log）
5. 检查 MCP 服务器本身的日志

## 参考链接

- [MCP Overview (官方)](https://docs.litellm.ai/docs/mcp)
- [Using your MCP](https://docs.litellm.ai/docs/mcp_usage)
- [MCP REST API](https://docs.litellm.ai/docs/mcp_rest_api)
- [MCP Permission Management](https://docs.litellm.ai/docs/mcp_control)
- [MCP Troubleshooting Guide](https://docs.litellm.ai/docs/mcp_troubleshoot)
- [MCP Deployment Guide](https://docs.litellm.ai/docs/mcp_deployment)
- [MCP from OpenAPI Specs](https://docs.litellm.ai/docs/mcp_openapi)
- [MCP OAuth](https://docs.litellm.ai/docs/mcp_oauth)

---

## 附录：实际案例 — 集成 mcpSway 技能库

以下记录本技能编写过程中，将 mcpSway 仓库（Sway 桌面配置技能集合）注册为 LiteLLM STDIO MCP 服务器的完整流程与经验总结。

### 背景

mcpSway 是 Hermes 技能库，包含 waybar-config 等 Sway 配置技能（SKILL.md 格式）。目标是：
- 注册到 LiteLLM 成为 MCP 服务，供多个 agent（Hermes、Cursor、Claude Desktop）共享访问
- 统一鉴权，不必每台机器各自配 key

### 配置步骤

#### 1. 创建 STDIO MCP 服务器脚本

```python
# mcpSway-server.py — 读取 skills/*/SKILL.md 暴露为 MCP 工具
# 协议：MCP JSON-RPC over stdio
# 位于子模块仓库 mcpSway/ 内，config.yaml 引用 /mcps/mcpSway/mcpSway-server.py
```

关键方法：
- `tools/list` → 扫描 skills/ 子目录，返回工具列表
- `tools/call` → 读取指定技能的 SKILL.md 内容（支持 ref/list_refs 子参数）

#### 2. 配置 config.yaml

```yaml
mcp_servers:
  mcpSway:
    transport: stdio
    command: python3
    args: [/mcps/mcpSway/mcpSway-server.py]
    allow_all_keys: true
    description: mcpSway 技能库 — Sway 桌面环境配置技能集合
```

#### 3. Docker 卷挂载

```yaml
volumes:
  - ./mcps:/mcps
```

### 验证清单

重启 LiteLLM 后依次执行：

```bash
# 1. 确认服务器已注册
curl -s http://litellm:4000/v1/mcp/server

# 2. 确认工具列表
curl -s "http://litellm:4000/mcp-rest/tools/list?server_id=mcpSway"

# 3. 原生 MCP 端点测试（需要 Accept header）
curl -s -X POST http://litellm:4000/mcpSway/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# 4. 调用工具
curl -s -X POST http://litellm:4000/mcpSway/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"mcpSway-waybar-config","arguments":{}}}' | grep data:
```

### 经验教训

#### ✅ 做对了的

| 做法 | 说明 |
|------|------|
| **client → LiteLLM gateway → stdio 子进程** | 三层架构清晰，LiteLLM 做鉴权和路由，STDIO 子进程只干一件事 |
| **`allow_all_keys: true`** | 个人部署场景省去了 per-key 权限配置，所有有效 key 都能用 |
| **原生 MCP 端点测试优先** | `POST /{server_name}/mcp` 比 REST API 更可靠（`/mcp-rest/tools/call` 对 STDIO 支持有限） |
| **STDIO 脚本独立测试再注册** | 在部署前先用 echo pipe 模拟 stdin 测试 MCP 协议交互，减少容器内 Debug 成本 |

#### ❌ 踩过的坑

| 问题 | 根因 | 修复 |
|------|------|------|
| `ValidationError: InitializeResult` | STDIO 服务器只实现了 `tools/list` 和 `tools/call`，**没有实现 `initialize` 握手** | 主循环添加 `initialize` 方法（返回 protocolVersion + capabilities + serverInfo）和 `notifications/initialized` 处理 |
| `Not Acceptable` | 原生 MCP 端点要求 `Accept: application/json, text/event-stream` | 调用时添加该 header |
| `Tool config not found` | `POST /mcp-rest/tools/call` 对 STDIO 类型服务器支持不完整 | 改用原生 MCP 端点 |
| **tools/list 返回空（无报错）** | `load_skills` 只扫 `skills/<name>/SKILL.md`，但实际结构是 `skills/local/<name>/SKILL.md` | 递归扫描多一级目录，或展平 `skills/` 去掉多余层级 |
| **standalone 副本 vs 子模块脚本** | 在 mcps/ 根目录创建了 `mcpSway-server.py` 副本，而非直接修改子模块内的脚本 | config.yaml 直接引用子模块内脚本，不要创建 standalone 副本 |
| **SWAY_DIR 随脚本位置错误** | 脚本从 mcps/ 根目录移到子模块内后，`SWAY_DIR = HERE / "mcpSway"` 仍沿用旧计算方式 | 改为 `SWAY_DIR = HERE`（脚本在 mcpSway 仓库内，skills 在同级） |
| **遗漏说明访问路径和鉴权** | 配置完只写了 "重启生效"，没说客户端怎么连怎么认证 | 见上方"配置提交清单"强制三步 |

### 架构决策

#### Hermes 接入方式对比

| 方式 | 路径 | 对多 agent 共享 | 复杂度 |
|------|------|-----------------|--------|
| Hermes 原生 stdio | `command: python3 args: [mcpSway-server.py]` | ❌ 每台机器各自配 | 低 |
| **Hermes HTTP → LiteLLM 网关** | `url: http://litellm:4000/mcpSway/mcp` | ✅ 统一 endpoint | 中 |
| Hermes external_dirs | 直接读 SKILL.md 文件 | ❌ 需文件系统访问 | 低 |

**推荐**：多 agent 共享场景走 LiteLLm 网关（HTTP），单机单 agent 走 external_dirs（零开销）。

#### 工具名前缀对比

| 层 | 前缀格式 | 示例 |
|----|---------|------|
| LiteLLM 原生 MCP 端点 | `{server_name}-{tool}` | `mcpSway-waybar-config` |
| Hermes native mcp_client | `mcp_{server}_{tool}` | `mcp_mcpSway_waybar-config` |

### 文件部署（远程服务器）

向运行 LiteLLM 的远程 server 部署自建 MCP 脚本时：

```bash
# 推荐：scp 直接复制
scp ./server.py user@host:~/project/mcps/server.py

# 避免：heredoc 嵌 Python（引号转义极易出错）
# 避免：echo base64 管道
```
