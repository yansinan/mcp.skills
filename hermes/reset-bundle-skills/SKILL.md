---
name: reset-bundle-skills
description: >-
  批量恢复 bundled skills 到上游版本。用于升级后大量 skill 被标记
  user_modified、用户想丢弃本地改动回到 bundle 基线、或对 profile
  做批量 rebaseline。优先用 hermes skills reset CLI 逐个恢复，
  批量循环用 terminal(background=true) 避免超时。
version: 1.1.0
author: hermes-agent-local
license: MIT
metadata:
  hermes:
    tags: [skills, bundle, reset, restore, manifest, maintenance, batch]
    related_skills: [daily-system-maintenance]
---

# 批量重置 bundled skills

## 何时使用

- 用户明确要"批量 reset 所有 bundled skill"
- 升级后大量 bundled skill 被标记 `user_modified`
- 丢弃所有本地改动，恢复到上游 bundled 版本
- 需要恢复前的 dry-run 清单

## 核心原则

1. **bundle 源只读** — 不修改 `skills/` 里的 bundle 内容。
2. **批量 = 逐个 reset 的循环** — Hermes 没有内置 `--all` 子命令。
3. **优先 dry-run** — 先列出目标，再执行恢复。
4. **明确语义**：
   - `--restore` = 删除用户副本 + 重新从 bundle 复制
   - `--no-restore`/`--rebaseline` = 只清 manifest，保留用户副本

## 推荐流程

### 1. 枚举目标清单

```bash
cat ~/.hermes/skills/.bundled_manifest | sed 's/:.*//'
```

### 2. 批量恢复（一个命令完成）

> ⚠️ 70+ skill 顺序跑约 **76–96s**（2026-06-29 实测 72 个 = 76s），
> 前台 terminal 默认 60s 超时。
> **必须用 `terminal(background=true, notify_on_complete=true)`**。

**优先调用现成脚本** —— `scripts/reset_bundled_skills.py` 已经封装了
"读 manifest → 逐个 reset → 写日志 → DONE 标记"的完整循环。
脚本位于 skill 自带的 `scripts/` 子目录下（绝对路径：
`~/.hermes/skills/local_share/hermes/reset-bundle-skills/scripts/reset_bundled_skills.py`）。
在 background terminal 中直接调用：

```bash
python3 ~/.hermes/skills/local_share/hermes/reset-bundle-skills/scripts/reset_bundled_skills.py
# 或 backup 手动循环：见下
```

如果脚本不可用（路径漂移、文件被误删），手动循环 fallback：

```bash
# ⚠️ background subshell 不会 source ~/.bashrc，必须用绝对路径
HERMES=/home/dr/.local/bin/hermes
for name in $(cat ~/.hermes/skills/.bundled_manifest | sed 's/:.*//'); do
  echo "$(date +%H:%M:%S) $name" >> /tmp/reset-bundle.log
  $HERMES skills reset "$name" --restore --yes 2>&1 >> /tmp/reset-bundle.log
done
echo "DONE" >> /tmp/reset-bundle.log
```

### 3. 验证

```bash
grep -c "Restored" /tmp/reset-bundle.log     # 确认恢复数量
tail -5 /tmp/reset-bundle.log                  # DONE 在末尾
rm -f /tmp/reset-bundle.log                    # 清理

# Parse 错误 smoke test（必须）—— 重置后任何 skill 的 frontmatter
# 或 references 损坏都会在这里暴露
hermes skills list 2>&1 | grep -iE "error|invalid|warn" | head -10
hermes skills list 2>&1 | wc -l               # 约 150 行（72 bundled + 50~70 local）
```

### 4. （可选）重建 manifest 基线

如果只想清除 manifest 的变更标记而不删除本地副本：

```bash
hermes skills reset <name> --restore --rebaseline
```

> ⚠️ **不存在 `hermes skills sync` 子命令** —— 截至 `hermes` v0.17.0（2026-06），
> `skills` 的子命令是 `browse search install inspect list check update audit
> uninstall reset list-modified diff opt-out opt-in repair-official publish
> snapshot tap config`。Manifest 基线由 `reset --restore` 自身隐式重建，无需额外命令。
> 误用 `hermes skills sync --quiet` 会得到：
> `argument skills_action: invalid choice: 'sync'`

## 常见坑

| 问题 | 正确做法 |
|------|----------|
| 把 `--yes` 当成 reset 参数 | reset 参数是 `--restore` |
| 前台跑 70+ skill 循环超时 | 用 `terminal(background=true, notify_on_complete=true)` |
| 恢复后 bundle 版本还在 user_modified | 重建 manifest：`hermes skills reset --restore --rebaseline` |
| 误以为 `--all` 存在 | Hermes 只支持逐个 reset，外部循环是唯一批量方式 |
| `hermes skills sync --quiet` 想重建 manifest | 不存在 `sync` 子命令；`reset --restore` 已隐式重建 |
| 批量循环里 `hermes: command not found` | 即使 `~/.bashrc` 有 `export PATH="$HOME/.local/bin:$PATH"`，**background subshell 也不会 source 它** —— 用绝对路径 `HERMES=/home/dr/.local/bin/hermes` 或显式 export |
| **忽略 `scripts/reset_bundled_skills.py` 现成脚本，自己重写 shell 循环** | skill 目录里已有封装好的 Python 脚本。先看 `scripts/`，再看 `references/`，最后才手写循环。脚本路径：`~/.hermes/skills/local_share/hermes/reset-bundle-skills/scripts/reset_bundled_skills.py`（绝对路径以 `~/.hermes/skills/local_share/hermes/reset-bundle-skills/` 为准，bundle 路径会随版本变化） |
| **误以为 `related_skills: daily-system-maintenance` 是已存在的 skill** | 截至 2026-06-29 `daily-system-maintenance` 还不存在，是个 planned umbrella。四步曲 cron 直接注入 prompt，不依赖该 skill |
| **耗时估算偏差**：实际 72 个 = 76s（不是 ~96s） | 用 `notify_on_complete=true` 后台跑，不要前台 60s 死等 |

## 参考文件

- `references/batch-reset-bundled-skills.md`：行为边界和语义说明
