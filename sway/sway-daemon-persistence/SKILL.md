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

一个经过实战检验的完整配置（4 个 timeout + 2 个 resume 配对）：

```
~/.config/swayidle/config

timeout 60    → --mark-idle / --mark-active       # idle 标记, 供 sway-session daemon
timeout 3600  → --screen-off / --screen-on         # 关/开 Philips 4K 外屏
timeout 3600  → sway-screensaver-day.sh / close    # 白天 6-22: 浏览器全屏屏保
timeout 3600  → sway-suspend-if-night.sh           # 夜晚 22-6: systemctl suspend
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

swayidle timeout 3600 调 `sway-suspend-if-night.sh` → systemctl suspend。s2idle 期间 swayidle 被 freeze_processes 冻，唤醒后自动 unfreeze。systemd service 对 freeze/unfreeze 透明——不会视作进程死了重启。

### sudo 命令的执行上下文

swayidle 跑在 systemd --user service 里（非 root，非交互式）。`systemctl suspend` 无需 root（logind 通过 polkit 授权），但 `systemctl hibernate` 或 `rtcwake` 需要 root。

**给 dr 用户配 NOPASSWD**（可选，仅给电源管理命令）：

```
dr ALL=(ALL) NOPASSWD: /usr/bin/systemctl suspend, /usr/bin/systemctl hibernate, /usr/sbin/rtcwake
```

或用 `systemctl suspend -i`（--user inhibit），无需 sudo。

## 经验教训（实际踩过的坑）

### 1. exec_always 是陷阱
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

### 5. swayidle 日志走 journald

systemd 管理后，日志不再写 `/tmp/swayidle.log`。
```bash
journalctl --user -u swayidle.service -f  # 实时跟踪
journalctl --user -u swayidle.service -n 50 --no-pager  # 最近 50 条
```

### 6. RestartSec 别设太短

`RestartSec=0` 或 `1` 可能导致 swayidle 连续 crash 后频繁 restart 冲刷 journal。实测 `RestartSec=2` 够用。

### 7. swayidle 重启后计时重置

swayidle 被 systemd 重启（无论什么原因）后，idle 计时从 0 开始。如果要"用户离开 1 小时才触发"，从重启时刻重算 1 小时。不影响实际使用（用户本来也没活动）。

## References

- [swaywm wiki — Systemd integration](https://github.com/swaywm/sway/wiki/Systemd-integration)
- `man systemd.unit` — `BindsTo=`、`PartOf=`、`Restart=` 语义
- `man sway` — `exec` vs `exec_always` 区别
- `man 5 systemd.service` — `Type=simple` / `Type=forking` 行为
