---
name: netease-music-cli
description: "使用 ncm-cli 操作网易云音乐（播放/搜索/推荐歌单/红心/控制播放/歌词）。命令集是登录门控的——登录前只有播放控制，登录后解锁搜索/推荐/红心/歌单等全部功能。脚本里必须用绝对路径调用 ncm-cli，否则会因为 env node 找不到 node 而静默失败（exit 127 被吞掉）。本机唯一后端是 ncm-cli（npm @music163/ncm-cli），已安装版本 v0.1.6。"
---

# 网易云音乐 CLI（ncm-cli v0.1.6）

通过 `ncm-cli`（npm `@music163/ncm-cli`，已安装 **v0.1.6**）操作网易云音乐：播放、搜索、推荐、红心、歌单、歌词。

## ⚠️ 登录门控（先做这一步）

`ncm-cli` 的命令集依赖登录状态。**未登录时只有静态的播放控制命令**，搜索/推荐/红心/歌单等资源命令根本不注册：

```bash
ncm-cli login --check --output json   # {"success": true, ...} = 已登录
ncm-cli commands                      # 列出当前实际可用的命令集
```

未登录时调用资源命令会直接报：

```
error: unknown command 'song'
error: unknown command 'playlist'
```

登录后（约 40+ 命令）才出现：

| 功能 | 命令（登录后） |
|---|---|
| 播放控制 | `play/pause/resume/stop/next/prev/seek/volume/queue/state` |
| 搜索 | `search song/album/playlist/all/mv/voice/podcast` |
| 推荐 | `recommend daily/heartbeat/fm` |
| 红心 | `song like/dislike` |
| 歌词 | `song lyric` |
| 歌单 | `playlist get/tracks/collected/created/radar/create/add/remove/reorder/updateName/updateDesc/updateTags/getTags/updateCover` |
| 用户 | `user favorite/history/listen-ranking/info/album-history/playlist-history` |
| 专辑 | `album get/tracks/collected` |
| 艺人 | `artist songs` |
| 评论 | `comment list-hot/post/reply` |
| 笔记 | `note publish/detail/delete/topicSearch` |
| 播客 | `podcast categories/subcategories/created/collected/voices/voiceUpload/...` |

登录方式只有一个（开放平台 OAuth 网页短链，不需要额外浏览器）：

```bash
ncm-cli login --background --output json
# → {"success": true, "clickableUrl": "https://163cn.tv/…", …}
```

未配置 API 凭证时先到[网易云音乐开放平台](https://developer.music.163.com/st/developer/apply/account?type=INDIVIDUAL)申请 appId / privateKey：

```bash
ncm-cli config set appId <你的AppId>
ncm-cli config set privateKey <你的privateKey>
```

## 脚本中必须用绝对路径

`ncm-cli` 的 shebang 是 `#!/usr/bin/env node`。waybar on-click 通过 `g_spawn_command_line_async` 直接 `execve`，**不走 shell**，子进程 PATH 通常不含 `~/.local/bin`，`env` 找不到 `node` 时返回 exit 127，又被 `2>/dev/null` 吞掉 → 上层脚本拿到空输出 → 误判成「无数据」→ 图标空白 / 按钮无响应。

**症状特征**：终端里 `ncm-cli state` 正常，waybar 点按钮无响应。

**修复**：被 waybar 调用的脚本（`ncm-player`、`ncm-playlist`）开头：

```bash
export PATH="$HOME/.local/bin:$PATH"
NCM_CLI="$HOME/.local/bin/ncm-cli"   # 绝对路径，不是 "ncm-cli"
```

Python 脚本：

```python
import os
os.environ["PATH"] = os.path.expanduser("~/.local/bin") + ":" + os.environ.get("PATH", "")
NCM_CLI_PATH = os.path.expanduser("~/.local/bin/ncm-cli")
```

同理，**所有** ncm-* waybar 模块的 `exec` / `on-click` 中调用的命令都必须用绝对路径 `/home/dr/.local/bin/ncm-player`。

## 状态读取：ncm-player 是唯一入口

`~/.local/bin/ncm` 这个 symlink **不存在**（已删除），不要写 `ncm state-get …`。用 `ncm-player`：

```bash
/home/dr/.local/bin/ncm-player state-get-json <key>   # 输出 {"text": "..."}，给 waybar return-type: json
/home/dr/.local/bin/ncm-player state-get <key>        # 输出裸值，给脚本取值
```

`/tmp/ncm-state.json`（由 daemon 与控制命令写入）支持的 key：

| key | 含义 |
|---|---|
| `status` | `stopped` / `playing` / `paused` |
| `logged_in` | `"true"` / `"false"` |
| `play` | `⏹`（播放中）/ `📻`（停止）/ 空串（未登录） |
| `like` | `❤` / `♡` / 空串 |
| `pl` | `📋` / 空串 |
| `status_icon` | 空串（已登录）/ `🔑`（未登录） |
| `status_class` | `logged-in` / `logged-out` |
| `current_encrypted_id` | 当前播放歌曲的 32 位 hex 加密 ID |
| `current_title` / `current_artist` | 当前曲目标题 / 歌手 |
| `liked_song_id` | 已红心歌曲的加密 ID（用于 ❤/♡ 比较） |
| `fav_playlist_id` | 红心歌单加密 ID（缓存） |

waybar 模块用「连续 while 输出」的子命令，不要自己轮询文件：

| waybar 模块 | exec | 内置节奏 |
|---|---|---|
| `custom/ncm-play` | `ncm-player waybar-play` | 2s |
| `custom/ncm-pl` | `ncm-player waybar-pl` | 5s |
| `custom/ncm-like` | `ncm-player waybar-like` | 5s |
| `custom/ncm-nowplaying` | `ncm-player waybar-nowplaying` | 5s |
| `custom/ncm-status` | `ncm-player state-get-json status_icon` | `interval: 30` + `signal: 6` |

`current_encrypted_id` / `current_title` / `current_artist` 由 `ncm-playlist` 与 `heartbeat_play` 播放新歌时写入 `/tmp/ncm-current.json`，daemon 下一轮合并进 `/tmp/ncm-state.json` —— 供 `ncm-player like` 等需要当前歌曲 ID 的命令读取。

## 性能：ncm-cli 每次调用 ~365ms

ncm-cli 是 Node.js 程序，每次执行 `login --check` / `state` / `recommend` 都要付一次 Node 运行时初始化开销，约 **365ms**。

因此 waybar 模块**不直接调 ncm-cli**，而是读 daemon 写好的状态文件：

- 事件驱动：各控制命令（toggle / next / prev / like / pl）结束时立即 `sync_state` 写文件，并 `pkill -RTMIN+6 waybar` 通知刷新（0 延迟）
- 兜底：daemon 每 **10s** 调一次 `sync_state`
- 登录态缓存：`~/.local/share/ncmctl/.login_cache`，TTL **3600s**，避免每轮调 `ncm-cli login --check`
- 红心歌单 ID（`fav_playlist_id`）同样缓存在状态文件里，只在为空时拉一次

结果：ncm-cli 调用量从 1860/h 降到 **6/h**（↓99.7%）。

### daemon 架构

```
控制命令(toggle/next/prev/like/pl/login)
  └─→ sync_state ──→ /tmp/ncm-state.json ──→ pkill -RTMIN+6 waybar
                             ↑                       │
daemon (systemd --user, 每 10s 兜底) ─────────────────┘
                             ↑
              ncm-cli state（唯一真相源）
```

daemon 由 systemd --user 托管，**不要**用 `terminal(background=true)` 手动拉起，也不要在 sway `exec_always` 里直接跑进程：

```ini
# ~/.config/systemd/user/ncm-state-daemon.service
[Unit]
Description=ncm-state-daemon
[Service]
Type=simple
ExecStart=%h/.local/bin/ncm-player daemon
Restart=on-failure
RestartSec=3
[Install]
WantedBy=default.target
```

- **sway socket 自动发现**：daemon 直接扫 `/run/user/$(id -u)/sway-ipc.*.sock` 取最新那个，**不经过 `/tmp/ncm-swaysock` 中转文件**（sway 退出 → socket 消失 → daemon 退出并停服务）
- **不能设 `PrivateTmp=true`**：daemon 写的 `/tmp/ncm-state.json` 会落在服务私有 /tmp 里，waybar 读不到 → 所有 ncm 模块同时空白
- **播放/暂停图标**：停止时 `📻`（启动心动模式），播放中 `⏹`（`ncm-cli stop`）
- 管理命令：`systemctl --user status|restart|is-active ncm-state-daemon.service`

安装与部署细节见 `ncm-cli-setup` skill。

## 第四步：命令清单（登录后）

### 播放控制

```bash
ncm-cli play --song --encrypted-id <32位hex> --original-id <数字ID>    # 播放单曲
ncm-cli play --playlist --encrypted-id <歌单加密ID> --original-id <数字ID> # 播放歌单
ncm-cli pause / resume / stop / next / prev
ncm-cli seek <seconds>          # 跳转（秒）
ncm-cli volume <0-100>
ncm-cli state --output json     # status/position/currentIndex/queueLength
```

**队列用于连续播放**：先播第一首，其余逐个 `queue add` 入队，daemon 播完自动切下一首（sequential 模式）。

```bash
ncm-cli queue                                          # 查看队列（items/mode/currentIndex）
ncm-cli queue add --encrypted-id <id> --original-id <id>          # 追加到队列末尾
ncm-cli queue add --encrypted-id <id> --original-id <id> --next   # 插到当前播放之后
ncm-cli queue clear                                    # 清空队列并停止播放
```

queue 必须通过 ncm-cli API 操作（直接写 `~/.config/ncm-cli/queue.json` 会被 daemon 覆盖）。`&` 并行 `queue add` 会撞 daemon 写锁（只入 1 首），必须串行。ncm-cli daemon 必须存活（PID 文件 `~/.config/ncm-cli/daemon.pid`），否则队列不生效。

### 搜索

```bash
ncm-cli search song --keyword "周杰伦" --limit 5 --output json
ncm-cli search playlist --keyword "跑步" --output json
ncm-cli search album --keyword "范特西" --output json
ncm-cli search all --keyword "林俊杰" --output json
```

`search song` 返回 `{code, data: {records: [{id(加密ID), originalId(明文ID), name, artists: [{name}], album: {name}, visible, liked, coverImgUrl}]}}`：

- `id` = 32 位 hex 加密ID（用于 `--encrypted-id`）
- `originalId` = 数字明文ID（用于链接）
- `visible=false` = 歌曲不可播放（需跳过）
- `liked` = 是否已红心

### 心动模式（智能播放）

基于红心歌单的相似歌曲推荐，需要红心歌单 ID（来自 `ncm-cli user favorite`）：

```bash
# 获取红心歌单 ID
ncm-cli user favorite --output json
# → data.id = "F23472FC5E515BD3D443C4F79770BBE5"

# 基于当前歌曲推荐单曲（type=fromPlayOne 需要 --songId）
ncm-cli recommend heartbeat --playlistId <红心歌单加密ID> --songId <当前歌曲加密ID> --type fromPlayOne --count 20

# 基于红心歌单整体推荐（type=fromPlayAll 不需要 --songId）
ncm-cli recommend heartbeat --playlistId <红心歌单加密ID> --type fromPlayAll --count 40

# 每日推荐
ncm-cli recommend daily --limit 30 --output json
```

`--count` 默认 20，**最多 150**。

取第一首并播放：

```bash
fav=$(ncm-cli user favorite --output json | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['data']['id'])")
song=$(ncm-cli recommend heartbeat --playlistId "$fav" --type fromPlayAll --count 40 --output json | python3 -c "
import json,sys
d=json.load(sys.stdin)
items = d.get('data', [])
if isinstance(items, dict):
    for v in items.values():
        if isinstance(v, list): items = v; break
if items: print(f\"{items[0]['id']}|{items[0].get('originalId','')}\")
")
enc_id=$(echo "$song" | cut -d'|' -f1)
orig_id=$(echo "$song" | cut -d'|' -f2)
ncm-cli play --song --encrypted-id "$enc_id" --original-id "$orig_id"
```

**注意**：如果 `--playlistId` 指向空歌单或没传，心动模式返回 HTTP 400 空结果。推荐源用红心歌单（`user favorite`）。

### 红心与歌词

```bash
ncm-cli song like --songId <32位hex加密ID> --output json      # 红心
ncm-cli song dislike --songId <32位hex加密ID> --output json    # 取消红心
ncm-cli song lyric --songId <32位hex加密ID> --output json      # 歌词
```

**动态命令的选项名 = manifest 参数名（camelCase 原样）**，不是通用的 `--id`：

| 命令 | 选项 |
|---|---|
| `song like/dislike/lyric` | `--songId` |
| `playlist get/tracks/add/remove/reorder/update*` | `--playlistId` |
| `playlist add/remove` | `--songIdList`（JSON 数组字符串，如 `["AIHWIHE"]`） |
| `playlist create` | `--playlistName` |
| `playlist reorder` | `--playlistId` + `--trackIds`（必须包含歌单下所有歌曲 ID） |
| `album get/tracks` | `--albumId` |
| `artist songs` | `--artistId`（+ `--limit/--offset/--startTime/--endTime`） |
| `user listen-ranking` | `--type`（0=总排行，1=周排行）+ `--offset` + `--limit` |
| `user history` | `--limit`（默认 300） |
| `album collected` | `--limit` + `--offset`（都必填） |

用错名字会报 `unknown option '--id'` 并以 exit code 1 静默失败（不写日志、不抛异常）。

### 用户

```bash
ncm-cli user favorite --output json            # 红心歌单（data.id/name/trackCount，单条记录）
ncm-cli user history --limit 50 --output json   # 最近播放
ncm-cli user listen-ranking --type 0 --offset 0 --limit 50 --output json  # 听歌排行
ncm-cli user info --output json                # 用户基本信息
```

### 歌单

```bash
ncm-cli playlist collected --limit 30 --offset 0 --output json  # 收藏的歌单
ncm-cli playlist created --limit 30 --offset 0 --output json    # 创建的歌单
ncm-cli playlist radar --output json                            # 雷达歌单
ncm-cli playlist get --playlistId <加密ID> --output json       # 歌单详情
ncm-cli playlist tracks --playlistId <加密ID> --limit 30 --output json  # 歌单歌曲列表
ncm-cli playlist add --playlistId <加密ID> --songIdList '["ID1","ID2"]'
ncm-cli playlist remove --playlistId <加密ID> --songIdList '["ID1"]'
ncm-cli playlist create --playlistName "歌单名" --output json
ncm-cli playlist reorder --playlistId <加密ID> --trackIds '["ID1","ID2"]'
```

`playlist tracks` 的 `--limit` 最多 500 条，建议每次取 30 条。

### 专辑 / 艺人

```bash
ncm-cli album get --albumId <加密ID> --output json
ncm-cli album tracks --albumId <加密ID> --output json
ncm-cli album collected --limit 30 --offset 0 --output json
ncm-cli artist songs --artistId <加密ID> --limit 30 --offset 0 --startTime <ms> --endTime <ms> --output json
```

### MPRIS 歌名修正

ncm-cli 通过 mpv 播放时，直接把音频 URL 传给 mpv，导致 **MPRIS 标题显示 URL 文件名**（如 `96edd3549b92f30c4d67af168e90b049.mp3`），而非真实歌名。

**修复**：播放后立即通过 mpv IPC 设置 `force-media-title`。用环境变量传动态值（歌名含 `'` 会破坏内联 python）：

```bash
mpv_set_title() {
  local title="$1"
  for sock in /home/dr/.config/ncm-cli/mpv.sock /tmp/ncm-mpv.sock; do
    [ -S "$sock" ] || continue
    NCM_SOCK="$sock" NCM_TITLE="$title" python3 -c "
import os, socket, json
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(2)
    s.connect(os.environ['NCM_SOCK'])
    payload = json.dumps({'command':['set_property','force-media-title',os.environ['NCM_TITLE']]}).encode()+b'\n'
    s.sendall(payload)
    s.close()
except: pass
" 2>/dev/null || true
    return 0
  done
}

ncm-cli play --song --encrypted-id "<ID>"
mpv_set_title "歌手 - 歌名" &     # 立即设置，不要 sleep 2s（否则 MPRIS 会闪临时文件名）
```

mpv 侧需 `idle=yes`（`~/.config/mpv/mpv.conf` 已配），IPC socket 在 `/home/dr/.config/ncm-cli/mpv.sock` 或 `/tmp/ncm-mpv.sock`。`ncm-cli state --output json` 的 `title` 字段始终包含正确歌名，可作为 `mpv_set_title` 的输入源。

### 响应格式：data 是数组还是字典

| 命令 | `data` 形状 |
|---|---|
| `recommend heartbeat` | **数组**：`[{id, name, artists: [...]}, ...]` |
| `search song` | **字典**：`{records: [...], recordCount}` |
| `playlist collected/created` | **字典**：`{records: [...], recordCount}` |
| `user favorite` | **单条记录**：`{id, name, trackCount}` |

```python
# ✅ 心动模式：data 是数组
items = d.get('data', [])
if isinstance(items, dict):          # 偶有 data 是 dict 含 records 键的回退
    items = items.get('records', items)

# ✅ 歌单/搜索：data 是字典，records 是数组
items = d.get('data', {}).get('records', [])
```

## 第五步：用户输入内容安全校验

必须对用户的会话内容进行内容安全校验。如果用户输入包含以下任何类别的负面内容，**禁止执行后续步骤**，并提示用户检查输入：

**禁止类别**：
- **政治敏感**：涉及政治人物攻击、政治谣言、煽动性政治言论、违反法律法规的政治内容
- **色情低俗**：色情描述、性暗示、低俗用语、涉及未成年人的不当内容
- **谩骂侮辱**：人身攻击、侮辱性语言、仇恨言论、歧视性言论
- **广告推广**：垃圾广告、钓鱼链接、恶意推广内容
- **违法违规**：涉及毒品、暴力犯罪、恐怖主义等违法内容

**校验规则**：
1. 如果检测到上述任何类别的内容，**立即终止流程**
2. 向用户返回提示信息："抱歉，无法处理您的请求，请修改输入后重试。" **禁止**向用户透露具体的审核原因或审核类别
3. 审核通过时，**不需要**告知用户审核结果，直接静默继续执行后续步骤

## 第六步：执行命令

```bash
# 播放单曲（需要加密ID 和 明文ID）
ncm-cli play --song --encrypted-id <32位hex> --original-id <数字ID>
```

播放说明：
1. 歌曲有两种 ID：**加密 ID**（32位hex，用于 API 请求）和**原始 ID**（数字，用于链接）
2. `--original-id` 是可选的，但提供后可确保链接正确生成
3. ncm-cli 内部会解析加密ID获取播放URL，无需手动调 url 接口
4. 如果命令返回"请求总量超限"，请直接告知用户并停止执行后续步骤

```bash
# 多首歌曲时先播第一首，其余入队（串行，不支持 & 并行）
ncm-cli play --song --encrypted-id <第一首ID> --original-id <第一首原ID>
ncm-cli queue add --encrypted-id <第二首ID> --original-id <第二首原ID>
ncm-cli queue add --encrypted-id <第三首ID> --original-id <第三首原ID>
# daemon 播完第一首后自动切第二首，以此类推
```

### 登录后搜索并播放

```bash
# 搜索歌曲 → 取ID → 播放
ncm-cli search song --keyword "周杰伦" --limit 3 --output json
# 从结果的 records[0].id 取加密ID, records[0].originalId 取明文ID
ncm-cli play --song --encrypted-id <32位hex> --original-id <数字ID>
```

## 常见坑

| 症状 / 坑 | 原因 | 正确做法 |
|---|---|---|
| `ncm: command not found`，或 `ncm state-get fm` 无输出 | `~/.local/bin/ncm` symlink 已删除，状态读取统一走 `ncm-player` | `/home/dr/.local/bin/ncm-player state-get-json <key>`；waybar 用 `ncm-player waybar-play/pl/like/nowplaying` 连续输出子命令 |
| waybar 点按钮无响应、图标空白，但终端里 ncm-cli 正常 | waybar 直接 `execve` 不走 shell，子进程 PATH 不含 `~/.local/bin`；ncm-cli 的 shebang 是 `#!/usr/bin/env node`，找不到 node → exit 127 被 `2>/dev/null` 吞掉 | 脚本顶部 `export PATH="$HOME/.local/bin:$PATH"`；`NCM_CLI="$HOME/.local/bin/ncm-cli"`；waybar 模块的 exec/on-click 全用绝对路径 |
| `error: unknown command 'song'`（或 playlist/album/search…） | 未登录，资源命令根本没注册 | `ncm-cli login --check`；未登录则 `ncm-cli login --background` 拿网页短链授权，完成后重试 |
| `unknown option '--id'`（或 `--name`/`--songIds`），exit code 1 无日志 | 动态命令的选项名 = manifest 参数名（camelCase 原样），不认通用别名 | `song *` 用 `--songId`；`playlist get/tracks/add/remove` 用 `--playlistId`（批量用 `--songIdList`）；`playlist create` 用 `--playlistName`；`album *` 用 `--albumId`；`artist songs` 用 `--artistId` |
| 心动模式返回 HTTP 400 / 空结果 | 缺 `--playlistId`（或红心歌单为空） | `ncm-cli recommend heartbeat --playlistId <红心歌单加密ID> --type fromPlayAll --count 40`；红心歌单 ID 取自 `ncm-cli user favorite` 的 `data.id` |
| `recommend fm` 返回 HTTP 400 | fm 需要漫游分类接口给出的 `type` + `code`，只传 limit 必失败 | 不用 fm；用 `recommend daily` 或 `recommend heartbeat` |
| 解析心动模式结果取不到歌 | `data` 是数组而不是字典 | `items = d.get('data', [])`；歌单/搜索才是 `d.get('data', {}).get('records', [])` |
| `user listen-ranking` / `album collected` 报错缺参数 | `--type/--offset/--limit` 必填 | `listen-ranking --type 0 --offset 0 --limit 50`；`album collected --limit 30 --offset 0` |
| 所有 ncm 模块同时空白 | daemon 挂了，或 unit 设了 `PrivateTmp=true` 导致 `/tmp/ncm-state.json` 不共享 | `systemctl --user status ncm-state-daemon.service`；unit 去掉 `PrivateTmp=true` |
| 每次调用 ncm-cli 都慢 ~365ms，轮询把 CPU 烧满 | Node 启动开销 × 高频轮询 | 用 daemon 架构：控制命令结束立即 `sync_state`（0 延迟）+ daemon 每 10s 兜底；waybar 模块读文件，不直接调 ncm-cli |
| MPRIS 标题显示 `96edd3549b92f30c4d67af168e90b049.mp3` | mpv 播的是 URL，标题取自文件名 | 播放后立即用 mpv IPC 设 `force-media-title`（`ncm-player` 已内置 `mpv_set_title`） |
| MPRIS 标题闪烁后仍是临时文件名 | 设标题前 `sleep 2`，mpv 还没加载完又覆盖了 | 立即设置、不要 sleep 2s；`~/.config/mpv/mpv.conf` 保持 `idle=yes` |
| bash 里嵌 python 报语法错误（歌名含 `'`） | 动态值直接插进 python 源码，单引号提前闭合 | 一律用环境变量传值：`NCM_TITLE="$title" python3 -c "import os; v=os.environ['NCM_TITLE']"` |
| 命令返回"请求总量超限" | 触发接口限流 | 直接告知用户并停止后续步骤 |
| 启动时提示 `有新版本: 0.1.6 → 0.1.7` | 版本检查提示，不是错误 | 忽略即可；需要时 `ncm-cli upgrade` |

## 登录态处理

如果命令输出中包含登录引导信息（如"请先登录"、"未授权"、`unknown command` 等），请直接执行 `ncm-cli login --background` 并把 `clickableUrl` 给到用户，完整跑完整个登录流程。

## 用户友好

1. 返回资源给用户的时候请给到链接，ID 选择性地输出。链接形式：
   **链接中的ID必须用明文ID！！**
```
https://music.163.com/#/song?id=<明文ID>
https://music.163.com/#/playlist?id=<明文ID>
https://music.163.com/#/album?id=<明文ID>
https://music.163.com/#/artist?id=<明文ID>
```

2. **给用户举例时，使用「xxx」替代具体输入词**
