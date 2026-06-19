# Agent-Browser 搜索插件模式

用 `agent-browser` CLI 构建 WebSearchProvider，替代直接 CDP WebSocket 操作。

## 适用场景

- 需要**快速实现搜索功能**，不想处理 CDP 生命周期、事件过滤、消息 ID 追踪
- 搜索引擎 DOM 变化频繁，不想用 querySelectorAll 硬编码 selector
- 需要跨引擎支持（Google/Bing/DuckDuckGo 等）——每个引擎容器/标题级别不同

## 架构

```
agent-browser CLI 双路径：
  open → wait → scroll → 
    ├→ get text "#container"   → 纯文本：{site, url, desc}
    └→ snapshot -u              → 无障碍树：{heading[level=2/3], url}
                                → 合并（按 URL 文本匹配）
                                → [{title, url, desc}]
```

## 关键实现

### 1. 引擎配置

```python
ENGINES = {
    "google":  {"container": "#rso",       "url": "https://..."},
    "bing":    {"container": "#b_results", "url": "https://..."},
    "duckduckgo": {"container": "article",  "url": "https://..."},
}
```

每个引擎三个差异点：

| 差异 | Google | Bing | DuckDuckGo |
|------|--------|------|------------|
| 容器选择器 | `#rso` | `#b_results` | `article` |
| heading 级别 | level=3 | level=2 | level=2 |
| URL 位置 | 链接前面直接跟 heading | 链接在heading同一行的父级 | 链接在 article 内的[1]索引 |
| get text 返回 | 所有结果 | 所有结果 | 首条可见结果 |
| 翻页参数 | `start=0,10,20` | `first=1,11,21` | `s=0,30,60`（仅桌面版） |

### 2. URL 文本匹配（核心算法）

```
get text URL:  "https://cloud.tencent.com › developer › article..."
snapshot URL:  "https://cloud.tencent.com/developer/article/2635432"

匹配流程:
  1. get text URL 去掉尾部 "...": "https://cloud.tencent.com › developer › article"
  2. 直接匹配 snapshot URL → 失败（›  vs  /）
  3. 把 › 转成 /:           "https://cloud.tencent.com/developer/article"
  4. snapshot URL 以它开头 → 匹配成功 ✅
  5. 从 avail 数组移除 → 防止同域名二次匹配
```

**匹配完从 `avail.pop(best_idx)` 移除，避免同域名下多个结果乱配。**

### 3. get text → desc（干净，无前缀 URL）

get text 每块结构：
```
知乎专栏
https://zhuanlan.zhihu.com › ...
2026年4月20日 — AI Agent 不需要知道...
```

解析：找到 `http` 行设为 `found=True`，其后的文本收集为 desc。跳过分隔符/翻译按钮行。

**坑：** get text 不保证每条结果用空行分隔。下一结果的标题可能直接跟在当前 desc 尾部。

### 4. snapshot → title + url（完整标题 + 绝对 URL）

同时捕获 level=2（Bing/DDG）和 level=3（Google）的 heading。

### 5. 合并策略

```python
if texts:
    return _merge(texts, snaps, seen)   # texts 主, snaps 补 URL
else:
    # DDG 场景: texts=0 但 snaps 有数据
    return snaps直接提 title+url (desc留空)
```

## 已知问题

| 问题 | 原因 |
|---|---|
| desc 混入下条 title | get text 输出无空行分隔 |
| DDG desc 为空 | get text "article" 只返回可见内容 |
| title 被截断 | heading 在无障碍树中被截断 |
| 法律声明混入 desc | 搜索引擎底部提示被收 |

## vs 直接 CDP 操作

| 维度 | agent-browser CLI | 直接 CDP WebSocket |
|------|------------------|--------------------|
| 代码量 | ~250 行 | ~400+ 行 |
| 连接管理 | CLI 自动管理 | self-bootstrap SSH tunnel |
| 事件过滤 | 内置 | 自己管理 msg_id |
| DOM 变化 | 几乎免疫（无障碍树） | querySelectorAll 依赖 DOM |
| DDG 支持 | 有限 | 更灵活（自定义 JS 轮询） |
