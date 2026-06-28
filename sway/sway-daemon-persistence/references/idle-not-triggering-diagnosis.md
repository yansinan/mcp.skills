# Idle 不触发 — 系统性诊断工作流

## 症状
空闲 60s+ 后 `/run/user/1000/sway-user-idle` 不存在，screensaver 不弹出，关屏/s2idle 无效。

## 检查清单（按顺序）

### 1. 进程存活
```bash
pidof swayidle
systemctl --user is-active swayidle
```
→ 进程不存在 / inactive → restart swayidle.service

### 2. SWAYSOCK 一致性（sway 重启后必查）
```bash
# swayidle 连的 socket
cat /proc/$(pidof swayidle)/environ | tr "\0" "\n" | grep SWAYSOCK
# 实际存在的 socket
ls /run/user/1000/sway-ipc.*.sock
# 当前 sway 进程
pgrep -a "^sway$"
```
→ 不一致 → `systemctl --user restart swayidle.service`（或 SIGKILL + start）

### 3. 错误日志
```bash
journalctl --user -u swayidle -n 20 --no-pager | grep -E "BlockInhibited|Failed|error"
```
→ `BlockInhibited` 错误 → swayidle 1.9.0 bug，需 `before-sleep /bin/true` 在 ExecStart（见 references/swayidle-1.9-blockinhibited-bug.md）
→ 无输出 → 往下走

### 4. Config 文件引号检查
```bash
cat ~/.config/swayidle/config | grep -E "^timeout|^before-sleep|^resume"
```
**每一条 `timeout` / `resume` 如果有参数，必须用单引号包裹整个命令。**
```
✅ timeout 30 '~/Scripts/sway-session --screensaver-day'
❌ timeout 30 ~/Scripts/sway-session --screensaver-day  (--screensaver-day 被忽略)
```
swayidle parser **只取第一个 token**，带参命令必须封装为脚本或用引号。
→ 缺引号 → 补上，restart swayidle.service

### 5a. sway-session.service 状态检查
```bash
systemctl --user is-active sway-session.service
systemctl --user is-enabled sway-session.service
```
→ inactive / not in graphical-session.target.wants/ → enable + start
```bash
systemctl --user enable sway-session.service
systemctl --user start sway-session.service
# 验证：
ls ~/.config/systemd/user/graphical-session.target.wants/
# 应有 sway-session.service
pgrep -af "sway-session.py --daemon"
# 预期：1 个（最新的 daemon）
```

注意：sway-session daemon 的 `save()` → `swaymsg()` → `find_swaysock()` 调用链自带自愈能力，
每个 5 分钟 tick 会自动重新发现当前 SWAYSOCK，sway 重启后无需额外操作。
但 daemon 进程本身必须活着。

### 5b. 积压 daemon 进程检查
```bash
pgrep -af "sway-session.py --daemon"
```
预期：1 个（当前 sway-session.service）。如果 >1 个，大部分是孤儿/旧进程。

清理方法：
```bash
# 先看有哪些
pgrep -f "sway-session.py --daemon" | sort -n
# 只保留最旧的（第一个=sway-session.service 自动拉起的），杀其余的
# 或更简单：全杀，让 systemd 重新拉
sudo kill -9 $(pgrep -f "sway-session.py --daemon" | tail -n +2)
systemctl --user restart sway-session.service
```

注意：旧 daemon 的 SWAYSOCK 可能指向已不存在的 sway PID，导致 swaymsg 调用全部静默失败。
每次 sway 重启后建议检查并清理积压 daemon。`save()` 函数内部通过 `swaymsg()` 包装器
每次调用前都会执行 `find_swaysock()` 动态刷新 SWAYSOCK，但 daemon 进程本身积累后的资源占用不健康。

### 6. 实测 idle 触发
切断所有输入事件（键盘/鼠标/触控板），等 60s 后：
```bash
ls -la /run/user/1000/sway-user-idle
journalctl --user -u swayidle --since "2 min ago" --no-pager | grep -E "mark|screensaver|idle"
```

预期 30s 后 screensaver 触发（6-22 时段），60s 后 idle marker 创建。

### 7. swayidle.service 文件核对（ExecStart）
```bash
grep ExecStart ~/.config/systemd/user/swayidle.service
```
`before-sleep` 必须写在 ExecStart 命令行（不能放 config 文件）：
```
ExecStart=/usr/bin/swayidle -w before-sleep /bin/true
```

## 要点汇总

| 检查点 | 工具 | 正常值 |
|--------|------|--------|
| 进程 | pidof / systemctl is-active | 在跑 / active |
| SWAYSOCK | /proc/PID/environ + ls /run/user | 指向当前 sway |
| BlockInhibited | journalctl | 不应有（或加 before-sleep 后工作） |
| 引号 | cat config | 全部 timeout 命令有单引号 |
| 积压进程 | pgrep sway-session | =1 个 |
| idle marker | ls /run/user/1000/sway-user-idle | 60s 后存在 |
