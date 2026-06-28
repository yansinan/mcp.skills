# ncm-watch — sway 退出检测 + 服务生命周期

## 问题

用 `BindsTo=graphical-session.target` 的服务只在**用户注销**时停止，但 sway 退出（重启/切换 tty）时 `graphical-session.target` 仍存活，服务继续运行。

## 方案

sway `exec_always` 启动一个 watcher 脚本，轮询 `$SWAYSOCK`。sway 退出时 socket 消失 → watcher 执行 `systemctl --user stop`。

## 实现

### 独立脚本

```bash
# ~/.local/bin/ncm-watch
#!/usr/bin/env bash
# sway 退出时自动停止 daemon
set -eo pipefail        # 注意：不用 -u，$SWAYSOCK 可能未设置

pkill -f "ncm-state-daemon.watch" 2>/dev/null || true

systemctl --user start ncm-state-daemon.service

while [ -S "$SWAYSOCK" ]; do sleep 2; done

systemctl --user stop ncm-state-daemon.service
```

### sway config

```bash
exec_always bash -c 'pkill -x ncm-watch 2>/dev/null; sleep 0.2; exec /home/dr/.local/bin/ncm-watch'
```

### 验证

```bash
# 启动
swaymsg reload

# 检查 watcher 是否在跑
pgrep -a -f ncm-watch

# 模拟 sway 退出（仅测试用）
# SWAYSOCK 消失 → while 结束 → systemctl stop
```

## 边界情况

| 事件 | 行为 |
|------|------|
| sway 启动 | exec_always 启动 watcher → start daemon → 进入 while 循环 |
| sway reload | pkill 旧 watcher → 新 watcher start daemon（幂等）→ while |
| sway 退出 | SWAYSOCK 消失 → while 结束 → stop daemon |
| watcher 被误杀 | daemon 保持运行（Restart=on-failure 自动恢复）|

## 注意事项

- `exec` 替换 shell 进程，不会留下多余 bash 外壳
- `pkill -x` 按进程名精准匹配，`-f` 会匹配命令行（可能误杀）
- `$SWAYSOCK` 由 sway 传给子进程。如果未设置，watcher 退出但不影响 daemon
