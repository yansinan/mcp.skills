# Creating an External Skill Repository

This is the **creation-side** counterpart to consuming external skills via `external_dirs`.
Use when building a portable, shareable skill collection from scratch — e.g. an mcpSway
repo for sway/Linux desktop configuration skills.

## Repository Structure

```
repo-name/
├── AGENTS.md             # AI Agent 工作指南 — 被此仓库的 agent 执行时第一件事就是读这个
├── PRINCIPLES.md         # 仓库基本原则 — 官方文档优先/来源必注明/来源层级/不确定即查证/定期同步
├── skills/
│   └── local/            # 所有本地自建技能在此（不要放在 local/ 以外）
│       ├── my-skill/
│       │   ├── SKILL.md
│       │   ├── references/   # 会话级细节、错误追踪、API 文档摘录
│       │   ├── templates/    # 可复制修改的样板文件
│       │   └── scripts/      # 可重用的验证/检测脚本
│       └── ...
└── README.md
```

### AGENTS.md 必备内容

操作此仓库的 AI Agent（Hermes、Claude Code 等）在首次接触时必须读 AGENTS.md。应包含：

- 仓库范围与目录结构
- 五项基本原则（来自 PRINCIPLES.md）
- Agent 操作规范（搜索优先级、技能编写规范、更新流程）

### PRINCIPLES.md 五项原则

| # | 原则 | 含义 |
|---|------|------|
| 1 | 官方文档优先 | 配置参数的最终依据是官方文档,非社区/经验 |
| 2 | 来源必注明 | 每个命令、配置项旁标注来源 URL |
| 3 | 来源优先级 | 官方文档 > 开源仓库 > 社区 > 经验 > 其他 |
| 4 | 不确定即查证 | 不盲猜,先查 man/官方文档/具体错误,找到确切答案再执行 |
| 5 | 定期同步 | 本地技能标注 source 字段,定期与线上官方文档对齐 |

## 迁移工作流（从 Hermes 到外部仓库）

### Step 1: 分析现有技能（使用 subagent）

不要手动对比每个技能。使用 `delegate_task` 并行分析：

```python
delegate_task(
    goal="分析 N 个技能的异同，给出合并/精简方案",
    context="已有 A, B, C 三个技能的完整内容，识别重叠和独有价值",
    toolsets=["file", "search"]
)
```

每个 subagent 分析一个组（如 3 个 btrfs 技能、2 个 sway 技能），返回：
- 重复内容清单
- 各自独有价值
- 合并建议（以哪个为基底，吸收什么）
- 建议的 source 字段值

### Step 2: 审阅 → 合并 → 合规

根据 subagent 报告：

| 动作 | 说明 |
|------|------|
| **合并** | 高度重叠的技能合并为 1 个（如 3×btrfs → 1, 3×RDP → 1） |
| **去重** | 被独立技能覆盖的章节从大技能中删除（如 sway-debian-setup 删除音频/UxPlay 章节） |
| **补 source** | 每个 SKILL.md 的 frontmatter 必须有 `source` 字段指向官方文档 |
| **修断裂引用** | 检查 references/ 中所有文件引用是否存在 |
| **加 tags** | 帮助分类检索 |

### Step 3: 移动到外部仓库

```bash
mkdir -p repo/skills/local/skill-name
cp -r ~/.hermes/skills/local/skill-name/references repo/skills/local/skill-name/
cp -r ~/.hermes/skills/local/skill-name/templates repo/skills/local/skill-name/
cp -r ~/.hermes/skills/local/skill-name/scripts repo/skills/local/skill-name/
cp ~/.hermes/skills/local/skill-name/SKILL.md repo/skills/local/skill-name/
```

### Step 4: 删除本地原始技能

```bash
rm -rf ~/.hermes/skills/<category>/<skill-name>
```

### Step 5: 验证 & 推送

```bash
cd repo && git add -A && git commit -m "feat: migrate skill-name"
git push origin main
```

## MCP 暴露（多 agent 共享）

为了让外部仓库的技能对多个 agent 可访问（而不只是本地 Hermes），通过 LiteLLM
注册一个 STDIO MCP 服务器：

### mcpSway 模式的参考实现

仓库根目录放 `mcpSway-server.py`，实现 MCP JSON-RPC over stdio：

```
repo/
├── mcpSway-server.py     ← MCP stdio 服务器
├── skills/local/
│   └── ...
```

`mcpSway-server.py` 自动扫描 `skills/local/` 目录，每个 SKILL.md 暴露为一个 MCP 工具。

### 关键：必须实现 initialize 握手

LiteLLM 的 MCP 客户端严格按照协议先发 `initialize` 再发 `tools/list`。
服务器必须在主循环中处理 `initialize` 方法（返回 protocolVersion + capabilities + serverInfo）
和 `notifications/initialized` notification。

```python
if method == "initialize":
    params = req.get("params", {})
    client_version = params.get("protocolVersion", "2025-03-26")
    resp = {
        "jsonrpc": "2.0", "id": req_id,
        "result": {
            "protocolVersion": client_version,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "mcpSway", "version": "1.0.0"},
        },
    }
    # write to stdout
    continue
```

缺少 `initialize` 处理会导致 `ValidationError: InitializeResult — protocolVersion Field required`。

### 注册到 LiteLLM

在 LiteLLM 的 `config.yaml` 中添加：

```yaml
mcp_servers:
  mySkillRepo:
    transport: stdio
    command: python3
    args: [/path/to/server.py]
    allow_all_keys: true
    description: My skill repository
```

Docker 部署时需要挂载仓库目录：

```yaml
volumes:
  - ./repo:/repo
```

### 访问方式

| 方式 | 路径 | 说明 |
|------|------|------|
| 原生 MCP 端点 | `POST /{server_name}/mcp` | 需 `Accept: application/json, text/event-stream` |
| REST API 清单 | `GET /mcp-rest/tools/list?server_id=mySkillRepo` | 列出工具 |
| Hermes mcp_servers | config.yaml 中配置 url | 自动发现为 mcp_{server}_{tool} |

**已知限制**：`POST /mcp-rest/tools/call` 对 STDIO 类型服务器支持不完整，
返回 "Tool config not found"。推荐使用原生 MCP 端点。

## Hermes 接入方式对比

| 方式 | 配置 | 多 agent 共享 | 复杂度 |
|------|------|---------------|--------|
| Hermes 原生 stdio MCP | `mcp_servers: { command: python3, args: [server.py] }` | ❌ 每台机器各自配 | 低 |
| Hermes HTTP → LiteLLM 网关 | `mcp_servers: { url: "http://gw:4000/{server}/mcp" }` | ✅ 统一端点 | 中 |
| Hermes external_dirs | `external_dirs: [/path/to/repo/skills]` | ❌ 需文件系统 | 低 |

**推荐**：多 agent 共享场景走 LiteLLM 网关，单机单 agent 走 external_dirs。

## 适用于此仓库的 AGENTS.md 规则

```markdown
### 编写技能（SKILL.md）
- 每个技能必须包含 `source` 字段，指向官方文档 URL
- 配置示例必须经过实际验证，不得凭空构造
- 中文注释
- 实用至上，避免冗余

### 搜索优先级
1. `man <component>` / `<command> --help`
2. 搜索官方文档
3. 搜索 GitHub issues 和项目文档
4. 本仓库已有技能和配置
5. 其他网络搜索

### 更新流程
1. 搜索官方文档确认最新配置方式
2. 在本地技能/配置中更新，注明来源
3. 验证配置有效
4. 提交变更
```
