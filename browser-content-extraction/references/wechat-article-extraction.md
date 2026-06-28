# WeChat 公众号文章提取（CAPTCHA 回退方案）

## 问题

微信公众号文章（`mp.weixin.qq.com/s/...`）在通过浏览器（CDP）访问时，
经常触发滑块验证码。标准 web_extract / Readability / Turndown 管道遇阻。

## 核心原理

微信文章的正文内容实际已嵌入在页面的原始 HTML 中，藏在 JavaScript 变量里。
即使面向爬虫的验证页拦截了 browser/cdp，这些变量仍然可用。

## 提取步骤

### 1. 用 curl 获取原始 HTML

```bash
curl -sL -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
  "https://mp.weixin.qq.com/s/7zT5-9WDp8zi4naCC2EmOg"
```

关键点：
- **必须用桌面 Chrome UA**（Mobile UA 或 MicroMessenger UA 可能仍触发验证）
- 不需要 cookie，不需要 referer

### 2. 提取关键字段

从原始 HTML 中搜索以下 JS 变量：

| 变量名 | 用途 |
|---|---|
| `var msg_title = "..."` | 文章标题 |
| `<div id="js_content">...</div>` | 文章正文（在 `<script>` 闭合标签之前） |
| `__biz = "MzUxNjg4NDEzNA=="` | 公众号唯一标识 |
| `mid = "2247534620"` | 消息 ID |
| `sn = "..."` | 防篡改签名 |

### 3. 提取正文内容

正文在 `<div id="js_content" style="visibility: hidden;opacity:0;">` 中，
其结束标签后紧跟一个 `<script>` 标签。Python 提取示例：

```python
import re, html as html_mod

rich_match = re.search(r'id="js_content"[^>]*>(.*?)</div>\s*<script', html, re.DOTALL)
if rich_match:
    content_html = rich_match.group(1)
    text = re.sub(r'<[^>]+>', ' ', content_html)
    text = html_mod.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
```

## 提取文章内提及的 GitHub 仓库

公众号科技号（如"逛逛GitHub"、"GitHubDaily"）的推荐文章末尾会贴出仓库地址。
用正则扫描正文中的 `github.com/.*?` 即可发现仓库名。

### 验证文章说辞：四步交叉验证

当你需要回答"这个仓库是否像文章说的那么好"时，不要只看文章内容——做四步交叉验证：

**① 查 GitHub API 基础数据**

```bash
curl -s -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/{owner}/{repo}"
```

重点关注：`stargazers_count`, `forks_count`, `created_at`, `pushed_at`,
`open_issues_count`, `license.spdx_id`, `topics`, `description`。

注意仓库可能已迁移组织（如 `chopratejas/headroom` → `headroomlabs-ai/headroom`），
curl 的 `-L` 会跟随 301 → 用最终 URL 的组织名查 API。

**② 读 README 验证核心数据**

```bash
curl -sL "https://raw.githubusercontent.com/{owner}/{repo}/main/README.md"
```

对照文章中的 claims 逐条核对：
- 文章说省 60-95% token → README 首行是否对应？
- 文章说 6 种压缩算法 → README 是否列出？
- 文章说可逆 CCR → README 有无专节？

**③ 查版本迭代节奏**

```bash
curl -s "https://api.github.com/repos/{owner}/{repo}/releases?per_page=3"
```

密集发布（10 天 3 个版本）= 活跃维护。长时间无更新 = 可能已停滞。

**④ 综合评估表**

用表格呈现评估结果，每行一个观点，标注 ✅（相符） / ⚠️（部分） / ❌（不符）：

```markdown
| 文章说法 | 仓库实际情况 | 结论 |
|---|---|---|
| "60-95% 省 token" | README 首行即 **60–95% fewer tokens** | ✅ |
| "6 种压缩方案" | ContentRouter + SmartCrusher / CodeCompressor / Kompress-base | ✅ |
| ... | ... | ... |
```

最后给出总体判断（值得关注 / 警惕夸大 / 数据不符）。

## 注意事项

- 正文初始样式为 `visibility: hidden;opacity:0;`，是微信的前端控制，
  不影响提取
- 如果 curl 请求也被 CAPTCHA 拦截，尝试切换不同 UA
- 微信 anti-scraping 按 IP 限频，多次请求后可能被封，建议间隔重试
- 正文中的 `<img>` 标签的 `src` 可能为 `data-src`，需要处理
