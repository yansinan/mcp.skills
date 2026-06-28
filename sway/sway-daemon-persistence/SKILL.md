---
name: sway-daemon-persistence
description: "Sway 组件持久化方案 — 用 systemd --user 守护 swayidle/sway-session 等进程，绑定其生命周期到 graphical-session.target，解决 crash 后不重启、sway 退出后进程孤立、exec_always 进程堆积三个问题"
---

# Sway 组件持久化方案

## 问题

Sway 管理的后台进程（swayidle、sway-session daemon、屏保等）有三个常见死法：

| 问题 | 表现 | 原因 |
|------|------|------|
| **Crash 后不重启** | 屏不关、布局不存 | `exec` 只启动一次，进程死后没有自动恢复机制 |
| **Sway 退出后进程孤立** | 日志里还有 swayidle 在跑 | 用 `setsid` 或 shell & 启动的进程独立于 sway session |
| **exec_always 堆积** | 每次 swaymsg reload 多一个进程 | `exec_always` 不会杀旧的，每次 reload 增量 fork |

## 方案：systemd --user + BindsTo=graphical-session.target

```
sway 启动 → graphical-session.target active
                ↓ BindsTo= (强绑定)
        systemd --user services
          ├─ swayidle.service        (Restart=always)
          ├─ sway-session.service    (Restart=always, --daemon 模式)
          └─ 其他 sway 扩展服务
                ↓ sway 退出
        graphical-session.target 销毁
                ↓ BindsTo=
        所有 services 立即 stop
```

## 适用范围

| 组件 | sway config 启动 | systemd 守护 | 说明 |
|------|-----------------|-------------|------|
| swayidle | ✗ 注释掉 | ✓ 全托管 | idle 检测 + timeout 事件 |
| sway-session daemon | ✗ 只保留 restore 行 | ✓ daemon 部分 | restore 一次性、daemon 长跑 |
| 屏保 | ✗ 注释掉 | ✓ 全托管 | 或由 swayidle timeout 触发 |
| kanshi | ✗ 用 exec（auto swap 不需要持久化） | 可选 | 自动显示器切换，一般 crash 概率低 |
| waybar/wob | ✗ 不推荐 | 可选 | sway bar 类自带内置重启机制 |

## Implementation

### Step 1: 编写 service 文件

`~/.config/systemd/user/swayidle.service`

```ini
[Unit]
Description=Sway idle manager
After=graphical-session.target
BindsTo=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/swayidle -w
Restart=always
RestartSec=2

[Install]
WantedBy=graphical-session.target
```

`~/.config/systemd/user/sway-session.service`（如果 sway-session 支持 `--daemon` 子命令）

```ini
[Unit]
Description=Sway session layout auto-save (5min tick, idle-aware)
After=graphical-session.target
BindsTo=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=/path/to/sway-session.py --daemon
Restart=always
RestartSec=5

[Install]
WantedBy=graphical-session.target
```

**关键字段**：
- `BindsTo=` — **强绑定**：sway 退出时 service 立即停（不依赖 service 自己检测）
- `PartOf=` — **附属关系**：sway 退出时 service 被标记为停止
- `After=` — **启动顺序**：等 sway 起来后再跑
- `Restart=always` — **进程死后自动重启**（RestartSec=N 秒延迟）
- `WantedBy=graphical-session.target` — **开机/登录时自动启动**
- `Type=simple` — **前台进程**（ExecStart 的命令不要 daemonize 自己）

### Step 2: 安装 + 启用

```bash
systemctl --user daemon-reload
systemctl --user enable swayidle.service
systemctl --user start swayidle.service
```

### Step 3: 从 sway config 删掉对应的 exec 行

编辑 `~/.config/sway/config`：

```
# swayidle 由 systemd 守护, sway config 不再 exec
# exec swayidle -w
```

### Step 4: 杀旧的独立进程（如有）

```bash
# 找旧进程
pgrep -ax swayidle

# 逐个杀（可能有多个，用 PID 别误伤 systemd 的新进程）
kill <旧PID>
# 如果 kill -15 无效，用 kill -9

# 验证只有 systemd 管理的在跑
systemctl --user status swayidle.service
```

### Step 5: 验证

```bash
# 状态
systemctl --user status swayidle.service

# 日志 (最近 10 条)
journalctl --user -u swayidle.service --no-pager -n 10

# 依赖链 (验证 BindsTo)
systemctl --user list-dependencies swayidle.service

# graphical-session.target 是否 active
systemctl --user is-active graphical-session.target
```

## 验证流程（端到端）

### 1. 正常启动
```bash
systemctl --user start swayidle.service
systemctl --user is-active swayidle.service
# 输出: active
```

### 2. Crash 自动重启（模拟）
```bash
# 记录当前 PID
OLD=$(systemctl --user show swayidle.service -p MainPID | cut -d= -f2)
echo "Old PID: $OLD"

# 杀了它
kill -9 $OLD
sleep 3

# 新 PID 出现
NEW=$(systemctl --user show swayidle.service -p MainPID | cut -d= -f2)
echo "New PID: $NEW"
# Old != New → 自动重启成功
```

### 3. Sway 退出后停（不可在线测，仅验证配置）
```bash
# 检查 dependency — BindsTo=graphical-session.target 应在链中
systemctl --user list-dependencies swayidle.service

# 真退出 sway 后（需另一会话检查）
systemctl --user is-active swayidle.service
# 应显示 inactive
```

## swayidle 配置编排（4 个实际事件）

swayidle 允许多个 timeout 事件独立并发注册（每个事件各自计时、各自触发）。单 config 文件可混搭多个 3600s 事件，只是它们**共享 idle 检测源**（ext-idle-notify 协议）。

**⚠️ 关键 pitfall：swayidle `parse_command` 只取 argv[0]，后续所有参数被丢弃。所有 timeout 命令必须用引号包裹。** 来源：swayidle `main.c:752`
```c
cmd->idle_cmd = parse_command(argc - 2, &argv[2]);
// parse_command 内部 return strdup(argv[0]);
// 然后 cmd_exec 用 sh -c param 执行
```
也就是说 `timeout 60 ~/Scripts/sway-session --mark-idle` 实际执行 `sh -c "/home/dr/Scripts/sway-session"`，**`--mark-idle` 被丢弃**。无参数调用 sway-session 会进入 daemon 模式（永不退出），不是用户期望的子命令。

**正确写法**：用单引号把命令+参数包成一个 token：
```
timeout 60 '~/Scripts/sway-session --mark-idle' resume '~/Scripts/sway-session --mark-active'
```
此时 argv[2] = `~/Scripts/sway-session --mark-idle`（一个字符串），swayidle 把它整体交给 `sh -c`，sh 自己解析字符串执行完整命令。

**症状**：journalctl 出现重复 N 次的 `[session] ✓ 已保存 3 个工作区` (N=timeout 触发次数)，systemd `restart swayidle` 卡 90 秒 `stop-sigterm` 超时后 SIGKILL（因为 swayidle 等 sh 子进程退出，sh 等 python3 daemon 退出）。

**自动验证脚本**：`scripts/validate-swayidle-config.sh` —— 一键扫描 config 找出未引号包裹的 timeout 命令。
**完整诊断流程 + 决策树**：见 `references/idle-tuning-test.md`。
**症状/触发链/为什么容易漏掉的深层分析**：见 `references/swayidle-parse-command-argv0-bug.md`
- **swayidle 1.9 BlockInhibited DBus 错误** — `before-sleep /bin/true` 放 service 文件 `ExecStart`（不能放 config），详见 `references/swayidle-1.9-blockinhibited-bug.md`
- **swayidle 闲置孤儿进程检测** — `pgrep -af sway-session` 找 PPID=1 的孤儿; `kill` 清理。
- **屏保配置简化 (kiosk, 无 profile)** — `references/screensaver-kiosk-config.md` — Chrome kiosk 屏保方案，简化自 helix 验证通过的做法
**Trixie ↔ Sid 版本升级坑矩阵（sway 1.10.1↔1.12 / swayidle 1.8↔1.9）**：见 `references/sway-version-upgrade-pitfalls.md` —— 配套 IPC 兼容性（BlockInhibited）、dpkg conffile 解决配方、内存陈旧二进制检测、孤儿进程清理、XDG_RUNTIME_DIR 下 marker 路径、完整升级+验证 workflow。

一个经过实战检验的完整配置（4 个 timeout + 2 个 resume 配对）：

```
~/.config/swayidle/config

timeout 60    → --mark-idle / --mark-active       # idle 标记, 供 sway-session daemon
timeout 600    → --screen-off / --screen-on         # 关/开 Philips 4K 外屏 (10 分钟)
timeout 3600  → sway-screensaver-day.sh / close    # 白天 6-22: 浏览器全屏屏保
timeout 3600  → systemctl suspend -i                 # 夜晚 22-6: s2idle (用户级，无 sudo)
```

### 白天浏览器屏保

6:00-22:00 期间 1 小时无活动 → 用 Chrome 全屏打开网页面，作为屏保。

**设计原则**：
- 用 `--user-data-dir=/tmp/...` 隔离屏保 Chrome 实例，不影响用户已有 Chrome session
- 用 `--new-window` 复用已有的 Chrome 进程（不是 fork 新的 Chrome 进程）
- resume 时先 `swaymsg [title=".*pattern.*"] kill` 正则匹配杀窗口，再 pkill 兜底

**打开脚本** (sway-screensaver-day.sh)：
```sh
#!/bin/sh
# 仅在 6-22 白天打开屏保
hour=$(date +%H)
if [ "$hour" -ge 6 ] && [ "$hour" -lt 22 ]; then
    google-chrome --new-window --start-fullscreen \
        --user-data-dir=/tmp/sway-screensaver-data \
        --ozone-platform-hint=auto \
        --no-first-run --noerrdialogs \
        --disable-pings --media-router=0 \
        "http://home.z-core.cn:8080/screensaver.web/"
fi
```

**关闭脚本** (sway-screensaver-close.sh)：
```sh
#!/bin/sh
# swaymsg 正则匹配窗口标题 (PCRE, 不是 shell glob!)
swaymsg '[title=".*Screen Saver.*"] kill' 2>/dev/null
sleep 0.5
# pkill 兜底: 杀特定 user-data-dir 的 Chrome 进程
kill $(pgrep -f "sway-screensaver-data" 2>/dev/null) 2>/dev/null
```

**关键**：swaymsg criteria 的 `title=` 字段用 **PCRE 正则**（不是 glob），所以匹配任意子串必须用 `.*Screen Saver.*`。用 `*Screen Saver*`（裸星号）会报 `quantifier does not follow a repeatable item` 错误。

| 写法 | 结果 |
|------|------|
| `[title="Screen Saver"]` | 精确匹配 — 只有窗口标题完全等于 "Screen Saver" 才命中 |
| `[title=".*Screen Saver.*"]` | ✅ 正则 — 标题包含 "Screen Saver" 就命中 |
| `[title="*Screen Saver*"]` | ❌ 报错 — `*` 前面没有可重复元素 |

### 昼夜时间窗口（22:00-06:00 触发 s2idle，06:00-22:00 触发屏保）

swayidle 本身不内置时间判断。时间窗口通过脚本内的 `date +%H` 检查实现：

```sh
hour=$(date +%H)
# 白天模式 (6-22): 浏览器屏保
if [ "$hour" -ge 6 ] && [ "$hour" -lt 22 ]; then
    google-chrome ...
fi
# 夜晚模式 (22-6): s2idle
if [ "$hour" -ge 22 ] || [ "$hour" -lt 6 ]; then
    systemctl suspend
fi
```

**边界值**（已验证）：
- hour=5 → `< 6` → 夜间 → s2idle
- hour=6 → `>= 6` → 白天 → 屏保
- hour=21 → `< 22` → 白天 → 屏保
- hour=22 → `>= 22` → 夜间 → s2idle

### systemctl --user restart 可能 hang

`systemctl --user restart swayidle.service` 发 SIGTERM 给 swayidle 后，如果 swayidle**正在跑 resume 子命令**（--screen-on / --mark-active），子进程不立即退出 → swayidle 进程在 SIGTERM handler 里等子进程完成 → systemd 等 `stop-sigterm` 超时（90 秒默认）。

**解决**：用 `kill -9 <PID>` 强杀 + `systemctl --user reset-failed` + `systemctl --user start swayidle.service`。

## 诊断模式

### 检查 swayidle 是否真的连上了 sway

```
# 查看 swayidle 进程树
pstree -aps $(pidof swayidle)

# 查看 swayidle 的 SWAYSOCK 指向
cat /proc/$(pidof swayidle)/environ | tr "\0" "\n" | grep SWAYSOCK

# 对比当前 sway 的 SWAYSOCK
ls /run/user/$UID/sway-ipc.*
```

sway 重启后，swayidle 的 SWAYSOCK 仍是旧的（已不存在的 socket），此时 idle 检测静默失效。  
**必须** `systemctl --user restart swayidle.service`。

### 孤儿进程检测

```
# 找 PPID=1 (init 收养) 且不属于 systemd 的孤儿
ps -eo pid,ppid,etime,command | awk '$2 == 1 && $4 !~ /systemd/'
# 杀掉确认
kill <PID>
```

sway 重启过程中 `BindsTo=graphical-session.target` 的子进程可能变成孤儿（PPID=1）。定期扫描清理。

### 进程树诊断

```
# swayidle 的子进程（正常：无或 1 个 short-lived sh）
pgrep -P $(pidof swayidle) -a

# sway-session 进程
pgrep -af sway-session

# 查看 journal 确认 idle 是否触发
journalctl --user -u swayidle -n 10 --no-pager
grep -E "mark|screensaver|suspend|跳过"
```

### 参考文件

此技能目录下另有以下参考文件（`references/` 目录），覆盖本次 session 中的具体场景：

- `swayidle-1.9-blockinhibited-bug.md` — swayidle 1.9.0 BlockInhibited DBus 错误及 `before-sleep true` 修复
- `sway-version-upgrade-pitfalls.md` — sid 源临时升级 sway/swayidle 的步骤与 dpkg conffile 处理
- `swayidle-wrapper-default-daemon-pitfall.md` — swayidle fork 出的 sh+python 陷入 main loop 的陷阱
- `swayidle-parse-command-argv0-bug.md` — swayidle 命令解析 argv0 bug
- `swayidle-config-edit-recovery.md` — config 编辑后恢复流程（清理孤立进程、重启验证）
- `idle-not-triggering-diagnosis.md` — idle 不触发的系统性诊断工作流（7 步清单含引号/SWAYSOCK/before-sleep 检查）

## 边界情况

### sway-session 的特殊处理

sway-session 脚本的 `exec sway-session.py`（restore + daemon 合一）不能直接转为 systemd service，因为：

- sway config 里 `exec sway-session.py` 先 restore 布局，再进入 daemon 循环（5 分钟 tick + idle 检查）
- systemd 启动 `sway-session.py --daemon` 只进 daemon 循环，不做 restore
- 如果同时保留 sway config 里的 `exec` 行 + systemd service → **两个进程重叠**

**推荐处理**：
1. sway config 保留 `exec sway-session.py`（restore + daemon — 启动时恢复布局）
2. systemd 的 sway-session.service **暂不启用**（等脚本拆出 `--restore-only` 子命令后，二者分离）
3. 风险：daemon 部分死后不自动重启，5 分钟布局跳过。权衡后接受

**如果脚本支持**`--restore-only`：
```diff
 # ~/.config/sway/config
-exec /home/dr/Scripts/sway-session.py
+exec /home/dr/Scripts/sway-session.py --restore-only   # 仅恢复, 不进 daemon
```
systemd service 负责 daemon。

### 22:00-06:00 时间窗口触发 s2idle

swayidle timeout 3600 直接调 `systemctl suspend -i`（无需 sudo，user 级通过 logind/polkit 授权）→ s2idle。s2idle 期间 swayidle 被 freeze_processes 冻，唤醒后自动 unfreeze。systemd service 对 freeze/unfreeze 透明——不会视作进程死了重启。

### sudo 命令的执行上下文

swayidle 跑在 systemd --user service 里（非 root，非交互式）。`systemctl suspend` 无需 root（logind 通过 polkit 授权），但 `systemctl hibernate` 或 `rtcwake` 需要 root。

**给 dr 用户配 NOPASSWD**（可选，仅给电源管理命令）：

```
dr ALL=(ALL) NOPASSWD: /usr/bin/systemctl suspend, /usr/bin/systemctl hibernate, /usr/sbin/rtcwake
```

或用 `systemctl suspend -i`（--user inhibit），无需 sudo。

## 经验教训（实际踩过的坑）

### 1. exec_always 不换行 + 不堆积

**换行陷阱**：sway config 里 `exec_always` 后面的命令不能换行——换行符被 sway 当成命令分隔符。所有逻辑必须一行写完或用独立脚本文件（见上节「关键约束」）。

**堆积陷阱**：`exec_always` 每次 sway reload 都 fork 新进程，旧的活着。
```diff
-# 不要这样写
-exec_always swayidle -w
+# 每次 swaymsg reload 都会 fork 一个新的 swayidle，旧的还活着
+# 正确做法：exec swayidle -w（不要 always）+ systemd 守护
```

### 2. setsid 导致孤立进程

`setsid swayidle -w` 创建独立 session leader。sway 退出后 swayidle 是 init 收养的子进程，永不死。**必须用 systemd BindsTo 避免**。

### 3. 旧进程杀不干净

`setsid` 创建的进程是 session leader，SIGTERM 可能被特定进程无视。实测 `kill -9 <PID>` 才有效。如果 pkill，小心误杀 systemd 的进程。

### 4. graphical-session.target 不一定 active

sway 从 TTY 手动启动（无 display manager）时，graphical-session.target 默认不 active。

**解决**：sway config 里显式启动：
```
exec systemctl --user start graphical-session.target
```

或让 systemd service 采用 `WantedBy=default.target` 兜底（但这样 sway 退出后无法自动停）。

### 5. swayidle wrapper 脚本必须显式要求 subcommand（不要默认进 daemon）

如果 wrapper（如 `~/Scripts/sway-session`）在没有参数时进入 daemon 主循环，swayidle fork 出的 `sh -c wrapper` 子进程永远不退出 → systemd 发 SIGTERM 时 swayidle 等子进程 → Timeout → SIGKILL 全家 → service restart thrash + 孤儿进程（PPID=1）累积数天。

修复：wrapper 必须 `sys.exit("usage: ...")` 当 `len(sys.argv) < 2`。详见 `references/swayidle-wrapper-default-daemon-pitfall.md`。

快速自检：`timeout 5 sh -c "$HOME/Scripts/<wrapper> --<subcommand>"` 必须在 1 秒内退出，rc=0。运行到 5s = 有这个 bug。

### 6. swayidle 日志走 journald

systemd 管理后，日志不再写 `/tmp/swayidle.log`。
```bash
journalctl --user -u swayidle.service -f  # 实时跟踪
journalctl --user -u swayidle.service -n 50 --no-pager  # 最近 50 条
```

### 6. RestartSec 别设太短

`RestartSec=0` 或 `1` 可能导致 swayidle 连续 crash 后频繁 restart 冲刷 journal。实测 `RestartSec=2` 够用。

### 7. swayidle 重启后计时重置

此后 `sway --version` 应显示新版本（如 1.12）。

**参考**：`references/sway-sid-upgrade-dpkg-conffile.md` — 完整升级步骤 + 验证。

### 8. sway 重启后 systemd --user 服务 SWAYSOCK

**现象**：swayidle 不触发 idle（mark-idle / screensaver 全静默）、sway-session 不保存布局。`journalctl --user -u swayidle` 无 idle 事件。

**根因**：`swaymsg exit + exec sway` 后新 sway 生成新 IPC socket（`/run/user/\$(id -u)/sway-ipc.*.sock`），但 swayidle.service / sway-session.service 的环境变量 `SWAYSOCK` 仍指向旧 socket。旧 socket 文件已删除（`(deleted)` 标记）。swayidle 启动时固定了 `SWAYSOCK`；sway-session daemon 的 `find_swaysock()` 只在 `main()` 入口调用一次，后续 `save()` 循环不再重新发现。

**修复**：每次 sway 重启后立即：
```bash
systemctl --user restart swayidle.service
systemctl --user restart sway-session.service
```

**验证**：
```bash
cat /proc/$(pidof swayidle)/environ | tr '\0' '\n' | grep SWAYSOCK
# 应输出当前 sway 的 socket 路径
ls /run/user/$(id -u)/sway-ipc.*.sock
```

### 9. sway-session daemon PID 堆积

**现象**：`pgrep -af "sway-session.py --daemon"` 显示多个 daemon 进程（预期 1 个），旧进程 PPID=1（孤儿）或无 SWAYSOCK。

**根因**：多次 `systemctl --user start` 未先 stop、或 sway 多次重启间旧 daemon 未清理。PID 不断积压。

**修复**：
```bash
pgrep -af "sway-session.py --daemon"
# 只保留最大的 PID（最新），杀其余的
kill <多余PID>
```

**代码级修复建议**：sway-session 的 `save()` 函数应在每次调用前重新 `find_swaysock()`，而非只启动时固定一次。

### 10. swayidle.service RestartSec 2s 避免日志洪泛

`RestartSec=2` 在 crash-restart 循环时防止 journal 被刷屏。经验值：`RestartSec=0` 或 `1` 导致 swayidle 连续 crash 日志翻几十倍，`RestartSec=2` 已够用。

## 外部组件启动模式（sway 级，归此处）

sway reload / 启动外部组件（waybar / mpv / ncm 等）有多个 sway 级陷阱，分散在各应用 skill 中都重复出现。这里集中维护，所有应用 skill 应 cross-ref 本节而非复制。

### SWAYSOCK stale env — 仅发生在从外部 shell 手动启动 waybar

**核心事实**：sway 的 `exec`/`exec_always` **会自动为子进程设置正确的 `SWAYSOCK`**（sway 内部调用 `setenv("SWAYSOCK", ipc_socket->path, true)`）。所以从 sway config 启动的 waybar 永远拿到正确 socket。

**`SWAYSOCK` 过期只在以下场景发生**：
- 从**外部 shell**（TTY、hermes terminal、SSH）手动启动 waybar
- 外部 shell 的 `SWAYSOCK` 环境变量指向**旧的 sway session**（sway 重启后 PID 变了，但 shell 里残留旧值）
- sway 重启后 **systemd --user 服务也出现同样的 stale SWAYSOCK 问题**（见第 10 节）

**修复（外部 shell）**：`export SWAYSOCK=$(ls /run/user/$(id -u)/sway-ipc.*.sock 2>/dev/null | head -n 1)`
**正确方案（2026-06-24 已验证 — 推翻之前推荐写法）**：sway config 用 `exec_always bash -c 'killall -e waybar; ... & ... & wait'`。**不要用 `exec_always exec waybar -c ...`**。

```bash
# ✅ sway config — Waybar 双栏（2026-06-24 验证）
exec_always bash -c 'killall -e waybar 2>/dev/null; sleep 0.3; waybar -c ~/.config/waybar/config-top & waybar -c ~/.config/waybar/config-bottom & wait'
```

**关键点**：
- `killall -e waybar` — `-e` = exact name match（**不是 `-x`，那是 pkill 的 flag**）。杀进程名精确为 `waybar` 的所有进程，但**不杀 bash 自身**（bash 进程名是 `bash`）
- `sleep 0.3` — 给旧 waybar 退出缓冲（关 GTK/GPU 需要时间）
- **单条 exec_always 包两个 waybar**——避免两条 exec_always 互相杀的 race condition
- `&` 后台启动 + `wait` 保活——sway 追踪 bash 进程；sway reload SIGTERM bash 时 bash 退出触发 `&` children 收到 SIGHUP 一起退出
- 整个命令包在 `bash -c '...'` 里——单条 exec_always 即可，不需要两条 + wrapper script

**❌ 之前错误推荐**（2026-06-24 之前写法，实测有 bug 已推翻）：
```bash
exec_always exec waybar -c ~/.config/waybar/config-top
exec_always exec waybar -c ~/.config/waybar/config-bottom
```

**为什么这种"exec + exec_always"不对**：sway 的 `exec_always` 重跑时**不会自动 SIGTERM 上次的 exec_always 启动的子进程**——只重跑命令启动新的。验证：连续 reload 3 次 → `pgrep -a waybar` 显示 6 个进程（旧 waybar 全留着）。用户报告"重载出来两个 waybar 了"是真实 bug，不是误判。

**❌ 不要用 `pkill -f "waybar -c"`**：bash 的 cmdline 包含 `waybar -c ~/.config/waybar/config-top`，`pkill -f "waybar -c"` 会匹配 bash 进程自身 → bash 死在 `sleep 0.3` 之前 → 新 waybar 永远不启动。

**详细排查 + 重载验证流程**：见 `waybar-config` 技能"## Pitfalls → Sway config: waybar 启动方式（2026-06-24 修正——之前推荐写法有 bug）"节。

**从外部 shell 手动启动时**才需要显式设 SWAYSOCK：
```bash
SWAYSOCK=$(ls -t /run/user/$(id -u)/sway-ipc.*.sock | head -1) waybar -c ~/.config/waybar/config-top
```

### sway exec_always while 循环进程堆积（ncm-watch 模式）

**核心问题**：sway 用 SIGTERM 杀 `exec_always` 起的 `bash -c '...'` 进程组，当 `bash -c` 内嵌 `while [ -S "$SWAYSOCK" ]; do sleep 2; done` 时——杀的是 bash，但 sleep 在极短的信号窗口期内可能幸存，积累成僵尸进程。

**实际观测**：sway reload 6 次 → 12 个残存 `sh -c bash -c '... while [ -S "$SWAYSOCK" ]...'` 进程。

**修复方案**：抽到独立脚本，`exec_always` 只做 `pkill + exec`：

```bash
# sway config
exec_always bash -c 'pkill -x ncm-watch 2>/dev/null; sleep 0.2; exec /home/dr/.local/bin/ncm-watch'
```

```bash
# ~/.local/bin/ncm-watch
#!/usr/bin/env bash
set -eo pipefail
pkill -f "ncm-state-daemon.watch" 2>/dev/null || true
systemctl --user start ncm-state-daemon.service
while [ -S "$SWAYSOCK" ]; do sleep 2; done
systemctl --user stop ncm-state-daemon.service
```

**`set -u` 陷阱**：`$SWAYSOCK` 在 exec_always 上下文可能**未设置**，`[ -S "$SWAYSOCK" ]` 触发 `-u` 错误直接退出。脚本用 `set -eo pipefail`（无 `-u`）或在访问前检查。

**旧建议修正**：之前声称 "sway reload 自动 SIGTERM 旧的 exec_always 进程组，不需要手动清理"——该结论对 while 循环不成立。sway 的进程组信号对嵌套 bash -c while 模式有遗漏。

**对 waybar 不需要这种修复**：waybar 没有 while 循环，单纯的 `exec_always exec waybar` 就够了（sway 自动管 PID）。见上文 "SWAYSOCK stale env" 节。

> **2026-06-24 已弃用**：此独立脚本模式已合并到 ncm-player daemon 自身。SWAYSOCK 通过文件传递（见下方「sway 退出检测：SWAYSOCK 文件传递」节），systemd 管理单实例，不再需要独立 watch 脚本。

### 浮动终端：foot --float flag 不存在

`foot --float` **不存在**。foot 浮窗通过 sway IPC 的 floating 窗口规则实现，不在命令行 flag 里。

**waybar on-click 调 foot 时必须加 `-H`（hold）**，否则命令执行完后终端立即关闭：

```bash
foot -H -e /path/to/login-script   # QR 码一闪而逝，必须 -H
```

**`-w` vs `-W` 区别**（foot 1.21）：
- `-w` = `--window-size-pixels`（**像素**，`-w 80x24` 窗口仅 80×24 像素，几乎不可见）
- `-W` = `--window-size-chars`（**字符**，`-W 80x24` 窗口 80 列 × 24 行，正确终端大小）

```bash
# waybar on-click 调扫码登录窗口
"on-click": "foot -a ncm-login -W 80x24 -H /path/to/login-script"
```

**sway `for_window` 浮窗规则**（QR 扫码窗口固定大小+居中）：

```bash
for_window [app_id="ncm-login"] floating enable
for_window [app_id="ncm-login"] resize set 700 400
for_window [app_id="ncm-login"] move position center
```

拆成 3 行（sway for_window 多命令分隔符文档没说清，3 行最稳）。

### 关键约束：sway exec/exec_always 不支持换行

> **这是 sway 配置写命令最常见的坑，也是最多话（wasted time）的原因。**

sway 解析 config 文件时，每个 token 按**空格/制表符**分割，**换行符是命令分隔符**。所以：

```
# ❌ 错误 — 多行写法
exec_always bash -c '
  systemctl --user start ncm-state-daemon.service
  while [ -S "$SWAYSOCK" ]; do sleep 2; done
'

# 等价于 sway 解析成三条命令：
#   exec_always bash -c '
#   systemctl --user start ncm-state-daemon.service
#   while [ -S "$SWAYSOCK" ]; do sleep 2; done
# — 除第一行外全报 "Unknown/invalid command"
```

**修正**：所有逻辑必须**内联成一行**，用 `;` 或 `&&` 分隔：

```
# ✅ 正确 — 一行写完
exec_always bash -c 'systemctl --user start ncm-state-daemon.service; while [ -S "$SWAYSOCK" ]; do sleep 2; done; systemctl --user stop ncm-state-daemon.service'
```

**如果逻辑超过一命令行放不下** → 抽到独立脚本，sway config 只写一行：

```bash
# ~/.config/sway/config
exec_always bash -c 'pkill -x ncm-watch 2>/dev/null; sleep 0.2; exec /home/dr/.local/bin/ncm-watch'
```

while / for / if / case 等结构化控制流必须进脚本文件，不能裸写在 sway config 里。

### sway 退出检测：SWAYSOCK 文件传递

当服务需要在 sway 退出时同步停止，但 systemd 环境无法继承 `$SWAYSOCK` 环境变量时：

**方案**：通过 `/tmp/ncm-swaysock` 文件传递 SWAYSOCK 路径。

```bash
# sway config
exec_always bash -c 'echo "$SWAYSOCK" > /tmp/ncm-swaysock; systemctl --user start ncm-state-daemon.service'
```

```bash
# daemon 内
SWAYSOCK=$(cat /tmp/ncm-swaysock 2>/dev/null || true)
while [ -n "$SWAYSOCK" ] && [ -S "$SWAYSOCK" ]; do
    # ... 每 2 秒轮询一次
done
systemctl --user stop ncm-state-daemon.service
```

**原理**：
1. sway `exec_always` 把 `$SWAYSOCK` 写进 `/tmp/ncm-swaysock`
2. daemon（systemd 启动，无 `$SWAYSOCK`）从文件读
3. 每轮 while 检查 socket 是否存在
4. sway 退出 → socket 删除 → while 结束 → stop 服务

**坑点**：
- **`PrivateTmp=true` 会使 daemon 的 `/tmp` 隔离**→ 读不到 `/tmp/ncm-swaysock` → while 不进入 → 服务秒退
- **`exec_always` 每 exec 一次** → sway reload 重写文件 → 新旧 daemon 都读同一文件，不影响（systemd 管单实例）

**行为矩阵**：

| 事件 | 服务状态 |
|------|---------|
| sway 启动 | systemctl start → daemon 启动 → while 循环 |
| sway reload | systemctl start (幂等) → 无变化 |
| sway 退出 | SWAYSOCK 消失 → while → systemctl stop |
| 用户注销 | systemd 自动停 (WantedBy=default.target) |

### 启动方式选择：exec / exec_always / nohup

| 场景 | 推荐 | 原因 |
|---|---|---|
| swayidle / mpv / 长时间守护进程 | systemd --user + BindsTo=graphical-session.target | 见本文档主方案 |
| 一次性脚本（登录后启动的帮手） | sway `exec`（不是 exec_always） | sway reload 不重复 |
| **waybar** | sway `exec_always exec waybar -c <config>`（不要 bash 包装） | sway 自动管 PID + 自动设 SWAYSOCK |
| **waybar** | sway `exec_always bash -c 'killall -e waybar; sleep 0.3; waybar ... & waybar ... & wait'` | sway reload 时显式 kill 旧 waybar + bash wait 兜底避免 zombie |

**为什么 waybar 用 bash 包装 + killall 而非 `exec_always exec waybar`**：
- `exec_always exec waybar` 看起来优雅但**实测有 bug**：sway 重跑命令启动新 waybar 时**不会 SIGTERM 旧 waybar**，连续 reload 累积（2026-06-24 验证：3 次 reload 后 6 个 waybar）
- `bash -c 'killall -e waybar; ...'` 显式杀旧 waybar → 0.3s 缓冲 → 启新 → `wait` 保活
- `&` 后台启动 + `wait` → sway 追踪 bash 进程；reload SIGTERM bash 时 bash 退出触发 `&` children 收到 SIGHUP 一起退出
- 单条 exec_always 包两个 waybar → 避免两条 exec_always 互相杀的 race condition
- 详细 pitfall 见 `waybar-config` 技能"## Pitfalls → Sway config: waybar 启动方式（2026-06-24 修正——之前推荐写法有 bug）"节

**为什么用 `nohup ... &` 而不是 `exec`**：`exec` 下 daemon 启动失败时没有任何错误输出。`nohup` + 日志文件可查 `/tmp/ncm-daemon.log` 定位问题。

### sway IPC 编程（脚本和 sway 通信）

sway 用 **i3 IPC 协议**（不是 raw JSON）。从脚本发命令必须包协议头：

```
b"i3-ipc\0" + 4-byte little-endian length + 4-byte little-endian type + payload
```

直接 `socket.connect + sendall(b'{"command":...}\n')` 会拿到 `Connection reset by peer`。

**两种用法**：

```python
# 方案 A：用现成库（推荐）
from i3ipc import Connection
i3 = Connection()
i3.command('reload')
i3.get_outputs()  # 返回 list of output dicts

# 方案 B：手搓协议头（调试 / 一次性 probe）
import socket, struct, json
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect('/run/user/1000/sway-ipc.1000.<pid>.sock')
payload = json.dumps({"command": ["get_outputs"]}).encode()
header = b"i3-ipc\0" + struct.pack("<II", len(payload), 0)  # type 0 = COMMAND
s.sendall(header + payload)
# 读响应同样要解析 i3-ipc 头
```

**典型用途**：脚本里查询 sway 状态（outputs / workspaces / tree），或从 cron / 通知事件触发 sway 操作。

## References

- [swaywm wiki — Systemd integration](https://github.com/swaywm/sway/wiki/Systemd-integration)
- `man systemd.unit` — `BindsTo=`、`PartOf=`、`Restart=` 语义
- `man sway` — `exec` vs `exec_always` 区别
- `man 5 systemd.service` — `Type=simple` / `Type=forking` 行为
