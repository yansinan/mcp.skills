# 批量重置 bundled skills

本参考文件记录行为边界：

- `skills_sync.py` 的主同步逻辑**不会**自动恢复 `user_modified` 的 bundled skill。
- 逐个恢复的入口是 `reset_bundled_skill(name, restore=True)`。
- Hermes 当前没有内置 `hermes skills reset --all`。
- `hermes skills reset <name>` 的文档语义是单个 skill；批量行为需要由外层循环实现。
- 不要把 `--yes` 当成 reset 参数；reset 路径使用的是 `--restore` 和 `--now`。

推荐批量流程：

1. 枚举 bundled skills 名称。
2. 先 dry-run 打印会被处理的 skill。
3. 对每个 skill 调用 `reset_bundled_skill(name, restore=True)`。
4. 最后重新跑一次 `sync_skills(quiet=True)` 做基线核验。

如果用户只想重建 manifest 基线而不删除本地副本，把 `restore=False` 作为单独模式保留。
