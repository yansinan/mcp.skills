# Waybar Tooltip 调试

## 常见问题 & 诊断

### 1. Tooltip 渲染为空（弹出空白框，无内容）

**最常见原因：`&` 未转义。**

Pango 标记中 `&` 是实体引用起始符（如 `&amp;`、`&lt;`、`&gt;`）。
如果 tooltip 文本中出现未转义的 `&`（例如硬编码的 "缓存 & 压缩"），Pango 解析器会将其视为实体的开始，找不到合法实体名后放弃渲染整个文档 → tooltip 弹出来但内容空白。

**修复**：对所有数据内容使用 `html.escape()` 后再拼接 tooltip。

```python
import html
# 错误：
line = f"缓存 & 压缩"           # & 未转义 → tooltip 空
# 正确：
line = f"缓存 {html.escape('&')} 压缩"
# 或对整段文本统一 escape：
lines = ["<b>标题</b>", html.escape(f"值: {api_data}")]
```

数据来源包括：
- API 返回的字段值
- 文件读取内容
- 命令行输出
- 模型名称、状态值等

**不转义 Pango 标记标签**：`<b>`, `<span>`, `</b>`, `</span>` 这些是 Pango 语法，不能 escape。需要将文字内容 escape 后再包在标签里。

```python
# ✅ 正确模式
lines.append(f"  <span color='#888'>{html.escape(label)}:</span> {html.escape(value)}")
```

### 2. Pango 标签不匹配（弹出但内容混乱/空白）

用以下命令检查 tag 平衡：

```python
import json, subprocess, re

out = subprocess.check_output(['python3', '/path/to/script.py'])
d = json.loads(out.decode())
tp = d['tooltip']

for tag_open, tag_close in [('<b>', '</b>'), ('<span', '</span>')]:
    o, c = tp.count(tag_open), tp.count(tag_close)
    print(f'{tag_open}: {o}, {tag_close}: {c}  {"OK" if o == c else "MISMATCH!"}')

bad_amp = re.findall(r'&(?!(amp;|lt;|gt;|quot;|#))', tp)
if bad_amp:
    print(f'WARNING: Unescaped &: {bad_amp[:5]}')
```

### 3. Tooltip 完全不出现（鼠标 hover 无反应）

**检查清单**：

| 检查项 | 排查方法 |
|--------|---------|
| 模块是否在运行 | 看模块 label 是否正常显示 |
| `tooltip: true` 是否配置 | 检查 config-top 中的模块定义 |
| JSON 输出中是否含 `tooltip` 字段 | 手动运行脚本检查输出 |
| `text` 与 `tooltip` 是否相同 | waybar 在两者相同时会用 label 文本代替（`text_ == tooltip_` 分支） |
| 模块是否被邻模块覆盖 | 增大 `#custom-xxx { margin: 2px 8px }` CSS 间距 |
| waybar 进程是否正常 | `pgrep -a waybar` 确认有 config-top 实例 |
| 配置文件 JSON 是否有效 | 见 Pitfalls 节 JSON 验证方法 |

### 4. 模块间距不足导致 hover 被覆盖

```css
#custom-<module-name> {
  margin: 2px 8px;   /* 左右 8px 拉开间距 */
  padding: 0 4px;
}
```

### 5. JSON 输出结构

```json
{
  "text": "  值  ",
  "alt": "ok",
  "class": "ok",
  "tooltip": "Pango 标记内容\n第二行\n第三行"
}
```

- `text` 和 `tooltip` 不同才有效（见检查清单第 4 项）
- `alt` 和 `class` 通常一致，用于 CSS 路由
- 确保 `json.dumps(..., ensure_ascii=False)` 避免中文被强制转义
