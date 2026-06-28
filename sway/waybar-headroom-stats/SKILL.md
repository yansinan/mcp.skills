---
name: waybar-headroom-stats
description: "Headroom 代理统计 — Waybar 状态栏模块，展示 http://serverhome/litellm/headroom/stats 的使用情况，tooltip 含详细模型/Token/缓存信息"
version: 1.0.0
author: Hermes Agent
platforms: [linux]
metadata:
  hermes:
    tags: [headroom, proxy, waybar, monitoring, serverhome]
    related_skills: [waybar-config, deepseek-cost]
---

# Waybar Headroom 统计模块

## 概述

Waybar top bar 模块，从 `http://serverhome/litellm/headroom/stats` 获取 Headroom 代理统计数据。

| 功能 | 说明 |
|------|------|
| 状态值 | 会话请求次数（`   9  `） |
| Tooltip | 模式、会话详情、按模型分布、Token、延迟、缓存命中率 |
| 刷新间隔 | 60 秒 |
| 错误态 | 连接失败时显示 `   ✗  ` + 红色错误文字 |

## 文件结构

```
~/.local/bin/
└── waybar-headroom-stats.py    # 采集脚本（~3.3KB）
~/.config/waybar/
├── config-top                  # 模块定义 + modules-right 条目
└── style.css                   # 间距样式
```

## 安装

### 1. 脚本

```bash
cp path/to/waybar-headroom-stats.py ~/.local/bin/
```

### 2. Waybar config-top

```json
"custom/headroom": {
  "exec": "python3 /home/dr/.local/bin/waybar-headroom-stats.py",
  "interval": 60,
  "return-type": "json",
  "tooltip": true
}
```

在 `modules-right` 数组中添加 `"custom/headroom"`。

### 3. CSS

```css
#custom-headroom {
  margin: 2px 8px;
  padding: 0 4px;
}
```

## 数据来源

```
GET http://serverhome/litellm/headroom/stats
```

返回 JSON 结构中的关键字段：

| 路径 | 含义 |
|------|------|
| `display_session.requests` | 当前会话请求数（状态值） |
| `display_session.total_input_tokens` | 输入 Token 数 |
| `tokens.output` | 输出 Token 数 |
| `tokens.saved` | 节省 Token 数 |
| `latency.average_ms` | 平均延迟 |
| `prefix_cache.totals.hit_rate` | 缓存命中率 |
| `requests.by_model` | 各模型请求分布 |
| `proxy_inbound.total` | 代理总入站数 |
| `summary.mode` | 运行模式 |
| `cost.total_input_cost_usd` | 总输入成本 |

## 调试

```bash
# 手动运行验证
python3 /home/dr/.local/bin/waybar-headroom-stats.py | python3 -m json.tool
```

Tooltip 调试见 `waybar-config` 技能的 `references/tooltip-debugging.md`（Pango 标记、tag 平衡、hover 覆盖问题排查）。
