# swayidle `resume` 关键字不接受 timeout 参数

## 症状

swayidle.service ExecStart 写成多行：

```ini
ExecStart=/usr/bin/swayidle -w \
  timeout 60 '/path/script --mark-idle' \
  resume 60 '/path/script --mark-active' \
  timeout 3600 '/path/script --screensaver-day' \
  ...
```

启动后 journalctl 立刻刷屏：

```
swayidle[468719]: 2026-07-02 10:02:29 - [Line 884] Unsupported command '/path/script --mark-active'
systemd[950]: swayidle.service: Main process exited, code=exited, status=255/EXCEPTION
systemd[950]: swayidle.service: Failed with result 'exit-code'.
systemd[950]: swayidle.service: Scheduled restart job, restart counter is at 1.
```

service `Restart=always` + `RestartSec=2` → 2s 后再拉 → 同样错 → 循环。重启 counter 几十次/分钟。

## 根因

`man swayidle` 写：

> timeout <timeout> <timeout command> [resume <resume command>]

**容易误读为** `resume <timeout> <command>`，实际是 `resume <command>` —— resume 是**活动时立即触发**，不再接 timeout。

swayidle 解析 argv 时：
- `timeout 60 'X --mark-idle'`：两个 token 后是 `'X --mark-idle'`（整体 token，OK）
- `resume 60 'X --mark-active'`：把 `60` 当 command → 整体失败？还是把 `'X --mark-active'` 当 command 但因含 `--` 触发 getopt 解析？

实测**第二个**是 unsupported 报错对象（`/path/script --mark-active`），说明 swayidle **接受**单引号整串，但参数布局错。

最稳写法：让 swayidle 走 `~/.config/swayidle/config`，**单行一条 rule**。

## 正确写法

### A. service ExecStart 单行（最简）

```ini
[Service]
ExecStart=/usr/bin/swayidle -w
```

### B. `~/.config/swayidle/config`

每条规则**单行写完**：

```ini
# 60s 标记 idle (供 sway-session daemon 跳过 5 分钟自动保存)
timeout 60 '~/Scripts/sway-session --mark-idle' resume '~/Scripts/sway-session --mark-active'

# 10 分钟关内置屏 eDP-1 (用户回来自动开)
timeout 600 '~/Scripts/sway-session --screen-off-internal' resume '~/Scripts/sway-session --screen-on-internal'

# 1 小时白天 (6-22) 屏保
timeout 3600 '~/Scripts/sway-session --screensaver-day' resume '~/Scripts/sway-session --screensaver-close'

# 1 小时夜晚 (22-6) s2idle (脚本内时间窗判定)
timeout 3600 '~/Scripts/sway-session --suspend-if-night'
```

**关键约束**（来自 swayidle 源码 `main.c`）：
- `parse_command(argc - 2, &argv[2])` 拿 timeout command 整串
- 整体交给 `sh -c param` 执行 —— 字符串里 `--args` 都正常传
- `resume` 关键字**只接一个 token**（command 整串），**不接 timeout**

## 调试步骤

1. 停 service：`systemctl --user stop swayidle.service`
2. 前台跑 swayidle 同等命令行，强杀 timeout 5s：
   ```bash
   timeout 3 /usr/bin/swayidle -w \
     timeout 60 '/path/script --mark-idle' \
     resume '/path/script --mark-active' \
     before-sleep '/bin/true' 2>&1
   echo "exit: $?"
   # exit 124 (timeout 强杀) = 解析成功
   # exit 255 + "Unsupported command" = 解析失败
   ```
3. 若失败 → 检查 `resume 60` 这种多出来的数字
4. 改回单行 ExecStart + config 文件方案

## 排错清单

| 现象 | 原因 | 修法 |
|---|---|---|
| `Unsupported command 'X --mark-active'` | `resume 60` 多写 timeout | 删 `60` |
| `Failed to parse get BlockInhibited property: Invalid argument` | swayidle 1.9 DBus 集成 warning，**非致命** | 忽略，swayidle 继续跑 |
| service 反复 restart counter 递增 | 上面 1 触发的死循环 | 修 config |
| 60s 等不到 marker | 全屏视频/Chrome idle-inhibitor enabled | `swaymsg -t get_tree` 查 `idle_inhibitors.application: enabled` |
| 60s 等不到 marker 但 service OK | `graphical-session.target` 没 active | `loginctl show-session` 看 `Type=unspecified` |

## 防回归

- service ExecStart 一律 `swayidle -w` 单行
- 规则全进 `~/.config/swayidle/config`
- 加新规则用 `timeout N 'cmd --arg'` 模板，**不要写 `timeout N 'cmd' resume N 'cmd2'`**
- 改完 `systemctl --user daemon-reload + restart swayidle.service` 验证
