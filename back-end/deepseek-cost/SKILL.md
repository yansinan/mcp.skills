---
name: deepseek-cost
description: "DeepSeek API 余额监控和消费分析 — Waybar 状态栏 + Hermes cron 双模式，充值感知，余额不足告警"
version: 1.0.1
author: Hermes Agent
platforms: [linux]
metadata:
  hermes:
    tags: [deepseek, cost, monitoring, waybar, cron, api]
    related_skills: [waybar-config, hermes-agent, hermes-model-config]
---

# DeepSeek 成本采集器

## 概述

充值感知的 DeepSeek API 成本采集器，支持双模式运行。

| 模式 | 参数 | 用途 | 频率 |
|------|------|------|------|
| Waybar | `--waybar` | 状态栏实时显示余额 | 5min |
| Cron（仅余额） | `--balance-only` | 高频采样 | 4h |
| Cron（日报） | `--days N` | 含 insights 的完整分析 | 每天 7:00 |

目录结构：
```
~/.hermes/skills/local/deepseek-cost/
├── SKILL.md
├── scripts/
│   └── collect.py          # 主采集脚本
└── data/
    └── balance_history.json # 自动创建，保留 90 条
```

## 安装

### 1. 配置 API Key

```bash
# 写入 environment.d 供 systemd user services 使用
cat > ~/.config/environment.d/99-deepseek.conf << 'EOF'
DEEPSEEK_API_KEY=sk-xxx...EOF
```

### 2. 验证

```bash
# 模拟 waybar 环境（无 env var）
env -u DEEPSEEK_API_KEY python3 ~/.hermes/skills/local/deepseek-cost/scripts/collect.py --waybar
# → {"text": " ¥12.34", "class": "ok", "tooltip": "...", ...}
```

## Waybar 集成

### config-top

```json
"custom/deepseek-cost": {
  "exec": "python3 /home/dr/.hermes/skills/local/deepseek-cost/scripts/collect.py --waybar",
  "return-type": "json",
  "interval": 300,
  "tooltip": true
}
```

**注意：不要加 `tooltip-format: "{tooltip}"`**（会覆盖 JSON 的 tooltip 字段，某些版本会导致文本消失）。

### CSS

```css
#custom-deepseek-cost            { color: #2d8a4e; }
#custom-deepseek-cost.ok         { color: #2d8a4e; }
#custom-deepseek-cost.warning    { color: #d2691e; font-weight: bold; }
#custom-deepseek-cost.critical   { color: #e05252; font-weight: bold; }
#custom-deepseek-cost.error      { color: #e05252; }
```

## 核心逻辑

### 余额采集 + 历史持久化
- 调 DeepSeek `/user/balance` API，返回 `total_balance`, `granted_balance`, `topped_up_balance`, `is_available`
- 历史存 `data/balance_history.json`，保留 90 条，同分钟同余额自动去重

### 充值检测
- 余额较前条跳涨 ≥ ¥8（每笔 ¥10 ）→ 标记 recharge 事件
- 消费速率分析**仅用充值后区间**，避免充值断点导致虚假高消耗
- 翻倍异常检测（消耗 ≥ 前段 2x + 警报）也在充值后区间内比较

### 状态类映射

| 余额 | class | 行为 |
|------|-------|------|
| ≥ ¥10 | `ok` | 绿色，正常 |
| ¥5 ~ ¥10 | `warning` | 橙色，提示关注 |
| < ¥5 | `critical` | 红色，催充值 |
| API 错误 | `error` | 灰色带 ✗ |

### 容错设计

1. **凭据 fallback**：`_load_api_key()` 先查 `DEEPSEEK_API_KEY` 环境变量 → 拿不到则读 `~/.config/environment.d/99-deepseek.conf` 文件
2. **API 超时/挂掉** → 输出 error class JSON（` ✗`），不抛 traceback，不污染 sway 日志
3. **间隔 < 1h** → 速率标记为「不可靠」，不做耗尽预测

## 凭证传递说明

Waybar 通过 sway `exec_always` 启动，继承的是 **sway 进程的环境**，不是 `systemd --user` 的。所以 `~/.config/environment.d/*.conf` 和 `systemctl --user import-environment` **对 waybar 无效**。

修复：脚本内直接读文件作为 fallback。

```python
def _load_api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key
    env_file = Path.home() / ".config" / "environment.d" / "99-deepseek.conf"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'")
    return ""
```

## 关键陷阱

### 1. tooltip 不显示

Waybar v0.12.0 的 `set_tooltip_markup()` 对 Pango 标记处理不稳定。如果 tooltip 不显示：
- 先去掉所有 `<b>`/`<span>` 标记用纯文本测试——如果纯文本能显示，说明是 Pango 标记问题
- 确认 `"tooltip": true` 在 config 中已设置且 `return-type: json` 正确
- 不要加 `tooltip-format`——这会覆盖 JSON tooltip

### 2. API Key 不继承

waybar 进程下测试：
```bash
env -u DEEPSEEK_API_KEY python3 scripts/collect.py --waybar
# 应返回正常余额，非 error
```

### 3. Insights 解析

`hermes insights` 输出格式可能随版本变化。`parse_insights()` 用正则提取；输出结构大变时需更新模式匹配。

### 4. 数据路径硬编码

`HISTORY_FILE` 为 `skill_dir/data/balance_history.json`。skill 迁移或重建会丢失历史数据。

## 参考文件

- `references/rtk-token-killer.md` — RTK（Rust Token Killer），终端输出压缩工具，与 DeepSeek 成本监控互补：deepseek-cost 管「花了多少」，RTK 管「少花点」。支持 `rtk init --agent hermes` 一键集成。

## Cron 日报示例

全量采集（含 hermes insights token 统计）：
```bash
# 每天 7:00
python3 /path/to/collect.py --days 1
```

仅余额快速采样：
```bash
# 每 4h
python3 /path/to/collect.py --balance-only
```
