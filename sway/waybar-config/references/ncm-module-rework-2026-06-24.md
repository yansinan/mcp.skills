# ncm 模块重构记录（2026-06-24～25）

## 问题清单

| # | 问题 | 根因 | 修复 |
|---|------|------|------|
| 1 | ncm-* 按钮不可见 | 1) `format: "{text}"` 缺失（fmt::arg 冲突）；2) 行缓冲陷阱（`print(..., end='')` 无 `\n`） | `return-type: json` + `format: "{text}"` + `print(json.dumps(...))` |
| 2 | 点击 toggle 没反应（waybar on-click） | `#!/usr/bin/env node` 脚本在 waybar 子进程中找不到 node（PATH 缺 `~/.local/bin`） | `export PATH="$HOME/.local/bin:$PATH"` 在 ncm-player 开头 |
| 3 | ♡ like 始终可见（未在停播时隐藏） | `waybar-like` 直接从 state 读 like 字段，不检查 status | 修改 `waybar-like`：`if d.get('status') in ('playing','paused')` 才输出 ♡，否则输出 `{"text":""}` |
| 4 | mpris 不显示 | mpv-mpris 0.7.1 PlaybackStatus 永远返回 "Stopped" | `format-stopped` 设为跟 `format` 一样强制显示 |
| 5 | sway reload 后 waybar 配置不更新（累计进程） | `exec_always exec waybar` 后 sway 不追踪新进程 | 单条 `exec_always bash -c 'killall -e waybar; sleep 0.3; waybar ... & waybar ... & wait'` |

## 新子命令

在 ncm-player 中添加了以下子命令用于 waybar 集成：

```bash
# 输出 JSON: {"text": "..."}
state-get-json|key="${2:-}"
    [ -z "$key" ] && { echo '{"text":""}'; exit 0; }
    python3 -c "
import json,sys
d=json.load(open('/tmp/ncm-state.json'))
val = d.get('$key', '')
print(json.dumps({'text': val}))
" 2>/dev/null || echo '{"text":""}'

# 连续 exec + JSON 输出（waybar 无 interval 模式）
waybar-play|   while ...; do "$0" state-get-json play;    sleep 2; done ;;
waybar-pl|     while ...; do "$0" state-get-json pl;      sleep 5; done ;;
waybar-like|   while ...; do python3 -c "...status check..." sleep 5; done ;;
```

## 架构原则更新

1. **全局 PATH 修复**：任何被 waybar on-click/exec 调用的脚本头部必须 `export PATH="$HOME/.local/bin:$PATH"`
2. **JSON 输出 > 纯文本**：`return-type: json` 方案更可靠（无 format 冲突、无行缓冲陷阱）
3. **连续 JSON exec**：当需要即时反馈时使用（toggle 按钮），普通显示用 interval + JSON
4. **状态门控**：like 等按钮的输出应根据 status 字段动态变化，而非固定值
