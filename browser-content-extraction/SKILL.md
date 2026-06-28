---
name: browser-content-extraction
source: https://github.com/yansinan/hermes-sidebar (hermes-sidebar extraction module)
description: "核心架构记录：Readability → Turndown 的网页内容提取管道。双路径（Chrome Extension + CDP）收敛点和架构分离原则。详细实现见 ~/.hermes/plugins/web/cdp_extract/。"
tags: [web-extraction, readability, turndown, cdp, chrome-extension, architecture]
---

# Browser Content Extraction — 架构核心

> 本技能记录**架构原则**和**管道接口**。具体实现（CDP 命令序列、Plugin 结构、Chrome 启动脚本）在 `~/.hermes/plugins/web/cdp_extract/` 插件中，其项目设计文档在 `~/workspace/cdp-extract/docs/`。

## ⚠️ 前置依赖：agent-browser

**配置 browser 工具集（`browser_navigate`/`browser_click`/`browser_type` 等）前，必须先确认 agent-browser 已安装：**

```bash
# 检查（可能 symlink 丢失而 npm cache 仍有包）
ls -la ~/.hermes/node/bin/agent-browser

# 如未安装或 symlink 丢失
npm install -g agent-browser --registry https://registry.npmmirror.com  # 国内镜像加速
```

**坑点：** `agent-browser` 的 npm 包可能已缓存但 `~/.hermes/node/bin/agent-browser` symlink 丢失（被误删或文件系统问题）。此时 `ls ~/.hermes/node/bin/agent-browser` 报错，但 `npm install -g agent-browser` 很快完成（3s，从缓存恢复 symlink）。所以检查时要 `ls -la` 看真实路径，不要只靠 npm list。

关键事实：
- `browser_navigate` 底层走的是 **agent-browser**（Vercel Labs / Anthropic 出品的 npm 包），**不是 Playwright**。
- 安装路径：`npm install -g agent-browser` → `~/.hermes/node/bin/agent-browser`（Hermes 托管 node）。
- 当 `config.yaml` 中配置了 `browser.cdp_url`，agent-browser 以 `--cdp ws://...` 模式直连已有 Chrome，不启动新进程。
- 如果 agent-browser 未安装，Hermes 会 fallback 到 `npx agent-browser`，首次使用触发 npm 下载，可能因 npm 缓存问题失败。
- cdp-extract 插件本身（`web_extract`）**不需要** agent-browser——它直连 Chrome CDP 端口自行控制。但 `browser_navigate` 等标准 browser 工具必须依赖 agent-browser。

## 管道

```
Raw Page DOM
    │
    ▼ 1. GET RAW HTML
    │   浏览器路径:  scripting.executeScript / Runtime.evaluate
    │   →  document.documentElement.outerHTML  ← 字符串
    │
    ▼ 2. Readability（去噪）
    │   new Readability(document).parse()
    │   → { title, html (clean), textContent, byline, ... }
    │   ★ 需要 DOM 实现（Node.js 下用 linkedom，非 jsdom）
    │
    ▼ 3. Turndown（HTML → Markdown）
    │   turndown.turndown(htmlString)  ← 直接吃 HTML 字符串
    │   → markdown
    │   ★ Turndown 有自有 HTML 解析器，不需要 DOM
```

## 两个访问路径 — 收敛点

### Chrome Extension 路径
- 注入：`scripting.executeScript({ files: ["readability.bundle.js"] })`
- 执行：`scripting.executeScript({ func, args })`
- 限制：只能返回 JSON 可序列化值（不能返回 DOM 节点）

### CDP 路径
- 取 HTML：`Runtime.evaluate({ expression: "document.documentElement.outerHTML" })`
- 用 CDP WebSocket（非 REST），消息需按 `id` 过滤
- 页面加载检测：`Page.lifecycleEvent(name="load")`，不是 `frameStoppedLoading`

### 收敛点

**两条路径都产生原始 HTML 字符串**，之后调用统一函数：

```typescript
function extractHtmlToMarkdown(
  html: string,
  baseUrl?: string,
  options?: ExtractOptions
): PageExtractionResult
```

这个函数是纯 JS，没有浏览器 API 依赖。Readability 需要 linkedom（在 Node.js 中），Turndown 直接吃字符串。

## 架构原则：获取层 vs 处理层

```
Caller (Acquisition Layer)              Library (Processing Layer)
─────────────────────────────           ────────────────────────────
browser_navigate(url) +                 extractHtmlToMarkdown(html)
browser_console({ expression:            ↑ 纯函数，无浏览器依赖
  "document.documentElement.outerHTML"})
  ↓
  raw HTML string ──────────────────►
```

| 关注点 | 属于 | 原因 |
|--------|------|------|
| 等待 JS 渲染 | 调用者 | 取 HTML 前需要足够延迟 |
| 无限滚动/懒加载 | 调用者 | 需 scroll 后再取 outerHTML |
| 跨域 iframe | 调用者 | 顶层 outerHTML 不包含 iframe；需 `frame_id` 逐帧获取 |
| SPA 路由变化 | 调用者 | 检测 URL 变化后重新取 HTML |
| 去噪、提取文章 | 处理层 | Readability 处理静态 HTML |
| HTML → Markdown | 处理层 | Turndown 转换 |

**获取层不关心处理细节，处理层不关心页面交互方式。** 这就是拆分的原因。

## 核心接口

```typescript
interface PageExtractionResult {
  text: string;             // Readability 纯文本（总有值）
  markdown?: string;        // Turndown 结果（失败时 undefined）
  html?: string;            // Readability HTML
  title?: string;
  error?: string;           // 'empty-html' | 'readability-error:...'
}

interface ExtractOptions {
  useReadability?: boolean;    // 默认 true
  headingStyle?: 'atx' | 'setext';
  skipTurndown?: boolean;      // 只返回 Readability HTML
  iframeHtmls?: { html: string; label?: string }[];
}
```

## 动态页面获取（调用者侧）

SPA 和 JS 重型页面：

1. 取 HTML 前等渲染完成
2. 对于懒加载内容：**单次 `Runtime.evaluate` 用 async IIFE 滚动到底**，`awaitPromise: true` 能处理 JS macrotask（setTimeout、setInterval）。之前所谓"awaitPromise 不处理 setTimeout"是 CDP receive buffer 污染导致的假象。
3. 滚动策略 vs 逐帧 scroll：前者更简洁（一次 CDP 调用），后者更易调试（多步可见）。

**关键：始终用 `msg.id` 匹配过滤响应**，不要裸调 `ws.recv()` —— 导航后的残留 CDP 事件会污染 buffer。

## `browser_snapshot` ≠ HTML

| | snapshot | outerHTML |
|--|----------|-----------|
| 格式 | 可访问性树 | 完整 DOM |
| 用途 | 交互（click/type）| 提取处理 |
| 大小 | 2-10 KB | 50-500 KB |

snapshot 是 ariaSnapshot，不是 HTML。`web_extract`/`read_down` 吃 outerHTML。

## `_call_readdown(**extra)` — options 透传（2026-06-17）

`_call_readdown()` 新增 `**extra` 参数，透传到 Node.js read_down 的 options：

```python
# 默认（Readability 提取文章）
rd = _call_readdown(html, url=url)

# SERP 搜索（保留 HTML 结构）
rd = _call_readdown(html, url=url, useReadability=False)

# 仅取 Readability HTML，跳过 Turndown
rd = _call_readdown(html, url=url, skipTurndown=True)

# 额外移除广告/视频元素后转 MD
rd = _call_readdown(html, url=url, extraRemovals=[".ad", ".video-section"])
```

这个模式在 `provider.py` 中实现（docstring 更新），不修改提取路径的既有行为。

## CDP 浏览器搜索

cdp-extract 扩展了 `supports_search() = True`，可以通过 CDP Chrome 直接搜索互联网。

### 架构：双路径

```
search(query, limit)
  │
  ├→ 主路径：_fetch_raw_html() → _call_readdown(useReadability=false)
  │    复用完整 CDP 管道（导航 + 滚动 + 懒加载）
  │    read_down 走 fallbackHtmlToMarkdown（保留 h3 / a href）
  │    → markdown + 结构化结果
  │
  └→ Fallback：Page.navigate → lifecycleEvent → Runtime.evaluate(querySelectorAll)
      当主路径异常时启用
      浏览器内 JS DOM 提取
```

### 关键发现：`useReadability: false` 对 SERP 更优

实测（Google SERP, 1.4MB HTML）：

| 维度 | 默认 Readability (`true`) | `useReadability: false` |
|------|--------------------------|------------------------|
| 输出大小 | ~3.6KB markdown | ~30-50KB（保留内容多） |
| `<a href>` → `[text](url)` | ❌ 丢失（混合） | ✅ 保留 |
| `<h3>` 标题 | ❌ 混入正文 | ✅ `### 标题` |
| URL 完整性 | 几乎全丢 | 保留 |
| 适用场景 | 文章提取 | **SERP / 列表页（结构优先）** |

`fallbackHtmlToMarkdown()`（`read_down/index.js` line 56-81）关键正则：
- `<h1-6>` → `#...`, `##...`（标题层级）
- `<a href>` → `[text](url)`（URL 不丢）
- `<li>` → `- text`（列表结构）

### `_scroll_serp()` — 参数化滚动（`browser.py`）

`_scroll_to_bottom()` 写死 80px 步进 + 无限滚到底 + 3s 等待。对 SERP 过度→滚到底触发无关内容→HTML 膨胀 1.4MB。

新建 `cdp_extract/browser.py` 放浏览器通用操作：

```python
async def _scroll_serp(ws, msg_id,
    step_size=0,        # 0 = 不滚动（SERP 默认）
    max_scrolls=2,      # 最多滚 2 次
    lazy_wait_ms=1000,  # 懒加载等待
):
```

`browser.py` 计划涵盖：创建 target、导航、滚动、JS 执行等所有浏览器通用操作。

### Config

```yaml
plugins:
  cdp_extract:
    browser_search:
      enabled: true
      default_engine: google
      lang: zh-CN
      use_readability: false      # SERP 专用：保持结构
      scroll:
        step_size: 0
        max_scrolls: 2
        lazy_wait_ms: 1000
      engines:
        google:
          url: "https://www.google.com/search?q={query}&hl={lang}"
        bing:
          url: "https://www.bing.com/search?q={query}&count={limit}"
```

URL 模板变量：`{query}`（搜索词, URL 编码）、`{lang}`（语言）、`{limit}`（结果数）。

### 与 SearXNG 的关键差异

| 维度 | SearXNG (HTTP) | CDP 浏览器搜索 |
|------|---------------|----------------|
| 请求方式 | HTTP GET（被封） | 真实 Chrome（有 cookies/JS/指纹） |
| 反爬能力 | 差（Google 被封数月） | 强（Google/Bing/Baidu 均不拦截） |
| 结果提取 | Python lxml XPath（DOM 易碎） | 浏览器 querySelectorAll 或 fallbackHtmlToMarkdown（不依赖 DOM） |
| 配置方式 | settings.yml XPath 写死 | Config 驱动 CSS selector（可热改） |

### 关键坑点

1. **`.g` 已过时** — Google 2025+ 改用 `div.MjjYud`。默认 selector `#rso > div` 兼容。
2. **JS 懒加载** — `lifecycleEvent('load')` 后还要 2-3s 渲染实际结果。
3. **反爬优势** — 本机 Chrome + 独立 profile，真实浏览器指纹。
4. **Readability 不适合 SERP** — 把结果合并成一篇"文章"→丢失结构。对 SERP 务必 `useReadability: false`。
5. **不要用 `_call_readdown` 默认参数对 SERP** — 产生 1.4MB→3.6KB 坍缩，URL 全丢。
6. **JS querySelectorAll 易碎** — 用户明确指出"搜索引擎一改 DOM 都白做"。优先用 agent-browser `get text`（accessibility tree，不依赖 DOM class 名）或 Readability 的 fallbackHtmlToMarkdown（基于标签提取而非 DOM class 名）。**
7. **显示原始输出，不要摘要** — 测试时把 `get text #rso`、`snapshot -u` 等命令的原始输出保存到 `/tmp/` 文件让用户审阅，不要只贴你总结的摘要。**
8. **snapshot -u -i 会滤掉 StaticText** — `-i` (interactive only) 过滤掉非交互节点，搜索结果描述在 StaticText 中，会被丢掉。搜索场景用 `snapshot -u` 不要加 `-i`。**
9. **snapshot --json ≠ 树** — `--json` 输出的是平面 ref 映射（`{e1: {name, role}}`），不是树。要树结构用文本模式解析。**
10. **agent-browser 有状态跨进程** — 必须用 `--session <name>` 多次调用才能维持同一浏览器上下文。**

### agent-browser CLI 搜索提取（2026-06-17 经验）

除了纯 CDP WebSocket 路径，还可以直接用 agent-browser CLI 进行搜索提取——更快速，且不依赖 DOM class 名 (依赖 accessibility tree)：

```python
def search_via_agent_browser(query: str) -> list[dict]:
    # 1. 连接存在 Chrome
    subprocess.run(["agent-browser", "--session", "s", "connect", ws_url])
    # 2. 打开搜索页
    subprocess.run(["agent-browser", "--session", "s", "open", search_url])
    # 3. 等渲染
    subprocess.run(["agent-browser", "--session", "s", "wait", "3000"])
    # 4. 两种提取方式：
    snap = subprocess.run(["agent-browser", "--session", "s", "snapshot", "-u"], capture_output=True, text=True)
    text = subprocess.run(["agent-browser", "--session", "s", "get", "text", "#rso"], capture_output=True, text=True)
    # 5. 关闭
    subprocess.run(["agent-browser", "--session", "s", "close"])
    return _merge(_parse_snapshot(snap.stdout), _parse_get_text(text.stdout))
```

**关键参数：**
- `--session <name>` — 跨多次 subprocess 调用维持同一浏览器会话
- 不传 `--cdp` 时用默认 Playwright 浏览器；传 `--cdp 9222` 连接已有 Chrome

### 提取方式对比（SERP Google）

| 方式 | 依赖 | URL 精度 | 描述完整度 | 抗 DOM 变化 |
|---|---|---|---|---|
| snapshot -u 树解析 | accessibility tree | ✅ link.url 绝对路径 | ⚠️ StaticText 可能截断 | ✅ 强 |
| get text "#rso" | accessibility tree 可见文本 | ❌ 隐藏于文本中 | ✅ 完整段落 | ✅ 强 |
| read_down(useReadability=false) | HTML 标签 | ⚠️ JS href | ✅ 完整段落 | ⚠️ 中 |
| eval querySelectorAll | DOM class 名 | ❌ 搜索改结构就碎 | ⚠️ 需额外 JS | ❌ 弱 |

**推荐：** snapshot -u 作为结构化提取主力（title + url），get text 补充描述文字。合并策略见 `references/agent-browser-capabilities.md`。

### 最优算法：三路并行提取 + 按标题融合

对搜索引擎结果页（SERP），不依赖单一提取方式——三路并行，按 `title` 融合：

```
去噪后 DOM (get html "#rso" + extraRemovals)
  │
  ├→ 路径 A: read_down(useReadability=false, extraRemovals=[...])
  │     fallbackHtmlToMarkdown → ###标题 + [URL] + 摘要文本
  │     → 摘要是完整连续文本 ← 描述主力
  │
  ├→ 路径 B: agent-browser snapshot -s "#rso" -u -json
  │     accessibility tree → heading[level=3] + link.url
  │     → URL 是浏览器原生 `link.url` 属性 ← URL 主力
  │
  └→ 路径 C: agent-browser get text "#rso"
       纯文本块 → 空行分隔每条结果
       → 轻量验证、补丁
```

融合策略（merge by title）：
```
  1. 路径 A 输出按 ### 分割 → 每段得 {title, url, desc}
  2. 路径 B 解析 heading[level=3] + link.url → {title, url}
  3. 路径 C 纯文本按空行分割 → {title, desc}
  4. 以路径 A 的(title, desc)为主干
  5. 对每条 A 结果，在路径 B 中找 heading 文本匹配的节点 → 取其 link.url
  6. 路径 C 的 desc 用于交叉验证（择长保留）
  7. 按最终 URL 去重
```

**为什么三路不是过度设计？** 因为每条路径各有所长，互补不重叠：

| 数据项 | 路径 A (read_down) | 路径 B (snapshot) | 路径 C (get text) |
|---|---|---|---|
| 标题 | ✅ `### 标题` 结构明确 | ✅ heading[level=3] 结构明确 | ⚠️ 文本流模糊 |
| URL | ⚠️ 可能 JS href/根域名 | ✅ **浏览器原生 link.url** | ❌ 隐藏 |
| 描述 | ✅ **完整连续文本** | ⚠️ 分散在 StaticText | ✅ 段落文本 |
| 抗 DOM 变化 | ✅ 强（基于标签类型） | ✅ 强（accessibility tree） | ✅ 强 |

**关键：路径 B (snapshot) 的 URL 最纯净，因为浏览器已经把 JS/重定向解析成绝对 URL。路径 A 的 desc 最完整，因为 Readability 的 textContent 是全文。三路都不依赖 DOM class 名。** 这和用户批评的 querySelectorAll 方案有本质区别。

### 去噪链

对 SERP 的完整去噪流程：

```
1. get html "#rso"             → CSS scope: 只取搜索结果容器
2. 传给 read_down 时:
   extraRemovals: [
     ".ad", ".ads", ".advertisement",
     ".video-card", ".video-section",
     "[data-ved*='video']",
     "#related",
     ".sidebar",
     "[role='navigation']",
     "header", "footer",
   ]
3. 如用 Readability: 自动去噪（对文章好，对 SERP 不用）
```

对文章提取的去噪：

```
1. get html "#article,#content,#main,.post,.entry"  (多 selector 回退)
2. read_down(useReadability=true)  → Readability 自动分析主内容区
   + extraRemovals 补充
```

实测数据（Google SERP hermes agent）：
| 处理方式 | 输出大小 | 结构保留 | URL 保留 |
|---|---|---|---|
| 原始 HTML | 1.47MB | ✅ 完整 | ✅ |
| `get html "#rso"` | ~150KB | ✅ 搜索结果范围 | ✅ |
| read_down(useReadability=true) | 4.3KB | ❌ 扁平 | ❌ 丢 |
| **read_down(useReadability=false)** | **27.8KB** | **✅ h3 + URL** | **✅ [text](url)** |
| snapshot -u -json | 28KB | ✅ accessibility tree | ✅ link.url |
| get text "#rso" | 3KB | ⚠️ 空行分割 | ❌ 隐藏 |

### 研究优先的设计方法论

用户明确的工作方式偏好——**先彻底研究所有模块能力，再设计方案，最后才写代码**：

```
1. 列出所有相关模块的全部参数/函数/能力
2. 对每种能力做实测，保存原始输出到 /tmp/ 文件让用户审阅
3. 根据实测数据设计方案（不要先假设再验证）
4. 写具体的技术方案（不是概要描述）
5. 得到确认后才写代码
```

**反例（用户批评过的）：**
- ❌ 跳过研究直接写 JS querySelectorAll → "搜索引擎一改 DOM 都白做"
- ❌ 方案写得模糊不够具体 → "这个设计太粗糙了"
- ❌ 测试输出只给摘要不给原文 → "别给我糊弄"
- ❌ 跳过 read_down 的 useReadability=false → 不知道有保留 URL 的选项

**正例（用户认可的）：**
- ✅ 把 read_down/index.js 完整读了一遍，列出所有 options
- ✅ 把 agent-browser 所有命令和参数列出来
- ✅ 把实测输出存到 /tmp/ 文件（/tmp/rd_default.md, /tmp/rd_raw.md, /tmp/snapshot_full.json）
- ✅ 对比三种提取方式的数据量、结构保留、URL 保留情况

### 代码分离

- `cdp_extract/search.py` — 搜索功能入口，三路并行 + merge by title
- `cdp_extract/browser.py` — 浏览器通用操作（创建 target、导航、参数化滚动、JS 执行）
- `cdp_extract/provider.py` — 提取管道（`_fetch_raw_html`、`_call_readdown(**extra)`），零改动
- `read_down/` — Node.js 模块，完整保留不动

## agent-browser 搜索提取（首选方法）

对于搜索引擎结果页（SERP），**优先用 agent-browser CLI 代替纯 CDP WebSocket 操作**：

### 流程

```bash
# 1. 连现有 Chrome（--cdp 9222）
agent-browser --cdp 9222 open "<search_url>"

# 2. 等网络空闲（比 lifecycleEvent('load') 更精确）
agent-browser --cdp 9222 wait --load networkidle

# 3. 提取搜索结果（accessibility tree，不依赖 DOM class 名）
agent-browser --cdp 9222 get text '#rso'
```

### 三种提取方式对比

| 方式 | 依赖 | 稳定性 | 典型输出大小 |
|------|------|--------|-------------|
| `get text '#rso'` | accessibility tree | ✅ 不依赖 DOM class 名 | ~3KB |
| `snapshot -i -u` | accessibility tree + ref | ✅ 不依赖 DOM class 名 | ~15KB |
| `eval` querySelectorAll | DOM class 名 | ❌ 搜索引擎改结构就碎 | 不确定 |

### 解析 `get text` 输出

输出格式（Google SERP）：空行分隔每条结果，每段含标题行 / 来源行 / URL 行 / 摘要行。

```python
def _parse_get_text_output(text: str) -> list[dict]:
    blocks = text.strip().split('\n\n')
    results = []
    for block in blocks:
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        if not lines:
            continue
        results.append({
            'title': lines[0],       # 第一行 = 标题
            'url': next((l for l in lines if l.startswith('http')), ''),
            'description': lines[-1] if len(lines) > 2 else '',
        })
    return results
```

### 坑点

1. **Chrome 被意外关闭** — `agent-browser close` 可能关掉整个 Chrome（而非仅当前 tab），导致 CDP 端口断开。`_fetch_raw_html` 等后续操作会失败。
2. **agent-browser 可能启动额外 headless Chrome** — `agent-browser open` 不带 `--cdp` 时会启动另一个 headless 实例。务必始终用 `--cdp 9222` 参数。
3. **`get html` 不带 selector 可能返回 73B** — `get html` 的默认行为有问题，远小于 `document.documentElement.outerHTML` 的正常输出。需要用带 selector 的 `get html body` 或 CDP 直连取 HTML。
4. **heading level 各搜索引擎不同** — Google 搜索结果标题在 heading[level=3]，Bing 在 heading[level=2]。解析 snapshot 时要同时匹配两种 level。
5. **DuckDuckGo 主站是 SPA** — `https://duckduckgo.com/` 用 JS 渲染搜索结果，accessibility tree 没有 heading 结构。需用 `https://html.duckduckgo.com/html/`（纯 HTML 版）。
6. **get text 的 URL 包含 ` › ` 分隔符和尾部 `...`** — 匹配 snapshot URL 时：只去掉尾部 `...`，保持 ` › ` 原样。然后试两种匹配：直接子串匹配；把 ` › ` 转 `/` 后匹配。一定要保留 ` › ` 不删。
7. **按 URL 匹配后要从匹配数组移除** — 防止同一域名多条结果互相干扰。匹配找到后 `avail.pop(best_idx)`。

### 合并 snapshot + get text 的实现模式

```python
def search(query: str, limit: int = 5, pages: Optional[int] = None) -> list[dict]:
    # 1. 初始化 CDP
    _init_cdp()

    # 2. 多页循环
    for p in range(num_pages):
        url = _page_url(query, engine, lang, p, limit)

        # 3. 每个页面: open → wait → 双路径提取
        _ab(["open", url], timeout=10)
        _ab(["wait", "3000"], timeout=10)
        texts = _text_results(container)    # get text "#rso"
        snaps = _snap_titles()              # snapshot -u

        # 4. 按 URL 文本匹配
        items = _merge(texts, snaps, seen)
        all_items.extend(items)

def _merge(texts, snaps, seen):
    """按 URL 文本匹配，匹配完从 avail 移除。"""
    avail = list(snaps)
    merged = []

    for t in texts:
        # 去掉尾部 "..." 但保留 " › "
        t_url_clean = t["url"].rstrip(".").strip()

        for idx, s in enumerate(avail):
            su = s["url"]
            # 直接子串匹配
            if t_url_clean in su or su in t_url_clean:
                best, best_idx = s, idx
                break
            # " › " 转 "/" 再试
            tws = t_url_clean.replace(" › ", "/").replace(" ›", "/").replace("› ", "/")
            if tws in su or su[:len(tws)] == tws:
                best, best_idx = s, idx
                break

        if best:
            # snapshot 提供完整 title+URL
            merged.append({"title": best["title"], "url": best["url"], "desc": t["desc"]})
            avail.pop(best_idx)  # 移除已匹配的，防止同域名干扰
        else:
            # 无匹配：用 get text 自己的数据
            merged.append({"title": t["site"], "url": t["url"], "desc": t["desc"]})

    return merged
```

### get text 原始结构（两种模式）

```
Google 模式:
  完整标题（带站点后缀）
  (空行)
  站点名
  URL（截断含 › ...）
  描述文字...
  (空行)

Bing 模式:
  站点名
  URL
  完整标题
  日期 — 描述...
  (空行)
```

解析时按空白行分块，Google 模式需合并「标题块 + 站点名块」，Bing 模式直接用首行作标题。


## SPA 表格数据采集 (added 2026-06-20)

对于 SPA 控制台中**结构化表格数据**（非文章/搜索结果），使用 CDP + `browser_console` 的 JS 提取模式，而非 Readability/Turndown 管道：

- **主力**: `browser_console(expression)` — 直接执行 JS 从 DOM 提取，返回 JSON 数组
- **browser_snapshot**: 仅用于初步识别 page/tab 元素的 ref（之后用 JS click 操作）
- **browser_click**: 只在快速翻页/切 tab 时用，SPA 重加载后 ref 失效→退回到 JS click
- **坑点**: `var` 重声明、ref 失效、哈希路由首次加载慢、`browser_console` 独立上下文
- **参考**: `references/cdp-table-scraping.md`（完整模式 + 本会话快照）

## 参考

- `~/.hermes/plugins/web/cdp_extract/` — 完整运行的 Hermes Provider 插件（代码实现）
  - ⚠ **先决条件：必须先通过 `/browser connect` 安装 agent-browser**（Chrome CDP 实例）
  - 缺失时 Hermes 无声降级为 curl，提取内容不完整
- `references/cdp-scroll-lazy-load.md` — CDP 滚动方案和懒加载策略
- `references/cdp-protocol-detail.md` — CDP 协议细节与 buffer 处理
- `references/cdp-browser-search.md` — CDP 浏览器搜索实现（搜索引擎 URL 模板、DOM 提取、SearXNG 对比）
- `references/agent-browser-capabilities.md` — agent-browser 0.27.0 完整能力清单 + `get text #rso` 提取方法论 + 测试输出保存规范
- `references/agent-browser-chat.md` — agent-browser `chat` 命令架构分析（system prompt 构造、工具接口、上下文管理、Vercel AI Gateway 依赖）
- `references/searxng-fallback-diagnosis.md` — SearXNG 意外回退的诊断路径
- `references/wechat-article-extraction.md` — 微信公众号文章提取（CDP 遇验证码时的 curl + JS 变量回退方案）：检查 config.yaml 的 `web.search_backend` 字段、provider 解析优先级（`_resolve()` 函数逻辑）、中间层回退无害原理、agent-browser 依赖缺失检测、修复命令
