---
name: mpv-waybar-control
description: 部署 mpv 作为 headless MPRIS 音频播放器，配合 waybar 鼠标按钮做控制面板（mpv+waybar 集成层，不含 mpv/mpris/sway/waybar 通用 pitfall）
tags: [sway, waybar, mpv, mpris, music, wayland]
---

# mpv-waybar-control

把 mpv 部署成常驻 headless MPRIS 播放器，waybar 鼠标点控制（不要快捷键）。后端可以是网易云、Spotify、本地文件、任何返回音频 URL 的服务。

## 触发场景

- 用户想用 mpv（不是 Spotify GUI / rhythmbox）当主音频播放器
- 想用 waybar 鼠标点击控制（**不要快捷键**）
- 需要显示当前歌曲/艺术家/喜欢状态
- 资源占用敏感（mpv ~30MB vs GUI 客户端 100MB+）
- 后端是 HTTP API（不是本地文件）

## 架构总览

```text
┌────────────────────────────────────────────────────────────┐
│ 后端 (任何 HTTP API)                                          │
│  - 网易云 / Spotify / Subsonic / 任意返回 mp3 URL 的服务    │
└─────────────────┬──────────────────────────────────────────┘
                  │ HTTP (curl) + 提取音频 URL
                  ▼
┌────────────────────────────────────────────────────────────┐
│ mpv (headless, idle)                                          │
│  --idle=yes --no-video --input-ipc-server=/tmp/mpv.sock     │
│  + 可选: Lua 脚本 (scripts/ncm.lua) 或 bash dispatcher      │
│  + mpris.so (D-Bus 接口)                                       │
└─────────────────┬──────────────────────────────────────────┘
                  │ MPRIS via D-Bus
                  ▼
┌────────────────────────────────────────────────────────────┐
│ waybar (顶部菜单栏)                                              │
│  - mpris 模块: 自动显示 歌名-歌手                              │
│  - custom/* 模块: 鼠标点控制（play/pause/prev/next/like）         │
│  - on-click → 通过 ncm-player (bash) 控制 mpv                  │
└────────────────────────────────────────────────────────────┘
                  │
                  ▼
              用户 (鼠标点)
```

### 两种调度器模式

**Lua 脚本模式**（原始设计）：`ncm.lua` 跑在 mpv 进程内，通过 IPC handler
接收外部命令，通过 `mp.commandv("loadfile", ...)` 直接操作 mpv 播放器。
需要 socat/UNIX socket 发送命令。详见下方 Lua 脚本章节。

**Bash dispatcher 模式**（用户实际采用）：`ncm-player` (bash) 是独立调度器，
通过 `ncm-cli` (npm 包) 发送播放命令 —— `ncm-cli` 内部通过 D-Bus 或 mpv IPC
完成播放控制。waybar 按钮直接调 `ncm-player toggle/next/prev`。
不依赖 `ncm.lua` 脚本，mpv `input-ipc-server` 是 ncm-cli 内部使用。

**注意**：bash dispatcher 模式更简单（不写 Lua），但代价是每次 `ncm-cli`
调用有 ~365ms Node.js 启动开销（详见 Pitfalls）。

## 必须装的包

```bash
sudo apt install -y mpv playerctl mpv-mpris fuzzel qrencode
```

**注意**：
- `mpv-mpris` 是 Debian **单独包**，不在 mpv 里——不装这个就没有 MPRIS D-Bus 接口
- `playerctl` 是 waybar 鼠标控制用的（或者 waybar 自带 libplayerctl）
- `qrencode` 比 `chafa` 渲染终端 QR 码清晰 10 倍（chafa 用于图像，qrencode 用于 QR）→ 安装 qrencode + 详细用法见 `ncm-state-daemon` 技能"登录流程坑点 → 终端 QR 用 qrencode，不要 chafa"

## mpv 配置

`~/.config/mpv/mpv.conf`:

```ini
# Headless 配置（no GUI window）
no-video
no-terminal
quiet
idle=yes
no-osc
no-input-default-bindings
force-window=no
audio-display=no
script-opts=osc-visibility=never,console-visibility=never
```

启动命令：
```bash
mpv --idle=yes --no-video --no-terminal \
    --input-ipc-server=/tmp/ncm-mpv.sock \
    --quiet
```

## mpv Lua 脚本（核心桥接）

`~/.config/mpv/scripts/ncm.lua` 注册 IPC handler，把 HTTP API 调用的结果 loadfile 到 mpv。

**两个核心坑**（详见 Pitfalls 章节）：

```lua
-- 1. 调 curl 必须用 mp.command_native + playback_only="no"
-- 2. 设置 force-media-title 必须用 commandv("set", key, value) 三元素

local r = mp.command_native({
    name = "subprocess",
    args = {"curl", "-sSL", url},
    playback_only = "no",   -- 否则 idle 时被 mpv kill
    capture_stdout = true,
})

mp.commandv("set", "force-media-title", title)  -- 必须是 3 元素数组
```

注册 IPC handler：
```lua
mp.register_script_message("ncm-fm", function() ... end)
mp.register_script_message("ncm-like", function() ... end)
```

外部触发：
```bash
echo '{"command": ["script-message", "ncm-fm"]}' | \
  socat - UNIX-CONNECT:/tmp/ncm-mpv.sock
# 或 Python:
python3 -c "
import socket, json
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect('/tmp/ncm-mpv.sock')
s.sendall(json.dumps({'command': ['script-message', 'ncm-fm']}).encode() + b'\n')
"
```

## waybar 配置片段

放在 `~/.config/waybar/config-top` 的 modules 列表：

```json
"modules-right": [
  "mpris",
  "custom/ncm-prev",
  "custom/ncm-like",
  "custom/ncm-play",
  "custom/ncm-next",
  "custom/ncm-status",
  "custom/ncm-fm",
  "custom/ncm-pl",
  ...
],

"mpris": {
  "format": " {} - {}",
  "format-paused": " {} - {}",
  "player": "mpv",
  "max-length": 22,            // eDP-1 1000px 屏需要
  "ignored-players": ["chromium.instance*"],
  "on-click": "ncm toggle",
  "on-click-middle": "ncm next",
  "on-click-right": "ncm prev"
},

"custom/ncm-play": {
  "format": "{}",
  "exec": "ncm play-button",    // 输出 ▶/⏸
  "interval": 1,
  "on-click": "ncm toggle"
},

"custom/ncm-like": {
  "format": "{}",
  "exec": "ncm like-button",    // 输出 ♥/♡
  "interval": 3,
  "on-click": "ncm like"
}
```

**`exec` 必须用绝对路径** —— waybar exec 不通过 shell，ncm 在 `~/.local/bin` 时找不到。

```json
"exec": "/home/dr/.local/bin/ncm play-button"   // ✓
"exec": "ncm play-button"                       // ✗ 找不到
```

## sway 配置

> sway 启动模式（SWAYSOCK 处理 / waybar-launch.sh / pkill 陷阱 / foot 浮窗）的完整决策已收敛到 `sway-daemon-persistence` 技能的"外部组件启动模式"节。本节仅保留 mpv 特有的 sway 配置（window rules）。

### mpv window rule

mpv 作为视频窗口时需要浮窗 / 全屏规则，waybar on-click 调起 mpv 时常见：

```ini
# ~/.config/sway/config
for_window [app_id="mpv"] floating enable, resize set width 800 height 450
for_window [title="(?i)mpv"] floating enable
```

mpv 默认 `--no-video` 时无窗口，无需规则。

## 验证清单

完成配置后**自己**跑（不要让用户测）：

```bash
# 1. mpv 启动 + Lua 加载 + MPRIS 注册
mpv --idle=yes --no-video --no-terminal --input-ipc-server=/tmp/ncm-mpv.sock -l debug 2>&1 | head -20
# 期望看到: [info] ncm.lua 已加载, [d][mpris] mpris.so 加载

# 2. waybar 启动 + 所有 module 加载
sway --validate       # sway config 无错
SWAYSOCK=/run/user/1000/sway-ipc.1000.$(awk '/comm==sway$/{print $1; exit}' /proc/[0-9]*/comm 2>/dev/null).sock \
  waybar -c config-top -l debug 2>&1 | head -30
# 期望: 无 "Disabling module" / "Unable to connect" / "less than minimum height"

# 3. mpris 工作
playerctl -l | grep mpv
playerctl -p mpv metadata --format '{{ artist }} - {{ title }}'

# 4. IPC 触发
echo '{"command": ["script-message", "ncm-fm"]}' | \
  socat - UNIX-CONNECT:/tmp/ncm-mpv.sock
# 期望: mpv 开始播放
```

## Pitfalls（按严重度排序）

> ⚠️ **Shared pitfalls.** Core mpv/mpris/sway/waybar issues are maintained in canonical skills (`mpv-mpris-media-stack` for mpv+mpris, `sway-daemon-persistence` for sway启动, `waybar-config` for waybar通用, `ncm-state-daemon` for NCM登录). This section only lists items where mpv+waybar integration adds unique context.

### P0: mpv-mpris 0.7 PlaybackStatus 卡 "Stopped"——根本原因

**症状**: mpv 实际在播（IPC playback-time 增长），但 `dbus-send` 查 PlaybackStatus 始终返回 "Stopped"。waybar 一直显示 "mpv-playing" 占位符。

**根源不是 waybar 缓存，是 mpv-mpris 自身不发 "Playing" 信号。**

**原因链**（mpv-mpris 0.7.1 mpris.c 逐行分析）：
1. mpv-mpris 只在 line 1000 观察 `pause` property 来推断 PlaybackStatus（`handle_property_change` line 837-849：pause=1 -> Paused, pause=0 -> Playing）
2. 当 mpv `--idle=yes` 时，**`pause` 已经是 `false`**（idle 只影响 `idle-active`，不影响 `pause`）
3. `loadfile url replace` 后，mpv idle->playing 过渡的过程中，`pause` 从 `false` 变成 `false`——**属性没变** -> 没有 `MPV_EVENT_PROPERTY_CHANGE` -> `handle_property_change("pause")` 不被调用 -> `ud->status` 一直保持 "Stopped"（`set_stopped_status` 在 `MPV_EVENT_IDLE` 时设的）
4. Waybar 收不到 "Playing" 信号，widget 保持 "mpv-playing" 占位符

**mpv-mpris 源码确凿证据**：`mpris.c` line 986 `ud.status = STATUS_STOPPED` 在 `mpv_open_cplugin` 初始化时设置。之后仅 `handle_property_change("pause")`（line 841-849）能改它。`MPV_EVENT_IDLE`（line 932-933）设 "Stopped" 后永不自动改回。

**修法（两路并进）**：
1. **ncm.lua 中 loadfile 后 0.5s/0.6s 强 toggle pause**（因为 idle 时 pause=false，toggle 一次才能触发 PROPERTY_CHANGE）：
   ```lua
   mp.add_timeout(0.5, function() mp.commandv("set", "pause", "yes") end)
   mp.add_timeout(0.6, function() mp.commandv("set", "pause", "no") end)
   ```
2. **waybar mpris 加 `"interval": 0`**（见下一 pitfall 的 waybar 侧根因分析）

**验证**：ncm fm 后 2 秒查 mpris：
```bash
dbus-send --session --print-reply \
  --dest=org.mpris.MediaPlayer2.mpv /org/mpris/MediaPlayer2 \
  org.freedesktop.DBus.Properties.Get \
  string:'org.mpris.MediaPlayer2.Player' \
  string:'PlaybackStatus' | grep variant
# 期望: variant string "Playing"
# 如果还是 "Stopped" -> 检查 mpv-mpris 包是否安装：dpkg -l mpv-mpris | grep '^ii'
```

## 已知不能做的（别试）

- waybar 不支持 per-output modules 配置（不能 eDP-1 显示部分 + DP-5 显示其他）
- sway IPC 用 `i3-ipc` 协议，需要 magic 头（不是 plain JSON）
- foot / kitty 协议直接显示图片（需要用 chafa/qrencode 文本化）
- waybar 隐藏 module（用 `min-length: 0` 不行——module 始终占空间）

## 工作流原则

### mpv/waybar 集成验证命令

改 waybar / sway / mpv config 后必跑：

| 命令 | 验证什么 |
|---|---|
| `sway --validate` | sway config 语法 |
| `waybar -c config-top -l debug` | 模块加载无 error，**检查 GTK widget tree 确认每个 module 实际出现**（不是只看 "no error"）|
| `playerctl -p mpv status` | mpv MPRIS 工作 |
| `cat /proc/<waybar_pid>/environ \| tr '\0' '\n' \| grep SWAYSOCK` | SWAYSOCK 指向当前 sway PID（不是 stale） |
| `dbus-send --session --print-reply --dest=org.mpris.MediaPlayer2.mpv /org/mpris/MediaPlayer2 org.freedesktop.DBus.Properties.Get string:'org.mpris.MediaPlayer2.Player' string:'PlaybackStatus'` | 验证 mpv-mpris PlaybackStatus 是 "Playing" 而非 "Stopped" |

对每个 waybar `on-click` 按钮：在终端跑一遍等效命令确认能工作，**不要第一次测试就丢给用户点击**。

## 相关技能

- `sway-music-client` — 简化版 CLI 控制模式 + 混合后端决策矩阵
- `mpv-mpris-media-stack` — 完整 mpv+MPRIS+waybar 架构参考（含共有 pitfall）
- `sway-daemon-persistence` — systemd --user 持久化 mpv
- `waybar-config` — waybar 配置管理