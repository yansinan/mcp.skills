# Chrome 全屏屏保 (kiosk 无 profile 简化版)

## 设计方案

**不建 Chrome profile** (`--user-data-dir`), 避免新 profile 卡在 Chrome 初始化界面。
直接 `--kiosk` 模式启动, 跟 helix 上的成功经验一致。

## 启动命令

```bash
# 30s idle 触发
google-chrome --kiosk http://home.z-core.cn:8080/screensaver.web/?interval=600
```

**对比旧方案 (已废弃)**

| 旧方案 | 新方案 | 原因 |
|--------|--------|------|
| `--new-window --start-fullscreen` | `--kiosk` | 隐含全屏, 更简洁 |
| `--user-data-dir=/tmp/...` | (无) | 新 profile 卡初始化 |
| `--disable-pings --media-router=0` | (无) | 新版 Chrome 不识别, 会报 warning |
| `--ozone-platform-hint=auto` | (无) | kiosk 模式下 auto 即可 |
| `--no-first-run --noerrdialogs` | (无) | kiosk 模式默认跳过首次运行 |

## 清理 (resume 触发)

**关键原则:** 不要 `pkill` 杀进程 — 屏保 Chrome 跟用户的 WebUI Chrome 是**同一个实例**,
杀进程 = 杀整个浏览器。必须用 `swaymsg` 按窗口**标题**精确关窗口。

```python
# 正确: swaymsg 按精确标题关窗口 (不杀进程)
swaymsg '[title="Screen Saver"]' kill
```

**`--new-window` 标志** 让屏保在新窗口打开, 配合 swaymsg 杀窗口, 只关屏保窗口不影响其他标签页。

**不要用:**
- `pkill -f "interval=600"` — 杀整个 Chrome 进程
- `pkill -f "google-chrome.*kiosk"` — 同理, 杀全家
- `swaymsg '[title=".*Screen Saver*"]'` — regex `.*Screen Saver*` 在 PCRE 里 =
  `Screen Save` + `r*` (零或多个), 误匹配含 "Screen Save" 的所有窗口

### DBus 错误

Chrome 启动时可能输出:
```
ERROR:dbus/bus.cc:405] Failed to connect to the bus
ERROR:google_apis/gcm/engine/registration_request.cc:291] Registration response error
```

均为**非致命**警告。DBus 错误是 Chrome 尝试连 session bus 时的消息, GCM 错误是
内网环境下无法连 Google 推送服务的结果。不影响全屏显示。

## 时区

hour 检查使用 `time.localtime().tm_hour` (系统本地时区),
两台机器都是 `Asia/Hong_Kong (HKT, +0800)` = 北京时间, 无需额外修复。

## 相关

- sway-session.py 的 `screensaver_day()` 和 `screensaver_close()` 函数
- swayidle config: `timeout 30 '...sway-session --screensaver-day' resume '...sway-session --screensaver-close'`