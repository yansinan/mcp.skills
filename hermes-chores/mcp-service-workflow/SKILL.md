---
name: mcp-service-workflow
description: "AI Agent 工作流指南 — 从 template.mcp fork 新 MCP 服务、分类技能、部署到 serverHome 的完整流程和坑点记录"
tags: [mcp, template, workflow, litellm]
---

# MCP Service Workflow

AI Agent 用 — 创建、维护 MCP 服务的操作流程和经验记录。

## 执行原则

1. **一次一步。** 执行完一步就报告，等用户确认再下一步。不要一次批 4 步 — 一步错了 4 步全废。
2. **只做要求的事。** "fork template" = fork template 而已。不加技能、不创建文档、不建子模块。用户没说的事不做。
3. **先查本地。** 操作某个仓库前，先确认 `~/workspace/` 里有没有本地 clone。不要每次都从 GitHub 拉。
4. **确认你在哪个仓库。** `git rm --cached`、`git add`、`.gitignore` 修改前，先 `pwd`。
5. **只 stage，不 commit。** `git add` 后展示 diff，让用户写 commit message。

## Fork template.mcp

```bash
# 1. 确认模板存在
ls ~/workspace/template.mcp/

# 2. 创建 GitHub 仓库
# 3. 克隆到 workspace
cd ~/workspace
git clone git@github.com:yansinan/<new-service>.mcp.git

# 4. 复制模板文件 — 只复制模板里的，不多不少
cp template.mcp/.gitignore <new-service>.mcp/
cp template.mcp/mcp-server.py <new-service>.mcp/
cp template.mcp/AGENTS.md <new-service>.mcp/
cp template.mcp/PRINCIPLES.md <new-service>.mcp/
cp template.mcp/README.md <new-service>.mcp/
mkdir -p <new-service>.mcp/{skills,scripts,configs,docs}

# 5. 定制：
#    - SERVER_INFO["name"] → camelCase, 无连字符
#    - SERVER_INFO["version"] → "1.0.0"
#    - README.md
# 6. git add → 展示 diff → 等用户写 commit message
```

## LiteLLM 注册

Registriation in LiteLLM `config.yaml` — 详细参考 `back-end/litellm-mcp-config`。要点：

- YAML key 用 camelCase，**不能含 `-`**
- 容器内路径取决于 docker-compose 的卷挂载（`./mcps:/mcps`）

## 技能分类与递归扫描

mcp.skills 仓库结构：

```
mcp.skills/
├── back-end/           # 后端服务类
│   ├── deepseek-cost/
│   ├── litellm-api-landscape/
│   └── litellm-mcp-config/
└── hermes-chores/      # 日常运维类
    ├── bundle_skill_restore_all/
    ├── hermes-webui/
    ├── systemd-resolved-dns-triage/
    └── mcp-service-workflow/
```

mcp-server.py 的 `load_entries()` 必须递归扫描（支持分类嵌套）。详见 template.mcp。

## 子模块共享

```bash
# 在 MCP 服务仓库中
git submodule add git@github.com:yansinan/mcp.skills.git skills
git submodule update --remote skills   # 拉最新
```

## serverHome 部署

```bash
ssh dr@serverhome.tail2e6efb.ts.net
cd ~/workspace/liteLLM.docker/mcps
git clone --recurse-submodules git@github.com:yansinan/<service>.mcp.git
# config.yaml 加 mcp_servers 条目
# 用户手动重启 docker（agent 不碰 docker）
```

## 验证

```python
# Stdio 测试
import subprocess, json
p = subprocess.Popen(["python3", "mcp-server.py"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
payload = (
    json.dumps({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}) + "\n" +
    json.dumps({"jsonrpc":"2.0","method":"notifications/initialized"}) + "\n" +
    json.dumps({"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}) + "\n"
)
out, _ = p.communicate(payload, timeout=10)
for line in out.strip().split("\n"):
    data = json.loads(line)
    if "tools" in data.get("result", {}):
        for t in data["result"]["tools"]:
            print(f"  {t['name']}: {t['description'][:60]}")
```

## 命名规范

| 元素 | 规范 | 示例 |
|------|------|------|
| GitHub 仓库名 | `<service>.mcp` | `hermes-chores.mcp` |
| LiteLLM YAML key | camelCase, 无连字符 | `mcpChores` |
| SERVER_INFO name | camelCase, 同 config key | `mcpChores` |
| 目录名 | 同仓库名 | `hermes-chores.mcp/` |

## 已知坑点

1. **不要创造内容** — fork 模板就是 fork 模板，不加技能不创建文档。用户说"这些技能哪来的"说明你编了。
2. **LiteLLM key 不能含连字符** — `hermes-chores` → `mcpChores`
3. **子模块是 pinned 的** — 要 `--remote` 才拉最新
4. **在正确的仓库里操作** — `~/.hermes/skills/local/` 里的 `git rm --cached` 要在父仓库做
5. **SSE 测试用双 Accept** — `Accept: application/json, text/event-stream`，单一个会 `Not Acceptable`
