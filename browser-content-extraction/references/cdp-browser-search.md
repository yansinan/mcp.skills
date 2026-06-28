# CDP 浏览器搜索 — 实现参考

> 对应 `browser-content-extraction` 技能的「CDP 浏览器搜索」章节。本文件记录 SearXNG 调研结果、搜索引擎 DOM 结构演化、selector 调试过程。

## SearXNG 搜索引擎实现（参考来源）

SearXNG（https://github.com/searxng/searxng）的每个引擎实现为两个函数：

```python
def request(query, params) -> dict:
    """构造 HTTP 请求参数：URL、headers、method、data"""
    params['url'] = search_url.format(query=query, ...)
    return params

def response(resp) -> list:
    """解析 HTTP 响应，lxml XPath 提取结果"""
    dom = html.fromstring(resp.text)
    return [{'url': ..., 'title': ..., 'content': ...}]
```

框架调 `request()` → 发 HTTP → 调 `response()`。

### 各引擎 URL 模板

| 引擎 | URL | 翻页参数 |
|------|-----|----------|
| Google | `https://www.google.com/search?q={query}&hl={lang}&cr={country}` | `start=0, 10, 20...` |
| Bing | `https://www.bing.com/search?q={query}&count=10&mkt={market}` | `first=1, 11, 21...` |
| Baidu | `https://www.baidu.com/s?wd={query}&pn=0,10,20&ie=utf-8` | `pn=0, 10, 20...` |

### 关键局限

SearXNG 用纯 HTTP 请求，搜索引擎全面封锁：
- Google: 社区反映"completely down for months"（GitHub #5651）
- Baidu: 显式 CAPTCHA 检测（`wappass.baidu.com` 重定向）
- Bing: Accept-Language Header 极其敏感

CDP 浏览器搜索用真实 Chrome 149，天然跳过这些封锁。

## Google 搜索结果 DOM 演化

| 时期 | 容器 class | 链接格式 | 备注 |
|------|-----------|----------|------|
| 2024 前 | `div.g` | `/url?q=REAL_URL&sa=...` | 经典结构 |
| 2025 | `div.MjjYud` | **直接 `a.href = REAL_URL`** | 不再用 /url?q= 跳转 |
| 当前 (2026) | `#rso > div.MjjYud` | `a.zReHs` + `a.href` | MjjYud 不带 data-hveid |

**调试命令（CDP Runtime.evaluate）：**
```javascript
// 查看 #rso 的直接子元素
document.querySelector('#rso').children

// 查看含 h3 的 div[data-hveid] 数量
document.querySelectorAll('div[data-hveid]:has(h3)').length

// 查看搜索结果容器的 class
Array.from(document.querySelectorAll('#rso > div'))
     .map(d => d.tagName + '.' + d.className)
```

## CDP 搜索 JS 提取核心代码

```javascript
(() => {
    const containers = document.querySelectorAll('#rso > div');
    const results = [];
    let count = 0;
    for (const el of containers) {
        if (count >= LIMIT) break;
        const titleEl = el.querySelector('h3');
        // URL: 找第一个外部链接（跳过 translate.google 等工具链接）
        let url = '';
        for (const a of el.querySelectorAll('a')) {
            const h = a.href || a.getAttribute?.('href') || '';
            if (h && h.startsWith('http') && !h.includes('translate.google')) {
                url = h; break;
            }
        }
        results.push({
            title: titleEl?.textContent?.trim() || '',
            url: url,
            description: el.querySelector('.VwiC3b, span.st')?.textContent?.trim() || '',
        });
        count++;
    }
    return results;
})()
```

## 已知坑点

1. **`load` 事件不够** — 搜索引擎页面用 JS 懒加载结果，`lifecycleEvent('load')` 只保证初始框架加载完。必须额外等 3s。
2. **CSS selector 易碎** — Google 经常改 DOM 结构。当前用 `#rso > div` 作为默认容器（兼容 MjjYud 和其他 variant），如果变了改 config 无需发版。
3. **Bing 需要 Accept-Language** — 通过 URL 的 `mkt` 参数控制。默认值 `zh-CN` 影响结果语言。
4. **Baidu 用 `wd` 不用 `q`** — URL 参数是 `?wd=搜索词`，不是 `?q=`。已在 config 模板中处理。
5. **`asyncio.run()` 限制** — `search()` 是同步函数，内部用 `asyncio.run(_cdp_search_page(...))`。在已运行的 event loop 中调用会抛 `RuntimeError`。目前 CDP provider 的 `extract()` 是 async，`search()` 是 sync（使用 asyncio.run）。

## Readability 对 SERP 的处理：实测发现

### 默认 Readability 路径（`useReadability: true`）

Google SERP (1.4MB HTML) 输入 → read_down 输出:

| 字段 | 大小 | 结构保留度 |
|------|------|-----------|
| text | ~1.2KB | 低 — 所有结果黏成一段 |
| markdown | ~3.6KB | 低 — _斜体_ 混连，无 h2/h3 分隔 |
| html (article) | ~7.6KB | 中 — Readability 提取的纯净 HTML |

**问题：** Readability 把整个 `#rso` 当成一篇"文章"的正文。输出是连续文本，每个搜索结果的标题、URL、摘要全部混在一起。URL 全部丢失（Readability 不保留 `<a href>`）。

### `useReadability: false` 路径

走 `fallbackHtmlToMarkdown()` — 基于正则的 HTML→Markdown 转换器：

```javascript
// 关键正则规则（read_down/index.js line 56-81）：
.replace(/<h([1-6])[^>]*>([\s\S]*?)<\/h\1>/gi, '\n' + '#'.repeat(n) + ' $2\n')
// → h3 变成 `### 标题`，标题层级保留 ✅

.replace(/<a[^>]*href="([^"]*)"[^>]*>([\s\S]*?)<\/a>/gi, '[$2]($1)')
// → <a href> 变成 `[text](url)`，URL 不丢失 ✅

.replace(/<p[^>]*>([\s\S]*?)<\/p>/gi, '\n$1\n')  // 段落换行
.replace(/<br\s*\/?>/gi, '\n')                      // 换行保留
.replace(/<li[^>]*>([\s\S]*?)<\/li>/gi, '- $1\n')  // 列表项
```

**优势：** 不依赖 Readability 的"文章识别"启发式，直接做格式转换。对列表页（搜索、目录、多条目）保留了每个条目的边界。

### 结论

| 场景 | 推荐模式 | 原因 |
|------|---------|------|
| 文章/博客/文档 | `useReadability: true`（默认） | 自动去导航/广告，提取纯净正文 |
| 搜索结果/列表页 | `useReadability: false` | 保留 h3 层级、URL、列表结构 |
| 未知页面（search + extract fallback） | 先走 true，false 作 fallback | 双路径兜底 |

### `_call_readdown()` options 透传

当前 `provider.py` 的 `_call_readdown()` 只接受 `debug` 参数。搜索场景需要透传 `useReadability`、`extraRemovals`、`skipTurndown` 等选项。

```python
# 当前签名（provider.py line 240）：
def _call_readdown(html: str, url: str = "", debug: bool = False) -> Dict[str, Any]:

# 搜索端绕过的方案：从 search.py 直接调 node 子进程，或扩展签名
payload = {"html": html, "url": url, "options": {"useReadability": False, "debugTrace": False}}
proc = subprocess.run(["node", READ_DOWN_INDEX], input=json.dumps(payload), ...)
```

建议扩展 `_call_readdown` 的签名接受 `**readdown_opts`，不影响现有调用者。

```yaml
# 仅在 DOM 变化时覆盖，保留以下注释字段
selectors:
  container: "#rso > div"      # 默认
  title: "h3"                   # 默认
  link: "a"                     # 默认
  snippet: ".VwiC3b, span.st"   # Google 专用
```
