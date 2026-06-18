# Hermes Skills → MCP Gateway Pipeline

将 Hermes 本地技能迁移为 MCP 协议服务的端到端模式。

## 架构

```
Hermes 本地技能                     MCP 服务端                    MCP 客户端
(~/.hermes/skills/)               (LiteLLM Gateway)             (任意 MCP 客户端)
         │                               │                            │
         │  copy/merge                    │                            │
         ├─────────────────► mcpSway/     │                            │
         │                   skills/      │                            │
         │                   ├── sw-x/    │  LiteLLM 启动              │
         │                   │   SKILL.md │ 时注册 STDIO              │
         │                   ├── sw-y/    │ MCP 服务器                 │
         │                   │   SKILL.md │ ├── tools/list             │
         │                   │   refs/    │ └── tools/call             │
         │                   └── sw-z/    │                            │
         │                       SKILL.md │   ▲                       │
         │                                │   │ HTTP (Streamable)     │
         │                                │   │                       │
         │                                │   ├── mcpSway/mcp ◄──────┼── Hermes
         │                                │   │                       │    (native MCP client)
         │                                │   │                       ├── Cursor
         │                                │   │                       ├── Claude Desktop
         │                                │   │                       └── 其他 agent
```

## 完整步骤

### 1. 创建集中仓库

```bash
mkdir -p ~/workspace/mcpSway/skills  # 技能文件
mkdir -p ~/workspace/mcpSway/scripts # 实用脚本
mkdir -p ~/workspace/mcpSway/configs # 参考配置
mkdir -p ~/workspace/mcpSway/docs    # 文档
git init
```

编写 `PRINCIPLES.md`（仓库基本原则）和 `AGENTS.md`（AI Agent 工作指南）。

### 2. 编写/迁入技能

每个技能 = `skills/<topic>/SKILL.md` + 可选 `references/` + `templates/` + `scripts/`。

**SKILL.md frontmatter 要求（AGENTS.md）：**

```yaml
---
name: topic-name
source: https://official-docs-url      # 必须！指向官方文档
description: "简短描述"
tags: [category, topic]
---
```

### 3. 创建 STDIO MCP 服务器脚本

```python
# mcpSway-server.py — 扫描 skills/*/SKILL.md 暴露为 MCP 工具
# 核心方法:
#   tools/list → 遍历 skills/ 子目录，返回工具列表
#   tools/call → 读取指定 SKILL.md 内容
```

完整实现参考 `litellm-mcp-config` 技能中 `references/custom-stdio-mcp-server-pattern.md`。

**关键要求：**
- 必须实现 `initialize` 握手（返回 protocolVersion + capabilities + serverInfo）
- 必须处理 `notifications/initialized`（notification，无需回复）
- 工具名在 LiteLLM 端自动加 server 前缀：`mcpSway-waybar-config`

### 4. 注册到 LiteLLM

**config.yaml：**

```yaml
mcp_servers:
  mcpSway:
    transport: stdio
    command: python3
    args: [/mcps/mcpSway-server.py]
    allow_all_keys: true
    description: Sway 桌面环境配置技能集合
```

**docker-compose.yml（Docker 部署时需要）：**

```yaml
volumes:
  - ./mcps:/mcps   # 使容器内可访问脚本和技能文件
```

### 5. Hermes 客户端接入

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  mcpSway:
    url: "http://litellm:4000/mcpSway/mcp"
    headers:
      x-litellm-api-key: "Bearer sk-..."
```

工具注册为 `mcp_mcpSway_<tool>`，如 `mcp_mcpSway_waybar-config`。

## 变更管理

### 添加新技能

1. 在 `skills/` 下创建子目录并写 SKILL.md
2. git add + commit + push
3. **无需重启 LiteLLM** — mcpSway-server.py 每次 `tools/list` 调用时实时扫描 skills/ 目录
4. Hermes 下次重启后自动发现新工具

### 更新已有技能

直接修改 SKILL.md，提交到 GitHub。`tools/call` 是实时读取文件内容，修改立即可见。

### 多客户端同步

使用 Git submodule 或子目录复制将 mcpSway 仓库部署到运行 LiteLLM 的服务器：

```bash
cd ~/liteLLM.docker/mcps
git submodule add https://github.com/user/mcpSway.git
```

## 技能分析/合并工作流

当需要从多个现有技能合并、去重、优化到 mcpSway 时，使用 **并行 subagent 分析**：

```python
# 1. 并行分析（每个 subagent 处理一批技能）
subagent1 = delegate_task(goal="分析技能 A、B、C 的冗余", toolsets=['file'])
subagent2 = delegate_task(goal="分析技能 D、E 的内容重叠", toolsets=['file'])
subagent3 = delegate_task(goal="检查技能 F、G 的合规性", toolsets=['file'])

# 2. 审阅各 subagent 报告，决策合并/精简方案

# 3. 按批执行：复制 → 修改 frontmatter → 去重内容 → 移动 linked files

# 4. 删除旧技能，提交推送，更新子模块
```

## 相关技能

- `litellm-mcp-config` — LiteLLM MCP 配置完整参考
- `hermes-external-skills` — Hermes external_dirs 技能加载
- `subagent-driven-development` — subagent 驱动开发工作流
