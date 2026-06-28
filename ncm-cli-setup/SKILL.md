---
name: ncm-cli-setup
description: "安装和配置网易云音乐 CLI 工具栈（ncm-cli + ncm-player），含 waybar 集成（CSS 状态类路由、登录门控、7 模块字段表）"
---

# 网易云音乐 CLI 工具栈

## 三层架构（当前）

## 后端选型（api-enhanced → ncm-cli 统一）

最初采用 `api-enhanced`（远程 HTTP 服务）获取音频 URL，2026-06-23 后全面替换为本地 ncm-cli。

| 后端 | 类型 | 现状 |
|---|---|---|
| **api-enhanced**（ncm.z-core.cn:3000） | 远程 Node.js HTTP 服务 | ❌ 已下线（502），源码归档 |
| **ncm-go**（Go 二进制 v0.2.1） | 本地编译产物 ~7.8MB | ❌ 废弃（需要 Playwright Chromium，用户不接受额外浏览器） |
| **ncm-cli**（npm `@music163/ncm-cli` v0.1.6） | 本地 Node.js CLI | ✅ **当前唯一使用** — 登录后支持全部功能 |

### 迁移原因

1. `api-enhanced` 部署在 serverhome 的 3000 端口，nginx 反向代理后长期 502 无维护
2. `ncm-go` 登录需 Playwright + Chromium（`ncm driver install --browser`），用户明确拒绝安装额外无头浏览器
3. `ncm-cli` 通过 OAuth 二维码登录后，实际支持全部功能（命令登录门控，见下文）

### ncm-cli 命令门控机制【关键发现】

`ncm-cli v0.1.6` 的 `commands` 输出依赖登录状态：

| 登录前 | 登录后 |
|--------|--------|
| `play/pause/resume/next/prev/state` | + `search song/album/playlist/all` |
| `login/logout/config` | + `song like/dislike/lyric` |
| `volume/queue` | + `recommend daily/heartbeat/fm` |
| `tui/upgrade/commands/diag` | + `user favorite/history/listen-ranking/info` |
| `cloudupload/cloud` | + `playlist collected/radar/create/get/tracks/add/remove` |
| **(约 10 个命令)** | + `album get/collected/tracks` |
| | + `comment list-hot/post/reply` |
| | + `note publish/delete/detail` |
| | + `podcast categories/voices/voiceUpload/voicelistCreate` |
| | **(约 40+ 命令)** |

**判断是否已登录**：`ncm-cli login --check --output json` 返回 `"success": true` 表示已登录，此时所有命令可用。

**判断可用命令**：`ncm-cli commands` 在登录前后输出不同，登录后会自动包含所有数据操作命令。

## 文件布局（部署后）

```
~/.config/mpv/
  mpv.conf                              # 基本配置（无 idle，ncm-cli 按需启动）
~/.config/ncmctl/config                  # api_base 已清空（留空兼容）
~/.local/share/ncmctl/{cookie,state.json}  # 运行时数据（cookie 不再使用）
~/.local/bin/
  ncm                                   # 调度器 symlink → ncm-player
  ncm-cli                               # npm 全局 bin 的 symlink
  ncm-player                            # shell 调度器（daemon/waybar/播放/登录）
  ncm-login                             # Python 扫码登录脚本
  ncm-playlist                          # fuzzel 选歌单脚本
~/.config/systemd/user/
  ncm-state-daemon.service              # daemon 的 systemd 服务
~/.config/sway/config                   # 不再有 exec_always daemon/mpv
~/.config/waybar/config-top             # + 4 个 ncm-* 自定义模块 + mpris（signal 触发，无 interval）
/tmp/ncm-state.json                     # daemon 每 3s 写入，waybar 模块读取
```

**废弃/已删文件**：
- `~/.config/mpv/scripts/ncm.lua` — 持久化 mpv IPC 脚本
- `~/.local/bin/ncm-go` — Go 二进制，需 Playwright，已删除
- `~/.local/share/ncmctl/cookie` — ncm-cli 内部管理 token

`ncm` 是 `ncm-player` 的 symlink（避免与已删除的 Go 二进制混淆）。`ncm-player` 包含 daemon 子命令（systemd 管理）。

```
ncm-player (shell script)      统一调度器 / daemon / waybar 入口
  ├── ncm-cli (npm)            播放控制（仅由 daemon 调用）
  ├── ncm (Go binary)          数据 API（search/playlist/...）
  └── mpv-mpris.so             D-Bus MPRIS → waybar mpris 模块
```

**组件角色**：

| 组件 | 位置 | 作用 |
|---|---|---|
| `ncm` | `~/.local/bin/ncm` (→ `ncm-player`) | 统一调度器：daemon 模式 + waybar 按钮输出 + 播放控制 + 登录 |
| `ncm-cli` | `~/.local/bin/ncm-cli` (→ hermes node) | 全功能引擎：播放/搜索/推荐/红心/歌单（登录后） |
| `ncm-playlist` | `~/.local/bin/ncm-playlist` | fuzzel 选歌单→播放整张歌单 (Python，`ncm-cli play --playlist`)|
| `mpv-mpris` | `/usr/lib/mpv-mpris/mpris.so` (Debian 包) | D-Bus MPRIS 桥接 |

**废弃组件**（已移除）：
- `ncm.lua` — 持久化 mpv IPC 脚本
- `ncm-login` — 合并到 ncm-player
- `api-enhanced` (ncm.z-core.cn) — 外部 Node.js API 服务，已下线
- `ncm-go` (Go 二进制) — 7.8MB，需 Playwright Chromium，已删除
- 持久化 mpv `--idle` 进程 — ncm-cli 按需启动

**关键变化**：`~/.local/bin/ncm` 原为 Go 二进制（v0.2.1），已重命名为 `ncm-go` 后删除。当前 `ncm` 是 `ncm-player` 的 symlink。不要误以为 `ncm` 是 Go 二进制。

**ncm-cli 直接提供 `play/pause/resume/next/prev/seek/stop/volume`**（mpris on-click-middle/right 直接转发 `ncm-cli next/prev`）——无需 IPC 中转。

早期架构有持久化 mpv（`--idle=yes` 常驻后台 + ncm.lua 处理 IPC），2026-06-23 后完全移除。当前 ncm-cli 在 `play` 命令时自动启动 mpv，播放结束后 mpv 自动退出。mpv-mpris 插件通过 Debian 包自动注册：

```bash
playerctl -l
# 应显示: mpv（mpv 正在播放时）
busctl --user list | grep mpris
# 应显示: org.mpris.MediaPlayer2.mpv（mpv 正在播放时）
```

**关键变化**：无 idle mpv → 无 `/tmp/ncm-mpv.sock` 持久 socket → daemon 不再读 mpv IPC，改为读 `ncm-cli state`。

### daemon（systemd 管理，慢兜底 v3，2026-06-24）

**v3 改动**：daemon 从"2s busy loop 主驱动"降级为"10s 慢兜底"。主驱动是各控制命令末尾的 `sync_state` 调用（事件驱动，0 延迟）。

```bash
daemon)
    SWAYSOCK=$(cat /tmp/ncm-swaysock 2>/dev/null || true)
    while [ -n "$SWAYSOCK" ] && [ -S "$SWAYSOCK" ]; do
        sync_state   # 兜底 mpv 自然结束/外部停止
        sleep 10
    done
    systemctl --user stop ncm-state-daemon.service
    ;;
```

完整架构图：
```
sway exec_always → echo "$SWAYSOCK" > /tmp/ncm-swaysock
                → systemctl --user start ncm-state-daemon.service
                        │
                ncm-player daemon (while true, 10s)
                  ├── 从 /tmp/ncm-swaysock 读 SWAYSOCK
                  └── sync_state（兜底）
                        │
        ┌───────────────┴───────────────┐
        │ 写 /tmp/ncm-state.json        │  pkill -RTMIN+6 waybar
        ↓                                ↓
   waybar 各模块读 cache           waybar 收到 signal 刷新
```

**关键差异 vs v2**：
- v2: daemon 是主驱动（每 2s 调 ncm-cli）
- v3: daemon 是慢兜底（10s），主驱动是 sync_state
- v3: login cache TTL 从 60s 改 3600s（1h）
- v3: ncm-cli 调用 ↓ 99.7%（1860/h → 6/h）

**关键细节**：
- 播放状态不调 ncm-cli（由 sync_state 调 ncm-cli 读）
- 登录状态用本地缓存文件 `~/.local/share/ncmctl/.login_cache`，1h 有效期
- 未登录时 daemon 把 `play/like/pl` 写空字符串，waybar 自动隐藏模块

### ♡ like 按钮：视觉反馈 + liked_song_id 追踪（2026-06-24 新增）

用户抱怨 like 按钮\"点了没反应\"——♡ 在 like 前后不变，用户不知道操作是否成功。

**修法**：在 state.json 里追踪 `liked_song_id`。like 成功后写 `liked_song_id = current_encrypted_id`。sync_state 比较两者：

- `current_encrypted_id == liked_song_id` → `like_icon = "❤"`
- 否则 → `like_icon = "♡"`

**like 命令**：在 `$NCM_CLI song like` 成功后，加 Python 块写入 liked_song_id，然后调 sync_state：
```bash
NCM_ENC="$enc_id" python3 -c "
import json, os
try:
    d = json.load(open('/tmp/ncm-state.json'))
    d['liked_song_id'] = os.environ.get('NCM_ENC','')
    json.dump(d, open('/tmp/ncm-state.json','w'))
except: pass
" 2>/dev/null
sync_state
```

**sync_state 计算**：改为读 `current_encrypted_id` 和 `liked_song_id`，比较决定图标。

**sync_state 保留规则**：sync_state 的 Python inline 全量重写 state.json。外部命令维护的字段（`liked_song_id`、`fav_playlist_id`）必须手动保留。每新增一个 state.json 外部字段，同步检查保留逻辑。

```python
# 在 sync_state 的 Python inline 中，dump 之前：
try:
    old = json.load(open('/tmp/ncm-state.json'))
    if 'fav_playlist_id' in old:
        s['fav_playlist_id'] = old['fav_playlist_id']
    if 'liked_song_id' in old:
        s['liked_song_id'] = old['liked_song_id']
except: pass
```

**行为**：\n- 首次 like → ❤ 显示\n- 切歌 → 自动复位 ♡（`current_encrypted_id` 变了）\n- 同首歌再 like → 幂等（ncm-cli song like 可重复调用），图标仍 ❤\n\n**不支持的**：取消红心（ncm-cli 无 dislike 命令）。

### 多源 state 文件 + race condition 修法（v3，2026-06-24）

数据流：
```
heartbeat_play ──┐
                 ├→ /tmp/ncm-current.json   (写最频，0~2s 内最准)
ncm-playlist   ──┘            ↓
                              daemon 10s 兜底 → /tmp/ncm-state.json
                              （也合并 current.json）
                              ↓
                    /tmp/ncm-state.json       (10s 内最准)
                              ↓
              ┌───────────────┼──────────────┐
              ↓               ↓              ↓
        ncm state-get    ncm like     ncm waybar play/pl
        (waybar 用)     (button 用)    (while 循环用)
```

**Like race condition（v3 已修）**：

旧 v2：用户点 toggle 启动新歌后立即点 like，`ncm like` 只读 `/tmp/ncm-state.json`，daemon 下一轮（最多 2s）才合并 current 进来，期间 like 报"未在播放歌曲"。

v3 修法：按"最新到最旧"顺序读，命中即停：

```bash
# ncm like 读当前歌曲 ID（2026-06-24 修复）
enc_id=$(NCM_CUR=/tmp/ncm-current.json NCM_STATE=/tmp/ncm-state.json python3 -c "
import os, json
for p in (os.environ.get('NCM_CUR',''), os.environ.get('NCM_STATE','')):
    try:
        d = json.load(open(p))
        v = d.get('current_encrypted_id', '')
        if v: print(v); break
    except: pass
" 2>/dev/null)
```

**为什么是消费者修而不是生产者**：生产者要"先写 current，再让 daemon 合并"——必须等 daemon 跑完一轮才有 state.json，延迟是 daemon 周期（v3 是 10s）。消费者直接读最新源，0 延迟。

**审计清单**：所有读 state.json 的命令都得考虑"是否有更早的源"：
```bash
grep -nE "state.json|current.json" ~/.local/bin/ncm-player
# 每个读 state.json 的 case 都要问：现在是否有更新的源？
```

### 未登录时只显示 🎵 按钮

daemon 根据 `$logged` 控制每个字段的输出：

| 字段 | 已登录 | 未登录 |
|------|--------|--------|
| `status_icon` | (空, 隐藏) | 🔑 |
| `status_class` | `logged-in` | `logged-out` |
| `play` | 📻/⏹ | (空) |
| `like` | ♡ | (空) |
| `pl` | 🎵 | (空) |

**已删除字段**（2026-06-24）：`prev`、`next`、`fm`（上/下一首和FM合并到播放toggle）。

CSS 样式：
```css
#custom-ncm-status.logged-in  { color: #2d8a4e; }
#custom-ncm-status.logged-out { color: #aaa; }
```

## 安装流程

### 第一步：安装 ncm-cli

```bash
npm install -g @music163/ncm-cli
```

验证：
```bash
ncm-cli --version
# 期望: 0.1.6
```

如果 `ncm-cli: command not found`，建软链：
```bash
ln -sf $(npm root -g)/../bin/ncm-cli ~/.local/bin/ncm-cli
```

### 第二步：安装 mpv + mpv-mpris

```bash
# mpv
sudo apt-get install mpv

# mpv-mpris (D-Bus 桥接)
sudo apt-get install mpv-mpris

# 确认安装路径
ls /usr/lib/mpv-mpris/mpris.so
```

### 第三步：安装 ncm-player 调度器

脚本在 `templates/ncm-player.sh`，部署到 `~/.local/bin/ncm-player` 并 `chmod +x`。

**重要**：
- 脚本内 `NCM_CLI` 必须用**绝对路径** `"$HOME/.local/bin/ncm-cli"`，否则从 foot/waybar 启动时找不到
- `NCM_GO` 同样用绝对路径 `"$HOME/.local/bin/ncm"`

### 第四步：登录

```bash
foot -a ncm-login -W 80x24 -H /home/dr/.local/bin/ncm-player login
```

`-H` 必须加，否则终端在命令结束后立即关闭，用户来不及扫码。
登录脚本内部不用 `notify-send`——所有信息（QR 码、成功/失败）直接打印到终端。

> ❌ **避免使用 `ncm login`**（Playwright 浏览器登录）——会安装独立的 Chromium。

## waybar 集成（daemon 模式）

### sway 配置：不再启动 daemon（由 systemd 管理）

> daemon 已迁移到 `ncm-state-daemon.service`（systemd --user），sway 配置中对应 `exec_always` 已移除。`BindsTo=graphical-session.target` 保证 sway 启动时自动拉起，`swaymsg reload` 不产生新进程。

管理命令：
```bash
systemctl --user status ncm-state-daemon.service   # 查看状态
systemctl --user restart ncm-state-daemon.service   # 重启
journalctl --user -u ncm-state-daemon.service -f    # 看日志
```

sway 配置中保留以下相关行：
```bash
# sway/config
for_window [app_id="ncm-login"] floating enable
for_window [app_id="ncm-login"] resize set 700 400
```

### waybar 模块配置（混合模式：连续 exec + interval，2026-06-24 验证）

**2026-06-24 验证方案**：混合模式。toggle/pl/like 用连续 exec（即时反馈），status/nowplaying 用连续 while。所有模块用 `return-type: json` + `format: "{text}"`（**必须**，否则 label 被 `fmt::format_error` 隐藏）。

#### ⚠️ Waybar 子进程 PATH 修复（重要，2026-06-24 发现）
waybar 的 `g_spawn_command_line_async` 用 `execve` 直接启动进程，不走 shell。子进程的 PATH **不含 `~/.local/bin`**。而 `ncm-cli` 的 shebang 是 `#!/usr/bin/env node`，`node` 装在 `~/.local/bin/node`（Hermes Node），找不到 `node` 时 `ncm-cli` 静默失败（exit 127 被 `2>/dev/null` 吞掉）。终端能跑通但 waybar 点击无响应。

**修复**：所有被 waybar 调用的脚本（`ncm-player`、`ncm-playlist`）顶部加：
```bash
# ncm-player (bash)
export PATH="$HOME/.local/bin:$PATH"
```

```python
# ncm-playlist (Python)
import os
os.environ["PATH"] = os.path.expanduser("~/.local/bin") + ":" + os.environ.get("PATH", "")
```

**验证方法**：
```bash
# 终端正常
/home/dr/.local/bin/ncm-cli state --output json | head -1

# 模拟 waybar PATH（只有 /usr/bin）→ 应失败
env -i PATH=/usr/bin:/bin HOME=$HOME /home/dr/.local/bin/ncm-cli state --output json 2>/dev/null
echo "exit: $?"  # 应为 127（但被 2>/dev/null 隐藏）
```

#### custom/ncm-nowplaying 模块（mpv-mpris bug 的终极修复）

**问题**：mpv-mpris 0.7.1 有 C 源码级 bug，PlaybackStatus 始终返回 "Stopped"。waybar 的 mpris 模块收到 Stopped 后 `skip update`，即使设了 `format-stopped` 也不显示。

**方案**：替换 waybar 内置 mpris 模块为 `custom/ncm-nowplaying`，直接从 `/tmp/ncm-state.json` 读歌曲信息，完全绕过 mpv-mpris D-Bus：

```json
// waybar config
"modules-right": ["custom/ncm-nowplaying", ...],  // 替换 "mpris"
"custom/ncm-nowplaying": {
    "exec": "/home/dr/.local/bin/ncm-player waybar-nowplaying",
    "format": "{text}",
    "return-type": "json",
    "max-length": 36,
    "on-click": "/home/dr/.local/bin/ncm-player toggle",
    "on-click-middle": "/home/dr/.local/bin/ncm-player next",
    "on-click-right": "/home/dr/.local/bin/ncm-player prev",
    "tooltip": true
}
```

tooltip 通过 JSON 的 `tooltip` 字段提供（waybar 自动使用），支持多行歌曲详情（歌曲名/歌手/红心状态/播放状态）。

现在每个模块的 `exec` 均为 `ncm-player waybar-*` 子命令（连续 while 循环输出 JSON）：

```json
"custom/ncm-play": {
    "exec": "ncm waybar play",
    "exec-on-event": false,
    "on-click": "/home/dr/.local/bin/ncm toggle",
},
"custom/ncm-like": {
    "exec": "ncm waybar logged",
    "on-click": "/home/dr/.local/bin/ncm like",
},
"custom/ncm-pl": {
    "exec": "ncm waybar pl",
    "exec-on-event": false,
    "on-click": "/home/dr/.local/bin/ncm pl",
},
"custom/ncm-status": {
    "exec": "ncm waybar status",
    "signal": 6,
    "on-click": "foot -a ncm-login -W 80x24 -H /home/dr/.local/bin/ncm-player login",
},
```

**已删除的模块**（2026-06-24）：`ncm-fm`（合并到播放按钮）、`ncm-prev`、`ncm-next`。对应 CSS 已一并清理。

### mpris 模块空闲时不显示 "mpv"

```json
"mpris": {
    "format-stopped": "",
    ...
}
```

`format-stopped` 设为空字符串，停止时模块隐藏。

**⚠️ 2026-06-24 发现**：空字符串可能导致\"闪一下消失\"——waybar mpris 模块在 mpv stopped→playing 过渡时先显示空字符串（0 高度）再 show/hide。如果 mpris 闪没，改为固定图标：
```json
\"mpris\": { \"format-stopped\": \" ⏸\", ... }
```
这样 mpris 模块始终占据空间，不会闪。

### CSS 状态类路由（play/pause 图标颜色）

JSON `return-type: json` + CSS `class` 字段让 ncm-player 的 Shell 脚本控制图标颜色：

```bash
# 在 ncm-player 脚本中输出 JSON，class 反映播放状态
play-button)
    state=$(python3 -c "import json;print(json.load(open('/tmp/ncm-state.json')).get('status','stopped'))")
    if [ "$state" = "playing" ]; then
        printf '{"text":"⏸","class":"playing"}'
    else
        printf '{"text":"▶","class":"paused"}'
    fi
    ;;
```

Waybar 配置：

```json
"custom/ncm-play": {
    "exec": "/home/dr/.local/bin/ncm-player play-button",
    "interval": 3,
    "return-type": "json",
    "on-click": "/home/dr/.local/bin/ncm-player toggle",
}
```

对应 CSS：

```css
#custom-ncm-play.playing { color: #2d8a4e; font-weight: bold; }
#custom-ncm-play.paused { color: #000000; }
```

### 登录门控模块隐藏（空 exec 返回）

Waybar custom 模块的 `exec` 返回空字符串时，GTK widget 自动不渲染。ncm-player daemon 的 waybar 状态文件用空字符串标记未登录：

```json
"custom/ncm-like": {
    "exec": "python3 -c \"import json;print(json.load(open('/tmp/ncm-state.json')).get('like',''))\"",
    ...
}
```

`like` 字段在未登录时为空字符串 → waybar 不显示该模块。配合 CSS 折叠空间：

### ncm-status 双 CSS class（logged-in / logged-out）

```json
"custom/ncm-status": {
    "exec": "python3 -c \"import json;s=json.load(open('/tmp/ncm-state.json'));print(json.dumps({'text':s.get('status_icon','🎵'),'class':s.get('status_class','logged-out')}))\"",
    "interval": 3,
    "return-type": "json",
    "on-click": "foot -a ncm-login -W 80x24 -H /home/dr/.local/bin/ncm-player login",
}
```

对应 CSS：

```css
#custom-ncm-status.logged-in  { color: #2d8a4e; }
#custom-ncm-status.logged-out { color: #aaa; }
```

### 剩余 4 个模块字段来源表（2026-06-24 更新）

所有模块使用 `return-type: json` + `interval` 或连续 while 循环（统一用 `waybar-*` 子命令输出 JSON）。

| 模块 | JSON 字段来源 | 模式 | 间隔 | 未登录时 |
|------|-------------|------|------|----------|
| ncm-play | `state-get-json play` → `{"text":"📻/⏹"}` | `waybar-play` (连续 while) | 2s | 隐藏（空串）|
| ncm-status | `state-get-json status_icon` → `{"text":"🔑/空"}` | `state-get-json status_icon` (interval) | 30s + signal 6 | 始终显示 🔑 |
| ncm-like | `state-get-json like` → `{"text":"♡"}` | `waybar-like` (连续 while) | 5s | 隐藏 |
| ncm-pl | `state-get-json pl` → `{"text":"📋"}` | `waybar-pl` (连续 while) | 5s | 隐藏 |

**关键变更**（vs 旧表）：
- `ncm waybar play/pl/logged/status` → `ncm-player waybar-play/waybar-pl/waybar-like`（新 while + JSON 模式）
- `state-get-json` 是新子命令：读 `/tmp/ncm-state.json` 输出 `{"text":"..."}` 格式 JSON
- `waybar-*` 子命令封装 while 循环，避免 waybar 配置出现复杂逻辑
- `return-type: json` + `format: "{text}"` 对全部模块是**强制的**（否则 label 被 `fmt::format_error` 隐藏）

**状态隐藏逻辑**：
- 登录后 `status_icon` 为空字符串 → waybar 隐藏该模块（登录按钮无用）
- 停止时 `like` 应输出空串 → 自动隐藏（需通过 daemon 或 waybar-like 检查 status 字段实现）

**已删除**：`ncm-fm`（合并到播放按钮）、`ncm-prev`、`ncm-next`（2026-06-24）。

### 音量图标恢复

`pulseaudio.format-icons` 不要留空字符串。三个数组元素分别对应低/中/高音量：

```json
"format-icons": {
    "default": ["\uf027", "\uf027", "\uf028"],
    "default-muted": ["\uf026", "\uf026", "\uf026"]
}
```

## 性能数据

### 优化历程

| 阶段 | 每日 ncm-cli 调用 | 说明 |
|------|-----------------|------|
| 原始（5 模块独立轮询） | ~150,000 | 每模块独立调 ncm-cli，含 login --check |
| 登录缓存 + 间隔调整 | ~40,000 | check_login 60s TTL，play 1→3s，like 3→30s |
| daemon + 直读 mpv IPC | ~28,800 | 仅 daemon 调 ncm-cli，waybar 模块读文件 |
| daemon login cache 命中 | ~864 | 仅 login --check 每 60s 一次 API 调用 |
| **v3 事件驱动（当前）** | **~144** | 1 login/h + 6 state/h（daemon 10s 兜底）|
| **v3 + fav 缓存（2026-06-24 新增）** | **~142** | 心动模式 fav 列表 ID 缓存到 state.json，第一次 sync_state 2s 拉取，之后 0 延迟 |

### 连续队列播放：heartbeat_play 入列全部推荐（2026-06-24 新增）

**问题**：`heartbeat_play` 原实现只播推荐列表的**第一首歌**，播完即止。用户预期点了 📻 后连续播放。

**方案**：利用 ncm-cli 的 `queue` 系统——推荐 40 首，播第一首，其余 39 首通过 `ncm-cli queue add` 入列。ncm-cli daemon 自动在每首播完后加载队列下一首。

```bash
heartbeat_play() {
  local fav
  # ... 获取 fav 歌单 ID ...

  # 获取 40 首推荐
  local result
  result=$($NCM_CLI recommend heartbeat --playlistId "$fav" --type fromPlayAll --count 40 --output json 2>/dev/null) || return 1

  # 解析全部 40 首（保留第一首即时播，其余入列）
  local all_songs
  all_songs=$(echo "$result" | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    items = d.get('data',[])
    if isinstance(items, dict):
        for v in items.values():
            if isinstance(v, list): items = v; break
    if not isinstance(items, list): items = [items]
    for s in items[:40]:
        eid = s.get('id','')
        oid = s.get('originalId','') or eid
        nm = s.get('name','未知')
        arts = '/'.join(a.get('name','') for a in (s.get('artists') or s.get('ar') or []))
        print(f'{eid}|{oid}|{nm}|{arts}')
except: pass
" 2>/dev/null) || true

  # 第一首信息
  IFS='|' read -r enc_id orig_id name artists <<< "$(echo "$all_songs" | head -1)" || true
  [ -z "$enc_id" ] && { echo "心动模式暂无推荐" >&2; return 1; }

  # 播第一首
  $NCM_CLI play --song --encrypted-id "$enc_id" --original-id "$orig_id" --output json >/dev/null 2>&1 || return 1

  # 后台入列剩余歌曲（sleep 2 等 daemon 就绪）
  ( sleep 2
    echo "$all_songs" | tail -n +2 | while IFS='|' read -r e o n a; do
      [ -n "$e" ] && $NCM_CLI queue add --encrypted-id "$e" --original-id "$o" >/dev/null 2>&1
    done
  ) &
  # ... set_current_song, sync_state, mpv_set_title ...
}
```

**关键**：
- `ncm-cli queue add` 将歌曲逐个添加到 daemon 维护的队列 → daemon 播完当前后自动切下一首
- `( sleep 2; ... ) &` 后台执行（播放不阻塞），2s 延迟防止 daemon 正在处理 play 命令时冲突
- 不支持 `&` 并行入列（daemon 有写锁，并行冲突会导致只入 1 首）
- `queueLength` 反映了队列深度，可在 ncm-cli state 或 queue.json 中查看
- **ncm-cli daemon 必须存活**（PID file 在 `~/.config/ncm-cli/daemon.pid`），否则 queue 不生效
- `queue.json` 路径：`~/.config/ncm-cli/queue.json`，格式为 `{items:[...], currentIndex: N, mode: "sequential"}`

**失败模式**：queue clear 后 daemon 可能清空内存队列；直接写 queue.json 无效（daemon 覆盖）。必须通过 `ncm-cli queue add` API 操作。

### fav 缓存：心动模式列表 ID（2026-06-24 新增）

**动机**：用户点 📻（ncm-play/toggle）从 stopped → heartbeat_play 时，每次都要调 `$NCM_CLI user favorite --output json` 拿红心歌单 ID（约 2s 网络延迟）。列表 ID 几乎不变，没必要每次拉。

**方案**：把 `fav_playlist_id` 缓存到 `/tmp/ncm-state.json`，由 `sync_state()` 在已登录 + 缓存为空时前台拉一次（一次性 2s），后续 `heartbeat_play` 直接读缓存。

**ncm-player helper 函数**：

```bash
# 读缓存
get_cached_fav() {
  python3 -c "
import json
try: print(json.load(open('/tmp/ncm-state.json')).get('fav_playlist_id',''))
except: pass
" 2>/dev/null
}

# 写缓存
set_cached_fav() {
  local fav="$1"
  python3 -c "
import json
try:
    d = json.load(open('/tmp/ncm-state.json'))
    d['fav_playlist_id'] = '$fav'
    json.dump(d, open('/tmp/ncm-state.json','w'))
except: pass
" 2>/dev/null
}
```

**sync_state 中（前台一次，~2s）**：

```bash
sync_state() {
  # ... 现有逻辑：读 ncm-cli state、login、计算 icons、写 state.json ...
  
  # 5. 如果 fav 未缓存且已登录，前台获取一次
  if [ "$logged" = "true" ] && [ -z "$(get_cached_fav)" ]; then
    fav=$($NCM_CLI user favorite --output json 2>/dev/null | python3 -c "
import json,sys
try: d=json.load(sys.stdin); print(d.get('data',{}).get('id',''))
except: pass
" 2>/dev/null)
    [ -n "$fav" ] && set_cached_fav "$fav"
  fi
}
```

**heartbeat_play 中（用缓存）**：

```bash
heartbeat_play() {
  local fav
  fav=$(get_cached_fav)   # 直接读 state.json，0 延迟
  if [ -z "$fav" ]; then   # 兜底：首次或缓存未命中
    fav=$($NCM_CLI user favorite --output json 2>/dev/null | python3 -c "
import json,sys
try: d=json.load(sys.stdin); print(d.get('data',{}).get('id',''))
except: pass
" 2>/dev/null)
    [ -z "$fav" ] && { echo "获取红心歌单失败" >&2; return 1; }
    set_cached_fav "$fav"
  fi
  # ... 后续 recommend heartbeat 用 $fav ...
}
```

**性能验证**（实测 2026-06-24）：
```
sync_state #1（清空 fav）:  2.382s  ← 拉 fav
sync_state #2（已缓存）:  0.801s  ← 0 延迟
toggle （用缓存 fav）:    5.4s    ← ncm-cli recommend/play 仍然 ~5s
```

**节省时间**：toggle 的 ncm-cli 调用从 2 次（fav + recommend）降到 1 次（只 recommend）。首次 sync_state 多 2s 拉 fav，后续状态切换快 2s。

**注意**`：`不要用后台 `&` 异步拉 fav，否则会跟 sync_state 写 state.json 撞 race condition（后台写完被 sync_state 覆盖）。前台 fetch 简单且无 race。  
**注意**：sync_state 的 Python inline 是全量重写——必须保留 `fav_playlist_id`（以及 `liked_song_id` 等其他外部字段）的保留逻辑。见 #4 节代码。

**通用模式**：缓存"很少变化、调用昂贵"的 ncm-cli 数据到 state.json。其它候选：用户信息（`ncm-cli user info`）、红心总数（`ncm-cli user favorite --output json` 长度）等——按需添加。

### v3 架构（事件驱动 + 慢兜底，2026-06-24）

```
播放控制命令（toggle/next/prev/heartbeat_play/ncm-playlist）
  │
  ├─→ ncm-cli 做动作
  ├─→ sync_state 读 ncm-cli state，写 /tmp/ncm-state.json，发 signal
  │
  └─→ waybar 立即看到新状态（0 延迟）

daemon（systemd --user，10s 慢轮询）
  │
  └─→ sync_state 兜底（处理 mpv 自然结束/外部停止）
```

### 阶段 2 架构（daemon + 共享状态文件）

消除所有 waybar→ncm-cli 调用。一个后台 daemon 集中调 ncm-cli（仅 1 次/3s），写入 `/tmp/ncm-state.json`。所有 waybar 模块转读本地文件（微秒级，零子进程）。

```text
sway ─┬─ exec_always mpv (守护进程)
      │          │
      │          └── /tmp/ncm-mpv.sock (IPC Unix socket)
      │
      ├─ exec_always ncm-player daemon (守护进程)
      │          │
      │          ├── 读 mpv IPC socket → idle/pause → 推导播放状态
      │          ├── 读登录缓存 (60s TTL) → 登录状态
      │          └── 写入 /tmp/ncm-state.json (每 3s)
      │
      └─ waybar ─┬─ mpris 模块 (D-Bus event, 显示歌名)
                 │
                 └─ ncm-* 模块 → 读 /tmp/ncm-state.json (零 ncm-cli)
```

daemon 模式的关键代码在 `ncm-player` 脚本的 `daemon` case 中。完整实现记录见 `ncm-state-daemon` 技能 `references/ncm-state-daemon.md`。

**注意**：sway `exec_always` 中 `nohup` 必须加 —— `bash -c 'cmd &'` 退出时子进程被 kill。正确写法：

```bash
exec_always bash -c 'sleep 1; nohup /home/dr/.local/bin/ncm-player daemon >/dev/null 2>&1 &'
```

### 登录缓存实现

```bash
LOGIN_CACHE="$STATE_DIR/.login_cache"

check_login() {
  cached_login() {
    [ -f "$LOGIN_CACHE" ] && [ $(( $(date +%s) - $(stat -c %Y "$LOGIN_CACHE") )) -lt 60 ]
  }
  if cached_login; then return 0; fi
  if $NCM_CLI login --check 2>&1 | grep -q '"success": true'; then
    touch "$LOGIN_CACHE"; return 0
  else
    rm -f "$LOGIN_CACHE"; return 1
  fi
}
```

## 常见陷阱

### ⚠️ 不要安装不必要的系统包
用终端输出就能完成的事，不要安装 `notify-send` / `libnotify-bin` / `fnott` / `mako` / `dunst`。登录流程全程在 foot 终端显示（QR 码 + 进度 + 结果），不需要桌面通知弹窗。误装了立即 `sudo apt-get remove --purge` 清理。

### ⚠️ Bash + `python3 -c` heredoc 字符串注入（实测 2026-06-24）

在 bash 里嵌入 `python3 -c "..."` 处理动态字符串时，**单引号会炸 python 解析器**：

```bash
# ❌ 错误：标题含 'Don't Stop Me' → python 解析失败（单引号提前关闭 bash heredoc）
python3 -c "
import json
d = {'title': '$title'}
json.dump(d, open('/tmp/x','w'))
"

# ✅ 正确：环境变量传值，完全免疫
NCM_TITLE="$title" python3 -c "
import os, json
d = {'title': os.environ.get('NCM_TITLE', '')}
json.dump(d, open('/tmp/x','w'))
"
```

**触发场景**（实测）：
- 英文歌名："It's My Life", "Don't Stop Me Now", "Queen's Best" — 含 `'` 直接崩
- 用户名、艺术家、专辑名同理
- 双引号嵌套、单引号、双引号混用都可能炸

**通用规则**（所有 `python3 -c "..."` 嵌入 bash 脚本的代码都适用）：
1. **动态值全用环境变量传**：`VAR="$var" python3 -c "import os; v=os.environ['VAR']"`
2. **静态 shell 部分用单引号包**：`python3 -c 'import json, sys; ...'`（避免 bash 插值）
3. **复杂 Python 逻辑提到外部 .py 文件**（最稳），ncm-player 里的 `python3 -c` 块只在简单解析时用

**已知存量 bug**（2026-06-24 已修）：
- `mpv_set_title`：标题含 `'` 时 mpv IPC 调用失败，silent fail
- `set_current_song`：同样问题，写 `/tmp/ncm-current.json` 失败导致 like 命令读不到 ID

**审计清单**（每次改 ncm-player 必查）：
```bash
grep -n "python3 -c" ~/.local/bin/ncm-player
# 每一行都得过：动态值是否在 '$...' 位置？→ 改用环境变量
```

### ⚠️ 登录流程子进程必须 trap 清理

`ncm-cli login --background` 会启动一个**持久的 ncm-cli 子进程**（OAuth 轮询）。如果用户 Ctrl-C 退出登录循环、ncm-cli 临时失败、QR 解析失败等任一退出路径都会留下孤儿进程。

**修法**：定义一个 `cleanup_login` 函数覆盖所有退出路径：

```bash
login)
    cleanup_login() {
        pkill -f 'ncm-cli.*login' 2>/dev/null || true  # 杀残留子进程
        rm -f "$STATE_DIR/qr.png"                       # 删二维码文件
    }
    trap 'cleanup_login; exit 1' INT TERM                # Ctrl-C / TERM
    ...
    # 每个 exit 1/0 之前都调 cleanup_login
    $NCM_CLI login --background ... || { cleanup_login; exit 1; }
    ...
    check_login && { echo "登录成功 ✓"; cleanup_login; exit 0; }
    cleanup_login  # 登录超时收尾
    ;;
```

**审计清单**：所有带 `exit` 的退出路径都得调 `cleanup_login`：
```bash
grep -n "exit " ~/.local/bin/ncm-player | grep -A0 -B0 -E "login|trap"
# 应能看到每个 exit 前都有 cleanup_login
```

### ⚠️ `NCM_CLI` 必须用绝对路径（避免 environment PATH 失效）

`ncm-player` 脚本内的 `NCM_CLI` 变量必须写绝对路径：

```bash
NCM_CLI="$HOME/.local/bin/ncm-cli"   # ✅ 正确
NCM_CLI="ncm-cli"                     # ❌ 错误——waybar/foot 环境 PATH 可能不含 ~/.local/bin
```

同样，`ncm-playlist` 中所有 `subprocess.run(["ncm-cli", ...])` 调用必须改为 `os.path.expanduser("~/.local/bin/ncm-cli")`。

**原因**：waybar 通过 D-Bus activation 启动进程，PATH 只有 `/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`，不含 `~/.local/bin`。foot 终端同理。省得你一个一个查 PATH。

### 安装流程

#### 第一步：安装 ncm-cli

```bash
npm install -g @music163/ncm-cli
ln -sf $(npm root -g)/../bin/ncm-cli ~/.local/bin/ncm-cli
```

**用户常见误解**：看到"二维码"误以为跟 api-enhanced 一样是手机扫码，触发 24h 频率限制。

**实际**：ncm-cli 使用**网易云音乐开放平台的 OAuth**（`/openapi/music/basic/user/oauth2/qrcodekey/get/v2`），生成的是**网页短链接**（`https://163cn.tv/...`），手机或电脑浏览器打开后完成网易云账号授权。**不受 api-enhanced 手机 QR 扫码频率限制**。这也是 ncm-cli 相比 api-enhanced 的核心优势——扫码失败次数不扣。

`ncm-cli login --background` 输出的是 `clickableUrl`（可点击链接），不是手机扫码用的 QR 码图片：

```json
{
  "success": true,
  "clickableUrl": "https://163cn.tv/9Egh7iB",
  "message": "后台轮询已启动，请点击链接登录"
}
```

### ⚠️ ncm-cli login --background 在后台进程中需要 PATH（Hermes Node 特定）

如果 ncm-cli 安装在 Hermes Agent 自带的 Node.js 下（`/home/dr/.hermes/node/bin/`），从 `terminal(background=true)` 启动 `ncm-cli login --background` 会失败报 `ncm-cli: command not found` 或 `env: node: No such file or directory`——因为后台 shell 的 PATH 不包含 Hermes Node。

**修法**：始终使用绝对路径 + 显示设置 PATH：
```bash
PATH="/home/dr/.hermes/node/bin:$PATH" ncm-cli login --background
# 或直接调完整路径
/home/dr/.hermes/node/bin/node /home/dr/.hermes/node/lib/node_modules/@music163/ncm-cli/dist/index.js login --background
```

**检查 `ncm-cli` 实际路径**：
```bash
head -1 ~/.local/bin/ncm-cli
# 如果是 Hermes Node：#!/usr/bin/env node
# 此时 PATH 需要包含 /home/dr/.hermes/node/bin
```

此问题也影响 waybar `on-click` 调用——waybar 直接 `execve`，不走 shell，PATH 同受限。所有 ncm-* 模块的 `exec`/`on-click` 必须用绝对路径。已将 `~/.local/bin/ncm-cli` 建软链到 Hermes Node 版本即可（该 `ncm-cli` 是 Hermes Node 的 symlink，走正确解释器）。

### ⚠️ foot 登录终端必须加 -H
`foot -H`（hold）让终端在命令结束后保持打开。不加的话 QR 码一闪而逝。

### ⚠️ sway exec_always 不要用 pkill -f 匹配自身

> 详细解释见 `sway-daemon-persistence` 技能的"外部组件启动模式 → sway exec_always 不要用 pkill -f 匹配自身"。一句话总结：sway reload 时自动 SIGTERM 旧的 exec_always 进程组，不需要手动清理。

### ⚠️ 脚本内 notify-send 是多余的
waybar on-click 打开的 foot 终端已经能显示所有信息。不要用 `notify-send` 发桌面通知——既增加对通知守护进程的依赖，也在终端场景下毫无意义。需要错误输出时用 `echo "消息" >&2`。

### ⚠️ systemd 服务管理取代手动启动/exec_always

daemon 通过 `systemctl --user` 管理，不要手动 `terminal(background=true)` 启动 daemon——会产生不受控制的孤儿进程。也无需在 sway `exec_always` 中启动（系统已移除）。

**调试**：如果 waybar 按钮突然消失，检查：
```bash
systemctl --user is-active ncm-state-daemon.service
systemctl --user status ncm-state-daemon.service
cat /tmp/ncm-state.json
```

如果 state 文件缺失或过时：
```bash
systemctl --user restart ncm-state-daemon.service
sleep 3
cat /tmp/ncm-state.json
```

### ⚠️ daemon trap 不能删除 state 文件

daemon 的 `trap` 处理器中不要 `rm -f /tmp/ncm-state.json`。state 文件是所有 waybar 模块的输入源，daemon 退出后应保留上次的状态数据。删除后 waybar 模块读取失败，所有按钮同时消失。

正确做法：
```bash
trap 'exit 0' TERM INT   # 只退出，不清理文件
```

### ⚠️ daemon 脚本必须脱敏 set -e（pipefail 吞掉静默失败）

`ncm-player` 脚本顶部有 `set -euo pipefail`。在 daemon 模式下，**任意一条子命令失败都会让整个 daemon 无声退出**（没有日志、没有报错），waybar 所有 ncm-* 模块同时变空。

典型触发场景：
- mpv IPC socket `/tmp/ncm-mpv.sock` 在 mpv 重启间隙不存在 → `socket.connect()` 抛异常 → `set -e` 退出 daemon
- `ncm-cli login --check` 因网络问题短暂失败 → pipe 检测失败 → `set -e` 退出
- `cat /tmp/ncm-state.json` 文件不存在 → python3 open() 报错 → `set -e` 退出
- `pkill -f "ncm.*daemon"` 匹配到多个进程时 kill 掉自身的子 shell → daemon 死亡

**解决方案（已实现）**：
1. 所有可能失败的命令用 `|| true` 或 `|| state="fallback"` 包裹
2. mpv socket 读取用 `try/except Exception` 包裹，catch 后设 `state=stopped`
3. python3 json 写入用 `2>/dev/null || true` 兜底
4. `check_login()` 的 `$NCM_CLI login --check | grep` 管道在 login 短暂失败时不会触发 `set -e`（因为 `if` 语句中的 pipe 不受 `set -e` 影响——Bash 约定）
5. 启动 daemon 后立即检查 `cat /tmp/ncm-state.json` 确认其存活

**调试**：如果 waybar 按钮突然全部消失，先检查 daemon 进程是否存在：
```bash
pgrep -a -f "ncm-player daemon" | grep -v hermes
# 无输出 = daemon 死了
```
然后手动前台跑一次看错误：
```bash
bash ~/.local/bin/ncm-player daemon
# Ctrl+C 中断，观察错误输出
```

### ⚠️ 永远不要 mv/rm 已有的二进制文件
`~/.local/bin/ncm` 是 Go 编译产物（7.8MB），来源不可恢复。

### ⚠️ 不要安装 Playwright Chromium
用户不接受额外的无头浏览器。一律用 `ncm-cli login --background` 二维码登录。

## 事件驱动缓存架构（v3，2026-06-24）

> **核心原则**：stats 唯一真相源 = `ncm-cli state`。`ncm-player` 永远不"猜"播放状态——先调 ncm-cli 做事，再读 ncm-cli state，再写缓存。所有缓存写入必须以"读 ncm-cli、写 ncm-cli 结果到缓存"为模板。

### 数据流（事件驱动 + 慢兜底）

```
┌─────────────┐
│ ncm-cli     │ ← 唯一真相源（state + login --check）
└──────┬──────┘
       │ 每次 sync_state 调用读
       ↓
┌─────────────┐
│ sync_state  │ ← ncm-player 内部 helper
└──────┬──────┘
       │ 写 + 发 signal
       ↓
┌─────────────┐
│ /tmp/ncm-   │ ← 缓存层（waybar 读这个）
│ state.json  │
└─────────────┘
```

### sync_state 触点（覆盖所有控制命令）

```bash
sync_state() {
  # 1. 读 ncm-cli state（真相源，不走缓存）
  local ncm_state=$(ncm_status)

  # 2. 读 ncm-cli login（真相源，1h 缓存）
  local logged="false"
  check_login && logged="true"

  # 3. 计算 icons（基于真相源）
  ...

  # 4. 写 /tmp/ncm-state.json（合并 /tmp/ncm-current.json 里的 current_*，保留 fav_playlist_id / liked_song_id）
  ...

  # 5. 发 signal 触发 waybar 刷新
  pkill -RTMIN+$STATUS_SIGNAL waybar 2>/dev/null || true
}
```

调用点（所有播放控制命令末尾 + 登录成功 + ncm-playlist 末尾）：
- `toggle`（ncm-player 内）：动作后调 sync_state
- `next` / `prev`（ncm-player 内）：ncm-cli 转发后调 sync_state
- `heartbeat_play`（toggle 启动心动模式后）：写 current.json + 调 sync_state
- `ncm-playlist`（Python 脚本）：subprocess 调 `ncm-player sync-state` 命令
- `login` 成功：sync_state 让 status_icon 从 🔑 变空

### daemon 只做慢兜底（10s 一次）

```bash
daemon)
    SWAYSOCK=$(cat /tmp/ncm-swaysock 2>/dev/null || true)
    while [ -n "$SWAYSOCK" ] && [ -S "$SWAYSOCK" ]; do
        sync_state   # 兜底：兜住 mpv 自然结束/外部停止等边界情况
        sleep 10
    done
    systemctl --user stop ncm-state-daemon.service
    ;;
```

**为什么是 10s 不是 2s**：
- 各控制命令已主动调 sync_state（0 延迟）
- daemon 兜底只需要处理"mpv 自然结束"这种边界情况，10s 用户可接受
- 旧 2s busy loop → 现在 6 calls/hour（**↓ 99.7%** ncm-cli 开销）

### 登录缓存 1h（不是 60s）

```bash
LOGIN_CACHE_TTL=3600  # 1h（cookie 24h+ 有效，用户根本不会退出）
```

**为什么 1h 够**：
- cookie 24h+ 有效，1h 验证足够
- 用户基本不会在 waybar 会话中登出
- 失败时立即 `rm -f` 缓存，下一次 check 立即重试（不卡 1h）

### ⚠️ 反模式：ncm-player 直接写 stats 字段

> 用户原话："不是 ncm-player 直接写 stats，而是播放控制动作后，读 ncm-cli stats，再写 ncm-cli stats 到缓存，统一 stats 源为 ncm-cli stats"

**禁止写法**：ncm-player 自己 "猜" 播放状态并写入缓存：
```bash
# ❌ 反模式
toggle)
    case "$state" in
        playing|paused) write_state play=📻 ;;  # 自己推断
    esac
```

**正确写法**：调 ncm-cli → 读 ncm-cli state → 写缓存：
```bash
# ✅ 正确
toggle)
    case "$state" in
        playing|paused) $NCM_CLI stop >/dev/null 2>&1 ;;
        *)              heartbeat_play ;;
    esac
    sync_state   # 读 ncm-cli 当前真实 state，写缓存
```

**为什么**：ncm-cli 才是 mpv 的实际管理者。ncm-player 自己推断会和 ncm-cli 实际状态脱钩（比如 ncm-cli 已自然停止，ncm-player 还显示 ⏹）。

### ncm-cli state JSON 结构（v0.1.6）

```json
{
    "success": true,
    "state": {
        "status": "stopped",        // stopped | playing | paused
        "position": 0,
        "volume": null,
        "currentIndex": 0,
        "queueLength": 0
    }
}
```

**只关心 `status` 字段**——`position` / `volume` / `currentIndex` / `queueLength` 都不需要。

### sync-state 命令暴露给 ncm-playlist

`ncm-playlist` 是 Python 脚本，不能直接调 ncm-player 内部 helper。暴露一个 `sync-state` 命令：

```bash
case "$1" in
    sync-state) sync_state ;;  # 让 ncm-playlist 等外部脚本触发
esac
```

ncm-playlist 末尾：
```python
subprocess.run([os.path.expanduser("~/.local/bin/ncm-player"), "sync-state"],
               capture_output=True, timeout=5)
```

## waybar 调试

配置改动后两步检查：

```bash
# 1. JSON 合法性
python3 -c "import json;json.load(open('~/.config/waybar/config-top'));print('OK')"

# 2. 重启
swaymsg reload
sleep 3
pgrep -af "ncm-player daemon"       # 应有且仅有一个
cat /tmp/ncm-state.json             # 应有最新状态
```

不要问用户测试——自己执行验证链，展示证据。

## 已知限制

| 限制 | 说明 | 状态 |
|---|---|---|
| 无游客模式 | 网易云要求登录才能使用所有 API | ⚠️ 永久 |
| 红心需当前歌曲加密ID | `ncm-cli song like --id <encrypted_id>` 需要知道当前播放歌曲的ID；state.json 需记录 | ⚠️ 需 daemon 配合 |
| ncm-cli vs ncm-go 登录不共享 | ncm-cli（二维码 OAuth）与 ncm-go（Playwright）使用各自独立的 session | ✅ 无影响（ncm-go 已废弃） |
| mpris `playback-status` 不存在 | mpv ≤ 0.40 无此属性，用 `idle` + `pause` 推导状态 | ✅ 已通过 daemon 解决 |

### 组件能力矩阵（最终版）

| 功能 | ncm-cli v0.1.6 (已登录) | ncm-go v0.2.1 | 说明 |
|---|---|---|---|
| 播放/暂停/切歌/音量 | ✅ | ❌ (只调桌面客户端) | ncm-cli 通过 mpv 播放 |
| 搜索歌曲/专辑/歌单 | ✅ (`search song/album/playlist/all`) | ✅ | ncm-cli 登录后可用 |
| `playlist` | `ncm-cli playlist created/collected/get/tracks/add/remove` | ❌ | ncm-cli 登录后可用 |\n| 红心/取消红心 | ✅ (`song like`) | ❌ | ncm-cli 登录后可用，无 dislike |
| 心动模式 | ✅ (`recommend heartbeat`) | ❌ | ncm-cli 登录后可用 |
| 每日推荐 | ✅ (`recommend daily`) | ✅ (`recommend songs`) | 两者均可 |
| 私人漫游(FM) | ✅ (`recommend fm`) | ❌ | ncm-cli 登录后可用 |
| 歌单管理 | ✅ (`playlist created/radar/collected/get/tracks/add/remove`) | ✅ | ncm-cli 登录后可用 |
| 用户信息/红心歌单 | ✅ (`user favorite/history/listen-ranking`) | ✅ (`me`) | ncm-cli 登录后可用 |
| 歌词 | ✅ (`song lyric`) | ✅ (`lyric`) | 两者均可 |
| 二维码登录 | ✅ (`login --background`) | ❌ (Playwright 浏览器) | ncm-cli 唯一登录方式 |
| **Playwright 浏览器登录** | ❌ | ✅ (`login`) | **已废弃**——用户不接受额外 Chromium |
| 游客访问 | ❌ | ❌ | 所有 API 需要登录态 |

**核心结论**：ncm-cli 登录后覆盖全部功能，ncm-go 已废弃。

## 参考文档

- `references/login-gated-commands.md` — ncm-cli 登录后解锁的全部命令列表与 JSON 响应格式
- `references/ncm-go-binary.md` — ncm Go 二进制信息（已废弃）
- `references/ncm-cli-backend.md` — ncm-cli 替代 api-enhanced 的安装与切换说明（历史文档）
- `ncm-state-daemon/references/ncm-daemon-patterns.md` — 登录门控 + mpris 优化细节
- `waybar-config/references/player-module-audit-2026-06-23.md` — 完整模块审计
