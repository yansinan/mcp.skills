# cgroup cleanup + Restart=always 死循环模式

## 现象

systemd --user service（swayidle、hermes-gateway、任何 user-level daemon）：

1. `Restart=always` + 短 `RestartSec` (2-5s)
2. service 启动时 `subprocess.Popen` 拉长寿命辅助进程（Chrome/agent-browser/长轮询 worker/mpv daemon）
3. service 主进程启动期校验失败快速退出（status=0/非0）
4. `ExecStopPost=` 跑清理脚本扫自己 cgroup，所有进程 SIGKILL
5. systemd Restart → 再起 → 再失败 → 再杀 → 循环

**用户感知**："为什么 [辅助进程] 在反复开关？"

## 真实案例：hermes-gateway.service 697 次重启

### 触发条件
`hermes-gateway.service` ExecStart:
```
/home/dr/.hermes/hermes-agent/venv/bin/python -m hermes_cli.main gateway run
```

服务单元：
```ini
Restart=always
RestartSec=5
KillMode=mixed
KillSignal=SIGTERM
ExecStopPost=-/home/dr/.hermes/hermes-agent/venv/bin/python -m gateway.cgroup_cleanup
```

启动 → weixin 平台配置校验失败：
```
ERROR gateway.run: Refusing to start: weixin has dm_policy/group_policy set to 'open' 
but neither GATEWAY_ALLOW_ALL_USERS nor WEIXIN_ALLOW_ALL_USERS is enabled.
ERROR gateway.run: Gateway exiting cleanly: weixin: open policy without allow-all opt-in
```

→ 干净退出 → systemd 5s 后 Restart → 再失败 → 循环。

期间 gateway 拉起 Chrome CDP 实例（`--remote-debugging-port=9222 --user-data-dir=/home/dr/.hermes/cdp-chrome`），整棵 Chrome 进程树 cgroup 在 hermes-gateway.service 下。每次 gateway 退出 → cgroup_cleanup.py SIGKILL 整棵树 → 下次再起 → 再杀。

实测 9:38-9:47（~10 分钟）内 **697 次重启**，Chrome 9222 PID 反复被换。

### 诊断命令

```bash
# 1. 看 service 重启频率
journalctl --user -u <service>.service --since '10 minutes ago' --no-pager | \
  grep -c 'Scheduled restart'

# 2. 看 SIGKILL 哪些辅助进程
journalctl --user -u <service>.service -n 200 --no-pager | \
  grep -E 'Killing process.*(chrome|chromium|agent-browser|mpv)' | tail -20

# 3. 看 cgroup 关系（确认辅助进程 cgroup 在 service 下）
systemctl --user status <service>.service --no-pager
# 输出 CGroup 树 → 看 service cgroup 下面挂着哪些进程

# 4. 看 ExecStopPost 跑啥
systemctl --user cat <service>.service | grep -A1 ExecStopPost
```

### 修复决策树

```
服务反复 restart 风暴
  │
  ├─ 1. 查启动失败根因 ──→ 修配置 (绝大多数情况, 这是真因)
  │     例: weixin policy / API key 缺失 / config schema 不匹配
  │
  ├─ 2. 启动期校验不可绕开但失败罕见 → 加节流
  │     Restart=always → Restart=on-failure
  │     + StartLimitBurst=5
  │     + StartLimitIntervalSec=300
  │     (300 秒内 5 次失败后停止重试, 防止日志/资源耗尽)
  │
  ├─ 3. 辅助进程需独立生命周期 → Delegate + Slice
  │     [Service]
  │     Delegate=true
  │     Slice=app-<service>-helpers.slice
  │     (systemd 233+ 支持, 辅助进程 cgroup 独立, service 退出不杀)
  │
  └─ 4. ExecStartPre 防多实例
        ExecStartPre=/usr/bin/pkill -f <helper> 2>/dev/null || true
        (每次启动前先杀旧实例, 避免 SIGKILL 遗漏导致多实例)
```

### 优先级

**永远先查 1 (启动失败根因)**。hermes-gateway 修 weixin policy 后 9:47 之后零次重启，Chrome 9222 稳定运行 4+ 分钟。

## cgroup_cleanup.py 模式溯源

`ExecStopPost=cgroup_cleanup.py` 是 issue #37454 的 workaround：service 主进程退出时，遗留在 cgroup 里的辅助进程（adb、platform bridges、CDP Chrome）会让 `Restart=always` 卡住（因为 cgroup 还活着）。解法是显式 SIGKILL。

源码 docstring（`gateway/cgroup_cleanup.py`）：
> "SIGKILL any process left in this systemd unit's cgroup. Runs as `ExecStopPost=` so it only fires after the gateway's main process has exited. The gateway already reaps its own tool subprocesses on a clean shutdown; this is the safety net for long-lived helpers it doesn't track (adb, platform bridges, etc.) that would otherwise be orphaned in the cgroup and block `Restart=always` — issue #37454."

**适用范围**：
- 任何 systemd --user service 启了不属于 service 主进程组的辅助进程
- 用了 `subprocess.Popen` 但没用 `start_new_session=True` 让辅助进程成为 session leader
- 用了 `Delegate=true` 的 service 不会触发（cgroup 已独立）

**反例**（不需要 cgroup_cleanup）：
- service 主进程是常驻守护，辅助进程是它的线程或显式管理的 child
- service 用 `Delegate=true` + `Slice=` 把辅助进程隔离

## 跟 swayidle 守护的对比

| 模式 | swayidle | hermes-gateway |
|---|---|---|
| 守护目标 | swayidle 进程 | gateway + Chrome CDP |
| 启停频率 | crash 时偶尔重启 | 配置错时疯狂重启 |
| 辅助进程 | 无（swayidle 单进程） | Chrome 9222 + crashpad handlers |
| cgroup cleanup 影响 | 不触发 | 每次 restart 杀 Chrome |
| 用户感知 | "屏保没跑" | "浏览器反复开关" |

**两类问题的根因不同**：
- swayidle → systemd 启动期 ConditionResult=no / graphical-session.target 没拉起（pitfall #4）
- hermes-gateway → service 配置导致启动期拒绝，触发 Restart 风暴

**共同修法原则**：
1. 查根因（journal + 启动错误信息）—— 别猜
2. 加节流（`StartLimitBurst` / `StartLimitIntervalSec`）—— 防止雪崩
3. 隔离 cgroup（`Delegate=true`）—— 防止 SIGKILL 误伤

## 防回归 checklist

- [ ] service 改完配置 `systemctl --user daemon-reload && restart`
- [ ] `journalctl --user -u <service>.service --since '5 minutes ago' | grep -c 'Scheduled restart'` 验证无新重启
- [ ] `systemctl --user status <service>.service` 看 `Active: active (running) since ...` 时间戳稳定
- [ ] 辅助进程 PID 不再反复换（`pgrep -af <helper> | head -1` 时间戳）

## 延伸阅读

- `man systemd.service` — `Restart=`, `StartLimitBurst`, `StartLimitIntervalSec`, `Delegate`
- `man systemd.kill` — `KillMode=mixed/control-group/process/none`
- `man systemd.resource-control` — `Slice=`, `CPUQuota=`, `MemoryMax=`
