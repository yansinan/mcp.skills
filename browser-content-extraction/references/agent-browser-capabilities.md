# agent-browser 能力参考

> agent-browser 0.27.0 — Vercel Labs / Anthropic 出品的浏览器自动化 CLI。Hermes `browser_navigate` 底层依赖。
> 安装：`npm install -g agent-browser` → `~/.hermes/node/bin/agent-browser`

## 对 CDP 搜索最关键的提取命令

| 命令 | 用法 | 对搜索管道的价值 |
|---|---|---|
| `get text <selector>` | `get text '#rso'` | **核心** — 返回 accessibility tree 可见文本，不依赖 DOM class 名 |
| `get html <sel>` | 带 selector 时返回 innerHTML | 仅限带 selector 调用 |
| `get title` | `get title` | 页面标题 |
| `get url` | `get url` | 当前 URL |
| `get count <sel>` | `get count h3` | 统计结果数 |
| `snapshot [-u -i -c -d -s --json]` | `snapshot -u` | **核心** — accessibility tree + URL |

## snapshot 的关键：输出格式

⚠️ **`snapshot -u` 输出是 YAML-like 文本树，不是 JSON。** `--json` 标志输出的是平面 ref 映射（`{e1: {name, role}, e2: ...}`），不是树。

⚠️ **`snapshot -u -i`（interactive）会滤掉 StaticText 描述节点**——搜索结果摘要文字不在 interactive 元素内，用 `-i` 后 desc 字段全空。搜索场景不要用 `-i`。

### 文本树中搜索结果的结构

```
- link "site+url display text" [url=https://actual-url.com/]
  └─ heading "Title" [level=3]            ← 标题
- generic
  ├─ StaticText "display url"             ← 显示 URL
  └─ StaticText "description..."          ← 摘要（可能截断或含冗余URL）
```

解析要点：
- `heading [level=3]` 是结果标题
- `link` 节点上的 `url=` 属性**是浏览器原生解析后的绝对 URL**（最精确的 URL 来源）
- `StaticText` 节点取摘要文字（可能有冗，需去噪）

## 浏览器生命周期

| 命令 | 说明 |
|---|---|
| `--cdp <port>` | **连接现有 Chrome 9222**，不启动新进程 |
| `connect <port\|url>` | 等价，更明确 |
| `--session <name>` | **隔离会话**——多次调用间维持状态（`open` → `snapshot` → `close` 跨子进程） |
| `wait <ms>` | 按毫秒等待（简单粗暴） |
| `scroll <dir> [px]` | 可控方向+像素滚动 |
| `close` | 关闭标签页（不关 Chrome 本身） |
| `--profile <name>` | 复用 Chrome 登录状态 |

### 会话模式（关键）

agent-browser 是**有状态 CLI**——每次调用维持同一个浏览器会话。跨子进程用法：

```bash
agent-browser --session mysesh connect ws://127.0.0.1:9222/...
agent-browser --session mysesh open "https://example.com"
agent-browser --session mysesh snapshot -u
agent-browser --session mysesh close
```

必须用 `--session <name>` 才能跨调用状态持久。

## `get text #rso` 输出格式（Google SERP）

### 实际结构（两层块）

```
Web results
完整标题1

站点名1
https://url1.com
·
翻译此页
摘要文字...

完整标题2

站点名2
https://url2.com
·
翻译此页
摘要文字...
```

**关键发现：** 输出分两层——第一个块是 `[段标题 + 完整标题]`，第二个块是 `[站点名 + URL + 摘要]`，由空行分隔。**两者都是同一条结果的组成部分。** 站点名（如"GitHub"、"知乎专栏"）不是单独的搜索结果。

### 常见结构变体

| 变体 | 例子 | 处理 |
|---|---|---|
| 标题长（含`\|`） | `Hermes Agent \| Nous Research` | 完整保留为 title |
| 标题短（仅站点名） | `Speedtest by Ookla` | 即 title |
| 视频/图片卡片 | `YouTube · Tech With Tim` | 混杂在结果中，保留或过滤 |
| 广告块 | — | 不含 `#rso` 内（Google SERP 广告在 `#rso` 外） |
| AI Overview | `AI Overview +11` | 位于 `#rso` 头部，需跳过 |

### Python 解析模式

```python
import re

def parse_get_text_serp(raw: str) -> list[dict]:
    """解析 get text #rso 输出，合并两层块。"""
    blocks = re.split(r"\n\n+", raw)
    merged = []
    skip_titles = {"Web results", "Search Results", "网页搜索结果", ...}

    for block in blocks:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if not lines or lines[0] in skip_titles:
            continue

        # 合并：标题块（无URL） + 站点块（有URL）
        # 第1块: ["Title1", "Title2"] → 用 Title1
        # 第2块: ["SiteName", "http://url", "desc"] → 追加 URL+desc
        if any(l.startswith("http") for l in lines[1:]):
            merged.append({"title": lines[0], "has_url_block": True})
        else:
            # 纯标题块 → 如果上块已有标题，跳过
            if not merged or merged[-1].get("has_url_block"):
                merged.append({"title": lines[0], "has_url_block": False})

    # 过滤出有 URL 的块
    results = []
    for m in merged:
        if m["title"] and m.get("has_url_block"):
            results.append({"title": m["title"]})
    return results
```

## 合并策略教训

snapshot 和 get text 的**标题粒度不一致**：
- snapshot heading[level=3]: 完整标题（`VS Code 1.110 官宣AI 新特性：AI 直接调试浏览器！ - 腾讯云`）
- get text 第一个块: 完整标题（同上）
- get text 第二个块: 站点名（`腾讯云`）——不是完整标题

**合并时不能直接用 title 做 key 匹配**——snapshot 的 title 更长，get text 的第二块只有站点名。可行的策略：
1. **单源**：全部从 snapshot 提取（title + url + desc 都在树里）
2. **按位置匹配**：snapshot 的第 N 条 = get text 的第 N 条（按顺序对齐）
3. **URL 匹配**：snapshot link.url 与 get text 块内的 URL 字符串匹配

推荐方案 1（单源 snapshot）——减少不一致导致的丢结果问题。

## 会话模式注意事项

- **connect + open + snapshot 必须在同一个 session 下**，否则新 session 不知道浏览器已打开
- **多次 `open` 导航**：同一 session 内 `open` 切换到新 URL，不会开新标签页（验证：仅切换，不创建新 tab）
- `close` 关闭当前 tab（若只剩一个 tab，则保持浏览器进程不退出——因为 CDP 是外部进程）
- 不同 session 共享同一个 CDP Chrome 实例（session 仅代理浏览器会话，不是浏览器实例）

## 完整能力清单（2026-06-17 session 验证）

### 核心交互
`open <url>` — 导航
`click/dblclick/hover/focus` — 元素操作
`type/fill/press`, `keyboard type/inserttext` — 输入
`check/uncheck/select/drag/upload/download` — 表单
`scroll <dir> [px]` — 可控滚动
`scrollintoview <sel>` — 滚动到可见
`wait <sel|ms>` / `wait --load networkidle` — 等待
`screenshot/pdf/eval <js>` — 截图/PDF/JS执行

### 内容提取
`get text/html/value/attr/title/url/count/box/styles` — 取页面信息
`snapshot [-i -u -c -d -s "sel" --json]` — access tree

### 浏览器控制
`set viewport/device/geo/offline/headers/credentials/media` — 设置
`--profile/--cdp/--headless/--headed/--user-agent/--proxy` — CLI 选项

### 网络/存储
`network route/unroute/requests/har` — 请求拦截
`cookies get/set/clear` — Cookie
`storage local/session` — Web Storage
`tab new/list/close` — Tab 管理

### 高级
`batch ["cmd"..] [--bail]` — 批量执行
`trace/profiler start/stop` — 性能分析
`record start/stop` — 视频录制
`console/errors` — 日志
`react tree/inspect/renders/suspense` — React 调试
`vitals [url]` — Core Web Vitals
`pushstate <url>` — SPA 导航
`clipboard read/write` — 剪贴板

### AI / Auth
`chat <message>` / `chat` (REPL) — 内置 AI 聊天（需 AI_GATEWAY_API_KEY）
`auth save/login/list/show/delete` — 凭据管理器
`state save/load` — Session 持久化
`diff snapshot/screenshot/url` — 差异对比

### 安装维护
`install / install --with-deps` — 下载浏览器
`upgrade` — 升级
`doctor [--fix]` — 诊断
`profiles` — 列出 Chrome profile

## 测试方法论：保存原始输出

当需要验证 agent-browser 提取效果时：

```bash
OUTDIR="/tmp/agent-browser-test"
mkdir -p "$OUTDIR"

agent-browser --session test connect ws://127.0.0.1:9222/...
agent-browser --session test open "<url>"
agent-browser --session test wait 3000
agent-browser --session test snapshot -u > "$OUTDIR/snapshot.txt"
agent-browser --session test get text '#rso' > "$OUTDIR/results.txt"
agent-browser --session test close

# 用户审阅：让用户看原始文件，不要只贴摘要
```

关键原则：显示原始输出，不要自己总结摘要。用户明确要求"给我看原文"和"我看到文件再决定"。
