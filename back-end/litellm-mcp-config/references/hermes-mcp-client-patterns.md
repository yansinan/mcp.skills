# Hermes 通过 LiteLLM MCP Gateway 接入的模式

当 LiteLLM 托管的 MCP 服务器包含的是 skill/文档类文件（如 mcpSway 技能库），Hermes 客户端有四种接入方式。按推荐优先级排列。

## 方式对比

| 方式 | 原理 | 适用场景 | 推荐度 |
|------|------|----------|--------|
| **A. Hermes external_dirs** (skills 加载) | 将 mcpSway/skills/ 加入技能搜索路径 | SKILL.md 原生文件 | ⭐⭐⭐⭐⭐ |
| **B. Hermes mcp_servers stdio** (本地进程) | 通过 stdio 直接启动 mcpSway-server.py | MCP 协议必须、文件在本地 | ⭐⭐⭐⭐ |
| **C. Hermes mcp_servers HTTP** (经 LiteLLM) | 通过 HTTP 连接到 LiteLLM 的 MCP 端点 | 需要经过 LiteLLM 统一鉴权/日志 | ⭐⭐⭐ |
| **D. 直接文件读取** (read_file / search_files) | 直接用文件工具读取 | 一次性查阅 | ⭐⭐⭐ |

## 方案 A：external_dirs（Hermes 技能系统最优选）

**原理**：mcpSway/skills/ 存放的是标准 SKILL.md 文件，Hermes 的技能引擎直接加载。

```yaml
# ~/.hermes/config.yaml
skills:
  external_dirs:
    - /home/dr/workspace/mcpSway/skills
```

**优点**：
- 零网络、零 Auth、零额外进程
- SKILL.md 的 frontmatter (tags/description/version) 完整保留
- 技能文件更新即时生效（Hermes 下次启动时）
- 使用已有的 `skill_view` / `skills_list` 接口

**条件**：mcpSway 仓库需要在 Hermes 可访问的本地路径。

## 方案 B：Hermes 原生 MCP 客户端 → 本地 stdio

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  mcpSway:
    command: python3
    args: ["/home/dr/workspace/mcpSway/mcpSway-server.py"]
```

**工具命名**：`mcp_mcpSway_waybar-config`
**条件**：Hermes 已安装 `mcp` Python 包（pip install mcp）

## 方案 C：Hermes 原生 MCP 客户端 → LiteLLM HTTP

```yaml
mcp_servers:
  mcpSway:
    url: "http://serverhome:4000/mcpSway/mcp"
    headers:
      x-litellm-api-key: "Bearer sk-..."
```

**条件**：
- LiteLLM 在运行且网络可达
- LiteLLM API key 有该服务器的访问权限
- Hermes 安装的 mcp 包支持 StreamableHTTP

## 决策树

```
内容是什么？
├── SKILL.md 文件 → 方案 A（external_dirs）最优
├── 通用 MCP 协议工具（API、数据库、文件系统）
│   ├── 本地执行 → 方案 B（stdio）
│   └── 远程或需要统一鉴权 → 方案 C（HTTP via LiteLLM）
```