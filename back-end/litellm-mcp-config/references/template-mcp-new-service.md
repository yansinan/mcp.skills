# template.mcp → 新 MCP 服务仓库工作流

`yansinan/template.mcp` 是标准化的 MCP 服务模板仓库，用于快速创建新的 MCP 服务。

## 工作流

### 1. 创建 GitHub 仓库

```bash
# 自动初始化 README
gh repo create yansinan/<service-name>.mcp --public --description "..." --add-readme

# 或通过 API / Web UI
```

### 2. 克隆到本地

```bash
cd ~/workspace
git clone https://github.com/yansinan/<service-name>.mcp.git
```

### 3. 从模板复制基础文件

```bash
cp ~/workspace/template.mcp/.gitignore   <new-dir>/
cp ~/workspace/template.mcp/AGENTS.md    <new-dir>/
cp ~/workspace/template.mcp/PRINCIPLES.md <new-dir>/
cp ~/workspace/template.mcp/mcp-server.py <new-dir>/
mkdir -p <new-dir>/{skills,scripts,configs,docs}
```

### 4. 定制 mcp-server.py

修改 **可定制区域** 的三个常量：

```python
SERVER_INFO = {
    "name": "your-service-name",  # ← 改
    "version": "1.0.0",
}
CONTENT_DIR = HERE / "skills"      # ← 指向实际内容目录
```

### 5. 填充技能内容

每个子目录是一个 MCP 工具。目录名 = 工具名（kebab-case）。

`skills/<name>/SKILL.md` 格式：

```markdown
---
description: "工具描述（tools/list 中展示）"
tags: [tag1, tag2]
---

## 正文内容

...
```

### 6. 验证 MCP 协议

```bash
cd ~/workspace/<service-name>.mcp

# initialize 握手
printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}\n' \
  | python3 mcp-server.py

# tools/list
printf '...{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n' \
  | python3 mcp-server.py

# tools/call
printf '...{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"<tool-name>","arguments":{}}}\n' \
  | python3 mcp-server.py
```

**注意**：连续输入多条消息时用换行分隔，`initialize` 必须在前（或至少有一个 `initialize` 在前）。

### 7. 注册到 LiteLLM

```yaml
mcp_servers:
  <service-name>:
    transport: stdio
    command: python3
    args: [/mcps/<service-name>.mcp/mcp-server.py]
    allow_all_keys: true
```

Docker 部署需要卷挂载：

```yaml
volumes:
  - ./mcps:/mcps
```

### 8. Stage（不 commit）

按用户工作流：**只 `git add`，不 `git commit`**。用户审阅 diff 后自己写 commit message 并提交。

## 模板结构说明

```
template.mcp/
├── mcp-server.py        # Stdio MCP 服务器骨架
├── PRINCIPLES.md        # 5 条基本原则（官方文档优先、来源必注明、优先级、查证、同步）
├── AGENTS.md            # AI Agent 操作指南
├── skills/              # 内容目录（MCP 工具暴露的数据）
├── scripts/             # 辅助脚本
├── configs/             # 参考配置
├── docs/                # 文档与笔记
└── README.md
```

## 与 mcpSway 模式的区别

| 维度 | mcpSway 模式 | template.mcp 模式 |
|------|-------------|-------------------|
| 用途 | Sway 桌面配置技能集合 | 通用 MCP 服务模板 |
| 内容类型 | 桌面配置技能 | 任意运维/知识类内容 |
| 仓库关系 | 独立仓库 + LiteLLM submodule | 独立仓库 + LiteLLM submodule |
| 触发方式 | 用户 /agent 主动调用 | 同左 |
| 部署方式 | LiteLLM STDIO | LiteLLM STDIO |
