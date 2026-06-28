# swayidle config 编辑后恢复流程

## 典型场景

修改 `~/.config/swayidle/config`（修 timeout 参数、加命令、调秒数）后，
需要执行以下完整的恢复步骤。

## 完整流程

```bash
# 1) 验证 config 语法 (检查引号问题)
bash ~/.hermes/skills/local_share/sway/sway-daemon-persistence/scripts/validate-swayidle-config.sh

# 2) 重启服务
systemctl --user restart swayidle.service

# 3) 验证服务状态
systemctl --user is-active swayidle.service
# 期望: active

# 4) 检查启动日志 (BlockInhibited 错误可接受)
journalctl --user -u swayidle -n 3 --no-pager | grep -v BlockInhibited

# 5) 清理旧的 sway-session daemon 进程
#    (因为旧的 config 可能 fork 了永不退出的 sway-session 守护)
#    检查:
pgrep -af "sway-session" | grep -v "sway-session.py --daemon" | grep -v grep
#    如果看到 sh -c sway-session / python3 sway-session（无 --daemon），杀掉:
#    kill <它们的_PID> (或全部 kill)

# 6) 验证 idle 触发
#    等 60s 不动键盘鼠标
ls -la /run/user/1000/sway-user-idle
#    期望: 文件存在 (mark-idle 60s timeout 创建)
```

## 常驻 daemon 的孤立进程问题

当 `~/.config/swayidle/config` 中 timeout 命令**缺少引号**时：

```
# ❌ 错误: parser 只取第一个 token "~/Scripts/sway-session"
timeout 60 ~/Scripts/sway-session --mark-idle resume ~/Scripts/sway-session --mark-active
```

swayidle 调用 `~/Scripts/sway-session`（无参），sway-session.py 检测到无参数后
进入**守护主循环**(daemon mode)，永不退出。当 config 被修复并重启 swayidle 后：

- 旧 swayidle 被杀 → 它的子进程 (sh + python3) 变成孤儿 (PPID=1)
- 新 swayidle 启动 → 正确调用 `--mark-idle` 短命子命令
- 孤立的 python3 daemon 继续用旧的 SWAYSOCK 连接，swaymsg 全部失败

**症状**: `pgrep -af sway-session` 显示多个进程，
部分或全部 `cat /proc/<PID>/environ | tr "\0" "\n" | grep SWAYSOCK` 为无或指向旧 sway。

**修复**: 杀掉所有 `pgrep -f "sway-session"` 里的可疑进程（带 `--daemon` 的正确守护除外）。

## sway-session.service 状态检查

sway 重启后，sway-session.service 可能不在 `graphical-session.target.wants/` 里：

```bash
ls /home/dr/.config/systemd/user/graphical-session.target.wants/
# 期望包含 sway-session.service

# 如果缺失:
systemctl --user enable sway-session.service
systemctl --user start sway-session.service

# 验证:
systemctl --user is-active sway-session.service
# 期望: active
```

## 验证全链

```bash
# mark-idle 60s → /run/user/1000/sway-user-idle 存在
test -f /run/user/1000/sway-user-idle && echo "✅" || echo "❌"

# screensaver-day 30s → journal 有记录
journalctl --user -u swayidle --since "1 min ago" | grep screensaver

# sway-session daemon 在跑
pgrep -af "sway-session.py --daemon" | grep -v grep

# SWAYSOCK 正确
cat /proc/$(pidof sway-session.py | head -1)/environ 2>/dev/null | tr "\0" "\n" | grep SWAYSOCK
```
