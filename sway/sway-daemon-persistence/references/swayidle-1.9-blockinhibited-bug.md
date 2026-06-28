# swayidle 1.9.0 BlockInhibited DBus 错误 (Issue #198)

## 症状

```
[Line 277] Failed to parse get BlockInhibited property: Invalid argument
```

idle 不触发：mark-idle 60s / screensaver-day 30s / screen-off 600s 全部静默。

## 根因

swayidle 1.9.0 引入了 `get_logind_idle_inhibit()` 调用，查询 logind 的 `BlockInhibited` DBus 属性。
仅在 `--before-sleep` 参数被传递时 `connect_to_bus()` 才会提前完成 DBus 握手，
使 `BlockInhibited` 查询获得正确的返回值格式。

**Issue**: https://github.com/swaywm/swayidle/issues/198 (open, unfixed)

## 修复方法

⚠️ **`before-sleep` 必须放在 `ExecStart` 命令行，不能放 `~/.config/swayidle/config`。**

`config` 文件里写的 `before-sleep` 在 `enable_timeouts()` 之后才被处理，
此时 `BlockInhibited` 查询已经失败。命令行参数的初始化顺序更早，
`connect_to_bus()` 在 `enable_timeouts()` 之前执行，DBus 握手正确完成。

### 正确做法

编辑 `~/.config/systemd/user/swayidle.service`：

```ini
[Service]
ExecStart=/usr/bin/swayidle -w before-sleep /bin/true
```

```bash
systemctl --user daemon-reload     # 改 service 文件后必须先 reload
systemctl --user restart swayidle.service
```

### 验证

```bash
# 等 30s 检查 screensaver / 60s 检查 idle marker
journalctl --user -u swayidle -n 10 --no-pager | grep -E "mark|screensaver|idle"
# 期望: [session] idle marker 已创建 ...
ls -la /run/user/1000/sway-user-idle
# 期望: 存在
```

注意: `BlockInhibited` 错误消息可能仍会在日志中出现一次 (在 `connect_to_bus()` 完成后
第一次查询时）, 但 idle 检测可以正常工作。**验证标准是 idle marker 是否存在, 不是错误消失。**

## 兼容性

| swayidle | sway | 兼容性 |
|----------|------|--------|
| 1.8.0 (trixie) | 1.10.1 (trixie) | ✅ 原生配套 |
| 1.9.0 (sid) | 1.10.1 (trixie) | ⚠️ BlockInhibited 错误; 加 `before-sleep true` 后 ok |
| 1.9.0 (sid) | 1.12 (sid) | ⚠️ 同前, 需 `before-sleep true` 直到上游修 #198 |

## 衍生效应对照

| 点 | 1.8.0 | 1.9.0 |
|----|-------|-------|
| 子进程策略 | 启动时 fork 所有 timeout 命令的 sh+python, 长期存活 | idle 触发时才 fork, 完成后退出 |
| SIGTERM 行为 | hang (子进程不退出) | hang (DBus 阻塞) |
| config before-sleep | 不支持 | 支持但初始化顺序错误 |
| dpkg 替换 | 正常 (压旧二进制的 (deleted) 跳过) | 同 |