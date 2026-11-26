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
# ⚠️ 2026-06-30 实测：/tmp tmpfs 在 x1tablet 上是 7.7G 满，
#    tee 写到 /tmp 会 No space left on device，必须把日志改到 /home
HERMES=/home/dr/.local/bin/hermes
LOG=/home/dr/.hermes/logs/reset-bundle-$(date +%Y%m%d).log
mkdir -p /home/dr/.hermes/logs
for name in $(cat ~/.hermes/skills/.bundled_manifest | sed 's/:.*//'); do
  echo "$(date +%H:%M:%S) $name" >> "$LOG"
  $HERMES skills reset "$name" --restore --yes >> "$LOG" 2>&1
done
echo "$(date +%H:%M:%S) DONE" >> "$LOG"
```

**脚本必须在 hermes-agent 目录下运行**：

⚠️ 2026-06-30 实测：reset_bundled_skills.py 内部 `from tools.skills_sync import`，
依赖 PYTHONPATH。从 skill 自身目录运行会 ModuleNotFoundError。
**必须**同时满足两件事：(a) cd 到 hermes-agent/ 源码树，(b) 把该目录
加进 PYTHONPATH。仅 `cd` 不会自动注入路径，仍会报 ModuleNotFoundError。
必须用 venv 里的 python（系统 python3 通常没装 hermes 的依赖）：

```bash
PYTHONPATH=/home/dr/.hermes/hermes-agent \
  /home/dr/.hermes/hermes-agent/venv/bin/python \
  ~/.hermes/skills/local_share/hermes/reset-bundle-skills/scripts/reset_bundled_skills.py --restore
```

2026-07-02 实测：`python3 reset_bundled_skills.py` → ModuleNotFoundError；
补上 PYTHONPATH 后 72 个 skill 11s 内全部 OK。

### 3. 验证

```bash
LOG=/home/dr/.hermes/logs/reset-bundle-$(date +%Y%m%d).log
grep -c "Restored" "$LOG"      # 确认恢复数量
tail -5 "$LOG"                 # DONE 在末尾

# Parse 错误 smoke test（必须）—— 重置后任何 skill 的 frontmatter
# 或 references 损坏都会在这里暴露
hermes skills list 2>&1 | grep -iE "error|invalid|warn" | head -10
hermes skills list 2>&1 | wc -l               # 约 150 行（72 bundled + 50~70 local）
```

> ⚠️ 日志写 `/home/dr/.hermes/logs/`，**不要写 /tmp**（x1tablet 的 /tmp 是 8G tmpfs，可能写满）。

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
| **`tee` 写到 /tmp 报 `No space left on device`** | x1tablet 上 /tmp 是 8G tmpfs，cron 启动时可能 100% 满（用户不可见文件撑满）。**永远把循环日志写到 `/home/dr/.hermes/logs/reset-bundle-YYYYMMDD.log`**，不要写 /tmp |
| **`cd hermes-agent` 后仍报 `ModuleNotFoundError: No module named 'tools'`** | 2026-07-02 实测：`cd` 不会自动把 cwd 加进 `sys.path`，`from tools.skills_sync import` 仍找不到模块。**必须显式 `PYTHONPATH=/home/dr/.hermes/hermes-agent`**，并且用 venv 里的 python：`/home/dr/.hermes/hermes-agent/venv/bin/python`。系统 `python3` 缺少 hermes 依赖也会失败 |
| **reset_bundled_skills.py 报 `ModuleNotFoundError: No module named 'tools'`** | 脚本内部 `from tools.skills_sync import`，必须 `cd /home/dr/.hermes/hermes-agent && python3 ...` 运行。从 skill 自身目录或 cron cwd 跑都会失败 |
| **reset_bundled_skills.py 报 `ImportError: cannot import name 'reset_bundled_skill' from 'tools.skills_sync'`**（2026-11-27 实测） | `reset_bundled_skill` 已从 `tools.skills_sync` 移到 `tools.skills_sync_bundled_ops`。脚本里拆成两行 import：`from tools.skills_sync import _discover_bundled_skills, _get_bundled_dir` + `from tools.skills_sync_bundled_ops import reset_bundled_skill` |
| **批量 reset 大量返回 `FAIL bundled_missing`**（2026-11-27 实测） | 该 skill 在 repo `skills/` 树里没有副本（只存在于 `optional-skills/`）。`reset` 只能解析 repo 树内的路径 → 改用 `hermes skills repair-official <name> --restore --yes` 恢复，会自动备份到 `~/.hermes/skills/.restore-backups/official-optional-<ts>` |
| **reset 只跑一遍不够**：manifest 里的可选 skill 不在 bundle 目录 | 遍历 `.bundled_manifest` 全部名字（`sed 's/:.*//'`），而不是只跑 `_discover_bundled_skills(bundled_dir)` 返回的子集——后者只覆盖 repo 内的 44 个 |
| **ccr 把 terminal 输出压成空字符串** | `df -h`、`ls -la /tmp/` 等长输出可能被 headroom ccr 压到 <1KB。绕道：把输出 redirect 到 `/home/dr/.hermes/_chk.txt`，用 `read_file` 读出，或 `split -l 1` 拆成单行文件逐行 read |

## 参考文件

- `references/batch-reset-bundled-skills.md`：行为边界和语义说明
