# ncm-player 心动模式自动续播（heart-watcher）

## 问题

`ncm-player toggle` → `heartbeat_play` 调用 `ncm-cli recommend heartbeat --count 40` 拉一批歌曲播完就停。用户播完列表后没新一批接上，必须手动再点一次。

`ncm-cli state` 末尾会显示 `status=stopped, currentIndex=queueLength-1`，但 ncm-cli 不会自己续播。

## 修复方案

后台 watcher 循环（marker 文件控生命周期）：

```bash
# 标记文件控制 watcher 启停
/tmp/ncm-heart-session         # 存在 = watcher 运行中
/tmp/ncm-heart-watcher.log     # 运行日志

heart_watcher_loop() {
  local logfile=/tmp/ncm-heart-watcher.log
  echo "[$(date -Iseconds)] watcher started" >> "$logfile"

  while [ -f /tmp/ncm-heart-session ]; do
    sleep 5
    [ ! -f /tmp/ncm-heart-session ] && break

    state_json=$($NCM_CLI state 2>/dev/null) || continue
    [ -z "$state_json" ] && continue

    # 解析 status / currentIndex / queueLength
    W_STATUS= W_CUR= W_TOTAL=
    eval "$(echo "$state_json" | python3 -c '
import json,sys
try:
    s=json.load(sys.stdin).get("state",{})
    print(f"W_STATUS={s.get(\"status\",\"\")!r}")
    print(f"W_CUR={s.get(\"currentIndex\",-1)!r}")
    print(f"W_TOTAL={s.get(\"queueLength\",0)!r}")
except: pass
' 2>/dev/null)"
    [ -z "$W_STATUS" ] && continue

    # 续播条件：stopped 且已到队列末尾
    if [ "$W_STATUS" = "stopped" ] \
       && [ "$W_CUR" -ge 0 ] \
       && [ "$W_TOTAL" -gt 0 ] \
       && [ "$W_CUR" -ge $((W_TOTAL-1)) ]; then
      echo "[$(date -Iseconds)] playlist ended (cur=$W_CUR total=$W_TOTAL), refilling" >> "$logfile"
      $NCM_CLI queue clear >/dev/null 2>&1
      sleep 1
      if heartbeat_play >> "$logfile" 2>&1; then
        echo "[$(date -Iseconds)] refill ok" >> "$logfile"
      else
        echo "[$(date -Iseconds)] refill failed, watcher exiting" >> "$logfile"
        rm -f /tmp/ncm-heart-session
      fi
    fi
  done
  echo "[$(date -Iseconds)] watcher exiting" >> "$logfile"
}
```

`toggle` case 改动：

```bash
toggle)
  state=$(ncm_status)
  case "$state" in
    playing|paused)
      $NCM_CLI stop >/dev/null 2>&1
      rm -f /tmp/ncm-heart-session                    # ← 关键：删标记让 watcher 退出
      pkill -f "ncm-player.*heart_watcher_loop" 2>/dev/null || true
      echo "已停止"
      ;;
    *)
      if heartbeat_play; then
        rm -f /tmp/ncm-heart-session
        touch /tmp/ncm-heart-session                  # ← 关键：写标记 + 启 watcher
        pkill -f "ncm-player.*heart_watcher_loop" 2>/dev/null || true
        ( heart_watcher_loop ) &
        disown
      fi
      ;;
  esac
  sync_state
  ;;
```

## 关键设计

- **Marker 文件 = 状态机**：用 `/tmp/ncm-heart-session` 文件存在/不存在表示"是否在心动模式"。`toggle` 启停时同步更新标记。watcher 只检查标记，不需要 IPC。
- **退出检测**：watcher 循环开头检查 marker，循环内每 5 秒再查一次。`toggle stop` 删除标记后 watcher 在 ≤5 秒内自然退出。
- **续播识别**：用 `status=stopped` + `currentIndex >= queueLength-1` 识别"自然播完"（不是用户中途 stop）。`queue clear` 不会误触发（queueLength=0 时条件不成立）。
- **不嵌套**：watcher 内部调 `heartbeat_play` 时不再启 watcher（避免递归），只由 `toggle` 的 `*` 分支启动一次。

## 验证

```bash
# 1. 启心动
ncm-player toggle
# 期望：返回 "artists - name" 立即，2 秒内日志出现 "watcher started"
tail -f /tmp/ncm-heart-watcher.log

# 2. watcher 进程在跑
pgrep -af heart_watcher_loop
# 标记文件存在
ls /tmp/ncm-heart-session

# 3. 主动停
ncm-player toggle
# 期望：5 秒内日志出现 "watcher exiting"，标记文件删除
ls /tmp/ncm-heart-session    # No such file

# 4. 端到端续播：让列表播完，应自动拉新一批（日志出现 "playlist ended, refilling"）
```

## Pitfall

- **`pkill` 在 `set -e` 下**：`pkill` 没匹配进程时返回 1，会被 `set -e` 当成错误退出。务必加 `|| true` 或 `2>/dev/null || true`。
- **disown 的 background subshell**：`set -e` 对 `&` 后台 subshell 的退出码不检查，可放心用。
- **race：用户 stop 正好赶在 watcher 续播中**：`toggle stop` 已删标记，watcher 已开始 refill。refill 完成后新歌会播。要避免可加 marker 前置二次检查，但通常不必要（用户可再点一次 stop）。
- **debug 标记别用 `touch`**：`touch` 创建空文件，验证时只能靠 `ls -la` 看时间戳。要带时间戳信息用 `date +%s > /tmp/marker` 或 `echo "[$(date -Iseconds)]" >> /tmp/log`。
- **不要用 `sh -c` 包装 on-click 测 toggle**：waybar 的 `g_spawn_command_line_async` 直接 fork+execve，shell 不是必须的。直接在 ncm-player 内部 `touch /tmp/marker` 第一行就是最简的测试方法（用户的"调试插标记在真实代码路径"原则）。
- **`currentIndex` 是 0-based**：`ncm-cli state` 返回的 `currentIndex` 比 1-based 队列小 1。所以判断末尾用 `cur >= total-1`。
