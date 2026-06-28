---
name: sway-exec-always-safety
title: Sway exec_always 安全参考
category: sway
tags: [sway, exec_always, pkill, dedup, swayidle, config-reload]
description: |
  Reference for safe sway/i3 exec_always patterns: pkill+exec dedup wrapper,
  single-line quoting rules, Bash vs exec_always quoting conflict, and
  post-reload process hygiene.  Covers pitfalls from real-world swayidle,
  UxPlay, and persistent-daemon configurations.
source: man 5 sway; yansinan/mcpSway PRs; swayidle/UxPlay 实战
---

## §1 进程去重: 标准 pkill + exec 模式

`exec_always` 在 sway reload 时**重新执行**命令。不加去重会导致一个进程攒出多份实例 (swayidle 堆叠、UxPlay 残留、waybar 分身)。

标准做法: 每次执行前先 `pkill` 同名进程,再启动。

```bash
# 单命令模式 (写在 sway config 的一行里):
exec_always --no-startup-id pkill -x swayidle; exec swayidle -w ...

# 或封装为 wrapper shell 函数 (写在 ~/.config/sway/exec-wrappers.sh):
kill_and_exec() {
  local name="$1"; shift
  pkill -x "$name" 2>/dev/null
  exec "$@"        # exec 替换当前 shell 进程,防止堆积
}
```

在 sway config 中引用:
```
exec_always --no-startup-id exec-wrappers.sh swayidle -w ...
```

关键要求:
- `pkill -x` 匹配完整进程名,避免误杀 (例如 `pkill -x sway` 不会误杀 swayidle)
- 用 `-f` 匹配完整命令行时,模式要足够精确
- `exec` 替换 shell 进程,避免 wrapper shell 本身在进程列表里留下一层

## §2 陷阱与规则

### §2.1 sway config 不支持命令续行

**规则**: sway config 每一行是一条独立的命令。Bash 风格的 `\` 续行符**不生效**——反斜杠被当作普通字符传给 shell。

反例 (`\` 续行被 sway 当成新一行):
```
exec_always --no-startup-id long-command \
  --flag value \
  --another-flag
# sway 第二行是独立语句 → 解析为未识别命令 → silent ignore
```

正解: 全部写在一行;或把命令写在外部脚本里,config 只写一行 `exec_always` 调用脚本。

超长命令拆进 wrapper script 的典型做法:
```bash
# ~/.config/sway/exec-wrappers.sh
launch_complex_daemon() {
  pkill -x mydaemon 2>/dev/null
  exec mydaemon --flag1 value1 --flag2 value2 \
    --long-flag value3
}
```
config 只写:
```
exec_always --no-startup-id exec-wrappers.sh launch_complex_daemon
```

### §2.2 引号嵌套规则

Bash 引号在 sway `exec_always` 里经过两层解析: sway 先解析一次,传给 shell 再解析一次。

**规则**: sway config 里用双引号包裹传给 shell 的字符串; shell 层再用单引号保留内部特殊字符。

**带多个 `-e` 参数的 notify-send 示例**:
```
exec_always --no-startup-id bash -c "pkill -x swaync; swaync -s 2>&1 | grep -v 'connection closed' &"
```

外层 `"..."` 给 sway,内层 `'...'` 给 bash。内层始终用单引号避免冲突。

### §2.3 `patch` 工具的 `"` 序列化陷阱

Hermes `patch` 工具把整个文件当字符串处理,采用 JSON 编码序列化。sway config 中含 `"` 的行写入时,JSON 反序列化可能额外转义。这是 **Hermes 端的问题**,不是 sway 的问题。

规避方法:
- 写 sway config 时用 `write_file` 而非 `patch`,避免序列化层干预
- sway config 中所有 `"` 保持原样写入,不需要额外反斜杠
- 如果必须用 `patch` 编辑 config,先 `cat` 确认实际写入内容正确

### §2.4 pgrep -ax 优于 ps | grep

验证进程存活时,用 `pgrep` 替代 `ps | grep`:

| 方式 | 问题 |
|------|------|
| `ps aux \| grep swayidle` | grep 进程自身可能被匹配;输出需二次解析;信号需要用`kill`命令单独发 |
| `pgrep -x swayidle` | 精确匹配进程名,只返回 PID,可直接配合 `pkill` |

验证 daemon 存活:
```
pgrep -x swayidle > /dev/null && echo "running" || echo "dead"
```

### §2.5 sway reload 不清理旧进程

**这是 `exec_always` 最隐蔽的问题**: `sway reload` 重新执行所有 `exec_always`,但**不会**先 stop 之前启动的进程。旧进程和新进程共存:

- swayidle: 两个实例同时监听 idle 事件,行为不可预测
- UxPlay: 两个进程争用同一个端口,第二个启动失败报 `Address already in use`
- waybar: 两个实例同时渲染,widget 状态震荡

**正确的模式**: 每个 `exec_always` 命令必须自包含去重逻辑,不能依赖 sway 帮你清理。

```bash
# 通用 wrapper — 放在 exec-wrappers.sh 中
launch_singleton() {
  local name="$1"; shift
  pkill -x "$name" 2>/dev/null
  sleep 0.1
  exec "$@"
}
```

config 中:
```
exec_always --no-startup-id exec-wrappers.sh launch_singleton swayidle -w ...
```

`sleep 0.1` 给被杀的进程释放资源 (端口、锁文件),尤其是 UxPlay 等监听 socket 的程序。

## §3 验证清单

修改 sway config 后验证流程:

1. 语法检查: `sway --validate` / `sway -c ~/.config/sway/config 2>&1`
   (不加 `-c` 默认检查当前 config)
2. reload 验证: `sway reload` 后 `pgrep -ax <name>` 看进程计数,不应超过 1
3. 端口冲突: `ss -tlnp | grep <port>` 确认单进程监听
4. 功能测试: 等 idle timeout 触发 screensaver / 投屏可连接
5. 日志检查: `journalctl --user -n 20 -u sway-session.target --grep ERROR`

## §4 本 skill 自包含,无需外部资源

本 skill 不依赖任何外部文件。所有 wrapper 示例可以直接复制到
`~/.config/sway/exec-wrappers.sh` 并在 sway config 中 `source` 使用。

## 历史上下文

- 核心模式源自对 `exec_always` 去重的长期实践
- §2.5 reload 不清理行为在 swayidle 屏保和 UxPlay 投屏配置中暴露最严重
  (reload 后重复进程导致端口冲突和 idle 事件紊乱)
- §2.1–§2.2 引号/续行规则来自 man 5 sway 和实际配置中遇到的行解析问题
