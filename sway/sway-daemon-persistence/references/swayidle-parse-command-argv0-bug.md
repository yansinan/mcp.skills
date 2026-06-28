# swayidle config parser: timeout 命令必须用引号包裹 (单 token 限制)

## 核心误区

swayidle 的 config parser **只取命令行的第一个空格分隔的 token** 作为要执行的命令。
所有带参数的命令必须用引号包裹为一个整体 token，否则参数被丢弃。

## 案例

```
# ❌ 错误: parser 只取 ~/Scripts/sway-session, --mark-idle 被丢弃
timeout 60 ~/Scripts/sway-session --mark-idle resume ~/Scripts/sway-session --mark-active
# → 实际执行: sh -c "~/Scripts/sway-session"  (无 --mark-idle → 进入 daemon 模式, 永不退出!)

# ✅ 正确: 引号包裹, 整个命令作为单 token 传给 sh -c
timeout 60 '~/Scripts/sway-session --mark-idle' resume '~/Scripts/sway-session --mark-active'
# → 实际执行: sh -c "~/Scripts/sway-session --mark-idle"  (正确创建 idle marker)
```

## 症状

| 症状 | 根因 | 修复 |
|------|------|------|
| mark-idle 60s 不触发, marker 不创建 | `timeout 60` 命令无引号 → `--mark-idle` 被丢弃 | 加引号 |
| swayidle 下有永不退出的 sh+python 子进程 | 同上 → sway-session 无参数进入 daemon 循环 | 加引号 |
| screen-off 3600s 不触发 | `timeout 3600` 命令无引号 | 加引号 |
| suspend-if-night 3600s 不触发 | 同上 | 加引号 |
| **screensaver 30s 正常** | 30s 行已有引号 `'...--screensaver-day'` | 不修 (已对) |

## 诊断

```bash
# 看 swayidle 子进程是否正常 (应无长期存活的 sh/python)
pstree -aps $(pidof swayidle)
# 期望: swayidle ─── (无子进程, 或极短命子进程)
# 异常: swayidle ─── sh -c sway-session ─── python3 sway-session  (长期存活, 需要 4+ 小时)
```

## 注意

- 只有 30s screensaver-day 行是**有引号**的 (当初写的人只修复了它), 别的行全错了。
- config 注释已写明: `# 注意: parse_command 只取第一个 token, 带参命令必须封装为脚本。`
- 但人眼容易忽略, 因为 30s 行工作, 错误地把 60s/3600s 的不工作归咎于其他原因。