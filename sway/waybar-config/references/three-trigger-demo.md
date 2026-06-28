# 三种 waybar 模块触发方式对照（v3，2026-06-24）

实际部署的 ncm 模块配置，包含所有三种触发方式。

## 目录

- `ncm-play` — while 循环 + exec-on-event: false
- `ncm-pl` — while 循环 + exec-on-event: false
- `ncm-like` — exec-on-event: true（默认，一次性，触发"刷新"效果）
- `ncm-status` — signal: 6（daemon 驱动）

## Waybar 配置（v3：全部绝对路径）

取自 `~/.config/waybar/config-top`：

```json
"custom/ncm-play": {
    "exec": "/home/dr/.local/bin/ncm waybar play",
    "exec-on-event": false,
    "on-click": "/home/dr/.local/bin/ncm-player toggle",
    "tooltip": true,
    "tooltip-format": "播放/暂停"
},
"custom/ncm-pl": {
    "exec": "/home/dr/.local/bin/ncm waybar pl",
    "exec-on-event": false,
    "on-click": "/home/dr/.local/bin/ncm-player pl",
    "tooltip": true,
    "tooltip-format": "我的歌单（点击选择）"
},
"custom/ncm-like": {
    "exec": "/home/dr/.local/bin/ncm waybar logged",
    "on-click": "/home/dr/.local/bin/ncm-player like",
    "tooltip": true,
    "tooltip-format": "喜欢/取消喜欢（未登录时隐藏）"
},
"custom/ncm-status": {
    "exec": "/home/dr/.local/bin/ncm waybar status",
    "signal": 6,
    "on-click": "foot -a ncm-login -W 80x24 -H /home/dr/.local/bin/ncm-player login",
    "tooltip": true,
    "tooltip-format": "网易云登录（点击扫码登录）"
}
```

> ⚠️ **exec 必须用绝对路径** — waybar 直接 execve，PATH 不含 `~/.local/bin`。
> 见 `SKILL.md` 的"exec-relative scripts also need absolute internal commands (double-layer PATH)" pitfall。

## ncm-player waybar 子命令（v3：用 $0 递归）

取自 `~/.local/bin/ncm-player`，所有逻辑集中在此。**关键改动**：内部用 `"$0"` 递归到自身（waybar 启动时已用绝对路径调起，`$0` 就是绝对路径）：

```bash
waybar)
    module="${2:-}"
    SELF="$0"   # 关键：waybar 调起时的绝对路径
    case "$module" in
      play)   while true; do "$SELF" state-get play;       sleep 2;  done ;;
      pl)     while true; do "$SELF" state-get pl;          sleep 5;  done ;;
      logged) sleep 0.5; if $NCM_CLI login --check 2>/dev/null | grep -q '"success": true'; then echo '♡'; else echo ''; fi ;;
      status) "$SELF" state-get status_icon ;;
    esac
    ;;
```

> ⚠️ **内部命令也必须用绝对路径或 $0** — waybar 启动的子进程 PATH 同样不含 `~/.local/bin`。
> 原来用 `ncm state-get play`（裸命令）→ exit 127 → 模块空白。
> 改用 `"$SELF" state-get play`（$0 递归到自身）→ 0 延迟。

## daemon 信号发送（v3：10s 慢兜底）

ncm-state-daemon.service 现在只做兜底（10s 一次 `sync_state`）。各控制命令末尾主动调 `sync_state` 才是主驱动（事件驱动，0 延迟）。

```bash
daemon)
    SWAYSOCK=$(cat /tmp/ncm-swaysock 2>/dev/null || true)
    while [ -n "$SWAYSOCK" ] && [ -S "$SWAYSOCK" ]; do
        sync_state   # 兜住 mpv 自然结束/外部停止
        sleep 10
    done
    ;;
```

`sync_state` 内部会写完 state.json 后发 `pkill -RTMIN+6 waybar`，触发 status 模块刷新。

## v2 → v3 变更总结

| 项目 | v2 (2s busy loop) | v3 (event-driven + 10s fallback) |
|------|-------------------|----------------------------------|
| 触发方式 | daemon 主动 2s 轮询 | 命令末尾 `sync_state` + daemon 10s 兜底 |
| toggle→图标延迟 | 0-2s | **0s** |
| ncm-cli calls/小时 | 1860 | **6** |
| login 缓存 TTL | 60s | **3600s**（1h） |
| waybar exec 命令 | 裸命令 `ncm waybar play` | 绝对路径 `/home/dr/.local/bin/ncm waybar play` |
| waybar case 内部 | 裸命令 `ncm state-get play` | `$0` 递归 `"$SELF" state-get play` |

## like 模块命名历史

| 旧名 | 新名 | 原因 |
|------|------|------|
| `ncm waybar like` | `ncm waybar logged` | `logged` 表示"检查登录态"，`like` 是"红心命令"（避免混淆） |
| `custom/ncm-like` waybar 模块 | 同上 | 模块名沿用 `like`（用户识别习惯） |
| `ncm-player like` 命令 | 不变 | 红心动作命令 |

旧名 `like` 在 waybar case 中保留为 alias（兼容老配置）：
```bash
logged|like) sleep 0.5; if $NCM_CLI login --check 2>/dev/null | grep -q '"success": true'; then echo '♡'; else echo ''; fi ;;
```
