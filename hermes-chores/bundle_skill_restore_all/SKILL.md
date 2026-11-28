---
name: bundle-skill-restore-all
description: >-
  Deprecated pointer to the canonical `reset-bundle-skills` skill, which
  batch-restores user-modified bundled skills. Kept only so older references
  to this skill name still resolve. Use `reset-bundle-skills` instead.
source: hermes
tags:
  - hermes
  - skills
  - bundled-skills
  - restore
  - batch
  - deprecated
---

# bundle-skill-restore-all — 已并入 `reset-bundle-skills`

**本技能已废弃，功能全部由 `reset-bundle-skills` 承担。**

| 旧文档里的说法 | 实际情况 |
|---|---|
| `hermes skills restore <name>` | ❌ 没有 `restore` 子命令。正确是 `hermes skills reset <name> --restore --yes` |
| `scripts/restore_all.py` | ❌ 脚本不存在。正确的是 `reset-bundle-skills/scripts/reset_bundled_skills.py` |
| `~/.hermes/skills/local/hermes_chores/...` 路径 | ❌ 目录不存在。脚本在 `~/.hermes/skills/local_share/hermes/reset-bundle-skills/scripts/` |

**唯一推荐路径**：

```bash
PYTHONPATH=/home/dr/.hermes/hermes-agent \
  /home/dr/.hermes/hermes-agent/venv/bin/python \
  ~/.hermes/skills/local_share/hermes/reset-bundle-skills/scripts/reset_bundled_skills.py --restore
```

查看哪些被改过：`hermes skills list-modified`
仅列出目标不改动：`... reset_bundled_skills.py --dry-run`

完整语义、坑位表和 `repair-official` 回退策略见 **`reset-bundle-skills`** 技能。
