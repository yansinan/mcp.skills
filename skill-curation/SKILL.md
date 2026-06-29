---
name: skill-curation
description: "Audit, reorganize, and consolidate existing user-local skills by abstraction hierarchy (sway > waybar > mpv > app). Physically absorb (not copy) — reference style, scoped content, verifiable references, clean cuts between topics. Merge two complementary skills into one when neither is clearly higher-abstraction (see `references/merge-two-skills-into-one.md`)."
metadata:
  hermes:
    tags: [hermes, skills, curation, organization, deduplication, abstraction-level]
related_skills: [hermes-agent-skill-authoring, hermes-external-skills, codebase-refactor-audit]
---

## 分层吸收

按抽象层级排序,重复内容吸收到更高层:

    sway > waybar > mpv/wireplumber > 应用(NCM/UxPlay)

物理吸收:把重复内容直接复制到高层 skill 的 SKILL.md,删除低层的重复。不留"参见"存根。

## 吸收质量门禁 (absorb, don't copy)

合并/吸收完成后,用以下四项检查确认结果是"吸收"而非"复制":

1.  **语言风格** — 是否在叙述"修了什么"而非"应该怎么做"?
    - 复制: "Helix 上 swayidle 屏保修复时遇到了 X 问题"
    - 吸收: "exec_always 的做法是 Y,因为 Z"
    - 技能是 reference material,不是会话纪要。例子可以用,但要当作通用规律来讲。

2.  **范围边界** — 每一节内容和 skill 主题是否直接相关?
    - 无关内容直接移除(单独成 skill),不要 append 在末尾
    - 例: sway exec_always skill 里不应包含跨机 Hermes API 探活

3.  **引用完整性** — 所有引用的 support file 存在吗?
    - references/ templates/ scripts/ 下的文件必须真实存在
    - 不存在就删除引用,或创建实际文件。不留 dangling link

4.  **切割清晰** — 如果内容属于另一个主题,独立成 skill,不硬塞
    - "跨机分享流程"不属于 sway exec_always,应独立
    - 同一个 PR/session 处理了多个主题 → 拆到对应 skill

## 合并双技能

当无法确立层级关系（两者同级,又互有重叠）,直接合并成一个:

1.  把两个 skill 的全部精华集成到新 SKILL.md
2.  `description` 反映合并后的范围
3.  删除被吸收的 skill (`skill_manage action=delete absorbed_into=<新 umbrella>`)

## 实战参考

- `references/git-commit-local-share-archive-orphans-2026-06-28.md` —
  local_share 仓库 `git add -A` 时如何处理 `.archive/` 孤儿目录、
  phantom modified（mtime 变化但内容相同的"假 modified"）、
  以及为什么 `.gitignore` 不生效的问题。

- `references/skill-optimization-patterns.md` — 迁移/优化 SKILL.md 时的精简原则
4.  在 reference 里注明吸收来源

## 执行流程

```text
1. skills_list/local_share → 识别重叠 skill
2. skill_view(A) + skill_view(B) → 对比内容
3. 判断层级关系:
   - 有层级 → 吸收到高层
   - 无层级 → 合并为新 skill (或吸收到已有 umbrella)
4. 写文件前先过质量门禁四项检查
5. 写两个 target (hermetic + repo), diff 验证一致
6. git commit + push
```
