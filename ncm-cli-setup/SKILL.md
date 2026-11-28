---
name: ncm-cli-setup
description: "安装和配置网易云音乐 CLI 工具栈（ncm-cli + ncm-player + mpv-mpris）：systemd --user daemon、waybar 集成（CSS 状态类路由、登录门控、5 个模块字段表）、常见坑速查表"
---

# 网易云音乐 CLI 工具栈

`ncm-cli` v0.1.6（npm `@music163/ncm-cli`）是本机唯一的网易云音乐后端：播放、搜索、推荐、红心、歌单、歌词全部由它提供。本 skill 覆盖安装、systemd daemon、waybar 集成与状态文件规范。

## 架构总览

**唯一真相源 = `ncm-cli`**。`ncm-player` 不猜播放状态：先调 ncm-cli 做事 → 读 `ncm-cli state` → 写 `/tmp/ncm-state.json` → 发 signal 6 通知 waybar。

```
ncm-player (shell, ~/.local/bin/ncm-player)     统一调度器
  ├── ncm-cli  (npm, ~/.local/bin/ncm-cli)       唯一后端：播放/搜索/推荐/红心/歌单
  ├── mpv + mpv-mpris.so (Debian 包)             实际播放 + D-Bus MPRIS
  └── ncm-playlist (Python, fuzzel)              选歌单 → ncm-cli play --playlist

控制命令(toggle/next/prev/like/pl/login)
  └─→ sync_state ──→ /tmp/ncm-state.json ──→ pkill -RTMIN+6 waybar
                             ↑                      │
daemon (systemd --user, 10s 慢兜底) ───────────────┘
```

| 组件 | 位置 | 作用 |
|---|---|---|
| `ncm-cli` | `~/.local/bin/ncm-cli` → Hermes Node 的 npm bin | 唯一后端引擎，登录后解锁全部功能 |
| `ncm-player` | `~/.local/bin/ncm-player` | 调度器：daemon / waybar-* / 播放控制 / 登录 / sync_state |
| `ncm-playlist` | `~/.local/bin/ncm-playlist` | fuzzel 双层选歌单 → 播放 |
| `mpv-mpris` | `/usr/lib/mpv-mpris/mpris.so`（Debian 包） | D-Bus MPRIS 桥接 |

**登录方式只有一个**：`ncm-cli login --background`（开放平台 OAuth 网页短链）。不要引入需要额外浏览器的登录方式。

### ncm-cli 命令门控【关键发现】

`ncm-cli v0.1.6` 的 `commands` 输出依赖登录状态：登录前只有约 10 个播放控制命令（`play/pause/resume/next/prev/state/volume/queue/login/logout/config/tui/upgrade/commands/diag/cloudupload/cloud`），登录后自动包含约 40+ 个数据操作命令（`search song/album/playlist/all`、`song like/dislike/lyric`、`recommend daily/heartbeat/fm`、`user favorite/history/listen-ranking/info`、`playlist collected/radar/create/get/tracks/add/remove`、`album get/collected/tracks`、`comment list-hot/post/reply`、`note publish/delete/detail`、`podcast categories/voices/voiceUpload/voicelistCreate` …）。

- 判断是否已登录：`ncm-cli login --check --output json` 返回 `"success": true`
- 判断实际可用命令：`ncm-cli commands`（登录前后输出不同）

## 文件布局（部署后）

```
~/.local/bin/
  ncm-cli                    # npm 全局 bin 的 symlink（Hermes Node）
  ncm-player                 # shell 调度器（daemon/waybar/播放/登录）
  ncm-playlist               # Python fuzzel 选歌单脚本
~/.config/mpv/mpv.conf       # mpv 基本配置
~/.config/ncm-cli/           # ncm-cli 运行时目录（queue.json / config.json / mpv-input.conf）
~/.config/systemd/user/ncm-state-daemon.service   # daemon 的 systemd --user 服务
~/.config/waybar/config-top  # 5 个 ncm-* 自定义模块（signal 触发 + 连续 while）
~/.local/share/ncmctl/.login_cache                # 登录态缓存（TTL 3600s）
/tmp/ncm-state.json          # daemon/控制命令写入，waybar 模块读取
/tmp/ncm-current.json        # 当前曲目（播放时写入）
```

被 waybar 调用的脚本内部必须 `export PATH="$HOME/.local/bin:$PATH"`（原因见「常见坑」）。

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

部署到 `~/.local/bin/ncm-player` 并 `chmod +x`。部署后的 `~/.local/bin/ncm-player` 是权威版本（含 `daemon` / `state-get-json` / `state-get` / `waybar-*` / `sync-state` / `info` 等子命令）；`templates/ncm-player.sh` 只是最初的脚手架，已明显落后于部署版本。

**重要**：

- 脚本内 `NCM_CLI` 必须用**绝对路径** `"$HOME/.local/bin/ncm-cli"`，否则从 foot/waybar 启动时找不到
- 脚本顶部必须 `export PATH="$HOME/.local/bin:$PATH"`（waybar 子进程 PATH 不含 `~/.local/bin`）

### 第四步：登录（网页短链授权）

```bash
foot -a ncm-login -W 80x24 -H /home/dr/.local/bin/ncm-player login
```

- `-H` 必须加，否则终端在命令结束后立即关闭，用户来不及扫码/点链接
- 登录信息（链接、二维码、成功/失败）直接打印到终端，不用 `notify-send`
- `ncm-cli login --background --output json` 返回的是**开放平台 OAuth 网页短链**（`clickableUrl`，形如 `https://163cn.tv/9Egh7iB`），不是手机 App 扫码用的 QR 图。浏览器打开短链完成网易云账号授权即可，**不受手机扫码频率限制**
- 常见误解：看到「二维码」以为是手机 App 扫码 → 实际点链接与扫屏幕二维码是同一个网页授权流程

```json
{
  "success": true,
  "clickableUrl": "https://163cn.tv/9Egh7iB",
  "message": "后台轮询已启动，请点击链接登录"
}
```

**登录子进程必须清理**：`ncm-cli login --background` 会拉起一个持久的 ncm-cli 子进程做 OAuth 轮询。Ctrl-C、超时、解析失败等任一退出路径都会留下孤儿进程，所有退出路径都要走 `cleanup_login`：

```bash
login)
    cleanup_login() {
        pkill -f 'ncm-cli.*login' 2>/dev/null || true  # 杀残留子进程
        rm -f "$STATE_DIR/qr.png"                       # 删二维码文件
    }
    trap 'cleanup_login; exit 1' INT TERM                # Ctrl-C / TERM
    ...
    $NCM_CLI login --background ... || { cleanup_login; exit 1; }
    ...
    check_login && { echo "登录成功 ✓"; cleanup_login; exit 0; }
    cleanup_login  # 登录超时收尾
    ;;
```

## systemd daemon 管理

daemon 由 `systemd --user` 托管（`ncm-state-daemon.service`）。不要用 `terminal(background=true)` 手动拉起，也不要在 sway `exec_always` 里直接跑 daemon 进程。

`~/.config/systemd/user/ncm-state-daemon.service`：

```ini
[Unit]
Description=ncm-state-daemon — mpv state poller + login cache for waybar NCM modules
Documentation=https://github.com/NetEase/skills

[Service]
Type=simple
ExecStart=%h/.local/bin/ncm-player daemon
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
```

- **不要加 `PrivateTmp=true`**：daemon 写的 `/tmp/ncm-state.json` 必须和 waybar 看到的是同一个文件；私有 /tmp 会让 waybar 读到空 → 所有 ncm 模块同时消失。`templates/ncm-state-daemon.service` 模板里带 `PrivateTmp=true`，复制模板时必须去掉。
- 已部署文件的 `[Install]` 是 `WantedBy=default.target`，实际 enable 软链位于 `~/.config/systemd/user/graphical-session.target.wants/`。
- `BindsTo/After=graphical-session.target` 可选（图形会话结束时应停）。

管理命令：

```bash
systemctl --user status ncm-state-daemon.service   # 查看状态
systemctl --user restart ncm-state-daemon.service   # 重启
systemctl --user is-active ncm-state-daemon.service # 1 = 存活
journalctl --user -u ncm-state-daemon.service -f    # 看日志
```

sway 配置只保留这几行：

```bash
# ~/.config/sway/config
exec_always systemctl --user start ncm-state-daemon.service
for_window [app_id="ncm-login"] floating enable
for_window [app_id="ncm-login"] resize set 700 400
for_window [app_id="ncm-login"] move position center
```

- `systemctl --user start` 幂等：服务已在跑时不会起第二个，`swaymsg reload` 不产生新进程。
- sway 退出时 daemon 自停：daemon 循环自发现 sway socket（`/run/user/$UID/sway-ipc.*.sock`），socket 消失即退出并 `systemctl --user stop ncm-state-daemon.service`。
- **不要再写 `/tmp/ncm-swaysock`** —— ncm-player 直接从 `/run/user/$UID/` 自发现最新 socket。

## 状态文件与缓存

`/tmp/ncm-state.json` 是所有 waybar 模块的唯一输入：

| 字段 | 写入者 | 说明 |
|---|---|---|
| `status` | sync_state | `stopped` / `playing` / `paused`（来自 `ncm-cli state`） |
| `logged_in` | sync_state | `"true"` / `"false"` |
| `play` | sync_state | 已登录：`⏹`（播放中）/ `📻`（停止）；未登录：空串 |
| `like` | sync_state | 已登录：`❤` / `♡`；未登录：空串 |
| `pl` | sync_state | 已登录：`📋`；未登录：空串 |
| `status_icon` | sync_state | 已登录：空串（模块隐藏）；未登录：`🔑` |
| `status_class` | sync_state | `logged-in` / `logged-out` |
| `current_encrypted_id` / `current_title` / `current_artist` | `set_current_song` 写 `/tmp/ncm-current.json`，sync_state 合并进来 | 当前曲目 |
| `liked_song_id` | like 命令 | 已红心的加密 ID（供 `❤`/`♡` 比较） |
| `fav_playlist_id` | sync_state（已登录且未缓存时拉一次） | 红心歌单 ID 缓存 |

sync_state 是**唯一写缓存的入口**（daemon 兜底除外），流程：

1. 读 `ncm-cli state --output json` → `status`
2. `check_login`（1h 缓存）→ `logged`
3. 计算 `play` / `like` / `pl` / `status_icon` / `status_class`
4. 写 `/tmp/ncm-state.json`：合并 `/tmp/ncm-current.json` 的 `current_*`，并保留外部维护的字段
5. 已登录且 `fav_playlist_id` 未缓存 → 前台拉一次 `ncm-cli user favorite` 写入缓存
6. `pkill -RTMIN+6 waybar` 通知刷新

外部命令维护的字段（`liked_song_id`、`fav_playlist_id`）必须保留 —— sync_state 的 Python inline 是**全量重写** state.json：

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

### 反模式：ncm-player 自己推断播放状态

ncm-cli 才是 mpv 的实际管理者。ncm-player 自己「猜」状态会和 ncm-cli 脱钩（比如 ncm-cli 已自然停止，ncm-player 还显示 `⏹`）。

```bash
# ❌ 反模式：自己推断
toggle)
    case "$state" in
        playing|paused) write_state play=📻 ;;
    esac

# ✅ 正确：调 ncm-cli → 读 ncm-cli state → 写缓存
toggle)
    case "$state" in
        playing|paused) $NCM_CLI stop >/dev/null 2>&1 ;;
        *)              heartbeat_play ;;
    esac
    sync_state   # 读 ncm-cli 当前真实 state，写缓存
```

### 事件驱动 + 10s 慢兜底

- 主驱动：各控制命令末尾的 `sync_state`（事件驱动，0 延迟）
- 兜底：daemon 每 10s 调一次 `sync_state`（兜 mpv 自然结束 / 外部停止）
- 登录缓存 TTL 3600s（1h）
- ncm-cli 调用量：1860/h → 6/h（**↓ 99.7%**）

```bash
daemon)
    trap 'exit 0' TERM INT
    # 自发现当前 sway socket（sway 退出 → 循环退出 → 服务自停）
    _ncm_current_swaysock() { ls -t /run/user/"$(id -u)"/sway-ipc.*.sock 2>/dev/null | head -1; }
    while SWAYSOCK=$(_ncm_current_swaysock); [ -n "$SWAYSOCK" ] && [ -S "$SWAYSOCK" ]; do
        sync_state   # 兜底：兜住 mpv 自然结束/外部停止等边界情况
        sleep 10
    done
    systemctl --user stop ncm-state-daemon.service 2>/dev/null || true
    ;;
```

### 登录缓存实现

```bash
LOGIN_CACHE="$STATE_DIR/.login_cache"   # STATE_DIR=$HOME/.local/share/ncmctl
LOGIN_CACHE_TTL=3600  # 1h（cookie 24h+ 有效，用户根本不会退出）

check_login() {
  [ -f "$LOGIN_CACHE" ] && [ $(( $(date +%s) - $(stat -c %Y "$LOGIN_CACHE") )) -lt $LOGIN_CACHE_TTL ] && return 0
  if $NCM_CLI login --check 2>&1 | grep -q '"success": true'; then
    touch "$LOGIN_CACHE"; return 0
  else
    rm -f "$LOGIN_CACHE"; return 1
  fi
}
```

- 真相源始终是 `ncm-cli login --check`，缓存只是 TTL 内的短路
- 检查失败立刻 `rm -f` 缓存 → 下一次 check 立即重试（不会卡 1h）

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

**只关心 `status` 字段** —— `position` / `volume` / `currentIndex` / `queueLength` 都不需要。

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

## 红心与心动模式

### ♡/❤ 视觉反馈（liked_song_id）

用户抱怨红心按钮「点了没反应」—— ♡ 在 like 前后不变，用户不知道操作是否成功。

**做法**：state.json 里追踪 `liked_song_id`。like 成功后写入 `liked_song_id = current_encrypted_id`，sync_state 比较两者：

- `current_encrypted_id == liked_song_id` → `like_icon = "❤"`
- 否则 → `like_icon = "♡"`

like 命令（ncm-cli 成功后写缓存，再 sync_state）：

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

**行为**：

- 首次 like → 显示 `❤`
- 切歌 → 自动复位 `♡`（`current_encrypted_id` 变了）
- 同一首再 like → 幂等（`ncm-cli song like` 可重复调用），图标仍 `❤`
- `ncm-cli song dislike`（取消红心）在 CLI 层可用（参数 `--songId`），但 ncm-player 的红心按钮目前只做加红心

### 多源 state 与 race condition（消费者修法）

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
        ncm-player state-get   ncm-player like   ncm-player waybar play/pl
        (waybar 用)     (button 用)    (while 循环用)
```

**为什么是消费者修而不是生产者**：生产者要「先写 current，再让 daemon 合并」—— 必须等 daemon 跑完一轮才有 state.json，延迟是 daemon 周期（10s）。消费者直接读最新源，0 延迟。

**修法**：按「最新到最旧」顺序读，命中即停。

```bash
# ncm like 读当前歌曲 ID
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

**审计清单**：所有读 state.json 的命令都得考虑「是否有更早的源」：

```bash
grep -nE "state.json|current.json" ~/.local/bin/ncm-player
# 每个读 state.json 的 case 都要问：现在是否有更新的源？
```

### 连续队列播放：heartbeat_play 入列全部推荐

`heartbeat_play` 原实现只播推荐列表的第一首歌，播完即止。用户预期点了 📻 后连续播放。

**做法**：利用 ncm-cli 的 `queue` —— 推荐 40 首，播第一首，其余 39 首通过 `ncm-cli queue add` 入列，daemon 播完当前后自动切下一首。

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

- `ncm-cli queue add` 逐个添加到 daemon 维护的队列 → daemon 播完当前后自动切下一首
- `( sleep 2; ... ) &` 后台执行（播放不阻塞），2s 延迟防止 daemon 正在处理 play 命令时冲突
- 不支持 `&` 并行入列（daemon 有写锁，并行冲突只会入 1 首）
- `queueLength` 反映队列深度，可在 ncm-cli state 或 queue.json 中查看
- **ncm-cli daemon 必须存活**（PID file 在 `~/.config/ncm-cli/daemon.pid`），否则 queue 不生效
- `queue.json` 路径：`~/.config/ncm-cli/queue.json`，格式为 `{items:[...], currentIndex: N, mode: "sequential"}`

**失败模式**：queue clear 后 daemon 可能清空内存队列；直接写 queue.json 无效（daemon 覆盖）。必须通过 `ncm-cli queue add` API 操作。

### fav 缓存：心动模式列表 ID

用户点 📻（ncm-play/toggle）从 stopped → heartbeat_play 时，每次都要调 `$NCM_CLI user favorite --output json` 拿红心歌单 ID（约 2s 网络延迟）。列表 ID 几乎不变，没必要每次拉。

**做法**：把 `fav_playlist_id` 缓存到 `/tmp/ncm-state.json`，由 `sync_state()` 在已登录 + 缓存为空时前台拉一次（一次性 ~2s），后续 `heartbeat_play` 直接读缓存。

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

  # 如果 fav 未缓存且已登录，前台获取一次
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

**注意**：不要用后台 `&` 异步拉 fav，否则会跟 sync_state 写 state.json 撞 race condition（后台写完被 sync_state 覆盖）。前台 fetch 简单且无 race。sync_state 的 Python inline 是全量重写 —— 必须保留 `fav_playlist_id`（以及 `liked_song_id` 等其他外部字段）的保留逻辑。

**通用模式**：缓存「很少变化、调用昂贵」的 ncm-cli 数据到 state.json。其它候选：用户信息（`ncm-cli user info`）、红心总数等 —— 按需添加。

## waybar 集成

5 个 `custom/ncm-*` 模块（`~/.config/waybar/config-top`）：

```json
"custom/ncm-like": {
  "exec": "/home/dr/.local/bin/ncm-player waybar-like",
  "format": "{text}",
  "return-type": "json",
  "on-click": "/home/dr/.local/bin/ncm-player like",
  "tooltip": true,
  "tooltip-format": "喜欢/取消喜欢（未登录时隐藏）"
},
"custom/ncm-nowplaying": {
  "exec": "/home/dr/.local/bin/ncm-player waybar-nowplaying",
  "format": "{text}",
  "return-type": "json",
  "max-length": 36,
  "on-click": "/home/dr/.local/bin/ncm-player toggle",
  "on-click-middle": "/home/dr/.local/bin/ncm-player next",
  "on-click-right": "/home/dr/.local/bin/ncm-player prev",
  "tooltip": true
},
"custom/ncm-play": {
  "exec": "/home/dr/.local/bin/ncm-player waybar-play",
  "format": "{text}",
  "return-type": "json",
  "on-click": "/home/dr/.local/bin/ncm-player toggle",
  "tooltip": true,
  "tooltip-format": "播放/暂停"
},
"custom/ncm-pl": {
  "exec": "/home/dr/.local/bin/ncm-player waybar-pl",
  "format": "{text}",
  "return-type": "json",
  "on-click": "/home/dr/.local/bin/ncm-player pl",
  "tooltip": true,
  "tooltip-format": "我的歌单（点击选择）"
},
"custom/ncm-status": {
  "exec": "/home/dr/.local/bin/ncm-player state-get-json status_icon",
  "format": "{text}",
  "interval": 30,
  "return-type": "json",
  "signal": 6,
  "on-click": "foot -a ncm-login -W 80x24 -H /home/dr/.local/bin/ncm-player login",
  "tooltip": true,
  "tooltip-format": "网易云登录（点击扫码登录）"
},
```

规则：

- `return-type: json` + `format: "{text}"` 对全部模块是**强制的**（否则 label 被 `fmt::format_error` 隐藏）
- `exec` / `on-click` 一律用绝对路径 `/home/dr/.local/bin/ncm-player`
- play/pl/like/nowplaying 用连续 while 循环（`waybar-*` 子命令自带循环：play 2s，pl/like/nowplaying 5s）；status 用 `interval: 30` + `signal: 6`（signal 由 sync_state 的 `pkill -RTMIN+6 waybar` 触发）
- exec 返回空字符串 → GTK widget 自动不渲染 → 未登录/未播放时对应模块自动隐藏

### 5 个模块字段来源表

| 模块 | exec | 模式 | 间隔 | 未登录 / 停止时 |
|---|---|---|---|---|
| `custom/ncm-play` | `ncm-player waybar-play` → `state-get-json play` → `{"text":"📻/⏹"}` | 连续 while | 2s | 隐藏（空串） |
| `custom/ncm-status` | `ncm-player state-get-json status_icon` → `{"text":"🔑/空"}` | interval + signal 6 | 30s | 显示 🔑（已登录则空串隐藏） |
| `custom/ncm-like` | `ncm-player waybar-like` → `{"text":"♡"}` | 连续 while | 5s | 隐藏 |
| `custom/ncm-pl` | `ncm-player waybar-pl` → `{"text":"📋"}` | 连续 while | 5s | 隐藏 |
| `custom/ncm-nowplaying` | `ncm-player waybar-nowplaying` → `{"text":"🎵 歌手 - 歌名"}` | 连续 while | 5s | 停止时隐藏 |

### CSS 状态类路由

waybar 的 `return-type: json` 支持 `class` 字段 → style.css 里按 `#<模块 id>.<class>` 路由颜色。当前 `~/.config/waybar/style.css` 已有：

```css
#custom-ncm-status.logged-in  { color: #2d8a4e; }
#custom-ncm-status.logged-out { color: #aaa; }
#custom-ncm-play.playing { color: #2d8a4e; font-weight: bold; }
#custom-ncm-play.paused  { color: #000000; }
```

class 值来自 ncm-player 输出的 JSON，state.json 里对应的状态字段是 `status_class`（`logged-in` / `logged-out`）和 `status`（`playing` / `paused` / `stopped`）。`state-get-json` 目前只输出 `text`；需要按播放状态着色时，让对应 JSON 输出带上 `"class"` 字段即可：

```bash
# 在 ncm-player 的 JSON 输出里输出 class 字段（示意）
printf '{"text":"⏸","class":"playing"}'
```

### 歌名显示：用 custom/ncm-nowplaying，不用内置 mpris

mpv-mpris 0.7.1 有 C 源码级 bug：PlaybackStatus 始终返回 "Stopped"，waybar 内置 mpris 模块收到 Stopped 后 `skip update`，`format-stopped` 也救不回来。

**做法**：`modules-right` 里用 `custom/ncm-nowplaying` 取代内置 `mpris`，直接从 `/tmp/ncm-state.json` 读 `current_title` / `current_artist`，完全绕过 mpv-mpris D-Bus。tooltip 通过 JSON 的 `tooltip` 字段提供（waybar 自动使用），可显示多行歌曲详情（歌曲名/歌手/红心状态/播放状态）。

### 音量图标

`pulseaudio.format-icons` 不要留空字符串。三个数组元素分别对应低/中/高音量：

```json
"format-icons": {
    "default": ["\uf027", "\uf027", "\uf028"],
    "default-muted": ["\uf026", "\uf026", "\uf026"]
}
```

## 性能

- ncm-cli 是 Node.js CLI，每次调用有约 **365ms** 的启动开销
- 因此 waybar 模块**不直接调 ncm-cli**：统一由 daemon/控制命令写 `/tmp/ncm-state.json`，模块只读文件（微秒级，零 ncm-cli 调用）
- 现状：v3 事件驱动 ≈ **144** 次 ncm-cli 调用/天；加上 fav 缓存后 ≈ **142**。对比「每模块独立轮询」的原始设计 ≈ 150,000 次/天
- 缓存通用模式：把「很少变化、调用昂贵」的数据缓存进 state.json，按需添加

## 常见坑

| 症状 / 坑 | 原因 | 正确做法 |
|---|---|---|
| waybar 点按钮无响应、图标空白，但终端里 ncm-cli 正常 | waybar 用 `g_spawn_command_line_async` 直接 `execve`，不走 shell；子进程 PATH 不含 `~/.local/bin`，而 ncm-cli 的 shebang 是 `#!/usr/bin/env node`，找不到 `node` 时 exit 127 被 `2>/dev/null` 吞掉 | 被 waybar 调用的脚本顶部加 `export PATH="$HOME/.local/bin:$PATH"`；`NCM_CLI="$HOME/.local/bin/ncm-cli"` 用绝对路径；Python 脚本里 `os.environ["PATH"] = os.path.expanduser("~/.local/bin") + ":" + os.environ.get("PATH","")` |
| 后台进程/服务里报 `ncm-cli: command not found` 或 `env: node: No such file or directory` | ncm-cli 装在 Hermes Agent 的 Node（`/home/dr/.hermes/node/bin/`）下，后台 shell 的 PATH 不含它 | `PATH="/home/dr/.hermes/node/bin:$PATH" ncm-cli login --background`；或 `/home/dr/.hermes/node/bin/node /home/dr/.hermes/node/lib/node_modules/@music163/ncm-cli/dist/index.js login --background`。`~/.local/bin/ncm-cli` 已是指向 Hermes Node 的 symlink |
| 歌名/用户名含 `'`（"Don't Stop Me Now"、"It's My Life"）时 python 解析失败，mpv 标题设置和当前曲目写入静默失败 | bash 里嵌 `python3 -c "..."` 时单引号提前闭合 | 动态值一律用环境变量传（见下方模板）；静态 shell 部分用单引号包；复杂逻辑提到外部 .py 文件 |
| 登录中断后残留 ncm-cli 孤儿进程 | `ncm-cli login --background` 起持久轮询子进程，任一退出路径没清理 | login case 里定义 `cleanup_login`（`pkill -f 'ncm-cli.*login'` + `rm -f "$STATE_DIR/qr.png"`），`trap 'cleanup_login; exit 1' INT TERM`，每个 exit 前都调 |
| waybar 所有 ncm 模块突然同时消失 | daemon 因 `set -euo pipefail` 遇一条失败子命令静默退出（无日志无报错） | 所有可能失败的命令用 `|| true` / `\|\| state="fallback"` 包裹；python 读写用 `2>/dev/null \|\| true`；先 `pgrep -a -f "ncm-player daemon"` 判断 daemon 是否存活，再 `bash ~/.local/bin/ncm-player daemon` 前台跑看报错 |
| daemon 退出后 waybar 读不到状态 | daemon 的 trap 里 `rm -f /tmp/ncm-state.json` | trap 只退出不删文件：`trap 'exit 0' TERM INT` |
| daemon 服务秒退 / waybar 读不到状态 | unit 里设了 `PrivateTmp=true`，daemon 写的 `/tmp/ncm-state.json` 落在私有命名空间 | 去掉 `PrivateTmp=true`（含 `templates/ncm-state-daemon.service` 模板里的那一行） |
| 手动启动 daemon 产生孤儿进程、sway reload 后重复起 | 绕过 systemd 管理，或在 sway `exec_always` 里直接跑 daemon 进程 | 只用 `systemctl --user start/restart ncm-state-daemon.service`；sway 里写 `exec_always systemctl --user start ncm-state-daemon.service`（幂等） |
| 登录窗口一闪而过，用户来不及扫码 | foot 缺 `-H` | `foot -a ncm-login -W 80x24 -H /home/dr/.local/bin/ncm-player login` |
| 想装 `notify-send` / `libnotify-bin` / `mako` / `dunst` 做桌面通知 | 终端流程已能显示全部信息，额外通知守护进程只增加依赖 | 不装；信息直接打印到终端，错误用 `echo "消息" >&2`。误装了 `sudo apt-get remove --purge` 清理 |
| queue 只入 1 首 / 队列莫名被清空 | `&` 并行 `queue add` 撞 daemon 写锁；直接写 queue.json 会被 daemon 覆盖 | 串行 `ncm-cli queue add --encrypted-id <id> --original-id <id>`；ncm-cli daemon 必须存活（PID `~/.config/ncm-cli/daemon.pid`） |
| 以为「二维码」是手机 App 扫码、触发频率限制 | ncm-cli 用开放平台 OAuth，返回的是网页短链 `clickableUrl` | 直接用 `ncm-cli login --background` 的网页短链授权，不做手机 App 扫码 |
| sway reload 后 exec_always 起的进程重复堆积 | 用 `pkill -f` 匹配自身（会把自己的进程组也杀掉） | 改用 systemd --user（幂等 start）；通用规则见 `sway-daemon-persistence` 技能的「sway exec_always 不要用 pkill -f 匹配自身」 |

### ✅ 通用模板：bash 里嵌 Python 一律用环境变量传动态值

```bash
# ❌ 错误：动态值直接插进 python 源码 → 标题含 ' 时 python 解析失败
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

规则：

1. 动态值全用环境变量传：`VAR="$var" python3 -c "import os; v=os.environ['VAR']"`
2. 静态 shell 部分用单引号包：`python3 -c 'import json, sys; ...'`（避免 bash 插值）
3. 复杂 Python 逻辑提到外部 .py 文件（最稳）

改完 ncm-player 必查：

```bash
grep -n "python3 -c" ~/.local/bin/ncm-player
# 每一行都要过：动态值是否在 '$...' 位置？→ 改用环境变量
```

## 调试

配置改动后两步检查：

```bash
# 1. JSON 合法性
python3 -c "import json;json.load(open('/home/dr/.config/waybar/config-top'));print('OK')"

# 2. 重启
swaymsg reload
sleep 3
pgrep -af "ncm-player daemon"       # 应有且仅有一个
cat /tmp/ncm-state.json             # 应有最新状态
```

`ncm-player info` 可一键打印登录态、`ncm-cli state`、当前曲目、state.json 与服务状态。

不要问用户测试 —— 自己执行验证链，展示证据。

## 已知限制

| 限制 | 说明 | 状态 |
|---|---|---|
| 无游客模式 | 网易云要求登录才能使用所有 API | ⚠️ 永久 |
| 红心需当前歌曲加密 ID | `ncm-cli song like --songId <encrypted_id>` 需要当前播放歌曲的 ID；由 state.json 的 `current_encrypted_id` 提供 | ⚠️ 需 daemon 配合 |
| ncm-cli 命令登录门控 | 未登录时 `search` / `recommend` / `song` / `playlist` / `user` 等子命令不在命令树中，调用报「命令不存在」 | ✅ 先 `login --check` |
| mpv-mpris 0.7.1 PlaybackStatus 恒为 Stopped | waybar 内置 mpris 模块拿不到真实播放状态 | ✅ 已用 `custom/ncm-nowplaying` 取代 |

## 参考文档

- `references/login-gated-commands.md` — 登录后解锁的全部命令与 JSON 响应格式
- `references/event-driven-cache-architecture-2026-06-24.md` — v3 事件驱动缓存架构细节
- `templates/ncm-player.sh` — 调度器初始脚手架（已落后于部署版本 `~/.local/bin/ncm-player`）
- `templates/ncm-state-daemon.service` — unit 模板（注意其中的 `PrivateTmp=true` 必须去掉）
- `scripts/install_mpv.py` — mpv 安装脚本
