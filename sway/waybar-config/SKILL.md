---
name: waybar-config
description: "Manage Waybar configuration — launcher buttons, custom modules, module ordering, PWA sync, and consolidated waybar pitfalls (interval throttling, exec PATH, emoji rendering, height warnings, format-icons)."
---

## Waybar Configuration Management

Workflow for maintaining Waybar config files (`~/.config/waybar/config-top`, `config-bottom`, `style.css`).

### 核心原则：配置文件不写逻辑，代码统一进脚本

> **waybar 配置文件（JSON）只做声明——声明 exec 调哪个脚本、on-click 跑什么命令。所有时序、循环、条件判断、状态读取必须放在独立的脚本文件里。**
>
> 这不是可选项。理由：
> 1. **waybar 配置无法退出循环**。如果 while 写在 config 里，你没法管理这个进程（kill、restart、debug）
> 2. **配置不支持注释**。JSON 没有注释，写复杂逻辑等于不留文档
> 3. **修改配置需要 reload waybar，影响全部模块**。改脚本只影响单一模块
> 4. **agent 擅长写脚本，不擅长改 JSON**。控制逻辑集中在脚本里，agent 可以灵活调整循环周期、条件分支、错误恢复

### 反面示例（不要在 waybar 配置里写这个）

```json
// ❌ 错误：把 while 循环逻辑写在 waybar 配置里
"exec": "while true; do python3 -c \"...\"; sleep 2; done"

// ❌ 错误：复杂的内联 Python
"exec": "python3 -c \"import json;print(json.load(open('/tmp/state.json')).get('play',''))\""
```

### 正确做法

```json
// ✅ 正确：waybar 配置只声明调用哪个脚本
"exec": "ncm waybar play",
"on-click": "/home/dr/.local/bin/ncm toggle"

// ncm-player 脚本内部管理所有逻辑
//   waybar)
//     play)   while true; do ncm state-get play; sleep 2; done ;;
//     like)   ncm state-get like ;;
//     status) ncm state-get status_icon ;;
```

## Signal-based module update（避免 interval 轮询）

> **更推荐的方式**：用 `signal` 替换 `interval`，避免 waybar 内部轮询浪费 CPU。  \
> 但 **2026-06-24 实战结论**：`interval` + `return-type: json` 更可靠（避开了行缓冲问题）。详见 `references/ncm-module-rework-2026-06-24.md`。

### 原理

```json
"custom/ncm-play": {
    "exec": "ncm state-get play",
    "signal": 10,
    "on-click": "/home/dr/.local/bin/ncm-player toggle"
}
```

- `"signal": 10` → waybar 监听 `SIGRTMIN+10`（Linux 实时信号第 44 号）
- 外部 daemon 写完状态文件后调用：
  ```bash
  pkill -RTMIN+10 waybar
  ```
- waybar 收到信号 → 重跑 `exec` 命令 → 更新显示

### 什么时候用 signal vs interval

| 方式 | 适用场景 | 缺点 |
|------|---------|------|
| `interval` | 模块自己决定更新频率（如时钟、CPU 温度） | 即使数据没变也跑，浪费 CPU |
| `signal` | 外部驱动更新（如播放状态、登录状态） | 需要外部 daemon 发信号 |

### 配置方法

1. 模块配置里写 `"signal": <N>`（N 建议 10-30，避免和系统信号冲突）
2. 确保 daemon 在更新数据后执行：
   ```bash
   pkill -RTMIN+10 waybar 2>/dev/null || true
   ```
3. daemon 发信号的频率就是实际更新频率（无需在 waybar 模块里额外写 `interval`）
4. 初次启动时 waybar 会自动跑一次 `exec`，不需要信号触发

### 一组模块共用一个信号

如果多个自定义模块（播放状态、红心、歌单）都由同一个 daemon 更新，可以共用同一个信号：

```json
"custom/ncm-play":  { "exec": "ncm state-get play", "signal": 10 },
"custom/ncm-like": { "exec": "ncm state-get like", "signal": 10 },
"custom/ncm-pl":   { "exec": "ncm state-get pl",    "signal": 10 }
```

daemon 发一次 `pkill -RTMIN+10 waybar` → 三个模块同时刷新。

### 方法三：while 循环 + stdout 持续输出（⚠️ 谨慎使用，纯 Python 推荐）

> **2026-06-24 实战结论**：连续 exec 模式**可用但需满足两个条件**：(1) `return-type: json` + `format: "{text}"` (2) Python 输出 `print()` 自带 `\n`。**纯 `interval` 模式 toggle 后有 0~2s 视觉延迟**。最终 ncm-* 用了**混合模式**（toggle/pl/like 用连续 exec + JSON，status 用 interval + JSON）。详见 `references/ncm-module-rework-2026-06-24.md` 第四、五根因节。

### 原理

```json
"custom/ncm-play": {
    "exec": "ncm waybar play",
    "exec-on-event": false,
    "on-click": "/home/dr/.local/bin/ncm toggle"
}
```

1. waybar 启动时跑 `exec` 一次，进程常驻（`ncm waybar play` = `while true; do ncm state-get play; sleep 2; done`）
2. 脚本内部 `while` 循环，每 2 秒输出一行到 stdout
3. waybar 收到新的 stdout 行就更新显示
4. 省掉 `interval`、`signal`、daemon 的信号发送——全部由脚本自己负责
5. **`exec-on-event: false`** 让 click 事件不重启脚本（默认 true 会在每次 on-click 后重新 exec）

### 五种触发方式完整对比

| 方式 | 配置 | 控制权 | 适用场景 | 容错 |
|------|------|--------|---------|------|
| `interval: N` | 定时轮询 | waybar | 数据自主变化（时钟、CPU温度） | waybar 每次重新跑，天然容错 |
| `signal: N` | 外部信号 | daemon 发 SIGRTMIN+N | 外部事件驱动 | daemon 挂了信号不到，模块卡死 |
| **while 循环 stdout** | **无 interval/signal，exec 进程常驻** | **脚本自控** | **所有场景，尤其 agent 可控** | **脚本崩溃后模块卡死在最后输出** |
| `exec-if:` | 条件执行 | exec-if 的 exit code | 登录态门控（未登录时不启动 exec） | 每次 interval 重新评估 |
| `exec-on-event:` | 点击后重跑 | waybar | 交互式模块（点一下执行一次） | 默认 true，每次 click 都重启 exec |
| `restart-interval:` | 崩溃重启 | waybar | 配合 while 循环兜底 | 脚本退出后 N 秒自动重启 |

### while 循环 + `exec-on-event: false` 最佳实践

```
自定义模块
  ├─ exec: ncm waybar <module>        ← while 常驻进程，自控时序
  ├─ exec-on-event: false             ← click 不重启循环
  ├─ restart-interval: 5              ← 脚本崩溃后 5s 自动重启（可选）
  └─ on-click: /path/to/ncm-player    ← click 事件独立执行，不干扰循环
```

## 集中调度模式（ncm-* 实战）

> **核心原则**：waybar 配置只写"哪个模块调什么脚本"，所有逻辑都在一个集中调度器里。  \
> waybar 配置保持极简。

### 方式 A：`interval` + `return-type: json`（推荐，已验证生产可靠）

**2026-06-24 验证**：ncm-* 模块从 while 循环连续 exec 迁移到此方式后正常工作。

```json
// waybar/config-top — 每个模块独立 interval + return-type: json
"custom/ncm-play":  { "exec": "... ncm-player state-get-json play",  "interval": 2,  "return-type": "json", "format": "{text}" }
"custom/ncm-pl":    { "exec": "... ncm-player state-get-json pl",    "interval": 5,  "return-type": "json", "format": "{text}" }
"custom/ncm-like":  { "exec": "... ncm-player state-get-json like",  "interval": 30, "return-type": "json", "format": "{text}" }
"custom/ncm-status":{"exec": "... ncm-player state-get-json status_icon", "interval": 30, "return-type": "json", "format": "{text}", "signal": 6 }
```

```bash
# ncm-player 中的 state-get-json 子命令
state-get-json)
    key="${2:-}"
    [ -z "$key" ] && { echo '{"text":""}'; exit 0; }
    python3 -c "
import json,sys
d=json.load(open('/tmp/ncm-state.json'))
val = d.get('$key', '')
print(json.dumps({'text': val}))
" 2>/dev/null || echo '{"text":""}'
    ;;
```

**特点**：\n- python3 `print(json.dumps(...))` 自带换行符 → 无行缓冲问题\n- `interval` → 每次重新 fork 进程 → EOF 触发 waybar 更新\n- `return-type: json` → 不走 `fmt::arg` 路径 → 无需纠结 format 问题\n- 每个模块独立 interval → 可根据数据变化频率精细控制\n\n### 方式 C：连续 JSON exec（折衷方案，⏹ toggle 即时反馈）\n\n当需要即时反馈（点击 toggle 后图标立刻变）时使用。同时解决可见性（JSON 格式）和行缓冲（`print()` 自带换行）。\n\n```bash\n# ncm-player 子命令\nwaybar-play)\n    while SWAYSOCK=$(_ncm_current_swaysock); [ -n \"$SWAYSOCK\" ] && [ -S \"$SWAYSOCK\" ]; do\n        \"$0\" state-get-json play  # ← JSON 输出，每行自带 \\n\n        sleep 2\n    done\n    ;;\nwaybar-like)\n    while SWAYSOCK=$(_ncm_current_swaysock); [ -n \"$SWAYSOCK\" ] && [ -S \"$SWAYSOCK\" ]; do\n        # 非播放时隐藏 like 按钮\n        python3 -c \"\nimport json\nd=json.load(open('/tmp/ncm-state.json'))\nif d.get('status') in ('playing','paused'):\n    print(json.dumps({'text': d.get('like','')}))\nelse:\n    print(json.dumps({'text': ''}))\n\" 2>/dev/null || echo '{\"text\":\"\"}'\n        sleep 5\n    done\n    ;;\n```\n\n```json\n// waybar 配置：无 interval，连续 exec + return-type: json\n\"custom/ncm-play\": {\n    \"exec\": \"/home/dr/.local/bin/ncm-player waybar-play\",\n    \"format\": \"{text}\",\n    \"return-type\": \"json\",\n    \"on-click\": \"/home/dr/.local/bin/ncm-player toggle\"\n}\n```\n\n**什么时候用**：toggle 按钮（点击后需要 <1s 反馈）和需要状态门控的模块（如 like 在 stopped 时隐藏）。普通显示模块用 interval + JSON 即可。

此方式曾是推荐方案，但在实际使用中发现可靠性低于 interval + JSON。详见上方「行缓冲陷阱」和 `references/ncm-module-rework-2026-06-24.md`。

```json
// waybar/config-top — 极简
"custom/ncm-play":  { "exec": "ncm waybar play",  "exec-on-event": false, "on-click": "ncm toggle" }
"custom/ncm-pl":    { "exec": "ncm waybar pl",    "exec-on-event": false, "on-click": "ncm pl" }
"custom/ncm-like":  { "exec": "ncm waybar logged" }                                       // exec-on-event 默认 true
"custom/ncm-status":{ "exec": "ncm waybar status", "signal": 6, "on-click": "foot -a ncm-login -W 80x24 -H /home/dr/.local/bin/ncm-player login" }
```

```bash
# ~/.local/bin/ncm-player — 集中调度
waybar)
  module="${2:-}"
  case "$module" in
    play)   while true; do ncm state-get play;       sleep 2;  done ;;
    pl)     while true; do ncm state-get pl;          sleep 5;  done ;;
    logged) sleep 0.5; if $NCM_CLI login --check 2>/dev/null | grep -q '"success": true'; then echo '♡'; else echo ''; fi ;;
    status) ncm state-get status_icon ;;
    *)      echo "用法: ncm waybar {play|pl|logged|status}" >&2; exit 1 ;;
  esac
  ;;
```

**性能对比**：

| 维度 | 方式 A (interval+JSON) | 方式 B (while 循环) |
|------|----------------------|---------------------|
| 每 tick 开销 | 每次 fork 脚本进程 | 脚本常驻，内部循环 |
| 更新机制 | fork → exec → EOF | stdout 行缓冲 → 每 `\n` 更新 |
| 行缓冲风险 | ✅ 无（退出 = EOF） | ❌ 必须保证 `\n` 结尾输出 |
| 文本增长 | ✅ 每次重新输出 | ⚠️ `print(end='')` 无换行时无限积累 |
| 重启代价 | 每次 interval | 需要 waybar 重启或信号 |
```

### 三种触发方式并存展示

| 模块 | 触发 | 配置 | daemon/脚本职责 |
|------|------|------|----------------|
| play | while 循环 | `exec: ncm waybar play`, `exec-on-event: false` | 脚本自循环 2s |
| pl | while 循环 | `exec: ncm waybar pl`, `exec-on-event: false` | 脚本自循环 5s |
| logged | exec-on-event | `exec: ncm waybar logged` | 点击后跑 0.5s + 查登录态 |
| status | signal | `exec: ncm waybar status`, `signal: 6` | daemon `pkill -RTMIN+6 waybar` 触发 |

**为什么四种模块用不同方式**：观察哪个方式的代价最低、反馈最自然。

### 设计要点

- **waybar 配置禁止 inline 代码**（`while`、`case`、`python3 -c "..."` 都不要）— 一律走脚本
- **每个 waybar 模块的 `exec` 走一个集中的 case 处理函数**（如 `ncm waybar <name>`），方便统一调整时序、加 sleep、改 icon
- **NCM_CLI 绝对路径**（`$HOME/.local/bin/ncm-cli`）— waybar 直接 execve，PATH 不含 `~/.local/bin`
- **daemon 的 signal 编号定义为常量**（`STATUS_SIGNAL=6` 写在 ncm-player 顶部），避免与 waybar 配置的 signal 值散落两处不同步
- **stdout 只能输出图标文字**— 操作结果（"已停止"/"❤ 已红心"）走 `>&2` 否则会污染 waybar 模块显示

### Stats 单一真相源原则（最重要的架构原则）

> **不要在 waybar 模块/调度器里"猜"状态，永远从 ncm-cli 读再写缓存。**

设计三层数据流：

```
┌─────────────┐
│ ncm-cli     │ ← 唯一真相源（state + login --check）
└──────┬──────┘
       │ 每次 sync_state 调用读
       ↓
┌─────────────┐
│ sync_state  │ ← 调度器内部 helper（ncm-player）
└──────┬──────┘
       │ 写 /tmp/ncm-state.json + 发 signal
       ↓
┌─────────────┐
│ /tmp/ncm-   │ ← 缓存层（waybar 读这个）
│ state.json  │
└─────────────┘
```

**绝对禁止**：
- ❌ `ncm-player toggle` 自己判断"现在应该是 playing"然后写 `"⏹"` 到缓存
- ❌ daemon 轮询 ncm-cli 后自己 `case $state in playing ...` 算图标
- ❌ 任何缓存写逻辑跳过 ncm-cli 直接判断状态

**必须**：
- ✅ 任何 ncm-cli 控制动作（toggle/play/stop/next/prev/heartbeat）执行后调 `sync_state` —— sync_state 内部调 ncm-cli 读最新状态再写缓存
- ✅ daemon 只做慢兜底（10s 一次），仍然走 sync_state，**不能简化成"我看一眼 daemon 自己写"**
- ✅ 缓存永远是 ncm-cli 的镜像，不是 daemon/ncm-player 的判断

**为什么**：ncm-cli 自己读 mpv IPC，状态永远准。如果 ncm-player 自己"猜"，会出现"ncm-cli state 显示 playing 但图标显示 📻"的撕裂。

### 事件驱动 + 慢兜底架构

> **不要做"忙等"daemon**。各命令主动同步状态，daemon 只做兜底。

旧设计（反例）：
```bash
# daemon 每 2s 打 ncm-cli 拿状态（1860 次/小时）
while true; do
  state=$(ncm-cli state)
  write_cache "$state"
  sleep 2
done
```

新设计（推荐）：
```bash
# 1. 各 ncm-player 控制命令末尾调 sync_state（0 延迟）
toggle)  ncm-cli stop; sync_state ;;
next)    ncm-cli next; sync_state ;;

# 2. daemon 只兜底（10s 一次），同步间隔从 2s 降到 10s
daemon)
  while [ -S "$SWAYSOCK" ]; do
    sync_state   # 兜 mpv 自然结束/外部停止
    sleep 10
  done
```

**触发频率**：
- ncm-player 控制命令：每次触发（0 延迟）
- daemon 兜底：10s 一次（兜 mpv 自然结束等 ncm-player 没法覆盖的场景）
- login 检查：1h 缓存（用户不会退出）

**收益**：ncm-cli 调用从 1860 次/小时降到 6 次/小时（↓99.7%），且起停延迟从 2s 降到 0。

### 优势

- waybar 配置短到一眼能审完
- 改时序、图标、sleep 只动 ncm-player 一处
- 三个触发方式可对比实测（同一种数据源下哪种最稳）

### 为什么推荐 `interval` + `return-type: json` 而非 while 循环

> **2026-06-24 实战结论**：`interval` + `return-type: json` + `format: "{text}"` 在当前环境（waybar 0.12+, Debian 13）中比 while 循环连续 exec 更可靠。

**推荐理由**：

1. **无行缓冲问题**：每次 fork 进程 → EOF 触发 waybar 更新 → 无需操心 `\n`
2. **配置更直白**：`interval: 2` 就是 2 秒刷新，不需要看 while 循环的 sleep
3. **waybar 自带容错**：模块进程崩溃后 waybar 自动等到下一个 interval 重新 fork
4. **单进程不积累文本**：不会出现 `print(..., end='')` 不断追加导致内存增长
5. **JSON 格式更可控**：可以设置 `alt`, `class`, `tooltip` 字段

### 写 while 循环脚本的原则

```bash
#!/usr/bin/env bash
# 示例：播放状态输出脚本
while true; do
    if check_login; then
        ncm state-get play
    else
        echo ""  # 未登录时输出空行，waybar 不显示
    fi
    # 可根据状态动态调整 sleep 时长
    sleep 2
done
```

### ⚠️ Bash 函数作用域陷阱（function-in-case not global）
> 2026-06-24 hard lesson. `ncm-player waybar-play` 进程挂掉因为 `_ncm_current_swaysock: command not found`。

**症状**：while 循环一开始就退出（exit code 127），waybar 日志报 `stopped unexpectedly, is it endless?`。

**根因**：Bash **不会**把 `case` 分支内定义的函数提升到全局作用域。函数只在进入该 `case` 分支时才被定义。当 waybar 调用 `ncm-player waybar-play`（非 `daemon` 分支），`daemon` 分支内的 `_ncm_current_swaysock()` 根本不存在。

```bash
# 在 waybar 配置中
"exec": "/home/dr/.local/bin/ncm-player waybar-play"

# ncm-player 脚本结构
case "${1:-help}" in
  waybar-play)
    # 调 _ncm_current_swaysock() → ❌ command not found
    # 该函数定义在 daemon 分支内，waybar-play 分支不可见
    ;;
  daemon)
    _ncm_current_swaysock() { ... }  # 只在此分支可见
    ;;
esac
```

**修法**：**所有全局函数定义在 `case` 之前**：

```bash
# ✅ 正确：case 之前定义
_ncm_current_swaysock() { ls -t /run/user/"$(id -u)"/sway-ipc.*.sock 2>/dev/null | head -1; }
SELF="$0"

case "${1:-help}" in
  waybar-play)  while ... do "$SELF" state-get-json play; sleep 2; done ;;
  daemon)       while ... do "$SELF" sync_state; sleep 10; done ;;
esac
```

**同时 `SELF` 必须显式赋值**（不是内置变量）。`set -u`（来自 `set -euo pipefail`）在 `$SELF` 未定义时报 `unbound variable`，此时 bash 行为是：**继续执行**（用空串替代未定义变量），导致 `"" state-get-json play` → 实际运行的是空命令 → exit code 127（command not found）→ waybar 日志报 `stopped unexpectedly, is it endless?`。

```bash
# ❌ 踩坑：set -u + $SELF 未定义
set -euo pipefail
case "${1:-help}" in
  waybar-play)
    "$SELF" state-get-json play  # set -u → 空串 → command not found → 127
    ;;
esac

# ✅ 正确：在 case 之前定义 SELF
set -euo pipefail
SELF="$0"
case "${1:-help}" in
  waybar-play)
    "$SELF" state-get-json play
    ;;
esac
```

**影响范围**：
- 任何在多个 `case` 分支间共享的 helper 函数
- `SELF="$0"`、`NCM_CLI="..."` 等路径变量
- `$SWAYSOCK` 等环境感知变量（应在 while 循环内每次迭代重新解析，见行缓冲陷阱下方）

### ⚠️ 行缓冲陷阱（newline trap）—— while 循环的最大坑

> 2026-06-24 hard lesson。根因是当时所有 ncm-* 按钮在 waybar 上不可见但 GTK tree 里有 label。

**核心事实**：waybar 在连续 exec 模式下用**行缓冲**读取 stdout pipe。  \
只有收到 `\n` 才认为一行完整，触发 label 更新。**无换行的数据会无限缓冲，永不被处理。**

```python
# ❌ 危险：print(..., end='') 无换行符
print('📻', end='')  # 输出 4 字节，无 \n
                    # → waybar 行缓冲，等待更多数据，永不更新
                    # → label 永远不可见

# ✅ 安全：print() 默认带换行符
print('📻')          # 输出 4 字节 + \n
                    # → waybar 收到完整行 → 立即更新 label

# ✅ 最佳：print(json.dumps(...)) 默认带换行符
print(json.dumps({'text': '📻'}))  # {"text":"📻"}\n
                                   # → waybar 收到 JSON 行 → 解析 → 更新
```

**验证方法**：检查脚本 stdout 是否以 `\n` 结尾：
```bash
# 看最后个字符是不是换行
/home/dr/.local/bin/ncm-player state-get play | xxd | tail -1
```

**对外部命令（`echo`）的影响**：
- `echo '📻'` → ✅ 自带换行（echo 默认）→ waybar 收到完整行
- `printf '📻'` → ❌ 无换行 → 同上行缓冲问题
- Python `print()` → ✅ 默认换行
- Python `print(..., end='')` → ❌ 无换行
- `cat file` → ✅ 如果文件以换行结尾
- `ncm-cli ...` (Node.js) → 取决于 CLI 实现，需测试

**为什么 `interval` 模式不受影响**：interval 模式每次重新 fork 进程 → 进程退出 → pipe 关闭 → EOF 信号 → waybar 把缓冲全部视为"一行" → 即使无 `\n` 也触发更新。

**推荐替代方案**：见下方「集中调度模式」的 `interval + return-type: json` 方式。`interval: 2` + `return-type: json` + `format: "{text}"` 已在生产环境可靠运行。详见 `references/ncm-module-rework-2026-06-24.md`。

- **每次迭代输出一行**：waybar 读一行刷新一次。多行输出会被逐行处理
- **输出空行 = 隐藏模块**：`echo ""` → waybar 不渲染该模块
- **支持 `return-type: json`**：如果输出 JSON 格式（`{"text":"...","alt":"...","tooltip":"..."}`），需要写 `"return-type": "json"`
- **进程挂了 waybar 不重启**：waybar 不会自动重启 `exec` 进程。如果脚本意外退出（如 `set -e` 触发），waybar 模块会一直显示最后一次输出。脚本要做错误恢复或 daemon 化保证存活

### `interval` + `return-type: json` vs daemon + signal 的取舍

| | `interval` + JSON | daemon + signal |
|---|---|---|
| 进程模型 | 每个 interval 重新 fork | 一个 daemon 管所有模块 |
| 状态来源 | 子进程每次自己读 | daemon 写共享状态文件 |
| 同步 | 不需要（各模块独立读） | 需要 signal 协调 |
| 复杂度 | 低（每个模块独立定时） | 中（daemon 写 + 模块读 + 信号协调） |
| 容错 | 一次 interval 失败下次自动重试 | daemon 挂了所有模块都停 |
| 可靠性 | ✅ 已验证生产可用 | 依赖 daemon 存活 |

**选型建议**：
- ✅ **默认推荐** → `interval` + `return-type: json`
- 需要极低间隔（< 1s）→ 考虑 while 循环（注意行缓冲问题）
- 已有 daemon 持续写状态文件 → signal 可减少 fork 开销

## Sync Chrome PWAs to Waybar launcher buttons

### Step 1: Discover installed PWAs
```bash
for f in ~/.local/share/applications/chrome-*.desktop; do
  echo "=== $(basename $f) ==="
  grep -E '^Name=' "$f" 2>/dev/null
  grep -E '^Exec=' "$f" 2>/dev/null | head -1
  echo
done
```

Key fields to extract from each `.desktop` file:
- **`Name=`**: display name (the PWA title)
- **`Exec=`**: contains `--app-id=<id>` — this is the Chrome app ID used in waybar `on-click`
- **`--app-launch-url-for-shortcuts-menu-item=`**: the actual URL the PWA connects to (HTTP vs HTTPS). Only present if the PWA has a "New conversation" or similar action.

### Step 2: Identify connection protocol
The `--app-launch-url-for-shortcuts-menu-item` reveals the destination URL:
- `http://localhost:8787/` → local HTTP
- `https://hermes-x1tablet.tail2e6efb.ts.net/` → Tailscale HTTPS
- Absent → no explicit URL (bare app-id launch)

When the user says "重复的只保留 https 连接的", keep the PWA whose shortcut URL starts with `https://` and remove the HTTP/unknown ones.

### Step 3: Cross-reference against waybar config
Compare the installed app-ids from `.desktop` files against the `--app-id=` values in `modules-left` entries of `config-top`.

**Stale app-id detection**: if an `.desktop` file exists for `app-id=A` but the waybar config references `app-id=B` for the same named app (e.g. code-server), B is stale. Update B → A.

**Missing detection**: if a PWA is installed but has no corresponding `custom/<name>` entry in waybar, it needs a new module.

**Orphan detection**: if a waybar `custom/<name>` entry references an app-id with no matching `.desktop` file, it's stale and should be removed.

### Step 4: Update waybar config
When updating `config-top`:
1. Fix stale app-ids in existing module definitions
2. Remove duplicate entries (keep HTTPS, remove HTTP/localhost)
3. Add new modules for newly discovered PWAs
4. Update the `modules-left` array to match — remove deleted module names, append new ones

### Step 5: Reload waybar
```bash
killall -SIGUSR2 waybar
```

### Naming convention for PWA launcher modules
| Module name | PWA | app-id (example) |
|---|---|---|
| `custom/term` | Terminal (foot) | n/a (native app) |
| `custom/chrome` | Chrome browser | n/a |
| `custom/fuzzel` | App launcher | n/a |
| `custom/code-server` | code-server | `anlhgcnfglodaccjojnfbabpjidhenop` |
| `custom/hermes` | Hermes (HTTPS) | `hbieppijmjjnadmpdpddnobiafcncocm` |
| `custom/rclone-webui` | Rclone WebUI | `hkmbpfkfjpljkndchoakjhmcpefichen` |
| `custom/rclone-webui-ip` | Rclone WebUI IP | `jaemjmjciacjhaekaofmdbfnibifddph` |

### Pitfalls

- `on-click` 走 `g_spawn_command_line_async`：**无 shell**。`sh -c 'cmd'` 可用（g_shell_parse_argv 拆 argv 再 execve），但 shell 特性（`>>` 重定向、`$(date)` 变量）不展开。测 on-click 是否触发最简方法是**在被调脚本内** `touch /tmp/waybar-clicked`——不要用 `sh -c` 包装器（用户偏好："调试插标记在真实代码路径"）。
- on-click 的环境继承自 waybar（不继承调用终端）。遇 NVM/conda 路径问题：用绝对路径或在被调脚本内 `export PATH=$HOME/.local/bin:$PATH`。
- `.desktop` file names don't reliably match app-id — always grep the **content**, not the filename.
- A PWA re-install (e.g. after clearing browser data) gets a **new random app-id**. Always verify `.desktop` app-ids match waybar entries.
- `chrome-<name>.desktop` (named shortcut) and `chrome-<appid>-Default.desktop` (auto-generated) can coexist for the same PWA. Use the one with the actual `Exec` line.
- `Name=` in `.desktop` may conflict between different PWA instances (e.g. three Hermes PWAs all named "Hermes"). Disambiguate via the shortcut URL.

    ' Why native mpris > custom module: a custom module that polls playerctl metadata every N seconds wastes CPU and fights XDG_MUSIC_DIR clashes; waybar-mpris is event-driven through the D-Bus signal.

## Critical protocol: NEVER delete or reorder the user system-status modules

The user modules-right contains modules they did NOT add via waybar-pwa-gen.py -- they wrote them by hand and rely on them daily:

    custom/temperature, cpu, custom/memory, pulseaudio,
    custom/network, custom/tailscale, custom/deepseek-cost,
    tray, clock

When extending modules-right (adding ncm buttons, mpris, etc.):
- **Append** new modules to the array - never delete, never reorder residents.
- **If the eDP-1 portrait screen (~1000 logical px) cannot fit all modules** and the user complains, do NOT silently drop system-status modules. Instead, ask: 'eDP-1 only 1000px wide. Which system-status modules (temp/cpu/memory/network/tailscale/deepseek-cost) do you rarely look at, so I can drop them to free space?' Let the user choose.

Violation of this rule generates extreme user frustration and lost trust.

## Self-verification protocol (MANDATORY)

After ANY config change to waybar config files:

1. **Validate JSON**:
   ```bash
   python3 -c "import json, os; json.load(open(os.path.expanduser('~/.config/waybar/config-top'))); print('JSON OK')"
   ```

   **Note**: Python's `json.load(open(...))` accepts trailing commas (unlike `python3 -m json.tool`).
   If `json.tool` fails but `json.load(open(...))` passes, the issue is likely a harmless trailing comma,
   not a real syntax error. See the Trailing comma pitfall below for details.
2. **Run waybar with debug** — use the ORPHAN-SAFE restart protocol above (NEVER `timeout 2 waybar -l trace`, that leaves orphans):
   ```bash
   # Step 1: JSON validate first
   python3 -c "import json, os; json.load(open(os.path.expanduser('~/.config/waybar/config-top'))); print('JSON OK')"

   # Step 2: Clean restart (TERM, not KILL; resolve SWAYSOCK fresh)
   pkill -TERM -f "waybar -c" 2>/dev/null; sleep 1.5
   pkill -9 -f "ncm-player" 2>/dev/null; pkill -9 -f "waybar -c" 2>/dev/null; sleep 0.5
   SWAYSOCK=$(ls -t /run/user/1000/sway-ipc.*.sock 2>/dev/null | head -1)
   SWAYSOCK="$SWAYSOCK" waybar -c ~/.config/waybar/config-top    >/tmp/waybar-verify.log 2>&1 &
   SWAYSOCK="$SWAYSOCK" waybar -c ~/.config/waybar/config-bottom >/tmp/waybar-bottom.log 2>&1 &
   sleep 2

   # Step 3: Verify zero orphans + both waybars running
   ps -eo pid,ppid,cmd | grep "ncm-player" | grep -v grep | awk '$2==1' | wc -l   # MUST be 0
   pgrep -fa "waybar -c" | grep -v "bash -l"   # MUST show 2 processes

   # For deeper debug: bump log level with WAYBAR_LOG_LEVEL=trace env, NOT by spawning a debug instance
   WAYBAR_LOG_LEVEL=trace SWAYSOCK="$SWAYSOCK" killall -USR1 waybar   # if supported
   ```
   **If a debug-level waybar is truly required** (rare — usually JSON validation + log inspection suffice), use `WAYBAR_LOG_LEVEL=debug` env var on the production instance. Do NOT spawn a separate `timeout N waybar -l trace` instance — see "CRITICAL: never SIGKILL waybar" pitfall above.
3. **Check GTK widget tree** — verify all expected modules appear:
   ```bash
   awk '/box.horizontal.modules-left/,/box.horizontal.modules-center/' /tmp/waybar-verify.log
   awk '/box.horizontal.modules-right/,/^$/' /tmp/waybar-verify.log
   ```
4. **Check for errors** — no "Disabling module", no "Unable to connect", no "exit 127":
   ```bash
   grep -iE "Disabling|error|warn|exit code 127" /tmp/waybar-verify.log | head -5
   ```
5. **Test mpris** (if affected): trigger playback and verify D-Bus state changes:
   ```bash
   dbus-send --session --print-reply --dest=org.mpris.MediaPlayer2.mpv \
     /org/mpris/MediaPlayer2 org.freedesktop.DBus.Properties.Get \
     string:'org.mpris.MediaPlayer2.Player' string:'PlaybackStatus'
   ```
6. **DO NOT ask the user to test** — run the verification yourself. Present the evidence.

### Critical: never silently delete or reorder user-written modules on modules-right

When the user reports "state bar is missing things" and the root cause is eDP-1 ~1000px overflow:

- **Do NOT silently drop system-status modules** (temperature, cpu, memory, network, tailscale, deepseek-cost) to free space. This causes extreme user frustration and loss of trust.
- Instead, present the evidence: "modules-right has 17 modules, eDP-1 is only ~1000px, estimated overflow ~450px. Which of these would you like to drop: temp/cpu/memory/network/tailscale/deepseek-cost?"
- Or let the user accept that DP-5 4K shows everything but eDP-1 truncates.

### Safely restarting waybar (dual-instance) — ORPHAN-SAFE PROTOCOL

The setup runs TWO independent waybar instances (config-top + config-bottom). Both must be managed together. **Always TERM, never KILL** — see "CRITICAL" pitfall above for why.

```bash
# Step 1: TERM both waybar instances (lets them close child pipes → ncm-player exits cleanly)
pkill -TERM -f "waybar -c" 2>/dev/null
sleep 1.5

# Step 2: Catch stragglers (TERM usually gets them all, but be safe)
pkill -9 -f "ncm-player" 2>/dev/null
pkill -9 -f "waybar -c" 2>/dev/null
sleep 0.5

# Step 3: Verify ZERO orphans
ORPHANS=$(ps -eo pid,ppid,cmd | grep "ncm-player" | grep -v grep | awk '$2==1' | wc -l)
[ "$ORPHANS" -eq 0 ] || { echo "WARNING: $ORPHANS orphan ncm-player processes — re-run step 2"; }
pgrep -fa "waybar -c" | grep -v "bash -l" || echo "all waybar killed"

# Step 4: Resolve current SWAYSOCK (hermes terminal may inherit old sway's socket)
SWAYSOCK=$(ls -t /run/user/1000/sway-ipc.*.sock 2>/dev/null | head -1)
[ -S "$SWAYSOCK" ] || { echo "no valid sway socket — is sway running?"; exit 1; }
echo "using SWAYSOCK=$SWAYSOCK"

# Step 5: Start both waybars with explicit SWAYSOCK
SWAYSOCK="$SWAYSOCK" waybar -c ~/.config/waybar/config-top  >/tmp/wb-top.log    2>&1 &
SWAYSOCK="$SWAYSOCK" waybar -c ~/.config/waybar/config-bottom >/tmp/wb-bottom.log 2>&1 &
sleep 1.5
pgrep -fa "waybar -c" | grep -v "bash -l"   # should show both
```

**Why NOT SIGUSR2 alone**: `killall -SIGUSR2 waybar` only hits whichever instance happens to be alive. If only config-bottom is running (e.g. top bar crashed), SIGUSR2 just reloads the bottom bar's CSS — the top bar stays dead. Always do a full pkill + restart.

**Why `ls -t` not `ls` (alphabetical)**: `ls -t /run/user/1000/sway-ipc.*.sock` sorts by **mtime** (newest first). `head -1` picks the most recent. Sway rotates the socket on restart; old sockets linger but are stale. Alphabetical sort has no correlation with recency.

**Hermes terminal SWAYSOCK trap**: When you run waybar from a terminal started outside the current sway session (e.g. a long-lived ssh/hermes terminal that survived a sway restart), the inherited `SWAYSOCK` env var points to a dead socket. Waybar then fails with "Disabling module sway/workspaces, Unable to connect to Sway" — even though the modules-right modules still work (they don't need SWAYSOCK). Always re-resolve SWAYSOCK before starting waybar in such a context.

## Auditing player/audio modules on modules-right

When analyzing waybar player modules (ncm-*, mpris, or any audio-related custom modules),
use this audit matrix to evaluate each module:

| Check | What to look for |
|-------|-----------------|
| **interval** | Is the poll frequency justified by the rate of change? Playing status needs 1-3s; login status needs 10-60s |
| **exec cost** | Is the command fast? Node.js CLIs cost ~365ms per invocation — cache aggressively |
| **login check** | Does the module call `ncm-cli login --check` on every poll? Cache login state in a local file |
| **output guarantee** | Does the script always output something? Login-gated modules should return empty string when not logged in (waybar hides them) |
| **CSS class** | Does the module set a `class` field for visual state differentiation? (play/pause, connected/disconnected) |
| **data source** | Does it read from D-Bus MPRIS (event-driven, fast) or from ncm-cli (poll, 365ms overhead)? Avoid dual sources for the same state |
| **click handler** | Does `on-click` use absolute paths? waybar uses execve, not shell |

### Common patterns and fixes

**Login check caching**: Create `~/.local/share/ncmctl/.logged_in` file:
- On login success: `touch .logged_in`
- In `check_login()`: stat mtime → if < 60s old, return success without calling ncm-cli
- On logout: `rm -f .logged_in`

**Like button**: Should output empty string (hidden) when not logged in, not a hardcoded icon.

**Play button interval**: 1s only matters during active playback. 3s is safe for all states.

**CSS classes**: The `alt` field in JSON output maps to CSS class. Use it:
```python
print(json.dumps({"text": "▶", "alt": "playing", "class": "playing"}))
```
Then in style.css:
```css
#custom-ncm-play          { color: #000; }
#custom-ncm-play.playing  { color: #2d8a4e; }
#custom-ncm-play.paused   { color: #888; }
```

### Reference file

See `references/player-module-audit-2026-06-23.md` for a complete real-world audit of
the eight player modules (mpris + 7 ncm-* modules) including polling intervals,
per-call timing, CSS gaps, and the `state.json` dual-source issue.

## MPRIS + mpv-mpris Debugging

See `references/mpris-debugging.md` for the complete source-level analysis of:

- Why waybar mpris shows "mpv-playing" and never updates
- The mpv idle + pause property change trap (root cause)
- The pause-toggle workaround for ncm.lua
- How to verify PlaybackStatus via D-Bus
- Links to waybar mpris.cpp and mpv-mpris mpris.c sources

## Pitfalls

- `on-click` 走 `g_spawn_command_line_async`：**无 shell**。`sh -c 'cmd'` 可用（g_shell_parse_argv 拆 argv 再 execve），但 shell 特性（`>>` 重定向、`$(date)` 变量）不展开。测 on-click 是否触发最简方法是**在被调脚本内** `touch /tmp/waybar-clicked`——不要用 `sh -c` 包装器（用户偏好："调试插标记在真实代码路径"）。
- on-click 的环境继承自 waybar（不继承调用终端）。遇 NVM/conda 路径问题：用绝对路径或在被调脚本内 `export PATH=$HOME/.local/bin:$PATH`。 (waybar-specific)

> 通用 waybar 配置 pitfalls（任何 custom 模块都适用）。NCM 特定 pitfalls 见 `ncm-cli-setup`；mpv+mpris 特定 pitfalls 见 `mpv-mpris-media-stack`。

### CRITICAL: custom 模块必须显式 `"format": "{text}"`（否则 label 被隐藏）

**症状**：GTK widget tree 里 `label#custom-ncm-xxx.module` 存在，但用户在屏幕上**看不到任何文字**。没有 Error、没有 Disabling warning，就是空白。

**根因**（waybar v0.12+，custom.cpp 实现细节）：
1. waybar custom 模块默认 `"format": "{}"`（隐式默认）
2. 当模块的 `name` 属性（由 `exec` 命令的 stdout 填充）被 waybar 内部设置为 `fmt::arg("text", ...)` 命名参数时
3. 默认 `"{}"` 格式化模板**不匹配命名参数** → `fmt::format_error` 异常
4. waybar 捕获异常后调用 `event_box_.hide()` → label 在屏幕层被隐藏
5. widget tree 可见，但 `is_visible() = false`

**修法**：给所有 `custom/*` 模块**显式写 `"format": "{text}"`**：

```json
// ❌ 错误 — 默认 "{}" 与 fmt::arg("text",...) 冲突
"custom/ncm-play": {
    "exec": "...",
    // format 省略 = 默认 "{}" → fmt 异常 → label 隐藏
}

// ✅ 正确 — 显式指定命名格式
"custom/ncm-play": {
    "exec": "...",
    "format": "{text}"   // 匹配 fmt::arg("text", ...)
}
```

**影响范围**：
- `return-type: "json"` 模块**不受影响**（JSON 解析不走 `fmt::arg` 路径）
- 带 `interval` 的模块也不受影响（interval 模式用不同渲染路径）
- 只有**纯 text exec 模式**（no interval, no return-type: json）踩到这个坑
- 2026-06-24 hard lesson: 用户屏幕上看不到所有 ncm 按钮，但 GTK tree 里 label 全在，无任何错误日志

> ⚠️ **注意**：即使解决了 format 问题，纯 text exec 模式还可能有**行缓冲陷阱**（见上方「行缓冲陷阱（newline trap）」节）。如果模块有 `interval` + 无换行输出，进程退出 EOF 触发更新。如果无 `interval` + 无换行输出，line buffer 永不触发更新。**最佳方案**：`interval` + `return-type: json` + `format: "{text}"`。

### CRITICAL: never SIGKILL waybar or use `timeout waybar -l trace` in production — leaves orphan children

> 2026-06-24 hard lesson. User got angry ("又是孤儿线程问题，能不能不再犯这个错了？！！！！"). This section is the **single most important pitfall in this skill**.

**Symptom**: After debugging or restart, you see `ncm-player waybar play` processes with PPID=1 (init). They're alive, holding pipes, consuming CPU — but no waybar parent to read their stdout. Module still shows blank.

**Why it happens**:
- `pkill -9 waybar` / `killall -9 waybar` sends SIGKILL to waybar only. The ncm-player child processes don't get notified, their stdin/stdout pipes stay open, they keep running. Kernel reparents them to init (PPID=1).
- `timeout N waybar -l trace` — even with timeout's SIGTERM, if you use `timeout --kill-after` or waybar doesn't forward the signal, same result.
- The "double-layer PATH" pitfall means you often want to debug-trace waybar to see why a module is blank — but the trace instance you spawn is itself the orphan source.

**Forbidden patterns** (don't do these in production):
```bash
# ❌ SIGKILL waybar — ncm-player children become init orphans
pkill -9 waybar
killall -9 waybar
killall -KILL waybar

# ❌ timeout'd debug waybar — same orphan problem after timeout kills it
timeout 2 waybar -c ~/.config/waybar/config-top -l trace
timeout 2.5 waybar -c ~/.config/waybar/config-top -l debug
```

**Right patterns**:
```bash
# ✅ Clean restart: TERM waybar (lets it close child pipes → children get SIGPIPE → exit)
#    Then KILL any stragglers by full path pattern
pkill -TERM -f "waybar -c" 2>/dev/null
sleep 1.5
pkill -9 -f "ncm-player" 2>/dev/null   # catch any stragglers
pkill -9 -f "waybar -c" 2>/dev/null
sleep 0.5
# verify zero orphans
ps -eo pid,ppid,cmd | grep -E "ncm-player|waybar -c" | grep -v grep

# ✅ Restart via terminal(background=true) — Hermes tracks lifecycle
SWAYSOCK=$(ls -t /run/user/1000/sway-ipc.*.sock | head -1) \
  waybar -c ~/.config/waybar/config-top >/tmp/wb-top.log 2>&1 &
```

**Why `pkill -9 -f \"ncm-player\"` as the fallback**: A few stragglers may have been mid-write when TERM hit. KILL them. But you almost never need this if TERM is given enough sleep (1.5s).IN+6 waybar
```
This avoids spawning a debug waybar entirely. See "Self-verification protocol" below — the old `timeout 2 waybar -l debug` step is replaced.

### `killall ncm-player` doesn't kill the runner — use `pkill -f` instead

**Symptom**: After `killall -9 ncm-player`, processes are still alive. `pgrep` shows them.

**Why**: `ncm-player` is a bash script invoked as `bash /home/dr/.local/bin/ncm-player waybar play`. The OS process name is `bash` (the interpreter), not `ncm-player` (the script). `killall ncm-player` matches by process name → finds nothing.

**Fix**: match by **cmdline** substring, not name:
```bash
# ❌ matches process name (bash) — fails silently
killall -9 ncm-player
pkill ncm-player           # -x default = exact name match — also fails

# ✅ matches full cmdline — works
pkill -9 -f "ncm-player"   # -f = full cmdline
pkill -9 -f "/home/dr/.local/bin/ncm-player"
```

**Same trap for any script**: `killall ncm-playlist`, `killall swaybar`, `killall ncm-state-daemon` all silently fail for the same reason. Always use `pkill -f <cmdline-substring>` for script-orchestrated processes.

### exec/on-click need absolute path
waybar exec / on-click does NOT go through a shell (direct execve), so ~/.local/bin/ncm is not found. Result: exit 127, waybar log shows 'sh: 1: ncm: not found'.

Fix: use absolute path in all custom module exec/on-click:
    exec: /home/dr/.full/bin/ncm-player play-button
    on-click: /home/dr/.full/bin/ncm-player login

**Don't use a symlink like `/home/dr/.local/bin/ncm → ncm-player` for this** — symlinks rot, get cleaned up by `stow` / package managers, and obscure the real path. Always use the actual binary name.

### exec-relative scripts also need absolute internal commands (double-layer PATH)
> 2026-06-24 lesson. Symptom: waybar config's `exec` is absolute path, but the script it spawns still fails with `command not found` / exit 127.

Even after you fix waybar's `exec` to use absolute path, **the spawned script inherits waybar's execve environment — no shell, no PATH expansion**. Any PATH-based command inside that script (including the script recursively calling itself by name) silently fails with `ncm: command not found`. Waybar shows blank module; user sees "buttons disappeared".

**Two layers of PATH exposure**:
1. Outer (waybar config): `exec: "ncm waybar play"` → `ncm: not found` (waybar's PATH)
2. **Inner (script body)**: script's `while true; do ncm state-get play; done` → `ncm: not found` (waybar-spawned subprocess PATH, same as #1)

User preference: "不可靠工具用绝对路径替代PATH查找" — applies to BOTH layers.

**Reproduction signature** in waybar trace log:
```
[debug] Cmd exited with code 127
/home/dr/.local/bin/ncm: line 269: ncm: command not found
```

**⚠️ 2026-06-24 新增：`#!/usr/bin/env node` 静默失败陷阱** — 当被调用的脚本（如 `ncm-cli`）的 shebang 是 `#!/usr/bin/env node`，且 `node` 不在 PATH 中时，`env` 找不到 `node` → 命令立即退出 (exit 127) → `2>/dev/null` 静默吞掉错误 → 上层脚本获得空输出 → 误以为是"无数据" → waybar 显示空白。

**症状特征**（比纯 PATH 缺失更隐蔽）：
- 用户在终端跑 `ncm-player toggle` → 一切正常（音频播放、状态切换、JSON 输出都对）
- 用户点 waybar 按钮 → **无声无息，无响应**，但 waybar 日志显示 `Cmd exited with code 0`
- 调试日志显示 `state_before=stopped`，但 `state_after=` 不存在 → toggle 命令卡在 ncm-cli 调用上
- 终端 `ncm-cli state --output json` 返回 `playing` / 实际在播 → 但 waybar 按钮调用的 `ncm_status()` 返回 `stopped`

**根因**：waybar 子进程的 PATH 通常不含 `~/.local/bin`，而 `node` 装在用户本地路径下（NVM / npm global）。即使 waybar 配置的 `exec` 用了绝对路径（如 `/home/dr/.local/bin/ncm-player`），ncm-player 内部调用的 `ncm-cli` 的 shebang `#!/usr/bin/env node` 仍通过 PATH 查找 node。

**修复**：在被 waybar 调用的脚本开头添加 PATH 扩展：
```bash
# 在 ~/.local/bin/ncm-player 或任何
# 被 waybar exec/on-click 调用的脚本顶部
export PATH="$HOME/.local/bin:$PATH"
```

**验证方法**（怀疑 PATH 缺失 vs 网络故障 vs 权限问题时）：
```bash
# 正常终端 → 应有输出
/home/dr/.local/bin/ncm-cli state --output json | head -1

# 模拟 waybar PATH（只有 /usr/bin）→ 应失败
env -i PATH=/usr/bin:/bin HOME=$HOME /home/dr/.local/bin/ncm-cli state --output json 2>/dev/null
echo "exit: $?"  # 应为 127（但被 2>/dev/null 藏了）
```

**如果脚本是 Python**（如 ncm-playlist）：
```python
import os, sys
os.environ["PATH"] = os.path.expanduser("~/.local/bin") + ":" + os.environ.get("PATH", "")
```

**影响范围**：任何使用 `#!/usr/bin/env node` 或 `#!/usr/bin/env python3` 的工具（ncm-cli、npm bin、pip --user 脚本），当被 waybar 子进程调用时都会静默失败。
**调试原则**：**先验证 on-click 被触发**（用 `touch /tmp/marker` 在 handler 开头），再验证 handler 内部调用是否执行。Marker 出现 + 动作没生效 = 几乎总是环境变量问题。

**⚠️ 2026-06-24 新增：`#!/usr/bin/env node` 静默失败陷阱** — 当被调用的脚本（如 `ncm-cli`）的 shebang 是 `#!/usr/bin/env node`，且 `node` 不在 PATH 中时，`env` 找不到 `node` → 命令立即退出 (exit 127) → `2>/dev/null` 静默吞掉错误 → 上层脚本获得空输出 → 误以为是"无数据" → waybar 显示空白。

与纯 PATH 缺失的区别：纯 PATH 缺失的脚本（如 `ncm: not found`）会在 waybar 日志留有 `exit 127` + 错误消息。但 `#!/usr/bin/env node` 脚本的失败更隐蔽：
- waybar 日志显示 `Cmd exited with code 0`（因为外层脚本（如 ncm-player）快速捕获了错误并继续执行）
- 没有 "not found" 错误消息（被 `2>/dev/null` 吞了）
- 只有对比直接终端和 waybar 调用的输出才能发现差异

**根因**：waybar 子进程的 PATH 通常不含 `~/.local/bin`，而 `node` 或 `python3` 装在用户本地路径下（NVM / npm global / pip --user）。即使 waybar 配置的 `exec` 用了绝对路径（如 `/home/dr/.local/bin/ncm-cli`），ncm-cli 的 shebang `#!/usr/bin/env node` 仍通过 PATH 查找 node。

**修复**：在被 waybar 调用的脚本开头添加 PATH 扩展：
```bash
# 在 ~/.local/bin/ncm-player 或任何
# 被 waybar exec/on-click 调用的脚本顶部
export PATH="$HOME/.local/bin:$PATH"
```

**影响范围**：任何使用 `#!/usr/bin/env node` 或 `#!/usr/bin/env python3` 的工具（ncm-cli、npm bin、pip --user 脚本），当被 waybar 子进程调用时都会静默失败。

**验证方法**：对比相同命令在终端和精简环境下的输出：
```bash
# 正常终端 → 应有输出
/home/dr/.local/bin/ncm-cli state --output json | head -1

# 模拟 waybar PATH（只有 /usr/bin）→ 应失败
env -i PATH=/usr/bin:/bin HOME=$HOME /home/dr/.local/bin/ncm-cli state --output json 2>/dev/null
echo "exit: $?"  # 应为 127（但被 2>/dev/null 藏了）
```

**Fix for inner recursion**: use `"$0"` to recurse to the script itself (always absolute when invoked by waybar):
```bash
waybar)
    module="${2:-}"
    SELF="$0"  # absolute path that waybar used to invoke us
    case "$module" in
        play)   while true; do "$SELF" state-get play; sleep 2; done ;;
        status) "$SELF" state-get status_icon ;;
    esac
    ;;
```

**Why `"$0"` not the script's hardcoded path**: keeps the script relocatable. The hardcoded path is captured at first invocation by waybar.

**Audit checklist** when debugging "blank waybar module":
```bash
# 1. Confirm waybar sees the module (does it appear in GTK widget tree?)
waybar -l trace -c ~/.config/waybar/config-top 2>&1 | grep "custom-ncm-foo"

# 2. Confirm the exec command itself works
SWAYSOCK=$(ls /run/user/1000/sway-ipc.*.sock | head -1) \
  /home/dr/.local/bin/ncm waybar play &
sleep 2
# Should print icon and stay alive

# 3. If the script works standalone but blank in waybar → check internal PATH commands
grep -nE '\bncm\b|\bcurl\b|\bpython3\b' ~/.local/bin/ncm-player | grep -vE 'NCM_CLI=|env -i|/usr/bin/|\$\("'
# Anything left is a bare command in the spawned environment — replace with abs path or $0
```

**Common trap**: `ncm` is a symlink to `ncm-player`. If waybar invokes `/home/dr/.local/bin/ncm waybar play`, the script's `$0` is `/home/dr/.local/bin/ncm` (not `ncm-player`). `"$SELF" state-get play` works because the symlink target is also executable.

### waybar-pwa-gen.py sort_keys=True silently reorders JSON keys

`waybar-pwa-gen.py` writes the full config file back with `sort_keys=True`:
```python
tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
```
Every time sway reload triggers `exec_always waybar-pwa-gen.py`, ALL JSON keys
in config-top get alphabetized. Although the script only intends to touch PWA
`custom/*` blocks and `modules-left`, the full-file rewrite means:
- Key ordering is lost (e.g. `"mpris"` might move before `"custom/ncm-status"`)
- Any manually maintained grouping or comments are stripped

**Mitigation**: Run `waybar-pwa-gen.py --dry-run` first to see proposed changes.
After the gen runs, verify `modules-right` is untouched (the script only edits
`modules-left`, but the sort_keys side-effect is global).

### Trailing comma false-positive in JSON validation

Python's `json.tool` rejects trailing commas (e.g. `"sway/window",` before `],`), but waybar's nlohmann/json parser **accepts them**. So `python3 -m json.tool config.json` may say "INVALID" for a file that waybar loads fine.

**However**: a **missing comma** between sibling array elements (e.g. `"sway/workspaces"\n    "sway/window"` without `,` between them) is a REAL JSON error — waybar will also fail to load the config and crash silently.

**How to distinguish real errors from false positives**:
- **Missing comma between sibling elements** → definitely a real error (JSON spec violation, waybar will also fail)
- **Trailing comma before `]` or `}`** → false positive (waybar accepts it, Python's `json.tool` doesn't)

**Recommended validation** — use `json.load(open(...))` NOT `json.tool`:

```bash
python3 -c "import json, os; json.load(open(os.path.expanduser('~/.config/waybar/config-top'))); print('JSON OK')"
```

This uses Python's built-in `json.load()` which rejects missing commas (real errors) but accepts trailing commas (false positives), matching waybar's actual behavior.

Best practice: run a quick waybar smoke test after JSON validation passes, or if `json.tool` fails, check whether it's a trailing comma issue before panicking.

### Tooltip debug

See `references/tooltip-debugging.md` for the complete tooltip debugging protocol — Pango markup pitfalls (`&` escaping), tag-balance checks, hover coverage diagnostics, and JSON output structure.

```bash
# Quick waybar smoke test without blocking the display
pkill -f "waybar -c" 2>/dev/null; sleep 1
waybar -c ~/.config/waybar/config-top &>/dev/null &
sleep 1
pgrep -f "waybar -c config-top" && echo "waybar accepted the config"
```

## Creating a "remote-stats" custom module

Pattern for a waybar custom module that fetches data from an HTTP endpoint:

### Script structure (`~/.local/bin/waybar-<name>-stats.py`)
```python
#!/usr/bin/env python3
import json, urllib.request, ssl, sys

STATS_URL = "http://server/endpoint"
ICON = "\uf1fe"  # Nerd Font   (chart-line)
TIMEOUT = 8

def emit(text, alt, tooltip):
    print(json.dumps({
        "text": text, "alt": alt, "class": alt, "tooltip": tooltip
    }, ensure_ascii=False))
    sys.exit(0)

def fail(reason):
    emit(f"   ✗", "error",
         f"<span color='#e74c3c'>不可用</span>\n{reason}")

def fetch():
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(STATS_URL)
        with urllib.request.urlopen(req, context=ctx, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return None

# main() — extract fields, build text + tooltip, call emit()
```

### Config entry in config-top
```json
"custom/headroom": {
    "exec": "python3 /home/dr/.local/bin/waybar-headroom-stats.py",
    "interval": 60,
    "return-type": "json",
    "tooltip": true
}
```

**Key rules**:
- `interval` should match the freshness needs (60s for server stats, 300s for cost data)
- Tooltip uses Pango markup — **always escape ALL data-derived content with `html.escape()`** (data from API, file reads, command output — anything that isn't the literal template text). One unescaped `&` breaks the entire Pango document → tooltip renders EMPTY.
- Error must gracefully degrade: show "✗" on failure, never crash waybar
- Absolute path in `exec` (waybar uses direct execve, not shell)

### ncm-cli polling overhead: ~365ms per invocation

`ncm-cli` is a Node.js binary — each invocation has ~365ms startup overhead
(Node runtime init + network handshake). When multiple waybar modules poll at
3s/3s/30s/30s/1s intervals, the combined load is substantial:

| Module | Interval | Calls/day | Daily CPU waste |
|--------|----------|-----------|-----------------|
| ncm-status | 3s | 28,800 | ~2.9h |
| ncm-fm | 30s | 2,880 | ~17.5min |
| ncm-pl | 30s | 2,880 | ~17.5min |
| ncm-like | 3s | 28,800 | ~2.9h |
| ncm-play | 1s | 86,400 | ~8.8h |
| **Total** | | **~149,760** | **~15.5h** |

**Fix**: Implement a local login cache (`~/.local/share/ncmctl/.logged_in`)
so `check_login()` reads file mtime instead of calling ncm-cli. The login
state only needs verification every 60s, not every poll cycle.

See `references/player-module-audit-2026-06-23.md` for the full audit.

### Debugging on-click: `g_spawn_command_line_async` does NOT use a shell

**核心事实**：waybar 的 `on-click` 通过 **GLib `g_spawn_command_line_async`** 执行命令。它用 `g_shell_parse_argv` 分割参数字符串（处理引号/空格），然后直接 `execve` — **不走 shell**。

这意味着：
```json
// ❌ 不支持 — 这些都是 shell 语法
"on-click": "/home/dr/.local/bin/ncm toggle >> /tmp/debug.log 2>&1"
"on-click": "touch /tmp/x && /home/dr/.local/bin/ncm toggle"
"on-click": "env | sort > /tmp/env.txt"
"on-click": "date; /home/dr/.local/bin/ncm toggle"

// ✅ 支持 — 纯命令 + 参数
"on-click": "/home/dr/.local/bin/ncm toggle"
"on-click": "/tmp/debug-wrapper.sh"
"on-click": "python3 /home/dr/.local/bin/write-log.py"
```

**调试方法（两种）**：

**方式 A：wrapper 脚本**（当需要 shell 功能时）
```bash
#!/bin/sh
# /tmp/debug-wrapper.sh
date >> /tmp/waybar-click.log
/home/dr/.local/bin/ncm-player toggle >> /tmp/waybar-click.log 2>&1
```
```json
"on-click": "/tmp/debug-wrapper.sh"
```

**方式 B：内部标记（用户偏好的方式）** — 在脚本的 handler 内直接加标记文件，不引入额外 shell 层：
```bash
# 在 ~/.local/bin/ncm-player 的 toggle case 内
toggle)
    touch /tmp/waybar-toggle-triggered   # ← 标记文件
    state=$(ncm_status)
    ...
```
点击后检查文件存在性：`ls /tmp/waybar-toggle-triggered`。

**优先用方式 B** — 更直接、不引入额外的 shell 脚本层、出错面更小。

### On-click 调试四步法（按优先级）

**1. 先确认 on-click 机制本身工作** — 临时把测试按钮的 `on-click` 改成最简动作：
```json
"custom/ncm-test": {
    "exec": "echo '{\"text\":\"🔵测试\"}'",
    "interval": 5,
    "on-click": "/bin/touch /tmp/waybar-clicked",
    ...
}
```
点一下 → `ls /tmp/waybar-clicked`。如果文件出现 → waybar on-click 工作正常。如果不出现 → waybar 配置问题（重新加载、模块名拼写、JSON 语法）。

**2. 确认 handler 被执行**（用户偏好方式 B）— 在 handler 第一行加 `touch`：
```bash
toggle)
    touch /tmp/waybar-toggle-triggered   # ← 确认 handler 被进入
    state=$(ncm_status)
    ...
```
点 → `ls /tmp/waybar-toggle-triggered`：
- 文件出现 + 后续动作没生效 → handler 进入了，是 handler 内部命令（ncm-cli、python3 等）失败
- 文件不出现 → handler 根本没执行，on-click 没触发（回到第 1 步）

**3. 隔离内部命令失败** — 在 handler 内部捕获每个子命令的输出：
```bash
toggle)
    touch /tmp/waybar-toggle-triggered
    {
        echo "=== $(date -Iseconds) ==="
        echo "state_before=$(ncm_status)"
        state=$(ncm_status)
        case "$state" in
            playing|paused) $NCM_CLI stop 2>&1 ;;
            *)              heartbeat_play 2>&1 ;;
        esac
        echo "state_after=$(ncm_status)"
        sync_state
    } >> /tmp/ncm-toggle-debug.log 2>&1
    ;;
```
检查 `/tmp/ncm-toggle-debug.log` 找卡在哪一行。

**4. 对比终端和 waybar 子进程环境**（怀疑 PATH/HOME 时）：
```bash
# 终端能跑通
/home/dr/.local/bin/ncm-cli state --output json | head -1

# 用最小 PATH 模拟 waybar 子进程
env -i PATH=/usr/bin:/bin HOME=$HOME /home/dr/.local/bin/ncm-cli state --output json 2>/dev/null
# → 如果输出不一致，就是 PATH 缺失
```

**最常见的坑（按发生频率）**：
1. **PATH 缺失 `~/.local/bin`** → `#!/usr/bin/env node` 静默失败（见 double-layer PATH 节）
2. **脚本里有 `ncm` 而非 `ncm-player` 全名** → bash 找不到
3. **脚本用 `$NCM_CLI` 但 `$HOME` 在子进程空** → 路径变成 `/.local/bin/ncm-cli`
4. **handler 中有 `return 1` 但脚本有 `set -e`** → 整个脚本立即退出，后续 sync_state 不跑
5. **ncm-cli 进程卡在网络请求** → heartbeat_play 的 `ncm-cli user favorite` 可能 30s+ 无响应

### foot has no --float flag

> 完整说明见 `sway-daemon-persistence` 技能"外部组件启动模式 → 浮动终端：foot --float flag 不存在"。

To launch a floating terminal from waybar on-click:
    on-click: foot -a ncm-login -w 80x24 /home/dr/.local/bin/ncm-login
Then in sway config:
    for_window [app_id=ncm-login] floating enable

### SWAYSOCK stale env disabling sway/window modules

Full fix + repro: see `references/orphan-process-protocol.md` § "SWAYSOCK stale env". The short version: re-resolve SWAYSOCK with `ls -t /run/user/1000/sway-ipc.*.sock | head -1` before each waybar start. `ls` (alphabetical) gives the lowest-PID socket, not the current one.

### mpv-mpris 0.7.x "PlaybackStatus always Stopped" bug

**发现日期**: 2026-06-24

**症状**: 即使在播（`time-pos` 跑到 54s, `eof-reached=false`），D-Bus `PlaybackStatus` 始终返回 `"Stopped"`。

**根因**: `mpv-mpris_0.7.1-1+b1` (Debian package) 的 PlaybackStatus 属性实现有 bug。mpv 通过 IPC 加载文件后，mpv-mpris 正确注册 D-Bus 接口、更新 Metadata（title/artist/url/length）、跟踪 Position，但 PlaybackStatus 卡在初始值 "Stopped" 不更新。

**修法（workaround）**：不允许 waybar 根据 PlaybackStatus 隐藏模块。把 `format-stopped` 设为跟 `format` 一样的参数，强制显示 Metadata：

```json
"mpris": {
    "format": " {player_icon} {artist} - {title}",
    "format-stopped": " {player_icon} {artist} - {title}",
}
```

**验证方法**：
```bash
dbus-send --session --dest=org.mpris.MediaPlayer2.mpv --type=method_call \
  --print-reply /org/mpris/MediaPlayer2 org.freedesktop.DBus.Properties.Get \
  string:"org.mpris.MediaPlayer2.Player" string:"PlaybackStatus"
# → variant string "Stopped"  ← 即使实际在播

# 对比 mpv 内部状态
python3 -c "
import socket,json
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
s.settimeout(3)
s.connect('/home/dr/.config/ncm-cli/mpv.sock')
s.sendall(json.dumps({'command':['get_property','time-pos']}).encode()+b'\n')
d=b''
while 1:
    c=s.recv(4096)
    if not c: break
    d+=c
    if c[-1]==10: break
print(d.decode())
s.close()
"
# → {"data":54.088,"error":"success"}  ← 实际在播
```

### mpv-mpris 0.7.x "PlaybackStatus always Stopped" bug — 终极修复：自定义模块替换 mpris

**发现日期**: 2026-06-24（工作日志）
**状态**: mpv-mpris 0.7.1 C 源码级别的 bug，不重新编译无法根治。waybar 的 mpris 模块即使设了 `format-stopped` 也不更新（"player stopped, skipping update"）。

**终极方案**：用 `custom/ncm-nowplaying` 自定义模块替换 waybar 内置 mpris 模块，直接从 `/tmp/ncm-state.json` 读歌曲信息，**完全绕过 mpv-mpris D-Bus**。

```json
// waybar config — 删除 mpris，添加 custom/ncm-nowplaying
"modules-right": [
    "custom/ncm-nowplaying",  // 替换原来这里的 "mpris"
    ...
],
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

```bash
# ncm-player waybar-nowplaying — 连续 exec 输出 JSON（含 tooltip）
waybar-nowplaying)
    while SWAYSOCK=$(_ncm_current_swaysock); [ -n "$SWAYSOCK" ] && [ -S "$SWAYSOCK" ]; do
        python3 -c "
import json
d=json.load(open('/tmp/ncm-state.json'))
if d.get('status') in ('playing','paused'):
    title = d.get('current_title','')
    artist = d.get('current_artist','')
    status = d.get('status','')
    liked_id = d.get('liked_song_id','')
    cur_id = d.get('current_encrypted_id','')
    liked = '❤' if liked_id and liked_id == cur_id else '♡'
    status_icon = '▶' if status == 'playing' else '⏸'
    text = f'🎵 {artist} - {title}' if artist else f'🎵 {title}'
    tooltip = (
        f'🎵 歌曲: {title}\\n'
        f'🎤 歌手: {artist}\\n'
        f'❤ {liked}\\n'
        f'🔴 状态: {status_icon} {status}'
    )
    print(json.dumps({'text': text, 'tooltip': tooltip}))
else:
    print(json.dumps({'text': ''}))
"
        sleep 5
    done
    ;;

**优势**：
- 完全绕过 mpv-mpris bug（不受 PlaybackStatus 影响）
- tooltip 可以自由定制（歌曲/歌手/红心状态/播放状态）
- 停播时自动隐藏（输出 `{"text":""}`）
- workaround: `format-stopped` 只改显示文本，waybar 仍会"skip update"

### `exec_always exec waybar` 陷阱：sway 不 SIGTERM 旧进程（2026-06-24 实证）

**发现日期**: 2026-06-24

**错误假设**: `exec_always exec waybar` 在 sway reload 时应自动杀死旧进程。

**实证结果**——连续 reload 3 次后 `pgrep -a waybar` 显示 6 个实例（新旧累计）：

```
reload 前:  waybar -c config-top, waybar -c config-bottom     ← 2 个
reload 1:   +waybar -c config-top, +waybar -c config-bottom   ← 4 个
reload 2:   +waybar -c config-top, +waybar -c config-bottom   ← 6 个
```

**原因**: sway 的 `exec_always` 中，`exec` 替换当前进程后，新进程的父进程变为 init，sway 不再能追踪/杀它。sway reload 时找不到它来发 SIGTERM。

**修正后的推荐**：单条 `exec_always bash -c 'killall -e waybar; ...; waybar ... & waybar ... & wait'`

### Sway config: waybar 启动方式（2026-06-24 修正）

> 之前推荐 `exec_always exec waybar -c ...` 的写法**实测不对**——`exec_always` 重载时虽然重新执行命令，但**老的 waybar 实例并没有被 SIGTERM 杀掉**，导致每次 reload 累积 2 个 waybar。验证：连续 reload 3 次后 `pgrep -a waybar` 显示 6 个进程。

**✅ 正确写法**（已验证，3 次连续 reload 干净）：
```bash
# ~/.config/sway/config — Waybar 双栏
exec_always bash -c 'killall -e waybar 2>/dev/null; sleep 0.3; waybar -c ~/.config/waybar/config-top & waybar -c ~/.config/waybar/config-bottom & wait'
```

**关键点**：
- `killall -e waybar` — `-e` = exact name match（**不是 `-x`，那是 pkill 的 flag**）。杀进程名精确为 `waybar` 的所有进程，但**不杀 bash 自身**（bash 进程名是 `bash`，不是 `waybar`）
- `sleep 0.3` — 给旧 waybar 退出缓冲（关 GTK/GPU 需要时间）
- **单条 exec_always 包两个 waybar**——避免两条 exec_always 互相杀的 race condition
- `&` 后台启动 + `wait` 保活——sway 追踪 bash 进程；sway reload SIGTERM bash 时，bash 退出触发 `&` children 收到 SIGHUP 一起退出
- 整个命令包在 `bash -c '...'` 里——单条 exec_always 即可，不需要两条 + wrapper script

**为什么不能用两条 exec_always**：如果分两条，第二条启动的 bash 会先 `killall -e waybar`，把第一条刚启动的 waybar 也杀掉。两条都会执行，但顺序导致 race condition。

**为什么不能只写 `exec_always exec waybar`（实证有 bug）**：
```
reload 1: 1 个 waybar-top + 1 个 waybar-bottom
reload 2: 2 个 waybar-top + 2 个 waybar-bottom（旧的没被 SIGTERM）
reload 3: 3 个 waybar-top + 3 个 waybar-bottom
```
旧 waybar 一直累积（虽然 exec_always 重跑命令启动新的，但 sway 不自动 kill 旧的）。

**为什么 `pkill -f "waybar -c"` 是自杀陷阱**：bash 的 cmdline 包含 `waybar -c ~/.config/waybar/config-top`，`pkill -f "waybar -c"` 会匹配 bash 进程自身 → bash 死在 `sleep 0.3` 之前 → 新 waybar 永远不启动。

**为什么 `killall -x waybar` 也是错的**：`killall` 没有 `-x` flag（`-x` 是 pkill 的）。正确的是 `killall -e`（exact）或 `killall -r ^waybar$`（regex）。

**❌ 反面**（不要用）：
```bash
# 反面 1: pkill -f 自杀
exec_always bash -c 'pkill -9 -f "waybar -c" 2>/dev/null; sleep 0.3; waybar ... & waybar ... &'

# 反面 2: exec_always exec 累积（之前推荐，实证有 bug）
exec_always exec waybar -c ~/.config/waybar/config-top
exec_always exec waybar -c ~/.config/waybar/config-bottom

# 反面 3: killall -x 不存在
exec_always bash -c 'killall -x waybar 2>/dev/null; ...'

# 反面 4: 写 wrapper script（用户偏好"别越走越偏"——能用 shell 一行解决就不要额外脚本层）
exec_always /home/dr/.local/bin/waybar-restart.sh
```

**手动启动 waybar 时**（hermes terminal / TTY）才需要显式设 SWAYSOCK：
```bash
SWAYSOCK=$(ls -t /run/user/$(id -u)/sway-ipc.*.sock | head -1) waybar -c ~/.config/waybar/config-top
```

**Hermes terminal SWAYSOCK trap**：当从外部 shell（hermes terminal、SSH 长连）手动启动 waybar 时，shell 里的 `$SWAYSOCK` 可能指向已死的旧 socket（sway 重启后 PID 变了但 shell 残留旧值）。永远用 `ls -t | head -1` 重新解析。

### modules overflow on narrow portrait screens
X1 Tablet eDP-1 transform 270 + scale 2.0 = ~1000px logical width. 14+ modules-right can overflow, hiding 6-7 modules off-screen right.

**Fix**: 缩 mpris `max-length` 到 18-20（省 ~80px）；砍 modules 必须先问用户；外接屏（DP-5 3840px）装得下所有。

**核心原则**: 不要私自删除或重排用户已有的 system-status modules（temperature/cpu/memory/pulseaudio/network/tailscale/deepseek-cost/tray/clock）。它们被直接写在 modules-right 数组里，不是自动生成的。

### waybar-mpris 模块是只读的（一个 click handler）

`waybar-mpris` 模块**没有 dropdown、没有 button**。要 N 个可点击动作，就声明 N 个 `custom/*` 模块，每个独立 `on-click`。把 `toggle/like/fm/login` 全做在一个 mpris 模块上做不到。

### 替换 module 时保留空字符串占位符

`waybar format-icons` 数组里的空字符串 `""` **不是缺漏**，是 Nerd Font PUA 码位的占位符（waybar 读这些位置填图标）。替换 module 时如果误删，音量/电池/网络模块的图标消失。复制现有 module 时**整段保留** array 元素个数。

### config-top / config-bottom 是独立配置

新 module 必须**同时**加到 config-top 的模块定义块 **和** `modules-left` / `modules-right` 数组。只加定义不加数组，module 不出现；只加数组不加定义，waybar 启动报错。verifying：`waybar -l debug | grep "Bar configured"`。

### waybar-mpris `ignored-players` 防 Chrome 抢断

默认 waybar-mpris 会监听**所有** MPRIS 客户端。Chrome 的 MediaSession 会和 mpv 抢断（两个同时显示，互相打断）。配置 `"ignored-players": ["chromium.instance*"]` 只让 mpv 显示。

### mpris tooltip `\n` 必须 JSON 转义

waybar mpris 模块的 tooltip 字段里换行要写 `"\\n"`（源码里就是字面两个字符 `\` + `n`）。如果写成 `\n`（一个换行符），JSON 解析失败，tooltip 显示为原始 `\n` 而不是真换行。**bug 现象**：tooltip 完全没有换行，单行很长。

### custom 模块空 exec 仍占位

`custom/*` 模块的 `exec` 返回空字符串时，**GTK 不会自动隐藏**，会渲染成带 padding 的 0-width label，仍然占空间。两种修法：

```css
#custom-ncm-like, #custom-ncm-pl, #custom-ncm-fm { min-width: 0; }
```
配合 exec 返回空字符串，module 折叠到 0 宽（但还在 GTK box 里，sibling spacing 留缝）。

真不可见：要么从 `modules-right` / `modules-left` 配置里删，要么用 `return-type: json` + `{"text":"","class":"hidden"}` + CSS `.hidden { display: none !important; }`。

### `format-stopped` 用 `""` 而非 `" "`

**症状**: waybar mpris 停止时 module 显示灰色占位，占水平空间。

**原因**: `format-stopped: " {}"` 中的一个字面 space 被渲染成灰色占位。`format-stopped: ""`（空字符串）才让 GTK 不渲染。

**修法**: 
```json
"mpris": { "format-stopped": "", ... }
```
再加 CSS `#custom-mpris { min-width: 0; }` 确保 GTK 折叠空间。

**⚠️ 2026-06-24 发现：空字符串可能导致 "闪一下消失"**。如果 mpris 闪烁（mpv stopped→playing 过渡时先占 0 高度再出现），改为静态图标：
```json
"mpris": { "format-stopped": " ⏸", ... }
```
这样模块始终可见，不会因空字符串导致的 0→nonzero 高度切换闪烁。折衷：停止时也占空间。

### mpris `interval` 默认 5s 拦截 "Playing" 信号

**症状**: 播放已触发，waybar mpris 仍显示 "Paused" 或 "mpv-playing" 几秒后才更新。

**原因**: waybar mpris 模块默认 `interval=5`，低于该值的 update 会被限流拦截。Stopped→Playing 过渡的 mpris 信号可能在 ~200ms 内到达，被拦截。

**修法**: 设 `interval: 0`（每次都跑完整逻辑）。mpris 信号本身不频繁（只在状态切换时发），零开销。

**验证**: `waybar -l debug` 触发播放后应出现 `mpris[mpv]: running update`。

### emoji 在 waybar 显示成方块

**症状**: Nerd Font PUA 码位的图标显示成方块或问号。

**原因**: PUA 码位（如 U+F00C）需要 8 位 hex 字面量。bash `printf '\xf00c'` 只解析 2 位 hex → `\xf0` + `0c`，产生错误字符。

**修法**: 用 8 位 hex。bash 用 `\U0000F00C`，Python 用 `'\U0000F00C'`。或 `python3 -c "import sys; sys.stdout.write(...)"` 替代 printf。

### Requested height: 26 < 35 required warning

**症状**: waybar debug log 报 `Requested height: 26 < 35 required`。

**修法**: config 写 `"height": 35`（任意低于 35 的值都会被 waybar 强制修正）。

### pulseaudio format-icons 为空 → 音量图标消失

**症状**: waybar 音量模块只显示 "100%" 或 "静音"，无图标。

**原因**: `format-icons.default` 数组 3 个元素全为空字符串：
```json
"format-icons": {
  "default": ["", "", ""],
  "default-muted": ["", "", ""]
}
```
`{icon}` 渲染为空。

**修法**: 填 Nerd Font 码位（fa-volume-down/up/off）：
```json
"format-icons": {
  "default": ["\uf027", "\uf027", "\uf028"],
  "default-muted": ["\uf026", "\uf026", "\uf026"]
}
```

**验证**: `wpctl set-volume @DEFAULT_AUDIO_SINK@ 30%` 后图标应出现。

