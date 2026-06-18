# 自建 STDIO MCP 服务器模式

将本地文件/技能库暴露为 MCP 工具，注册到 LiteLLM 的通用模式。

## 适用场景

- 有一组本地文档、技能文件或配置文件需要被 LLM agent 通过 MCP 协议访问
- 但相关服务没有现成的 HTTP MCP server（如 mcpSway 技能库）
- 需要 LiteLLM 统一管理对这些本地内容工具的访问权限

## 架构

```
LLM Agent (Hermes) → LiteLLM Gateway → [stdio] → mcpSway-server.py → skills/*/SKILL.md
```

LiteLLM 为 stdio 子进程提供 stdin/stdout 管道，MCP JSON-RPC 协议通过管道通信。

## 标准协议实现

MCP stdio 协议基于 JSON-RPC 2.0，通过 stdin 读请求、stdout 写响应。完整生命周期：

```
Client                                Server
  │                                     │
  ├── initialize (protocolVersion)  →── │
  │                  ←── InitializeResult (protocolVersion, capabilities, serverInfo)
  │                                     │
  ├── initialized (notification)    →── │  (无回复)
  │                                     │
  ├── tools/list                    →── │
  │                  ←── tools[]         │
  ├── tools/call                    →── │
  │                  ←── content[]      │
```

### initialize — 握手（必先执行）

```python
# 输入（Client → Server）
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"litellm","version":"1.0.0"}}}

# 输出（Server → Client）
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-03-26","capabilities":{"tools":{}},"serverInfo":{"name":"my-server","version":"1.0.0"}}}
```

InitializeResult 必须包含三个字段：
- `protocolVersion`: 与 client 请求的版本对齐
- `capabilities`: 声明服务器能力，至少 `{"tools": {}}`
- `serverInfo`: 服务器名称和版本

### tools/list — 列出工具

```python
# 输入（Agent → LiteLLM → stdio stdin）
{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}

# 输出（stdio stdout → LiteLLM → Agent）
{"jsonrpc":"2.0","id":1,"result":{"tools":[{"name":"waybar-config","description":"...","inputSchema":{"type":"object","properties":{},"required":[]}}]}}
```

每个工具必须包含 `name`、`description`、`inputSchema` 三个字段。

### tools/call — 调用工具

```python
# 输入
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"waybar-config","arguments":{"list_refs":true}}}

# 输出
{"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"..."}]}}
```

`content` 是数组，目前常用 `{"type": "text", "text": "..."}` 格式。

## 完整主循环骨架（含初始化握手）

```python
import json, sys

MCP_PROTOCOL_VERSION = "2025-03-26"
SERVER_INFO = {"name": "my-server", "version": "1.0.0"}
CAPABILITIES = {"tools": {}}

def handle_list_tools() -> dict:
    return {"tools": [...]}

def handle_call_tool(name: str, arguments: dict) -> dict:
    return {"content": [{"type": "text", "text": "..."}]}

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        method = req.get("method", "")
        req_id = req.get("id")

        # MCP 初始化握手
        if method == "initialize":
            params = req.get("params", {})
            client_version = params.get("protocolVersion", MCP_PROTOCOL_VERSION)
            resp = {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "protocolVersion": client_version,
                    "capabilities": CAPABILITIES,
                    "serverInfo": SERVER_INFO,
                },
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
            continue

        # initialized notification — 无需回复
        if method == "notifications/initialized":
            continue

        params = req.get("params", {})

        if method == "tools/list":
            result = handle_list_tools()
        elif method == "tools/call":
            result = handle_call_tool(params.get("name"), params.get("arguments", {}))
        else:
            resp = {
                "jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
            continue

        resp = {"jsonrpc": "2.0", "id": req_id, "result": result}
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()

if __name__ == "__main__":
    main()
```

注意：
- `initialize` 的 `req_id` 来自请求，不能硬编码为 1
- `notifications/initialized` 是 notification（无 id 字段），**不可回复**
- 未知方法应返回标准 JSON-RPC 错误码 `-32601`

## 验证

```bash
# 模拟完整 MCP 协议流
printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}\n{"jsonrpc":"2.0","id":2,"method":"notifications/initialized","params":{}}\n{"jsonrpc":"2.0","id":3,"method":"tools/list","params":{}}\n{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"...","arguments":{}}}' | python3 my_server.py
```

## 注册到 LiteLLM

### 1. config.yaml

```yaml
mcp_servers:
  my_local_content:
    transport: stdio
    command: python3
    args: [/path/to/server.py]
    description: My local skills and docs
```

### 2. Docker 卷挂载

如果 LiteLLM 在 Docker 中运行，需要挂载脚本目录：

```yaml
volumes:
  - ./mcps:/mcps   # 使 /mcps/server.py 在容器内可访问
```

### 3. 重启令配置生效

```bash
# 只有当 LiteLLM 不服务于当前 Agent 的模型时才能执行
docker compose restart litellm
```

**如果当前 Agent 正通过此 LiteLLM 获取推理** → 不能重启。做好配置修改后告知用户手动操作的步骤。

## 通过 LiteLLM 验证部署

注册到 LiteLLM 并重启后，通过以下命令验证 STDIO 服务器是否正常工作。

### 准备工作

需要一个有效的 LiteLLM API key（虚拟 key，非 master key）：

```bash
# 生成临时 key
KEY_DATA=$(curl -s -X POST "http://litellm:4000/key/generate" \
  -H "x-litellm-api-key: Bearer $MASTER_KEY" \
  -H "Content-Type: application/json" -d "{}")
KEY=$(echo "$KEY_DATA" | python3 -c "import sys,json;print(json.load(sys.stdin)['key'])")
```

### 验证 MCP 服务器已注册

```bash
curl -s "http://litellm:4000/v1/mcp/server" \
  -H "x-litellm-api-key: Bearer $KEY" | python3 -m json.tool
```

确认新服务器出现在列表中。

### 验证工具列表（原生 MCP 端点）

原生 MCP 端点使用 Streamable HTTP 协议，需要指明 Accept header：

```bash
curl -s -X POST "http://litellm:4000/{server_name}/mcp" \
  -H "x-litellm-api-key: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

响应为 SSE 格式：

```
event: message
data: {"jsonrpc":"2.0","id":1,"result":{"tools":[{"name":"mcpSway-waybar-config",...}]}}
```

**注意**：LiteLLM 会自动为工具名添加 `{server_name}-` 前缀。

### 验证工具调用

```bash
curl -s -X POST "http://litellm:4000/{server_name}/mcp" \
  -H "x-litellm-api-key: Bearer $KEY" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"{server_name}-{tool_name}","arguments":{}}}'
```

### REST API 的局限性

| 端点 | STDIO 支持 | 说明 |
|------|-----------|------|
| `GET /v1/mcp/server` | 完全支持 | 列出服务器 |
| `GET /mcp-rest/tools/list?server_id=xxx` | 完全支持 | 列出工具 |
| `POST /mcp-rest/tools/call` | 可能报 `Tool config not found` | 对 STDIO 不保证可用 |
| `POST /{server_name}/mcp` | 完全支持 | **推荐**使用此端点 |

对于 STDIO 类型的 MCP 服务器，始终优先使用原生 MCP 端点 `POST /{server_name}/mcp`。

### 无 key 验证

配置了 `allow_all_keys: true` 时，任何有效的 LiteLLM 虚拟 key 均可访问，无需额外的 `object_permission`。完全不传 key 会返回 `MCP request failed`。

## 文件传输到远程服务器

向运行 LiteLLM 的远程主机部署自建 MCP 服务器脚本时：

1. **优先用 `scp`** — 避免 heredoc 引号转义问题
   ```bash
   scp ./server.py user@host:~/project/mcps/server.py
   ```

2. **用 base64 管道传输 Python 脚本**（如无 scp）：
   ```bash
   base64 -w0 server.py | ssh host "cat > server.py && base64 -d > server.py"
   ```

3. **避免 heredoc 嵌套** — `<< 'EOF'` 内嵌 Python 代码含未转义的 `$`、反斜杠、引号时极易出错
