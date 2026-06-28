# Multi-Engine Search via agent-browser (2026-06-17 实现)

## 架构

```
search(query, limit, pages=N)
  │
  ├→ _init_cdp()                连接本地 CDP Chrome
  │
  ├→ for p in range(pages):     多页循环
  │   ├→ _page_url()            构造引擎 URL（含翻页参数）
  │   ├→ _ab("open", url)       打开搜索页
  │   ├→ _ab("wait", 3000)      等渲染
  │   ├→ _text_results(container)  get text "#rso" → [{site, url, desc}]
  │   └→ _snap_titles()            snapshot -u → [{title, url}]
  │
  ├→ _merge(texts, snaps, seen)  按 URL 文本匹配 + 去重
  │
  └→ return [{title, url, desc}]
```

## 引擎配置

| 引擎 | URL 模板 | container selector | heading level |
|---|---|---|---|
| google | `https://www.google.com/search?q={query}&hl={lang}&start={start}` | `#rso` | 3 |
| bing | `https://www.bing.com/search?q={query}&count={limit}&first={first}` | `#b_results` | 2 |
| duckduckgo | `https://html.duckduckgo.com/html/?q={query}` (HTML 版) | `.results` | — |

## 翻页参数

| 引擎 | 第 1 页 | 第 2 页 | 第 3 页 |
|---|---|---|---|
| google | `&start=0` | `&start=10` | `&start=20` |
| bing | `&first=1` | `&first=11` | `&first=21` |

## URL 匹配算法

```
get text URL:  "https://cloud.tencent.com › developer › article..."
  1. 去掉尾部 "...":  "https://cloud.tencent.com › developer › article"
  2. 直接子串匹配 → 对不上（" › " vs "/"）
  3. " › " 转 "/":  "https://cloud.tencent.com/developer/article"
  4. 检查 snapshot URL 是否以这个开头: ✅

关键: 只去掉 "..."，不去掉 " › "。用户明确纠正过。
```

## 合并关键

1. **title + url** → 来自 snapshot（heading 文本 + link.url 属性）
2. **desc** → 来自 get text（accessibility tree 可见文本，干净无前缀）
3. **去重** → `seen: set[str]` 存已处理的 URL，跨页共享
4. **防同域名干扰** → 匹配到后 `avail.pop(best_idx)`，从 snapshot 候选列表中移除

## get text 的两种结构

### Google 模式
```
完整标题（可能含站点后缀）
(空行)
站点名
https://domain.com › path...（显示 URL，含 › 和 ...）
·
翻译此页
2026年4月20日 — 描述文字...
(空行)
```
解析：站点名+URL+描述 块的标题需要和前面「完整标题」块合并。

### Bing 模式
```
github.com
https://github.com › vercel-labs › agent-browser
GitHub - vercel-labs/agent-browser: Browser automation CLI for …
8 Jun 2026 · Description text...
(空行)
```
解析：首行 = 站点名，二行 = URL，三行 = 完整标题，后续 = 描述。

## DuckDuckGo 特殊处理

主站 `https://duckduckgo.com/` 是 SPA，accessibility tree 没有 heading 结构。
**必须用 HTML 版**：`https://html.duckduckgo.com/html/?q={query}`。

## agent-browser CLI 会话管理

```python
import subprocess

_SESSION = "bsearch"

def _ab(args, timeout=20):
    """每次 subprocess.run，通过 --session 维持同一浏览器上下文。"""
    r = subprocess.run(
        ["agent-browser", "--session", _SESSION] + args,
        capture_output=True, text=True, timeout=timeout,
    )
    return (r.stdout or r.stderr).strip()

# 使用示例
_ab(["connect", ws_url])     # 连 CDP Chrome（状态持久）
_ab(["open", search_url])    # 导航（状态持久）
_ab(["wait", "3000"])        # 等渲染
snap = _ab(["snapshot", "-u"])    # 无障碍树
text = _ab(["get", "text", "#rso"])  # 纯文本
_ab(["close"])               # 关闭 tab
```
