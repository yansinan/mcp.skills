# STDIO MCP 服务器 tools/list 空调试指南

LiteLLM 注册的 STDIO MCP 服务器注册成功（`GET /v1/mcp/server` 能看到）但 `tools/list` 返回空数组时的系统化调试方法。

## 典型表现

```
# REST API — allowed_tools 为 0
GET /v1/mcp/server → {"server_name":"my_srv","transport":"stdio","allowed_tools":[],...}

# 原生 MCP 端点 — 工具列表为空
POST /my_srv/mcp → {"result":{"tools":[]}}
```

**无错误日志**：因为脚本 stdout 输出了合法的 JSON-RPC 结果，所以 LiteLLM 不会报错。唯一排查路径是独立测试脚本。

## 调试步骤

### 第一步：独立测试 STDIO 脚本

绕过 LiteLLM，直接在命令行模拟完整 MCP 协议交互：

```bash
cd /path/to/mcps/
printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}\n\
{"jsonrpc":"2.0","id":2,"method":"notifications/initialized","params":{}}\n\
{"jsonrpc":"2.0","id":3,"method":"tools/list","params":{}}\n' | python3 my_server.py 2>/tmp/mcp_stderr
```

检查：
- **stdout**：看第三条消息（`id:3`）的 `result.tools` 是否为空
- **stderr**（`cat /tmp/mcp_stderr`）：有无 Python 语法错误、IndentationError、ModuleNotFoundError

如果脚本直接返回空列表 → 脚本逻辑问题（见下文常见原因）。

### 第二步：检查实际目录结构与脚本扫描深度

```bash
# 查看 SKILL.md 实际位置
find skills -name SKILL.md -type f

# 查看脚本中 load_skills 扫描了多深
grep -n 'iterdir\|skills_dir\|SKILL.md' my_server.py | head -10
```

**关键判断**：脚本的 `iterdir()` 扫描目录层级是否覆盖了实际 SKILL.md 的层级。

### 第三步：确认脚本语法正确

```bash
python3 -c "compile(open('my_server.py').read(), 'my_server.py', 'exec'); print('Syntax OK')"
```

Python 的 IndentationError 不会导致脚本崩溃（MCP 主循环是逐行读取 stdin），但会卡在语法错误的位置。特别是通过 `sed`/`replace` 修复脚本后，缩进可能被破坏。

## 常见原因

### 1. 目录深度不匹配（最常见）

| 脚本期望 | 实际结构 | 结果 |
|----------|----------|------|
| `skills/<skill>/SKILL.md` | `skills/local/<skill>/SKILL.md` | 空工具列表 |

**两种修复方式**：

**方案 A — 递归扫描**（不动目录结构）：`load_skills` 改为先扫一级，再扫每个子目录：

```python
def _scan(dir_path: Path):
    for sub in sorted(dir_path.iterdir()):
        skill_md = sub / "SKILL.md"
        if not skill_md.is_file():
            continue
        entries.append({
            "name": sub.name,
            "description": "...",
            "path": str(skill_md),
        })

# 一级扫描
_scan(skills_dir)
# 二级扫描（skills/<cat>/<skill>/SKILL.md）
for sub in sorted(skills_dir.iterdir()):
    if sub.is_dir():
        _scan(sub)
```

**方案 B — 展平 `skills/`**（推荐，如果分类层是 agent 错误操作）：直接把 `skills/local/<name>/` 移到 `skills/<name>/`：

```bash
cd path/to/mcpSway/skills
for d in local/*/; do mv "$d" ./; done
rmdir local
```

优点：原始 `load_skills`（只扫一级）无需修改即可工作。确定 skills 不应该有多余层级时才用。

### 2. 文件未通过卷挂载映射

Docker 部署时，脚本路径在容器内可见，但 `skills/` 可能不在挂载范围内。确认 `docker-compose.yml` 的 volumes 覆盖了完整目录树：

```yaml
volumes:
  - ./mcps:/mcps     # 确保 /mcps/my_proj/skills/ 完整映射
```

### 3. initialize 握手未实现

如果脚本未处理 `initialize` 方法，LiteLLM 的 MCP SDK 会报 `ValidationError`（不是静默空列表，有错误日志）。参见 SKILL.md 关键陷阱 #1。

## 完整诊断脚本

```bash
#!/bin/bash
# diagnose_stdio_mcp.sh — 快速诊断 STDIO MCP 服务器
SERVER_PY="$1"
if [ -z "$SERVER_PY" ]; then
  echo "Usage: $0 <server.py>"
  exit 1
fi

echo "=== 1. 语法检查 ==="
python3 -c "compile(open('$SERVER_PY').read(), '$SERVER_PY', 'exec'); print('OK')" || exit 1

echo ""
echo "=== 2. 目录结构 ==="
SCRIPT_DIR=$(dirname "$(realpath "$SERVER_PY")")
find "$SCRIPT_DIR" -name SKILL.md -type f 2>/dev/null | head -20

echo ""
echo "=== 3. MCP tools/list 测试 ==="
printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}\n{"jsonrpc":"2.0","id":2,"method":"notifications/initialized","params":{}}\n{"jsonrpc":"2.0","id":3,"method":"tools/list","params":{}}\n' | timeout 5 python3 "$SERVER_PY" 2>/tmp/mcp_diag_stderr | grep '"tools"'

echo ""
echo "=== 4. Stderr 输出 ==="
cat /tmp/mcp_diag_stderr
```
