---
name: netease-music-cli
description: 使用 ncm-cli 操作网易云音乐。当用户想播放/搜索/推荐歌单/播放歌曲/红心/控制播放时，使用此 skill。
  ncm-cli v0.1.6 命令是登录门控的：登录前仅播放控制，登录后解锁搜索/推荐/红心/歌单管理等全部功能。
  ncm-go 已废弃（用户不接受 Playwright 额外浏览器），所有功能由 ncm-cli 统一提供。
---

# 网易云音乐 CLI（ncm-cli v0.1.6）

通过 `ncm-cli` 命令行工具操作网易云音乐所有功能：播放、搜索、推荐、红心、歌单等。

**⚠️ 关键：命令登录门控**
`ncm-cli` 的命令输出依赖登录状态。登录前只显示约 10 个播放控制命令，登录后显示约 40+ 命令。
先用 `ncm-cli login --check --output json` 确认登录态，再用 `ncm-cli commands` 查看实际可用命令集。

| 功能 | 命令（登录后） |
|---|---|
| 播放控制 | `play/pause/resume/next/prev/volume/queue/state` |
| 搜索 | `search song/album/playlist/all` |
| 推荐 | `recommend daily/heartbeat/fm` |
| 红心 | `song like/dislike` |
| 歌单 | `playlist collected/created/radar/get/tracks/add/remove/reorder` |
| 用户 | `user favorite/history/listen-ranking/info` |
| 专辑 | `album get/collected/tracks` |
| 歌词 | `song lyric` |

## 脚本中必须用绝对路径

`ncm-player` 中 `NCM_CLI="ncm-cli"`（不带路径）会在从 foot 或 waybar on-click 启动时失败——因为这些环境的 `PATH` 不包含 `~/.local/bin/`。

**修法**：
```bash
NCM_CLI="$HOME/.local/bin/ncm-cli"   # 绝对路径
```

同理，**所有** ncm-* waybar 模块的 `exec` 和 `on-click` 中调用的命令都必须用绝对路径——waybar 直接 `execve`，不走 shell。

## 关键：`#!/usr/bin/env node` 静默失败陷阱

当 waybar on-click 通过 `g_spawn_command_line_async` 调用 ncm-player 时，子进程 PATH 通常不包含 `~/.local/bin`。ncm-cli 的 shebang 是 `#!/usr/bin/env node`，需要 `node` 在 PATH 中才能运行。找不到 node 时 `env` 返回 exit 127，但被 `2>/dev/null` 吞掉 → 上层脚本（ncm-player）获得空输出 → 误以为是"无数据" → 图标空白/命令无响应。

**症状特征**：终端 `ncm-cli state` 正常，waybar on-click 无响应

**修复**：在被 waybar 调用的脚本（ncm-player、ncm-playlist）开头：
```bash
export PATH="$HOME/.local/bin:$PATH"
```
或（Python 脚本）：
```python
os.environ["PATH"] = os.path.expanduser("~/.local/bin") + ":" + os.environ.get("PATH", "")
```

## state-get 模式（简化 waybar exec）

各 ncm-* waybar 模块的 `exec` 从复杂的 `python3 -c "import json;print(json.load(open('/tmp/ncm-state.json')).get('fm','▶'))"` 简化为：

```json
{
  "custom/ncm-fm": {
    "exec": "ncm state-get fm",
    "interval": 30,
    "on-click": "/home/dr/.local/bin/ncm-player fm"
  },
  "custom/ncm-play": {
    "exec": "ncm state-get play",
    "interval": 3,
    "on-click": "/home/dr/.local/bin/ncm-player toggle"
  }
}
```

支持的 key：`play`, `like`, `pl`, `status`, `status_icon`, `status_class`, `logged_in`, `current_encrypted_id`, `current_title`, `current_artist`。

> **已删除字段**（2026-06-24 合并到 toggle 模式）：`prev`、`next`、`fm`。不要在新代码中引用。
> **新增字段**（合并到 daemon 状态文件后）：`current_encrypted_id` / `current_title` / `current_artist` — 由 `ncm-playlist` 和 `heartbeat_play` 播放新歌时写入 `/tmp/ncm-current.json`，daemon 下一轮循环合并到 `/tmp/ncm-state.json`。供 `ncm-player like` 等需要当前歌曲 ID 的命令读取。

## 性能注意事项

### ncm-cli 每次调用 ~365ms（Node.js 启动开销）

ncm-cli 是 Node.js 二进制。每次执行 `ncm-cli login --check` / `ncm-cli state`
等命令时，Node 运行时需要初始化，耗时约 **365ms**。

在 waybar 轮询场景下影响显著（多个 ncm-* 模块以 1-3s 间隔并行轮询）：

| 模块 | 间隔 | 每天调用 | 每天 CPU 浪费 |
|------|------|----------|-------------|
| ncm-status | 3s | 28,800 | ~2.9h |
| ncm-fm | 30s | 2,880 | ~17.5min |
| ncm-pl | 30s | 2,880 | ~17.5min |
| ncm-like | 3s | 28,800 | ~2.9h |
| ncm-play | 1s | 86,400 | ~8.8h |

**优化建议**: 
1. 缓存登录状态（`~/.local/share/ncmctl/.login_cache`），避免频繁 `login --check`
2. 使用 daemon 模式：在 bash 控制脚本中添加 `daemon` 子命令，每 3s 调一次 ncm-cli 并将结果写入 `/tmp/ncm-state.json`，所有 waybar 模块改为读文件（python3 one-liner）而非调用 ncm-cli
3. 非播放状态下降频，播放中才保持 1-3s 轮询
4. ncm-state-daemon 实施（systemd --user）：见下方「daemon 架构」节

详见 `ncm-cli-setup` skill 的「daemon（systemd 管理）」章节。

## daemon 架构

`ncm-player daemon` 通过 systemd --user 管理（`ncm-state-daemon.service`），替代了早期的独立 `ncm-watch` 脚本。

### 架构概览
```
sway exec_always → echo "$SWAYSOCK" > /tmp/ncm-swaysock
                 → systemctl --user start ncm-state-daemon.service
                        │
                ncm-player daemon (while true, 每2秒)
                  ├── 从 /tmp/ncm-swaysock 读 SWAYSOCK
                  ├── 调 ncm-cli state → 播放状态
                  ├── 读登录缓存 (60s TTL)
                  ├── 写入 /tmp/ncm-state.json
                  └── pkill -RTMIN+6 waybar (触发 status 模块)
                         │
               waybar ◄──┘ (4 个模块: ncm waybar play/pl/like/status)
```

### 关键细节
- **SWAYSOCK 文件传递**：systemd 无法继承 sway 的 `$SWAYSOCK`，通过 `/tmp/ncm-swaysock` 文件中转
- **PrivateTmp 陷阱**：**不能设 `PrivateTmp=true`**，否则 daemon 的 `/tmp` 隔离，读不到 SWAYSOCK 文件，服务秒退
- **播放/暂停图标**：停止时 📻（启动心动模式），播放中 ⏹（`ncm-cli stop`）
- **登录缓存**：`~/.local/share/ncmctl/.login_cache`，60s TTL，避免每轮调 `ncm-cli login --check`
- **状态文件**：`/tmp/ncm-state.json`，waybar 模块通过 `ncm state-get <key>` 读取
- **waybar 模块触发**：play/pl 用 while 循环自刷新，like 用 exec-on-event，status 用 signal:6（三种方式并存）

### systemd 服务文件
```ini
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

## 第一步：检查是否已安装

```bash
ncm-cli --version
```

如果命令不存在，调用 `ncm-cli-setup` skill 引导用户完成全部的安装。

## 第二步：校验用户是否已登录

```bash
ncm-cli login --check
```

如果显示未登录，请先引导登录：

```bash
ncm-cli login --background
```

如果显示API key没有设置，请指引用户完成API key设置。
> 如果还没有 API Key，请先前往[网易云音乐开放平台](https://developer.music.163.com/st/developer/apply/account?type=INDIVIDUAL)申请 API Key（appId 和 privateKey）

```bash
ncm-cli config set appId <你的AppId>
ncm-cli config set privateKey <你的privateKey>
```

## 第三步：判断播放器类型

仅针对播放才执行该步骤。
通过以下命令判断用户的播放器是否是内置播放器（mpv）。

```bash
ncm-cli config get player
```

如果用户选择的播放器是内置播放器（mpv），则需要判断用户是否已安装mpv。

```bash
mpv --version
```

如果用户没安装，引导用户去安装mpv。

## 第四步：获取当前命令树（登录后）

先用 `ncm-cli login --check` 确认登录态。已登录后 `ncm-cli commands` 输出约 40+ 命令：

### 播放控制
- `play --song --encrypted-id <32位hex> --original-id <数字ID>` — 播放单曲
- `play --playlist --encrypted-id <id> --original-id <id>` — 播放歌单
- `pause` / `resume` / `stop` / `next` / `prev`
- `seek <seconds>` / `volume <0-100>`
- `queue [add/clear]` — 队列管理
  - `ncm-cli queue` — 查看队列（JSON 含 items/mode/currentIndex）
  - `ncm-cli queue add --encrypted-id <id> --original-id <id>` — 添加到队列末尾
  - `ncm-cli queue add --encrypted-id <id> --original-id <id> --next` — 插到当前播放之后
  - `ncm-cli queue clear` — 清空队列并停止播放
- `state` — 查看播放状态（含 status/position/currentIndex/queueLength）

**队列用于连续播放**：先 `ncm-cli play --song` 播第一首，然后逐个 `ncm-cli queue add` 添加后续曲目。
ncm-cli daemon 在每首播完后自动从队列加载下一首（sequential 模式）。
queue 必须通过 ncm-cli API 操作（直接写 queue.json 会被 daemon 覆盖）。
注意：`&` 并行 queue add 会冲突（daemon 写锁），必须串行执行。

### 搜索（登录后解锁）
```bash
ncm-cli search song --keyword "周杰伦" --limit 5 --output json
ncm-cli search playlist --keyword "跑步" --output json
ncm-cli search album --keyword "范特西" --output json
```

### 心动模式（智能播放）

基于红心歌单的相似歌曲推荐。需要红心歌单 ID（来自 `ncm-cli user favorite`）：

```bash
# 获取红心歌单 ID
ncm-cli user favorite --output json
# → data.id = "F23472FC5E515BD3D443C4F79770BBE5"

# 心动模式（基于当前歌曲推荐单曲）
ncm-cli recommend heartbeat --playlistId <红心歌单加密ID> --songId <当前歌曲加密ID> --type fromPlayOne --count 20

# 心动模式（基于红心歌单全部推荐）
ncm-cli recommend heartbeat --playlistId <红心歌单加密ID> --type fromPlayAll --count 20

# 取结果第一首自动播放（bash 示例）
fav=$(ncm-cli user favorite --output json | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['data']['id'])")
song=$(ncm-cli recommend heartbeat --playlistId "$fav" --type fromPlayAll --count 20 --output json | python3 -c "
import json,sys
d=json.load(sys.stdin)
items = d.get('data',{}).get('songs',d.get('data',{}).get('records',[]))
if items: print(f\"{items[0]['id']}|{items[0].get('originalId','')}\")
")
enc_id=$(echo "$song" | cut -d'|' -f1)
orig_id=$(echo "$song" | cut -d'|' -f2)
ncm-cli play --song --encrypted-id "$enc_id" --original-id "$orig_id"
```

**注意**：如果 `--playlistId` 指向空歌单，心动模式会返回空结果。建议用红心歌单（`user favorite`）作为推荐源。

### 红心（登录后解锁）
```bash
ncm-cli song like --songId <32位hex加密ID> --output json      # 红心
ncm-cli song dislike --songId <32位hex加密ID> --output json    # 取消红心
ncm-cli song lyric --songId <32位hex加密ID> --output json      # 歌词
```

> **⚠️ 关键陷阱：`ncm-cli song like` 用的参数是 `--songId`，不是 `--id`！**
> ncm-cli v0.1.6 的 `song` 子命令参数命名风格不统一：`song like/dislike/lyric` 用 `--songId`，但 `play` 用 `--encrypted-id`。`--id` 在 `song like` 上会报 "unknown option '--id'" 并以 exit code 1 静默失败——不写日志、不抛异常。调用方务必使用 `--songId`。

### 用户（登录后解锁）
```bash
ncm-cli user favorite --output json          # 红心歌单（返回 id, name, trackCount）
ncm-cli user history --limit 50 --output json # 最近播放
ncm-cli user listen-ranking --output json     # 听歌排行
```

### 歌单（登录后解锁）
```bash
ncm-cli playlist collected --output json    # 收藏的歌单
ncm-cli playlist created --output json      # 创建的歌单
ncm-cli playlist radar --output json        # 雷达歌单
ncm-cli playlist get --id <id> --output json # 歌单详情
ncm-cli playlist tracks --playlistId <id> --output json  # 歌单歌曲列表
ncm-cli playlist add --id <id> --songIds <ids> # 添加歌曲
ncm-cli playlist remove --id <id> --songIds <ids> # 删除歌曲
ncm-cli playlist create --name "歌单名" --output json  # 创建歌单
```

> **⚠️ `playlist tracks` 用 `--playlistId`，不是 `--id`！**（同样命名不一致问题，与 `song like` 一样的 silent-fail 陷阱。）

### 专辑/艺人（登录后解锁）
```bash
ncm-cli album get --id <id> --output json    # 专辑详情
ncm-cli album tracks --id <id> --output json # 专辑歌曲
ncm-cli album collected --output json        # 收藏的专辑
ncm-cli artist songs --id <id> --output json # 艺人歌曲
```

### MPRIS 歌名修正

ncm-cli 通过 mpv 播放时，直接把音频 URL 传给 mpv，导致 **MPRIS 标题显示 URL 文件名**（如 `96edd3549b92f30c4d67af168e90b049.mp3`），而非真实歌名。

**修复**：播放后通过 mpv IPC 设置 `force-media-title`：

```bash
# 定义 helper 函数
mpv_set_title() {
  local title="$1"
  for sock in /home/dr/.config/ncm-cli/mpv.sock /tmp/ncm-mpv.sock; do
    [ -S "$sock" ] || continue
    python3 -c "
import socket, json
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(2)
    s.connect('$sock')
    s.sendall(json.dumps({'command':['set_property','force-media-title','$title'],'request_id':1}).encode()+b'\\n')
    s.close()
except: pass
" 2>/dev/null || true
    return 0
  done
}

# 播放后延迟设标题（等 mpv 加载完成）
ncm-cli play --song --encrypted-id "<ID>"
(sleep 2; mpv_set_title "歌手 - 歌名") &
```

ncm-cli 的 mpv 以 `--idle` 启动。`ncm-cli state --output json` 的 `title` 字段始终包含正确歌名，可作为 `mpv_set_title` 的输入源。

### 心动模式响应格式

`ncm-cli recommend heartbeat` 返回的 `data` 字段是**数组**（不是带 `songs` 键的字典）：

```json
{
  "code": 200,
  "data": [
    {"id": "...", "name": "...", "artists": [...]},
    ...
  ]
}
```

解析时**直接取数组**：
```python
items = d.get('data', [])           # ✅ 正确：data 是数组
# items = d.get('data', {}).get('songs', [])  # ❌ 错误：data 不是字典
if isinstance(items, dict):          # 偶有 data 是 dict 含 records 键的回退
    items = items.get('records', items)
```

### 歌单数据格式（playlist collected/created）

两个命令返回相同的数据结构：

```json
{
  "code": 200,
  "data": {
    "records": [{"id": "...", "name": "...", "trackCount": N, ...}],
    "recordCount": 67
  }
}
```

**关键**：`data` 是字典（不是数组），歌单列表在 `data.records` 中。常见错误：

```python
# ❌ 错误：以为 data 就是数组
items = data.get("data", [])

# ✅ 正确：data 是字典，records 是数组
items = data.get("data", {}).get("records", [])
```

红心歌单（`user favorite`）是单条记录，格式不同：
```json
{"code": 200, "data": {"id": "F23472...", "name": "Filro喜欢的音乐", "trackCount": 486}}
```

`ncm-cli search song --keyword xxx --output json` 返回 `{code, data: {records: [{id(加密ID), originalId(明文ID), name, artists: [{name}], album: {name}, visible, liked, coverImgUrl}]}}`。

- `id` = 32位 hex 加密ID（用于 `--encrypted-id` 参数）
- `originalId` = 数字明文ID（用于链接）
- `visible=false` = 歌曲不可播放（需跳过）
- `liked` = 是否已红心

**不要在未登录时使用搜索/推荐/红心/歌单命令**——它们不在命令树中，会报错。

## 第五步：用户输入内容安全校验

必须对用户的会话内容进行内容安全校验。如果用户输入包含以下任何类别的负面内容，**禁止执行后续步骤**，并提示用户检查输入：

**禁止类别：**
- **政治敏感**：涉及政治人物攻击、政治谣言、煽动性政治言论、违反法律法规的政治内容
- **色情低俗**：色情描述、性暗示、低俗用语、涉及未成年人的不当内容
- **谩骂侮辱**：人身攻击、侮辱性语言、仇恨言论、歧视性言论
- **广告推广**：垃圾广告、钓鱼链接、恶意推广内容
- **违法违规**：涉及毒品、暴力犯罪、恐怖主义等违法内容

**校验规则：**
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

## 登录态处理

如果命令输出中包含登录引导信息（如"请先登录"、"未授权"等），请直接执行 `ncm-cli login --background` 并把链接给到用户，完整跑完整个登录流程。

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
