# SearXNG —— CDP extract 的搜索主力（不是回退）

> 本用户的设计中，SearXNG 是 **搜索主力**，CDP 浏览器引擎（Google/Bing/Baidu）是 SearXNG 不足时的 **fallback**。不要默认把 SearXNG 当作"需要消除的回退"。

## 设计意图

```yaml
web:
  search_backend: searxng       # 搜索主力
  extract_backend: cdp-extract  # 提取直接走 CDP
  backend: cdp-extract          # 兜底
```

搜索流程：

```
web_search_tool()
  → _get_search_backend() → "searxng" ← 配置意图
  → _wsp_get_provider("searxng") → SearXNGProvider ✅
  → SearXNG HTTP GET → 结果
  → 如果不足 → CDP 浏览器引擎 (Google/Bing) fallback
```

SearXNG 不可达或结果不够时，CDP 浏览器搜索（通过 `agent-browser` / CDP WebSocket 操作 Google/Bing）作为副路径补充。

## 何时需要诊断

只在以下场景把 SearXNG 当作问题排查：

- SearXNG 实例彻底不可达（HTTP 超时/500）
- 搜索结果持续为空或过少（上游引擎被封）
- 新机器上尚不清楚搜索后端状态

## 诊断流程

### Step 1: 检查配置文件

```bash
grep -A5 '^web:' ~/.hermes/config.yaml
```

关键字段：

| 字段 | 含义 | 意图值 |
|------|------|--------|
| `web.search_backend` | 搜索后端（**最高优先级**） | `searxng` |
| `web.extract_backend` | 内容提取后端 | `cdp-extract` |
| `web.backend` | 兜底后端（search/extract 未设置时生效） | `cdp-extract` |

**注意：** `cdp-extract` 不在 `web_tools.py` 旧后端的已知名称列表（`{"parallel", "firecrawl", "tavily", "exa", "searxng", "brave-free", "ddgs", "xai"}`）中。这意味着 `_is_backend_available("cdp-extract")` 返回 `False`，`_get_capability_backend()` 始终回退到 `_get_backend()`。详见下文「深层陷阱」。

### Step 2: 理解 Provider 解析优先级

`web_search_registry._resolve()` 的解析链（`web_search_registry.py` line 133–219）：

```
1. 显式配置（优先）:
   → web.search_backend → web.backend
   → 找到后直接返回，不管 is_available()
   
2. 唯一可用 provider:
   → 如果只有一个注册的 provider 支持该能力且 is_available()
   
3. Legacy 偏好序（按顺序找第一个可用的）:
   firecrawl → parallel → tavily → exa → searxng → brave-free → ddgs
   
   ⚠ cdp-extract 不在这个列表中！
     这意味着它是通过显式配置才能被选中的 provider。
     如果既没有显式配置，searxng provider 又注册了且可用，
     SearXNG 就会在步骤 3 胜出。
```

### Step 3: 修复

SearXNG 作为搜索主力是设计意图。只在以下情况需要修复：

- **SearXNG 不可达：** 检查 `SEARXNG_URL=http://searxng.z-core.cn` 是否可达，或 `~/.hermes/.env` 中是否有正确的 URL
- **需要切换搜索后端：** `hermes config set web.search_backend cdp-extract`（让 CDP 浏览器引擎接手搜索）
- **提取异常：** 确保 `extract_backend: cdp-extract` 且 Chrome CDP (port 9222) 在运行

不要直接编辑 `config.yaml`——Hermes 会拦截（"Refusing to write to security-sensitive config"）。用 `hermes config` CLI。

### Step 4: 验证

```bash
# 确认配置
grep -A5 '^web:' ~/.hermes/config.yaml

# 预期输出（搜索主力 SearXNG + 提取 cdp-extract）:
# web:
#   search_backend: searxng
#   extract_backend: cdp-extract
#   backend: cdp-extract
```

如果切换为 CDP 浏览器搜索：

```bash
hermes config set web.search_backend cdp-extract
# → search_backend: cdp-extract
```

## agent-browser 依赖

CDP 搜索不走 CDP WebSocket 直连——它依赖 `agent-browser` CLI 控制浏览器。

### 检查

```bash
ls -la ~/.hermes/node/bin/agent-browser   # 看 symlink 目标是否真实存在
~/.hermes/node/bin/agent-browser --version
```

注意：npm 包可能已缓存但 symlink 丢失（被误删）。此时 ls 报错但 npm install -g agent-browser 很快完成（~3s，从缓存恢复 symlink）。用 ls -la 确认，不要只靠 npm list。

### 安装

```bash
# 国内用 npmmirror registry 加速（默认 registry 慢或超时）
npm install -g agent-browser --registry https://registry.npmmirror.com
```

### 缺失后果

- CDPExtractProvider.search() 调用 multi_search(skip_backend=True) 时失败
- multi_search 调 _ab() 运行 agent-browser
- agent-browser 缺失 → _ab() 静默返回空字符串 (except: return "")
- CDP 浏览器搜索返回空结果

CDP 提取 (extract()) 不受影响——走原生 CDP WebSocket。

## 数据流总览

### 搜索主力：search_backend=searxng

```
web_search("query")
  │
  ▼
_get_search_backend() → "searxng" ← config
  │
  ▼
_wsp_get_provider("searxng") → SearXNGProvider
  │
  ├── HTTP GET → SearXNG instance (searxng.z-core.cn)
  └── lxml XPath parse → 结果列表
```

### 切换后：search_backend=cdp-extract

当需要 CDP 浏览器引擎接手搜索时：

```
web_search("query")
  │
  ▼
get_active_search_provider() → CDPExtractProvider
  │
  ▼
CDPExtractProvider.search(query, limit)
  │  → multi_search(skip_backend=True) 避免递归
  │
  ├── agent-browser connect ws://...:9222
  ├── agent-browser open google.com/search?...
  ├── agent-browser get text "#rso"
  └── agent-browser close
```

### 提取（始终 cdp-extract）

```
web_extract(urls)
  │
  ▼
get_active_extract_provider() → CDPExtractProvider ✅
  │
  ├── CDP Chrome → _fetch_raw_html(url)
  ├── _call_readdown(html) → Readability + Turndown
  └── 结构化 Markdown 结果
```

## 深层陷阱：`_get_backend()` 中间层不认识 cdp-extract

即使 `extract_backend: cdp-extract` 配置正确，旧 `web_tools.py` 的 `_get_capability_backend()` 仍可能返回 `searxng`：

```
_get_capability_backend("search"):
  → 读取 web.search_backend = "searxng" ✅ 直接返回
  （当 extract_backend="cdp-extract" 时:）
  → 读取 web.extract_backend = "cdp-extract"
  → _is_backend_available("cdp-extract") → False ❌
    （旧 if-elif 链不认识 cdp-extract，不在 {"parallel","firecrawl",
     "tavily","exa","searxng","brave-free","ddgs","xai"} 中）
  → 回退到 _get_backend()
  → 检测到 SEARXNG_URL（通过 get_env_value，在 Hermes config layer）
  → 返回 "searxng"
```

**这无害。** 真正的 dispatch 在 `web_search_tool()` / `web_extract_tool()` 中继续：

```
# search 路径
backend = _get_search_backend()          # "searxng" ← 正确
provider = _wsp_get_provider("searxng")  # SearXNGProvider ✅
→ 用 SearXNG 搜索

# extract 路径
backend = _get_extract_backend()          # "searxng" ← 旧系统不认识 cdp-extract
provider = _wsp_get_provider("searxng")   # None (SearXNG 不支持 extract)
if provider is None or not provider.supports_extract():
    provider = get_active_extract_provider()  # cdp-extract ✅
→ 用 cdp-extract 提取
```

所以 **`_get_backend()` 的名字只是一个中间查询结果**，最终由插件注册表决定实际使用的 provider。

### `_is_backend_available` 对 cdp-extract 始终返回 False

这是设计使然——旧 `web_tools.py` 的后端只识别传统 HTTP API 类后端（exa/parallel/firecrawl/tavily/searxng/brave/ddgs）。cdp-extract 是一个插件 provider，其可用性由 `CDPExtractProvider.is_available()` 判定（检查 Node.js + CDP 端口），不走 env var 检测。

影响：`_get_capability_backend("extract")` 遇到 `extract_backend: cdp-extract` 时总会 fallthrough。但无害——最终 dispatch 通过插件注册表正确解析。

### 如何验证没有真正回退

```python
# 确认实际 dispatch 走的是 cdp-extract
from agent.web_search_registry import get_active_search_provider
p = get_active_search_provider()
print(p.name)  # → "cdp-extract"
```

### SEARXNG_URL 的隐藏来源

`SEARXNG_URL` 可能通过 `hermes config set` 或 `.env` 文件设置在 Hermes 的 config-aware env layer 中，而非单纯在 shell 的 `~/.bashrc` 或 `~/.profile` 里。检查方式：

```bash
# 检查 Hermes config layer
~/hermes/hermes-agent/venv/bin/python3 -c "
from hermes_cli.config import get_env_value
print('SEARXNG_URL:', repr(get_env_value('SEARXNG_URL')))
"

# 对比原始 os.environ
~/hermes/hermes-agent/venv/bin/python3 -c "
import os
print('SEARXNG_URL in os.environ:', repr(os.environ.get('SEARXNG_URL')))
"
```

## 相关文件

- `agent/web_search_registry.py` — provider 解析逻辑（`_resolve()` 函数，`_LEGACY_PREFERENCE` 列表）
- `agent/web_search_provider.py` — WebSearchProvider ABC
- `~/.hermes/plugins/web/cdp_extract/search.py` — multi_search / _search_hermes_backend
- `~/.hermes/plugins/web/cdp_extract/provider.py` — CDPExtractProvider.search() / extract()
