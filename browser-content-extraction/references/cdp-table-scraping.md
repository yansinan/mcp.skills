# CDP Table Scraping — SPA Dashboard Structured Data Extraction

> 2026-06-20 — 阿里云百炼控制台（免费额度页面），提取 220 个模型代码（有免费额度）

## 场景

从 SPA 控制台的表格中提取结构化数据（模型列表、配额等），涉及：
- 多标签页（大语言模型 / 视觉模型 / 全模态模型 / 语音模型 / 向量模型）
- 分页每页 100 条，共约 2 页
- 按配额值现场过滤（排除"无免费额度"行）
- 输出为 markdown 文件

## 标准工作流

```
1. browser_navigate(url)          → 打开 SPA 页面
2. browser_snapshot(full=true)     → 确认页面结构、识别 tab/页面元素
3. browser_console(expression)     → 用 JS 提取表格数据（标准模式见下）
4. [如有分页]   JS click paganition → 重复步骤 3
5. [如有其他 tab] JS click tab     → 重复步骤 3-4
6. 汇总去重 → write_file 写为 markdown
```

## 核心工具

**只用 `browser_console` 和 `browser_navigate` / `browser_click`。不要用 `browser_snapshot` 的 accessibility tree 读表格（截断、缺少列数据）。**

- `browser_navigate(url)` — 导航到 SPA 页面
- `browser_console(expression)` — 执行 JS 并获取返回值，**这是主力**
- `browser_click(ref)` — 只在需要点击 tab/页码时使用
- `browser_snapshot` — 仅用于**初步确认页面结构**（识别 tab ref、页码元素 ref）

## JS 提取模式

### 1. 提取表格列数据（最简单）

```javascript
var codes = [...document.querySelectorAll('table tbody tr td:first-child')]
    .map(td => td.textContent.trim());
JSON.stringify({count: codes.length, codes: codes})
```

### 2. 提取多列 + 过滤

```javascript
var rows = [...document.querySelectorAll('table tbody tr')]
    .map(row => {
        let cells = row.querySelectorAll('td');
        return cells.length >= 2
            ? {code: cells[0].textContent.trim(), quota: cells[1].textContent.trim()}
            : null;
    })
    .filter(Boolean);
var withQuota = rows.filter(m => !m.quota.includes('无'));
JSON.stringify({total: rows.length, hasQuota: withQuota.length, codes: withQuota.map(m => m.code)})
```

### 3. 点击页码（Ant Design 分页组件）

```javascript
// Ant Design: li.efm_ant-pagination-item-{N}
document.querySelector('li.efm_ant-pagination-item-1').click()  // 第 1 页
document.querySelector('li.efm_ant-pagination-item-2').click()  // 第 2 页
// 检查当前页码:
[...document.querySelectorAll('li[class*="pagination-item"]')]
    .map(el => ({text: el.textContent.trim(), active: el.className.includes('active')}))
```

### 4. 点击标签页（按文字查找）

```javascript
var tabs = [...document.querySelectorAll('[class*="tab"], [role="tab"]')];
var tab = tabs.find(t => t.textContent.trim() === '视觉模型');
if (tab) tab.click();
```

## 分页检查流程

```javascript
// 提取后检查分页控件
var pages = [...document.querySelectorAll('li[class*="pagination-item"]')]
    .filter(el => /^\d+$/.test(el.textContent.trim()))
    .map(el => el.textContent.trim());
// pages = ["1"] → 只有一页
// pages = ["1", "2"] → 有第二页
```

## 常见坑点

### 1. `var` 重声明报错
Hermes 的 `browser_console` 每次在新的 eval 上下文中执行，但同一个 `expression` 重复调用时如果声明了同名 `var` 会报 `Identifier has already been declared`。

**解决**: 每次换变量名：
```javascript
// 第一次
var c1 = [...]; JSON.stringify(c1)
// 第二次
var c2 = [...]; JSON.stringify(c2)
```

### 2. 页面导航导致 ref 失效
`browser_snapshot` 返回的 ref (`@e111`, `@e213` 等) 在页面重新加载后**完全失效**。SPA 导航虽然是单页，但如果通过导航重新加载也会生成新的 ref。

**解决**: 
- 用 JS 点击（`element.click()`）代替 `browser_click(ref)` 定位 tab/页码
- 只在首次加载后用 `browser_click` 和 `browser_snapshot` 的 ref

### 3. SPA 哈希路由首次加载慢
`#/costing-balance/free-quota?modelType=Text` 这种 hash 路由在 `browser_navigate` 后不一定立即渲染。

**解决**: 导航后先 `browser_snapshot` 确认页面渲染完成，再提取数据。

### 4. 表格行数 ≠ 页面大小
`querySelectorAll('table tbody tr').length` 得到的是真实行数，不要与页面声称的"100 条/页"等值做假设。先查实际行数再做判断。

### 5. 每次 `browser_console` 独立上下文
`browser_console` 每次执行是独立 eval 调用。用 `var` 声明的变量不会跨调用持久化（CDP 的 Runtime.evaluate 默认丢弃全局执行上下文除非 `replMode: true`）。

**解决**: 每次调用都声明变量并 JSON.stringify 输出。

## 数据组装模式

采集完成后，用 Python（`execute_code`）汇总去重：

```python
# 合并多个来源
all_codes = sorted(set(list_a + list_b + list_c))

# 写入 markdown
lines = ["# 模型列表\n"]
for code in all_codes:
    lines.append(f"- {code}")
write_file(path, "\n".join(lines))
```

## 本会话快照

- **目标**: 阿里云百炼控制台 — 免费额度页面
- **Tab**: 大语言模型 (p1=100, p2=33有额度) + 视觉模型 (p1=87有额度)
- **已排除**: 77 个"无免费额度"模型（全在分页第2页或视觉第2页）
- **输出**: 220 个模型代码 → `qwenModelList.md`
- **关键发现**: 阿里百炼的 tab（全模态/语音/向量）可能无数据内容，不必全检查
