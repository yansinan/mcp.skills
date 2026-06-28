# Swayidle Idle Timeout 调试与调试捷径

## 调试目标：缩短 idle 时间到 30s 快速验证 swayidle 是否触发

不要等 1 小时才知道配置对不对。改 30s，鼠标键盘停 30s 立即看效果。

## Step 1: 改一条 timeout 到 30s 测试

只动一条（最直观的那条），不要全改。推荐 screensaver-day 那条，因为它会启动 Chrome 屏保（有视觉反馈）。

```bash
# 备份
cp ~/.config/swayidle/config ~/.config/swayidle/config.bak

# 改一条
sed -i 's/timeout 3600 ~/Scripts\/sway-session --screensaver-day/timeout 30 ~\/\Scripts\/sway-session --screensaver-day/' ~/.config/swayidle/config
```

## Step 2: 重启 swayidle

```bash
systemctl --user restart swayidle
```

注意：swayidle 通常会被它的子进程拖住，systemd stop-sigterm 超时 90 秒才 SIGKILL。**这是诊断信号，不是 bug**：

```
swayidle.service: State 'stop-sigterm' timed out. Killing.
```

如果看到这行，说明 swayidle 的某个 timeout 命令有"挂着的子进程"问题（详见 `references/parse-command-argv0-bug.md`）。

## Step 3: 看 journal 验证

```bash
journalctl --user -u swayidle -f
```

成功触发应看到：
```
swayidle[3564031]: [session] screensaver: 已启动 Chrome 屏保
```

## Step 4: 恢复 3600

测试完恢复：
```bash
mv ~/.config/swayidle/config.bak ~/.config/swayidle/config
systemctl --user restart swayidle
```

## 调试 checklist（按顺序）

1. **swayidle 在跑吗？** `pgrep -a swayidle`
2. **service active？** `systemctl --user is-active swayidle`
3. **graphical-session.target active？** `systemctl --user is-active graphical-session.target`
4. **WAYLAND_DISPLAY 注入了吗？** `cat /proc/$(pgrep swayidle)/environ | tr '\0' '\n' | grep WAYLAND`
5. **swayidle 在等事件吗？** `cat /proc/$(pgrep swayidle)/wchan` → 应是 `do_epoll_wait`
6. **子进程有残留吗？** `ps -o pid,ppid,stat,etime,cmd --ppid $(pgrep swayidle)` → 应空（否则 timeout 触发了挂死进程）
7. **timeout 命令真的执行了吗？** `journalctl --user -u swayidle -n 30 | grep -i "session"` → 应看到对应的子命令日志

如果 1-5 都 OK 但 6 有 sh/python3 子进程残留且 7 没看到日志 → **100% 是 swayidle parse_command argv0 陷阱**。详见 `references/parse-command-argv0-bug.md`。