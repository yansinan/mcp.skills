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

> ⚠️ 70+ skill 顺序跑约 96s，前台 terminal 默认 60s 超时。
> **必须用 `terminal(background=true, notify_on_complete=true)`**。

在 Hermes 中执行该终端命令（background + notify）：

```python
# 在 Hermes terminal 中：
terminal(background=true, notify_on_complete=true):
  for name in $(cat ~/.hermes/skills/.bundled_manifest | sed 's/:.*//'); do
    echo "$(date +%H:%M:%S) $name" >> /tmp/reset-bundle.log
    hermes skills reset "$name" --restore --yes 2>&1 >> /tmp/reset-bundle.log
  done
  echo "DONE" >> /tmp/reset-bundle.log
```

### 3. 验证

```bash
grep -c "Restored" /tmp/reset-bundle.log     # 确认恢复数量
tail -5 /tmp/reset-bundle.log                  # DONE 在末尾
rm -f /tmp/reset-bundle.log                    # 清理
hermes skills list                             # 检查 skill 状态
```

### 4. （可选）重建 manifest 基线

如果只想清除 manifest 的变更标记而不删除本地副本：

```bash
hermes skills reset <name> --restore --rebaseline
```

## 常见坑

| 问题 | 正确做法 |
|------|----------|
| 把 `--yes` 当成 reset 参数 | reset 参数是 `--restore` |
| 前台跑 70+ skill 循环超时 | 用 `terminal(background=true, notify_on_complete=true)` |
| 恢复后 bundle 版本还在 user_modified | 重建 manifest：`hermes skills sync --quiet` |
| 误以为 `--all` 存在 | Hermes 只支持逐个 reset，外部循环是唯一批量方式 |

## 参考文件

- `references/batch-reset-bundled-skills.md`：行为边界和语义说明
